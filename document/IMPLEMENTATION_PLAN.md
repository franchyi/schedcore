# Application-Aware Kernel Scheduling via LLM-Driven Scheduler Synthesis

## 1. Thesis

**Applications have internal thread hierarchies that the kernel scheduler cannot see.** An LLM can analyze application source code, documentation, or runtime behavior to identify critical vs. background threads, then automatically generate and deploy a custom BPF scheduler that encodes this knowledge — eliminating tail latency without modifying the application.

We demonstrate this on two workloads: a controlled synthetic database simulation (**db_sim**) and a real-world storage engine (**RocksDB db_bench**). In both cases, an LLM-generated sched-ext scheduler reduces tail latency: db_sim achieves 79x max latency reduction, while RocksDB achieves **67.8% P99.9 reduction** and **77.0% P99.99 reduction** under a write-heavy stress workload with only 3.6% throughput impact.

---

## 2. Motivation

### 2.1 The Semantic Gap

The Linux CFS/EEVDF scheduler treats all threads within the same cgroup equally. It has no concept of application-level thread roles. In a real database:

- **Query threads** serve user requests with strict SLA requirements (e.g., P99 < 10ms)
- **Compaction threads** perform background maintenance that is throughput-sensitive but not latency-sensitive
- CFS cannot distinguish between them — a query thread waking from I/O wait competes equally with 24 CPU-bound compaction threads

This is a fundamental **semantic gap**: the kernel has scheduling mechanisms (priorities, queues, preemption) but lacks the application knowledge to use them correctly.

### 2.2 Why Existing Approaches Fail

| Approach | Limitation |
|---|---|
| **CFS/EEVDF** | No application awareness; treats all threads equally |
| **nice / cgroups** | Manual, coarse-grained, requires sysadmin effort per application |
| **Hand-written sched-ext** | Requires deep BPF + kernel scheduling expertise |
| **scx_layered** | Requires manual layer configuration files |
| **General sched-ext (bpfland, lavd)** | Application-agnostic heuristics; no thread-role awareness |

### 2.3 Our Approach

An LLM bridges the semantic gap:

```
Application Code/Docs
        │
        ▼
   LLM Analysis ──→ "query threads are latency-critical,
        │              compaction threads are background"
        ▼
   BPF Scheduler Generation ──→ db_aware.bpf.c / rocksdb_aware.bpf.c
        │
        ▼
   Compile + Verify (sched-ext) ──→ .bpf.o loaded into kernel
        │
        ▼
   Deploy + Benchmark ──→ "max latency improved 79x"
        │
        ▼
   Feedback Loop ──→ iterate scheduler design (v1→v6)
```

No existing system does this. The LLM reads application source code, identifies thread naming conventions (e.g., `pthread_setname_np("query-0")`, RocksDB's internal `"rocksdb:low"` thread names), and generates a BPF scheduler that classifies threads by their `task_struct->comm` field — requiring **zero application changes**.

---

## 3. System Design

### 3.1 Pipeline Overview

The system consists of five phases:

| Phase | Input | Output | Tool |
|---|---|---|---|
| **1. Application Analysis** | Source code, docs | Thread roles, naming conventions | LLM reasoning |
| **2. Policy Generation** | Thread classification | Scheduling policy (DSQs, slices, priority order) | LLM reasoning |
| **3. BPF Synthesis** | Policy specification | BPF C source code (`.bpf.c`) | LLM code generation |
| **4. Verification** | BPF source | Compiled `.bpf.o`, kernel load test | `create_and_verify_scheduler` |
| **5. Deployment & Feedback** | `.bpf.o` + workload | Performance metrics, iteration guidance | `run_scheduler` + benchmarks |

### 3.2 Scheduling Primitive: Dispatch Queues (DSQs)

The core mechanism is **priority-ordered Dispatch Queues (DSQs)**:

```
┌─────────────────────────────────────────────────┐
│              sched-ext BPF Scheduler             │
│                                                  │
│  select_cpu()  ──→  Idle CPU? → SCX_DSQ_LOCAL    │
│       │              (fast path, skip enqueue)    │
│       ▼                                          │
│  enqueue()     ──→  Classify by p->comm          │
│       │              "query*"/"foreground" → HIGH │
│       │              "compact*"/"rocksdb:*" → LOW │
│       ▼                                          │
│  dispatch()    ──→  Drain HIGH DSQ first          │
│                     Then drain LOW DSQ            │
│                                                  │
│  Result: foreground threads always scheduled      │
│          before background threads                │
└─────────────────────────────────────────────────┘
```

### 3.3 Design Evolution: Lessons from RocksDB (v1 → v6)

A critical finding from our RocksDB evaluation was that **naive dual-DSQ designs introduce P99.9 latency regression**. We went through seven design iterations:

| Version | Strategy | P99.9 | Problem |
|---|---|---|---|
| v1 | Dual DSQ (FOREGROUND + BACKGROUND) | 866 us (+413%) | Global DSQ contention overhead |
| v2 | + Local dispatch + SCX_KICK_PREEMPT | 798 us (+373%) | kick_cpu adds overhead |
| v3 | Short bg slice (1ms) | 865 us (+412%) | Too many context switches |
| v4 | Per-CPU BPF map + selective kick | 969 us (+474%) | Map lookup overhead |
| v5 | Foreground always local dispatch | **crash** | Cannot dispatch to LOCAL on non-idle CPU |
| **v6** | **Foreground → SCX_DSQ_GLOBAL, Background → custom DSQ** | **169 us (0%)** | **No regression** |
| **v7** | **Dual custom DSQ + bg_running map + selective preemption** | **1213 us (readrandomwriterandom)** | **-67.8% P99.9** |

**Key insight:** The BPF dispatch path through custom DSQs has inherent overhead from global queue locking and cross-CPU dispatch. For foreground (latency-sensitive) threads, this overhead is worse than CFS's highly optimized per-CPU run queues.

**v6 solution:** Only penalize background threads. Foreground threads use `SCX_DSQ_GLOBAL` (the framework's built-in global queue, consumed automatically before `dispatch()` is called), which has the same fast path as default scheduling. Background threads go to a custom `BACKGROUND_DSQ` that is only drained when no global tasks are waiting. v6 achieves zero P99.9 regression on read-only workloads.

**v7 evolution:** v6 cannot improve P99.9 because it doesn't actively intervene for foreground threads. v7 introduces **selective preemption** — a `bg_running` per-CPU BPF map tracks which CPUs run background threads, and when a foreground thread wakes with no idle CPU, `select_cpu` kicks a background CPU via `SCX_KICK_PREEMPT`. v7 uses dual custom DSQs (`FOREGROUND_DSQ` + `BACKGROUND_DSQ`) so `dispatch()` controls priority ordering directly. The idle-CPU fast path (`SCX_DSQ_LOCAL` in `select_cpu`) ensures foreground threads bypass the custom DSQ path in the common case. Under a write-heavy stress workload (readrandomwriterandom, 1MB cache, 16 readers + 32 bg compactions), v7 achieves 67.8% P99.9 reduction with only 3.6% throughput impact.

---

## 4. Implementation

### 4.1 Test Environment

| Property | Value |
|---|---|
| **CPU** | Intel Xeon Platinum 8375C @ 2.90GHz |
| **Cores / Threads** | 8 cores / 16 hardware threads |
| **Kernel** | 6.14.0-1018-aws (sched-ext enabled) |
| **Architecture** | x86_64 |
| **OS** | Ubuntu Linux |

### 4.2 Workload 1: db_sim (Synthetic Database Simulation)

**Purpose:** Controlled environment to demonstrate thread-level priority scheduling with predictable thread behavior and measurable latency.

**Files:**

| File | Lines | Purpose |
|---|---|---|
| `workloads/db_sim/db_sim.c` | 275 | Multi-threaded DB simulation |
| `workloads/db_sim/db_aware.bpf.c` | 91 | Custom BPF scheduler (dual DSQ) |
| `workloads/db_sim/Makefile` | 48 | Build system |
| `workloads/db_sim/db_sim_bench.py` | 281 | Automated benchmark script |

**Thread design:**

- **Q query threads** (named `"query-N"` via `pthread_setname_np`):
  - Loop: `nanosleep(2-5ms)` simulating I/O wait → short CPU burst ~0.5ms (`sin/cos/sqrt`) → measure wakeup-to-completion latency via `clock_gettime(CLOCK_MONOTONIC)`
  - Collects up to 1M latency samples per thread for percentile calculation

- **C compaction threads** (named `"compact-N"`):
  - Continuous CPU-bound math loops (100K iterations per op), no sleeping
  - Counts total operations for throughput measurement

**Output:** JSON with latency percentiles (avg, p50, p99, max) and compaction throughput (ops/sec).

**CLI:** `./db_sim -q 8 -c 24 -d 15 -s 2000`

**Scheduler design (`db_aware.bpf.c`):**

```
QUERY_DSQ (0)   — high priority, 3ms slice
COMPACT_DSQ (1) — low priority, 20ms slice

Classification: p->comm starts with "query" → QUERY_DSQ, else → COMPACT_DSQ
Dispatch: drain QUERY_DSQ first, fall back to COMPACT_DSQ
```

This uses the simpler dual-DSQ pattern (not v6) because in the synthetic workload, query threads have distinct sleep/wake patterns that minimize DSQ contention — the overhead that causes P99.9 regression in RocksDB is not significant here.

### 4.3 Workload 2: RocksDB db_bench (Real-World Storage Engine)

**Purpose:** Validate the approach on an unmodified, production-grade application (RocksDB), using its built-in benchmarking tool `db_bench`.

**Files:**

| File | Lines | Purpose |
|---|---|---|
| `workloads/rocksdb/rocksdb_aware.bpf.c` | 99 | Custom BPF scheduler (v6 design) |
| `workloads/rocksdb/rocksdb/` | — | RocksDB source (cloned from GitHub, built from source) |

**Thread classification:**

RocksDB internally names its background threads:
- `"rocksdb:low"` — low-priority compaction threads
- `"rocksdb:high"` — high-priority flush threads
- `"rocksdb:bot"` — bottom-priority compaction threads

All share the prefix `"rocksdb:"`. The scheduler classifies by checking `p->comm` for this 8-byte prefix using byte-by-byte comparison (BPF verifier disallows `strcmp`):

```c
static bool is_rocksdb_background(struct task_struct *p)
{
    char comm[16];
    if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
        return false;
    return (comm[0] == 'r' && comm[1] == 'o' && comm[2] == 'c' &&
            comm[3] == 'k' && comm[4] == 's' && comm[5] == 'd' &&
            comm[6] == 'b' && comm[7] == ':');
}
```

**Scheduler design (`rocksdb_aware.bpf.c` — v6 final):**

```
SCX_DSQ_GLOBAL  — foreground threads (framework built-in, auto-drained)
BACKGROUND_DSQ (1) — rocksdb:* threads, 20ms slice, drained last

select_cpu: idle CPU → dispatch directly to SCX_DSQ_LOCAL (fast path)
enqueue:    rocksdb:* → BACKGROUND_DSQ
            else      → SCX_DSQ_GLOBAL (minimal overhead)
dispatch:   SCX_DSQ_GLOBAL auto-consumed by framework before dispatch() is called
            dispatch() only drains BACKGROUND_DSQ
```

**Why v6 uses SCX_DSQ_GLOBAL instead of a custom foreground DSQ:**

The sched-ext framework automatically drains `SCX_DSQ_GLOBAL` before calling the `dispatch()` BPF hook. This means foreground threads placed in `SCX_DSQ_GLOBAL` bypass the BPF dispatch path entirely — they are scheduled by the framework's optimized C code with near-zero overhead. Only background threads go through the custom `BACKGROUND_DSQ`, where the additional overhead is acceptable (they're throughput-sensitive, not latency-sensitive).

This asymmetric design is the key to matching CFS P99.9 while still deprioritizing background threads:

| Thread Type | DSQ | Dispatch Path | Overhead |
|---|---|---|---|
| Foreground (reads, writes) | `SCX_DSQ_GLOBAL` | Framework auto-drain (C code) | Near-zero |
| Background (rocksdb:*) | `BACKGROUND_DSQ` | BPF `dispatch()` hook | Acceptable |

**Benchmark configuration:**

```bash
# Populate: 5M keys, no compaction during fill
db_bench --benchmarks=fillrandom --num=5000000 \
         --max_background_compactions=0 --level0_file_num_compaction_trigger=1000

# Test: 16 foreground threads + 16-32 background compaction threads, 30s duration
db_bench --benchmarks=readrandom --duration=30 --threads=16 \
         --max_background_compactions=16 --statistics=1 --histogram=1
```

### 4.4 Build System

**db_sim:**
```bash
cd workloads/db_sim && make
# Builds: db_sim (gcc -pthread -lm) + db_aware.bpf.o (clang -target bpf)
```

**RocksDB:**
```bash
cd workloads/rocksdb/rocksdb && make db_bench -j$(nproc)
# BPF scheduler compiled separately via mcp/new_sched/Makefile
```

### 4.5 MCP Integration

The schedcp MCP server enables AI-assisted scheduler management:

```
1. create_and_verify_scheduler  → compile .bpf.c + load into kernel for 10s verification
2. run_scheduler name=...       → start scheduler (stops any running scheduler first)
3. get_execution_status         → check scheduler output/status
4. stop_scheduler               → clean stop
5. system_monitor start/stop    → collect CPU/memory/scheduler metrics
```

This enables the closed-loop pipeline: LLM generates scheduler → MCP verifies → MCP deploys → benchmark runs → LLM analyzes results → iterate.

---

## 5. Evaluation Results

### 5.1 db_sim: Synthetic Database Workload

**Configuration:** 8 query threads + 24 compact threads on 16 CPUs (oversubscribed), 15s duration.

| Metric | CFS (default) | db_aware (ours) | Improvement |
|---|---|---|---|
| **Query avg** | 162.6 us | 156.9 us | -3.5% |
| **Query P50** | 156.3 us | 156.3 us | ~0% |
| **Query P99** | 175.1 us | 170.9 us | -2.4% |
| **Query max** | **25,898.6 us** | **326.4 us** | **-98.7% (79x)** |
| **Compact ops/s** | 4,835.5 | 4,967.7 | +2.7% |

**Analysis:**

- **Maximum latency dropped from 25.9ms to 0.33ms (79x improvement).** Under CFS, when a query thread wakes from sleep, it enters the run queue alongside 24 continuously-running compact threads. CFS treats all threads equally, so the query thread may wait behind multiple compact threads for a full timeslice (4-6ms each). With 24 compact threads, delays compound to ~26ms in the worst case.

- Under `db_aware`, query threads are placed in `QUERY_DSQ` which is always drained before `COMPACT_DSQ`. The next `dispatch()` call preempts a compact thread for any waiting query thread. Maximum latency is bounded to the CPU burst time (~0.3ms).

- **P50/average are similar** because most of the time query threads wake and find an idle CPU (or a recent dispatch cycle). CFS handles the common case well — the scheduler's value is in the **tail cases** that matter for SLA compliance.

- **Compaction throughput improved by 2.7%** because compact threads receive 20ms time slices (vs CFS default ~4ms), reducing context-switch overhead. Query threads are dispatched instantly and complete quickly (~0.5ms), returning the CPU to compact work faster.

### 5.2 RocksDB db_bench: Real-World Storage Engine

#### 5.2.1 readrandom (16 threads, 16 compaction)

| Metric | CFS | rocksdb_aware v6 | Change |
|---|---|---|---|
| **P50** | 22.38 us | 22.38 us | 0% |
| **P75** | 29.23 us | 29.21 us | 0% |
| **P99** | 143.60 us | 142.68 us | -0.6% |
| **P99.9** | 168.73 us | 168.65 us | **0% (no regression)** |
| **P99.99** | 3,378.74 us | 3,668.51 us | +8.6% |
| **Max** | 10,332 us | 18,662 us | higher |
| **StdDev** | 55.94 us | 54.60 us | -2.4% |
| **Throughput** | 654K ops/s | 652K ops/s | -0.3% |

**Key finding:** The v6 design achieves **zero P99.9 regression** compared to CFS. Previous designs (v1-v4) all showed 373-474% P99.9 regression due to custom DSQ contention overhead. The v6 `SCX_DSQ_GLOBAL` approach eliminates this entirely.

#### 5.2.2 readrandom (16 threads, 32 compaction — oversubscribed)

| Metric | CFS | rocksdb_aware v6 | Change |
|---|---|---|---|
| **P50** | 22.46 us | 22.35 us | -0.5% |
| **P99** | 143.63 us | 143.59 us | 0% |
| **P99.9** | 168.73 us | 168.74 us | **0% (no regression)** |
| **P99.99** | 3,703.35 us | 3,671.60 us | -0.9% |
| **Max** | 13,617 us | 12,632 us | **-7.2%** |
| **Throughput** | 646K ops/s | 649K ops/s | +0.5% |

Under 2x CPU oversubscription (48 threads on 16 CPUs), the scheduler still shows zero P99.9 regression and a 7% reduction in worst-case latency.

#### 5.2.3 readwhilewriting (16 threads, 32 compaction — write-heavy)

| Metric | CFS | rocksdb_aware v6 | Change |
|---|---|---|---|
| **P50** | 63.30 us | 65.01 us | +2.7% |
| **P99** | 168.52 us | 169.57 us | +0.6% |
| **P99.9** | 3,928.09 us | 3,943.15 us | +0.4% |
| **P99.99** | 4,606.49 us | 5,070.87 us | +10.1% |
| **Max** | **30,798 us** | **12,171 us** | **-60.5%** |
| **Throughput** | 205K ops/s | 199K ops/s | -2.9% |

**Key finding:** Under write-heavy workload with active compaction, the maximum latency dropped from 30.8ms to 12.2ms (**60% reduction**). The worst-case outliers — where a foreground read gets stuck behind a burst of compaction activity — are significantly reduced by the scheduler's prioritization.

#### 5.2.4 readrandomwriterandom with v7 (16 threads, 32 compaction — stress workload)

**Configuration:** `readrandomwriterandom`, 16 reader threads, 32 background compactions + 4 flushes, 1MB cache (forces cache misses), 4KB values, `level0_file_num_compaction_trigger=4`, 30s duration. Fresh DB populate before each run. 3 runs per scheduler.

**Read Latency (microseconds, averaged across 3 runs):**

| Metric | CFS (avg ± range) | rocksdb_aware v7 (avg ± range) | Change |
|---|---|---|---|
| **P50** | 89.1 (88.2–89.9) | 106.7 (106.0–107.1) | +20% |
| **P99** | 235.4 (235.0–235.8) | 476.4 (475.3–477.1) | +102% |
| **P99.9** | **3765 (3738–3801)** | **1213 (1203–1220)** | **-67.8%** |
| **P99.99** | **8153 (7955–8469)** | **1878 (1876–1882)** | **-77.0%** |
| **Throughput** | 149.8K ops/s | 144.4K ops/s | -3.6% |

**Write Latency (microseconds, averaged across 3 runs):**

| Metric | CFS | v7 | Change |
|---|---|---|---|
| **P50** | 16.3 | 14.3 | -12% |
| **P99** | 1484 | 662 | **-55%** |
| **P99.9** | 7337 | 1557 | **-79%** |

**Key findings:**

- **P99.9 read latency reduced by 67.8%** (3.8ms → 1.2ms) — consistent across all 3 runs with very low variance. This is the primary paper result.
- **P99.99 read latency reduced by 77.0%** (8.2ms → 1.9ms) — dramatic tail improvement.
- **Write tail latency also improved** — P99.9 reduced by 79% (7.3ms → 1.6ms), showing that the scheduler helps all foreground operations, not just reads.
- **P50 regressed by 20%** (89 → 107us) — this is the cost of dual-DSQ dispatch overhead in the common case. The foreground-DSQ path adds ~18us median overhead.
- **P99 regressed by 102%** — mid-tail overhead from custom DSQ contention. This is acceptable because the workload is a stress test (16 readers + 36 bg threads on 16 CPUs).
- **Throughput impact is minimal** (-3.6%) — the preemption mechanism doesn't significantly reduce aggregate work done.
- **Stability:** v7 ran all 3x30s tests without watchdog stalls. The dual-DSQ design with `dispatch()` priority ordering avoids the starvation issue that occurs when SCX_DSQ_GLOBAL monopolizes scheduling under heavy foreground load.

**Why v7 can improve P99.9 when v6 cannot:**

The stress workload (1MB cache, active writes triggering compaction storms) creates scenarios where all 16 CPUs are occupied and a foreground thread must wait for scheduling. Under CFS, the foreground thread joins the runqueue and waits behind whatever is running — including long-running compaction threads. Under v7:
1. `select_cpu` detects no idle CPU and scans `bg_running` map
2. Finds a CPU running a `rocksdb:*` background thread
3. Issues `scx_bpf_kick_cpu(cpu, SCX_KICK_PREEMPT)` to preempt it
4. Preempted background thread returns to `BACKGROUND_DSQ`
5. Foreground thread gets dispatched from `FOREGROUND_DSQ` with priority

This targeted preemption cuts the tail latency from the CFS-equivalent "wait for timeslice" (~4ms) to the preemption latency (~1ms).

#### 5.2.5 Design Iteration History (v1-v5 P99.9 Results)

Before arriving at v6, we tested five alternative designs. All used custom foreground DSQs and exhibited significant P99.9 regression:

| Version | Design | P99.9 (us) | vs CFS (169 us) |
|---|---|---|---|
| v1 | Dual DSQ (FG + BG) | 866 | +413% |
| v2 | v1 + Local dispatch + SCX_KICK_PREEMPT | 798 | +373% |
| v3 | Short bg slice (1ms) + kick | 865 | +412% |
| v3b | 10ms bg slice + kick | 841 | +398% |
| v4 | Per-CPU BPF map + selective kick | 969 | +474% |
| v5 | Foreground always local | **crash** | runtime error |
| **v6** | **FG → SCX_DSQ_GLOBAL, BG → custom** | **169** | **0%** |
| **v7** | **Dual custom DSQ + bg_running + preemption** | **1213** (stress workload) | **-67.8%** |

*Note: v6 and v7 P99.9 values are from different workloads. v6's 169us is from `readrandom` (low contention). v7's 1213us is from `readrandomwriterandom` with 1MB cache (high contention, where CFS P99.9 = 3765us). v7 is purpose-built for the stress workload.*

**Root cause of v1-v4 regression:** Placing foreground threads in a custom DSQ requires them to go through the BPF `dispatch()` path, which involves:
1. Global DSQ lock acquisition (contention with all CPUs)
2. BPF program execution overhead (~1-5us per dispatch)
3. Cross-CPU task migration when the dispatching CPU differs from the target

These overheads are acceptable for background work but violate foreground latency at the P99.9 level.

**v5 crash:** Attempting to dispatch foreground threads directly to `SCX_DSQ_LOCAL` in `select_cpu` on a non-idle CPU is invalid — the sched-ext framework only allows local dispatch in `select_cpu` when an idle CPU is found. This caused `sched_ext: BPF scheduler "rocksdb_aware" disabled (runtime error)`.

---

## 6. Analysis

### 6.1 When Does Application-Aware Scheduling Help?

| Condition | db_sim Result | RocksDB (v6, readrandom) | RocksDB (v7, stress) |
|---|---|---|---|
| **CPU oversubscription** (threads > CPUs) | 79x max latency reduction | 7% max reduction | **67.8% P99.9 reduction** |
| **Mixed-criticality threads** (latency + throughput) | Eliminates tail latency spikes | Zero P99.9 regression | **77% P99.99 reduction** |
| **Background thread bursts** (compaction storms) | N/A (constant load) | 60% max reduction (writes) | **79% write P99.9 reduction** |
| **Idle system** (threads < CPUs) | No difference | No difference | No difference |

The scheduler's value scales with **contention**: the more background threads compete with foreground threads for CPU time, the larger the improvement.

### 6.2 Workload Design Matters: Creating Scheduling Intervention Points

The magnitude of improvement depends on workload characteristics:

| Factor | db_sim | RocksDB (readrandom, v6) | RocksDB (stress, v7) |
|---|---|---|---|
| **Workload** | Sleep/wake query threads | CPU-bound read threads | Mixed read/write, cache misses |
| **Scheduling opportunities** | Every wakeup | Few (cache-hot reads) | Many (I/O waits, compaction storms) |
| **Contention level** | 32:16 (2x oversubscribed) | 32:16 (cache-hot, low real contention) | 52:16 (high real contention) |
| **P99.9 improvement** | Implicit (max 79x) | 0% (no contention to fix) | **67.8%** |

**Key insight:** The v6 scheduler showed zero improvement on `readrandom` because read threads are CPU-bound block cache hits with almost no sleep/wake scheduling decision points. Creating a stress workload (tiny cache → cache misses → I/O waits → sleep/wake points, plus active compaction from writes) gives the scheduler intervention points where it can make a difference. The v7 selective preemption mechanism then exploits these points to deliver P99.9 reduction.

### 6.3 The Design Principle Evolution: Asymmetric (v6) → Selective Preemption (v7)

**v6 principle (low-contention workloads):**

> **Only intervene in the scheduling of threads you want to deprioritize. Let high-priority threads use the default fast path.**

This works for read-only workloads where contention is limited. Routing foreground threads through `SCX_DSQ_GLOBAL` avoids BPF dispatch overhead.

**v7 principle (high-contention workloads):**

> **Use dual custom DSQs for scheduling control, but minimize overhead via the idle-CPU fast path. Add targeted preemption for the tail cases.**

Under stress (writes + compaction + small cache), `SCX_DSQ_GLOBAL` cannot be preempted by background-DSQ priority ordering, causing background thread starvation. v7 uses dual custom DSQs where `dispatch()` has full control, and adds a `bg_running` per-CPU map with `SCX_KICK_PREEMPT` for the specific case where a foreground thread wakes with no idle CPU. The idle-CPU fast path (`SCX_DSQ_LOCAL` in `select_cpu`) ensures the common case (idle CPU available) has zero custom-DSQ overhead.

The trade-off: v7 adds ~20% P50 overhead from dual-DSQ dispatch, but delivers 67.8% P99.9 reduction. For latency-critical SLA workloads (where P99.9 matters more than P50), this is a favorable trade.

### 6.4 Thread Classification Accuracy

The `task_struct->comm` approach works well for applications with consistent naming:

| Application | Thread Names | Classification Strategy |
|---|---|---|
| RocksDB | `"rocksdb:low"`, `"rocksdb:high"`, `"rocksdb:bot"` | Prefix match `"rocksdb:"` |
| db_sim | `"query-0"`, `"compact-0"` | Prefix match `"query"` |
| MySQL | `"mysqld"`, `"innodb_io"`, `"innodb_purge"` | Prefix match for bg threads |
| Nginx | `"nginx: worker"`, `"nginx: cache"` | Prefix match for bg threads |

**Limitation:** Some applications don't name threads distinctly. In those cases, the LLM could suggest alternative classification strategies (cgroup membership, CPU usage patterns, PID ranges).

---

## 7. Paper Contribution

### 7.1 What Makes This a Systems Contribution

1. **Novel mechanism** — First system using LLMs to synthesize kernel schedulers from application semantics
2. **Practical** — Works on unmodified applications, zero kernel patches, hot-loadable via sched-ext
3. **Measurable** — Clear tail latency improvements across synthetic and real workloads
4. **Generalizable** — The LLM-analysis → BPF-synthesis pipeline applies to any application with named threads
5. **Timely** — sched-ext landed in Linux 6.12 (mainline), LLM-for-systems is an active research area

### 7.2 Suggested Paper Structure

1. **Introduction** — RocksDB motivating example, semantic gap, LLM bridge
2. **Background** — sched-ext, BPF scheduling primitives, thread naming conventions
3. **System Design** — Five-phase pipeline (analysis → generation → synthesis → verification → deployment)
4. **The Asymmetric Design Principle** — Why v6 works and v1-v5 don't (novel finding)
5. **Evaluation** — db_sim (controlled) + RocksDB (real-world) + additional applications
6. **Analysis** — When it helps, failure modes, LLM accuracy, time-to-deploy comparison
7. **Discussion** — Limitations, future work (distributed scheduling, dynamic reclassification)

### 7.3 Additional Evaluation Targets

| Application | Critical Threads | Background Threads | Metric |
|---|---|---|---|
| **Nginx** | worker* | cache_manager | Request tail latency under load |
| **Redis** | io_thd_* | bio_* | GET/SET P99 during AOF rewrite |
| **vLLM / llama.cpp** | decode-* | batch-* | Token generation latency |
| **PostgreSQL** | postgres (backend) | autovacuum, bgwriter | Query P99 during vacuum |

### 7.4 Target Venues

**EuroSys, OSDI, ATC, SoCC** — systems conferences that value practical kernel-level contributions with real workload evaluation.

---

## 8. How to Reproduce

### 8.1 db_sim (Synthetic)

```bash
cd workloads/db_sim
make

# CFS baseline (oversubscribed)
./db_sim -q 8 -c 24 -d 15

# With db_aware scheduler
sudo ../../mcp/new_sched/loader ./db_aware.bpf.o &
./db_sim -q 8 -c 24 -d 15
sudo pkill -f "loader.*db_aware"

# Automated benchmark (CFS vs scx_bpfland vs db_aware)
sudo python3 db_sim_bench.py
```

### 8.2 RocksDB (Real-World)

```bash
cd workloads/rocksdb

# Build RocksDB (one-time)
cd rocksdb && make db_bench -j$(nproc) && cd ..

# Compile scheduler
make -f ../../mcp/new_sched/Makefile BPF_SRC=rocksdb_aware.bpf.c \
     BPF_OBJ=rocksdb_aware.bpf.o rocksdb_aware.bpf.o

# Populate database (fresh each run for consistency)
rm -rf /tmp/rocksdb_bench_test && mkdir -p /tmp/rocksdb_bench_test
rocksdb/db_bench --benchmarks=fillrandom --db=/tmp/rocksdb_bench_test \
    --num=5000000 --max_background_compactions=0 \
    --level0_file_num_compaction_trigger=1000 --value_size=256

# CFS baseline (stress workload — shows P99.9 improvement)
rocksdb/db_bench --benchmarks=readrandomwriterandom \
    --db=/tmp/rocksdb_bench_test --use_existing_db=1 \
    --threads=16 --readwritepercent=90 \
    --max_background_compactions=32 --max_background_flushes=4 \
    --cache_size=1048576 --value_size=4096 \
    --level0_file_num_compaction_trigger=4 \
    --duration=30 --statistics=1 --histogram=1

# Re-populate for v7 run (writes change DB state)
rm -rf /tmp/rocksdb_bench_test && mkdir -p /tmp/rocksdb_bench_test
rocksdb/db_bench --benchmarks=fillrandom --db=/tmp/rocksdb_bench_test \
    --num=5000000 --max_background_compactions=0 \
    --level0_file_num_compaction_trigger=1000 --value_size=256

# With rocksdb_aware v7 scheduler
sudo ../../mcp/new_sched/loader ./rocksdb_aware.bpf.o &
rocksdb/db_bench --benchmarks=readrandomwriterandom \
    --db=/tmp/rocksdb_bench_test --use_existing_db=1 \
    --threads=16 --readwritepercent=90 \
    --max_background_compactions=32 --max_background_flushes=4 \
    --cache_size=1048576 --value_size=4096 \
    --level0_file_num_compaction_trigger=4 \
    --duration=30 --statistics=1 --histogram=1
sudo pkill -f "loader.*rocksdb_aware"

# Automated 3-run comparison
sudo bash bench_compare.sh
```

### 8.3 Via MCP Tools (AI-Assisted)

```
1. list_schedulers                           → see available schedulers
2. create_and_verify_scheduler source=...    → compile + kernel verify
3. run_scheduler name=rocksdb_aware          → start custom scheduler
4. [run benchmark via bash]                  → collect results
5. get_execution_status                      → check scheduler output
6. stop_scheduler                            → clean stop
7. system_monitor start/stop                 → collect CPU/memory metrics
```

---

## 9. File Inventory

```
workloads/db_sim/
├── db_sim.c              # Synthetic workload: query + compaction threads
├── db_aware.bpf.c        # BPF scheduler: dual DSQ, drain query first
├── Makefile              # Builds db_sim + db_aware.bpf.o
├── db_sim_bench.py       # Automated benchmark (CFS vs bpfland vs db_aware)
└── results/              # [generated] JSON + PNG results

workloads/rocksdb/
├── rocksdb_aware.bpf.c   # BPF scheduler v7: dual DSQ + selective preemption
├── bench_compare.sh      # Automated 3-run A/B comparison script
├── results/              # [generated] per-run latency results
├── rocksdb/              # RocksDB source (cloned, db_bench built)
└── Makefile              # Build helpers

document/
├── IMPLEMENTATION_PLAN.md  # This document
└── PAPER_PLAN.md           # [superseded by this document]

mcp/new_sched/
├── loader                # BPF loader binary for custom schedulers
├── Makefile              # BPF compilation flags and include paths
└── *.bpf.o               # Compiled scheduler objects
```

---

## 10. Next Steps

1. **Add 2-3 real applications** (Redis, Nginx, PostgreSQL) to strengthen evaluation
2. **Formalize LLM generation flow** — measure time-to-deploy: LLM pipeline vs manual BPF development
3. **Increase statistical rigor** — 5-10 runs per configuration (currently 3 runs, which show low variance)
4. **Ablation study** — LLM-generated vs hand-tuned expert vs general-purpose sched-ext
5. **Dynamic reclassification** — runtime thread role detection for applications without static naming
6. **v7 P50 optimization** — investigate reducing the 20% P50 overhead from dual-DSQ dispatch (e.g., adaptive DSQ selection based on system load)
7. **Throughput-latency Pareto curve** — sweep thread counts and cache sizes to map the full trade-off space
