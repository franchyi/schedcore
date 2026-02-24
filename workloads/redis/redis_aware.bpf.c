/* SPDX-License-Identifier: GPL-2.0 */
/*
 * redis_aware - Thread-aware BPF scheduler for Redis with selective preemption
 *
 * Strategy:
 * - Two custom DSQs: FOREGROUND_DSQ (high priority) and BACKGROUND_DSQ (low priority)
 * - Idle CPU fast path: all threads → SCX_DSQ_LOCAL (zero overhead common case)
 * - select_cpu preemption: when foreground wakes with no idle CPU, kick a bg CPU
 * - dispatch() drains foreground first, then background
 *
 * Thread classification (from Redis source bio.c, iothread.c):
 *   "bio_*"        -> background (bio_close_file, bio_aof, bio_lazy_free)
 *   "redis-rdb*"   -> background (BGSAVE forked child)
 *   "redis-aof*"   -> background (BGREWRITEAOF forked child)
 *   everything else -> foreground (main event loop, io_thd_*, clients)
 */
#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

UEI_DEFINE(uei);

#define FOREGROUND_DSQ  0x200
#define BACKGROUND_DSQ  0x201

#define DEFAULT_SLICE_NS     5000000ULL   /* 5ms */
#define BACKGROUND_SLICE_NS  20000000ULL  /* 20ms */
#define BG_MIN_RUN_NS        2000000ULL   /* 2ms minimum before preemption */
#define MAX_CPUS 256

/*
 * bg_running: per-CPU flag indicating whether a background thread is running.
 */
struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, MAX_CPUS);
	__type(key, u32);
	__type(value, u8);
} bg_running SEC(".maps");

/*
 * bg_start_ns: per-CPU timestamp when current background thread started.
 */
struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, MAX_CPUS);
	__type(key, u32);
	__type(value, u64);
} bg_start_ns SEC(".maps");

static bool is_redis_background(struct task_struct *p)
{
	char comm[16];

	if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
		return false;

	/* bio_close_file, bio_aof, bio_lazy_free — match "bio_" prefix */
	if (comm[0] == 'b' && comm[1] == 'i' && comm[2] == 'o' &&
	    comm[3] == '_')
		return true;

	/* redis-rdb-bgsave — match "redis-r" prefix */
	if (comm[0] == 'r' && comm[1] == 'e' && comm[2] == 'd' &&
	    comm[3] == 'i' && comm[4] == 's' && comm[5] == '-' &&
	    comm[6] == 'r')
		return true;

	/* redis-aof-rewrite — match "redis-a" prefix */
	if (comm[0] == 'r' && comm[1] == 'e' && comm[2] == 'd' &&
	    comm[3] == 'i' && comm[4] == 's' && comm[5] == '-' &&
	    comm[6] == 'a')
		return true;

	return false;
}

s32 BPF_STRUCT_OPS(redis_aware_select_cpu, struct task_struct *p,
		   s32 prev_cpu, u64 wake_flags)
{
	bool is_idle = false;
	s32 cpu;

	cpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);

	if (is_idle) {
		u64 slice = is_redis_background(p) ?
			    BACKGROUND_SLICE_NS : DEFAULT_SLICE_NS;
		scx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, 0);
		return cpu;
	}

	/*
	 * No idle CPU. If this is a foreground thread, try to preempt a CPU
	 * that's running a background thread that has run long enough.
	 */
	if (!is_redis_background(p)) {
		u64 now = bpf_ktime_get_ns();
		u32 i;

		bpf_for(i, 0, MAX_CPUS) {
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

void BPF_STRUCT_OPS(redis_aware_enqueue, struct task_struct *p,
		    u64 enq_flags)
{
	if (is_redis_background(p)) {
		scx_bpf_dsq_insert(p, BACKGROUND_DSQ, BACKGROUND_SLICE_NS,
				    enq_flags);
	} else {
		scx_bpf_dsq_insert(p, FOREGROUND_DSQ, DEFAULT_SLICE_NS,
				    enq_flags);
	}
}

void BPF_STRUCT_OPS(redis_aware_dispatch, s32 cpu, struct task_struct *prev)
{
	/* Priority order: foreground first, then background */
	if (scx_bpf_dsq_move_to_local(FOREGROUND_DSQ))
		return;
	scx_bpf_dsq_move_to_local(BACKGROUND_DSQ);
}

void BPF_STRUCT_OPS(redis_aware_running, struct task_struct *p)
{
	if (is_redis_background(p)) {
		u32 key = bpf_get_smp_processor_id();
		u8 val = 1;
		u64 now = bpf_ktime_get_ns();
		bpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
		bpf_map_update_elem(&bg_start_ns, &key, &now, BPF_ANY);
	}
}

void BPF_STRUCT_OPS(redis_aware_stopping, struct task_struct *p,
		    bool runnable)
{
	if (is_redis_background(p)) {
		u32 key = bpf_get_smp_processor_id();
		u8 val = 0;
		bpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
	}
}

s32 BPF_STRUCT_OPS_SLEEPABLE(redis_aware_init)
{
	s32 ret;

	ret = scx_bpf_create_dsq(FOREGROUND_DSQ, -1);
	if (ret)
		return ret;
	return scx_bpf_create_dsq(BACKGROUND_DSQ, -1);
}

void BPF_STRUCT_OPS(redis_aware_exit, struct scx_exit_info *ei)
{
	UEI_RECORD(uei, ei);
}

SCX_OPS_DEFINE(redis_aware_ops,
	       .select_cpu	= (void *)redis_aware_select_cpu,
	       .enqueue		= (void *)redis_aware_enqueue,
	       .dispatch	= (void *)redis_aware_dispatch,
	       .running		= (void *)redis_aware_running,
	       .stopping	= (void *)redis_aware_stopping,
	       .init		= (void *)redis_aware_init,
	       .exit		= (void *)redis_aware_exit,
	       .name		= "redis_aware");
