# Implementation Details: From Thread Knowledge to Kernel Scheduling Policy

This document explains, with precise code references, how our framework translates LLM-extracted thread role knowledge into BPF kernel scheduling policy via the Linux sched-ext framework. We cover the full data-plane pipeline: thread identification in BPF, dispatch queue (DSQ) topology, scheduling callback structure, selective preemption, and the per-task classification caching optimization. All code references point to concrete schedulers built for three real-world applications.

**Source files:**
- `workloads/db_sim/db_aware.bpf.c` — synthetic database (simplest, dual-DSQ)
- `workloads/rocksdb/rocksdb_aware.bpf.c` — RocksDB (selective preemption)
- `workloads/redis/redis_aware.bpf.c` — Redis (multi-pattern matching, selective preemption)
- `workloads/nginx/nginx_aware.bpf.c` — Nginx (asymmetric design, task local storage caching)

---

## 1. The Core Problem: Bridging Semantic Knowledge to Kernel Space

The LLM's analysis produces a **thread classification table** — a mapping from thread name patterns to scheduling roles:

| Application | Background Pattern(s) | Foreground / Latency-Critical |
|---|---|---|
| db_sim | `compact*` | `query*` |
| RocksDB | `rocksdb:*` (compaction/flush threads) | everything else (db_bench reader threads) |
| Redis | `bio_*`, `redis-r*`, `redis-a*` | everything else (main event loop, I/O threads) |
| Nginx | `stress-ng*` (co-located CPU hog) | `nginx` workers (+ everything else) |

The question is: **how does a BPF program running inside the kernel scheduler translate these string patterns into differentiated scheduling behavior?** The answer involves five mechanisms working together.

---

## 2. Mechanism 1: Thread Identification via `task_struct->comm`

Every Linux thread has a 16-byte name stored in `task_struct->comm`. BPF programs can read this field, but the BPF verifier prohibits standard C library functions like `strcmp` or `strncmp`. We use **byte-by-byte comparison** against the patterns extracted by the LLM.

### 2.1 Simple Single-Pattern Matching (db_sim)

The simplest case: one prefix identifies the critical thread class.

```c
// db_aware.bpf.c:25-34
static bool is_query_task(struct task_struct *p)
{
    char comm[16];
    if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
        return false;
    return (comm[0] == 'q' && comm[1] == 'u' && comm[2] == 'e' &&
            comm[3] == 'r' && comm[4] == 'y');
}
```

`bpf_probe_read_kernel_str` safely copies the kernel-space `comm` string into a BPF stack buffer. The 5-byte prefix check `"query"` is sufficient because db_sim names its threads `query_0`, `query_1`, etc. Any thread not matching this pattern is treated as background (compaction).

### 2.2 Multi-Pattern Matching (Redis)

Redis spawns several distinct background thread types, each with a different naming convention discovered by the LLM reading `bio.c` and `server.c`:

```c
// redis_aware.bpf.c:51-76
static bool is_redis_background(struct task_struct *p)
{
    char comm[16];
    if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
        return false;

    /* bio_close_file, bio_aof, bio_lazy_free — match "bio_" prefix */
    if (comm[0] == 'b' && comm[1] == 'i' && comm[2] == 'o' &&
        comm[3] == '_')
        return true;

    /* redis-rdb-bgsave — match "redis-r" prefix */
    if (comm[0] == 'r' && comm[1] == 'e' && comm[2] == 'd' &&
        comm[3] == 'i' && comm[4] == 's' && comm[5] == '-' &&
        comm[6] == 'r')
        return true;

    /* redis-aof-rewrite — match "redis-a" prefix */
    if (comm[0] == 'r' && comm[1] == 'e' && comm[2] == 'd' &&
        comm[3] == 'i' && comm[4] == 's' && comm[5] == '-' &&
        comm[6] == 'a')
        return true;

    return false;
}
```

Three separate prefix checks capture all background thread variants. The `"redis-r"` and `"redis-a"` patterns share a 6-byte common prefix `"redis-"` but diverge at byte 6 — the LLM identified that `r` (rdb/bgsave) and `a` (aof/rewrite) sufficiently disambiguate them from foreground threads like the main event loop or I/O threads (which have comm `redis-server` or `io_thd_*`).

### 2.3 Distinguishing Application vs. External Threads (Nginx)

Nginx presents a different challenge: the contention comes from *external* CPU-bound processes (e.g., stress-ng) co-located on the same machine, not from internal application threads. The classifier needs a three-way distinction:

```c
// nginx_aware.bpf.c:34-38
#define TASK_UNKNOWN  0
#define TASK_NGINX    1
#define TASK_CPU_HOG  2
#define TASK_NORMAL   3
```

```c
// nginx_aware.bpf.c:92-101
if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) >= 0) {
    /* "nginx" */
    if (comm[0] == 'n' && comm[1] == 'g' && comm[2] == 'i' &&
        comm[3] == 'n' && comm[4] == 'x')
        result = TASK_NGINX;
    /* "stress-ng" prefix */
    else if (comm[0] == 's' && comm[1] == 't' && comm[2] == 'r' &&
             comm[3] == 'e' && comm[4] == 's' && comm[5] == 's' &&
             comm[6] == '-' && comm[7] == 'n' && comm[8] == 'g')
        result = TASK_CPU_HOG;
}
```

- `TASK_NGINX` — identified for preemption benefit (can kick CPU hogs)
- `TASK_CPU_HOG` — deprioritized into `BACKGROUND_DSQ`
- `TASK_NORMAL` — all other processes (wrk2 load generator, system daemons) — use the default fast path, never deprioritized

This three-way split is critical. In early iterations (v1), we mistakenly routed *all* non-nginx threads into `BACKGROUND_DSQ`, which starved the wrk2 load generator and caused P50 latency to spike from 1.5ms to 12 seconds.

---

## 3. Mechanism 2: Dispatch Queue (DSQ) Topology

The sched-ext framework provides several built-in queues and the ability to create custom ones. The choice of DSQ topology is the primary mechanism for expressing scheduling priority.

### 3.1 Built-in DSQs

| DSQ | Behavior |
|---|---|
| `SCX_DSQ_LOCAL` | Per-CPU local queue. Tasks dispatched here run immediately on that CPU. Fastest path — no global contention. |
| `SCX_DSQ_GLOBAL` | Framework-managed global FIFO. The framework drains this automatically *before* calling `ops.dispatch()`. |

### 3.2 Custom DSQs

Custom DSQs are created in `ops.init()` and drained explicitly in `ops.dispatch()`. This gives us full control over priority ordering.

**db_sim** uses two custom DSQs with strict priority ordering:

```c
// db_aware.bpf.c:19-20
#define QUERY_DSQ   0
#define COMPACT_DSQ 1
```

```c
// db_aware.bpf.c:68-77
s32 BPF_STRUCT_OPS_SLEEPABLE(db_aware_init)
{
    s32 ret;
    ret = scx_bpf_create_dsq(QUERY_DSQ, -1);
    if (ret)
        return ret;
    return scx_bpf_create_dsq(COMPACT_DSQ, -1);
}
```

**RocksDB and Redis** use `FOREGROUND_DSQ` + `BACKGROUND_DSQ`:

```c
// rocksdb_aware.bpf.c:29-30
#define FOREGROUND_DSQ  0x100
#define BACKGROUND_DSQ  0x101
```

**Nginx** uses only one custom DSQ — `BACKGROUND_DSQ` — because foreground threads go through `SCX_DSQ_GLOBAL` (the asymmetric design):

```c
// nginx_aware.bpf.c:27
#define BACKGROUND_DSQ  0x201
```

```c
// nginx_aware.bpf.c:198-202
s32 BPF_STRUCT_OPS_SLEEPABLE(nginx_aware_init)
{
    nr_cpus = scx_bpf_nr_cpu_ids();
    return scx_bpf_create_dsq(BACKGROUND_DSQ, -1);
}
```

### 3.3 Design Evolution: Why DSQ Topology Matters

We discovered through iteration that the DSQ topology choice directly impacts P50 vs. tail latency:

| Design | Foreground Path | Background Path | Effect |
|---|---|---|---|
| **Dual custom DSQ** (db_sim, rocksdb v7, redis) | `FOREGROUND_DSQ` → explicit drain in `dispatch()` | `BACKGROUND_DSQ` → drained second | Full priority control, but foreground pays BPF dispatch overhead on every scheduling event |
| **Asymmetric** (nginx v3, rocksdb v6) | `SCX_DSQ_GLOBAL` → framework fast path | `BACKGROUND_DSQ` → drained only when GLOBAL empty | Foreground avoids custom dispatch overhead; lower P50, same tail benefit |

The asymmetric design emerged as a key finding: routing foreground threads through the framework's native `SCX_DSQ_GLOBAL` avoids the BPF-to-kernel dispatch round-trip, reducing per-event overhead. The tradeoff is that `dispatch()` cannot prioritize foreground *over* global — but since foreground *is* global, this is moot.

---

## 4. Mechanism 3: The sched-ext Callback Pipeline

Each BPF scheduler registers a set of struct_ops callbacks that the kernel invokes at specific points in the scheduling lifecycle. The combination of these callbacks implements the full scheduling policy.

### 4.1 Callback Structure (all four schedulers)

```c
// rocksdb_aware.bpf.c:165-173  (representative)
SCX_OPS_DEFINE(rocksdb_aware_ops,
    .select_cpu  = (void *)rocksdb_aware_select_cpu,
    .enqueue     = (void *)rocksdb_aware_enqueue,
    .dispatch    = (void *)rocksdb_aware_dispatch,
    .running     = (void *)rocksdb_aware_running,
    .stopping    = (void *)rocksdb_aware_stopping,
    .init        = (void *)rocksdb_aware_init,
    .exit        = (void *)rocksdb_aware_exit,
    .name        = "rocksdb_aware");
```

### 4.2 `select_cpu`: Idle CPU Fast Path + Preemption Trigger

`select_cpu` is the first callback invoked when a task becomes runnable. It has two responsibilities:

**Responsibility 1: Idle CPU fast path.** If an idle CPU exists, dispatch the task directly to `SCX_DSQ_LOCAL` — bypassing the enqueue/dispatch pipeline entirely. This is the zero-overhead common case.

```c
// redis_aware.bpf.c:78-91
s32 BPF_STRUCT_OPS(redis_aware_select_cpu, struct task_struct *p,
                   s32 prev_cpu, u64 wake_flags)
{
    bool is_idle = false;
    s32 cpu;

    cpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);

    if (is_idle) {
        u64 slice = is_redis_background(p) ?
                    BACKGROUND_SLICE_NS : DEFAULT_SLICE_NS;
        scx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, 0);
        return cpu;
    }
    // ... preemption logic follows
}
```

`scx_bpf_select_cpu_dfl()` is the framework's default CPU selection — it tries the previous CPU first (cache locality), then scans for idle CPUs. When `is_idle == true`, we short-circuit the entire scheduling pipeline by inserting directly into `SCX_DSQ_LOCAL`.

Note the time-slice differentiation even on the fast path: background threads get `BACKGROUND_SLICE_NS` (20ms) so they yield less frequently, while foreground threads get `DEFAULT_SLICE_NS` (5ms) for better responsiveness.

**Responsibility 2: Selective preemption** (when no idle CPU exists). Covered in Section 5.

### 4.3 `enqueue`: Thread Classification → DSQ Routing

When the fast path in `select_cpu` doesn't fire (no idle CPU, task not dispatched locally), `enqueue` is called. This is where the classifier function routes threads to the appropriate DSQ.

**db_sim** — binary foreground/background split:

```c
// db_aware.bpf.c:51-58
void BPF_STRUCT_OPS(db_aware_enqueue, struct task_struct *p, u64 enq_flags)
{
    if (is_query_task(p)) {
        scx_bpf_dsq_insert(p, QUERY_DSQ, QUERY_SLICE_NS, enq_flags);
    } else {
        scx_bpf_dsq_insert(p, COMPACT_DSQ, COMPACT_SLICE_NS, enq_flags);
    }
}
```

**Nginx (asymmetric)** — only CPU hogs go to a custom DSQ; everything else stays on the framework fast path:

```c
// nginx_aware.bpf.c:159-169
void BPF_STRUCT_OPS(nginx_aware_enqueue, struct task_struct *p,
                    u64 enq_flags)
{
    if (classify_task(p) == TASK_CPU_HOG) {
        scx_bpf_dsq_insert(p, BACKGROUND_DSQ, BACKGROUND_SLICE_NS,
                            enq_flags);
    } else {
        scx_bpf_dsq_insert(p, SCX_DSQ_GLOBAL, DEFAULT_SLICE_NS,
                            enq_flags);
    }
}
```

The difference is significant: in the nginx design, foreground threads (nginx workers, wrk2, system daemons) go to `SCX_DSQ_GLOBAL` — the framework drains this queue automatically without calling `ops.dispatch()`, avoiding BPF dispatch overhead entirely for the latency-sensitive path.

### 4.4 `dispatch`: Priority-Ordered Queue Draining

`dispatch()` is called when a CPU needs work and `SCX_DSQ_LOCAL`/`SCX_DSQ_GLOBAL` are empty. It explicitly drains custom DSQs in priority order.

**db_sim** — strict priority, foreground first:

```c
// db_aware.bpf.c:60-66
void BPF_STRUCT_OPS(db_aware_dispatch, s32 cpu, struct task_struct *prev)
{
    /* Always drain query DSQ first for low latency */
    if (!scx_bpf_dsq_move_to_local(QUERY_DSQ)) {
        scx_bpf_dsq_move_to_local(COMPACT_DSQ);
    }
}
```

`scx_bpf_dsq_move_to_local()` atomically moves the first task from the named DSQ to the calling CPU's local queue. The return value indicates whether a task was found — enabling the priority cascade.

**Nginx (asymmetric)** — only drains background, since foreground is already in GLOBAL:

```c
// nginx_aware.bpf.c:171-175
void BPF_STRUCT_OPS(nginx_aware_dispatch, s32 cpu, struct task_struct *prev)
{
    /* Background DSQ drained only when GLOBAL is empty */
    scx_bpf_dsq_move_to_local(BACKGROUND_DSQ);
}
```

This is the key to the asymmetric design: `dispatch()` is only called *after* the framework has already drained `SCX_DSQ_GLOBAL`. So background threads from `BACKGROUND_DSQ` only run when no foreground work is pending — achieving strict priority without touching the foreground path.

---

## 5. Mechanism 4: Selective Preemption

Under CPU oversubscription (more runnable threads than CPUs), a high-priority thread may wake up with no idle CPU available. Without intervention, it would wait in a DSQ until some thread's timeslice expires — adding tens of milliseconds of latency. **Selective preemption** solves this by forcibly rescheduling a CPU running a low-priority thread.

### 5.1 Per-CPU Background Thread Tracking

Two BPF maps track which CPUs are currently running background threads and when they started:

```c
// rocksdb_aware.bpf.c:40-55
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, MAX_CPUS);
    __type(key, u32);
    __type(value, u8);
} bg_running SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, MAX_CPUS);
    __type(key, u32);
    __type(value, u64);
} bg_start_ns SEC(".maps");
```

These maps are updated by two callbacks:

**`running`** — called when a task starts executing on a CPU:

```c
// rocksdb_aware.bpf.c:129-138
void BPF_STRUCT_OPS(rocksdb_aware_running, struct task_struct *p)
{
    if (is_rocksdb_background(p)) {
        u32 key = bpf_get_smp_processor_id();
        u8 val = 1;
        u64 now = bpf_ktime_get_ns();
        bpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
        bpf_map_update_elem(&bg_start_ns, &key, &now, BPF_ANY);
    }
}
```

**`stopping`** — called when a task is descheduled:

```c
// rocksdb_aware.bpf.c:140-148
void BPF_STRUCT_OPS(rocksdb_aware_stopping, struct task_struct *p,
                    bool runnable)
{
    if (is_rocksdb_background(p)) {
        u32 key = bpf_get_smp_processor_id();
        u8 val = 0;
        bpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
    }
}
```

Together, these maintain a real-time bitmap of which CPUs are running deprioritized threads.

### 5.2 Preemption Trigger in `select_cpu`

When a foreground thread wakes and no idle CPU is available, we scan the `bg_running` bitmap:

```c
// rocksdb_aware.bpf.c:88-104
if (!is_rocksdb_background(p)) {
    u64 now = bpf_ktime_get_ns();
    u32 i;

    bpf_for(i, 0, MAX_CPUS) {
        u32 key = i;
        u8 *running = bpf_map_lookup_elem(&bg_running, &key);
        if (!running || !*running)
            continue;

        u64 *start = bpf_map_lookup_elem(&bg_start_ns, &key);
        if (start && (now - *start) >= BG_MIN_RUN_NS) {
            scx_bpf_kick_cpu(i, SCX_KICK_PREEMPT);
            break;
        }
    }
}
```

The logic:
1. Iterate over CPUs (using `bpf_for`, the BPF-safe bounded loop)
2. Check `bg_running[cpu]` — skip CPUs not running background threads
3. Check `bg_start_ns[cpu]` — only preempt if the background thread has run at least `BG_MIN_RUN_NS` (2ms). This prevents thrashing: a background thread that just started should not be immediately preempted, as the context switch overhead would outweigh the benefit.
4. `scx_bpf_kick_cpu(i, SCX_KICK_PREEMPT)` sends an IPI (inter-processor interrupt) to force a reschedule on CPU `i`. The background thread is moved back to `BACKGROUND_DSQ`, and the foreground thread gets to run.
5. `break` after the first kick — we only need one CPU freed.

### 5.3 Nginx Optimization: Bounded CPU Scan

The default `bpf_for(i, 0, MAX_CPUS)` iterates over 256 entries regardless of actual CPU count. On a 16-CPU machine, this wastes ~240 iterations per preemption attempt. The nginx scheduler introduced a bounded scan:

```c
// nginx_aware.bpf.c:136-140
u32 limit = nr_cpus;
u32 i;

if (limit > MAX_CPUS)
    limit = MAX_CPUS;

bpf_for(i, 0, limit) {
```

Where `nr_cpus` is set once during initialization:

```c
// nginx_aware.bpf.c:200
nr_cpus = scx_bpf_nr_cpu_ids();
```

---

## 6. Mechanism 5: Per-Task Classification Caching

In the db_sim, RocksDB, and Redis schedulers, the classifier function (`is_query_task`, `is_rocksdb_background`, `is_redis_background`) calls `bpf_probe_read_kernel_str` **on every scheduling event**. This is a kernel function call that copies 16 bytes from kernel memory — not catastrophically expensive, but it adds up.

In the nginx scheduler, the classifier is called from four callbacks (`select_cpu`, `enqueue`, `running`, `stopping`), potentially 3-4 times per scheduling cycle per task. Profiling showed this caused a measurable P50 regression (10.6ms vs 1.5ms baseline).

### 6.1 BPF Task Local Storage

The solution uses `BPF_MAP_TYPE_TASK_STORAGE` — a BPF map type that attaches a per-task data structure to `task_struct`, with the kernel managing the lifecycle (allocation on first access, cleanup on task exit).

```c
// nginx_aware.bpf.c:43-52
struct task_class {
    u8 class;
};

struct {
    __uint(type, BPF_MAP_TYPE_TASK_STORAGE);
    __uint(map_flags, BPF_F_NO_PREALLOC);
    __type(key, int);
    __type(value, struct task_class);
} task_class_map SEC(".maps");
```

### 6.2 Cached Classification Logic

```c
// nginx_aware.bpf.c:80-111
static u8 classify_task(struct task_struct *p)
{
    struct task_class *tc;

    /* Fast path: return cached classification */
    tc = bpf_task_storage_get(&task_class_map, p, 0, 0);
    if (tc && tc->class != TASK_UNKNOWN)
        return tc->class;

    /* Slow path: first time seeing this task — read comm and classify */
    char comm[16];
    u8 result = TASK_NORMAL;

    if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) >= 0) {
        if (comm[0] == 'n' && comm[1] == 'g' && comm[2] == 'i' &&
            comm[3] == 'n' && comm[4] == 'x')
            result = TASK_NGINX;
        else if (comm[0] == 's' && comm[1] == 't' && comm[2] == 'r' &&
                 comm[3] == 'e' && comm[4] == 's' && comm[5] == 's' &&
                 comm[6] == '-' && comm[7] == 'n' && comm[8] == 'g')
            result = TASK_CPU_HOG;
    }

    /* Cache for future calls */
    tc = bpf_task_storage_get(&task_class_map, p, 0,
                              BPF_LOCAL_STORAGE_GET_F_CREATE);
    if (tc)
        tc->class = result;

    return result;
}
```

The flow:
1. **Cache hit** (`bpf_task_storage_get` with flags=0): returns the previously stored classification. Cost: one hash lookup, no kernel string copy.
2. **Cache miss** (first scheduling event for this task): perform the full `bpf_probe_read_kernel_str` + byte comparison, then store the result with `BPF_LOCAL_STORAGE_GET_F_CREATE`.
3. **All subsequent calls**: hit the cache. Since thread names in these applications are set once at creation and never change, the cache is always valid.

**Impact**: P50 latency dropped from 10.6ms to 6.7ms — a 37% reduction — solely from avoiding redundant `bpf_probe_read_kernel_str` calls.

---

## 7. Putting It All Together: Scheduling Event Lifecycle

Here is the complete flow when a foreground thread (e.g., an nginx worker) wakes up on a fully loaded 16-CPU system with background CPU hogs running:

```
nginx worker wakes up
  │
  ▼
ops.select_cpu()
  ├── scx_bpf_select_cpu_dfl() → no idle CPU (is_idle=false)
  ├── classify_task(p) → TASK_NGINX (from cache)
  ├── Scan bg_running[0..15]: find CPU 7 running stress-ng for 3.1ms
  ├── scx_bpf_kick_cpu(7, SCX_KICK_PREEMPT) → IPI to CPU 7
  └── return selected cpu
  │
  ▼
ops.enqueue()
  ├── classify_task(p) → TASK_NGINX (cache hit)
  └── scx_bpf_dsq_insert(p, SCX_DSQ_GLOBAL, 5ms, flags)
  │
  ▼
[CPU 7 receives IPI, reschedules]
  ├── ops.stopping(stress_ng) → bg_running[7] = 0
  ├── stress-ng task → back to BACKGROUND_DSQ
  │
  ▼
[CPU 7 calls ops.dispatch(), but first drains GLOBAL]
  ├── Framework auto-drains SCX_DSQ_GLOBAL → finds nginx worker
  └── nginx worker starts running on CPU 7
  │
  ▼
ops.running(nginx_worker)
  └── classify_task(p) → TASK_NGINX → no bg_running update (not a CPU hog)
```

Total added latency vs. CFS: one cache-hit classification (~ns), one bg_running scan (16 array lookups), one IPI. The nginx worker runs within microseconds of waking up instead of waiting for the stress-ng thread's timeslice to expire naturally (potentially 20ms+).

---

## 8. Time-Slice Differentiation

All four schedulers assign asymmetric time-slices based on thread role:

| Thread Role | Time Slice | Rationale |
|---|---|---|
| Foreground / latency-critical | 5ms (`DEFAULT_SLICE_NS`) | Short slices ensure foreground threads yield quickly, keeping queue wait times low for other foreground threads |
| Background / CPU-heavy | 20ms (`BACKGROUND_SLICE_NS`) | Long slices reduce context-switch frequency for throughput-oriented work; fewer interruptions = better cache utilization |
| db_sim query threads | 3ms (`QUERY_SLICE_NS`) | Even shorter — db_sim queries complete in <1ms, so 3ms is generous while keeping scheduling overhead low |

```c
// nginx_aware.bpf.c:29-31
#define DEFAULT_SLICE_NS     5000000ULL   /* 5ms */
#define BACKGROUND_SLICE_NS  20000000ULL  /* 20ms */
#define BG_MIN_RUN_NS        2000000ULL   /* 2ms minimum before preemption */
```

The `BG_MIN_RUN_NS` (2ms) parameter prevents preemption thrashing: a background thread that was just scheduled should run for at least 2ms before being kicked, otherwise the system wastes time on context switches that provide no latency benefit.

---

## 9. Design Variants Across Applications

The four schedulers instantiate the same template with different parameters, but also exhibit structural differences driven by workload characteristics:

### 9.1 Comparison Table

| Feature | db_sim | RocksDB (v7) | Redis | Nginx (v3) |
|---|---|---|---|---|
| **DSQ topology** | 2 custom (QUERY + COMPACT) | 2 custom (FG + BG) | 2 custom (FG + BG) | 1 custom (BG) + SCX_DSQ_GLOBAL |
| **Foreground path** | Custom DSQ | Custom DSQ | Custom DSQ | SCX_DSQ_GLOBAL |
| **Selective preemption** | No | Yes | Yes | Yes |
| **Per-task caching** | No | No | No | Yes (task local storage) |
| **Classification calls** | 2 per cycle (select_cpu + enqueue) | 2-3 per cycle | 2-3 per cycle | 3-4 per cycle (cached after first) |
| **Contention model** | Internal (query vs. compact threads) | Internal (reader vs. compaction threads) | Internal (event loop vs. bio/persistence threads) | External (nginx workers vs. co-located CPU hogs) |
| **CPU scan bound** | N/A | MAX_CPUS (256) | MAX_CPUS (256) | nr_cpus (actual count) |

### 9.2 When Each Design Applies

- **Dual custom DSQ** (db_sim): Simplest. Use when both thread classes are part of the same application and you need explicit priority control in `dispatch()`.
- **Dual custom DSQ + preemption** (RocksDB, Redis): When background threads can hold CPUs for long periods and foreground threads are latency-sensitive. The preemption mechanism ensures foreground threads don't wait for background timeslices to expire.
- **Asymmetric + preemption + caching** (Nginx): When the scheduler must handle all system threads (not just one application), the asymmetric design avoids penalizing unrelated processes. Caching is essential when the classifier is called from many callbacks.

---

## 10. Compilation and Kernel Verification

BPF schedulers must pass the kernel verifier before they can run. The compilation pipeline:

```bash
# Compile BPF C to object file
clang -g -O2 -target bpf -D__TARGET_ARCH_x86 \
    -I../../scheduler/scx/scheds/include \
    -I../../scheduler/scx/scheds/include/bpf-compat \
    -idirafter /usr/include/x86_64-linux-gnu \
    -c nginx_aware.bpf.c -o nginx_aware.bpf.o

# Load into kernel for verification + execution
sudo ../../bpf_loader/loader ./nginx_aware.bpf.o
```

The BPF verifier checks:
- All memory accesses are bounded (no out-of-bounds reads)
- All loops terminate (guaranteed by `bpf_for` bounded iteration)
- No unbounded recursion
- All map accesses use valid keys
- All helper function calls use correct argument types

This is why we use patterns like byte-by-byte comparison (verifier can prove each access is within the 16-byte `comm` buffer) and `bpf_for` (verifier can prove the loop terminates) instead of standard C idioms.

---

## 11. Summary

The implementation pipeline from LLM knowledge to kernel behavior:

```
LLM Analysis Output                BPF Implementation
─────────────────                  ───────────────────
Thread name patterns         →     byte-by-byte comm comparison in classifier function
Thread role assignment       →     DSQ routing in enqueue() callback
  (foreground vs background)
Priority ordering            →     DSQ drain order in dispatch() callback
Latency sensitivity          →     Selective preemption in select_cpu() callback
                                   (bg_running/bg_start_ns maps + scx_bpf_kick_cpu)
Time-slice policy            →     SLICE_NS constants per thread class
Performance optimization     →     Idle CPU fast path (SCX_DSQ_LOCAL in select_cpu)
                                   Per-task classification caching (BPF task local storage)
                                   Asymmetric DSQ topology (foreground on SCX_DSQ_GLOBAL)
```

Each mechanism is independently simple. The engineering challenge is combining them correctly — a wrong DSQ topology choice (v1 nginx: all non-nginx → BACKGROUND) or a missing optimization (v2 nginx: no classification caching) can turn a latency improvement into a latency regression. The iterative compile-deploy-benchmark loop, driven by the LLM interpreting performance data, is what makes the system converge on a correct design.
