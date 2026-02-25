# LLM Analysis Transcripts: Application-Aware Scheduler Synthesis

This document records the **exact prompts** given to the LLM (Claude Code) for each
workload, what the LLM produced, and how the design iterated. The goal is
reproducibility: given these prompts and an application, another LLM session should
produce a comparable scheduler.

---

## How the Process Actually Works

After building the first proof-of-concept (db_sim), we developed three real-world
schedulers: RocksDB, Redis, and Nginx. The process for each was different, and it is
important to be honest about what the LLM did autonomously vs. what the human provided.

### RocksDB: LLM Did the Thread Discovery

For RocksDB, the human gave a single open-ended prompt:

> "Can you use rocksdb or redis and ycsb benchmark to verify? you can clone from
> github. Pick rocksdb or redis, one is enough"

The LLM autonomously:
1. Chose RocksDB over Redis
2. Cloned the RocksDB repository
3. Read the source code (`env/env_posix.cc`, thread pool implementation)
4. Discovered the `"rocksdb:"` thread naming convention
5. Wrote the first BPF scheduler
6. Iterated through v1-v6 to find the asymmetric design

### Redis and Nginx: Human Provided the Thread Classification

For Redis and Nginx, the human had already analyzed the source code (likely with
LLM assistance in earlier, unrecorded sessions) and wrote **detailed implementation
plans** that included the thread classification upfront. The LLM's job was to
implement the plan, not discover the threads.

This distinction matters for the paper: the RocksDB case demonstrates end-to-end
LLM-driven discovery, while Redis and Nginx demonstrate the LLM executing a
human-provided specification with autonomous iteration when things go wrong.

---

## 1. RocksDB

### 1.1 Thread Discovery: The Actual Prompt

The RocksDB thread discovery happened in a single conversation session. After the
LLM successfully built the db_sim proof-of-concept (with synthetic `"query"` and
`"compact"` threads), the human gave this prompt:

```
Can you use rocksdb or redis and ycsb benchmark to verify? you can clone from
github. Pick rocksdb or redis, one is enough
```

That's it. From this single sentence, the LLM:

1. **Chose RocksDB** — reasoning that it has clear foreground (reader) vs. background
   (compaction) thread roles, matching the db_sim pattern
2. **Cloned and built RocksDB** from GitHub
3. **Read source code** to find thread naming:
   - `env/env_posix.cc` — thread pool implementation
   - `util/threadpool_imp.cc` — `pthread_setname_np()` calls
   - `tools/db_bench_tool.cc` — benchmark tool

4. **Discovered the naming convention:**
   ```
   Thread pool priority LOW    → thread name "rocksdb:low"
   Thread pool priority HIGH   → thread name "rocksdb:high"
   Thread pool priority BOTTOM → thread name "rocksdb:bot"
   ```
   All background threads share the 8-byte prefix `"rocksdb:"`.
   Foreground threads (db_bench readers/writers) do not have this prefix.

5. **Wrote `rocksdb_aware.bpf.c` v1** and ran A/B benchmarks
6. **Iterated through v1-v6** autonomously when results showed P99.9 regression,
   eventually discovering the asymmetric design principle

The human then gave a follow-up prompt to push for better P99.9:

```
Help me further improve P99.9
```

And later, after the context ran out and was resumed:

```
Can you further optimize the P99 and P999 latency on rocksdb? Introducing more
optimizing scheduling technique or building more suitable workloads? I observed
we only work in max latency, which is not enough for a paper....
```

This led to the v7 implementation plan (shown below), where the human synthesized
the lessons from v1-v6 into a structured plan for v7.

### 1.2 Phase 2: The Exact Implementation Prompt

This is the complete prompt given to the LLM to build the RocksDB v7 scheduler
(the earlier v1-v6 iterations happened in a previous session):

```
Implement the following plan:

# Plan: Improve RocksDB P99/P99.9 Latency for Paper-Worthy Results

## Context

Current RocksDB results only show max latency improvements (60%), not P99/P99.9.
Root causes:
1. Reads are CPU-bound block cache hits — no sleep/wake scheduling intervention points
2. Insufficient CPU oversubscription (8+8=16 threads on 16 CPUs)
3. `readwhilewriting` has only 1 writer — limited background pressure
4. v6 scheduler's "hands-off for foreground" avoids regression but can't actively
   improve P99.9

For a paper, we need measurable P99.9 improvements under realistic contention.

## Two-Track Approach

### Track A: Workload Design (create real scheduling contention)

Try workload configs in order. For each, run CFS baseline first to verify contention
exists.

**A1. readrandomwriterandom + tiny cache + 4x oversubscription** (most promising)

    --benchmarks=readrandomwriterandom --threads=32
    --max_background_compactions=32 --max_background_flushes=4
    --cache_size=1048576 (1MB) --value_size=4096
    --level0_file_num_compaction_trigger=4 --duration=30
    --statistics=1 --histogram=1

68 threads on 16 CPUs. Tiny cache forces cache misses → I/O waits → sleep/wake
points where scheduler can intervene.

**A2. updaterandom (write-heavy)** — if A1 doesn't create enough stress
**A3. readwhilewriting with 32+32 threads** — safest fallback with proven mode

### Track B: Scheduler Enhancement (v7 — targeted background preemption)

Key insight: v6 keeps foreground on SCX_DSQ_GLOBAL (zero overhead) but does nothing
to actively help. v7 adds **selective preemption** — when a foreground thread needs
CPU and none is idle, kick a CPU running a background thread.

**v7 design:**
1. `bg_running` BPF array map: tracks which CPUs run `rocksdb:*` threads
2. `running` callback: updates `bg_running[cpu]` when task starts
3. `select_cpu`: if no idle CPU and task is foreground, scan `bg_running` for a
   background CPU and `scx_bpf_kick_cpu(cpu, SCX_KICK_PREEMPT)`
4. Foreground still goes to `SCX_DSQ_GLOBAL` (preserves v6 zero-overhead principle)
5. Kick cost only applies when no idle CPU → targets exactly the tail cases

This differs from failed v2: v2 put foreground in custom DSQ (overhead on ALL
dispatches). v7 keeps foreground in SCX_DSQ_GLOBAL and only kicks in the tail cases.

**Fallback variants if v7 alone isn't enough:**
- `SCX_ENQ_PREEMPT` flag on foreground enqueue (simpler)
- Adaptive background slices: 2ms when foreground waiting, 20ms otherwise

## Implementation Steps

1. **Workload A1 CFS baseline** — populate DB, run readrandomwriterandom, check if
   P99.9 is elevated
2. **Workload A1 with v6** — confirm v6 baseline
3. **Implement v7** — update `workloads/rocksdb/rocksdb_aware.bpf.c` with bg_running
   map + selective preemption
4. **Compile + verify v7** — BPF verifier must pass, load test 10s
5. **Test v7 on A1** — compare P99.9 vs CFS
6. If A1 doesn't show contention, try A2/A3
7. If v7 helps, run 3x for confidence
8. Update `document/IMPLEMENTATION_PLAN.md` with results

## Files to Modify

| File | Action |
|---|---|
| `workloads/rocksdb/rocksdb_aware.bpf.c` | Upgrade to v7 with preemption |
| `mcp/new_sched/rocksdb_aware.bpf.o` | Recompile |
| `document/IMPLEMENTATION_PLAN.md` | Update with new results |

## Verification

1. v7 scheduler compiles (clang BPF target, no verifier errors)
2. Load test: run 10s under load, no dmesg errors
3. A/B test on stress workload: CFS vs v7, compare P50/P99/P99.9/P99.99/Max
4. Success criteria: P99.9 improvement ≥20% with no P50 regression >5%
```

### 1.3 What the LLM Produced

From this prompt, the LLM:

1. **Wrote `rocksdb_aware.bpf.c` v7** — dual custom DSQs (`FOREGROUND_DSQ` + `BACKGROUND_DSQ`), `bg_running`/`bg_start_ns` per-CPU maps, selective preemption in `select_cpu`, idle CPU fast path
2. **Compiled and verified** — passed BPF verifier
3. **Ran benchmarks** — discovered the starvation bug (background thread couldn't run for 35s), added `BG_MIN_RUN_NS` (2ms minimum) guard
4. **Iterated** — the final v7 design uses `FOREGROUND_DSQ` (not `SCX_DSQ_GLOBAL`) because the LLM discovered that the framework drains GLOBAL before calling `dispatch()`, which would starve background threads

### 1.4 Design Iterations (v1 through v7)

The earlier iterations (v1-v6) happened in a prior session where the prompt was more
exploratory: "create an application-aware scheduler for RocksDB db_bench". The LLM
iterated through 6 failed designs before finding the asymmetric principle.

See `document/IMPLEMENTATION_PLAN.md` Section 5.2.3 for the full iteration table
with P99.9 numbers. Summary:

- **v1-v4**: All used custom foreground DSQs → +373% to +474% P99.9 regression
  on the `readrandom` workload (CFS baseline P99.9 = 169us)
- **v5**: Kernel crash (can't dispatch to SCX_DSQ_LOCAL on non-idle CPU)
- **v6**: Asymmetric breakthrough — FG→SCX_DSQ_GLOBAL, BG→custom DSQ → 0% regression
- **v7**: Different workload (`readrandomwriterandom`, much higher contention) —
  dual custom DSQ + selective preemption → -67.8% P99.9

**Important:** v1-v6 and v7 were tested on **different workloads** with different
CFS baselines. v1-v6 used `readrandom` (CFS P99.9 = 169us, low contention). v7 used
`readrandomwriterandom` with 1MB cache (CFS P99.9 = 3765us, high contention). The
numbers are not directly comparable across workloads.

### 1.5 Results

**RocksDB v6 (readrandom, low contention):**

| Metric | CFS | rocksdb_aware v6 | Change |
|---|---|---|---|
| P50 | 22.38 us | 22.35 us | 0% |
| P99.9 | 168.73 us | 168.65 us | **0% (no regression)** |
| Max | 13,617 us | 12,632 us | -7.2% |
| Throughput | 646K ops/s | 649K ops/s | +0.5% |

**RocksDB v7 (readrandomwriterandom, high contention — different workload):**

v7 trades P50 and P99 for dramatic P99.9/P99.99 improvement. Under this stress
workload, CFS has very high tail latency (P99.9 = 3.7ms) because compaction threads
(32 `rocksdb:*` threads) compete with reader threads (32 threads) on 16 CPUs. v7's
selective preemption targets exactly these tail cases.

| Metric | CFS | rocksdb_aware v7 | Change |
|---|---|---|---|
| P50 | 89.1 us | 106.7 us | +20% |
| P99 | 235.4 us | 476.4 us | +102% |
| **P99.9** | **3765 us** | **1213 us** | **-67.8%** |
| **P99.99** | **8153 us** | **1878 us** | **-77.0%** |
| Throughput | 149.8K ops/s | 144.4K ops/s | -3.6% |

The P99 regression (+102%) is a known tradeoff: v7 uses dual custom DSQs (not
SCX_DSQ_GLOBAL), so all threads pay BPF dispatch overhead. This hurts P50/P99 but
allows `dispatch()` to enforce strict priority ordering, which dramatically cuts
P99.9/P99.99 — the metrics that matter for SLA compliance.

---

## 2. Redis

### 2.1 Thread Discovery: Done by Human Before the Prompt

Unlike RocksDB, the Redis thread classification was **provided by the human** in the
implementation plan. The human had already analyzed Redis source code (likely by
reading `src/bio.c`, `src/iothread.c`, and `src/server.c`, possibly with LLM
assistance in an earlier unrecorded session) and knew:

- `bio.c` creates 3 background threads via `pthread_create` + `pthread_setname_np`:
  `bio_close_file`, `bio_aof`, `bio_lazy_free`
- `BGSAVE` forks a child process with comm `redis-rdb-bgsave`
- `BGREWRITEAOF` forks a child process with comm `redis-aof-rewrite`
- Main event loop and I/O threads (`io_thd_*`) are latency-critical foreground

This classification was embedded directly into the implementation plan below.

### 2.2 The Exact Implementation Prompt

```
Implement the following plan:

# Plan: Redis-Aware BPF Scheduler via LLM-Driven Synthesis

## Context

We've demonstrated LLM-driven scheduler synthesis on db_sim (79x max latency) and
RocksDB (67.8% P99.9 reduction). Redis is the next target to strengthen the paper's
evaluation. Redis has a clear thread hierarchy: a latency-critical main event loop +
I/O threads vs. background persistence threads (bio_close_file, bio_aof,
bio_lazy_free).

The `workloads/redis/` directory already has Makefile, benchmark scripts, and a Redis
git submodule (not yet initialized). We need to build Redis, write the BPF scheduler,
create contention, and benchmark.

## Thread Classification

Redis thread names (from `pthread_setname_np` in `src/bio.c`):
- **Background (deprioritize):** `bio_close_file`, `bio_aof`, `bio_lazy_free`
- **Background (forked processes):** `redis-rdb-bgsave`, `redis-aof-rewrite`
  (child procs from fork)
- **Foreground (fast path):** everything else (main event loop, I/O threads
  `io_thd_*`)

Classification: match `comm` prefix `"bio_"` for bio threads, `"redis-rdb"` /
`"redis-aof"` for forked persistence children.

## Contention Strategy

Run Redis with `io-threads 4` + `appendonly yes`. Populate with data, then run heavy
GET/SET benchmark while triggering `BGSAVE` + `BGREWRITEAOF` — the forked child
processes + bio threads compete with the main event loop for CPU. The benchmark
clients themselves also create load.

## Implementation Steps

### 1. Build Redis (~2 min)
- `git submodule update --init workloads/redis/redis-src`
- `cd workloads/redis/redis-src && make -j$(nproc)`

### 2. Write `workloads/redis/redis_aware.bpf.c`
Following v7 dual-DSQ + selective preemption pattern:
- `FOREGROUND_DSQ` (0x200), `BACKGROUND_DSQ` (0x201)
- `is_redis_background()`: match `bio_*` prefix (4 bytes) OR `redis-rdb` /
  `redis-aof` prefix
- `select_cpu`: idle fast path → SCX_DSQ_LOCAL + preempt bg CPU if no idle
- `running`/`stopping`: bg_running per-CPU map
- `dispatch`: foreground first, then background

### 3. Compile + verify scheduler
- `make -f ../../mcp/new_sched/Makefile BPF_SRC=redis_aware.bpf.c \
       BPF_OBJ=redis_aware.bpf.o`
- Load test: `sudo loader redis_aware.bpf.o`, verify enabled, run 10s under load

### 4. Create `workloads/redis/redis_bench_compare.sh`
A/B comparison script:
- Start redis-server with: `--io-threads 4 --appendonly yes --save ""
  --protected-mode no`
- Populate: `redis-benchmark -t set -n 1000000 -d 256 -r 100000 -q`
- Background pressure loop: continuously issue `BGSAVE` + `BGREWRITEAOF`
  during benchmark
- Benchmark: `redis-benchmark -t get,set -c 32 -n 500000 -r 100000 -d 256 --csv`
- 3 runs CFS, 3 runs redis_aware
- Parse CSV for p50/p99/p99.9/throughput

### 5. Run experiments, collect results

### 6. Update documentation (IMPLEMENTATION_PLAN.md, CLAUDE.md)

## Files to Create/Modify

| File | Action |
|---|---|
| `workloads/redis/redis_aware.bpf.c` | **Create** — BPF scheduler |
| `workloads/redis/redis_bench_compare.sh` | **Create** — A/B benchmark |
| `document/IMPLEMENTATION_PLAN.md` | Update with Redis results |
| `CLAUDE.md` | Update results table |

## Verification

1. Scheduler compiles (clang BPF target)
2. Loads into kernel, `/sys/kernel/sched_ext/state` = enabled
3. Stable for 30s under load (no watchdog stall)
4. A/B test: CFS vs redis_aware during BGSAVE/BGREWRITEAOF
5. Target: P99 or P99.9 improvement during background persistence ops
```

### 2.3 What the LLM Produced

From this prompt, the LLM:

1. Built Redis from submodule
2. Wrote `redis_aware.bpf.c` with three-way prefix matching (`bio_*`, `redis-r*`, `redis-a*`)
3. Wrote `redis_bench_compare.sh` with automated A/B benchmarking
4. Compiled, verified, ran benchmarks — worked on the first iteration (no design failures), because the Redis prompt already incorporated all lessons from RocksDB v1-v7

### 2.4 Results

**GET Operations:**

| Metric | CFS | redis_aware | Change |
|---|---|---|---|
| RPS | 74,226 | 85,418 | **+15.1%** |
| P50 | 0.311 ms | 0.321 ms | +3.2% |
| P95 | 0.897 ms | 0.431 ms | **-51.9%** |
| **P99** | **2.785 ms** | **0.673 ms** | **-75.8%** |

**SET Operations:**

| Metric | CFS | redis_aware | Change |
|---|---|---|---|
| RPS | 70,598 | 84,852 | **+20.2%** |
| P50 | 0.321 ms | 0.332 ms | +3.4% |
| P95 | 1.111 ms | 0.607 ms | **-45.4%** |
| **P99** | **2.959 ms** | **0.833 ms** | **-71.9%** |

---

## 3. Nginx

### 3.1 Thread Discovery: Done by Human Before the Prompt

Like Redis, the Nginx thread/process analysis was **provided by the human** in the
implementation plan. The human already knew:

- Nginx uses `fork()` (multi-process), not `pthread_create()` (multi-thread)
- All nginx processes (master + workers) have `comm = "nginx"`
- Unlike Redis/RocksDB, Nginx has no internal background threads to deprioritize
- The scheduling opportunity is **external**: nginx workers vs. co-located CPU-bound processes

However, the human's initial classification was **wrong** — the plan said
"Non-nginx processes = background (default path)", which would deprioritize the wrk2
load generator. The LLM discovered this error during benchmarking and autonomously
fixed it (see v1→v2 iteration in Section 3.3).

### 3.2 The Exact Implementation Prompt

```
Implement the following plan:

# Plan: Nginx-Aware BPF Scheduler

## Context

Apply the LLM-driven application-aware scheduling approach to Nginx. Nginx uses a
multi-process model: a master process manages N worker processes that handle HTTP
requests via epoll. Under CPU oversubscription (background CPU load competing with
nginx workers), tail latency spikes because CFS treats nginx workers equally with
background CPU-bound processes.

**Key insight**: All nginx processes have `comm = "nginx"`. Unlike Redis (which has
distinct bio_*/redis-rdb*/redis-aof* background threads), Nginx's scheduling
opportunity is about **prioritizing nginx worker processes over co-located background
CPU work** (stress-ng, log rotation, etc.) under contention.

## Environment

- 16 CPUs, stress-ng available, no wrk/wrk2/nginx installed
- Nginx source at `workloads/schedcp_legacy/nginx/nginx/` (submodule, needs init)
- Legacy Makefile/config at `workloads/schedcp_legacy/nginx/`
- Template: `workloads/redis/redis_aware.bpf.c` + `workloads/redis/redis_bench_compare.sh`

## Files to Create

All in `workloads/nginx/`:

### 1. `nginx_aware.bpf.c`
Based on `redis_aware.bpf.c`:
- `is_nginx_worker()`: match `comm[0..4] == "nginx"` (all nginx processes =
  foreground)
- Non-nginx processes = background (default path)
- Two DSQs: `FOREGROUND_DSQ` (nginx), `BACKGROUND_DSQ` (everything else under
  sched-ext)
- Idle CPU fast path → `SCX_DSQ_LOCAL` (zero overhead common case)
- Selective preemption: nginx can kick background threads that ran >= 2ms
- Per-CPU `bg_running`/`bg_start_ns` maps
- 5ms foreground / 20ms background slices

### 2. `nginx_bench_compare.sh`
Self-contained A/B benchmark script (following redis_bench_compare.sh):
- **Setup**: init nginx submodule, build nginx with `--with-threads`, clone+build
  wrk2
- **Config**: `worker_processes 16`, port 8080, static file serving, access_log off
- **Background pressure**: `stress-ng --cpu 24 --cpu-method matrixprod`
  (24+16=40 threads on 16 CPUs)
- **Benchmark**: wrk2 at high request rate (e.g. 50k req/s), 8 threads,
  200 connections, 30s duration, `--latency`
- **Phase 1**: CFS baseline — 3 runs with stress-ng
- **Phase 2**: nginx_aware scheduler — 3 runs with stress-ng
- **Output**: parse wrk2 latency percentiles, report P50/P99/P99.9 comparison table

### 3. `nginx.conf`
Adapted from `workloads/schedcp_legacy/nginx/nginx.conf` with corrected paths.

## Build & Run

    cd workloads/nginx
    make -f ../../mcp/new_sched/Makefile BPF_SRC=nginx_aware.bpf.c \
         BPF_OBJ=nginx_aware.bpf.o nginx_aware.bpf.o
    sudo ./nginx_bench_compare.sh

## Verification

1. BPF scheduler compiles and passes kernel verification
2. Nginx serves HTTP 200 under both CFS and custom scheduler
3. wrk2 produces latency percentile data
4. Expect P99/P99.9 improvement under CPU oversubscription
```

### 3.3 What the LLM Produced — and How It Went Wrong

Unlike Redis (which worked first try), the Nginx prompt's initial design was **wrong**.
The prompt said "Non-nginx processes = background" — but this is the classification
inversion trap. The LLM faithfully implemented this, causing a catastrophic failure:

**v1 (from prompt as-is):** All non-nginx → `BACKGROUND_DSQ`
- Result: P50 = 9-12 **seconds** (catastrophic)
- The wrk2 load generator was starved in BACKGROUND_DSQ

The LLM then iterated autonomously through v2-v4 to fix this:

| Version | Change from Prompt | Result | LLM Diagnosis |
|---|---|---|---|
| v1 | Followed prompt exactly | P50=12s | wrk2 and system daemons starved in BACKGROUND_DSQ |
| v2 | Only stress-ng → BACKGROUND, everything else → SCX_DSQ_GLOBAL | P50=10.6ms, P99=32.7ms | `bpf_probe_read_kernel_str` called 3x per event for all processes |
| v3 | Added BPF task local storage + nr_cpus bound | **P50=6.7ms, P99=32.6ms** | Classification cached per-task; 37% P50 improvement |
| v4 | Tried SCX_DSQ_LOCAL_ON to fix P50 | P50=38ms-2s | Head-of-line blocking; reverted to v3 |

### 3.4 Results

**Nginx v3 (averaged across 3 runs):**

| Metric | CFS | nginx_aware v3 | Change |
|---|---|---|---|
| RPS | 49,894 | 49,785 | -0.2% |
| P50 | 1.54ms | 6.57ms | +4.3x |
| **P99** | **190.98ms** | **32.33ms** | **-83%** |
| **P99.9** | **276.48ms** | **36.37ms** | **-87%** |
| **Max** | **347.39ms** | **38.56ms** | **-89%** |

---

## 4. What You Actually Need to Reproduce This

### What Actually Happened vs. the Idealized Pipeline

Be honest: the process was **not** a clean "LLM reads source → generates scheduler"
pipeline for all three applications.

| Application | Thread Discovery | Scheduler Implementation |
|---|---|---|
| **RocksDB** | LLM did it autonomously from a one-line prompt | LLM iterated v1-v7 with human nudges ("improve P99.9") |
| **Redis** | Human provided classification in the plan | LLM implemented it — worked first try (lessons from RocksDB already baked in) |
| **Nginx** | Human provided classification in the plan (with a mistake) | LLM implemented it, discovered the mistake, iterated v1-v4 autonomously |

The RocksDB case is the strongest evidence for LLM-driven thread discovery. For Redis
and Nginx, the LLM's contribution was primarily in **implementation and iteration**,
not discovery.

### To Reproduce the End-to-End Process (RocksDB-Style)

Give the LLM access to the application source code and a minimal prompt:

```
I have a [application] workload that I want to optimize with a custom BPF
kernel scheduler. The application is at [path]. Can you:

1. Read the source code and identify thread/process naming conventions
2. Figure out which threads are latency-critical vs. background
3. Write a sched-ext BPF scheduler that prioritizes the critical threads
4. Benchmark it against CFS under CPU oversubscription
```

This is essentially what happened for RocksDB (the prompt was even simpler: "Can you
use rocksdb or redis and ycsb benchmark to verify?"). The LLM needs:
- Access to the source code (local filesystem or git clone)
- A BPF scheduler template to follow (e.g., `db_aware.bpf.c`)
- Ability to compile and load BPF programs (clang, sudo loader)
- Ability to run benchmarks and read results

### To Reproduce the Human-Guided Process (Redis/Nginx-Style)

If you've already analyzed the application and know the thread roles, give the LLM
a structured implementation plan (see the exact prompts in Sections 1.2, 2.2, 3.2).
This is faster and more reliable, but the LLM is acting as a code generator, not an
analyst.

### Either Way, Let the LLM Iterate

The LLM will likely need 1-3 iterations to handle:
- Classification mistakes (who is foreground vs. background)
- Performance overhead from BPF dispatch
- sched-ext API constraints (e.g., SCX_DSQ_LOCAL only on idle CPUs)
- Starvation of background threads under heavy foreground load

The key is that the LLM has access to benchmark results and can diagnose + fix
issues autonomously. The Nginx case shows this: the initial plan's classification
was wrong, but the LLM iterated through 4 versions to find the correct design.

---

## 5. Cross-Workload Design Principles

Principles discovered through iterative development across all workloads:

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

### Principle 3: Selective Preemption with Starvation Guard
> When foreground threads wake with no idle CPU, preempt background threads via
> SCX_KICK_PREEMPT — but only if they've run at least 2ms.

- Discovered: RocksDB v7 (starvation bug forced the 2ms guard)
- Validated: Redis, Nginx v3

### Principle 4: Classification Caching
> Cache per-task classification in BPF task local storage to avoid repeated
> bpf_probe_read_kernel_str calls.

- Discovered: Nginx v3 (37% P50 improvement)
- Applicable when: many concurrent processes, classifier called from multiple callbacks

### Principle 5: Contention Model Determines Policy
> Internal contention (app's own background threads) → classify by app thread names.
> External contention (co-located CPU hogs) → classify the hogs specifically,
> leave everything else on the default path.

- Discovered: Nginx v1 failure (blanket deprioritization starved load generator)
- Internal: RocksDB (`rocksdb:*`), Redis (`bio_*`, `redis-rdb*`, `redis-aof*`)
- External: Nginx (`stress-ng*`)

---

## Appendix: Conversation Transcript Locations

Full interactive transcripts are stored in:
- RocksDB development: `/home/ubuntu/.claude/projects/-home-ubuntu-schedcp/e98faf33-be8d-4966-9ded-957f2c16ce76.jsonl`
- Redis development: `/home/ubuntu/.claude/projects/-home-ubuntu-schedcp/da6419af-da14-41a5-bc58-2f8060dd361f.jsonl`
- Nginx development: `/home/ubuntu/.claude/projects/-home-ubuntu-schedcp/46c7c4d1-cfe9-44c5-9613-7487da0089a8.jsonl`
