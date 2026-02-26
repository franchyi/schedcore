# SchedCP: Future Plan and Extension Trajectory
**Goal:** Elevate SchedCP from a promising prototype to a top-tier systems conference submission (OSDI, SOSP, EuroSys, NSDI) by moving from manual, human-in-the-loop BPF authorship to a fully automated, dynamic, and safe kernel scheduling synthesis framework.

This document outlines the concrete technical roadmap to address the "Honest Status Assessment" gap and introduce novel systems-level contributions.

---

## 1. Close the Loop: Fully Automated BPF Synthesis & Agentic Feedback (The "Must-Have")
Currently, the LLM pipeline stops at the Thread Manifest JSON, and the BPF schedulers are hand-authored. A true "LLM-Synthesized" system requires end-to-end automation.

**Action Items:**
- **Hybrid Semantic-Structural Classification (The Two-Step Extract & Parse Method):**
  1. **Step 1 (Deterministic Extraction):** Use deterministic program analysis tools (like Tree-sitter for static AST call-graphs, or eBPF for dynamic request tracing) to automatically extract hard structural facts about a thread. For example, identify exactly which threads invoke `send()` or `recv()` on the critical path, or which threads are spun up from `pthread_create` and have zero network I/O. Package these structural metrics and the associated source code entry point into a "Systematic Thread Dossier."
  2. **Step 2 (LLM Semantic Handoff):** Feed the Systematic Thread Dossier into the LLM. Rather than having the LLM guess based on naming conventions, the LLM uses the hard structural facts to perform semantic synthesis: *"Does this thread's source code indicate it blocks a user-facing request?"*. The LLM then rigorously classifies the thread into objective categories based on the **User Request Critical Path**: 
     - **Foreground:** Synchronous threads executing on the critical path of user request processing.
     - **Background:** Asynchronous, deferred, or periodic threads operating outside the critical path.
- **Parameterized BPF Templates Compiler:** Build a code generator (Stage 2) that consumes the LLM's classification and injects it into pre-verified BPF C templates. The LLM will no longer write arbitrary C code, but rather populate a structured BPF template.
- **Automated Policy Regime Selection:** Implement a heuristic or ML-driven decision engine that automatically selects the appropriate scheduling topology (*Asymmetric Deprioritization*, *Selective Preemption*, or *External Isolation*) based on workload characteristics rather than human intuition.
- **Agentic Feedback Loop (Closed-Loop Tuning):** Build an orchestrator that executes the entire cycle: Generate & compile -> Hot-load -> Run benchmark -> Observe tail latency -> Adjust BPF parameters -> Re-deploy.

## 2. Dynamic Behavioral Profiling (Beyond Source Code)
Relying solely on static analysis of `pthread_setname_np` or C/C++ ASTs is brittle. Many modern runtimes (Go, Rust, JVM) or legacy applications do not cleanly name their OS threads.

**Action Items:**
- **Runtime Heuristic Discovery:** Develop a lightweight, passive BPF profiler that runs for 60 seconds to observe thread behavior (e.g., sleep/wake patterns, system call frequencies, CPU burst durations) *before* generating the scheduler.
- **Behavioral Signatures:** Use these runtime metrics to supplement static analysis. For example, identify that "Thread A spends 90% of its time in `epoll_wait` (Foreground/I/O), while Thread B spends 99% of its time in CPU-bound user-space loops (Background/Compaction)."
- **Hybrid Semantic Model:** Combine the static source code context with dynamic runtime profiles to create a universally applicable thread classification system, drastically increasing the system's robustness and applicability.

### Implementation Guide: Dynamic Behavioral Profiling

To implement Dynamic Behavioral Profiling, the goal is to observe what a thread *actually does* at runtime rather than relying on what the developer named it in the source code. This is crucial for applications that don't name their threads or for detecting when a thread's behavior changes. This can be achieved by writing a lightweight eBPF profiler that runs in the background for a short window (e.g., 10–60 seconds), collects behavioral metrics per thread (TID), and then classifies them.

#### Step 1: Define the "Features" of a Thread
To classify a thread as Foreground (Latency-Critical) vs. Background (Throughput/Batch), specific metrics must be collected:
*   **Foreground (e.g., Nginx worker, Redis event loop):** 
    *   **Behavior:** Spends most of its time asleep waiting for network I/O. When it wakes up, it executes a very short, fast CPU burst to process the request, then goes back to sleep.
    *   **Syscalls:** Heavy use of `epoll_wait`, `read`, `write`, `sendmsg`, `recvmsg`.
*   **Background (e.g., RocksDB compaction, garbage collection):**
    *   **Behavior:** CPU-bound. Uses up its entire scheduler timeslice (e.g., 4-5ms) without sleeping, or it does heavy, blocking disk I/O.
    *   **Syscalls:** Heavy use of `pwrite`, `fsync`, or compute-heavy loops with almost no syscalls.

#### Step 2: The eBPF Instrumentation (Kernel-Space)
Write an eBPF program that hooks into kernel tracepoints to gather metrics securely and with very low overhead.

**Key Hook Points:**
1.  **`tracepoint:sched:sched_switch`**: 
    *   Fires every time a thread is scheduled on or off a CPU.
    *   **What to measure:** Calculate the *CPU Burst Time* (time from schedule-in to schedule-out). If a thread constantly uses its full timeslice, it's likely a background compute thread.
2.  **`tracepoint:sched:sched_wakeup`**:
    *   Fires when a sleeping thread is woken up.
    *   **What to measure:** Calculate the *Sleep Time* (time from schedule-out to wakeup). Also, track *who* woke it up. If a hardware interrupt (network card) wakes the thread, it's highly likely to be a foreground thread.
3.  **`tracepoint:raw_syscalls:sys_enter`**:
    *   Fires on every system call.
    *   **What to measure:** Maintain a histogram of syscall types per TID. Group them into buckets: Network I/O, Disk I/O, Synchronization (futex), etc.

**BPF Maps Structure:**
Store this state in a BPF Hash Map where the key is the `TID` (Thread ID) and the value is a struct:
```c
struct thread_metrics {
    u64 total_run_time;
    u64 total_sleep_time;
    u64 num_cpu_bursts;
    u64 max_cpu_burst;
    u64 network_syscalls;
    u64 disk_syscalls;
};
```

#### Step 3: The Classification Engine (User-Space)
After running the eBPF profiler for 60 seconds, a user-space daemon reads the BPF map and extracts the feature vector for every TID. Threads can be classified using one of three approaches:

1.  **Heuristics (Simplest):**
    *   *Rule 1:* If `(total_run_time / num_cpu_bursts) > 2ms` and `disk_syscalls > 100`, mark as **BACKGROUND** (Compaction/Batch).
    *   *Rule 2:* If `total_sleep_time >> total_run_time` and `network_syscalls > 1000`, mark as **FOREGROUND** (Event loop).
2.  **Unsupervised Machine Learning:**
    *   Feed the metrics (Run/Sleep ratio, Network/Disk ratio) into a K-Means clustering algorithm ($k=2$ or $3$). It will naturally group latency-sensitive threads together and batch threads together.
3.  **LLM-Assisted:**
    *   Format the metrics into a JSON profile and pass it to an LLM: *"Here is the runtime behavior of 40 threads belonging to PID 1234. Which ones are the latency-critical foreground threads?"*

#### Step 4: Integration into SchedCP
Once the user-space engine outputs the classification, it generates the **Thread Manifest**. Instead of generating a BPF scheduler that uses string comparison (`strncmp("rocksdb:low")`), a scheduler is generated that uses the exact TIDs or behavioral profiles to route them to the `BACKGROUND_DSQ` or `FOREGROUND_DSQ`. 

*(Note: Because TIDs change when threads restart, the profiler needs to run periodically, or the profile can be used to learn the thread creation patterns to catch new threads as they spawn).*

## 3. Application-Semantic Priority Inheritance via USDT and Resource Monitoring (The "Hard Systems Problem")
A fundamental critique of deprioritizing background threads is **Priority Inversion**. In modern, highly optimized databases, this rarely manifests as standard `pthread_mutex` contention (which a naive `futex` BPF hook might catch). Instead, it appears as application-specific lock contention or shared resource exhaustion. For example:
- **RocksDB:** Compaction threads acquire a global `DBMutex` to install new SST files. If starved while holding this, foreground `Put()` operations block.
- **PostgreSQL:** Background `bgwriter` processes hold custom spinlocks (LWLocks) on buffer partitions. If deprioritized, foreground query backends spin and stall.
- **Redis:** Background persistence (`BGSAVE` or AOF rewrite) saturates I/O bandwidth, causing the latency-critical foreground event loop to fall into uninterruptible sleep (`iowait`) inside the kernel.

**Action Items:**
- **USDT & Custom Tracepoint Hooks:** The LLM will analyze application source code to identify specific synchronization primitives (e.g., RocksDB's `DBMutex`, PostgreSQL's LWLocks) and generate a BPF scheduler that attaches to the application's native USDT (Userland Statically Defined Tracing) probes (e.g., `rocksdb:mutex_wait_start` or `postgresql:lwlock_wait_start`).
- **I/O Starvation Throttling:** For single-threaded event loops like Redis, the BPF scheduler will monitor kernel I/O wait states (`tracepoint:sched:sched_stat_iowait`). If a foreground thread blocks on I/O, the scheduler will dynamically throttle background I/O submission rates to unblock the hot path.
- **Dynamic Boosting:** When application-specific contention is detected via these advanced hooks, the BPF scheduler dynamically boosts the blocking background thread to the `FOREGROUND_DSQ` (fast path) until the resource is released.
- **Contribution:** Demonstrating that an LLM can analyze application semantics to automatically wire up USDT-driven priority inheritance and I/O throttling within a programmable kernel scheduler (`sched-ext`) represents a massive, novel technical contribution.

## 4. Formalize the "BPF Scheduling Cost Model"
Top-tier systems papers require rigorous evaluation of trade-offs and fundamental limits, not just empirical performance improvements. SchedCP's cost model proves mathematically *why* and *when* different BPF scheduling topologies (Regimes) are optimal.

### Implementation Guide: The BPF Scheduling Cost Model

#### Step 1: Deconstruct the Per-Event BPF Overhead ($O_{bpf}$)
Every time a thread wakes up or goes to sleep, `sched-ext` calls the BPF program. This path introduces measurable overhead:
*   **$C_{ctx}$ (Context Setup):** The baseline cost of transitioning from the kernel scheduling core into the eBPF VM.
*   **$C_{map}$ (Classification/Map Lookup):** The cost to look up the thread's classification in a BPF map (e.g., `BPF_MAP_TYPE_TASK_STORAGE` or a hash map).
*   **$C_{lock}$ (DSQ Lock Contention):** If a thread is routed to a custom Dispatch Queue (DSQ), `sched-ext` must acquire a global spinlock. As core count scales, this lock contention grows non-linearly.
*   **$C_{ipi}$ (Preemption Kick):** The cost of issuing an Inter-Processor Interrupt (`SCX_KICK_PREEMPT`) to force a CPU to reschedule.

**Total Dispatch Overhead ($O_{dispatch}$):**
$$O_{dispatch} = C_{ctx} + C_{map} + C_{lock} + (P_{kick} \times C_{ipi})$$
*(Where $P_{kick}$ is the probability a preemption kick is needed).*

#### Step 2: Model the Waiting Time ($W$)
The latency of a foreground request ($L_{fg}$) is its actual execution time ($S$) plus the time it spends waiting in a runqueue ($W$), plus the scheduling overhead ($O_{dispatch}$):
$$L_{fg} = S + W + O_{dispatch}$$

**Under Default CFS:**
*   $O_{dispatch} \approx 0$ (highly optimized C code, per-CPU lockless queues).
*   $W_{cfs}$ depends heavily on contention. If a foreground thread wakes up on a CPU where a background thread is running, it must wait for the background thread's timeslice ($T_{bg}$).
*   Expected worst-case wait: $W_{cfs\_worst} \approx T_{bg}$ (e.g., 4-5ms).

**Under SchedCP (Regime 2 - Selective Preemption):**
*   $W$ is minimized because the foreground thread is placed in a high-priority queue and preempts the background thread.
*   $W_{schedcp\_worst} \approx C_{ipi} + C_{ctx}$ (just the time to interrupt and switch).
*   *But*, SchedCP pays a higher $O_{dispatch}$ on *every single scheduling event*, even when there is no contention.

#### Step 3: Formulate the Trade-off Inequality
This model mathematically defines the exact boundary of when SchedCP is beneficial. SchedCP improves latency when the time saved by avoiding CFS contention is greater than the cumulative BPF overhead added to the fast path.

**The "Do No Harm" Threshold (Why naive dual-queues fail):**
In low-contention workloads (like RocksDB `readrandom` with a large cache), threads rarely block, and $W_{cfs} \approx 0$.
If a naive dual-queue BPF scheduler is used, latency becomes:
$$L_{schedcp} = S + 0 + O_{dispatch}$$
Because $O_{dispatch}$ (specifically the global $C_{lock}$) is non-zero, $L_{schedcp} > L_{cfs}$. **This mathematically proves why v1-v4 designs caused a 400% latency regression.**

**The Asymmetric Principle (Regime 1):**
To fix the above, Regime 1 routes foreground threads directly to the kernel's lockless `SCX_DSQ_GLOBAL` or `SCX_DSQ_LOCAL`.
*   Foreground $O_{dispatch} = C_{ctx} + C_{map}$ (no $C_{lock}$).
*   By using Task Local Storage ($C_{map} \approx O(1)$ cache hit), the overhead drops to ~1-2 microseconds, eliminating the P50 regression while isolating background threads.

**The Contention Threshold (Regime 2/3):**
Under high contention (RocksDB stress workload), $W_{cfs}$ spikes to multi-milliseconds.
$$W_{cfs} \gg O_{dispatch}$$
Here, paying 5 microseconds of $O_{dispatch}$ to save 5,000 microseconds of $W_{cfs}$ is a massive win, resulting in 67-87% P99.9 reductions.

**Action Items:**
- **Microbenchmark the Primitives:** Write a minimal `sched-ext` scheduler to measure the raw cost of $C_{ctx}$, $C_{map}$, and $C_{lock}$ across different CPU core counts.
- **Plot the "Cost Surface":** Create a 3D plot mapping Contention Level (X-axis) against BPF Overhead (Y-axis) to show Foreground P99 Latency (Z-axis).
- **Define the Automaton:** SchedCP's Agentic Feedback Loop will use the inequality to automatically select regimes:
    *   *If Application Contention Delay > BPF Custom Queue Overhead -> Select Regime 2.*
    *   *If Application Contention Delay < BPF Custom Queue Overhead -> Select Regime 1.*