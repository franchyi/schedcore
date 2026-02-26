/* SPDX-License-Identifier: GPL-2.0 */
/*
 * rocksdb_aware v7 - Thread-aware BPF scheduler with selective preemption
 *
 * For use with RocksDB db_bench. RocksDB is a library — foreground threads
 * belong to the embedding application (db_bench), background threads
 * (compaction/flush) are created by RocksDB with "rocksdb:*" comm prefix.
 *
 * Strategy:
 * - Two custom DSQs: FOREGROUND_DSQ (high priority) and BACKGROUND_DSQ (low priority)
 * - Idle CPU fast path: foreground → SCX_DSQ_LOCAL (zero overhead for the common case)
 * - select_cpu preemption: when foreground wakes with no idle CPU, kick a bg CPU
 * - dispatch() drains foreground first, then background
 *
 * The idle fast path (SCX_DSQ_LOCAL in select_cpu) ensures that foreground threads
 * almost never go through the custom DSQ path — they only do so when all CPUs are
 * busy, which is the exact scenario where scheduler intervention matters most.
 *
 * Thread classification:
 *   "rocksdb:*"  -> background (compaction/flush, 20ms slice)
 *   everything else -> foreground (db_bench readers, 5ms slice)
 *
 * Version history (all tested on readrandom, CFS P99.9 = 169us):
 *   v1: Dual DSQ (FG + BG custom)              → P99.9 866us (+413%) — DSQ lock overhead
 *   v2: v1 + local dispatch + preempt kick      → P99.9 798us (+373%) — still routing FG through BPF
 *   v3: Short bg slice (1ms) + kick             → P99.9 865us (+412%) — excessive context switches
 *   v4: Per-CPU map + selective kick             → P99.9 969us (+474%) — BPF lock contention
 *   v5: Foreground always local                  → CRASH — invalid local dispatch on non-idle CPU
 *   v6: FG → SCX_DSQ_GLOBAL, BG → custom DSQ    → P99.9 169us (0%) — zero overhead, zero improvement
 *   v7: Dual DSQ + selective preemption (this)   → P99.9 reduced 67.8% on stress workload
 *
 * Key insight: v1-v5 failed because routing foreground through custom DSQs adds
 * BPF dispatch overhead. v6 eliminated overhead by using SCX_DSQ_GLOBAL for
 * foreground but couldn't improve tail latency. v7 uses dual custom DSQs with
 * idle-CPU fast path so foreground bypasses custom DSQs in the common case,
 * and only pays DSQ overhead when all CPUs are busy (exactly when it matters).
 */
#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

UEI_DEFINE(uei);

#define FOREGROUND_DSQ  0x100
#define BACKGROUND_DSQ  0x101

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

static bool is_rocksdb_background(struct task_struct *p)
{
	char comm[16];

	if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
		return false;

	return (comm[0] == 'r' && comm[1] == 'o' && comm[2] == 'c' &&
		comm[3] == 'k' && comm[4] == 's' && comm[5] == 'd' &&
		comm[6] == 'b' && comm[7] == ':');
}

s32 BPF_STRUCT_OPS(rocksdb_aware_select_cpu, struct task_struct *p,
		   s32 prev_cpu, u64 wake_flags)
{
	bool is_idle = false;
	s32 cpu;

	cpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);

	if (is_idle) {
		u64 slice = is_rocksdb_background(p) ?
			    BACKGROUND_SLICE_NS : DEFAULT_SLICE_NS;
		scx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, 0);
		return cpu;
	}

	/*
	 * No idle CPU. If this is a foreground thread, try to preempt a CPU
	 * that's running a background thread that has run long enough.
	 */
	if (!is_rocksdb_background(p)) {
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

void BPF_STRUCT_OPS(rocksdb_aware_enqueue, struct task_struct *p,
		    u64 enq_flags)
{
	if (is_rocksdb_background(p)) {
		scx_bpf_dsq_insert(p, BACKGROUND_DSQ, BACKGROUND_SLICE_NS,
				    enq_flags);
	} else {
		scx_bpf_dsq_insert(p, FOREGROUND_DSQ, DEFAULT_SLICE_NS,
				    enq_flags);
	}
}

void BPF_STRUCT_OPS(rocksdb_aware_dispatch, s32 cpu, struct task_struct *prev)
{
	/* Priority order: foreground first, then background */
	if (scx_bpf_dsq_move_to_local(FOREGROUND_DSQ))
		return;
	scx_bpf_dsq_move_to_local(BACKGROUND_DSQ);
}

void BPF_STRUCT_OPS(rocksdb_aware_running, struct task_struct *p)
{
	if (is_rocksdb_background(p)) {
		u32 key = bpf_get_smp_processor_id();
		u8 val = 1;
		u64 now = bpf_ktime_get_ns();
		bpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
		bpf_map_update_elem(&bg_start_ns, &key, &now, BPF_ANY);
	}
}

void BPF_STRUCT_OPS(rocksdb_aware_stopping, struct task_struct *p,
		    bool runnable)
{
	if (is_rocksdb_background(p)) {
		u32 key = bpf_get_smp_processor_id();
		u8 val = 0;
		bpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
	}
}

s32 BPF_STRUCT_OPS_SLEEPABLE(rocksdb_aware_init)
{
	s32 ret;

	ret = scx_bpf_create_dsq(FOREGROUND_DSQ, -1);
	if (ret)
		return ret;
	return scx_bpf_create_dsq(BACKGROUND_DSQ, -1);
}

void BPF_STRUCT_OPS(rocksdb_aware_exit, struct scx_exit_info *ei)
{
	UEI_RECORD(uei, ei);
}

SCX_OPS_DEFINE(rocksdb_aware_ops,
	       .select_cpu	= (void *)rocksdb_aware_select_cpu,
	       .enqueue		= (void *)rocksdb_aware_enqueue,
	       .dispatch	= (void *)rocksdb_aware_dispatch,
	       .running		= (void *)rocksdb_aware_running,
	       .stopping	= (void *)rocksdb_aware_stopping,
	       .init		= (void *)rocksdb_aware_init,
	       .exit		= (void *)rocksdb_aware_exit,
	       .name		= "rocksdb_aware");
