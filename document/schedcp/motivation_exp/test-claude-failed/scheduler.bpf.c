#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>

char LICENSE[] SEC("license") = "GPL";

#define MAX_CPUS 128
#define MAX_TASKS 10000

struct task_stats {
    u64 runtime_ns;
    u64 vruntime;
    u32 cpu;
    u32 priority;
};

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_TASKS);
    __type(key, u32);
    __type(value, struct task_stats);
} task_info SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, MAX_CPUS);
    __type(key, u32);
    __type(value, u64);
} cpu_idle_time SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, u32);
    __type(value, u64);
} min_vruntime SEC(".maps");

static __always_inline u64 get_min_vruntime(void)
{
    u32 key = 0;
    u64 *value = bpf_map_lookup_elem(&min_vruntime, &key);
    return value ? *value : 0;
}

static __always_inline void update_min_vruntime(u64 new_min)
{
    u32 key = 0;
    bpf_map_update_elem(&min_vruntime, &key, &new_min, BPF_ANY);
}

SEC("tp_btf/sched_wakeup")
int BPF_PROG(sched_wakeup, struct task_struct *p)
{
    u32 pid = BPF_CORE_READ(p, pid);
    struct task_stats *stats, new_stats = {};
    
    stats = bpf_map_lookup_elem(&task_info, &pid);
    if (!stats) {
        new_stats.vruntime = get_min_vruntime();
        new_stats.priority = BPF_CORE_READ(p, prio);
        bpf_map_update_elem(&task_info, &pid, &new_stats, BPF_ANY);
    }
    
    return 0;
}

SEC("tp_btf/sched_switch")
int BPF_PROG(sched_switch, bool preempt, struct task_struct *prev, struct task_struct *next)
{
    u32 prev_pid = BPF_CORE_READ(prev, pid);
    u32 next_pid = BPF_CORE_READ(next, pid);
    u64 now = bpf_ktime_get_ns();
    struct task_stats *prev_stats, *next_stats;
    
    prev_stats = bpf_map_lookup_elem(&task_info, &prev_pid);
    if (prev_stats) {
        u64 delta = now - prev_stats->runtime_ns;
        prev_stats->vruntime += delta;
        prev_stats->runtime_ns = now;
    }
    
    next_stats = bpf_map_lookup_elem(&task_info, &next_pid);
    if (next_stats) {
        next_stats->runtime_ns = now;
        next_stats->cpu = bpf_get_smp_processor_id();
        
        if (next_stats->vruntime < get_min_vruntime()) {
            update_min_vruntime(next_stats->vruntime);
        }
    }
    
    return 0;
}

SEC("struct_ops/sched_ext_ops")
struct sched_ext_ops simple_ops = {
    .select_cpu = (void *)simple_select_cpu,
    .enqueue = (void *)simple_enqueue,
    .dequeue = (void *)simple_dequeue,
    .dispatch = (void *)simple_dispatch,
    .name = "simple_ebpf_scheduler",
};

SEC("struct_ops.s/simple_select_cpu")
int BPF_PROG(simple_select_cpu, struct task_struct *p, int prev_cpu, u64 wake_flags)
{
    u32 cpu, min_cpu = 0;
    u64 min_idle = UINT64_MAX;
    u32 key;
    
    for (cpu = 0; cpu < MAX_CPUS && cpu < bpf_num_possible_cpus(); cpu++) {
        key = cpu;
        u64 *idle_time = bpf_map_lookup_elem(&cpu_idle_time, &key);
        if (idle_time && *idle_time < min_idle) {
            min_idle = *idle_time;
            min_cpu = cpu;
        }
    }
    
    return min_cpu;
}

SEC("struct_ops.s/simple_enqueue")
void BPF_PROG(simple_enqueue, struct task_struct *p, u64 enq_flags)
{
    u32 pid = BPF_CORE_READ(p, pid);
    struct task_stats *stats;
    
    stats = bpf_map_lookup_elem(&task_info, &pid);
    if (!stats) {
        struct task_stats new_stats = {
            .vruntime = get_min_vruntime(),
            .priority = BPF_CORE_READ(p, prio),
            .runtime_ns = bpf_ktime_get_ns(),
        };
        bpf_map_update_elem(&task_info, &pid, &new_stats, BPF_ANY);
    }
    
    scx_bpf_dispatch(p, SCX_DSQ_GLOBAL, SCX_SLICE_DFL, enq_flags);
}

SEC("struct_ops.s/simple_dequeue")
void BPF_PROG(simple_dequeue, struct task_struct *p, u64 deq_flags)
{
    u32 pid = BPF_CORE_READ(p, pid);
    
    if (deq_flags & SCX_DEQ_SLEEP)
        bpf_map_delete_elem(&task_info, &pid);
}

SEC("struct_ops.s/simple_dispatch")
void BPF_PROG(simple_dispatch, s32 cpu, struct task_struct *prev)
{
    scx_bpf_consume(SCX_DSQ_GLOBAL);
}