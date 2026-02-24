/* SPDX-License-Identifier: GPL-2.0 */
/*
 * db_aware - Thread-aware BPF scheduler for database workloads
 *
 * Prioritizes latency-sensitive "query" threads over CPU-heavy "compaction"
 * threads by dispatching from separate DSQs in priority order.
 *
 * Classification via task comm name:
 *   "query*"   -> QUERY_DSQ (high priority, 3ms slice)
 *   "compact*" -> COMPACT_DSQ (low priority, 20ms slice)
 *   other      -> COMPACT_DSQ
 */
#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

UEI_DEFINE(uei);

#define QUERY_DSQ   0
#define COMPACT_DSQ 1

#define QUERY_SLICE_NS   3000000ULL   /* 3ms */
#define COMPACT_SLICE_NS 20000000ULL  /* 20ms */

static bool is_query_task(struct task_struct *p)
{
	char comm[16];

	if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
		return false;

	return (comm[0] == 'q' && comm[1] == 'u' && comm[2] == 'e' &&
		comm[3] == 'r' && comm[4] == 'y');
}

s32 BPF_STRUCT_OPS(db_aware_select_cpu, struct task_struct *p, s32 prev_cpu,
		   u64 wake_flags)
{
	bool is_idle = false;
	s32 cpu;

	cpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);
	if (is_idle) {
		u64 slice = is_query_task(p) ? QUERY_SLICE_NS : COMPACT_SLICE_NS;
		scx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, 0);
	}

	return cpu;
}

void BPF_STRUCT_OPS(db_aware_enqueue, struct task_struct *p, u64 enq_flags)
{
	if (is_query_task(p)) {
		scx_bpf_dsq_insert(p, QUERY_DSQ, QUERY_SLICE_NS, enq_flags);
	} else {
		scx_bpf_dsq_insert(p, COMPACT_DSQ, COMPACT_SLICE_NS, enq_flags);
	}
}

void BPF_STRUCT_OPS(db_aware_dispatch, s32 cpu, struct task_struct *prev)
{
	/* Always drain query DSQ first for low latency */
	if (!scx_bpf_dsq_move_to_local(QUERY_DSQ)) {
		scx_bpf_dsq_move_to_local(COMPACT_DSQ);
	}
}

s32 BPF_STRUCT_OPS_SLEEPABLE(db_aware_init)
{
	s32 ret;

	ret = scx_bpf_create_dsq(QUERY_DSQ, -1);
	if (ret)
		return ret;

	return scx_bpf_create_dsq(COMPACT_DSQ, -1);
}

void BPF_STRUCT_OPS(db_aware_exit, struct scx_exit_info *ei)
{
	UEI_RECORD(uei, ei);
}

SCX_OPS_DEFINE(db_aware_ops,
	       .select_cpu	= (void *)db_aware_select_cpu,
	       .enqueue		= (void *)db_aware_enqueue,
	       .dispatch	= (void *)db_aware_dispatch,
	       .init		= (void *)db_aware_init,
	       .exit		= (void *)db_aware_exit,
	       .name		= "db_aware");
