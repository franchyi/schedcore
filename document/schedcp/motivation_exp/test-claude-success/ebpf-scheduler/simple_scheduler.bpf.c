// SPDX-License-Identifier: GPL-2.0
#include "scx_common.h"

char _license[] SEC("license") = "GPL";

/* Scheduler name - must be unique */
const char sched_name[] = "simple_ebpf_scheduler";

/* Statistics tracking */
struct stats {
    u64 cnt[4];
};

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, u32);
    __type(value, struct stats);
} stats_map SEC(".maps");

enum stat_idx {
    STAT_ENQUEUE = 0,
    STAT_DISPATCH,
    STAT_DEQUEUE,
    STAT_SELECT_CPU,
    __NR_STATS,
};

static void inc_stat(enum stat_idx idx)
{
    u32 key = 0;
    struct stats *stats;

    stats = bpf_map_lookup_elem(&stats_map, &key);
    if (stats && idx < __NR_STATS)
        stats->cnt[idx]++;
}

/* Define a custom dispatch queue ID */
#define MY_DSQ_ID 0x1000

/* Initialize scheduler */
s32 BPF_STRUCT_OPS_SLEEPABLE(simple_init)
{
    /* Create a custom dispatch queue */
    s32 ret = scx_bpf_create_dsq(MY_DSQ_ID, -1);
    if (ret)
        return ret;

    return 0;
}

/* Clean up scheduler */
void BPF_STRUCT_OPS(simple_exit, struct scx_exit_info *ei)
{
    /* Clean exit - destroy custom DSQ */
    scx_bpf_destroy_dsq(MY_DSQ_ID);
}

/* Select CPU for a task */
s32 BPF_STRUCT_OPS(simple_select_cpu, struct task_struct *p, s32 prev_cpu, u64 wake_flags)
{
    s32 cpu;
    
    inc_stat(STAT_SELECT_CPU);
    
    /* Try to keep task on its previous CPU for cache locality */
    if (scx_bpf_test_and_clear_cpu_idle(prev_cpu))
        return prev_cpu;
    
    /* Otherwise, find any idle CPU */
    cpu = scx_bpf_pick_idle_cpu(p->cpus_ptr, 0);
    if (cpu >= 0)
        return cpu;
    
    /* No idle CPU found, return previous CPU */
    return prev_cpu;
}

/* Enqueue a task */
void BPF_STRUCT_OPS(simple_enqueue, struct task_struct *p, u64 enq_flags)
{
    u64 dsq_id = MY_DSQ_ID;
    u64 slice = SCX_SLICE_DFL;
    
    inc_stat(STAT_ENQUEUE);
    
    /* For CPU-intensive tasks, give them a longer time slice */
    if (p->prio < 120) /* Higher priority (lower nice value) */
        slice = SCX_SLICE_DFL * 2;
    
    /* Dispatch to our custom DSQ */
    scx_bpf_dispatch(p, dsq_id, slice, enq_flags);
}

/* Dequeue a task */
void BPF_STRUCT_OPS(simple_dequeue, struct task_struct *p, u64 deq_flags)
{
    inc_stat(STAT_DEQUEUE);
    /* Nothing special to do on dequeue */
}

/* Dispatch tasks from DSQ to CPU */
void BPF_STRUCT_OPS(simple_dispatch, s32 cpu, struct task_struct *prev)
{
    inc_stat(STAT_DISPATCH);
    
    /* First, try to consume from our custom DSQ */
    scx_bpf_consume(MY_DSQ_ID);
    
    /* If no tasks found, consume from global DSQ as fallback */
    scx_bpf_consume(SCX_DSQ_GLOBAL);
}

/* Scheduler operations structure */
SEC(".struct_ops.link")
struct sched_ext_ops simple_scheduler_ops = {
    .init           = (void *)simple_init,
    .exit           = (void *)simple_exit,
    .select_cpu     = (void *)simple_select_cpu,
    .enqueue        = (void *)simple_enqueue,
    .dequeue        = (void *)simple_dequeue,
    .dispatch       = (void *)simple_dispatch,
    .name           = "simple_scheduler",
};