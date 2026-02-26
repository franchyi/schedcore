# SchedCP: Future Plan

**Core thesis:** LLM + static analysis can identify thread roles (foreground vs background) from application source code, enabling developers to write application-aware sched-ext schedulers that eliminate tail latency — without modifying the application.

The LLM's role is **thread discovery**, not scheduler generation. Writing BPF schedulers is a systems engineering task best done by hand, guided by the thread classification the LLM provides.

---

## What We Have

| Component | Status |
|---|---|
| Stage 1a: Tree-sitter static thread extraction | Done |
| Stage 1b: LLM semantic classification | Done |
| Thread Manifest schema + verification | Done |
| Hand-written BPF schedulers (db_sim, RocksDB, Redis, Nginx) | Done |
| Benchmark results (4 workloads, 67-87% P99 reduction) | Done |

---

## 1. Strengthen Thread Discovery (Core Contribution)

The thread discovery pipeline (Stage 1) is the main research contribution. It needs to be more robust, cover more languages, and work on applications that don't cleanly name their threads.

### 1a. Improve Static Analysis Coverage

Current `stage1a_static_analysis.py` only handles C/C++ with tree-sitter. Extend to:

- **Go:** `go func()` goroutines, `runtime.LockOSThread()`, goroutine naming via labels
- **Rust:** `std::thread::Builder::new().name("...")`, `tokio::spawn` for async tasks
- **Java/JVM:** `Thread.setName()`, `ExecutorService` thread pools, `@Async` annotations

For each language, the tree-sitter query extracts thread creation sites and naming patterns. The LLM then classifies them — same two-step pipeline, different parsers.

### 1b. Dynamic Behavioral Profiling (Beyond Source Code)

Static analysis is brittle for applications that don't name their threads (Go goroutines, JVM thread pools, legacy C code). A lightweight eBPF profiler can observe thread behavior at runtime to supplement or replace static analysis.

**Approach:** Run a passive BPF profiler for 10-60 seconds that attaches to kernel tracepoints:

| Tracepoint | What it measures |
|---|---|
| `sched:sched_switch` | CPU burst time (schedule-in to schedule-out) |
| `sched:sched_wakeup` | Sleep duration, wakeup source (IRQ vs thread) |
| `raw_syscalls:sys_enter` | Syscall histogram per TID (network vs disk vs sync) |

**Per-thread metrics collected in BPF hash map:**
```c
struct thread_metrics {
    u64 total_run_time;
    u64 total_sleep_time;
    u64 num_cpu_bursts;
    u64 max_cpu_burst;
    u64 network_syscalls;  // epoll_wait, read, write, sendmsg, recvmsg
    u64 disk_syscalls;     // pwrite, fsync, fdatasync
};
```

**Classification heuristics:**
- **Foreground:** `total_sleep_time >> total_run_time` AND `network_syscalls > 1000` (event loop pattern)
- **Background:** `(total_run_time / num_cpu_bursts) > 2ms` AND `disk_syscalls > 100` (compaction/batch pattern)

**Output:** Same Thread Manifest JSON. The profiler produces a behavioral dossier per thread; the LLM (or heuristics) classifies each as foreground/background.

**Why this matters:** Makes SchedCP applicable to *any* application, not just C/C++ programs with clean thread naming. This is the key extension for conference reviewers who will ask "does this generalize?"

### 1c. Broaden Application Coverage

Add more workloads to demonstrate generality:

| Application | Thread Pattern | Expected Benefit |
|---|---|---|
| PostgreSQL | bgwriter, autovacuum, checkpointer vs query backends | Reduce query tail latency during vacuum |
| Memcached | worker threads vs slab rebalancer | Isolate cache hits from maintenance |
| MySQL/InnoDB | purge threads, page cleaner vs query threads | Reduce read latency during heavy writes |
| Kafka | log cleaner, compaction vs broker I/O threads | Reduce produce/consume latency |

For each: run Stage 1 to discover threads, hand-write BPF scheduler, benchmark CFS vs application-aware.

---

## 2. Scheduler Design Patterns (Systems Engineering)

The BPF schedulers are written by hand, but the design patterns we've discovered should be documented as reusable knowledge.

### Scheduling Regimes

| Regime | When to Use | Example |
|---|---|---|
| **Asymmetric Deprioritization** | Low contention; foreground must not regress | Nginx under normal load |
| **Selective Preemption** | High contention; background bursts steal CPU | RocksDB stress, Redis with BGSAVE |
| **External Isolation** | Background load comes from separate processes | Nginx + stress-ng co-location |

**Key design principle (discovered v1→v6):** Only intervene in scheduling of threads you want to *deprioritize*. Let foreground threads use the kernel's default fast path (`SCX_DSQ_GLOBAL`). Routing foreground threads through custom DSQs adds BPF dispatch overhead that hurts P99.9.

### Priority Inversion Awareness

Deprioritizing background threads can cause priority inversion when those threads hold locks needed by foreground threads:

- **RocksDB:** Compaction acquires `DBMutex` to install SST files. Starving compaction → foreground `Put()` blocks.
- **Redis:** BGSAVE saturates I/O bandwidth → foreground event loop hits `iowait`.
- **PostgreSQL:** bgwriter holds LWLocks on buffer partitions → query backends spin.

**Mitigation strategies** (hand-implemented per application):
- Give background threads long time slices (20ms) so they finish critical sections quickly once scheduled
- Monitor `iowait` states and temporarily boost background threads
- Use application USDT probes (e.g., `rocksdb:mutex_wait_start`) to detect lock-holding and boost dynamically

---

## 3. BPF Scheduling Cost Model (Theoretical Contribution)

A formal model explaining *why* and *when* application-aware scheduling helps, and when it hurts.

### Per-Event BPF Overhead

Every scheduling event (wake/sleep) invokes the BPF program:

$$O_{dispatch} = C_{ctx} + C_{map} + C_{lock} + (P_{kick} \times C_{ipi})$$

| Component | Cost | Description |
|---|---|---|
| $C_{ctx}$ | ~0.5μs | Kernel → BPF VM transition |
| $C_{map}$ | ~0.1μs | Task classification lookup (O(1) with task storage) |
| $C_{lock}$ | 0-10μs | DSQ spinlock contention (scales with cores) |
| $C_{ipi}$ | ~5μs | Inter-processor interrupt for preemption kick |

### The Trade-off

Foreground request latency: $L_{fg} = S + W + O_{dispatch}$

- **CFS:** $O_{dispatch} \approx 0$, but $W_{worst} \approx T_{bg}$ (4-5ms timeslice)
- **SchedCP:** $O_{dispatch} > 0$ on every event, but $W_{worst} \approx C_{ipi}$ (5μs)

**When SchedCP wins:** $W_{cfs} \gg O_{dispatch}$ — high contention workloads where foreground threads compete with background for CPU. Paying 5μs overhead to avoid 5ms wait = massive win (67-87% P99 reduction).

**When SchedCP loses:** $W_{cfs} \approx 0$ — low contention workloads. The BPF overhead is pure cost with no benefit. **This is why v1-v4 designs caused 400% P99.9 regression on read-only RocksDB.**

**Asymmetric fix:** Route foreground → `SCX_DSQ_GLOBAL` (no $C_{lock}$). Overhead drops to $C_{ctx} + C_{map}$ ≈ 1μs. Eliminates regression while still isolating background threads.

### Action Items

- Microbenchmark $C_{ctx}$, $C_{map}$, $C_{lock}$ across core counts (4, 8, 16, 32, 64)
- Plot cost surface: contention level × BPF overhead → P99 latency
- Validate model predictions against empirical results from 4 workloads

---

## Implementation Priority

| Priority | Item | Effort | Impact |
|---|---|---|---|
| **P0** | Broaden evaluation (PostgreSQL, Memcached) | Medium | Proves generality |
| **P0** | Cost model microbenchmarks | Medium | Theoretical foundation |
| **P1** | Dynamic behavioral profiler | High | Handles unnamed threads |
| **P1** | Go/Rust/Java static analysis | Medium | Language coverage |
| **P2** | USDT-based priority inversion detection | High | Hard systems problem |
| **P2** | Cost surface visualization | Low | Paper figure |
