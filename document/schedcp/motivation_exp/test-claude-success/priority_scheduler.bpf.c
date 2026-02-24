// SPDX-License-Identifier: GPL-2.0
/*
 * Priority-based eBPF scheduler using sched_ext
 * 
 * This scheduler implements priority-based scheduling with:
 * - Multiple priority levels
 * - Per-CPU local queues for better cache locality
 * - Load balancing between CPUs
 */

#include <vmlinux.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>

char _license[] SEC("license") = "GPL";

/* Configuration */
#define MAX_CPUS 128
#define NR_PRIORITIES 5
#define HIGH_PRIORITY 0
#define LOW_PRIORITY (NR_PRIORITIES - 1)

/* Custom dispatch queue IDs */
#define PRIO_DSQ_BASE 100

/* Per-CPU statistics */
struct cpu_stat {
    u64 nr_enqueued;
    u64 nr_dispatched;
    u64 nr_migrations;
};

/* Maps */
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(key_size, sizeof(u32));
    __uint(value_size, sizeof(struct cpu_stat));
    __uint(max_entries, MAX_CPUS);
} cpu_stats SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(key_size, sizeof(pid_t));
    __uint(value_size, sizeof(u32));
    __uint(max_entries, 10000);
} task_priorities SEC(".maps");

/* Helper to get task priority */
static u32 get_task_priority(struct task_struct *p)
{
    pid_t pid = BPF_CORE_READ(p, pid);
    u32 *prio;
    
    prio = bpf_map_lookup_elem(&task_priorities, &pid);
    if (prio)
        return *prio;
    
    /* Default priority based on nice value */
    int nice = BPF_CORE_READ(p, nice);
    if (nice < -10)
        return HIGH_PRIORITY;
    else if (nice < 0)
        return 1;
    else if (nice == 0)
        return 2;
    else if (nice < 10)
        return 3;
    else
        return LOW_PRIORITY;
}

/* Helper to find least loaded CPU */
static s32 find_idle_cpu(void)
{
    u32 min_load = U32_MAX;
    s32 best_cpu = -1;
    
    for (s32 cpu = 0; cpu < MAX_CPUS && cpu < nr_cpu_ids; cpu++) {
        struct cpu_stat *stat;
        u32 key = cpu;
        
        if (!bpf_cpumask_test_cpu(cpu, cpu_online_mask))
            continue;
            
        stat = bpf_map_lookup_elem(&cpu_stats, &key);
        if (stat && stat->nr_enqueued < min_load) {
            min_load = stat->nr_enqueued;
            best_cpu = cpu;
        }
    }
    
    return best_cpu;
}

/* Initialize scheduler */
SEC("struct_ops/priority_init")
s32 BPF_PROG(priority_init)
{
    /* Create custom dispatch queues for each priority */
    for (u32 i = 0; i < NR_PRIORITIES; i++) {
        scx_bpf_create_dsq(PRIO_DSQ_BASE + i, -1);
    }
    
    return 0;
}

/* Exit handler */
SEC("struct_ops/priority_exit")
void BPF_PROG(priority_exit, struct scx_exit_info *ei)
{
    /* Destroy custom dispatch queues */
    for (u32 i = 0; i < NR_PRIORITIES; i++) {
        scx_bpf_destroy_dsq(PRIO_DSQ_BASE + i);
    }
}

/* Select CPU for task */
SEC("struct_ops/priority_select_cpu")
s32 BPF_PROG(priority_select_cpu, struct task_struct *p, s32 prev_cpu, u64 wake_flags)
{
    s32 cpu;
    
    /* Try to keep task on same CPU for cache locality */
    if (scx_bpf_test_and_clear_cpu_idle(prev_cpu))
        return prev_cpu;
    
    /* Find an idle CPU */
    cpu = scx_bpf_pick_idle_cpu(BPF_CORE_READ(p, cpus_ptr));
    if (cpu >= 0)
        return cpu;
    
    /* Load balance: find least loaded CPU */
    cpu = find_idle_cpu();
    if (cpu >= 0)
        return cpu;
    
    return prev_cpu;
}

/* Enqueue task */
SEC("struct_ops/priority_enqueue")
void BPF_PROG(priority_enqueue, struct task_struct *p, u64 enq_flags)
{
    u32 prio = get_task_priority(p);
    u32 cpu = scx_bpf_task_cpu(p);
    struct cpu_stat *stat;
    u64 dsq_id;
    u64 slice;
    
    /* Update statistics */
    if (cpu < MAX_CPUS) {
        stat = bpf_map_lookup_elem(&cpu_stats, &cpu);
        if (stat)
            __sync_fetch_and_add(&stat->nr_enqueued, 1);
    }
    
    /* Calculate time slice based on priority */
    slice = SCX_SLICE_DFL * (NR_PRIORITIES - prio) / NR_PRIORITIES;
    if (slice < SCX_SLICE_DFL / 4)
        slice = SCX_SLICE_DFL / 4;
    
    /* Dispatch to priority queue */
    dsq_id = PRIO_DSQ_BASE + prio;
    scx_bpf_dispatch(p, dsq_id, slice, enq_flags);
}

/* Dequeue task */
SEC("struct_ops/priority_dequeue")
void BPF_PROG(priority_dequeue, struct task_struct *p, u64 deq_flags)
{
    u32 cpu = scx_bpf_task_cpu(p);
    struct cpu_stat *stat;
    
    /* Update statistics */
    if (cpu < MAX_CPUS) {
        stat = bpf_map_lookup_elem(&cpu_stats, &cpu);
        if (stat && stat->nr_enqueued > 0)
            __sync_fetch_and_sub(&stat->nr_enqueued, 1);
    }
}

/* CPU dispatch */
SEC("struct_ops/priority_dispatch")
void BPF_PROG(priority_dispatch, s32 cpu, struct task_struct *prev)
{
    struct cpu_stat *stat;
    u32 key = cpu;
    
    /* Update statistics */
    if (cpu < MAX_CPUS) {
        stat = bpf_map_lookup_elem(&cpu_stats, &key);
        if (stat)
            __sync_fetch_and_add(&stat->nr_dispatched, 1);
    }
    
    /* Try local queue first */
    if (scx_bpf_consume(SCX_DSQ_LOCAL))
        return;
    
    /* Consume from priority queues in order */
    for (u32 prio = 0; prio < NR_PRIORITIES; prio++) {
        if (scx_bpf_consume(PRIO_DSQ_BASE + prio))
            return;
    }
}

/* Task migration */
SEC("struct_ops/priority_migrate")
void BPF_PROG(priority_migrate, struct task_struct *p, s32 from, s32 to)
{
    struct cpu_stat *stat;
    
    /* Update migration statistics */
    if (to < MAX_CPUS) {
        u32 key = to;
        stat = bpf_map_lookup_elem(&cpu_stats, &key);
        if (stat)
            __sync_fetch_and_add(&stat->nr_migrations, 1);
    }
}

/* Define scheduler operations */
SEC(".struct_ops.link")
struct sched_ext_ops priority_scheduler = {
    .select_cpu     = (void *)priority_select_cpu,
    .enqueue        = (void *)priority_enqueue,
    .dequeue        = (void *)priority_dequeue,
    .dispatch       = (void *)priority_dispatch,
    .migrate        = (void *)priority_migrate,
    .init           = (void *)priority_init,
    .exit           = (void *)priority_exit,
    .name           = "priority_scheduler",
    .timeout_ms     = 1000,
    .flags          = 0,
};