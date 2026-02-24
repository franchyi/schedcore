# SchedCP: Bridging the Application-Kernel Scheduling Gap via LLM-Synthesized BPF Schedulers

**Target venue:** EuroSys / ATC / SOSP (systems track)

---

## Abstract (draft sketch)

Modern applications embed rich scheduling semantics — thread priorities, latency-critical paths, background maintenance — but the kernel scheduler is fundamentally blind to them. We present SchedCP, a framework that uses large language models to *automatically* analyze application source code, extract thread-role semantics, and synthesize custom BPF kernel schedulers that are hot-loaded via Linux sched-ext. SchedCP addresses three key challenges: (1) **structured semantic extraction** from unreliable LLM code understanding via a constrained analysis protocol grounded in verifiable code artifacts; (2) **a scheduling policy design space** that navigates the fundamental tradeoff between median and tail latency through workload-adaptive policy selection; and (3) **a parameterized BPF policy template** that separates the control plane (LLM-driven semantic analysis and policy decisions) from the data plane (verified, low-overhead BPF scheduling logic). We evaluate SchedCP on four unmodified production applications — RocksDB, Redis, Nginx, and a synthetic DB simulation — achieving up to 83% P99 reduction (Nginx), 76% P99 reduction (Redis), and 67.8% P99.9 reduction (RocksDB) under CPU oversubscription, with zero application modification.

---

## 1. Introduction  (~2 pages)

### Opening: The Semantic Gap Is Universal

- Applications internally distinguish between latency-critical work and background maintenance: RocksDB has foreground reads vs. background compaction; Redis has its event loop vs. `bio_*` persistence threads; Nginx has workers vs. co-located batch jobs. These roles are **explicit in the source code** but **invisible to the kernel**.
- The Linux CFS/EEVDF scheduler treats all threads within a cgroup equally. When a RocksDB read thread wakes from I/O and competes with 32 compaction threads, CFS has no basis to prioritize it. Result: tail latency spikes under contention.
- Existing solutions (nice, cgroups, hand-written sched-ext, scx_layered) require manual, per-application expert effort. They don't scale across the diversity of modern applications.

### The Opportunity: sched-ext + LLMs

- Linux 6.12 introduced sched-ext: BPF programs can implement custom kernel scheduling policies, hot-loaded without reboot. This is the *mechanism*.
- LLMs can read and reason about source code at scale. They can identify thread naming conventions, thread pool architectures, and criticality hierarchies. This is the *knowledge source*.
- But simply prompting an LLM with "write me a scheduler" produces naive designs that **make things worse** (our v1-v4 designs all regressed P99.9 by 373-474%). The gap between LLM code generation capability and correct, high-performance scheduler synthesis is the core challenge.

### Contributions

1. **SchedCP**, an end-to-end framework that closes the loop from application source code to deployed kernel scheduler, using an LLM as the semantic bridge between application and kernel. Unlike manual approaches, SchedCP requires no scheduling expertise from the user and no modifications to the application.

2. **A constrained semantic extraction protocol** that structures the LLM's analysis into verifiable, kernel-actionable artifacts (thread comm patterns, criticality rankings, contention models), addressing the unreliability of unconstrained LLM code understanding.

3. **The Asymmetric Scheduling Principle and its workload-adaptive generalization**: a design space for BPF scheduling policies that navigates the P50-vs-tail tradeoff. We identify three policy regimes — *passthrough* (zero overhead, zero improvement), *asymmetric deprioritization* (near-zero P50 cost, moderate tail improvement), and *selective preemption* (bounded P50 cost, maximum tail improvement) — and show how to select among them based on application characteristics.

4. **A parameterized BPF policy template** with clean control plane / data plane separation. The control plane (LLM + verification) fills in application-specific parameters (thread classification rules, DSQ topology, preemption thresholds); the data plane (BPF template code) provides verified, low-overhead scheduling primitives. This makes the framework extensible to new applications without redesigning the scheduler core.

5. **Evaluation on four unmodified applications** demonstrating 67-87% tail latency reduction across diverse workload types (storage engine, cache, web server, synthetic database).

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
- **Key gap**: no prior work uses LLMs to synthesize *kernel scheduling policies* from *application semantics*

---

## 3. Problem and Motivation  (~2 pages)

### 3.1 The Semantic Gap: A Quantitative Study

Concrete example with RocksDB: show what happens when 16 foreground read threads compete with 32 background compaction threads on 16 CPUs under CFS.

- CFS treats all 48 threads equally
- A read thread waking from I/O wait enters the runqueue behind compaction threads
- Worst case: read waits for a full compaction timeslice (4-6ms) before being scheduled
- Measured: P99.9 = 3.8ms, max = 25.9ms (db_sim)

### 3.2 Why Naive LLM-Generated Schedulers Fail

This is critical — show that the problem is **not trivially solved** by prompting an LLM.

**Experiment**: Ask an LLM to generate a BPF scheduler for RocksDB given its source code. The natural design (dual DSQ: foreground vs. background) **regresses P99.9 by 413%** (169us → 866us).

| Naive Design | P99.9 Regression | Root Cause |
|---|---|---|
| Dual custom DSQ (v1) | +413% | Global DSQ lock contention on all enqueue/dispatch |
| + SCX_KICK_PREEMPT (v2) | +373% | Preemption IPI overhead on the fast path |
| + Short bg slice (v3) | +412% | Excessive context switches |
| + Per-CPU maps (v4) | +474% | BPF map lookup overhead per scheduling event |
| + Force local dispatch (v5) | **Crash** | sched-ext API constraint violation |

**Takeaway**: BPF scheduling has a hidden cost model that LLMs don't understand. Routing latency-critical threads through *any* custom dispatch path adds overhead that exceeds the benefit. A correct scheduler must navigate non-obvious design constraints.

### 3.3 Three Challenges

**Challenge 1: Unreliable Semantic Extraction.** LLMs can hallucinate thread names, miss critical threads, or misclassify roles. An incorrect classification (e.g., deprioritizing the Redis event loop) can be catastrophic. The extraction must be *grounded* in verifiable code artifacts and *validated* before deployment.

**Challenge 2: The P50-vs-Tail Tradeoff.** Any BPF scheduling intervention adds per-event overhead (enqueue callbacks, map lookups, cross-CPU dispatch). This overhead is amortized at the tail (where contention causes multi-millisecond waits) but visible at the median. Different applications have different tolerance: RocksDB can absorb 20% P50 regression for 68% P99.9 improvement; Nginx cannot.

**Challenge 3: Policy Generalization.** Each application has unique thread roles, naming conventions, and contention patterns. But writing a custom BPF scheduler per application doesn't scale. We need *reusable scheduling primitives* that the LLM can parameterize, not arbitrary BPF code generation.

---

## 4. SchedCP Design  (~4 pages)

### 4.1 Architecture Overview

```
                          CONTROL PLANE
    ┌─────────────────────────────────────────────────┐
    │                                                 │
    │  ┌──────────┐    ┌──────────────┐    ┌────────┐ │
    │  │ App Code │───→│  Structured  │───→│ Policy │ │
    │  │ Analysis │    │  Semantic    │    │ Select │ │
    │  │ (LLM)   │    │  Extraction  │    │        │ │
    │  └──────────┘    └──────────────┘    └───┬────┘ │
    │                                         │      │
    │  ┌──────────┐    ┌──────────────┐       │      │
    │  │ Compile  │◄───│  Template    │◄──────┘      │
    │  │ + Verify │    │  Instantiate │               │
    │  └────┬─────┘    └──────────────┘               │
    │       │                                         │
    └───────┼─────────────────────────────────────────┘
            │ hot-load .bpf.o
            ▼
    ┌─────────────────────────────────────────────────┐
    │                   DATA PLANE                    │
    │                                                 │
    │  ┌────────────┐  ┌───────────┐  ┌────────────┐ │
    │  │ select_cpu │─→│  enqueue  │─→│  dispatch  │ │
    │  │ (idle CPU  │  │ (classify │  │ (priority  │ │
    │  │  fast path)│  │  + route) │  │  drain)    │ │
    │  └────────────┘  └───────────┘  └────────────┘ │
    │                                                 │
    │  ┌──────────────────────────────────────────┐   │
    │  │ Per-task classification cache (BPF TLS)  │   │
    │  │ Per-CPU bg tracking maps                 │   │
    │  │ Selective preemption logic                │   │
    │  └──────────────────────────────────────────┘   │
    │                                                 │
    └─────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────┐
    │                 FEEDBACK LOOP                   │
    │  Benchmark → Metrics → LLM Analysis → Iterate  │
    └─────────────────────────────────────────────────┘
```

**Key insight: separation of concerns.** The LLM operates only in the control plane — it never generates arbitrary BPF code. Instead, it fills in parameters of a verified template. The data plane is a fixed, pre-verified BPF skeleton with parameterized slots. This bounds the LLM's blast radius: a wrong thread classification wastes scheduling priority but cannot crash the kernel.

### 4.2 Structured Semantic Extraction (Control Plane — Challenge 1)

**Problem**: Unconstrained LLM prompting ("What are the critical threads?") produces unreliable, unverifiable answers.

**Solution**: A multi-phase extraction protocol that constrains the LLM to produce structured, verifiable outputs.

**Phase 1: Thread Inventory.**
- Prompt: "List all `pthread_setname_np`, `prctl(PR_SET_NAME)`, and thread pool creation sites in the codebase."
- Output: Structured table of `{comm_pattern, source_location, creation_context}`
- *Verifiable*: Each entry points to a specific source line. Human or automated tool can confirm.

**Phase 2: Criticality Ranking.**
- Prompt: "For each thread group, classify as: (a) latency-critical (serves user requests), (b) throughput-sensitive (background maintenance), (c) neutral. Justify from code context."
- Output: Ranked list with per-entry justification grounded in source code evidence
- *Verifiable*: Justifications reference concrete code paths (e.g., "rocksdb:low handles compaction scheduled via `BGWorkCompaction`, not on the read path")

**Phase 3: Contention Model.**
- Prompt: "How do these thread groups interact? Which ones compete for CPU? Under what conditions (write-heavy, cache miss, oversubscription)?"
- Output: Contention graph (which thread groups interfere) + trigger conditions
- *Verification*: Cross-reference with application profiling or documentation

**Phase 4: Validation.**
- *comm-pattern verification*: Run the application and check `ps -eLo comm` against predicted patterns. Flag mismatches before scheduler generation.
- *Criticality smoke test*: If the LLM identifies thread X as "background", verify that deprioritizing X does not crash or stall the application (short test run with scheduler loaded).

**Why structured extraction matters**: It transforms an unbounded NLP problem ("understand this codebase") into a series of bounded, verifiable sub-problems. Each phase produces an artifact that can be independently validated before proceeding. This is analogous to how compilers use typed intermediate representations rather than pattern-matching on source text.

### 4.3 Workload-Adaptive Policy Selection (Control Plane — Challenge 2)

**Problem**: No single scheduling policy works for all applications. Dual-DSQ adds P50 overhead but helps tail; asymmetric has zero P50 overhead but limited tail improvement.

**Solution**: Three policy regimes, selected based on the contention model from Phase 3.

#### Policy Regime 1: Asymmetric Deprioritization
```
Foreground → SCX_DSQ_GLOBAL (framework fast path, ~0 overhead)
Background → BACKGROUND_DSQ (deprioritized, drained last)
```
- **When**: Low-contention workloads where foreground threads rarely compete (e.g., RocksDB readrandom with large cache)
- **Tradeoff**: 0% P50 regression, modest tail improvement (max latency -60%), zero P99.9 improvement under low contention
- **Mechanism**: Only background threads pay the custom-DSQ cost. Foreground threads are indistinguishable from CFS at the scheduling level.

#### Policy Regime 2: Selective Preemption
```
Foreground → FOREGROUND_DSQ (priority dispatch)
Background → BACKGROUND_DSQ (deprioritized, long slice)
+ Idle-CPU fast path (SCX_DSQ_LOCAL, bypasses both DSQs)
+ bg_running per-CPU map + SCX_KICK_PREEMPT
```
- **When**: High-contention workloads where foreground threads frequently find all CPUs busy (e.g., RocksDB stress, Redis under persistence pressure)
- **Tradeoff**: ~20% P50 regression from dual-DSQ, but 67-76% P99/P99.9 reduction. The idle-CPU fast path ensures P50 overhead only manifests when CPUs are actually contended.
- **Mechanism**: Active intervention — when foreground wakes and no idle CPU exists, preempt a background thread. The `bg_running` map provides O(N_cpu) lookup to find a preemption target.

#### Policy Regime 3: External Contention Isolation
```
App threads → SCX_DSQ_GLOBAL (framework fast path)
Known CPU hogs → BACKGROUND_DSQ (deprioritized)
+ BPF task local storage (classification cache)
+ Selective preemption for identified app threads
```
- **When**: Application contends with *external* CPU-bound processes, not internal threads (e.g., Nginx under co-located batch jobs)
- **Tradeoff**: ~5ms P50 increase (inherent sched-ext overhead), but 83% P99 reduction and dramatically lower variance
- **Mechanism**: Classify external processes (not app threads) as background. Task local storage caches classification to amortize the per-event BPF overhead.

#### Policy Selection Logic

The LLM's contention model (Phase 3) determines which regime to use:
- Internal contention + low intensity → Regime 1 (Asymmetric)
- Internal contention + high intensity → Regime 2 (Selective Preemption)
- External contention → Regime 3 (External Isolation)

This can be formalized as a decision tree the LLM follows, rather than an open-ended design choice.

### 4.4 Parameterized BPF Policy Template (Data Plane — Challenge 3)

**Problem**: Generating arbitrary BPF code per application is error-prone, unverifiable, and doesn't leverage shared scheduling primitives.

**Solution**: A fixed BPF template with parameterized slots.

#### Template Structure

```c
/* === PARAMETERS (filled by control plane) === */
#define POLICY_REGIME     <1|2|3>          // from policy selection
#define FG_SLICE_NS       <5000000>        // foreground timeslice
#define BG_SLICE_NS       <20000000>       // background timeslice
#define PREEMPT_THRESHOLD <2000000>        // min bg runtime before preempt (ns)

/* === CLASSIFICATION FUNCTION (generated per-app) === */
static u8 classify_task(struct task_struct *p) {
    // Task local storage cache lookup
    // One-time comm pattern matching (app-specific)
    // Return: TASK_FOREGROUND | TASK_BACKGROUND | TASK_NORMAL
}

/* === FIXED SCHEDULING LOGIC (shared across all apps) === */
// select_cpu: idle-CPU fast path (always)
// enqueue: route by classification (regime-dependent)
// dispatch: priority drain (regime-dependent)
// running/stopping: bg_running map update (regime 2,3)
```

**What the LLM generates**: Only `classify_task()` (the comm pattern matching) and the parameter values. The scheduling logic is fixed template code — pre-verified against the BPF verifier, tested across applications.

**What is NOT LLM-generated**: The dispatch logic, DSQ topology, preemption mechanism, fast paths. These are engineering contributions encoded in the template.

#### Template Primitives (reusable across all apps)

| Primitive | Purpose | Used In |
|---|---|---|
| **Idle-CPU fast path** | `select_cpu` → `SCX_DSQ_LOCAL` when idle | All regimes |
| **Task local storage cache** | Cache `classify_task()` result per-task | All regimes (amortizes overhead) |
| **Priority dispatch** | `dispatch()` drains FG DSQ before BG DSQ | Regime 2 |
| **Selective preemption** | `bg_running` map + `SCX_KICK_PREEMPT` | Regime 2, 3 |
| **Background slice extension** | 20ms slices for BG threads (reduce ctx switches) | All regimes |
| **Graceful degradation** | If scheduler errors, sched-ext falls back to CFS | All regimes |

### 4.5 Closed-Loop Verification and Iteration (Feedback Loop)

**Problem**: Even with correct semantic extraction and policy selection, the scheduler may not achieve the expected improvement (or may regress) due to workload dynamics.

**Solution**: A benchmark-driven feedback loop.

```
1. Deploy scheduler (hot-load .bpf.o)
2. Run standardized benchmark (same binary, same config)
3. Collect metrics: P50, P99, P99.9, throughput
4. Compare against CFS baseline
5. If regression detected:
   a. LLM analyzes metrics + scheduler config
   b. Identifies potential cause (wrong classification? wrong regime?)
   c. Adjusts parameters or regime
   d. Re-compile, re-verify, re-deploy
6. Iterate until convergence or timeout
```

**Example iteration (real, from our evaluation)**:
- Nginx v1: All non-nginx → BACKGROUND. Result: wrk2 starved, P50 = 12s. LLM diagnosis: "BACKGROUND_DSQ starvation — load generator and system daemons incorrectly classified as background."
- Nginx v2: Only stress-ng → BACKGROUND. Result: P50 = 10.6ms. LLM diagnosis: "`bpf_probe_read_kernel_str` called 3x per scheduling event."
- Nginx v3: + Task local storage. Result: P50 = 6.7ms, P99 = 33ms. Converged.

---

## 5. Implementation  (~1.5 pages)

### 5.1 Infrastructure

- **MCP server** (Rust): scheduler lifecycle management, compilation, verification, monitoring
- **BPF compilation**: clang + sched-ext headers → .bpf.o
- **Loader**: custom loader binary loads .bpf.o into kernel, monitors sched-ext state
- **Benchmark harness**: per-workload scripts with automated A/B comparison, multiple runs, statistical summary

### 5.2 BPF Implementation Details

- Thread classification: byte-by-byte `p->comm` comparison (BPF verifier disallows `strcmp`)
- Task local storage: `BPF_MAP_TYPE_TASK_STORAGE` for per-task classification caching
- Per-CPU tracking: `BPF_MAP_TYPE_ARRAY` maps for `bg_running` / `bg_start_ns`
- Bounded loops: `bpf_for(i, 0, nr_cpus)` for preemption target search
- Kernel API constraints: `SCX_DSQ_LOCAL` only valid in `select_cpu` when idle CPU found; `SCX_DSQ_LOCAL_ON` causes head-of-line blocking (discovered empirically in Nginx v4)

### 5.3 LLM Integration

- Model: Claude (code analysis) via MCP tool interface
- Structured prompts for each extraction phase
- Automated comm-pattern verification via `ps -eLo comm` cross-check
- Human-in-the-loop approval for classification before scheduler deployment

---

## 6. Evaluation  (~4 pages)

### 6.1 Experimental Setup

| Property | Value |
|---|---|
| CPU | Intel Xeon Platinum 8375C @ 2.90GHz, 8 cores / 16 HW threads |
| Kernel | 6.14.0+ (sched-ext enabled) |
| OS | Ubuntu Linux |
| Baselines | CFS (default kernel scheduler), scx_bpfland (general-purpose sched-ext) |

### 6.2 End-to-End Results (Summary Table)

| Workload | Contention Type | Policy Regime | P99 Change | P99.9 Change | P50 Change | Throughput |
|---|---|---|---|---|---|---|
| **db_sim** (synthetic) | Internal, constant | Regime 2 | -2.4% | -98.7% (max) | 0% | +2.7% |
| **RocksDB** (read-only) | Internal, low | Regime 1 | -0.6% | 0% | 0% | -0.3% |
| **RocksDB** (stress) | Internal, high | Regime 2 | +102% | **-67.8%** | +20% | -3.6% |
| **Redis** (GET+persist) | Internal, bursty | Regime 2 | **-75.8%** | N/A | +3.2% | **+15.1%** |
| **Nginx** (HTTP+stress) | External | Regime 3 | **-83%** | **-87%** | +4.3x | -0.2% |

### 6.3 Detailed Results per Workload

#### 6.3.1 RocksDB db_bench

- **Low contention** (readrandom, 16 threads + 16 compaction): Regime 1 achieves **zero P99.9 regression** — validates "first, do no harm" principle
- **High contention** (readrandomwriterandom, 16 threads + 32 compaction + 4 flush, 1MB cache): Regime 2 achieves **67.8% P99.9 reduction** (3.8ms → 1.2ms), **77% P99.99 reduction** (8.2ms → 1.9ms), with 3.6% throughput cost
- **Write latency also improves**: P99.9 reduced by 79% — scheduler helps all foreground operations

#### 6.3.2 Redis

- **76% P99 reduction** (GET), **72% P99 reduction** (SET) under persistence pressure + CPU oversubscription
- **+15-20% throughput improvement** — event loop runs with less interference, improving both latency and throughput
- Demonstrates Regime 2 on a single-threaded event loop with I/O threads

#### 6.3.3 Nginx

- **83% P99 reduction**, **87% P99.9 reduction** under external CPU oversubscription
- **Dramatically more consistent**: CFS P99 variance = 5x across runs, nginx_aware = 1.06x
- **P50 tradeoff**: 1.5ms → 6.7ms (inherent sched-ext BPF dispatch overhead)
- Demonstrates Regime 3 (external contention model) and task local storage optimization

#### 6.3.4 db_sim (Synthetic, Controlled)

- **79x max latency reduction** (25.9ms → 0.33ms) under 2x CPU oversubscription
- Validates the fundamental mechanism in a controlled environment

### 6.4 Ablation Studies

#### 6.4.1 Policy Regime Selection Matters

Compare Regime 1 vs Regime 2 on the same workload:
- RocksDB readrandom: Regime 1 = 0% P99.9 change; Regime 2 = +20% P50 for minimal gain → **Regime 1 correct**
- RocksDB stress: Regime 1 = 0% P99.9 improvement; Regime 2 = -67.8% P99.9 → **Regime 2 correct**
- Wrong regime selection costs: either unnecessary P50 overhead or missed tail improvement

#### 6.4.2 Task Local Storage Impact (Nginx)

| Optimization | P50 | P99 |
|---|---|---|
| No caching (v2) | 10.6ms | 32.7ms |
| Task local storage (v3) | 6.7ms | 32.6ms |
| **Improvement** | **-37%** | ~0% |

Task storage reduces the per-event overhead but doesn't affect tail (tail is dominated by contention, not per-event cost).

#### 6.4.3 Design Iteration History (RocksDB v1-v7)

Full table showing 7 iterations, the P99.9 result, and the root cause of each failure. This demonstrates that the design space is non-trivial and that systematic exploration (via the feedback loop) is necessary.

#### 6.4.4 Comparison with General-Purpose sched-ext

Compare SchedCP-generated schedulers vs. scx_bpfland (best general-purpose sched-ext scheduler):
- scx_bpfland: application-agnostic heuristics (vruntime-based)
- SchedCP: application-aware classification
- Expected: SchedCP matches or beats bpfland on tail latency, bpfland may have lower P50 overhead

### 6.5 Overhead Analysis

- BPF scheduling overhead per event: ~X us (measured via `bpf_ktime_get_ns` instrumentation)
- Task local storage lookup: ~Y ns (vs ~Z ns for `bpf_probe_read_kernel_str`)
- Memory overhead: per-task storage (8 bytes) + per-CPU maps (2 x 256 entries)
- Scheduler load/unload time: <2 seconds
- Total LLM pipeline time (analysis → deploy): measure minutes vs. hours for manual expert

---

## 7. Discussion  (~1.5 pages)

### 7.1 When Does SchedCP Help?

The improvement scales with **contention intensity**:
- Under-subscribed systems (threads < CPUs): No benefit — idle-CPU fast path handles everything
- Moderate oversubscription: Regime 1 prevents regression, modest tail improvement
- Heavy oversubscription: Regime 2/3 deliver dramatic tail reduction

**Rule of thumb**: SchedCP helps when an application has mixed-criticality threads and runs under CPU contention (common in cloud environments with co-located workloads).

### 7.2 Limitations

1. **Thread naming dependency**: Applications that don't name threads (or use generic names) are harder to classify. Mitigation: fall back to PID-range or cgroup-based classification.
2. **P50 overhead**: sched-ext BPF dispatch adds inherent overhead (Nginx: 1.5ms → 6.7ms). For workloads where P50 matters more than tail, SchedCP may not be appropriate.
3. **Static classification**: Thread roles are determined at analysis time. Applications with dynamic thread role changes (e.g., thread pool reassignment) need runtime reclassification (future work).
4. **LLM accuracy**: While structured extraction reduces errors, the LLM can still misclassify threads. The validation phase catches gross errors but subtle mis-rankings may persist.
5. **Single-machine scope**: SchedCP operates on individual nodes. Distributed scheduling (e.g., cluster-wide thread placement) is out of scope.

### 7.3 Generality Beyond These Four Applications

Discuss applicability to: PostgreSQL (autovacuum vs. query backends), MySQL (InnoDB purge vs. client threads), vLLM (prefill vs. decode), memcached (worker threads vs. slab rebalancer).

### 7.4 BPF Verifier as Safety Net

Unlike arbitrary kernel modules, BPF programs are verified before loading. Even if the LLM generates incorrect scheduling logic, the BPF verifier guarantees:
- No infinite loops (bounded iteration)
- No invalid memory access
- No kernel crashes
- Graceful fallback to CFS on scheduler error (`UEI_RECORD` + sched-ext exit handler)

This makes LLM-generated schedulers **safe to deploy** even without full formal verification.

---

## 8. Related Work  (~1 page)

### Application-Aware Scheduling Systems

| System | Approach | Requires App Changes | Auto-Derived Policy | Overhead |
|---|---|---|---|---|
| Shinjuku | HW interrupt preemption | Yes (runtime) | No | Low (HW) |
| Caladan | Core allocation | Yes (runtime lib) | No | Medium |
| ghOSt | User-space delegation | Yes (agent) | No | High |
| scx_layered | BPF + manual layers | No | No | Low |
| **SchedCP** | **BPF + LLM-derived policy** | **No** | **Yes** | **Low** |

### LLM for Systems

- LLM-assisted kernel config tuning (e.g., TuneBench)
- LLM for bug detection in systems code
- **Distinction**: SchedCP uses LLMs not just for analysis but for *policy synthesis* — the LLM's output directly determines kernel scheduling behavior

### Programmable Scheduling

- sched-ext ecosystem (bpfland, lavd, rusty): general-purpose, application-agnostic
- eBPF for network scheduling (EDT, pacing): analogous control/data plane separation
- **Distinction**: SchedCP bridges application semantics into the sched-ext framework automatically

---

## 9. Conclusion  (~0.5 pages)

SchedCP demonstrates that the semantic gap between applications and the kernel scheduler can be bridged automatically using LLMs. By structuring the problem into constrained semantic extraction, workload-adaptive policy selection, and parameterized BPF templates, we avoid the pitfalls of unconstrained LLM code generation while achieving significant tail latency improvements across four diverse, unmodified applications. The framework requires no scheduling expertise, no application modifications, and no kernel patches — only the application's source code.

---

## Appendix: Figure / Table Plan

### Figures
1. Architecture diagram (Section 4.1) — control plane / data plane / feedback loop
2. CDF plots: latency distribution for each workload (CFS vs SchedCP)
3. Design iteration timeline (RocksDB v1-v7) showing P99.9 progression
4. Policy regime decision tree
5. BPF template structure diagram

### Tables
1. End-to-end results summary (Section 6.2)
2. Per-workload detailed results (6.3)
3. Design iteration history (6.4.3)
4. Comparison with prior systems (Section 8)
5. Thread classification accuracy (extraction validation)

### Key Graphs to Generate
- [ ] RocksDB: P50 vs P99.9 Pareto curve across v1-v7 designs
- [ ] Nginx: CFS vs nginx_aware CDF overlay (showing tail compression)
- [ ] Redis: RPS + P99 bar chart (CFS vs redis_aware)
- [ ] Overhead breakdown: per-event BPF cost with/without task local storage
- [ ] Sensitivity: P99 improvement vs. oversubscription ratio (sweep stress-ng workers)
