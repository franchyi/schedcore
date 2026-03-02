#!/usr/bin/env python3
"""
Stage 1c: Dynamic eBPF Thread Behavior Profiler

Supplements static analysis (Stage 1a) by observing what threads actually do
at runtime. Useful for applications without pthread_setname_np (Go goroutines,
JVM pools, legacy C) where static analysis cannot discover thread names.

Attaches BPF tracepoints to measure per-thread:
  - CPU burst time (on-CPU duration per wake)
  - Sleep duration and wakeup frequency
  - Syscall type histogram (network vs disk vs sync)

Classifies threads by behavioral pattern and outputs a Thread Manifest JSON
compatible with the rest of the pipeline (Stage 2/3/4).

Requires: BCC (bpfcc-tools), root privileges, Linux 5.8+

Usage:
  # Profile by PID for 30 seconds
  sudo python3 stage1c_dynamic_profiler.py --pid <pid> --duration 30

  # Profile by comm name pattern
  sudo python3 stage1c_dynamic_profiler.py --comm "redis" --duration 30

  # Output to file
  sudo python3 stage1c_dynamic_profiler.py --pid <pid> --duration 30 --output results/profile.json

  # Include application metadata for manifest
  sudo python3 stage1c_dynamic_profiler.py --pid <pid> --duration 30 \\
      --app-name redis --source-path workloads/redis/redis-src/
"""

import argparse
import ctypes
import json
import os
import signal
import sys
import time

# ── BPF program ──────────────────────────────────────────────────────────────

BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>
#include <linux/sched.h>

struct thread_metrics {
    u64 total_run_ns;
    u64 total_sleep_ns;
    u64 num_wakeups;
    u64 max_run_ns;
    u64 network_syscalls;
    u64 disk_syscalls;
    u64 sync_syscalls;
    u64 last_switch_ns;
    u32 tgid;
    char comm[16];
};

BPF_HASH(metrics, u32, struct thread_metrics, 4096);

// Filter parameters (set from Python)
BPF_ARRAY(filter_pid, u32, 1);     // 0 = no filter
BPF_ARRAY(filter_tgid, u32, 1);    // 0 = no filter

static inline bool should_trace(u32 pid, u32 tgid) {
    int key = 0;
    u32 *fpid = filter_pid.lookup(&key);
    if (fpid && *fpid != 0) {
        return tgid == *fpid;
    }
    // If no PID filter, trace everything (comm filter done in Python)
    return true;
}

// sched_switch: measure on-CPU duration for prev, record off-CPU start for next
TRACEPOINT_PROBE(sched, sched_switch) {
    u64 now = bpf_ktime_get_ns();
    u32 prev_pid = args->prev_pid;
    u32 next_pid = args->next_pid;

    // Record run duration for prev task
    if (prev_pid > 0) {
        struct thread_metrics *m = metrics.lookup(&prev_pid);
        if (m && m->last_switch_ns > 0) {
            u64 run_ns = now - m->last_switch_ns;
            m->total_run_ns += run_ns;
            if (run_ns > m->max_run_ns)
                m->max_run_ns = run_ns;
        }
    }

    // Record schedule-in time for next task
    if (next_pid > 0) {
        u32 tgid = bpf_get_current_pid_tgid() >> 32;
        struct thread_metrics *m = metrics.lookup(&next_pid);
        if (m) {
            m->last_switch_ns = now;
        } else if (should_trace(next_pid, tgid)) {
            struct thread_metrics new_m = {};
            new_m.last_switch_ns = now;
            new_m.tgid = tgid;
            bpf_get_current_comm(&new_m.comm, sizeof(new_m.comm));
            metrics.update(&next_pid, &new_m);
        }
    }

    return 0;
}

// sched_wakeup: measure sleep duration
TRACEPOINT_PROBE(sched, sched_wakeup) {
    u32 pid = args->pid;
    u64 now = bpf_ktime_get_ns();

    struct thread_metrics *m = metrics.lookup(&pid);
    if (m) {
        m->num_wakeups += 1;
        if (m->last_switch_ns > 0) {
            u64 sleep_ns = now - m->last_switch_ns;
            // Only count as sleep if it looks like the task was off-CPU
            // (last_switch_ns was set when it was switched out)
            m->total_sleep_ns += sleep_ns;
        }
    }
    return 0;
}

// Syscall enter: categorize by type
TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
    u64 pid_tgid = bpf_get_current_pid_tgid();
    u32 pid = pid_tgid;
    u32 tgid = pid_tgid >> 32;

    if (!should_trace(pid, tgid))
        return 0;

    struct thread_metrics *m = metrics.lookup(&pid);
    if (!m)
        return 0;

    long syscall_id = args->id;

    // Network syscalls (x86_64 numbers)
    // accept=43, connect=42, sendto=44, recvfrom=45, sendmsg=46, recvmsg=47
    // epoll_wait=232, epoll_pwait=281, read=0, write=1 (ambiguous but common)
    // select=23, poll=7, ppoll=271
    if (syscall_id == 232 || syscall_id == 281 ||  // epoll_wait, epoll_pwait
        syscall_id == 43 || syscall_id == 42 ||     // accept, connect
        syscall_id == 44 || syscall_id == 45 ||     // sendto, recvfrom
        syscall_id == 46 || syscall_id == 47 ||     // sendmsg, recvmsg
        syscall_id == 23 || syscall_id == 7 ||      // select, poll
        syscall_id == 271) {                         // ppoll
        m->network_syscalls += 1;
        return 0;
    }

    // Disk syscalls
    // pwrite64=18, pread64=17, fsync=74, fdatasync=75, sync=162
    // io_submit=209, io_uring_enter=426
    if (syscall_id == 17 || syscall_id == 18 ||     // pread64, pwrite64
        syscall_id == 74 || syscall_id == 75 ||     // fsync, fdatasync
        syscall_id == 162 ||                         // sync
        syscall_id == 209 || syscall_id == 426) {    // io_submit, io_uring_enter
        m->disk_syscalls += 1;
        return 0;
    }

    // Sync syscalls
    // futex=202, nanosleep=35, clock_nanosleep=230
    if (syscall_id == 202 || syscall_id == 35 ||    // futex, nanosleep
        syscall_id == 230) {                         // clock_nanosleep
        m->sync_syscalls += 1;
    }

    return 0;
}
"""

# ── Classification heuristics ────────────────────────────────────────────────

def classify_thread(comm, total_run_ns, total_sleep_ns, num_wakeups,
                    max_run_ns, network_syscalls, disk_syscalls, sync_syscalls):
    """Classify a thread based on behavioral metrics.

    Returns: (role, pattern_name, reason)
    """
    total_ns = total_run_ns + total_sleep_ns
    if total_ns == 0 or num_wakeups == 0:
        return "foreground", "idle", "insufficient data (default to foreground for safety)"

    sleep_ratio = total_sleep_ns / total_ns
    avg_burst_ns = total_run_ns / num_wakeups

    # Event loop: mostly sleeping, frequent wakeups, short bursts, network-heavy
    if (sleep_ratio > 0.8 and network_syscalls > 100 and
            avg_burst_ns < 1_000_000):  # < 1ms
        return "foreground", "event_loop", \
            f"sleep_ratio={sleep_ratio:.2f}, network={network_syscalls}, avg_burst={avg_burst_ns/1e6:.2f}ms"

    # I/O worker: moderate sleeping, network activity
    if sleep_ratio > 0.5 and network_syscalls > 50:
        return "foreground", "io_worker", \
            f"sleep_ratio={sleep_ratio:.2f}, network={network_syscalls}"

    # CPU-bound batch: long bursts, disk I/O
    if avg_burst_ns > 2_000_000 and disk_syscalls > 50:  # > 2ms
        return "background", "cpu_batch", \
            f"avg_burst={avg_burst_ns/1e6:.2f}ms, disk={disk_syscalls}"

    # Compaction/GC: very long bursts, mostly running
    if avg_burst_ns > 5_000_000 and sleep_ratio < 0.3:  # > 5ms
        return "background", "compaction", \
            f"avg_burst={avg_burst_ns/1e6:.2f}ms, sleep_ratio={sleep_ratio:.2f}"

    # Default: foreground (safe — don't deprioritize unknown threads)
    return "foreground", "unknown", \
        f"sleep_ratio={sleep_ratio:.2f}, avg_burst={avg_burst_ns/1e6:.2f}ms"


def build_manifest(thread_data, app_name, source_path):
    """Build a Thread Manifest JSON from classified thread data.

    Groups threads by (role, comm_prefix) and deduplicates.
    """
    # Group by comm prefix (strip trailing digits/underscores for grouping)
    groups = {}
    for td in thread_data:
        comm = td["comm"]
        role = td["role"]

        # Find common prefix: strip trailing digits and underscores
        prefix = comm.rstrip("0123456789")
        prefix = prefix.rstrip("_")
        if not prefix:
            prefix = comm

        group_key = (role, prefix)
        if group_key not in groups:
            groups[group_key] = {
                "comms": [],
                "pattern": td["pattern"],
                "reason": td["reason"],
                "role": role,
                "prefix": prefix,
            }
        groups[group_key]["comms"].append(comm)

    threads = []
    for (role, prefix), group in sorted(groups.items()):
        comms = sorted(set(group["comms"]))
        if len(comms) == 1:
            name_pattern = comms[0]
            id_type = "comm_exact"
        else:
            name_pattern = f"{prefix}*"
            id_type = "comm_prefix"

        # Determine comm_prefix for BPF matching
        comm_prefix = prefix
        comm_length = len(comm_prefix)

        threads.append({
            "name_pattern": name_pattern,
            "role": role,
            "purpose": f"Classified by runtime profiling as {group['pattern']} ({group['reason']})",
            "identification": {
                "type": id_type,
                "comm_prefix": comm_prefix,
                "comm_length": comm_length,
                "function_symbol": None,
                "library_path": None,
            }
        })

    bg_threads = [t for t in threads if t["role"] == "background"]
    fg_threads = [t for t in threads if t["role"] == "foreground"]

    manifest = {
        "application": app_name or "unknown",
        "source_path": source_path or "",
        "language": "unknown",
        "identification_method": "comm",
        "default_role": "foreground",
        "rationale": (
            f"Dynamic profiling identified {len(bg_threads)} background thread type(s) "
            f"and {len(fg_threads)} foreground thread type(s) based on CPU burst time, "
            f"sleep ratio, and syscall patterns. Background threads exhibit long CPU "
            f"bursts and/or disk-heavy syscall profiles. Foreground threads show short "
            f"bursts with network-heavy syscall profiles (event loops, I/O workers)."
        ),
        "threads": threads,
    }
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Stage 1c: Dynamic eBPF thread behavior profiler")
    parser.add_argument("--pid", type=int, default=0,
                        help="PID (tgid) of the application to profile")
    parser.add_argument("--comm", type=str, default="",
                        help="Comm name prefix to filter threads (alternative to --pid)")
    parser.add_argument("--duration", type=int, default=30,
                        help="Profiling duration in seconds (default: 30)")
    parser.add_argument("--output", type=str, default="",
                        help="Output file path for manifest JSON")
    parser.add_argument("--app-name", type=str, default="",
                        help="Application name for manifest metadata")
    parser.add_argument("--source-path", type=str, default="",
                        help="Application source path for manifest metadata")
    args = parser.parse_args()

    if args.pid == 0 and args.comm == "":
        print("Error: specify --pid or --comm to filter threads", file=sys.stderr)
        sys.exit(1)

    if os.geteuid() != 0:
        print("Error: must run as root (BPF requires CAP_BPF)", file=sys.stderr)
        sys.exit(1)

    try:
        from bcc import BPF
    except ImportError:
        print("Error: BCC not installed. Install with: apt install bpfcc-tools python3-bpfcc",
              file=sys.stderr)
        sys.exit(1)

    # Load BPF program
    print(f"Loading BPF program...", file=sys.stderr)
    b = BPF(text=BPF_PROGRAM)

    # Set PID filter if specified
    if args.pid > 0:
        filter_pid = b["filter_pid"]
        filter_pid[ctypes.c_int(0)] = ctypes.c_uint32(args.pid)
        print(f"Filtering by PID (tgid): {args.pid}", file=sys.stderr)

    # Profile
    print(f"Profiling for {args.duration} seconds...", file=sys.stderr)

    # Handle SIGINT gracefully
    interrupted = [False]
    def handler(sig, frame):
        interrupted[0] = True
    old_handler = signal.signal(signal.SIGINT, handler)

    start_time = time.time()
    while time.time() - start_time < args.duration and not interrupted[0]:
        time.sleep(0.5)

    signal.signal(signal.SIGINT, old_handler)
    elapsed = time.time() - start_time
    print(f"Profiling complete ({elapsed:.1f}s)", file=sys.stderr)

    # Read BPF map
    metrics = b["metrics"]
    thread_data = []

    for tid, m in metrics.items():
        comm = m.comm.decode("utf-8", errors="replace").rstrip("\x00")

        # Apply comm filter if specified
        if args.comm and not comm.startswith(args.comm):
            # Also check if this thread belongs to a process matching the comm
            # by checking tgid — but we can't easily do that here, so just
            # include all threads when using --comm filter broadly
            if args.pid == 0:
                continue

        if m.total_run_ns == 0 and m.num_wakeups == 0:
            continue

        role, pattern, reason = classify_thread(
            comm, m.total_run_ns, m.total_sleep_ns, m.num_wakeups,
            m.max_run_ns, m.network_syscalls, m.disk_syscalls, m.sync_syscalls)

        thread_data.append({
            "tid": tid.value,
            "tgid": m.tgid,
            "comm": comm,
            "role": role,
            "pattern": pattern,
            "reason": reason,
            "total_run_ms": m.total_run_ns / 1e6,
            "total_sleep_ms": m.total_sleep_ns / 1e6,
            "num_wakeups": m.num_wakeups,
            "max_run_ms": m.max_run_ns / 1e6,
            "avg_burst_ms": (m.total_run_ns / m.num_wakeups / 1e6) if m.num_wakeups > 0 else 0,
            "network_syscalls": m.network_syscalls,
            "disk_syscalls": m.disk_syscalls,
            "sync_syscalls": m.sync_syscalls,
        })

    if not thread_data:
        print("Warning: no thread data collected. Check --pid or --comm filter.", file=sys.stderr)
        sys.exit(1)

    # Print behavioral summary
    print(f"\n{'TID':>7} {'Comm':<16} {'Role':<12} {'Pattern':<14} {'Run(ms)':>9} {'Sleep(ms)':>10} "
          f"{'Wakeups':>8} {'AvgBurst':>9} {'Net':>5} {'Disk':>5} {'Sync':>5}",
          file=sys.stderr)
    print("-" * 120, file=sys.stderr)
    for td in sorted(thread_data, key=lambda x: x["total_run_ms"], reverse=True):
        print(f"{td['tid']:>7} {td['comm']:<16} {td['role']:<12} {td['pattern']:<14} "
              f"{td['total_run_ms']:>9.1f} {td['total_sleep_ms']:>10.1f} "
              f"{td['num_wakeups']:>8} {td['avg_burst_ms']:>8.2f}ms "
              f"{td['network_syscalls']:>5} {td['disk_syscalls']:>5} {td['sync_syscalls']:>5}",
              file=sys.stderr)

    # Build and output manifest
    app_name = args.app_name or args.comm or f"pid_{args.pid}"
    manifest = build_manifest(thread_data, app_name, args.source_path)

    output_json = json.dumps(manifest, indent=2)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output_json + "\n")
        print(f"\nManifest written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)

    # Summary
    bg_count = sum(1 for td in thread_data if td["role"] == "background")
    fg_count = sum(1 for td in thread_data if td["role"] == "foreground")
    print(f"\nClassification: {bg_count} background, {fg_count} foreground "
          f"(out of {len(thread_data)} threads)", file=sys.stderr)


if __name__ == "__main__":
    main()
