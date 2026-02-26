#!/usr/bin/env python3
"""
RocksDB scheduler A/B benchmark: CFS vs rocksdb_aware.

Runs db_bench readwhilewriting under each scheduler and compares
read latency (micros/op) and throughput (ops/sec).

Workload: fillrandom to populate DB, then readwhilewriting with
multiple reader threads + writer triggering compaction.
"""

import subprocess
import time
import json
import os
import sys
import re
import signal
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True
).strip()

DB_BENCH = os.path.join(SCRIPT_DIR, "rocksdb", "db_bench")
ROCKSDB_AWARE_BPF = os.path.join(SCRIPT_DIR, "rocksdb_aware.bpf.o")
LOADER = os.path.join(PROJECT_ROOT, "bpf_loader", "loader")
SCHED_BIN = os.path.expanduser("~/.schedcp/scxbin")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
DB_PATH = "/tmp/rocksdb_bench_data"
os.makedirs(RESULTS_DIR, exist_ok=True)

# Benchmark parameters
NUM_KEYS = 5_000_000       # keys to populate
VALUE_SIZE = 256           # bytes per value
DURATION = 30              # seconds for readwhilewriting
READ_THREADS = 8           # reader threads (foreground)
# RocksDB compaction threads set via max_background_compactions


def cleanup_db():
    """Remove and recreate the DB directory."""
    if os.path.exists(DB_PATH):
        shutil.rmtree(DB_PATH)
    os.makedirs(DB_PATH, exist_ok=True)


def populate_db():
    """Fill the database with random data to create compaction pressure."""
    print("  Populating database...")
    cmd = [
        DB_BENCH,
        f"--db={DB_PATH}",
        "--benchmarks=fillrandom",
        f"--num={NUM_KEYS}",
        f"--value_size={VALUE_SIZE}",
        "--disable_wal=false",
        "--max_background_compactions=4",
        "--max_background_flushes=2",
        "--compression_type=snappy",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        print(f"  ERROR populating DB: {proc.stderr[:300]}")
        return False
    print("  Database populated.")
    return True


def run_readwhilewriting():
    """Run readwhilewriting benchmark, return raw output."""
    cmd = [
        DB_BENCH,
        f"--db={DB_PATH}",
        "--benchmarks=readwhilewriting",
        "--use_existing_db=true",
        f"--num={NUM_KEYS}",
        f"--duration={DURATION}",
        f"--threads={READ_THREADS}",
        f"--value_size={VALUE_SIZE}",
        "--max_background_compactions=8",
        "--max_background_flushes=2",
        "--statistics=true",
        "--histogram=true",
        "--compression_type=snappy",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DURATION + 60
        )
        output = proc.stdout + "\n" + proc.stderr
        return output, proc.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1
    except Exception as e:
        return str(e), -1


def parse_db_bench_output(output):
    """Parse db_bench output for key metrics."""
    result = {
        "micros_per_op": None,
        "ops_per_sec": None,
        "p50_us": None,
        "p99_us": None,
        "p999_us": None,
        "max_us": None,
    }

    # Parse the summary line: "readwhilewriting : X.XXX micros/op NNNNN ops/sec"
    summary = re.search(
        r"readwhilewriting\s*:\s*([\d.]+)\s*micros/op\s*([\d]+)\s*ops/sec",
        output,
    )
    if summary:
        result["micros_per_op"] = float(summary.group(1))
        result["ops_per_sec"] = int(summary.group(2))

    # Parse histogram percentiles from the rocksdb.db.get.micros section
    # Format: "P50 : X.XXXXXX P95 : X.XXXXXX P99 : X.XXXXXX ..."
    hist_block = re.search(
        r"rocksdb\.db\.get\.micros[^\n]*\n((?:.*\n)*?.*P99\s*:.*)",
        output,
    )
    if hist_block:
        block = hist_block.group(0)
        for label, key in [("P50", "p50_us"), ("P99", "p99_us"),
                           ("P999", "p999_us"), ("Max", "max_us")]:
            m = re.search(rf"{label}\s*:\s*([\d.]+)", block)
            if m:
                result[key] = float(m.group(1))

    # Fallback: try parsing per-thread latency line if histogram not found
    if result["p99_us"] is None:
        # Try "Percentiles: P50: X.XX P95: X.XX P99: X.XX P99.9: X.XX P99.99: X.XX"
        pct_line = re.search(
            r"P50:\s*([\d.]+).*?P99:\s*([\d.]+).*?P99\.9:\s*([\d.]+)",
            output,
        )
        if pct_line:
            result["p50_us"] = float(pct_line.group(1))
            result["p99_us"] = float(pct_line.group(2))
            result["p999_us"] = float(pct_line.group(3))

    return result


def start_custom_scheduler():
    """Start rocksdb_aware scheduler via loader."""
    if not os.path.exists(ROCKSDB_AWARE_BPF):
        print(f"  BPF object not found: {ROCKSDB_AWARE_BPF}")
        return None
    if not os.path.exists(LOADER):
        print(f"  Loader not found: {LOADER}")
        return None

    print("  Starting rocksdb_aware scheduler...")
    proc = subprocess.Popen(
        ["sudo", LOADER, ROCKSDB_AWARE_BPF],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )
    time.sleep(3)
    if proc.poll() is not None:
        stderr = proc.stderr.read().decode()
        print(f"  Scheduler failed: {stderr[:200]}")
        return None
    return proc


def start_builtin_scheduler(name):
    """Start a built-in scx scheduler."""
    sched_bin = os.path.join(SCHED_BIN, name)
    if not os.path.exists(sched_bin):
        print(f"  Binary not found: {sched_bin}")
        return None

    print(f"  Starting {name}...")
    proc = subprocess.Popen(
        ["sudo", sched_bin],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )
    time.sleep(3)
    if proc.poll() is not None:
        stderr = proc.stderr.read().decode()
        print(f"  Scheduler failed: {stderr[:200]}")
        return None
    return proc


def stop_scheduler(proc):
    """Stop a scheduler process."""
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=3)
            except Exception:
                pass
    time.sleep(2)


def run_test(label, start_fn=None):
    """Run a single test: populate DB, start scheduler, benchmark, stop."""
    cleanup_db()
    if not populate_db():
        return None

    sched_proc = None
    try:
        if start_fn:
            sched_proc = start_fn()
            if sched_proc is None:
                return None

        print(f"  Running readwhilewriting ({DURATION}s, {READ_THREADS} threads)...")
        output, rc = run_readwhilewriting()
        if rc != 0 and "TIMEOUT" not in output:
            print(f"  db_bench failed (rc={rc})")
            print(f"  Output: {output[:300]}")
        result = parse_db_bench_output(output)
        result["raw_output_tail"] = output[-500:] if output else ""
        return result
    finally:
        if sched_proc:
            print("  Stopping scheduler...")
            stop_scheduler(sched_proc)


def print_table(all_results):
    """Print comparison table."""
    print("\n" + "=" * 90)
    print(f"{'Config':<20} {'us/op':>10} {'ops/sec':>12} {'p50 (us)':>10} "
          f"{'p99 (us)':>10} {'p99.9 (us)':>12} {'max (us)':>10}")
    print("-" * 90)

    for name, res in all_results.items():
        if res is None:
            print(f"{name:<20} {'FAILED':>10}")
            continue
        usop = f"{res['micros_per_op']:.1f}" if res['micros_per_op'] else "-"
        ops = f"{res['ops_per_sec']:,}" if res['ops_per_sec'] else "-"
        p50 = f"{res['p50_us']:.1f}" if res['p50_us'] else "-"
        p99 = f"{res['p99_us']:.1f}" if res['p99_us'] else "-"
        p999 = f"{res['p999_us']:.1f}" if res['p999_us'] else "-"
        mx = f"{res['max_us']:.1f}" if res['max_us'] else "-"
        print(f"{name:<20} {usop:>10} {ops:>12} {p50:>10} {p99:>10} {p999:>12} {mx:>10}")

    print("=" * 90)


def generate_chart(all_results):
    """Generate comparison chart."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib not available, skipping chart")
        return

    names = []
    ops_sec = []
    p99_vals = []
    usop_vals = []

    for name, res in all_results.items():
        if res is None or res["ops_per_sec"] is None:
            continue
        names.append(name)
        ops_sec.append(res["ops_per_sec"])
        p99_vals.append(res.get("p99_us") or 0)
        usop_vals.append(res["micros_per_op"])

    if len(names) < 2:
        return

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle(
        f"RocksDB readwhilewriting: Scheduler Comparison ({READ_THREADS} threads, {DURATION}s)",
        fontsize=13, fontweight="bold",
    )

    x = np.arange(len(names))
    colors = ["#4C72B0", "#55A868", "#DD8452"][:len(names)]

    # ops/sec
    ax = axes[0]
    bars = ax.bar(x, ops_sec, color=colors, alpha=0.85)
    ax.set_ylabel("Throughput (ops/sec)")
    ax.set_title("Throughput (higher is better)")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.grid(axis="y", alpha=0.3)
    for bar, val in zip(bars, ops_sec):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{val:,}", ha="center", va="bottom", fontsize=8)

    # micros/op
    ax = axes[1]
    bars = ax.bar(x, usop_vals, color=colors, alpha=0.85)
    ax.set_ylabel("Latency (us/op)")
    ax.set_title("Avg Latency (lower is better)")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.grid(axis="y", alpha=0.3)

    # p99
    ax = axes[2]
    bars = ax.bar(x, p99_vals, color=colors, alpha=0.85)
    ax.set_ylabel("p99 Latency (us)")
    ax.set_title("p99 Latency (lower is better)")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    chart_path = os.path.join(RESULTS_DIR, "rocksdb_sched_comparison.png")
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to: {chart_path}")


def main():
    if not os.path.exists(DB_BENCH):
        print(f"Error: db_bench not found at {DB_BENCH}")
        print("Run 'make build' in workloads/rocksdb/ first.")
        sys.exit(1)

    configs = [
        ("CFS (default)", None),
        ("scx_bpfland", lambda: start_builtin_scheduler("scx_bpfland")),
        ("rocksdb_aware", start_custom_scheduler),
    ]

    print("=" * 60)
    print("  RocksDB Scheduler A/B Benchmark")
    print(f"  Keys: {NUM_KEYS:,} | Threads: {READ_THREADS} | Duration: {DURATION}s")
    print(f"  Workload: readwhilewriting (reads + writes + compaction)")
    print("=" * 60)

    all_results = {}

    for i, (label, start_fn) in enumerate(configs):
        print(f"\n[{i+1}/{len(configs)}] Testing {label}...")
        result = run_test(label, start_fn)
        all_results[label] = result
        if result and result["ops_per_sec"]:
            print(f"  Result: {result['ops_per_sec']:,} ops/sec, "
                  f"{result['micros_per_op']:.1f} us/op")

    # Save results
    json_path = os.path.join(RESULTS_DIR, "rocksdb_sched_results.json")
    # Strip raw output for clean JSON
    save_results = {}
    for k, v in all_results.items():
        if v:
            save_results[k] = {key: val for key, val in v.items()
                               if key != "raw_output_tail"}
        else:
            save_results[k] = None
    with open(json_path, "w") as f:
        json.dump(save_results, f, indent=2)
    print(f"\nResults saved to: {json_path}")

    print_table(all_results)
    generate_chart(all_results)


if __name__ == "__main__":
    main()
