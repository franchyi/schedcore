# Application-Aware Kernel Scheduling via LLM-Driven Thread Discovery

## Problem

The Linux CFS/EEVDF scheduler treats all threads equally within a cgroup. It cannot distinguish latency-critical foreground threads (event loops, query handlers) from throughput-oriented background threads (compaction, persistence, GC). Under CPU oversubscription, this causes tail latency spikes.

## Approach

We present a framework that builds application-specific BPF kernel schedulers using sched-ext. Given application source code, the framework:

1. **Discovers threads** via static analysis (tree-sitter) + LLM classification, producing a Thread Manifest (thread name to role mapping)
2. **Selects a scheduling pattern** based on contention level (dual DSQ, selective preemption, or asymmetric + task storage)
3. **Generates a BPF scheduler skeleton** from the manifest and pattern
4. **Validates** via A/B benchmarking against CFS

The LLM's role is thread discovery only. BPF schedulers are hand-written systems engineering guided by the thread classification.

### Pipeline Architecture

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

### Key Design Insight: The Asymmetric Principle

> Only intervene in scheduling of threads you want to deprioritize. Let foreground threads use the kernel's default fast path.

Routing foreground threads through custom dispatch queues adds overhead that hurts P99.9 latency. Instead: push background threads into a deprioritized custom DSQ, let the framework handle foreground threads natively via `SCX_DSQ_GLOBAL`.

## Results

Evaluated on 4 workloads (8-core / 16-thread Intel Xeon, Linux 6.14, sched-ext):

| Workload | Scheduler | Tail Latency Reduction |
|---|---|---|
| **db_sim** (synthetic DB) | `db_aware` | 79x max latency reduction (25.9ms to 0.33ms) |
| **RocksDB** (stress) | `rocksdb_aware` | 67.8% P99.9, 77% P99.99 |
| **Redis** (persistence pressure) | `redis_aware` | 76% P99 (GET), 72% P99 (SET) |
| **Nginx** (external contention) | `nginx_aware` | 83% P99, 87% P99.9 |

All schedulers preserve or improve throughput. The trade-off is modest P50 overhead (0-20%) in exchange for dramatic tail latency reduction.

### Runtime Thread Discovery

The dynamic eBPF profiler (Stage 1c) discovered `jemalloc_bg_thd` in Redis -- 4 background memory purging threads from the jemalloc allocator that are invisible to static source analysis. This demonstrates the value of runtime profiling for dependency-level threads.

## Documents

| Document | Purpose |
|---|---|
| `design.md` | Full technical design: scheduler patterns, per-workload architecture, evaluation results |
| `pipeline_guide.md` | Step-by-step pipeline instructions with Redis as example |
| `future_plan.md` | Research roadmap |
