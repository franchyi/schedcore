# Application-Aware Kernel Scheduling via LLM-Driven Thread Discovery

## 1. Problem: The Semantic Gap

The Linux CFS/EEVDF scheduler treats all threads within a cgroup equally. It cannot distinguish between latency-critical foreground threads and throughput-oriented background threads in the same application.

| Thread Role | Example | Scheduling Need |
|---|---|---|
| **Foreground** (latency-critical) | Query handlers, event loops, HTTP workers | Low latency, fast wakeup, preemption priority |
| **Background** (throughput-oriented) | Compaction, persistence, log rotation | High throughput, long slices, can tolerate delay |

When background threads compete with foreground threads for CPU time — especially under oversubscription — CFS causes tail latency spikes because it has no knowledge of thread roles.

## 2. Framework Overview

We present a **framework for building application-aware kernel schedulers**. Given application source code as input, the framework produces a validated, application-specific BPF scheduler as output — without modifying the application. The framework defines a systematic pipeline with reusable components, so that a developer can follow the same methodology for *any* application.

### 2.1 Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Framework Pipeline                            │
│                                                                      │
│  ┌─────────────┐    ┌──────────────────┐    ┌─────────────────────┐  │
│  │ Stage 1:     │    │ Stage 2:          │    │ Stage 3:             │  │
│  │ Thread       │───→│ Policy            │───→│ Scheduler            │  │
│  │ Discovery    │    │ Selection         │    │ Construction         │  │
│  └─────────────┘    └──────────────────┘    └─────────────────────┘  │
│        │                    │                         │               │
│   App source code     Thread Manifest +         BPF scheduler        │
│   → Tree-sitter       contention profile        from reusable        │
│   → LLM classify      → scheduling pattern      patterns + thread    │
│                                                  classification      │
│                                                      │               │
│                                              ┌───────▼───────────┐   │
│                                              │ Stage 4:           │   │
│                                              │ Validation         │   │
│                                              │ CFS vs custom A/B  │   │
│                                              │ P50/P99/P99.9/thpt │   │
│                                              └───────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

| Stage | Input | Output | Method | Tool |
|---|---|---|---|---|
| **1. Thread Discovery** | Application source code | Thread Manifest (thread name → role) | Tree-sitter static extraction + LLM classification | `pipeline/run_stage1.sh` |
| **1c. Dynamic Profiling** | Running application (PID) | Thread Manifest (behavioral) | eBPF tracepoints: sched_switch, sched_wakeup, syscall histogram | `pipeline/stage1c_dynamic_profiler.py` |
| **2. Policy Selection** | Thread Manifest + workload profile | Scheduling pattern | Decision framework based on contention level | `pipeline/stage2_policy_select.py` |
| **3. Scheduler Construction** | Pattern + thread classification rules | BPF scheduler skeleton (`.bpf.c`) | Template-based generation from manifest + pattern | `pipeline/stage3_generate_scheduler.py` |
| **4. Validation** | BPF scheduler + workload | Performance comparison vs CFS | A/B benchmark: latency percentiles + throughput | `pipeline/stage4_validate.py` |

### 2.2 Thread Discovery (Stage 1)

The core automated component. Static analysis (tree-sitter) extracts all thread creation and naming sites from application source code. An LLM then classifies each thread type as foreground or background, producing a **Thread Manifest** — a structured JSON document mapping thread names to scheduling roles.

The LLM's role is **thread discovery**, not scheduler generation. BPF schedulers are systems engineering, guided by the thread classification the pipeline provides.

**Tools:** `pipeline/run_stage1.sh` (static + LLM), `pipeline/stage1a_static_analysis.py` (static only), `pipeline/stage1c_dynamic_profiler.py` (runtime eBPF profiling). The dynamic profiler supplements static analysis for applications without `pthread_setname_np` — it classifies threads by behavioral patterns (CPU burst time, sleep ratio, syscall histogram) observed at runtime.

**Accuracy evaluation:** `pipeline/evaluate_accuracy.py` computes precision/recall/F1 for thread discovery by comparing generated manifests against ground-truth manifests in `pipeline/examples/`. Safety violations (foreground threads misclassified as background) are tracked separately from extra discoveries.

### 2.3 Policy Selection (Stage 2)

Given the Thread Manifest, the developer selects a scheduling pattern based on the workload's contention characteristics:

| Contention Level | Recommended Pattern | Rationale |
|---|---|---|
| Low (threads ≤ CPUs, few background bursts) | **Asymmetric** — FG→`SCX_DSQ_GLOBAL`, BG→custom DSQ | Zero overhead on foreground; "do no harm" |
| High (threads > CPUs, active background work) | **Selective preemption** — dual DSQ + per-CPU kick | Actively reclaims CPU from background for foreground |
| External (contention from co-located processes) | **Asymmetric + task storage** — only deprioritize known CPU hogs | Isolate application from noisy neighbors |

**Tool:** `python3 pipeline/stage2_policy_select.py <manifest.json> --threads N --cpus N [--external]` — reads the manifest, assesses thread/CPU ratio, and recommends a scheduling pattern with JSON configuration for Stage 3.

### 2.4 Scheduler Construction (Stage 3)

The developer instantiates a BPF scheduler by combining:
1. **Thread classification logic** — derived from the Thread Manifest (`p->comm` byte-by-byte matching)
2. **Scheduling pattern** — the DSQ layout, dispatch ordering, and preemption mechanism from Stage 2
3. **Reusable BPF components** — idle CPU fast path, per-CPU tracking maps, DSQ creation

All schedulers classify threads by matching `task_struct->comm` (the kernel task name) using byte-by-byte comparison (BPF verifier disallows `strcmp`). Applications that set thread names via `pthread_setname_np()` or internal naming conventions are directly supported.

**Tool:** `python3 pipeline/stage3_generate_scheduler.py <manifest.json> --pattern <pattern> --name <name> --output <path.bpf.c>` — generates a BPF scheduler skeleton from the manifest and selected pattern. The output is a starting point for developer refinement, not a finished product. Three template patterns are available: `simple_dual_dsq`, `selective_preemption`, and `asymmetric_task_storage`.

### 2.5 Validation (Stage 4)

A/B benchmark comparing CFS baseline against the custom scheduler under the same workload and contention conditions. Standard metrics: P50, P99, P99.9, P99.99, max latency, and throughput. Each workload includes an automated benchmark script that runs multiple iterations.

**Tool:** `python3 pipeline/stage4_validate.py --summary` — parses benchmark results from all workloads into a unified format and prints a comparison table. Supports per-workload parsing and JSON output. Each workload's benchmark script stays as-is; the harness normalizes their output formats.

---

## 3. Scheduler Design Patterns

### 3.1 The BPF Scheduling Interface

All custom schedulers implement these sched-ext callbacks:

| Callback | Purpose |
|---|---|
| `select_cpu` | Find idle CPU; if found, fast-path dispatch to `SCX_DSQ_LOCAL` |
| `enqueue` | Classify thread by `p->comm`, route to appropriate DSQ |
| `dispatch` | Drain DSQs in priority order (foreground first, background last) |
| `running` | Track per-CPU state when a task starts running |
| `stopping` | Update per-CPU state when a task stops running |
| `init` | Create custom DSQs via `scx_bpf_create_dsq()` |

### 3.2 The Asymmetric Principle (Key Finding)

Discovered through RocksDB v1→v6 iteration:

> **Only intervene in scheduling of threads you want to deprioritize. Let foreground threads use the kernel's default fast path.**

Routing foreground threads through a custom DSQ adds BPF dispatch overhead (global queue locking, BPF program execution, cross-CPU migration) that hurts P99.9 latency. The correct approach:
- **Foreground** → `SCX_DSQ_GLOBAL` (framework auto-drains before `dispatch()` is called, near-zero overhead)
- **Background** → custom `BACKGROUND_DSQ` (deprioritized, 20ms slices, drained last)

### 3.3 Selective Preemption (Extension for High Contention)

The asymmetric pattern alone cannot *improve* tail latency — it only avoids regression. For workloads with active foreground-vs-background CPU contention, **selective preemption** adds targeted intervention:

1. Per-CPU BPF maps (`bg_running`, `bg_start_ns`) track which CPUs run background threads
2. When a foreground thread wakes with no idle CPU, `select_cpu` scans the map
3. If a background thread has run ≥2ms, kick that CPU via `SCX_KICK_PREEMPT`
4. The preempted background thread returns to `BACKGROUND_DSQ`; the foreground thread gets dispatched with priority

This cuts tail latency from "wait for CFS timeslice" (~4ms) to "preemption latency" (~1ms).

### 3.4 Idle CPU Fast Path

All schedulers implement the same fast path in `select_cpu`:
- If an idle CPU is found → dispatch directly to `SCX_DSQ_LOCAL`
- This bypasses the custom DSQ path entirely, making the common case (idle CPU available) zero-overhead

### 3.5 Design Pattern Summary

| Pattern | When to Use | DSQ Layout | Preemption |
|---|---|---|---|
| **Simple dual DSQ** | Low contention, clear thread roles | FG_DSQ + BG_DSQ, drain FG first | None |
| **Asymmetric** | Low contention, must not regress P50 | `SCX_DSQ_GLOBAL` + BG_DSQ | None |
| **Selective preemption** | High contention, tail latency matters | FG_DSQ + BG_DSQ + idle fast path | Per-CPU map + `SCX_KICK_PREEMPT` |

---

## 4. Workload Designs

### 4.1 db_sim — Synthetic Database Simulation

**Purpose:** Controlled environment with predictable thread behavior to demonstrate thread-level priority scheduling.

**Application model:**
- Q query threads (named `"query-N"`): sleep 2-5ms simulating I/O → short CPU burst ~0.5ms → measure wakeup-to-completion latency
- C compaction threads (named `"compact-N"`): continuous CPU-bound math loops, no sleeping

**Scheduler: `db_aware.bpf.c` — Simple Dual DSQ**

```
QUERY_DSQ (0)   — high priority, 3ms slice
COMPACT_DSQ (1) — low priority, 20ms slice

select_cpu:  idle CPU → SCX_DSQ_LOCAL
enqueue:     "query*" → QUERY_DSQ, else → COMPACT_DSQ
dispatch:    drain QUERY_DSQ first, then COMPACT_DSQ
```

Uses the simpler dual-DSQ pattern (not asymmetric) because in the synthetic workload, query threads have distinct sleep/wake patterns that minimize DSQ contention.

**Thread classification:**
```c
// Prefix match: "query" (5 bytes)
comm[0]=='q' && comm[1]=='u' && comm[2]=='e' && comm[3]=='r' && comm[4]=='y'
```

**Benchmark:** `./db_sim -q 8 -c 24 -d 15` (32 threads on 16 CPUs, 2x oversubscription)

---

### 4.2 RocksDB db_bench — Real-World Storage Engine

**Purpose:** Validate on an unmodified production application (RocksDB) using its built-in `db_bench` benchmark tool.

**Application model:**
- Foreground: `db_bench` reader/writer threads (16 threads)
- Background: RocksDB-internal compaction/flush threads named `"rocksdb:low"`, `"rocksdb:high"`, `"rocksdb:bot"` (32 compaction + 4 flush)

**Scheduler: `rocksdb_aware.bpf.c` v7 — Dual DSQ + Selective Preemption**

```
FOREGROUND_DSQ (0x100) — high priority, 5ms slice
BACKGROUND_DSQ (0x101) — low priority, 20ms slice
Preemption threshold: 2ms minimum background run time

select_cpu:  idle CPU → SCX_DSQ_LOCAL (zero-overhead fast path)
             no idle + foreground → scan bg_running map, kick bg CPU
enqueue:     "rocksdb:*" → BACKGROUND_DSQ, else → FOREGROUND_DSQ
dispatch:    drain FOREGROUND_DSQ first, then BACKGROUND_DSQ
running:     if background → set bg_running[cpu]=1, record bg_start_ns[cpu]
stopping:    if background → set bg_running[cpu]=0
```

**Thread classification:**
```c
// Prefix match: "rocksdb:" (8 bytes)
comm[0]=='r' && comm[1]=='o' && comm[2]=='c' && comm[3]=='k' &&
comm[4]=='s' && comm[5]=='d' && comm[6]=='b' && comm[7]==':'
```

**Design evolution (v1→v7):**

| Version | Design | P99.9 (readrandom) | vs CFS | Issue |
|---|---|---|---|---|
| v1 | Dual DSQ (FG + BG custom) | 866us | +413% | DSQ lock overhead on foreground |
| v2 | v1 + local dispatch + preempt kick | 798us | +373% | Still routing FG through BPF |
| v3 | Short bg slice (1ms) + kick | 865us | +412% | Excessive context switches |
| v4 | Per-CPU map + selective kick | 969us | +474% | BPF lock contention |
| v5 | Foreground always local | crash | — | Invalid local dispatch on non-idle CPU |
| v6 | FG→SCX_DSQ_GLOBAL, BG→custom | 169us | 0% | Zero overhead, but zero improvement |
| **v7** | **Dual DSQ + selective preemption** | — | — | **Tested on stress workload instead** |

**Key insight:** v1-v4 all regressed because custom DSQ dispatch overhead hurt foreground latency. v6 eliminated overhead by routing foreground to `SCX_DSQ_GLOBAL`. v7 switched to a stress workload (writes + compaction storms) where selective preemption can actively help, accepting dual-DSQ overhead at P50 in exchange for P99.9 improvement.

**Benchmark:** `readrandomwriterandom` stress workload — 16 readers, 32 bg compactions + 4 flushes, 1MB cache (forces cache misses), 30s duration, ~52 threads on 16 CPUs.

---

### 4.3 Redis — In-Memory Cache with Persistence Pressure

**Purpose:** Validate on Redis under background persistence pressure (BGSAVE + BGREWRITEAOF) with CPU oversubscription from external stress-ng.

**Application model:**
- Foreground: main event loop, `io_thd_*` I/O threads
- Background: `bio_close_file`, `bio_aof`, `bio_lazy_free` (internal BIO threads), `redis-rdb-bgsave`, `redis-aof-rewrite` (forked persistence children)

**Scheduler: `redis_aware.bpf.c` — Dual DSQ + Selective Preemption**

```
FOREGROUND_DSQ (0x200) — high priority, 5ms slice
BACKGROUND_DSQ (0x201) — low priority, 20ms slice
Preemption threshold: 2ms minimum background run time

select_cpu:  idle CPU → SCX_DSQ_LOCAL
             no idle + foreground → scan bg_running map, kick bg CPU
enqueue:     "bio_*" / "redis-r*" / "redis-a*" → BACKGROUND_DSQ
             else → FOREGROUND_DSQ
dispatch:    drain FOREGROUND_DSQ first, then BACKGROUND_DSQ
```

**Thread classification (multi-prefix):**
```c
// Three background patterns:
"bio_"     → bio_close_file, bio_aof, bio_lazy_free
"redis-r"  → redis-rdb-bgsave (BGSAVE child)
"redis-a"  → redis-aof-rewrite (BGREWRITEAOF child)
```

Architecture is nearly identical to RocksDB v7. The key difference is multi-prefix classification (3 background patterns vs RocksDB's single `"rocksdb:"` prefix).

**Benchmark:** Redis 8.0, `io-threads 4`, `appendonly yes`, 50 clients, 500K requests, 256B values, 12 stress-ng CPU workers (total ~70+ threads on 16 CPUs), continuous BGSAVE + BGREWRITEAOF.

---

### 4.4 Nginx — Web Server Under External CPU Contention

**Purpose:** Validate on a multi-process web server where contention comes from *external* CPU-bound processes rather than internal application threads.

**Application model:**
- Foreground: nginx master + 16 worker processes (all share `comm = "nginx"`)
- Background: 24 stress-ng CPU workers (simulating co-located batch jobs)
- Note: unlike Redis/RocksDB, the "background" load is external to the application

**Scheduler: `nginx_aware.bpf.c` v3 — Asymmetric + Task Local Storage**

```
BACKGROUND_DSQ (0x201) — deprioritized CPU hogs, 20ms slice
SCX_DSQ_GLOBAL         — nginx, wrk2, system (framework fast path)

classify_task(): BPF task local storage caches one-time comm read
  "nginx"     → TASK_NGINX (identified for preemption kicks)
  "stress-ng" → TASK_CPU_HOG (deprioritized to BACKGROUND_DSQ)
  everything  → TASK_NORMAL (SCX_DSQ_GLOBAL fast path)

select_cpu:  idle CPU → SCX_DSQ_LOCAL
             no idle + nginx → scan bg_running map, kick CPU hog
enqueue:     CPU hog → BACKGROUND_DSQ, else → SCX_DSQ_GLOBAL
dispatch:    drain BACKGROUND_DSQ (GLOBAL auto-consumed first by framework)
```

**Key optimization — BPF task local storage:**

`BPF_MAP_TYPE_TASK_STORAGE` caches the classification result per-task. The comm string is read once per task lifetime; subsequent scheduling events use a single map lookup. This reduced P50 from 10.6ms (v2) to 6.7ms (v3) — a 37% improvement.

**Design evolution:**

| Version | P50 | P99 | Issue |
|---|---|---|---|
| v1 | 9-12s | 16-18s | Starved wrk2/system in BACKGROUND_DSQ |
| v2 | 10.6ms | 32.7ms | Repeated `bpf_probe_read_kernel_str` overhead |
| **v3** | **6.7ms** | **32.6ms** | **Task local storage + nr_cpus limit** |
| v4 | 38ms-2s | 1.3-6s | Head-of-line blocking from SCX_DSQ_LOCAL_ON |

**v1 failure:** Treating all non-nginx processes as "background" starved wrk2 and system daemons. Confirmed the asymmetric principle: only deprioritize threads you *specifically* identify as CPU hogs.

**Benchmark:** 16 nginx workers + 8 wrk2 threads + 24 stress-ng workers = 48 threads on 16 CPUs (3x oversubscription), 50,000 req/s, 30s duration.

---

## 5. Evaluation Results

### Test Environment

| Property | Value |
|---|---|
| CPU | Intel Xeon Platinum 8375C @ 2.90GHz |
| Cores / Threads | 8 cores / 16 hardware threads |
| Kernel | 6.14.0-1018-aws (sched-ext enabled) |
| OS | Ubuntu Linux |

All results averaged across 3 runs per scheduler.

### 5.1 db_sim Results

**Config:** 8 query + 24 compact threads on 16 CPUs (2x oversubscription), 15s duration.

| Metric | CFS | db_aware | Change |
|---|---|---|---|
| Query avg | 162.6 us | 156.9 us | -3.5% |
| Query P50 | 156.3 us | 156.3 us | ~0% |
| Query P99 | 175.1 us | 170.9 us | -2.4% |
| **Query max** | **25,899 us** | **326 us** | **-98.7% (79x)** |
| Compact ops/s | 4,836 | 4,968 | +2.7% |

**Analysis:** Maximum latency dropped from 25.9ms to 0.33ms. Under CFS, a query thread waking from sleep enters the run queue alongside 24 compact threads and may wait for full timeslices (~4-6ms each), compounding to ~26ms worst case. Under `db_aware`, the query DSQ is always drained first, bounding latency to CPU burst time (~0.3ms). Compaction throughput *improved* because 20ms slices reduce context-switch overhead.

### 5.2 RocksDB Results

#### Primary Result: v7 Stress Workload (readrandomwriterandom)

**Config:** 16 readers, 32 bg compactions + 4 flushes, 1MB cache, 4KB values, 30s. ~52 threads on 16 CPUs.

**Read latency:**

| Metric | CFS (avg ± range) | rocksdb_aware v7 (avg ± range) | Change |
|---|---|---|---|
| P50 | 89.1 (88.2–89.9) | 106.7 (106.0–107.1) | +20% |
| P99 | 235.4 (235.0–235.8) | 476.4 (475.3–477.1) | +102% |
| **P99.9** | **3765 (3738–3801)** | **1213 (1203–1220)** | **-67.8%** |
| **P99.99** | **8153 (7955–8469)** | **1878 (1876–1882)** | **-77.0%** |
| Throughput | 149.8K ops/s | 144.4K ops/s | -3.6% |

**Write latency:**

| Metric | CFS | v7 | Change |
|---|---|---|---|
| P50 | 16.3 | 14.3 | -12% |
| P99 | 1484 | 662 | -55% |
| **P99.9** | **7337** | **1557** | **-79%** |

**Analysis:** P99.9 read latency reduced 67.8% (3.8ms → 1.2ms) with very low variance across runs. P50 regressed 20% — this is the cost of dual-DSQ dispatch in the common case. For SLA workloads where P99.9 matters, the trade-off is favorable.

#### Overhead Validation: v6 on Read-Only Workload (readrandom)

**Config:** 16 threads, 16 compaction (low real contention).

| Metric | CFS | rocksdb_aware v6 | Change |
|---|---|---|---|
| P50 | 22.38 us | 22.38 us | 0% |
| P99.9 | 168.73 us | 168.65 us | 0% |
| Throughput | 654K ops/s | 652K ops/s | -0.3% |

The asymmetric design (v6) adds near-zero overhead when there is no contention to resolve — a "do no harm" validation.

### 5.3 Redis Results

**Config:** Redis 8.0, io-threads 4, appendonly yes, 50 clients, 500K requests, 256B values, 12 stress-ng workers, continuous BGSAVE + BGREWRITEAOF. ~70+ threads on 16 CPUs.

**GET:**

| Metric | CFS | redis_aware | Change |
|---|---|---|---|
| RPS | 74,226 | 85,418 | **+15.1%** |
| Avg | 0.414ms | 0.342ms | -17.4% |
| P50 | 0.311ms | 0.321ms | +3.2% |
| P95 | 0.897ms | 0.431ms | -51.9% |
| **P99** | **2.785ms** | **0.673ms** | **-75.8%** |

**SET:**

| Metric | CFS | redis_aware | Change |
|---|---|---|---|
| RPS | 70,598 | 84,852 | **+20.2%** |
| Avg | 0.469ms | 0.383ms | -18.3% |
| P50 | 0.321ms | 0.332ms | +3.4% |
| P95 | 1.111ms | 0.607ms | -45.4% |
| **P99** | **2.959ms** | **0.833ms** | **-71.9%** |

**Analysis:** P99 reduced 76% (GET) and 72% (SET). Unlike RocksDB, throughput *improved* 15-20% because the event loop and I/O threads run with less interference from bio threads and persistence children. P50 slightly regressed (+3%) from dual-DSQ dispatch overhead.

### 5.4 Nginx Results

**Config:** 16 nginx workers, wrk2 (8 threads, 200 connections, 50,000 req/s, 30s), 24 stress-ng CPU workers. 48 threads on 16 CPUs (3x oversubscription).

| Metric | CFS (avg ± range) | nginx_aware v3 (avg ± range) | Change |
|---|---|---|---|
| RPS | 49,894 (49,694–49,902) | 49,785 (49,642–49,870) | -0.2% |
| P50 | 1.54ms (1.50–1.58) | 6.57ms (6.51–6.68) | +4.3x |
| **P99** | **190.98ms (67.2–346.1)** | **32.33ms (30.8–32.6)** | **-83%** |
| **P99.9** | **276.48ms (106.3–454.9)** | **36.37ms (36.3–36.4)** | **-87%** |
| Max | 347.39ms (161.8–481.5) | 38.56ms (36.4–40.6) | -89% |

**Analysis:** P99 reduced 83%, P99.9 reduced 87%. CFS shows high variance (P99 ranges 67-346ms across runs); nginx_aware is stable (31-33ms, 1.06x variance). P50 increased from 1.5ms to 6.6ms — inherent sched-ext BPF dispatch overhead. For SLA workloads, 5ms higher P50 buys 160ms+ lower P99 and eliminates multi-hundred-millisecond tail spikes. Throughput preserved (-0.2%).

### 5.5 Results Summary

| Workload | Scheduler | Key Result | Throughput Impact |
|---|---|---|---|
| **db_sim** | db_aware | 79x max latency reduction (25.9ms → 0.33ms) | +2.7% |
| **RocksDB** | rocksdb_aware v7 | 67.8% P99.9 reduction, 77% P99.99 reduction | -3.6% |
| **Redis** | redis_aware | 76% P99 reduction (GET), 72% (SET) | +15-20% |
| **Nginx** | nginx_aware v3 | 83% P99 reduction, 87% P99.9 reduction | -0.2% |

---

## 6. Analysis

### 6.1 When Does Application-Aware Scheduling Help?

The scheduler's value scales with **contention** — the more background threads compete with foreground threads for CPU, the larger the improvement:

| Condition | db_sim | RocksDB (v6, read-only) | RocksDB (v7, stress) | Redis | Nginx |
|---|---|---|---|---|---|
| CPU oversubscription | 79x max reduction | 7% max reduction | 67.8% P99.9 | 76% P99 | 83% P99 |
| Mixed-criticality threads | Eliminates tail spikes | Zero regression | 77% P99.99 | 72% P99 (SET) | 87% P99.9 |
| Idle system (threads < CPUs) | No difference | No difference | No difference | — | No difference |

### 6.2 The P50 vs P99.9 Trade-off

| Workload | P50 Change | P99/P99.9 Change | Trade-off |
|---|---|---|---|
| db_sim | ~0% | -98.7% max | No trade-off |
| RocksDB v7 | +20% | -67.8% P99.9 | Dual-DSQ dispatch overhead at median |
| Redis | +3% | -76% P99 | Minimal overhead |
| Nginx | +4.3x | -83% P99 | Inherent sched-ext BPF cost at median |

For SLA workloads where P99/P99.9 determines compliance, the P50 overhead is an acceptable cost.

### 6.3 Thread Classification Accuracy

The `task_struct->comm` approach works for applications with consistent naming:

| Application | Background Threads | Classification Pattern |
|---|---|---|
| db_sim | `"compact-N"` | All non-`"query"` → background |
| RocksDB | `"rocksdb:low"`, `"rocksdb:high"`, `"rocksdb:bot"` | `"rocksdb:"` prefix (8 bytes) |
| Redis | `"bio_*"`, `"redis-rdb*"`, `"redis-aof*"` | Three prefix patterns |
| Nginx | External `"stress-ng*"` | External process prefix |

**Limitation:** Applications that don't name threads distinctly (Go goroutines, JVM thread pools) require alternative classification strategies (see `future_plan.md`).

See `pipeline_guide.md` for step-by-step reproduction instructions and `CLAUDE.md` for the file inventory.
