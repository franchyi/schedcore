# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**schedcp** is a research project exploring **Application-Aware Kernel Scheduling via LLM-Driven Scheduler Synthesis**. The core idea: an LLM analyzes application source code to identify thread roles (latency-critical vs. background), then automatically generates, compiles, and deploys a custom BPF kernel scheduler via the Linux sched-ext framework — eliminating tail latency without modifying the application.

The project builds on a scheduler management infrastructure (MCP server, scheduler library, benchmarking tools) and adds a closed-loop pipeline where the LLM is the scheduler author:

```
Application Source Code → LLM Analysis → BPF Scheduler Generation →
Compile & Verify → Deploy & Benchmark → Feedback & Iterate
```

### Research Results (Current)

| Workload | Scheduler | Key Result |
|---|---|---|
| **db_sim** (synthetic DB) | `db_aware` | 79x max latency reduction (25.9ms → 0.33ms) |
| **RocksDB db_bench** (read-only) | `rocksdb_aware` v6 | 0% P99.9 regression, 60% max latency reduction |
| **RocksDB db_bench** (stress) | `rocksdb_aware` v7 | **67.8% P99.9 reduction**, 77% P99.99 reduction, -3.6% throughput |
| **Redis** (GET/SET + persistence) | `redis_aware` | **76% P99 reduction** (GET), 72% P99 reduction (SET), +15-20% throughput |

See `document/IMPLEMENTATION_PLAN.md` for full evaluation results and design evolution (v1→v7).

## Directory Structure

```
schedcp/
├── CLAUDE.md                      # This file
├── document/
│   ├── IMPLEMENTATION_PLAN.md     # Full research plan, design, and results
│   ├── CLAUDE_ORIGINAL.md         # Original schedcp CLAUDE.md (infrastructure reference)
│   ├── 2509.01245v2.pdf/txt       # Research paper
│   └── schedcp/                   # Original schedcp infrastructure docs
│       ├── AI_AGENTS.md, USAGE_GUIDE.md, PROJECT_STRUCTURE.md
│       ├── schedcp-design.md, sched-agent-design.md, devlog.md
│       ├── design.png, linux.gif, schbench-optimize.gif
│       ├── devlog/                # Development logs
│       ├── motivation_exp/        # Motivation experiments
│       └── scx/                   # sched-ext documentation
│
├── workloads/                     # Application workloads and custom schedulers
│   ├── db_sim/                    # Synthetic DB workload (controlled experiment)
│   │   ├── db_sim.c               # Multi-threaded query + compaction simulation
│   │   ├── db_aware.bpf.c         # LLM-generated BPF scheduler (dual DSQ)
│   │   ├── Makefile               # Builds db_sim + db_aware.bpf.o
│   │   └── db_sim_bench.py        # Automated benchmark (CFS vs bpfland vs db_aware)
│   ├── rocksdb/                   # Real-world RocksDB workload
│   │   ├── rocksdb_aware.bpf.c    # LLM-generated BPF scheduler (v6, asymmetric DSQ)
│   │   ├── rocksdb_sched_bench.py # Automated benchmark script
│   │   └── rocksdb/               # RocksDB source (cloned, db_bench built)
│   ├── redis/                     # Redis cache workload
│   │   ├── redis_aware.bpf.c      # LLM-generated BPF scheduler (dual DSQ)
│   │   ├── redis_bench_compare.sh # A/B benchmark script (CFS vs redis_aware)
│   │   └── redis-src/             # Redis source (git submodule)
│   └── schedcp_legacy/            # Original schedcp benchmark workloads
│       ├── basic/                 # schbench latency benchmark
│       ├── llama.cpp/             # LLM inference workload
│       ├── cxl-micro/             # Memory subsystem benchmark
│       └── ...                    # nginx, faiss, pytorch, vllm, etc.
│
├── mcp/                           # MCP server (scheduler management infrastructure)
│   ├── src/
│   │   ├── scheduler_manager.rs   # Scheduler lifecycle (built-in + custom)
│   │   ├── scheduler_generator.rs # Custom BPF scheduler compilation/verification
│   │   ├── system_monitor.rs      # Real-time CPU/memory/scheduler metrics
│   │   ├── workload_profile.rs    # Workload classification and history
│   │   ├── storage.rs             # Persistent performance data
│   │   ├── main.rs                # MCP server entry point
│   │   ├── lib.rs                 # Core MCP implementation
│   │   └── cli.rs                 # CLI tool implementation
│   ├── new_sched/                 # Custom scheduler working directory
│   │   ├── loader                 # BPF loader binary for custom .bpf.o files
│   │   ├── Makefile               # BPF compilation flags and include paths
│   │   └── *.bpf.{c,o}           # Custom scheduler sources and compiled objects
│   └── schedcp_workloads.json     # Performance history database
│
├── scheduler/                     # Scheduler build system and library
│   ├── scx/                       # sched-ext framework (git submodule)
│   ├── sche_bin/                  # Compiled scheduler binaries
│   ├── scheduler_runner.py        # Python scheduler interface
│   └── schedulers.json            # Scheduler metadata and capabilities
│
└── autotune/                      # Auto-tuning daemon (Rust)
```

## Key Concepts

### The Semantic Gap Problem

The Linux CFS/EEVDF scheduler treats all threads equally within a cgroup. It cannot distinguish between a latency-critical query thread and a CPU-heavy background compaction thread in the same application. This causes tail latency spikes when background threads compete with foreground threads for CPU time.

### The LLM-Driven Solution

An LLM bridges this gap by:
1. Reading application source code to identify thread roles and naming conventions
2. Generating a BPF scheduler that classifies threads by `task_struct->comm` (thread name)
3. Using sched-ext Dispatch Queues (DSQs) to prioritize latency-sensitive threads

### The Asymmetric Design Principle (Key Finding)

Through iterating on the RocksDB scheduler (v1→v6), we discovered:

> **Only intervene in scheduling of threads you want to deprioritize. Let high-priority threads use the default fast path.**

Routing foreground threads through a custom DSQ adds BPF dispatch overhead that hurts P99.9 latency. The correct approach: push background threads into a deprioritized custom DSQ, let the framework handle foreground threads via `SCX_DSQ_GLOBAL` natively.

### BPF Scheduler Patterns

All custom schedulers follow this structure:

| BPF Operation | Purpose |
|---|---|
| `select_cpu` | Find idle CPU; if idle, fast-path to `SCX_DSQ_LOCAL` |
| `enqueue` | Classify thread by `p->comm`, route to appropriate DSQ |
| `dispatch` | Drain DSQs in priority order (high first, low last) |
| `init` | Create custom DSQs via `scx_bpf_create_dsq()` |
| `exit` | Record exit info via `UEI_RECORD` |

Thread classification uses byte-by-byte `p->comm` comparison (BPF verifier disallows `strcmp`):
```c
// Example: detect RocksDB background threads
return (comm[0] == 'r' && comm[1] == 'o' && comm[2] == 'c' &&
        comm[3] == 'k' && comm[4] == 's' && comm[5] == 'd' &&
        comm[6] == 'b' && comm[7] == ':');
```

## Essential Build Commands

### Custom BPF Schedulers
```bash
# Compile a custom BPF scheduler (from any workload directory)
make -f ../../mcp/new_sched/Makefile BPF_SRC=scheduler.bpf.c \
     BPF_OBJ=scheduler.bpf.o scheduler.bpf.o

# Or from workloads/db_sim with its own Makefile
cd workloads/db_sim && make
```

### MCP Server and CLI
```bash
cd mcp && cargo build --release
# mcp/target/release/schedcp     (MCP server)
# mcp/target/release/schedcp-cli (CLI tool)
```

### Built-in Schedulers
```bash
cd scheduler && make deps && make
make install  # Install to ~/.schedcp/scxbin/
```

### Workload-Specific Builds
```bash
# db_sim (synthetic)
cd workloads/db_sim && make

# RocksDB (real-world)
cd workloads/rocksdb/rocksdb && make db_bench -j$(nproc)
```

## Running Experiments

### Quick A/B Test Pattern

```bash
# 1. Run workload under CFS (baseline)
./workload_binary [args] > /tmp/cfs_results.txt

# 2. Start custom scheduler
sudo ../../mcp/new_sched/loader ./scheduler.bpf.o &

# 3. Run same workload under custom scheduler
./workload_binary [args] > /tmp/custom_results.txt

# 4. Stop scheduler
sudo pkill -f "loader.*scheduler"

# 5. Compare results
```

### db_sim Experiment
```bash
cd workloads/db_sim

# CFS baseline (oversubscribed: 32 threads on 16 CPUs)
./db_sim -q 8 -c 24 -d 15

# With db_aware scheduler
sudo ../../mcp/new_sched/loader ./db_aware.bpf.o &
./db_sim -q 8 -c 24 -d 15
sudo pkill -f "loader.*db_aware"
```

### RocksDB Experiment
```bash
cd workloads/rocksdb

# Populate
rm -rf /tmp/rocksdb_bench_test && mkdir -p /tmp/rocksdb_bench_test
rocksdb/db_bench --benchmarks=fillrandom --db=/tmp/rocksdb_bench_test \
    --num=5000000 --max_background_compactions=0 \
    --level0_file_num_compaction_trigger=1000 --value_size=256

# CFS baseline
rocksdb/db_bench --benchmarks=readrandom --db=/tmp/rocksdb_bench_test \
    --use_existing_db=1 --duration=30 --threads=16 \
    --max_background_compactions=16 --statistics=1 --histogram=1

# With rocksdb_aware scheduler
sudo ../../mcp/new_sched/loader ./rocksdb_aware.bpf.o &
rocksdb/db_bench --benchmarks=readrandom --db=/tmp/rocksdb_bench_test \
    --use_existing_db=1 --duration=30 --threads=16 \
    --max_background_compactions=16 --statistics=1 --histogram=1
sudo pkill -f "loader.*rocksdb_aware"
```

### Via MCP Tools (AI-Assisted)
```
list_schedulers                        # See available schedulers
create_and_verify_scheduler source=... # Compile + kernel verify custom scheduler
run_scheduler name=<scheduler>         # Start scheduler
get_execution_status                   # Check scheduler output/status
stop_scheduler                         # Clean stop
system_monitor start/stop              # Collect CPU/memory metrics
workload create/list/get_history       # Manage workload profiles
```

## Development Patterns

### Adding a New Application Workload

1. Create directory under `workloads/<app_name>/`
2. Identify thread naming conventions in the application source code
3. Write a BPF scheduler (`.bpf.c`) that classifies threads by `p->comm`:
   - Background threads → custom `BACKGROUND_DSQ` (low priority, long slice)
   - Foreground threads → `SCX_DSQ_GLOBAL` (framework fast path, minimal overhead)
   - Idle CPU fast path → `SCX_DSQ_LOCAL` in `select_cpu`
4. Compile with: `make -f ../../mcp/new_sched/Makefile BPF_SRC=... BPF_OBJ=...`
5. Write benchmark script following `db_sim_bench.py` or `rocksdb_sched_bench.py` patterns
6. Run A/B test: CFS baseline vs custom scheduler
7. Report: P50, P99, P99.9, P99.99, max latency, throughput

### Design Guidelines for Custom Schedulers

- **Use the asymmetric pattern (v6):** foreground → `SCX_DSQ_GLOBAL`, background → custom DSQ
- **Avoid custom foreground DSQs** — they add BPF dispatch overhead that hurts P99.9
- **Give background threads long slices** (20ms) to reduce context-switch overhead
- **Always implement the idle CPU fast path** in `select_cpu` → `SCX_DSQ_LOCAL`
- **Use byte-by-byte comm comparison** — BPF verifier disallows `strcmp`/`strncmp`
- **Test with CPU oversubscription** — the scheduler's value shows when threads > CPUs

### MCP Infrastructure (Reference)

The MCP server (`mcp/src/`) provides the automation layer:

- **scheduler_manager.rs**: Lifecycle management for built-in and custom schedulers
- **scheduler_generator.rs**: Compiles `.bpf.c` → `.bpf.o` with clang, loads into kernel for verification
- **system_monitor.rs**: Collects CPU/memory/scheduler metrics from `/proc`
- **workload_profile.rs**: Natural language workload descriptions + performance history
- **storage.rs**: Persists workload data in `schedcp_workloads.json`

See `document/CLAUDE_ORIGINAL.md` for detailed MCP architecture documentation.

## Requirements and Environment

- Linux kernel 6.12+ with sched-ext support
- Clang/LLVM >= 16 (17 recommended)
- Rust toolchain >= 1.82
- Meson >= 1.2.0, libbpf >= 1.2.2
- Root privileges required for scheduler loading
- For MCP: set `SCHEDCP_SUDO_PASSWORD` env var or configure passwordless sudo

## Key References

- `document/IMPLEMENTATION_PLAN.md` — Full research plan, design evolution (v1→v6), all results
- `document/CLAUDE_ORIGINAL.md` — Original schedcp infrastructure documentation
- `scheduler/schedulers.json` — Metadata for all built-in schedulers
- `mcp/new_sched/Makefile` — BPF compilation flags and include paths
