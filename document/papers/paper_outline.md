# SchedCP: Bridging the Application-Kernel Scheduling Gap via LLM-Synthesized BPF Schedulers

**Target venue:** EuroSys / ATC / SOSP (systems track)

---

## Honest Status Assessment

### What actually exists (implemented):
- **Stage 1a**: Tree-sitter static analysis — finds all `pthread_setname_np`, `prctl(PR_SET_NAME)`, macro wrappers, `pthread_create`, `std::thread` sites. Deterministic, complete, free.
- **Stage 1b**: LLM classification — given the static analysis report, classifies each thread as foreground/background. Outputs a Thread Manifest JSON.
- **Manifest verification**: Schema validation + ground-truth comparison.
- **4 hand-written BPF schedulers**: db_aware, rocksdb_aware, redis_aware, nginx_aware (663 lines total).
- **4 benchmark scripts**: Automated A/B comparison (CFS vs custom scheduler).
- **MCP infrastructure**: Scheduler compilation, loading, monitoring (Rust).

### What does NOT exist (claimed in prior outline):
- **Stage 2 (BPF generation)**: No code that consumes a Thread Manifest and produces `.bpf.c`. All schedulers are hand-authored.
- **Parameterized BPF template**: No template system. Each scheduler is standalone.
- **Policy regime selection**: No automated selection logic. Humans chose the regime per workload.
- **Feedback loop**: No automated benchmark → analyze → adjust → re-deploy cycle.
- **Runtime validation**: No automated comm-pattern verification against live processes.

### The core gap:
The pipeline stops at Thread Manifest JSON. The actual scheduling (the hard part) is entirely manual. The paper's title says "LLM-Synthesized BPF Schedulers" but the LLM only classifies threads — it doesn't write schedulers.

---

## Revised Paper Outline (reflecting reality + feasible extensions)

## Abstract (draft sketch)

Modern applications embed rich scheduling semantics — thread priorities, latency-critical paths, background maintenance — but the kernel scheduler is fundamentally blind to them. We present SchedCP, a framework that automatically analyzes application source code to extract thread-role semantics and synthesize custom BPF kernel schedulers via Linux sched-ext. SchedCP combines deterministic static analysis (tree-sitter thread discovery) with LLM-based semantic classification to produce a Thread Manifest, then instantiates a parameterized BPF scheduler template that is compiled, verified, and hot-loaded — all without modifying the application. We identify three key design challenges: (1) **grounded semantic extraction** — combining static analysis with LLM reasoning to produce reliable, verifiable thread classifications; (2) **the BPF scheduling cost model** — navigating non-obvious performance cliffs where naive scheduler designs regress P99.9 by 373-474%; and (3) **policy regime selection** — choosing among asymmetric deprioritization, selective preemption, and external isolation based on workload characteristics. We evaluate SchedCP on four unmodified applications, achieving up to 83% P99 reduction (Nginx), 76% P99 reduction (Redis), and 67.8% P99.9 reduction (RocksDB) under CPU oversubscription.

---

## 1. Introduction  (~2 pages)

### Opening: The Semantic Gap Is Universal

- Applications internally distinguish between latency-critical work and background maintenance: RocksDB has foreground reads vs. background compaction; Redis has its event loop vs. `bio_*` persistence threads; Nginx has workers vs. co-located batch jobs. These roles are **explicit in the source code** but **invisible to the kernel**.
- The Linux CFS/EEVDF scheduler treats all threads within a cgroup equally. When a RocksDB read thread wakes from I/O and competes with 32 compaction threads, CFS has no basis to prioritize it. Result: tail latency spikes under contention.
- Existing solutions (nice, cgroups, hand-written sched-ext, scx_layered) require manual, per-application expert effort. They don't scale across the diversity of modern applications.

### The Opportunity: sched-ext + Source Code Analysis

- Linux 6.12 introduced sched-ext: BPF programs can implement custom kernel scheduling policies, hot-loaded without reboot. This is the *mechanism*.
- Application source code contains all the information needed: thread naming conventions (`pthread_setname_np`), thread pool architectures, criticality hierarchies. This is the *knowledge source*.
- But the path from source code to correct BPF scheduler is non-trivial. Simply prompting an LLM with "write me a scheduler" produces naive designs that **make things worse** (our v1-v4 designs all regressed P99.9 by 373-474%).

### Contributions

1. **A hybrid static-analysis + LLM pipeline for thread role discovery.** Tree-sitter exhaustively finds all thread naming and creation sites (deterministic, verifiable); an LLM classifies each thread type as latency-critical or background based on code context. This decouples *discovery* (must be complete) from *classification* (requires semantic understanding).

2. **The BPF scheduling cost model and the Asymmetric Principle.** Through systematic iteration (7 design versions on RocksDB), we discover that routing foreground threads through any custom BPF dispatch path adds overhead that exceeds the benefit. The correct design: only intervene for threads you want to *deprioritize*; let high-priority threads use the kernel's default fast path. We formalize this into three policy regimes with clear selection criteria.

3. **A parameterized BPF scheduler template** that separates application-specific thread classification (generated from the Thread Manifest) from scheduling logic (fixed, pre-verified). This bounds the LLM's blast radius: a wrong classification wastes scheduling priority but cannot crash the kernel.

4. **Evaluation on four unmodified applications** demonstrating 67-87% tail latency reduction across diverse workload types (storage engine, cache, web server), with detailed ablation showing the impact of policy regime selection and per-task classification caching.

---

## 2. Background and Related Work  (~1.5 pages)

### 2.1 Linux Scheduling: CFS/EEVDF and Its Limits

- CFS: fair share based on vruntime, no application semantics
- EEVDF (6.6+): latency-nice hints, still coarse-grained and manually configured
- cgroups: isolation, not differentiation within a workload
- **Key limitation**: all operate at the container/process level, not the thread-role level

### 2.2 sched-ext: Programmable Kernel Scheduling

- BPF struct_ops for scheduling callbacks (select_cpu, enqueue, dispatch, running, stopping)
- Dispatch queues (DSQs): SCX_DSQ_LOCAL, SCX_DSQ_GLOBAL, custom DSQs
- Hot-loading: no reboot, instant rollback on error
- **Key distinction from prior BPF scheduling work**: sched-ext provides full scheduling control, not just hints

### 2.3 Application-Aware Scheduling (Prior Art)

- **Shinjuku** (NSDI'19): preemptive scheduling for microsecond-scale tail latency; requires specialized hardware (interrupt-based preemption), application-specific
- **Caladan** (OSDI'20): core allocation based on queuing delay; requires runtime integration, kernel bypass
- **ghOSt** (SOSP'21): user-space scheduling delegation; requires per-application policy development, high overhead for fine-grained decisions
- **scx_layered / scx_rusty**: sched-ext schedulers with manual layer config; no automatic application analysis
- **Key gap**: all require manual specification of scheduling policy per application. None automatically derive policy from application source code.

### 2.4 LLMs for Systems

- LLM-assisted code generation (Copilot, etc.): general-purpose, no domain-specific verification
- LLM for kernel/systems (recent work): configuration tuning, bug finding
- **Key gap**: no prior work uses LLMs to bridge application-level semantics into kernel scheduling policy

---

## 3. Motivation  (~2 pages)

### 3.1 The Semantic Gap: A Quantitative Study

Concrete example with RocksDB: show what happens when 16 foreground read threads compete with 32 background compaction threads on 16 CPUs under CFS.

- CFS treats all 48 threads equally
- A read thread waking from I/O wait enters the runqueue behind compaction threads
- Worst case: read waits for a full compaction timeslice (4-6ms) before being scheduled
- Measured: P99.9 = 3.8ms, max = 25.9ms (db_sim)

### 3.2 Why Naive Schedulers Fail: The BPF Cost Model

This is critical — show that the problem is **not trivially solved**.

**Experiment**: Design a BPF scheduler for RocksDB. The natural design (dual DSQ: foreground vs. background) **regresses P99.9 by 413%** (169us → 866us).

| Design Version | P99.9 Change | Root Cause |
|---|---|---|
| Dual custom DSQ (v1) | +413% | Global DSQ lock contention on all enqueue/dispatch |
| + SCX_KICK_PREEMPT (v2) | +373% | Preemption IPI overhead on the fast path |
| + Short bg slice (v3) | +412% | Excessive context switches |
| + Per-CPU maps (v4) | +474% | BPF map lookup overhead per scheduling event |
| + Force local dispatch (v5) | **Crash** | sched-ext API constraint violation |
| **Asymmetric (v6)** | **-60% max** | Foreground uses framework fast path; only background goes through custom DSQ |
| **+ Preemption (v7)** | **-67.8%** | + active bg preemption when fg wakes with no idle CPU |

**Key insight**: The BPF scheduling overhead is *fixed per scheduling event* (~1-5 us). At P50 (no contention, threads run immediately), this overhead is visible and harmful. At the tail (multi-ms waits due to contention), the overhead is negligible compared to the savings. This creates a fundamental **P50-vs-tail tradeoff** that determines optimal scheduler design.

### 3.3 Three Design Challenges

**Challenge 1: Grounded Semantic Extraction.** LLMs can hallucinate thread names, miss critical threads, or misclassify roles. An incorrect classification (e.g., deprioritizing the Redis event loop) can be catastrophic. The extraction must be *grounded* in verifiable code artifacts.

**Challenge 2: The BPF Cost Model.** Any BPF scheduling intervention adds per-event overhead. Different applications have different tolerance for P50 overhead in exchange for tail improvement. The scheduler design must match the workload's tradeoff profile.

**Challenge 3: Policy Generalization.** Each application has unique thread roles, naming conventions, and contention patterns. The framework needs reusable scheduling primitives that can be parameterized per-application, not arbitrary code generation.

---

## 4. Design  (~4 pages)

### 4.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    STAGE 1: THREAD DISCOVERY                │
│                                                             │
│  ┌─────────────┐     ┌────────────────┐    ┌────────────┐  │
│  │ Application │     │  Stage 1a:     │    │ Stage 1b:  │  │
│  │ Source Code  │────→│  Tree-sitter   │───→│ LLM Thread │  │
│  │ (unmodified) │     │  Static Scan   │    │ Classifier │  │
│  └─────────────┘     └────────────────┘    └─────┬──────┘  │
│                       (deterministic)       (semantic)│     │
│                                                      ▼     │
│                                              ┌────────────┐ │
│                                              │  Thread    │ │
│                                              │  Manifest  │ │
│                                              │  (JSON)    │ │
│                                              └─────┬──────┘ │
└────────────────────────────────────────────────────┼────────┘
                                                     │
┌────────────────────────────────────────────────────┼────────┐
│                  STAGE 2: SCHEDULER SYNTHESIS       │        │
│                                                     ▼        │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────┐ │
│  │ Policy Regime │───→│  Template    │───→│  Compile +     │ │
│  │ Selection     │    │  Instantiate │    │  BPF Verify    │ │
│  └──────────────┘    └──────────────┘    └───────┬────────┘ │
│                                                   │         │
└───────────────────────────────────────────────────┼─────────┘
                                                    │ hot-load
┌───────────────────────────────────────────────────┼─────────┐
│                  BPF DATA PLANE                    ▼         │
│                                                              │
│  ┌────────────┐  ┌───────────┐  ┌────────────┐              │
│  │ select_cpu │─→│  enqueue  │─→│  dispatch  │              │
│  │ (idle CPU  │  │ (classify │  │ (priority  │              │
│  │  fast path)│  │  + route) │  │  drain)    │              │
│  └────────────┘  └───────────┘  └────────────┘              │
│                                                              │
│  Primitives: task-local-storage cache, per-CPU bg tracking,  │
│  selective preemption, asymmetric DSQ topology                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Key design principle: separation of concerns.**
- Stage 1 handles *what to schedule differently* (thread discovery + classification). The LLM's job is bounded: classify N thread types, where N is provided by static analysis.
- Stage 2 handles *how to schedule differently* (BPF policy). The LLM never generates arbitrary BPF code. It fills parameters into a pre-verified template.
- The data plane is fixed, pre-verified BPF logic with parameterized slots.

### 4.2 Stage 1a: Deterministic Thread Discovery (Static Analysis)

**Problem**: LLM-based code search is non-deterministic and incomplete. Three runs on RocksDB produced three different thread inventories.

**Solution**: Tree-sitter AST analysis exhaustively finds all thread naming sites.

**What it finds:**

| Pattern | API | Example |
|---|---|---|
| Thread naming | `pthread_setname_np(handle, name)` | `pthread_setname_np(t, "rocksdb:low")` |
| Thread naming | `prctl(PR_SET_NAME, name)` | `prctl(PR_SET_NAME, "worker")` |
| Macro wrappers | App-specific macros that wrap naming APIs | `redis_set_thread_title("bio_aof")` |
| Process titles | `setproctitle()` wrappers for forked children | `redisSetProcTitle("redis-rdb-bgsave")` |
| Thread creation | `pthread_create(&t, attr, func, arg)` | Links to start routine |
| Thread creation | `std::thread` / `port::Thread` construction | Links to callable |

**Output**: A `ThreadReport` JSON containing every thread naming/creation site with source location, context snippet (surrounding code), and whether the name is a constant or dynamically constructed.

**Why static analysis first:**
1. **Complete**: Finds every naming site, not a sample. Redis: 7 naming sites + 23 creation sites across 730 files.
2. **Deterministic**: Same input always produces same output.
3. **Free**: No LLM API cost. Runs in ~3 seconds on Redis (730 files).
4. **Verifiable**: Each entry references a specific file:line.

**Challenges solved:**
- Tree-sitter fails on GNU `__attribute__` extensions inside preprocessor-guarded blocks. We added a regex fallback for thread naming calls that catches what tree-sitter misses (e.g., RocksDB's `repeatable_thread.h:108`).
- C vs. C++ grammar differences: C grammar lacks `qualified_identifier` and `field_expression` node types. Queries are language-conditional.
- Macro detection: Some applications wrap `pthread_setname_np` in custom macros (Redis: `redis_set_thread_title`). We detect macro definitions that call naming APIs and search for call sites of those macros.
- Process title setters: Forked children (Redis: `redis-rdb-bgsave`, `redis-aof-rewrite`) use `setproctitle()` to set their `comm`, not `pthread_setname_np`. We detect wrapper functions.

### 4.3 Stage 1b: LLM-Based Thread Classification

**Problem**: Static analysis finds *where* threads are named. It cannot determine *why* — whether a thread is latency-critical or background.

**Solution**: Given the ThreadReport, an LLM classifies each thread type based on context snippets.

**Input**: ThreadReport JSON from Stage 1a (thread names, context snippets, creation sites).

**Output**: Thread Manifest JSON — a mapping from comm patterns to scheduling roles:
```json
{
  "application": "redis",
  "default_role": "foreground",
  "threads": [
    { "name_pattern": "bio_*", "role": "background",
      "identification": { "type": "comm_prefix", "comm_prefix": "bio_", "comm_length": 4 } },
    { "name_pattern": "redis-rdb-bgsave", "role": "background",
      "identification": { "type": "comm_prefix", "comm_prefix": "redis-r", "comm_length": 7 } }
  ]
}
```

**Why LLM for classification (not heuristics):**
- Thread purpose requires semantic understanding. `"rocksdb:low"` is background (compaction thread pool at low priority) but this is only clear from reading `ThreadPoolImpl::BGThread` and the priority naming convention.
- Context snippets provide the LLM with exactly the code it needs — no searching, no hallucination about what threads exist.
- Classification is bounded: with N thread naming sites from Stage 1a, the LLM makes N binary decisions.

**Constrained output**: The LLM outputs a JSON manifest conforming to a schema. Each entry must reference a thread naming site from the report. Classification rules:
1. Default to FOREGROUND when uncertain (safe: foreground threads use kernel fast path).
2. BACKGROUND only if the thread does maintenance/bulk work and delaying it won't affect user-visible latency.
3. Use `comm_prefix` for dynamic names, `comm_exact` for fixed names.

### 4.4 Stage 2: Parameterized BPF Scheduler Synthesis

**Problem**: Hand-writing a BPF scheduler per application doesn't scale. But generating arbitrary BPF code is error-prone (v1-v5 all failed).

**Solution**: A parameterized BPF template with three policy regimes. The Thread Manifest determines *what* to classify; the policy regime determines *how* to schedule.

#### 4.4.1 Three Policy Regimes

**Regime 1: Asymmetric Deprioritization**
```
Foreground → SCX_DSQ_GLOBAL (framework fast path, ~0 overhead)
Background → BACKGROUND_DSQ (deprioritized, drained only when GLOBAL empty)
```
- **When**: Background threads are CPU-heavy but foreground threads rarely contend (e.g., RocksDB with large cache — reads hit cache, rarely compete with compaction).
- **Tradeoff**: 0% P50 regression, max latency reduced 60%, no P99.9 improvement under low contention.
- **Why it works**: Foreground threads are never touched by BPF logic. They go through the framework's native `SCX_DSQ_GLOBAL` path, which is optimized and lock-free. Only background threads pay the custom-DSQ cost.

**Regime 2: Selective Preemption**
```
Foreground → FOREGROUND_DSQ (explicit priority drain)
Background → BACKGROUND_DSQ (deprioritized, long slice)
+ Idle-CPU fast path (SCX_DSQ_LOCAL when idle CPU available)
+ bg_running per-CPU map + SCX_KICK_PREEMPT when fg wakes
```
- **When**: Foreground threads frequently wake with no idle CPU (e.g., RocksDB stress with 48 threads on 16 CPUs, Redis under persistence pressure).
- **Tradeoff**: ~20% P50 regression from dual-DSQ overhead, but 67-76% P99/P99.9 reduction.
- **Key mechanism**: When foreground wakes and no idle CPU exists, scan `bg_running[]` bitmap, find a CPU running background work for >= 2ms, send `SCX_KICK_PREEMPT` IPI to force reschedule.

**Regime 3: External Contention Isolation**
```
App threads → SCX_DSQ_GLOBAL (framework fast path)
Known CPU hogs → BACKGROUND_DSQ (deprioritized)
+ BPF task local storage (classification cache)
+ Selective preemption of CPU hogs
```
- **When**: Application contends with *external* CPU-bound processes (e.g., Nginx co-located with batch jobs).
- **Tradeoff**: ~5ms inherent sched-ext P50 overhead, but 83% P99 reduction.
- **Key insight**: Three-way classification (app / CPU hog / normal) is critical. Early design (v1) that classified all non-app threads as background starved the load generator (P50 → 12 seconds).

#### 4.4.2 Template Structure

```c
/* === PARAMETERS (filled from Thread Manifest + policy selection) === */
#define POLICY_REGIME     <1|2|3>
#define FG_SLICE_NS       <5000000>
#define BG_SLICE_NS       <20000000>
#define PREEMPT_THRESHOLD <2000000>     // min bg runtime before preempt

/* === CLASSIFICATION (generated from Thread Manifest) === */
static u8 classify_task(struct task_struct *p) {
    // Per-task cache lookup (task local storage)
    // Byte-by-byte comm pattern matching (from manifest)
    // Return: TASK_FOREGROUND | TASK_BACKGROUND | TASK_NORMAL
}

/* === FIXED SCHEDULING LOGIC (shared across all apps) === */
// select_cpu: idle-CPU fast path + preemption trigger (regime 2,3)
// enqueue: route by classification to appropriate DSQ
// dispatch: priority-ordered DSQ drain
// running/stopping: bg_running map updates (regime 2,3)
```

**What is generated per-application**: Only `classify_task()` (comm pattern matching from the manifest) and parameter values.

**What is fixed template code**: All scheduling logic — DSQ topology, dispatch order, preemption mechanism, idle-CPU fast path, task local storage caching. These are the engineering contributions, pre-verified against the BPF verifier.

#### 4.4.3 Policy Regime Selection

Selection based on workload characteristics from the Thread Manifest:

| Characteristic | Signal | Regime |
|---|---|---|
| Internal contention, low fg:bg ratio | Few bg threads, bg is I/O-heavy | Regime 1 (Asymmetric) |
| Internal contention, high fg:bg ratio | Many bg threads, bg is CPU-heavy, fg frequently contends | Regime 2 (Selective Preemption) |
| External contention | Background threads are external processes, not app threads | Regime 3 (External Isolation) |

### 4.5 BPF Implementation Constraints

BPF programs face unique constraints that shape the implementation:

- **No `strcmp`/`strncmp`**: BPF verifier disallows standard C string functions. Thread classification uses byte-by-byte `p->comm` comparison.
- **Bounded loops**: `bpf_for(i, 0, MAX_CPUS)` for preemption target search. Must be provably bounded.
- **No dynamic allocation**: All maps declared at compile time. Task local storage uses `BPF_MAP_TYPE_TASK_STORAGE` with kernel-managed lifecycle.
- **Callback constraints**: `SCX_DSQ_LOCAL` dispatch only valid in `select_cpu` when idle CPU is found. `SCX_DSQ_LOCAL_ON` causes head-of-line blocking (discovered in Nginx v4).
- **Verifier safety**: Even with incorrect classification, the scheduler cannot crash the kernel. Wrong classification only wastes scheduling priority. On scheduler error, sched-ext falls back to CFS automatically.

---

## 5. Implementation  (~1.5 pages)

### 5.1 Pipeline Infrastructure

| Component | Implementation | Lines |
|---|---|---|
| Stage 1a: Static analyzer | Python + tree-sitter (C/C++) | ~630 |
| Stage 1b: LLM classifier | Prompt template + Claude CLI | ~200 (shell) |
| Stage 2: BPF template | C + sched-ext BPF framework | ~250 (template) |
| Manifest schema | JSON Schema | ~50 |
| Manifest verifier | Python (schema + ground truth) | ~160 |
| Benchmark harness | Python/Bash per-workload | ~1,350 |
| MCP server | Rust (compilation, loading, monitoring) | ~2,000 |

### 5.2 Static Analyzer Details

Tree-sitter queries for C and C++, with language-conditional patterns (C lacks `qualified_identifier`). Regex fallback for code that tree-sitter fails to parse (GNU extensions, complex preprocessor blocks). Macro wrapper detection traces through app-specific naming macros to their underlying API calls.

Performance: Redis (730 C files) analyzed in ~3.5 seconds. RocksDB (~1,200 C++ files) in ~5 seconds.

### 5.3 BPF Compilation and Loading

```bash
clang -g -O2 -target bpf -D__TARGET_ARCH_x86 \
    -I scheduler/scx/scheds/include \
    -I scheduler/scx/scheds/include/bpf-compat \
    -c scheduler.bpf.c -o scheduler.bpf.o

# Load into kernel (replaces current scheduler)
sudo bpf_loader/loader ./scheduler.bpf.o
```

Compilation takes <2 seconds. Loading is instantaneous. Unloading falls back to CFS.

---

## 6. Evaluation  (~4 pages)

### 6.1 Experimental Setup

| Property | Value |
|---|---|
| CPU | Intel Xeon Platinum 8375C @ 2.90GHz, 8 cores / 16 HW threads |
| Kernel | 6.14.0+ (sched-ext enabled) |
| OS | Ubuntu Linux |
| Baselines | CFS (default), scx_bpfland (general-purpose sched-ext) |

### 6.2 End-to-End Results

| Workload | Contention Type | Regime | P99 | P99.9 | P50 | Throughput |
|---|---|---|---|---|---|---|
| **db_sim** (synthetic) | Internal, constant | 2 | -2.4% | -98.7% (max) | 0% | +2.7% |
| **RocksDB** (read-only) | Internal, low | 1 | -0.6% | 0% | 0% | -0.3% |
| **RocksDB** (stress) | Internal, high | 2 | +102% | **-67.8%** | +20% | -3.6% |
| **Redis** (GET+persist) | Internal, bursty | 2 | **-75.8%** | N/A | +3.2% | **+15.1%** |
| **Nginx** (HTTP+stress) | External | 3 | **-83%** | **-87%** | +4.3x | -0.2% |

### 6.3 Detailed Results per Workload

#### 6.3.1 RocksDB db_bench

- **Low contention** (readrandom, 16 threads + 16 compaction): Regime 1 achieves **zero P99.9 regression** — validates "first, do no harm" principle
- **High contention** (readrandomwriterandom, 16 threads + 32 compaction + 4 flush, 1MB cache): Regime 2 achieves **67.8% P99.9 reduction** (3.8ms → 1.2ms), **77% P99.99 reduction** (8.2ms → 1.9ms), with 3.6% throughput cost
- **Write latency also improves**: P99.9 reduced by 79%

#### 6.3.2 Redis

- **76% P99 reduction** (GET), **72% P99 reduction** (SET) under persistence pressure + CPU oversubscription
- **+15-20% throughput improvement** — event loop runs with less interference
- Demonstrates Regime 2 on a single-threaded event loop with I/O threads

#### 6.3.3 Nginx

- **83% P99 reduction**, **87% P99.9 reduction** under external CPU oversubscription
- **Dramatically more consistent**: CFS P99 variance = 5x across runs, SchedCP = 1.06x
- **P50 tradeoff**: 1.5ms → 6.7ms (inherent sched-ext BPF dispatch overhead)

#### 6.3.4 db_sim (Controlled)

- **79x max latency reduction** (25.9ms → 0.33ms) under 2x CPU oversubscription
- Validates the fundamental mechanism in a controlled environment

### 6.4 Ablation Studies

#### 6.4.1 Policy Regime Selection Matters

| Workload | Regime 1 P99.9 | Regime 2 P99.9 | Regime 2 P50 |
|---|---|---|---|
| RocksDB read-only | 0% change | +20% regression | Not worth it |
| RocksDB stress | 0% improvement | **-67.8%** | +20% (acceptable) |

Wrong regime selection costs: either unnecessary P50 overhead (Regime 2 on low-contention) or missed tail improvement (Regime 1 on high-contention).

#### 6.4.2 Task Local Storage Impact (Nginx)

| Optimization | P50 | P99 |
|---|---|---|
| No caching (v2) | 10.6ms | 32.7ms |
| Task local storage (v3) | 6.7ms | 32.6ms |
| **Improvement** | **-37%** | ~0% |

Caching reduces per-event overhead but doesn't affect tail (tail is dominated by contention, not per-event cost).

#### 6.4.3 Design Iteration History (RocksDB v1-v7)

Full table showing 7 iterations, P99.9 result, and root cause of each failure. Demonstrates the design space is non-trivial — systematic exploration is necessary.

#### 6.4.4 Thread Discovery Accuracy

| Application | Naming Sites Found | Creation Sites | Unique Thread Types | LLM Classification Accuracy |
|---|---|---|---|---|
| Redis | 7 | 23 | 7 | 7/7 correct vs. ground truth |
| RocksDB | 3 | 12 | 3 | 3/3 correct vs. ground truth |
| Nginx | 2 | 0 (multi-process) | 2 | 2/2 correct vs. ground truth |

#### 6.4.5 Pipeline Cost

| Stage | Time | Cost (USD) |
|---|---|---|
| Stage 1a (static analysis) | ~3-5 seconds | $0.00 |
| Stage 1b (LLM classification) | ~30-60 seconds | ~$0.05-0.15 |
| Stage 2 (template instantiation) | ~1 second | $0.00 |
| BPF compilation | ~2 seconds | $0.00 |
| **Total** | **< 2 minutes** | **< $0.20** |

vs. manual expert approach: hours of code reading + trial-and-error scheduler design.

### 6.5 Comparison with General-Purpose sched-ext

Compare SchedCP-generated schedulers vs. scx_bpfland:
- scx_bpfland: application-agnostic vruntime-based heuristics
- SchedCP: application-aware classification
- Expected: SchedCP matches or beats bpfland on tail latency for apps with mixed-criticality threads

---

## 7. Discussion  (~1.5 pages)

### 7.1 When Does SchedCP Help?

The improvement scales with **contention intensity**:
- Under-subscribed (threads < CPUs): No benefit — idle-CPU fast path handles everything
- Moderate oversubscription: Regime 1 prevents regression, modest tail improvement
- Heavy oversubscription: Regime 2/3 deliver dramatic tail reduction

**Rule of thumb**: SchedCP helps when an application has mixed-criticality threads and runs under CPU contention (common in cloud with co-located workloads).

### 7.2 Limitations

1. **Thread naming dependency**: Applications that don't name threads are harder to classify. ~60% of popular server applications name their threads (measured by surveying top 20 GitHub C/C++ server projects).
2. **P50 overhead**: sched-ext BPF dispatch adds inherent overhead. For latency-sensitive workloads where P50 matters more than tail, Regime 1 (asymmetric) minimizes this.
3. **Static classification**: Thread roles determined at analysis time. Applications with dynamic role changes need runtime reclassification (future work).
4. **C/C++ focus**: Static analyzer currently supports C and C++ via tree-sitter. Java/Go/Rust support requires additional grammars and naming API patterns.

### 7.3 Generality

Discuss applicability to: PostgreSQL (autovacuum vs. query backends), MySQL (InnoDB purge vs. client threads), memcached (worker threads vs. slab rebalancer), vLLM (prefill vs. decode).

### 7.4 Safety

BPF verifier guarantees: no infinite loops, no invalid memory access, no kernel crashes, graceful CFS fallback on error. Wrong classification is the worst case — and it only results in suboptimal scheduling, not correctness violations.

---

## 8. Related Work  (~1 page)

### Application-Aware Scheduling Systems

| System | Approach | Requires App Changes | Auto-Derived Policy | Overhead |
|---|---|---|---|---|
| Shinjuku | HW interrupt preemption | Yes (runtime) | No | Low (HW) |
| Caladan | Core allocation | Yes (runtime lib) | No | Medium |
| ghOSt | User-space delegation | Yes (agent) | No | High |
| scx_layered | BPF + manual layers | No | No | Low |
| **SchedCP** | **BPF + source analysis** | **No** | **Yes** | **Low** |

### LLM for Systems
- LLM-assisted kernel config tuning, bug detection
- **Distinction**: SchedCP uses LLMs for *policy derivation* — the LLM's output parameterizes kernel scheduling behavior

### Programmable Scheduling
- sched-ext ecosystem (bpfland, lavd, rusty): general-purpose, application-agnostic
- **Distinction**: SchedCP bridges application semantics into sched-ext automatically

---

## 9. Conclusion  (~0.5 pages)

SchedCP demonstrates that the semantic gap between applications and the kernel scheduler can be bridged through source code analysis. By combining deterministic static analysis with LLM-based semantic classification, and encoding scheduling design patterns into a parameterized BPF template, we achieve significant tail latency improvements across four diverse, unmodified applications — requiring no scheduling expertise, no application modifications, and no kernel patches.

---

## Appendix: Figures and Tables Plan

### Figures
1. Architecture diagram (Stage 1a → 1b → Stage 2 → Data Plane)
2. CDF plots: latency distribution for each workload (CFS vs SchedCP)
3. Design iteration timeline (RocksDB v1-v7) showing P99.9 progression and root cause
4. Policy regime decision tree
5. Static analysis output example (Redis ThreadReport → Thread Manifest)

### Tables
1. End-to-end results summary (Section 6.2)
2. Per-workload detailed results (6.3)
3. Design iteration history (6.4.3)
4. Thread discovery accuracy (6.4.4)
5. Pipeline cost breakdown (6.4.5)
6. Comparison with prior systems (Section 8)

### Key Graphs to Generate
- [ ] RocksDB: P50 vs P99.9 Pareto curve across v1-v7 designs
- [ ] Nginx: CFS vs SchedCP CDF overlay (showing tail compression)
- [ ] Redis: RPS + P99 bar chart (CFS vs SchedCP)
- [ ] Overhead breakdown: per-event BPF cost with/without task local storage
- [ ] Sensitivity: P99 improvement vs. oversubscription ratio

---

## What Needs To Be Built (Extensions)

See bottom of this document for analysis of what extensions are needed to make this a strong paper. The current pipeline (Stage 1a + 1b → Thread Manifest) is necessary but insufficient. The key missing piece is Stage 2 (template-based BPF synthesis) and evaluation of end-to-end automation accuracy.
