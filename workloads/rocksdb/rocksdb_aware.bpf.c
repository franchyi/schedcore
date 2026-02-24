/* SPDX-License-Identifier: GPL-2.0 */
/*
 * rocksdb_aware v6 - Minimal-overhead thread-aware BPF scheduler
 *
 * Strategy: only penalize background threads, let foreground use
 * the fast default path (SCX_DSQ_GLOBAL). This minimizes BPF
 * overhead for latency-sensitive foreground threads.
 *
 * - Foreground (non-rocksdb): SCX_DSQ_GLOBAL (framework default path)
 * - Background (rocksdb:*): BACKGROUND_DSQ with long slice, drained last
 * - dispatch() drains SCX_DSQ_GLOBAL implicitly, then BACKGROUND_DSQ
 *
 * Thread classification:
 *   "rocksdb:*"  -> background (compaction/flush, 20ms slice)
 *   everything else -> default global path (5ms slice)
 */
#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

UEI_DEFINE(uei);

#define BACKGROUND_DSQ  1

#define DEFAULT_SLICE_NS     5000000ULL   /* 5ms */
#define BACKGROUND_SLICE_NS  20000000ULL  /* 20ms */

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
		/* Fast path: idle CPU, dispatch directly to local */
		u64 slice = is_rocksdb_background(p) ?
			    BACKGROUND_SLICE_NS : DEFAULT_SLICE_NS;
		scx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, 0);
	}

	return cpu;
}

void BPF_STRUCT_OPS(rocksdb_aware_enqueue, struct task_struct *p,
		    u64 enq_flags)
{
	if (is_rocksdb_background(p)) {
		/* Background: low-priority DSQ, long slice */
		scx_bpf_dsq_insert(p, BACKGROUND_DSQ, BACKGROUND_SLICE_NS,
				    enq_flags);
	} else {
		/* Foreground: use global DSQ for minimal overhead */
		scx_bpf_dsq_insert(p, SCX_DSQ_GLOBAL, DEFAULT_SLICE_NS,
				    enq_flags);
	}
}

void BPF_STRUCT_OPS(rocksdb_aware_dispatch, s32 cpu, struct task_struct *prev)
{
	/*
	 * SCX_DSQ_GLOBAL is consumed automatically by the framework
	 * before calling dispatch(). So when we get here, global DSQ
	 * is already drained. Only need to drain background.
	 */
	scx_bpf_dsq_move_to_local(BACKGROUND_DSQ);
}

s32 BPF_STRUCT_OPS_SLEEPABLE(rocksdb_aware_init)
{
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
	       .init		= (void *)rocksdb_aware_init,
	       .exit		= (void *)rocksdb_aware_exit,
	       .name		= "rocksdb_aware");
