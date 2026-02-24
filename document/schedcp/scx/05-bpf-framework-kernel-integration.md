# BPF Framework and Kernel Integration

## Table of Contents
1. [Overview](#overview)
2. [BPF Programming Model](#bpf-programming-model)
3. [Kernel Interfaces](#kernel-interfaces)
4. [BPF Libraries and Utilities](#bpf-libraries-and-utilities)
5. [Safety and Verification](#safety-and-verification)
6. [Data Structures and Maps](#data-structures-and-maps)
7. [Advanced Features](#advanced-features)
8. [Development Best Practices](#development-best-practices)

## Overview

The sched_ext framework leverages BPF (Berkeley Packet Filter) technology to enable safe, dynamic kernel scheduler implementations. BPF provides a secure sandbox environment where custom scheduling logic can execute within the kernel without risking system stability.

### Key Advantages

1. **Safety**: BPF verifier ensures programs cannot crash the kernel
2. **Performance**: JIT compilation provides near-native performance
3. **Flexibility**: Runtime loading and modification of schedulers
4. **Observability**: Rich introspection and debugging capabilities

## BPF Programming Model

### Scheduler Structure

A sched_ext BPF scheduler consists of several callback functions that the kernel invokes at specific scheduling events:

```c
// Basic scheduler structure
struct sched_ext_ops {
    // CPU selection for waking tasks
    s32 (*select_cpu)(struct task_struct *p, s32 prev_cpu, u64 wake_flags);
    
    // Enqueue task to run
    void (*enqueue)(struct task_struct *p, u64 enq_flags);
    
    // Dispatch tasks from global to local queues
    void (*dispatch)(s32 cpu, struct task_struct *prev);
    
    // Task state transitions
    void (*running)(struct task_struct *p);
    void (*stopping)(struct task_struct *p, bool runnable);
    void (*quiescent)(struct task_struct *p, u64 deq_flags);
    
    // Scheduler lifecycle
    s32 (*init)(void);
    void (*exit)(struct scx_exit_info *ei);
};
```

### BPF Program Types

1. **Regular Operations**: Fast-path scheduling decisions
   ```c
   void BPF_STRUCT_OPS(scheduler_enqueue, struct task_struct *p, u64 enq_flags)
   {
       // Enqueue logic here
   }
   ```

2. **Sleepable Operations**: Can perform blocking operations
   ```c
   s32 BPF_STRUCT_OPS_SLEEPABLE(scheduler_init)
   {
       // Can allocate memory, create maps, etc.
   }
   ```

### Execution Context

- **IRQ Context**: Most scheduler operations run with interrupts disabled
- **Preemption**: BPF programs run with preemption disabled
- **Time Limits**: BPF programs have execution time limits enforced by the verifier

## Kernel Interfaces

### Core kfuncs (Kernel Functions)

#### 1. Dispatch Queue Management
```c
// Create a custom dispatch queue
s32 scx_bpf_create_dsq(u64 dsq_id, s32 node);

// Insert task into dispatch queue
void scx_bpf_dsq_insert(struct task_struct *p, u64 dsq_id, u64 slice, u64 vtime, u64 flags);

// Move tasks from DSQ to local CPU queue
bool scx_bpf_dsq_move_to_local(u64 dsq_id);

// Consume tasks from dispatch queue
bool scx_bpf_dsq_consume(u64 dsq_id);
```

#### 2. CPU Management
```c
// Select CPU using default logic
s32 scx_bpf_select_cpu_dfl(struct task_struct *p, s32 prev_cpu, u64 wake_flags, bool *found);

// Wake up an idle CPU
void scx_bpf_kick_cpu(s32 cpu, u64 flags);

// Check if CPU is idle
bool scx_bpf_cpumask_test_cpu(s32 cpu, const struct cpumask *mask);
```

#### 3. Task Management
```c
// Dispatch task directly
void scx_bpf_dispatch(struct task_struct *p, u64 dsq_id, u64 slice, u64 enq_flags);

// Set task time slice
void scx_bpf_task_set_slice(struct task_struct *p, u64 slice);

// Get task-specific data
struct task_ctx *scx_bpf_task_ctx(const struct task_struct *p);
```

#### 4. Error Handling
```c
// Report scheduler error
void scx_bpf_error(const char *fmt, ...);

// Exit scheduler with reason
void scx_bpf_exit(s64 exit_code, const char *fmt, ...);
```

### Scheduling Hooks

#### 1. select_cpu
```c
s32 BPF_STRUCT_OPS(my_select_cpu, struct task_struct *p, s32 prev_cpu, u64 wake_flags)
{
    // Return CPU where task should run
    // -1 means no preference
    if (wake_flags & SCX_WAKE_SYNC)
        return prev_cpu;  // Prefer previous CPU for sync wakeups
    
    return scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, NULL);
}
```

#### 2. enqueue
```c
void BPF_STRUCT_OPS(my_enqueue, struct task_struct *p, u64 enq_flags)
{
    u64 vtime = calculate_vtime(p);
    u64 slice = calculate_slice(p);
    
    // Enqueue to global dispatch queue
    scx_bpf_dsq_insert(p, GLOBAL_DSQ, slice, vtime, enq_flags);
}
```

#### 3. dispatch
```c
void BPF_STRUCT_OPS(my_dispatch, s32 cpu, struct task_struct *prev)
{
    // Move tasks from global to local CPU queue
    scx_bpf_dsq_move_to_local(GLOBAL_DSQ);
    
    // Or dispatch specific tasks
    struct task_struct *p = find_next_task();
    if (p)
        scx_bpf_dispatch(p, SCX_DSQ_LOCAL, slice, 0);
}
```

## BPF Libraries and Utilities

### 1. CPU Mask Operations (`cpumask.bpf.c`)
```c
// Initialize CPU mask
struct bpf_cpumask *cpumask = bpf_cpumask_create();

// Set/clear CPUs
bpf_cpumask_set_cpu(cpu, cpumask);
bpf_cpumask_clear_cpu(cpu, cpumask);

// Test operations
if (bpf_cpumask_test_cpu(cpu, cpumask)) {
    // CPU is in the mask
}

// Cleanup
bpf_cpumask_release(cpumask);
```

### 2. Topology Information (`topology.bpf.c`)
```c
// Get CPU topology information
s32 llc_id = scx_bpf_cpu_llc_id(cpu);
s32 numa_node = scx_bpf_cpu_numa_id(cpu);

// Check if CPUs share cache
bool share_llc = (scx_bpf_cpu_llc_id(cpu1) == scx_bpf_cpu_llc_id(cpu2));
```

### 3. Min-Heap Operations (`minheap.bpf.c`)
```c
// Priority queue for tasks
struct min_heap heap = {
    .nr = 0,
    .size = MAX_TASKS,
};

// Insert task with priority
minheap_push(&heap, task, priority);

// Get highest priority task
struct task_struct *p = minheap_pop(&heap);
```

### 4. Arena Memory Management (`arena.bpf.c`)
```c
// Allocate from BPF arena
void *ptr = bpf_arena_alloc(&arena, size);

// Use allocated memory
struct my_data *data = ptr;
data->value = 42;

// Memory is automatically managed
```

## Safety and Verification

### BPF Verifier Checks

1. **Memory Safety**:
   - All memory accesses are bounds-checked
   - No null pointer dereferences
   - No out-of-bounds array access

2. **Control Flow**:
   - No infinite loops
   - Bounded recursion depth
   - All paths must terminate

3. **Type Safety**:
   - Strong typing enforced
   - No arbitrary type casts
   - Safe pointer arithmetic

### Safe Coding Patterns

#### 1. Bounded Loops
```c
// Use can_loop macro for safe iteration
int i;
bpf_for(i, 0, nr_cpus) {
    if (!can_loop)
        break;
    
    // Process CPU i
    process_cpu(i);
}
```

#### 2. Safe Pointer Access
```c
// Use MEMBER_VPTR for struct member access
struct task_ctx *ctx = MEMBER_VPTR(task_ctxs, [pid]);
if (!ctx)
    return;  // Handle null case

// Use ARRAY_ELEM_PTR for array access
int *elem = ARRAY_ELEM_PTR(my_array, idx, nr_elems);
if (!elem)
    return;  // Handle out-of-bounds
```

#### 3. Error Handling
```c
// Use UEI_RECORD for error reporting
if (error_condition) {
    UEI_RECORD(uei, "Error: invalid state %d", state);
    return;
}
```

## Data Structures and Maps

### 1. Per-CPU Arrays
```c
// Define per-CPU statistics
struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, u32);
    __type(value, struct stats);
} stats_map SEC(".maps");

// Update stats
struct stats *stats = bpf_map_lookup_elem(&stats_map, &zero);
if (stats)
    stats->count++;
```

### 2. Task Storage
```c
// Define per-task data
struct {
    __uint(type, BPF_MAP_TYPE_TASK_STORAGE);
    __uint(map_flags, BPF_F_NO_PREALLOC);
    __type(key, int);
    __type(value, struct task_data);
} task_data_map SEC(".maps");

// Access task data
struct task_data *data = bpf_task_storage_get(&task_data_map, p, NULL, 
                                               BPF_LOCAL_STORAGE_GET_F_CREATE);
```

### 3. Hash Maps
```c
// Define hash map for lookups
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, u32);
    __type(value, struct entry);
} lookup_map SEC(".maps");
```

### 4. Queue Maps
```c
// FIFO queue for tasks
struct {
    __uint(type, BPF_MAP_TYPE_QUEUE);
    __uint(max_entries, 1024);
    __type(value, u64);  // Task PIDs
} task_queue SEC(".maps");
```

## Advanced Features

### 1. BPF Arena
```c
// Shared memory between BPF and userspace
struct {
    __uint(type, BPF_MAP_TYPE_ARENA);
    __uint(max_entries, 1 << 20);  // 1MB
} arena SEC(".maps");

// Allocate shared data
struct shared_data *data = bpf_arena_alloc(&arena, sizeof(*data));
data->timestamp = bpf_ktime_get_ns();
```

### 2. Cgroup Integration
```c
// Cgroup-aware scheduling
struct cgroup *cgrp = scx_bpf_task_cgroup(p);
u64 weight = scx_bpf_cgroup_weight(cgrp);

// Apply cgroup-based policies
if (weight > 100) {
    // High priority cgroup
    slice *= 2;
}
```

### 3. Performance Monitoring
```c
// Read performance counters
u64 cycles = bpf_perf_event_read(&cycles_map, cpu);
u64 instructions = bpf_perf_event_read(&instructions_map, cpu);

// Calculate IPC
u64 ipc = instructions * 100 / cycles;
```

### 4. Machine Learning Integration
```c
// Use BPF arena for ML model weights
struct ml_model *model = load_model_from_arena();

// Make scheduling decision
int decision = evaluate_model(model, task_features);
if (decision == LATENCY_SENSITIVE) {
    // Prioritize task
}
```

## Development Best Practices

### 1. Code Organization
```c
// Separate concerns into different files
#include "common.bpf.h"      // Common definitions
#include "topology.bpf.h"    // Topology helpers
#include "stats.bpf.h"       // Statistics collection

// Main scheduler logic
void BPF_STRUCT_OPS(my_enqueue, struct task_struct *p, u64 enq_flags)
{
    collect_stats(p);
    update_topology_info(p);
    enqueue_task(p);
}
```

### 2. Debugging
```c
// Use trace output for debugging
#ifdef DEBUG
    bpf_printk("Task %d enqueued on CPU %d\n", p->pid, cpu);
#endif

// Use statistics for monitoring
__sync_fetch_and_add(&stats->enqueue_count, 1);
```

### 3. Compatibility
```c
// Handle different kernel versions
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 12, 0)
    // Use new API
    scx_bpf_task_set_weight(p, weight);
#else
    // Use compatibility layer
    task_set_weight_compat(p, weight);
#endif
```

### 4. Testing
```c
// Add self-tests
static bool self_test(void)
{
    // Test dispatch queue creation
    if (scx_bpf_create_dsq(TEST_DSQ, -1) < 0)
        return false;
    
    // Test CPU mask operations
    struct bpf_cpumask *mask = bpf_cpumask_create();
    if (!mask)
        return false;
    
    bpf_cpumask_release(mask);
    return true;
}
```

### 5. Performance Optimization
```c
// Minimize BPF map lookups
struct task_ctx *ctx = lookup_task_ctx(p);
if (!ctx)
    return;

// Cache frequently used values
u64 now = bpf_ktime_get_ns();
ctx->last_run = now;
ctx->total_runtime += now - ctx->start_time;

// Use per-CPU data when possible
struct pcpu_data *pcpu = this_cpu_ptr(&pcpu_data);
pcpu->nr_switches++;
```

The BPF framework provides a powerful and safe environment for implementing custom schedulers, with comprehensive APIs, strong safety guarantees, and excellent performance characteristics.