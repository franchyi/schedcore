# Application-Aware Kernel Scheduling via LLM-Driven Scheduler Synthesis

An LLM reads application source code, identifies thread roles (latency-critical vs. background), and automatically generates a custom BPF kernel scheduler via Linux [sched-ext](https://github.com/sched-ext/scx) — eliminating tail latency **without modifying the application**.

```
Application Source Code → LLM Analysis → BPF Scheduler Generation →
Compile & Verify → Deploy & Benchmark → Feedback & Iterate
```

## The Problem

The Linux CFS/EEVDF scheduler treats all threads equally within a cgroup. It cannot distinguish between a latency-critical query thread and a CPU-heavy background compaction thread in the same application. When background threads compete with foreground threads for CPU time, tail latency spikes.

This is a **semantic gap**: the kernel has scheduling mechanisms (priorities, queues, preemption) but lacks the application knowledge to use them correctly.

## The Solution

An LLM bridges this gap by:
1. Reading application source code to identify thread roles and naming conventions
2. Generating a BPF scheduler that classifies threads by `task_struct->comm` (thread name)
3. Using sched-ext Dispatch Queues (DSQs) to prioritize latency-sensitive threads
4. Iterating on the scheduler design based on benchmark feedback

No application changes required. No manual configuration. The LLM is the scheduler author.

## Key Results

| Workload | Scheduler | Key Result | Throughput Impact |
|---|---|---|---|
| **db_sim** (synthetic DB) | `db_aware` | 79x max latency reduction (25.9ms → 0.33ms) | Neutral |
| **RocksDB** (read-only) | `rocksdb_aware` v6 | 0% P99.9 regression, 60% max latency reduction | Neutral |
| **RocksDB** (stress) | `rocksdb_aware` v7 | **67.8% P99.9 reduction**, 77% P99.99 reduction | -3.6% |
| **Redis** (GET/SET + persistence) | `redis_aware` | **76% P99 reduction** (GET), 72% P99 reduction (SET) | +15-20% |

## Key Finding: The Asymmetric Design Principle

Through iterating on the RocksDB scheduler (v1→v7), we discovered:

> **Only intervene in scheduling of threads you want to deprioritize. Let high-priority threads use the default fast path.**

Routing foreground threads through a custom DSQ adds BPF dispatch overhead that hurts P99.9 latency. The correct approach: push background threads into a deprioritized custom DSQ and let the framework handle foreground threads natively.

## Repository Structure

```
workloads/
├── db_sim/              # Synthetic DB workload + db_aware BPF scheduler
├── rocksdb/             # RocksDB workload + rocksdb_aware BPF scheduler
├── redis/               # Redis workload + redis_aware BPF scheduler
└── schedcp_legacy/      # Original schedcp benchmark workloads

document/
├── IMPLEMENTATION_PLAN.md   # Full research plan, design evolution (v1→v7), all results
└── schedcp/                 # Original schedcp infrastructure docs

mcp/                     # MCP server (scheduler compilation, deployment, monitoring)
scheduler/               # sched-ext framework and built-in scheduler binaries
autotune/                # Auto-tuning daemon
```

## Quick Start

### Prerequisites

- Linux kernel 6.12+ with sched-ext support
- Clang/LLVM >= 16 (17 recommended)
- Root privileges for scheduler loading

### Build Infrastructure

```bash
git submodule update --init --recursive scheduler/scx
cd scheduler && make && make install && cd ..
cd mcp && cargo build --release && cd ..
```

### Run an Experiment (db_sim example)

```bash
cd workloads/db_sim && make

# CFS baseline (32 threads on 16 CPUs — oversubscribed)
./db_sim -q 8 -c 24 -d 15

# With LLM-generated scheduler
sudo ../../mcp/new_sched/loader ./db_aware.bpf.o &
./db_sim -q 8 -c 24 -d 15
sudo pkill -f "loader.*db_aware"
```

See [IMPLEMENTATION_PLAN.md](document/IMPLEMENTATION_PLAN.md) for full experiment details, design evolution, and all results.

## Built On

This project builds on [**schedcp**](https://github.com/eunomia-bpf/schedcp) — an MCP server for AI-driven Linux scheduler management. schedcp provides the infrastructure layer: scheduler compilation, deployment, monitoring, and workload profiling. See [document/schedcp/](document/schedcp/) for the original schedcp documentation.

Paper: [SchedCP: Towards Agentic OS](https://arxiv.org/abs/2509.01245)

## License

See [LICENSE](LICENSE) for details.
