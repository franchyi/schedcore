# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A **framework for building application-aware kernel schedulers** via LLM-driven thread discovery. Given application source code as input, the framework produces a validated, application-specific BPF scheduler as output — without modifying the application.

The framework pipeline:

| Stage | Input | Output | Method |
|---|---|---|---|
| **1. Thread Discovery** | Application source code | Thread Manifest (thread name → role) | Tree-sitter static extraction + LLM classification |
| **2. Policy Selection** | Thread Manifest + workload profile | Scheduling pattern | Decision framework based on contention level |
| **3. Scheduler Construction** | Pattern + classification rules | BPF scheduler (`.bpf.c`) | Hand-written using reusable BPF patterns + `p->comm` classification |
| **4. Validation** | BPF scheduler + workload | Performance comparison vs CFS | A/B benchmark: latency percentiles + throughput |

The LLM's role is **thread discovery** (Stage 1), not scheduler generation. BPF schedulers are hand-written systems engineering, guided by the thread classification the pipeline provides.

### Evaluation Results

| Workload | Scheduler | Key Result |
|---|---|---|
| **db_sim** (synthetic DB) | `db_aware` | 79x max latency reduction (25.9ms → 0.33ms) |
| **RocksDB db_bench** (stress) | `rocksdb_aware` v7 | **67.8% P99.9 reduction**, 77% P99.99 reduction, -3.6% throughput |
| **Redis** (GET/SET + persistence) | `redis_aware` | **76% P99 reduction** (GET), 72% P99 reduction (SET), +15-20% throughput |
| **Nginx** (HTTP + CPU oversubscription) | `nginx_aware` v3 | **83% P99 reduction**, 87% P99.9 reduction, 0% throughput impact |

See `document/design.md` for full design, framework architecture, and evaluation results.

## Directory Structure

```
├── pipeline/                      # Framework pipeline tooling
│   ├── stage1a_static_analysis.py # Tree-sitter thread extraction (deterministic)
│   ├── stage1_thread_discovery.prompt.md  # LLM classification prompt template
│   ├── run_stage1.sh              # Pipeline runner (Stage 1a → 1b)
│   ├── stage1c_dynamic_profiler.py # Runtime eBPF thread behavior profiler
│   ├── verify_manifest.py         # Result validation against ground truth
│   ├── evaluate_accuracy.py       # Batch precision/recall/F1 evaluation
│   ├── stage2_policy_select.py    # Policy selection (contention → pattern)
│   ├── stage3_generate_scheduler.py # BPF skeleton generator (manifest → .bpf.c)
│   ├── stage4_validate.py         # Unified validation harness (parse benchmarks)
│   ├── thread_manifest.schema.json # Thread Manifest JSON schema
│   ├── examples/                  # Ground-truth thread manifests
│   └── results/                   # Generated pipeline outputs
│
├── workloads/                     # Stage 3-4: Application schedulers and benchmarks
│   ├── db_sim/                    # Synthetic DB workload
│   │   ├── db_sim.c               # Multi-threaded query + compaction simulation
│   │   ├── db_aware.bpf.c         # BPF scheduler (dual DSQ)
│   │   ├── Makefile               # Builds db_sim + db_aware.bpf.o
│   │   └── db_sim_bench.py        # Automated benchmark
│   ├── rocksdb_dbbench/           # RocksDB db_bench workload
│   │   ├── rocksdb_aware.bpf.c    # BPF scheduler v7 (dual DSQ + selective preemption)
│   │   ├── bench_compare.sh       # A/B benchmark script (CFS vs v7)
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
├── bpf_loader/                    # BPF compilation infrastructure
│   ├── loader                     # BPF loader binary
│   ├── Makefile                   # BPF compilation flags and include paths
│   └── *.bpf.{c,o}               # Custom scheduler sources and compiled objects
│
├── scheduler/scx/                 # sched-ext framework (git submodule, headers only)
│
└── document/
    ├── design.md                  # Framework design and evaluation results
    └── future_plan.md             # Research roadmap
```

## Key Concepts

### The Semantic Gap Problem

The Linux CFS/EEVDF scheduler treats all threads equally within a cgroup. It cannot distinguish between a latency-critical query thread and a CPU-heavy background compaction thread in the same application. This causes tail latency spikes when background threads compete with foreground threads for CPU time.

### Policy Selection (Stage 2)

| Contention Level | Recommended Pattern | Example |
|---|---|---|
| Low (threads ≤ CPUs) | **Asymmetric** — FG→`SCX_DSQ_GLOBAL`, BG→custom DSQ | RocksDB read-only (v6) |
| High (threads > CPUs, active bg work) | **Selective preemption** — dual DSQ + per-CPU kick | RocksDB stress (v7), Redis |
| External (co-located CPU hogs) | **Asymmetric + task storage** — deprioritize known hogs | Nginx + stress-ng |

### The Asymmetric Design Principle (Key Finding)

Through iterating on the RocksDB scheduler (v1→v6), we discovered:

> **Only intervene in scheduling of threads you want to deprioritize. Let high-priority threads use the default fast path.**

Routing foreground threads through a custom DSQ adds BPF dispatch overhead that hurts P99.9 latency. The correct approach: push background threads into a deprioritized custom DSQ, let the framework handle foreground threads via `SCX_DSQ_GLOBAL` natively.

### BPF Scheduler Structure

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
make -f ../../bpf_loader/Makefile BPF_SRC=scheduler.bpf.c \
     BPF_OBJ=scheduler.bpf.o scheduler.bpf.o

# Or from workloads/db_sim with its own Makefile
cd workloads/db_sim && make
```

### Workload-Specific Builds
```bash
# db_sim (synthetic)
cd workloads/db_sim && make

# RocksDB (real-world)
cd workloads/rocksdb_dbbench/rocksdb && make db_bench -j$(nproc)
```

## Running Experiments

### Quick A/B Test Pattern

```bash
# 1. Run workload under CFS (baseline)
./workload_binary [args] > /tmp/cfs_results.txt

# 2. Start custom scheduler
sudo ../../bpf_loader/loader ./scheduler.bpf.o &

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
sudo ../../bpf_loader/loader ./db_aware.bpf.o &
./db_sim -q 8 -c 24 -d 15
sudo pkill -f "loader.*db_aware"
```

### RocksDB Experiment
```bash
cd workloads/rocksdb_dbbench

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
sudo ../../bpf_loader/loader ./rocksdb_aware.bpf.o &
rocksdb/db_bench --benchmarks=readrandom --db=/tmp/rocksdb_bench_test \
    --use_existing_db=1 --duration=30 --threads=16 \
    --max_background_compactions=16 --statistics=1 --histogram=1
sudo pkill -f "loader.*rocksdb_aware"
```

### Nginx Experiment
```bash
cd workloads/nginx

# Compile BPF scheduler
make -f ../../bpf_loader/Makefile BPF_SRC=nginx_aware.bpf.c \
     BPF_OBJ=nginx_aware.bpf.o nginx_aware.bpf.o

# Automated A/B benchmark (builds nginx + wrk2 if needed, runs everything)
sudo ./nginx_bench_compare.sh 3
```

## Development Patterns

### Adding a New Application Workload

Follow the framework pipeline:

1. **Thread Discovery (Stage 1):**
   ```bash
   # Static analysis + LLM classification
   ./pipeline/run_stage1.sh <app_name> <source_path> <language> <description>

   # Or: runtime eBPF profiling (for apps without pthread_setname_np)
   sudo python3 pipeline/stage1c_dynamic_profiler.py --pid <pid> --duration 30 \
       --app-name <name> --output pipeline/results/<name>_manifest.json

   # Evaluate accuracy against ground truth
   python3 pipeline/evaluate_accuracy.py
   ```
2. **Policy Selection (Stage 2):**
   ```bash
   python3 pipeline/stage2_policy_select.py pipeline/results/<name>_manifest.json \
       --threads <N> --cpus <N> [--external]
   ```
3. **Scheduler Construction (Stage 3):** Generate a skeleton, then refine:
   ```bash
   # Generate BPF skeleton from manifest + pattern
   python3 pipeline/stage3_generate_scheduler.py pipeline/results/<name>_manifest.json \
       --pattern <selective_preemption|simple_dual_dsq|asymmetric_task_storage> \
       --name <name>_aware --output workloads/<name>/<name>_aware.bpf.c

   # Compile
   make -f bpf_loader/Makefile BPF_SRC=workloads/<name>/<name>_aware.bpf.c \
       BPF_OBJ=workloads/<name>/<name>_aware.bpf.o workloads/<name>/<name>_aware.bpf.o
   ```
4. **Validation (Stage 4):** Run A/B benchmark, then view unified results:
   ```bash
   # Run workload-specific benchmark script (see existing examples)
   # Then parse results into unified format
   python3 pipeline/stage4_validate.py --workload <name>

   # Or view all workloads
   python3 pipeline/stage4_validate.py --summary
   ```

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

- `document/design.md` — Framework design, scheduler patterns, and evaluation results
- `document/future_plan.md` — Research roadmap
- `bpf_loader/Makefile` — BPF compilation flags and include paths
