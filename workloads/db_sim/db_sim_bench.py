#!/usr/bin/env python3
"""
db_sim benchmark: Compare query latency under CFS vs db_aware scheduler.

Runs db_sim under each scheduler configuration and generates comparison
results (JSON + chart).
"""

import subprocess
import time
import json
import os
import sys
import signal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True
).strip()

DB_SIM = os.path.join(SCRIPT_DIR, "db_sim")
DB_AWARE_BPF = os.path.join(SCRIPT_DIR, "db_aware.bpf.o")
LOADER = os.path.join(PROJECT_ROOT, "bpf_loader", "loader")
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# db_sim parameters
QUERY_THREADS = 8
COMPACT_THREADS = 24  # oversubscribed on 16 CPUs for dramatic effect
DURATION = 15
SLEEP_US = 2000


def run_db_sim():
    """Run db_sim and return parsed JSON output."""
    cmd = [
        DB_SIM,
        "-q", str(QUERY_THREADS),
        "-c", str(COMPACT_THREADS),
        "-d", str(DURATION),
        "-s", str(SLEEP_US),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DURATION + 30
        )
        if proc.returncode != 0:
            print(f"  db_sim failed: {proc.stderr[:200]}")
            return None
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"  Failed to parse JSON: {e}")
        print(f"  stdout: {proc.stdout[:300]}")
        return None
    except Exception as e:
        print(f"  Error running db_sim: {e}")
        return None


def start_custom_scheduler():
    """Start db_aware custom scheduler via loader. Returns process or None."""
    if not os.path.exists(DB_AWARE_BPF):
        print(f"  BPF object not found: {DB_AWARE_BPF}")
        return None
    if not os.path.exists(LOADER):
        print(f"  Loader not found: {LOADER}")
        return None

    print("  Starting db_aware scheduler...")
    proc = subprocess.Popen(
        ["sudo", LOADER, DB_AWARE_BPF],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )
    time.sleep(3)

    if proc.poll() is not None:
        stderr = proc.stderr.read().decode()
        print(f"  Scheduler exited early: {stderr[:200]}")
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
    """Run a single test configuration."""
    sched_proc = None
    try:
        if start_fn:
            sched_proc = start_fn()
            if sched_proc is None:
                return None

        print(f"  Running db_sim ({DURATION}s)...")
        result = run_db_sim()
        return result
    finally:
        if sched_proc:
            print(f"  Stopping scheduler...")
            stop_scheduler(sched_proc)


def print_table(all_results):
    """Print a comparison table."""
    print("\n" + "=" * 85)
    print(f"{'Config':<20} {'Avg':>10} {'p50':>10} {'p99':>10} {'Max':>10} {'Compact ops/s':>15}")
    print(f"{'':20} {'(us)':>10} {'(us)':>10} {'(us)':>10} {'(us)':>10} {'':>15}")
    print("-" * 85)

    for name, res in all_results.items():
        if res is None:
            print(f"{name:<20} {'FAILED':>10}")
            continue
        ql = res["query_latency_us"]
        ct = res["compaction_throughput"]
        print(f"{name:<20} {ql['avg']:>10.1f} {ql['p50']:>10.1f} "
              f"{ql['p99']:>10.1f} {ql['max']:>10.1f} {ct['ops_per_sec']:>15.0f}")

    print("=" * 85)


def generate_chart(all_results):
    """Generate comparison bar chart."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib not available, skipping chart generation")
        return

    names = []
    avg_lat = []
    p50_lat = []
    p99_lat = []
    max_lat = []
    throughput = []

    for name, res in all_results.items():
        if res is None:
            continue
        names.append(name)
        ql = res["query_latency_us"]
        avg_lat.append(ql["avg"])
        p50_lat.append(ql["p50"])
        p99_lat.append(ql["p99"])
        max_lat.append(ql["max"])
        throughput.append(res["compaction_throughput"]["ops_per_sec"])

    if len(names) < 2:
        print("Not enough results for chart")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(
        f"db_sim Scheduler Comparison ({QUERY_THREADS}q + {COMPACT_THREADS}c threads)",
        fontsize=14, fontweight="bold",
    )

    x = np.arange(len(names))
    w = 0.2

    # Query latency
    ax = axes[0]
    ax.bar(x - w * 1.5, avg_lat, w, label="avg", color="#4C72B0", alpha=0.85)
    ax.bar(x - w * 0.5, p50_lat, w, label="p50", color="#55A868", alpha=0.85)
    ax.bar(x + w * 0.5, p99_lat, w, label="p99", color="#DD8452", alpha=0.85)
    ax.bar(x + w * 1.5, max_lat, w, label="max", color="#C44E52", alpha=0.85)
    ax.set_ylabel("Query Latency (us)")
    ax.set_title("Query Latency (lower is better)")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Compaction throughput
    ax = axes[1]
    colors = ["#4C72B0", "#55A868", "#DD8452"][:len(names)]
    bars = ax.bar(x, throughput, color=colors, alpha=0.85)
    ax.set_ylabel("Compaction Throughput (ops/s)")
    ax.set_title("Compaction Throughput (higher is better)")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15, ha="right")
    ax.grid(axis="y", alpha=0.3)
    for bar, val in zip(bars, throughput):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height(),
            f"{val:.0f}", ha="center", va="bottom", fontsize=9,
        )

    plt.tight_layout()
    chart_path = os.path.join(RESULTS_DIR, "db_sim_comparison.png")
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to: {chart_path}")


def main():
    if not os.path.exists(DB_SIM):
        print(f"Error: db_sim binary not found at {DB_SIM}")
        print("Run 'make' first to build.")
        sys.exit(1)

    configs = [
        ("CFS (default)", None),
        ("db_aware", start_custom_scheduler),
    ]

    print("=" * 60)
    print("  db_sim Scheduler Benchmark")
    print(f"  Query threads: {QUERY_THREADS} | Compact threads: {COMPACT_THREADS}")
    print(f"  Duration: {DURATION}s | Sleep: {SLEEP_US}us")
    print("=" * 60)

    all_results = {}

    for i, (label, start_fn) in enumerate(configs):
        print(f"\n[{i+1}/{len(configs)}] Testing {label}...")
        result = run_test(label, start_fn)
        all_results[label] = result
        if result:
            ql = result["query_latency_us"]
            print(f"  Query p99: {ql['p99']:.1f}us, avg: {ql['avg']:.1f}us")

    # Save JSON results
    json_path = os.path.join(RESULTS_DIR, "db_sim_results.json")
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {json_path}")

    # Print comparison table
    print_table(all_results)

    # Generate chart
    generate_chart(all_results)


if __name__ == "__main__":
    main()
