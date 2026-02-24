# eBPF Scheduler Development Guide

{
      "sessionId": "-root-yunwei37-new-sched",
      "inputTokens": 159,
      "outputTokens": 11783,
      "cacheCreationTokens": 82655,
      "cacheReadTokens": 2107627,
      "totalTokens": 2202224,
      "totalCost": 5.597331749999999,
      "lastActivity": "2025-07-18",
      "modelsUsed": [
        "claude-opus-4-20250514"
      ],
      "modelBreakdowns": [
        {
          "modelName": "claude-opus-4-20250514",
          "inputTokens": 159,
          "outputTokens": 11783,
          "cacheCreationTokens": 82655,
          "cacheReadTokens": 2107627,
          "cost": 5.597331749999999
        }
      ]
    }

│ test-scheduler │ - opus-4    │       39 │    6,093 │     $1.49 │ 2025-07-18  │
├────────────────┼─────────────┼──────────┼──────────┼───────────┼─────────────┤
│ new-sched      │ - opus-4    │      168 │   11,976 │     $6.45 │ 2025-07-18  │

real    33m42.155s
user    3m47.956s
sys     0m19.744s



This guide explains how to write an eBPF-based scheduler using the sched_ext framework in Linux.

## What is sched_ext?

sched_ext (Extensible Scheduler Class) is a Linux kernel framework that allows you to implement custom CPU schedulers using eBPF programs. It was jointly developed by Meta and Google and provides a safe way to experiment with scheduling policies without modifying kernel code.

### Key Benefits:
- **Safety**: BPF verifier ensures no memory errors or infinite loops
- **Dynamic**: Can be loaded/unloaded at runtime without rebooting
- **Flexibility**: Implement any scheduling algorithm
- **Fallback**: System automatically falls back to default scheduler on errors

## Required Components

### 1. Header Files and Dependencies

```c
#include <vmlinux.h>          // Kernel type definitions
#include <bpf/bpf_helpers.h>  // BPF helper functions
#include <bpf/bpf_tracing.h>  // BPF tracing helpers
```

### 2. System Requirements

- Linux kernel 6.0+ with sched_ext support
- Kernel config options:
  ```
  CONFIG_BPF=y
  CONFIG_SCHED_CLASS_EXT=y
  CONFIG_BPF_SYSCALL=y
  CONFIG_BPF_JIT=y
  CONFIG_DEBUG_INFO_BTF=y
  ```

### 3. Development Tools

- `clang` - For compiling BPF programs
- `libbpf` - BPF loading library
- `bpftool` - For generating vmlinux.h and debugging

## Basic Structure of an eBPF Scheduler

### 1. Core Callbacks

A scheduler must implement these key operations:

```c
struct sched_ext_ops {
    // Required callbacks
    void (*enqueue)(struct task_struct *p, u64 enq_flags);
    void (*dispatch)(s32 cpu, struct task_struct *prev);
    
    // Optional callbacks
    s32  (*select_cpu)(struct task_struct *p, s32 prev_cpu, u64 wake_flags);
    void (*dequeue)(struct task_struct *p, u64 deq_flags);
    void (*init)(void);
    void (*exit)(struct scx_exit_info *ei);
    
    // Scheduler name
    char name[128];
};
```

### 2. Key Concepts

- **Dispatch Queues (DSQ)**: Where tasks wait to be scheduled
  - `SCX_DSQ_GLOBAL`: Global queue shared by all CPUs
  - `SCX_DSQ_LOCAL`: Per-CPU local queue
  - Custom DSQs can be created

- **Task Lifecycle**:
  1. `select_cpu()` - Choose CPU for waking task
  2. `enqueue()` - Place task in dispatch queue
  3. `dispatch()` - CPU picks next task to run
  4. `dequeue()` - Task stops running

### 3. Helper Functions

Key BPF helpers for schedulers:

```c
// Dispatch task to a queue
void scx_bpf_dispatch(struct task_struct *p, u64 dsq_id, u64 slice, u64 enq_flags);

// Consume tasks from a queue
bool scx_bpf_consume(u64 dsq_id);

// Kick a CPU to reschedule
void scx_bpf_kick_cpu(s32 cpu, u64 flags);
```

## Example Schedulers

### 1. Minimal FIFO Scheduler

See `minimal_scheduler.bpf.c` - A simple global FIFO scheduler that:
- Uses a single global queue
- Processes tasks in order
- Demonstrates basic structure

### 2. Advanced Examples

The Linux kernel includes several example schedulers in `tools/sched_ext/`:

- `scx_simple` - Basic scheduler with local/global queues
- `scx_qmap` - Priority queue based scheduler  
- `scx_central` - Centralized queue scheduler
- `scx_pair` - Pairs tasks with CPUs
- `scx_flatcg` - Cgroup-aware scheduler

### 3. Rust-based Schedulers

The `scx_rustland` project shows how to implement schedulers with:
- BPF component in kernel
- Policy logic in Rust userspace
- Communication via BPF maps

## Building and Running

### 1. Generate vmlinux.h

```bash
bpftool btf dump file /sys/kernel/btf/vmlinux format c > vmlinux.h
```

### 2. Compile BPF Program

```bash
clang -g -O2 -target bpf -c minimal_scheduler.bpf.c -o minimal_scheduler.bpf.o
```

### 3. Load Scheduler

Using bpftool:
```bash
bpftool struct_ops register minimal_scheduler.bpf.o /sys/fs/bpf/my_scheduler
```

Or using a loader program (see `minimal_scheduler.c`)

### 4. Verify Loading

```bash
cat /sys/kernel/sched_ext/root/ops
```

### 5. Unload Scheduler

```bash
bpftool struct_ops unregister /sys/fs/bpf/my_scheduler
```

## Debugging and Safety

- Scheduler errors are logged to kernel log (`dmesg`)
- System automatically falls back on errors
- Use `SysRq-S` to force disable custom scheduler
- BPF verifier prevents unsafe operations

## Best Practices

1. **Start Simple**: Begin with basic FIFO, add features incrementally
2. **Test Thoroughly**: Use stress tests and various workloads
3. **Monitor Performance**: Track scheduling latency and fairness
4. **Handle Edge Cases**: Empty queues, CPU hotplug, etc.
5. **Use Tracing**: Add BPF trace points for debugging

## Resources

- [Kernel Documentation](https://www.kernel.org/doc/html/next/scheduler/sched-ext.html)
- [sched_ext Examples](https://github.com/sched-ext/scx)
- [BPF Documentation](https://docs.kernel.org/bpf/)
- [libbpf Documentation](https://libbpf.readthedocs.io/)

## Next Steps

1. Study the example schedulers in this directory
2. Modify the minimal scheduler to add features
3. Experiment with different scheduling policies
4. Measure performance with real workloads