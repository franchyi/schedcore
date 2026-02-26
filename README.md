# Application-Aware Kernel Scheduling via LLM-Driven Thread Discovery

An LLM reads application source code, identifies thread roles (latency-critical vs. background), enabling developers to write custom BPF kernel schedulers via Linux [sched-ext](https://github.com/sched-ext/scx) — eliminating tail latency **without modifying the application**.

## The Problem

The Linux CFS/EEVDF scheduler treats all threads equally within a cgroup. It cannot distinguish between a latency-critical query thread and a CPU-heavy background compaction thread in the same application. When background threads compete with foreground threads for CPU time, tail latency spikes.

This is a **semantic gap**: the kernel has scheduling mechanisms (priorities, queues, preemption) but lacks the application knowledge to use them correctly.

## The Solution

Static analysis (tree-sitter) + LLM bridges this gap by:
1. Extracting all thread creation and naming sites from application source code
2. Classifying each thread type as foreground (latency-critical) or background
3. Producing a Thread Manifest that guides hand-written BPF scheduler design

The BPF scheduler classifies threads by `task_struct->comm` (thread name) and uses sched-ext Dispatch Queues (DSQs) to prioritize latency-sensitive threads. No application changes required.

## Key Results

| Workload | Scheduler | Key Result | Throughput Impact |
|---|---|---|---|
| **db_sim** (synthetic DB) | `db_aware` | 79x max latency reduction (25.9ms → 0.33ms) | Neutral |
| **RocksDB** (stress) | `rocksdb_aware` v7 | **67.8% P99.9 reduction**, 77% P99.99 reduction | -3.6% |
| **Redis** (GET/SET + persistence) | `redis_aware` | **76% P99 reduction** (GET), 72% P99 reduction (SET) | +15-20% |
| **Nginx** (HTTP + CPU oversubscription) | `nginx_aware` v3 | **83% P99 reduction**, 87% P99.9 reduction | Neutral |

## Key Finding: The Asymmetric Design Principle

Through iterating on the RocksDB scheduler (v1→v7), we discovered:

> **Only intervene in scheduling of threads you want to deprioritize. Let high-priority threads use the default fast path.**

Routing foreground threads through a custom DSQ adds BPF dispatch overhead that hurts P99.9 latency. The correct approach: push background threads into a deprioritized custom DSQ and let the framework handle foreground threads natively.

## Repository Structure

```
pipeline/                # LLM-driven thread discovery
├── stage1a_static_analysis.py   # Tree-sitter thread extraction
├── stage1_thread_discovery.prompt.md  # LLM classification prompt
├── run_stage1.sh        # Pipeline runner
├── verify_manifest.py   # Result validation
└── examples/            # Ground-truth thread manifests

workloads/
├── db_sim/              # Synthetic DB workload + db_aware BPF scheduler
├── rocksdb_dbbench/     # RocksDB db_bench workload + rocksdb_aware v7 BPF scheduler
├── redis/               # Redis workload + redis_aware BPF scheduler
└── nginx/               # Nginx workload + nginx_aware BPF scheduler

bpf_loader/           # BPF compilation (Makefile + loader)
scheduler/scx/           # sched-ext framework headers (git submodule)
document/                # Research documentation
```

## Quick Start

### Prerequisites

- Linux kernel 6.12+ with sched-ext support
- Clang/LLVM >= 16 (17 recommended)
- Root privileges for scheduler loading

### Build

```bash
git submodule update --init --recursive scheduler/scx
make   # builds bpf_loader/loader
```

### Run an Experiment (db_sim example)

```bash
cd workloads/db_sim && make

# CFS baseline (32 threads on 16 CPUs — oversubscribed)
./db_sim -q 8 -c 24 -d 15

# With application-aware scheduler
sudo ../../bpf_loader/loader ./db_aware.bpf.o &
./db_sim -q 8 -c 24 -d 15
sudo pkill -f "loader.*db_aware"
```

See [IMPLEMENTATION_PLAN.md](document/IMPLEMENTATION_PLAN.md) for full experiment details, design evolution, and all results.

## License

See [LICENSE](LICENSE) for details.
