/* SPDX-License-Identifier: GPL-2.0 */
/*
 * nginx_aware - Low-overhead process-aware BPF scheduler for Nginx
 *
 * Asymmetric design (following the project's key finding):
 * - Only intervene for threads we want to DEprioritize (CPU hogs)
 * - Everything else (nginx, wrk2, system) uses SCX_DSQ_GLOBAL fast path
 * - Idle CPU fast path: all threads -> SCX_DSQ_LOCAL (zero overhead)
 * - Selective preemption: nginx can kick CPU hog threads that ran >= 2ms
 *
 * Performance optimizations:
 * - BPF task local storage caches classification per-task (one comm read per
 *   task lifetime instead of per scheduling event)
 * - CPU scan limited to actual nr_cpus
 *
 * Thread classification:
 *   "stress-ng*" -> CPU hog (deprioritized to BACKGROUND_DSQ, 20ms slice)
 *   "nginx"      -> foreground (identified for preemption kicks)
 *   everything   -> normal (SCX_DSQ_GLOBAL, framework fast path)
 */
#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

UEI_DEFINE(uei);

#define BACKGROUND_DSQ  0x201

#define DEFAULT_SLICE_NS     5000000ULL   /* 5ms */
#define BACKGROUND_SLICE_NS  20000000ULL  /* 20ms */
#define BG_MIN_RUN_NS        2000000ULL   /* 2ms minimum before preemption */
#define MAX_CPUS 256

/* Task classification values */
#define TASK_UNKNOWN  0
#define TASK_NGINX    1
#define TASK_CPU_HOG  2
#define TASK_NORMAL   3

/*
 * Per-task cached classification. Avoids reading comm on every scheduling event.
 */
struct task_class {
	u8 class;
};

struct {
	__uint(type, BPF_MAP_TYPE_TASK_STORAGE);
	__uint(map_flags, BPF_F_NO_PREALLOC);
	__type(key, int);
	__type(value, struct task_class);
} task_class_map SEC(".maps");

/*
 * bg_running: per-CPU flag indicating whether a CPU hog thread is running.
 */
struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, MAX_CPUS);
	__type(key, u32);
	__type(value, u8);
} bg_running SEC(".maps");

/*
 * bg_start_ns: per-CPU timestamp when current CPU hog thread started.
 */
struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, MAX_CPUS);
	__type(key, u32);
	__type(value, u64);
} bg_start_ns SEC(".maps");

/* Actual number of CPUs, set in init */
static u32 nr_cpus;

/*
 * Classify task once, cache the result.
 */
static u8 classify_task(struct task_struct *p)
{
	struct task_class *tc;

	tc = bpf_task_storage_get(&task_class_map, p, 0, 0);
	if (tc && tc->class != TASK_UNKNOWN)
		return tc->class;

	/* First time seeing this task — read comm and classify */
	char comm[16];
	u8 result = TASK_NORMAL;

	if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) >= 0) {
		/* "nginx" */
		if (comm[0] == 'n' && comm[1] == 'g' && comm[2] == 'i' &&
		    comm[3] == 'n' && comm[4] == 'x')
			result = TASK_NGINX;
		/* "stress-ng" prefix */
		else if (comm[0] == 's' && comm[1] == 't' && comm[2] == 'r' &&
			 comm[3] == 'e' && comm[4] == 's' && comm[5] == 's' &&
			 comm[6] == '-' && comm[7] == 'n' && comm[8] == 'g')
			result = TASK_CPU_HOG;
	}

	/* Cache for future calls */
	tc = bpf_task_storage_get(&task_class_map, p, 0,
				  BPF_LOCAL_STORAGE_GET_F_CREATE);
	if (tc)
		tc->class = result;

	return result;
}

s32 BPF_STRUCT_OPS(nginx_aware_select_cpu, struct task_struct *p,
		   s32 prev_cpu, u64 wake_flags)
{
	bool is_idle = false;
	s32 cpu;
	u8 cls;

	cpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);
	cls = classify_task(p);

	if (is_idle) {
		u64 slice = (cls == TASK_CPU_HOG) ?
			    BACKGROUND_SLICE_NS : DEFAULT_SLICE_NS;
		scx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, 0);
		return cpu;
	}

	/*
	 * No idle CPU. If this is nginx, try to preempt a CPU running a
	 * CPU hog thread that has run >= 2ms.
	 */
	if (cls == TASK_NGINX) {
		u64 now = bpf_ktime_get_ns();
		u32 limit = nr_cpus;
		u32 i;

		if (limit > MAX_CPUS)
			limit = MAX_CPUS;

		bpf_for(i, 0, limit) {
			u32 key = i;
			u8 *running = bpf_map_lookup_elem(&bg_running, &key);
			if (!running || !*running)
				continue;

			u64 *start = bpf_map_lookup_elem(&bg_start_ns, &key);
			if (start && (now - *start) >= BG_MIN_RUN_NS) {
				scx_bpf_kick_cpu(i, SCX_KICK_PREEMPT);
				break;
			}
		}
	}

	return cpu;
}

void BPF_STRUCT_OPS(nginx_aware_enqueue, struct task_struct *p,
		    u64 enq_flags)
{
	if (classify_task(p) == TASK_CPU_HOG) {
		scx_bpf_dsq_insert(p, BACKGROUND_DSQ, BACKGROUND_SLICE_NS,
				    enq_flags);
	} else {
		scx_bpf_dsq_insert(p, SCX_DSQ_GLOBAL, DEFAULT_SLICE_NS,
				    enq_flags);
	}
}

void BPF_STRUCT_OPS(nginx_aware_dispatch, s32 cpu, struct task_struct *prev)
{
	/* Background DSQ drained only when GLOBAL is empty */
	scx_bpf_dsq_move_to_local(BACKGROUND_DSQ);
}

void BPF_STRUCT_OPS(nginx_aware_running, struct task_struct *p)
{
	if (classify_task(p) == TASK_CPU_HOG) {
		u32 key = bpf_get_smp_processor_id();
		u8 val = 1;
		u64 now = bpf_ktime_get_ns();
		bpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
		bpf_map_update_elem(&bg_start_ns, &key, &now, BPF_ANY);
	}
}

void BPF_STRUCT_OPS(nginx_aware_stopping, struct task_struct *p,
		    bool runnable)
{
	if (classify_task(p) == TASK_CPU_HOG) {
		u32 key = bpf_get_smp_processor_id();
		u8 val = 0;
		bpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
	}
}

s32 BPF_STRUCT_OPS_SLEEPABLE(nginx_aware_init)
{
	nr_cpus = scx_bpf_nr_cpu_ids();
	return scx_bpf_create_dsq(BACKGROUND_DSQ, -1);
}

void BPF_STRUCT_OPS(nginx_aware_exit, struct scx_exit_info *ei)
{
	UEI_RECORD(uei, ei);
}

SCX_OPS_DEFINE(nginx_aware_ops,
	       .select_cpu	= (void *)nginx_aware_select_cpu,
	       .enqueue		= (void *)nginx_aware_enqueue,
	       .dispatch	= (void *)nginx_aware_dispatch,
	       .running		= (void *)nginx_aware_running,
	       .stopping	= (void *)nginx_aware_stopping,
	       .init		= (void *)nginx_aware_init,
	       .exit		= (void *)nginx_aware_exit,
	       .name		= "nginx_aware");
