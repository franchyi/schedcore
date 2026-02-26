# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**schedcp** is a research project exploring **Application-Aware Kernel Scheduling via LLM-Driven Thread Discovery**. The core idea: an LLM + static analysis identifies thread roles (latency-critical vs. background) from application source code, enabling developers to write custom BPF kernel schedulers via the Linux sched-ext framework — eliminating tail latency without modifying the application.

The LLM's role is **thread discovery**, not scheduler generation. BPF schedulers are hand-written systems engineering, guided by the thread classification the pipeline provides.

### Research Results (Current)

| Workload | Scheduler | Key Result |
|---|---|---|
| **db_sim** (synthetic DB) | `db_aware` | 79x max latency reduction (25.9ms → 0.33ms) |
| **RocksDB db_bench** (stress) | `rocksdb_aware` v7 | **67.8% P99.9 reduction**, 77% P99.99 reduction, -3.6% throughput |
| **Redis** (GET/SET + persistence) | `redis_aware` | **76% P99 reduction** (GET), 72% P99 reduction (SET), +15-20% throughput |
| **Nginx** (HTTP + CPU oversubscription) | `nginx_aware` v3 | **83% P99 reduction**, 87% P99.9 reduction, 0% throughput impact |

See `document/IMPLEMENTATION_PLAN.md` for full evaluation results and design evolution.

## Directory Structure

```
schedcp/
├── CLAUDE.md                      # This file
├── pipeline/                      # LLM-driven thread discovery
│   ├── stage1a_static_analysis.py # Tree-sitter thread extraction (deterministic)
│   ├── stage1_thread_discovery.prompt.md  # LLM classification prompt template
│   ├── run_stage1.sh              # Pipeline runner (Stage 1a → 1b)
│   ├── verify_manifest.py         # Result validation against ground truth
│   ├── thread_manifest.schema.json # Thread Manifest JSON schema
│   ├── examples/                  # Ground-truth thread manifests
│   └── results/                   # Generated pipeline outputs
│
├── workloads/                     # Application workloads and custom schedulers
│   ├── db_sim/                    # Synthetic DB workload
│   │   ├── db_sim.c               # Multi-threaded query + compaction simulation
│   │   ├── db_aware.bpf.c         # BPF scheduler (dual DSQ)
│   │   ├── Makefile               # Builds db_sim + db_aware.bpf.o
│   │   └── db_sim_bench.py        # Automated benchmark
│   ├── rocksdb/                   # Real-world RocksDB workload
│   │   ├── rocksdb_aware.bpf.c    # BPF scheduler (asymmetric DSQ + selective preemption)
│   │   ├── rocksdb_sched_bench.py # Automated benchmark script
│   │   └── rocksdb/               # RocksDB source (cloned, db_bench built)
│   ├── redis/                     # Redis cache workload
│   │   ├── redis_aware.bpf.c      # BPF scheduler (dual DSQ + selective preemption)
│   │   ├── redis_bench_compare.sh # A/B benchmark script (CFS vs redis_aware)
│   │   └── redis-src/             # Redis source (git submodule)
│   └── nginx/                     # Nginx web server workload
│       ├── nginx_aware.bpf.c      # BPF scheduler (asymmetric + task storage)
│       ├── nginx_bench_compare.sh # Self-contained A/B benchmark
│       └── nginx.conf             # Nginx config template (16 workers)
│
├── mcp/new_sched/                 # BPF compilation infrastructure
│   ├── loader                     # BPF loader binary
│   ├── Makefile                   # BPF compilation flags and include paths
│   └── *.bpf.{c,o}               # Custom scheduler sources and compiled objects
│
├── scheduler/scx/                 # sched-ext framework (git submodule, headers only)
│
└── document/
    ├── IMPLEMENTATION_PLAN.md     # Full research plan, design, and results
    ├── future_plan.md             # Research roadmap
    ├── CLAUDE_ORIGINAL.md         # Original schedcp infrastructure reference
    ├── 2509.01245v2.pdf/txt       # Research paper
    └── schedcp/                   # Original schedcp infrastructure docs
```

## Key Concepts

### The Semantic Gap Problem

The Linux CFS/EEVDF scheduler treats all threads equally within a cgroup. It cannot distinguish between a latency-critical query thread and a CPU-heavy background compaction thread in the same application. This causes tail latency spikes when background threads compete with foreground threads for CPU time.

### The LLM-Driven Solution

Static analysis (tree-sitter) + LLM bridges this gap by:
1. Extracting all thread creation and naming sites from application source code (Stage 1a)
2. Classifying each thread type as foreground or background (Stage 1b)
3. Producing a Thread Manifest that guides BPF scheduler design

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

### Nginx Experiment
```bash
cd workloads/nginx

# Compile BPF scheduler
make -f ../../mcp/new_sched/Makefile BPF_SRC=nginx_aware.bpf.c \
     BPF_OBJ=nginx_aware.bpf.o nginx_aware.bpf.o

# Automated A/B benchmark (builds nginx + wrk2 if needed, runs everything)
sudo ./nginx_bench_compare.sh 3
```

## Development Patterns

### Adding a New Application Workload

1. Create directory under `workloads/<app_name>/`
2. Run thread discovery pipeline: `./pipeline/run_stage1.sh <app_name> <source_path> <language> <description>`
3. Review the Thread Manifest — identify background vs foreground threads
4. Write a BPF scheduler (`.bpf.c`) that classifies threads by `p->comm`:
   - Background threads → custom `BACKGROUND_DSQ` (low priority, long slice)
   - Foreground threads → `SCX_DSQ_GLOBAL` (framework fast path, minimal overhead)
   - Idle CPU fast path → `SCX_DSQ_LOCAL` in `select_cpu`
5. Compile with: `make -f ../../mcp/new_sched/Makefile BPF_SRC=... BPF_OBJ=...`
6. Write benchmark script following `db_sim_bench.py` or `redis_bench_compare.sh` patterns
7. Run A/B test: CFS baseline vs custom scheduler
8. Report: P50, P99, P99.9, P99.99, max latency, throughput

### Design Guidelines for Custom Schedulers

- **Use the asymmetric pattern:** foreground → `SCX_DSQ_GLOBAL`, background → custom DSQ
- **Avoid custom foreground DSQs** — they add BPF dispatch overhead that hurts P99.9
- **Give background threads long slices** (20ms) to reduce context-switch overhead
- **Always implement the idle CPU fast path** in `select_cpu` → `SCX_DSQ_LOCAL`
- **Use byte-by-byte comm comparison** — BPF verifier disallows `strcmp`/`strncmp`
- **Test with CPU oversubscription** — the scheduler's value shows when threads > CPUs

## Requirements and Environment

- Linux kernel 6.12+ with sched-ext support
- Clang/LLVM >= 16 (17 recommended)
- Root privileges required for scheduler loading

## Key References

- `document/IMPLEMENTATION_PLAN.md` — Full research plan, design evolution (v1→v6), all results
- `document/future_plan.md` — Research roadmap
- `mcp/new_sched/Makefile` — BPF compilation flags and include paths
