# eBPF Scheduler

A simple but functional eBPF-based scheduler implementation using the Linux kernel's sched_ext framework.

## Overview

This project implements a real eBPF scheduler that can replace the default Linux scheduler. It demonstrates:
- Custom task scheduling policies
- Per-CPU dispatch queues
- Statistics collection
- Dynamic loading/unloading

## Requirements

- Linux kernel 6.0+ with `CONFIG_SCHED_CLASS_EXT=y`
- BPF development tools (clang, llvm, bpftool)
- libbpf-dev
- Root privileges to load the scheduler

## Files

- `simple_scheduler.bpf.c` - eBPF scheduler implementation
- `simple_scheduler.c` - Userspace loader and monitor
- `scx_common.h` - Common definitions for sched_ext
- `test_scheduler.sh` - Test script to validate the scheduler
- `benchmark.sh` - Performance benchmark script
- `Makefile` - Build configuration

## Building

```bash
make
```

## Running

### Basic Usage

1. Load the scheduler (requires root):
```bash
sudo ./simple_scheduler
```

2. In another terminal, enable the scheduler:
```bash
sudo make enable
```

3. Check scheduler status:
```bash
sudo make status
```

4. Disable the scheduler:
```bash
sudo make disable
```

### Running Tests

```bash
sudo ./test_scheduler.sh
```

### Running Benchmarks

```bash
sudo ./benchmark.sh
```

## How It Works

The scheduler implements the following scheduling policy:

1. **CPU Selection** (`select_cpu`):
   - Tries to keep tasks on their previous CPU for cache locality
   - Falls back to finding any idle CPU
   - Returns previous CPU if no idle CPU available

2. **Task Enqueueing** (`enqueue`):
   - Places tasks in a custom dispatch queue (DSQ)
   - High-priority tasks (nice < 0) get double time slice

3. **Task Dispatching** (`dispatch`):
   - CPUs consume tasks from the custom DSQ
   - Falls back to global DSQ if custom DSQ is empty

4. **Statistics**:
   - Tracks enqueue, dispatch, dequeue, and CPU selection events
   - Per-CPU statistics for scalability

## Scheduler Statistics

The loader prints statistics every 2 seconds showing:
- `enqueue`: Number of tasks enqueued
- `dispatch`: Number of dispatch operations
- `dequeue`: Number of tasks dequeued
- `select_cpu`: Number of CPU selection operations

## Safety

The eBPF scheduler is safe to use because:
- BPF verifier ensures memory safety
- Automatic fallback to CFS on errors
- Can be disabled via sysrq (Alt+SysRq+S)
- Clean shutdown on SIGINT/SIGTERM

## Troubleshooting

If the scheduler fails to load:
1. Check kernel support: `ls /sys/kernel/sched_ext/`
2. Check dmesg for BPF verifier errors: `sudo dmesg | tail`
3. Ensure no other sched_ext scheduler is running
4. Try disabling any existing scheduler: `echo 0 | sudo tee /sys/kernel/sched_ext/enabled`

## Next Steps

This is a basic scheduler. You can extend it by:
- Implementing per-CPU queues for better scalability
- Adding cgroup support
- Implementing more sophisticated scheduling algorithms
- Adding priority inheritance
- Implementing load balancing