# eBPF-based Linux Scheduler

{
      "sessionId": "-root-yunwei37-test-scheduler",
      "inputTokens": 39,
      "outputTokens": 6093,
      "cacheCreationTokens": 26947,
      "cacheReadTokens": 350957,
      "totalTokens": 384036,
      "totalCost": 1.4892517499999998,
      "lastActivity": "2025-07-18",
      "modelsUsed": [
        "claude-opus-4-20250514"
      ],
      "modelBreakdowns": [
        {
          "modelName": "claude-opus-4-20250514",
          "inputTokens": 39,
          "outputTokens": 6093,
          "cacheCreationTokens": 26947,
          "cacheReadTokens": 350957,
          "cost": 1.4892517499999998
        }
      ]
    },

A simple eBPF-based scheduler implementation using Linux's sched_ext framework.

## Features

- Fair scheduling based on virtual runtime (vruntime)
- CPU load balancing
- Task priority support
- Real-time statistics monitoring
- Minimal overhead

## Requirements

- Linux kernel 6.6+ with CONFIG_SCHED_CLASS_EXT enabled
- libbpf development files
- clang and bpftool
- Root privileges to load BPF programs

## Building

```bash
make
```

## Usage

```bash
# Basic usage
sudo ./scheduler

# With statistics output
sudo ./scheduler --stats

# With verbose logging
sudo ./scheduler --verbose

# Custom stats interval (seconds)
sudo ./scheduler --stats --interval 5
```

## How it Works

The scheduler implements a simple fair scheduling algorithm:

1. **Task Tracking**: Maintains per-task statistics including virtual runtime and priority
2. **CPU Selection**: Selects the least loaded CPU for new tasks
3. **Fair Scheduling**: Uses virtual runtime to ensure fair CPU time distribution
4. **Load Balancing**: Distributes tasks across available CPUs

## Architecture

- `scheduler.bpf.c`: eBPF program implementing scheduling logic
- `scheduler.c`: Userspace control program
- `scheduler.h`: Shared definitions
- `Makefile`: Build configuration

## Limitations

This is a demonstration scheduler and may not be suitable for production use. Consider:
- Limited to basic fair scheduling
- No support for real-time tasks
- Simple load balancing algorithm
- No power-aware scheduling

## License

GPL-2.0