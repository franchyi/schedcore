#ifndef __SCHEDULER_H
#define __SCHEDULER_H

#define MAX_CPUS 128
#define MAX_TASKS 10000
#define SCHED_SLICE_NS 10000000

struct sched_config {
    __u64 slice_ns;
    __u32 nr_cpus;
    __u32 debug;
};

struct task_stats_user {
    __u64 runtime_ns;
    __u64 vruntime;
    __u32 cpu;
    __u32 priority;
    __u32 pid;
    char comm[16];
};

enum sched_event_type {
    SCHED_EVENT_ENQUEUE,
    SCHED_EVENT_DEQUEUE,
    SCHED_EVENT_DISPATCH,
    SCHED_EVENT_SWITCH,
};

struct sched_event {
    __u64 timestamp;
    __u32 cpu;
    __u32 pid;
    __u32 event_type;
    __u32 extra;
};

#endif