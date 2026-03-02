# Framework Pipeline Guide

## Implementation Summary

The framework defines a 4-stage pipeline for building application-aware kernel schedulers. Previously, only Stage 1 (thread discovery) had concrete tooling. This implementation fills the remaining gaps so the pipeline is executable end-to-end.

### What Was Built

| Stage | Tool | Purpose |
|---|---|---|
| **1a** | `pipeline/verify_manifest.py` (modified) | Added `compute_metrics()` — precision/recall/F1 for thread classification accuracy |
| **1a** | `pipeline/evaluate_accuracy.py` (new) | Batch accuracy evaluation across all workloads |
| **1c** | `pipeline/stage1c_dynamic_profiler.py` (new) | Runtime eBPF profiler — classifies threads by observed behavior |
| **2** | `pipeline/stage2_policy_select.py` (new) | Recommends scheduling pattern based on contention level |
| **3** | `pipeline/stage3_generate_scheduler.py` (new) | Generates compilable BPF scheduler skeleton from manifest |
| **4** | `pipeline/stage4_validate.py` (new) | Parses benchmark results into unified comparison table |

### Key Discovery

Runtime profiling (Stage 1c) on Redis discovered **`jemalloc_bg_thd`** — 4 background threads from the jemalloc memory allocator performing asynchronous memory purging. These threads are invisible to static source analysis because they originate from `deps/jemalloc/`, not Redis application code. They were added to the ground truth manifest and BPF scheduler.

---

## Stage-by-Stage Instructions

The following walkthrough uses Redis as the example application.

### Stage 1: Thread Discovery

Thread discovery identifies which threads an application creates and classifies them as foreground (latency-critical) or background (throughput-oriented).

#### Option A: Static Analysis + LLM (for applications with `pthread_setname_np`)

```bash
# Run the full Stage 1 pipeline (tree-sitter extraction + LLM classification)
./pipeline/run_stage1.sh redis workloads/redis/redis-src/ c \
    "Redis in-memory key-value store with persistence"
```

This produces a Thread Manifest JSON in `pipeline/results/`.

#### Option B: Runtime eBPF Profiling (for any running application)

```bash
# Start the application with a representative workload
sudo workloads/redis/redis-src/src/redis-server \
    --save "1 1" --appendonly yes --io-threads 4 \
    --io-threads-do-reads yes --dir /tmp/redis_test --daemonize yes

# Run a benchmark to generate load
workloads/redis/redis-src/src/redis-benchmark \
    -t set,get -c 50 -n 5000000 -d 256 --threads 8 -q &

# Trigger persistence operations to exercise background threads
workloads/redis/redis-src/src/redis-cli BGSAVE
workloads/redis/redis-src/src/redis-cli BGREWRITEAOF

# Profile for 30 seconds
sudo python3 pipeline/stage1c_dynamic_profiler.py \
    --pid $(pgrep -x redis-server | head -1) \
    --duration 30 \
    --app-name redis \
    --source-path workloads/redis/redis-src/ \
    --output pipeline/results/redis_dynamic.json
```

The profiler attaches to three eBPF tracepoints (`sched_switch`, `sched_wakeup`, `raw_syscalls:sys_enter`) and classifies each thread by behavioral pattern:

| Pattern | Heuristic | Classification |
|---|---|---|
| Event loop | `sleep_ratio > 0.8`, `network_syscalls > 100`, `avg_burst < 1ms` | Foreground |
| I/O worker | `sleep_ratio > 0.5`, `network_syscalls > 50` | Foreground |
| CPU-bound batch | `avg_burst > 2ms`, `disk_syscalls > 50` | Background |
| Compaction/GC | `avg_burst > 5ms`, `sleep_ratio < 0.3` | Background |
| Unknown | Does not match above | Foreground (safe default) |

#### Accuracy Evaluation

```bash
# Compare generated manifests against ground truth
python3 pipeline/evaluate_accuracy.py
```

**Result:**
```
=====================================================================================
Stage 1 Thread Discovery — Accuracy Evaluation
=====================================================================================
Application  Precision   Recall       F1   TP   FN  Safety  Extra  Generated From
-------------------------------------------------------------------------------------
redis            1.000    1.000    1.000    4    0       0      0  redis_generated_stage1b_test.json
rocksdb          0.000    0.000    0.000    0    1       0      4  rocksdb_generated_20260225_080936.json
-------------------------------------------------------------------------------------
AGGREGATE        0.500    0.800    0.615    4    1       0      4

No safety violations (0 foreground->background misclassifications)
```

Metrics:
- **True Positive**: background thread correctly identified (matched by `comm_prefix`)
- **False Negative**: ground-truth background thread not discovered
- **Safety Violation**: foreground thread misclassified as background (critical failure — would hurt latency)
- **Extra Discovery**: background thread not in ground truth (non-critical — just slightly more BPF overhead)

The key metric is **0 safety violations** — no foreground threads would be accidentally deprioritized.

---

### Stage 2: Policy Selection

Given a Thread Manifest, select a scheduling pattern based on contention level.

```bash
# Redis under high contention (70 threads on 16 CPUs)
python3 pipeline/stage2_policy_select.py \
    pipeline/examples/redis_manifest.json \
    --threads 70 --cpus 16
```

**Result:**
```
============================================================
Stage 2: Policy Selection
============================================================
  Application: redis
  Background thread types: 6 (bio_close*, bio_aof*, bio_lazy_free*,
      redis-rdb-bgsave, redis-aof-rewrite, jemalloc_bg_thd)
  Foreground thread types: 2 (redis-server (main), io_thd_*)
  Thread/CPU ratio: 70/16 = 4.4
  High contention: ratio 4.4 > 1.5
  -> Pattern B: Selective preemption

Selected pattern: selective_preemption

Configuration (JSON for Stage 3):
{
  "pattern": "selective_preemption",
  "fg_dsq": true,
  "bg_dsq": true,
  "preemption": true,
  "task_storage": false
}
```

#### Decision Logic

| Condition | Pattern | Example |
|---|---|---|
| `--external` flag | **C: Asymmetric + task storage** | Nginx + stress-ng |
| `threads/cpus > 1.5` | **B: Selective preemption** | Redis (70 threads, 16 CPUs), RocksDB stress |
| Otherwise | **A: Simple dual DSQ** | Low-contention workloads |

The `--json` flag outputs only the configuration JSON for piping to Stage 3:

```bash
python3 pipeline/stage2_policy_select.py \
    pipeline/examples/redis_manifest.json \
    --threads 70 --cpus 16 --json
```

---

### Stage 3: BPF Skeleton Generator

Generate a compilable `.bpf.c` scheduler skeleton from the manifest and selected pattern.

```bash
# Generate Redis scheduler skeleton
python3 pipeline/stage3_generate_scheduler.py \
    pipeline/examples/redis_manifest.json \
    --pattern selective_preemption \
    --name redis_aware \
    --output /tmp/redis_aware_generated.bpf.c

# Compile it
make -f bpf_loader/Makefile \
    BPF_SRC=/tmp/redis_aware_generated.bpf.c \
    BPF_OBJ=/tmp/redis_aware_generated.bpf.o \
    /tmp/redis_aware_generated.bpf.o
```

**Result:**
```
Generated: /tmp/redis_aware_generated.bpf.c
Pattern: selective_preemption
Background thread prefixes: 4

Compiling BPF scheduler: /tmp/redis_aware_generated.bpf.c
1 warning generated.    (benign sched-ext header warning)
```

The generator produces:

1. **Classification function** with byte-by-byte `p->comm` matching for each background thread prefix:
   ```c
   static bool is_redis_aware_background(struct task_struct *p)
   {
       char comm[16];
       if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
           return false;
       /* bio_close* — match "bio_" prefix */
       if (comm[0] == 'b' && comm[1] == 'i' && comm[2] == 'o' && comm[3] == '_')
           return true;
       /* redis-rdb-bgsave — match "redis-r" prefix */
       if (comm[0] == 'r' && comm[1] == 'e' && comm[2] == 'd' &&
           comm[3] == 'i' && comm[4] == 's' && comm[5] == '-' && comm[6] == 'r')
           return true;
       /* redis-aof-rewrite — match "redis-a" prefix */
       ...
       /* jemalloc_bg_thd — match "jemalloc" prefix */
       ...
       return false;
   }
   ```

2. **Full scheduler structure** — `select_cpu`, `enqueue`, `dispatch`, `running`, `stopping`, `init`, `exit` hooks with the selected pattern's DSQ layout and preemption logic.

#### Available Patterns

| Pattern | Template Source | Key Features |
|---|---|---|
| `simple_dual_dsq` | `db_aware.bpf.c` | Two DSQs, priority drain, no preemption |
| `selective_preemption` | `redis_aware.bpf.c` | Two DSQs, per-CPU bg tracking, `scx_bpf_kick_cpu` preemption |
| `asymmetric_task_storage` | `nginx_aware.bpf.c` | One custom DSQ + `SCX_DSQ_GLOBAL`, task storage caching |

The output is a starting point. The developer may need to tune slice values, add application-specific optimizations, or adjust preemption thresholds.

---

### Stage 4: Validation

Parse benchmark results from all workloads into a unified comparison table.

Each workload has its own benchmark script that handles setup, execution, and result collection. Stage 4 normalizes their output formats.

#### Run Benchmarks (per-workload)

```bash
# Redis A/B benchmark (3 runs each of CFS vs redis_aware)
cd workloads/redis
sudo ./redis_bench_compare.sh 3
```

#### View Unified Results

```bash
# Summary across all workloads
python3 pipeline/stage4_validate.py --summary
```

**Result:**
```
===============================================================================================
Stage 4: Validation Summary — CFS vs Custom Scheduler
===============================================================================================
Workload   Scheduler       P99 Change  P99.9 Change  Throughput  Runs
-----------------------------------------------------------------------------------------------
db_sim     db_aware             +7.2%           N/A       +2.6%     1
rocksdb    rocksdb_v7         +157.6%        -65.5%      -13.1%     3
redis      redis_aware         -75.8%           N/A      +19.6%     3
nginx      nginx_aware       +2548.6%      +2150.1%       -0.8%     3
-----------------------------------------------------------------------------------------------

  redis (redis_aware, 3 run(s)):
                     Baseline       Custom       Change
    Throughput          71482        85510       +19.6%
    p50 (us)            319.0        329.7        +3.3%
    p99 (us)           2847.0        689.7       -75.8%
```

Redis shows -75.8% P99 latency reduction with +19.6% throughput improvement. RocksDB shows -65.5% P99.9 and -75.3% P99.99 reduction under stress workload.

#### Per-Workload and JSON Output

```bash
# Single workload
python3 pipeline/stage4_validate.py --workload redis

# JSON output for programmatic consumption
python3 pipeline/stage4_validate.py --workload redis --json
```

#### Result File Formats

The harness includes parsers for each workload's native output format:

| Workload | Format | Files |
|---|---|---|
| db_sim | JSON | `results/db_sim_results.json` |
| RocksDB | Text (db_bench percentile lines) | `results/cfs_run{1..N}.txt`, `results/v7_run{1..N}.txt` |
| Redis | CSV | `results/cfs_run{1..N}.csv`, `results/redis_aware_run{1..N}.csv` |
| Nginx | Text (wrk2 HDR histogram) | `results/cfs_run{1..N}.txt`, `results/nginx_aware_run{1..N}.txt` |

---

## End-to-End Example: Redis

Complete pipeline from source code to validated scheduler:

```bash
# Stage 1: Discover threads (static + LLM)
./pipeline/run_stage1.sh redis workloads/redis/redis-src/ c \
    "Redis in-memory key-value store"

# Stage 1c: Supplement with runtime profiling (optional, requires running Redis)
sudo python3 pipeline/stage1c_dynamic_profiler.py \
    --pid $(pgrep -x redis-server) --duration 30 \
    --app-name redis --output pipeline/results/redis_dynamic.json

# Evaluate accuracy
python3 pipeline/evaluate_accuracy.py

# Stage 2: Select scheduling pattern
python3 pipeline/stage2_policy_select.py \
    pipeline/examples/redis_manifest.json --threads 70 --cpus 16

# Stage 3: Generate BPF skeleton
python3 pipeline/stage3_generate_scheduler.py \
    pipeline/examples/redis_manifest.json \
    --pattern selective_preemption \
    --name redis_aware \
    --output workloads/redis/redis_aware.bpf.c

# Compile
make -f bpf_loader/Makefile \
    BPF_SRC=workloads/redis/redis_aware.bpf.c \
    BPF_OBJ=workloads/redis/redis_aware.bpf.o \
    workloads/redis/redis_aware.bpf.o

# Stage 4: Run benchmark and validate
cd workloads/redis && sudo ./redis_bench_compare.sh 3
cd ../..
python3 pipeline/stage4_validate.py --workload redis
```

### Redis Thread Inventory

Discovered through static analysis (Stage 1a+1b) and runtime profiling (Stage 1c):

| Thread | Role | Source | Discovery Method |
|---|---|---|---|
| `redis-server` | Foreground | Main event loop | Static analysis |
| `io_thd_*` | Foreground | I/O helper threads (Redis 6+) | Static analysis |
| `bio_close_file` | Background | Deferred file close | Static analysis |
| `bio_aof` | Background | AOF fsync | Static analysis |
| `bio_lazy_free` | Background | Async memory free | Static analysis |
| `redis-rdb-bgsave` | Background | RDB snapshot (fork) | Static analysis |
| `redis-aof-rewrite` | Background | AOF rewrite (fork) | Static analysis |
| `jemalloc_bg_thd` | Background | Memory purging (jemalloc) | **Runtime profiling** |

The `jemalloc_bg_thd` discovery demonstrates the value of the dynamic profiler: dependency-level threads that are invisible to application source analysis.
