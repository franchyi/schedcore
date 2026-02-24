# LLM Analysis Transcripts: Application-Aware Scheduler Synthesis

This document records the LLM's analysis process, prompts, reasoning, and results
for each workload in the SchedCP project. Extracted from Claude Code conversation
transcripts.

---

## 1. RocksDB (db_bench)

### 1.1 Initial Prompt and Context

**User prompt (framing the paper thesis):**
> "This is a strong paper idea. The core contribution is: **LLM-driven,
> application-aware kernel scheduler synthesis via sched-ext**."

**Workload selection prompt:**
> "I'll go with **RocksDB + db_bench** -- it's the perfect match for our
> thread-priority story (read threads vs compaction threads, exactly like
> db_sim but real)."

### 1.2 LLM Thread Analysis

**Source code analyzed:** RocksDB source tree (`src/db/`, `src/util/`, `db_bench`)

**Thread inventory discovered:**

| Thread Name | Source Location | Role | Classification |
|---|---|---|---|
| `rocksdb:low` | `env/env_posix.cc` (thread pool) | Low-priority compaction | Background |
| `rocksdb:high` | `env/env_posix.cc` (thread pool) | High-priority flush (write buffer) | Background |
| `rocksdb:bot` | `env/env_posix.cc` (thread pool) | Bottom-priority compaction | Background |
| `db_bench` main threads | `tools/db_bench_tool.cc` | Reader/writer threads | **Foreground** |

**LLM's key reasoning:**
1. RocksDB uses `pthread_setname_np()` to mark thread roles with consistent naming
2. All background threads share the 8-byte prefix `"rocksdb:"`
3. Foreground = db_bench reader/writer threads (latency-sensitive, serve user requests)
4. Background = rocksdb:* threads (throughput-sensitive, can tolerate scheduling delay)
5. This is a classic mixed-criticality workload

**Classification code generated:**
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

### 1.3 Design Iterations and Reasoning

**v1: Dual DSQ (naive approach)**
- Design: `FOREGROUND_DSQ` + `BACKGROUND_DSQ`, drain foreground first
- Result: **+413% P99.9 regression** (169us -> 866us)
- LLM diagnosis: "Global DSQ lock contention overhead — every foreground enqueue
  takes the global lock, adding latency on the hot path"

**v2: + Local dispatch + SCX_KICK_PREEMPT**
- Design: v1 + preemption kicks for background threads
- Result: **+373% P99.9 regression** (798us)
- LLM diagnosis: "SCX_KICK_PREEMPT sends IPIs which add overhead even when
  preemption isn't necessary"

**v3: Short background slice (1ms)**
- Design: v1 + reduced background timeslice to 1ms
- Result: **+412% P99.9 regression** (865us)
- LLM diagnosis: "Too many context switches — 1ms slices cause excessive
  scheduling overhead for background threads"

**v4: Per-CPU BPF map + selective kick**
- Design: Per-CPU map tracking background threads, only kick when needed
- Result: **+474% P99.9 regression** (969us)
- LLM diagnosis: "BPF map lookup overhead on every scheduling event adds up"

**v5: Foreground always local dispatch**
- Design: Dispatch foreground directly to SCX_DSQ_LOCAL in select_cpu
- Result: **Kernel crash** (sched_ext runtime error)
- LLM diagnosis: "Cannot dispatch to SCX_DSQ_LOCAL on a non-idle CPU — this is
  a sched-ext API constraint. LOCAL dispatch only valid when select_cpu found
  an idle CPU."

**v6: Asymmetric breakthrough**
- Design: Foreground -> `SCX_DSQ_GLOBAL`, Background -> custom `BACKGROUND_DSQ`
- Result: **0% P99.9 regression** (168.65us vs 168.73us baseline)
- LLM reasoning: "The sched-ext framework automatically drains SCX_DSQ_GLOBAL
  before calling dispatch(). This means foreground threads bypass the BPF
  dispatch path entirely — they are scheduled by the framework's optimized C
  code with near-zero overhead. Only background threads go through the custom
  DSQ."

**Key insight discovered:**
> "Only intervene in scheduling of threads you want to deprioritize. Let
> high-priority threads use the default fast path."

**v7: Selective preemption (stress workload)**
- Problem: v6 achieves zero regression but cannot *improve* P99.9 on read-only
  workloads because it doesn't actively intervene for foreground threads
- Design: Dual custom DSQs + `bg_running` per-CPU map + `SCX_KICK_PREEMPT`
  + idle-CPU fast path (`SCX_DSQ_LOCAL`)
- LLM reasoning:
  > "The fundamental problem: the framework consumes SCX_DSQ_GLOBAL *before*
  > calling dispatch(). So background threads in BACKGROUND_DSQ never get a
  > chance when foreground is heavy. I need to NOT use SCX_DSQ_GLOBAL and
  > instead use a FOREGROUND_DSQ that I drain with priority over background."
  >
  > "The key insight: if foreground gets the idle fast path (SCX_DSQ_LOCAL)
  > in select_cpu, the only time it goes through enqueue -> custom DSQ is
  > when no idle CPU exists — which is exactly the contention case where we
  > want to intervene anyway."
- Result: **-67.8% P99.9** (3765us -> 1213us), **-77% P99.99** (8153us -> 1878us)

**Starvation issue discovered during v7 development:**
> "'runnable task stall' — a background thread (rocksdb:low) couldn't run
> for 35 seconds. The issue: with heavy foreground traffic and preemption,
> background threads can be perpetually starved."
>
> Solution: bg_start_ns per-CPU map with 2ms minimum running time before
> allowing preemption. This bounds the starvation while still allowing
> aggressive foreground prioritization.

### 1.4 Final Results

**RocksDB v6 (readrandom, low contention):**

| Metric | CFS | rocksdb_aware v6 | Change |
|---|---|---|---|
| P50 | 22.38 us | 22.35 us | 0% |
| P99.9 | 168.73 us | 168.65 us | **0% (no regression)** |
| Max | 13,617 us | 12,632 us | -7.2% |
| Throughput | 646K ops/s | 649K ops/s | +0.5% |

**RocksDB v7 (readrandomwriterandom, high contention):**

| Metric | CFS | rocksdb_aware v7 | Change |
|---|---|---|---|
| P50 | 89.1 us | 106.7 us | +20% |
| P99 | 235.4 us | 476.4 us | +102% |
| **P99.9** | **3765 us** | **1213 us** | **-67.8%** |
| **P99.99** | **8153 us** | **1878 us** | **-77.0%** |
| Throughput | 149.8K ops/s | 144.4K ops/s | -3.6% |

---

## 2. Redis

### 2.1 Initial Prompt and Context

**User prompt:**
The LLM was asked to implement a Redis-aware BPF scheduler following the pattern
established by db_sim (79x max latency) and RocksDB (67.8% P99.9 reduction).

**Key context provided:**
- Redis source code at `workloads/redis/redis-src/`
- Relevant source files: `bio.c` (background I/O), `iothread.c` (I/O threads)
- Clear thread hierarchy visible in the code

### 2.2 LLM Thread Analysis

**Source code analyzed:** Redis source tree (`src/bio.c`, `src/iothread.c`, `src/server.c`)

**Thread inventory discovered:**

| Thread Name | Source Location | Role | Classification |
|---|---|---|---|
| `bio_close_file` | `src/bio.c` | Deferred file close | Background |
| `bio_aof` | `src/bio.c` | AOF fsync | Background |
| `bio_lazy_free` | `src/bio.c` | Lazy memory free | Background |
| `redis-rdb-*` | forked child (BGSAVE) | RDB snapshot persistence | Background |
| `redis-aof-*` | forked child (BGREWRITEAOF) | AOF rewrite | Background |
| main event loop | `src/server.c` | Client request handling | **Foreground** |
| `io_thd_*` | `src/iothread.c` | I/O thread workers | **Foreground** |

**LLM's key reasoning:**
1. Redis has a two-tier architecture: latency-critical event loop + I/O threads
   vs. background persistence threads
2. With `io-threads 4`, Redis has natural parallelism the kernel doesn't understand
3. Background threads (`bio_*`) are created via `pthread_create` with explicit naming
   via `pthread_setname_np` in `bio.c`
4. Persistence children (`redis-rdb-*`, `redis-aof-*`) are forked processes that
   inherit the Redis naming convention
5. The event loop and I/O threads are the latency-critical path

**Classification code generated:**
```c
static bool is_redis_background(struct task_struct *p)
{
    char comm[16];
    if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
        return false;

    /* bio_close_file, bio_aof, bio_lazy_free — match "bio_" prefix */
    if (comm[0] == 'b' && comm[1] == 'i' && comm[2] == 'o' && comm[3] == '_')
        return true;

    /* redis-rdb-bgsave — match "redis-r" prefix */
    if (comm[0] == 'r' && comm[1] == 'e' && comm[2] == 'd' &&
        comm[3] == 'i' && comm[4] == 's' && comm[5] == '-' && comm[6] == 'r')
        return true;

    /* redis-aof-rewrite — match "redis-a" prefix */
    if (comm[0] == 'r' && comm[1] == 'e' && comm[2] == 'd' &&
        comm[3] == 'i' && comm[4] == 's' && comm[5] == '-' && comm[6] == 'a')
        return true;

    return false;
}
```

### 2.3 Design Decisions

**Scheduler design:** Asymmetric dual-DSQ with selective preemption (Regime 2),
directly applying the principles discovered during RocksDB v6/v7 development.

```
FOREGROUND_DSQ (0x200): 5ms slice, high priority
BACKGROUND_DSQ (0x201): 20ms slice, low priority

Mechanisms:
- Idle CPU fast path: all threads -> SCX_DSQ_LOCAL (zero overhead)
- Selective preemption: foreground kicks background after 2ms minimum runtime
- Priority dispatch: always drain FOREGROUND_DSQ first
- bg_running + bg_start_ns per-CPU maps for background thread tracking
```

**Key design decisions:**
1. Applied asymmetric pattern directly — deprioritize identified background threads
2. 20ms vs 5ms slices — balance throughput and latency responsiveness
3. 2ms preemption minimum — prevent thrashing while maintaining responsiveness
4. Three-way prefix matching (`bio_`, `redis-r`, `redis-a`) covers all background threads
5. No task local storage needed (fewer concurrent threads than Nginx scenario)

### 2.4 Contention Model

**Setup:** 16 CPUs + 12 stress-ng CPU workers for oversubscription

**Contention sources:**
- Internal: `bio_*` threads competing with event loop during persistence operations
- Internal: forked `redis-rdb-*` / `redis-aof-*` children during BGSAVE/BGREWRITEAOF
- External: stress-ng CPU workers simulating co-located background work

**Benchmark:** Continuous BGSAVE (every 0.5s) + BGREWRITEAOF during benchmark.
50 benchmark clients, 500K requests per run, 256B values, AOF enabled.

### 2.5 Results

**GET Operations:**

| Metric | CFS | redis_aware | Change |
|---|---|---|---|
| RPS | 74,226 | 85,418 | **+15.1%** |
| Avg | 0.414 ms | 0.342 ms | -17.4% |
| P50 | 0.311 ms | 0.321 ms | +3.2% |
| P95 | 0.897 ms | 0.431 ms | **-51.9%** |
| **P99** | **2.785 ms** | **0.673 ms** | **-75.8%** |
| Max | 9.684 ms | 9.393 ms | -3.0% |

**SET Operations:**

| Metric | CFS | redis_aware | Change |
|---|---|---|---|
| RPS | 70,598 | 84,852 | **+20.2%** |
| Avg | 0.469 ms | 0.383 ms | -18.3% |
| P50 | 0.321 ms | 0.332 ms | +3.4% |
| P95 | 1.111 ms | 0.607 ms | **-45.4%** |
| **P99** | **2.959 ms** | **0.833 ms** | **-71.9%** |

**Key findings:**
- Throughput *improved* 15-20% (unlike RocksDB where it slightly decreased) —
  event loop runs with less interference, improving both latency and throughput
- P50 slightly regressed (+3%) — expected BPF overhead, acceptable
- The asymmetric design principle generalized directly from RocksDB to Redis

---

## 3. Nginx

### 3.1 Initial Prompt and Context

**User prompt (planning phase):**
> "Implement the following plan: Nginx-Aware BPF Scheduler. Apply the LLM-driven
> application-aware scheduling approach to Nginx."

**Key context provided in the plan:**
- Nginx uses a multi-process model: master + N worker processes
- All nginx processes have `comm = "nginx"` (unlike Redis with distinct thread names)
- The scheduling opportunity is about prioritizing nginx workers over co-located
  background CPU work (stress-ng, log rotation, etc.)
- Template: `workloads/redis/redis_aware.bpf.c` + `redis_bench_compare.sh`

### 3.2 LLM Thread Analysis

**Source code analyzed:** Nginx source tree (`workloads/schedcp_legacy/nginx/nginx/`)

**Process inventory:**

| Process Name | Role | Classification |
|---|---|---|
| `nginx` (master) | Process manager | Foreground (idle most of the time) |
| `nginx` (workers) | HTTP request handling via epoll | **Foreground** |
| `stress-ng-*` | External CPU hog (simulating batch jobs) | **Background (CPU hog)** |
| `wrk` | Load generator | Normal (must not be deprioritized!) |
| System daemons | Various | Normal |

**LLM's key reasoning:**
1. **Process-level vs thread-level:** Nginx uses `fork()` (multi-process) not
   `pthread_create()` (multi-thread). The `task_struct->comm` classification works
   identically for both — the kernel sees processes and threads uniformly.
2. **External contention model:** Unlike Redis/RocksDB where background threads are
   *internal* to the application, Nginx's scheduling contention comes from
   *external* CPU-bound processes. This is a fundamentally different contention model.
3. **Classification inversion:** Cannot use "nginx = foreground, everything else =
   background" because that would deprioritize the load generator (wrk2) and system
   daemons. Must specifically identify the CPU hogs.

**Classification code generated:**
```c
static bool is_nginx_worker(struct task_struct *p)
{
    char comm[16];
    if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
        return false;
    /* Match "nginx" */
    return (comm[0] == 'n' && comm[1] == 'g' && comm[2] == 'i' &&
            comm[3] == 'n' && comm[4] == 'x');
}

static bool is_cpu_hog(struct task_struct *p)
{
    char comm[16];
    if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
        return false;
    /* Match "stress-ng" prefix */
    if (comm[0] == 's' && comm[1] == 't' && comm[2] == 'r' &&
        comm[3] == 'e' && comm[4] == 's' && comm[5] == 's' &&
        comm[6] == '-' && comm[7] == 'n' && comm[8] == 'g')
        return true;
    return false;
}
```

### 3.3 Design Iterations and Reasoning

**v1: Dual DSQ (all non-nginx = background)**
- Design: `FOREGROUND_DSQ` (nginx) + `BACKGROUND_DSQ` (everything else)
- Result: **P50 = 9-12 seconds, P99 = 16-18 seconds** (catastrophic)
- LLM diagnosis: "BACKGROUND_DSQ starvation — the wrk2 load generator and
  system daemons are incorrectly classified as background. wrk2 can't generate
  requests fast enough, creating a feedback loop. This confirms the asymmetric
  design principle: only deprioritize threads you specifically identify as
  CPU hogs."

**v2: Asymmetric (only stress-ng deprioritized)**
- Design: stress-ng -> `BACKGROUND_DSQ`, everything else -> `SCX_DSQ_GLOBAL`
- Result: P50 = 10.6ms, **P99 = 32.7ms** (good tail, bad median)
- LLM diagnosis: "`bpf_probe_read_kernel_str` is called 3 times per scheduling
  event (enqueue, running, stopping) for every process on the system. With ~50
  processes scheduling thousands of times per second, this adds ~4ms to P50."

**v3: + BPF task local storage + nr_cpus limit (FINAL)**
- Design: v2 + `BPF_MAP_TYPE_TASK_STORAGE` caches classification per-task +
  CPU scan limited to `scx_bpf_nr_cpu_ids()` instead of hardcoded 256
- Result: **P50 = 6.7ms, P99 = 32.6ms, P99.9 = 36.4ms**
- LLM reasoning: "Task local storage caches the classification result per-task.
  comm is read once per task lifetime, and subsequent scheduling events use a
  single map lookup. This reduced P50 from 10.6ms to 6.7ms (37% improvement)
  without affecting tail latency."

**v4: SCX_DSQ_LOCAL_ON bypass (attempt to fix P50)**
- Design: Dispatch non-hog tasks directly to `SCX_DSQ_LOCAL_ON | cpu` in
  select_cpu, bypassing enqueue + GLOBAL queue entirely
- Result: **P50 = 38ms-2s, P99 = 1.3-6s** (catastrophic)
- LLM diagnosis: "SCX_DSQ_LOCAL_ON causes head-of-line blocking. When a task is
  pinned to a busy CPU's local queue, it waits behind whatever is running on
  that specific CPU rather than being load-balanced across all CPUs. This is
  especially bad under oversubscription."

**Key insight (P50 tradeoff):**
> "The remaining P50 gap (6.7ms vs CFS 1.5ms) is the inherent cost of sched-ext
> BPF dispatch. Every scheduling event goes through BPF select_cpu -> enqueue
> even when just routing to SCX_DSQ_GLOBAL. CFS has zero BPF overhead at P50
> but loses badly at the tail. The tradeoff is clear: 5ms higher P50 buys
> 160ms+ lower P99 and eliminates multi-hundred-millisecond tail spikes."

### 3.4 Final Results

**Nginx v3 (averaged across 3 runs):**

| Metric | CFS (avg +/- range) | nginx_aware v3 (avg +/- range) | Change |
|---|---|---|---|
| RPS | 49,894 (49,694-49,902) | 49,785 (49,642-49,870) | -0.2% |
| P50 | 1.54ms (1.50-1.58) | 6.57ms (6.51-6.68) | +4.3x |
| **P99** | **190.98ms (67.2-346.1)** | **32.33ms (30.8-32.6)** | **-83%** |
| **P99.9** | **276.48ms (106.3-454.9)** | **36.37ms (36.3-36.4)** | **-87%** |
| **Max** | **347.39ms (161.8-481.5)** | **38.56ms (36.4-40.6)** | **-89%** |

**Critical observation — consistency:**
- CFS P99 ranged from 67ms to 346ms across runs (**5x variance**)
- nginx_aware P99 ranged from 31ms to 33ms (**1.06x variance**)
- The scheduler eliminates CFS's unpredictable tail behavior

### 3.5 Nginx-Specific Insights

1. **External contention model:** Unlike Redis/RocksDB where background threads are
   internal, Nginx contention comes from external processes. The LLM must analyze
   both the application *and* the deployment environment.

2. **Classification inversion trap (v1 failure):** The naive "app = foreground,
   everything else = background" classification starved the load generator and
   system daemons. Must specifically identify CPU hogs, not blanket-deprioritize
   everything else.

3. **Task local storage is essential at scale:** With 50+ processes, per-event
   `bpf_probe_read_kernel_str` adds significant overhead. Caching via
   `BPF_MAP_TYPE_TASK_STORAGE` was the key optimization (37% P50 improvement).

4. **SCX_DSQ_LOCAL_ON is a trap:** Bypassing GLOBAL queue eliminates contention
   but also eliminates load balancing, causing head-of-line blocking under
   oversubscription. Never pin tasks to specific CPUs when CPUs are oversubscribed.

---

## 4. Cross-Workload Design Principles

Principles discovered through iterative development across all four workloads:

### Principle 1: Asymmetric Scheduling
> Only intervene in scheduling of threads you want to deprioritize. Let
> high-priority threads use the default fast path.

- Discovered: RocksDB v6 (after v1-v5 failures)
- Validated: Redis, Nginx v2+
- Violated: Nginx v1 (starved wrk2), RocksDB v1-v4 (foreground DSQ overhead)

### Principle 2: Idle-CPU Fast Path
> Use SCX_DSQ_LOCAL in select_cpu whenever an idle CPU is found. This bypasses
> enqueue/dispatch entirely.

- Discovered: RocksDB v6
- Validated: All workloads
- Critical for: Nginx (reduces per-event overhead)

### Principle 3: Selective Preemption for Tail
> When foreground threads wake with no idle CPU, actively preempt background
> threads via SCX_KICK_PREEMPT + bg_running per-CPU tracking.

- Discovered: RocksDB v7
- Validated: Redis, Nginx v3
- Tradeoff: Adds P50 overhead but dramatically reduces P99.9

### Principle 4: Classification Caching
> Cache per-task classification in BPF task local storage to avoid repeated
> bpf_probe_read_kernel_str calls.

- Discovered: Nginx v3 (37% P50 improvement)
- Applicable: Any workload with many concurrent processes

### Principle 5: Starvation Prevention
> Background threads must have a minimum guaranteed runtime (2ms) before
> preemption is allowed.

- Discovered: RocksDB v7 (runnable task stall after 35s)
- Mechanism: bg_start_ns per-CPU map, check elapsed time before SCX_KICK_PREEMPT

### Principle 6: Contention Model Matters
> The contention model (internal threads vs external processes) determines
> the policy regime. Internal contention uses the app's own thread names
> for classification. External contention must identify the CPU hogs specifically.

- Discovered: Nginx v1 failure vs v2 success
- Internal contention: RocksDB, Redis (classify app's own background threads)
- External contention: Nginx (classify co-located CPU hogs)
