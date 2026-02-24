#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

char LICENSE[] SEC("license") = "GPL";

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, __u64);
} sched_switch_count SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, __u64);
} sched_wakeup_count SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 16);
    __type(key, __u32);
    __type(value, __u64);
} cpu_switch_count SEC(".maps");

// Track scheduler switches
SEC("tracepoint/sched/sched_switch")
int trace_sched_switch(void *ctx)
{
    __u32 key = 0;
    __u64 *count = bpf_map_lookup_elem(&sched_switch_count, &key);
    
    if (count) {
        __sync_fetch_and_add(count, 1);
        if (*count % 10000 == 0) {
            bpf_printk("Scheduler switches: %llu\n", *count);
        }
    } else {
        __u64 init = 1;
        bpf_map_update_elem(&sched_switch_count, &key, &init, BPF_ANY);
    }
    
    // Track per-CPU switches
    __u32 cpu = bpf_get_smp_processor_id();
    __u64 *cpu_count = bpf_map_lookup_elem(&cpu_switch_count, &cpu);
    if (cpu_count) {
        __sync_fetch_and_add(cpu_count, 1);
    } else {
        __u64 init_count = 1;
        bpf_map_update_elem(&cpu_switch_count, &cpu, &init_count, BPF_ANY);
    }
    
    return 0;
}

// Track process wakeups
SEC("tracepoint/sched/sched_wakeup")
int trace_sched_wakeup(void *ctx)
{
    __u32 key = 0;
    __u64 *count = bpf_map_lookup_elem(&sched_wakeup_count, &key);
    
    if (count) {
        __sync_fetch_and_add(count, 1);
        if (*count % 5000 == 0) {
            bpf_printk("Wakeup events: %llu\n", *count);
        }
    } else {
        __u64 init = 1;
        bpf_map_update_elem(&sched_wakeup_count, &key, &init, BPF_ANY);
    }
    
    return 0;
}

// Track new task wakeups  
SEC("tracepoint/sched/sched_wakeup_new")
int trace_sched_wakeup_new(void *ctx)
{
    bpf_printk("New task wakeup detected\n");
    return 0;
}

// Track process migration
SEC("tracepoint/sched/sched_migrate_task")
int trace_sched_migrate(void *ctx)
{
    __u32 cpu = bpf_get_smp_processor_id();
    bpf_printk("Task migration on CPU %d\n", cpu);
    return 0;
}