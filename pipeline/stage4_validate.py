#!/usr/bin/env python3
"""
Stage 4: Common Validation Harness

Parses existing benchmark results from all workloads into a unified format
and prints a summary comparison table. This is a wrapper that normalizes
existing outputs — not a benchmark rewrite.

Each workload's benchmark script stays as-is (they handle complex setup).
This harness just parses their output.

Usage:
  # Parse a specific workload's results
  python3 stage4_validate.py --workload redis

  # Summary across all workloads
  python3 stage4_validate.py --summary

  # Output JSON
  python3 stage4_validate.py --summary --json
"""

import argparse
import csv
import json
import os
import re
import sys

# Base directory for workloads (relative to this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
WORKLOADS_DIR = os.path.join(PROJECT_DIR, "workloads")


def parse_db_sim(results_dir=None):
    """Parse db_sim results from JSON.

    Expected file: results/db_sim_results.json
    """
    if results_dir is None:
        results_dir = os.path.join(WORKLOADS_DIR, "db_sim", "results")

    path = os.path.join(results_dir, "db_sim_results.json")
    if not os.path.exists(path):
        return None

    with open(path) as f:
        data = json.load(f)

    cfs = data.get("CFS (default)", {})
    custom = data.get("db_aware", {})

    cfs_lat = cfs.get("query_latency_us", {})
    custom_lat = custom.get("query_latency_us", {})
    cfs_tput = cfs.get("compaction_throughput", {}).get("ops_per_sec", 0)
    custom_tput = custom.get("compaction_throughput", {}).get("ops_per_sec", 0)

    return {
        "workload": "db_sim",
        "scheduler": "db_aware",
        "runs": 1,
        "baseline": {
            "throughput": cfs_tput,
            "latency_us": {
                "p50": cfs_lat.get("p50"),
                "p99": cfs_lat.get("p99"),
                "p99.9": None,
                "max": cfs_lat.get("max"),
            },
        },
        "custom": {
            "throughput": custom_tput,
            "latency_us": {
                "p50": custom_lat.get("p50"),
                "p99": custom_lat.get("p99"),
                "p99.9": None,
                "max": custom_lat.get("max"),
            },
        },
    }


def parse_rocksdb(results_dir=None):
    """Parse RocksDB db_bench results from text files.

    Expected files: results/cfs_run{1,2,3}.txt, results/v7_run{1,2,3}.txt
    Each file has lines like:
      readrandomwriterandom : ... ops/sec ...
      Percentiles: P50: 83.01 P75: 106.78 P99: 223.90 P99.9: 3966.30 P99.99: 9975.98
    """
    if results_dir is None:
        results_dir = os.path.join(WORKLOADS_DIR, "rocksdb_dbbench", "results")

    def parse_run(path):
        if not os.path.exists(path):
            return None
        with open(path) as f:
            text = f.read()

        ops_match = re.search(r'(\d+)\s+ops/sec', text)
        ops_sec = int(ops_match.group(1)) if ops_match else 0

        # Parse first Percentiles line (read percentiles)
        pct_matches = re.findall(
            r'Percentiles:\s+P50:\s+([\d.]+)\s+P75:\s+([\d.]+)\s+P99:\s+([\d.]+)\s+P99\.9:\s+([\d.]+)\s+P99\.99:\s+([\d.]+)',
            text)
        if pct_matches:
            p = pct_matches[0]  # First percentile line (read latencies)
            return {
                "ops_sec": ops_sec,
                "p50": float(p[0]),
                "p99": float(p[2]),
                "p99.9": float(p[3]),
                "p99.99": float(p[4]),
            }
        return None

    cfs_runs = []
    custom_runs = []
    for i in range(1, 10):
        r = parse_run(os.path.join(results_dir, f"cfs_run{i}.txt"))
        if r:
            cfs_runs.append(r)
        r = parse_run(os.path.join(results_dir, f"v7_run{i}.txt"))
        if r:
            custom_runs.append(r)

    if not cfs_runs or not custom_runs:
        return None

    def avg_runs(runs):
        n = len(runs)
        return {
            "ops_sec": sum(r["ops_sec"] for r in runs) / n,
            "p50": sum(r["p50"] for r in runs) / n,
            "p99": sum(r["p99"] for r in runs) / n,
            "p99.9": sum(r["p99.9"] for r in runs) / n,
            "p99.99": sum(r["p99.99"] for r in runs) / n,
        }

    cfs_avg = avg_runs(cfs_runs)
    custom_avg = avg_runs(custom_runs)

    return {
        "workload": "rocksdb",
        "scheduler": "rocksdb_v7",
        "runs": min(len(cfs_runs), len(custom_runs)),
        "baseline": {
            "throughput": cfs_avg["ops_sec"],
            "latency_us": {
                "p50": cfs_avg["p50"],
                "p99": cfs_avg["p99"],
                "p99.9": cfs_avg["p99.9"],
                "p99.99": cfs_avg["p99.99"],
            },
        },
        "custom": {
            "throughput": custom_avg["ops_sec"],
            "latency_us": {
                "p50": custom_avg["p50"],
                "p99": custom_avg["p99"],
                "p99.9": custom_avg["p99.9"],
                "p99.99": custom_avg["p99.99"],
            },
        },
    }


def parse_redis(results_dir=None):
    """Parse Redis benchmark results from CSV files.

    Expected files: results/cfs_run{1,2,3}.csv, results/redis_aware_run{1,2,3}.csv
    CSV columns: test,rps,avg_latency_ms,min_latency_ms,p50_latency_ms,p95_latency_ms,p99_latency_ms,max_latency_ms
    """
    if results_dir is None:
        results_dir = os.path.join(WORKLOADS_DIR, "redis", "results")

    def parse_csv_run(path):
        if not os.path.exists(path):
            return None
        results = {}
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                test = row["test"].strip('"')
                results[test] = {
                    "rps": float(row["rps"].strip('"')),
                    "p50_ms": float(row["p50_latency_ms"].strip('"')),
                    "p99_ms": float(row["p99_latency_ms"].strip('"')),
                    "max_ms": float(row["max_latency_ms"].strip('"')),
                }
        return results

    cfs_runs = []
    custom_runs = []
    for i in range(1, 10):
        r = parse_csv_run(os.path.join(results_dir, f"cfs_run{i}.csv"))
        if r:
            cfs_runs.append(r)
        r = parse_csv_run(os.path.join(results_dir, f"redis_aware_run{i}.csv"))
        if r:
            custom_runs.append(r)

    if not cfs_runs or not custom_runs:
        return None

    # Average across runs, combine GET and SET
    def avg_redis_runs(runs):
        n = len(runs)
        # Average GET throughput (primary metric)
        avg_rps = sum(r.get("GET", r.get("SET", {})).get("rps", 0) for r in runs) / n
        avg_p50 = sum(r.get("GET", r.get("SET", {})).get("p50_ms", 0) for r in runs) / n
        avg_p99 = sum(r.get("GET", r.get("SET", {})).get("p99_ms", 0) for r in runs) / n
        return {"rps": avg_rps, "p50_ms": avg_p50, "p99_ms": avg_p99}

    cfs_avg = avg_redis_runs(cfs_runs)
    custom_avg = avg_redis_runs(custom_runs)

    return {
        "workload": "redis",
        "scheduler": "redis_aware",
        "runs": min(len(cfs_runs), len(custom_runs)),
        "baseline": {
            "throughput": cfs_avg["rps"],
            "latency_us": {
                "p50": cfs_avg["p50_ms"] * 1000,  # Convert ms → us
                "p99": cfs_avg["p99_ms"] * 1000,
                "p99.9": None,
            },
        },
        "custom": {
            "throughput": custom_avg["rps"],
            "latency_us": {
                "p50": custom_avg["p50_ms"] * 1000,
                "p99": custom_avg["p99_ms"] * 1000,
                "p99.9": None,
            },
        },
    }


def parse_nginx(results_dir=None):
    """Parse Nginx wrk2 results from text files.

    Expected files: results/cfs_run{1,2,3}.txt, results/nginx_aware_run{1,2,3}.txt
    wrk2 output contains percentile lines like:
       50.000%    1.39ms
       99.000%    9.98ms
       99.900%   29.20ms
    And throughput: Requests/sec: 49701.68
    """
    if results_dir is None:
        results_dir = os.path.join(WORKLOADS_DIR, "nginx", "results")

    def parse_wrk2_run(path):
        if not os.path.exists(path):
            return None
        with open(path) as f:
            text = f.read()

        result = {}

        # Parse percentiles from the distribution section
        # Format: " 50.000%    1.39ms" or " 99.000%    9.98ms"
        for pct_label, key in [("50.000%", "p50"), ("99.000%", "p99"),
                                ("99.900%", "p99.9"), ("99.990%", "p99.99")]:
            match = re.search(
                rf'^\s*{re.escape(pct_label)}\s+([\d.]+)(ms|us|s)',
                text, re.MULTILINE)
            if match:
                val = float(match.group(1))
                unit = match.group(2)
                if unit == "s":
                    val *= 1_000_000
                elif unit == "ms":
                    val *= 1000
                # us stays as-is
                result[key] = val

        # Parse throughput
        rps_match = re.search(r'Requests/sec:\s+([\d.]+)', text)
        result["rps"] = float(rps_match.group(1)) if rps_match else 0

        return result if result.get("p50") is not None else None

    cfs_runs = []
    custom_runs = []
    for i in range(1, 10):
        r = parse_wrk2_run(os.path.join(results_dir, f"cfs_run{i}.txt"))
        if r:
            cfs_runs.append(r)
        r = parse_wrk2_run(os.path.join(results_dir, f"nginx_aware_run{i}.txt"))
        if r:
            custom_runs.append(r)

    if not cfs_runs or not custom_runs:
        return None

    def avg_runs(runs):
        n = len(runs)
        result = {"rps": sum(r["rps"] for r in runs) / n}
        for key in ["p50", "p99", "p99.9", "p99.99"]:
            vals = [r[key] for r in runs if key in r]
            result[key] = sum(vals) / len(vals) if vals else None
        return result

    cfs_avg = avg_runs(cfs_runs)
    custom_avg = avg_runs(custom_runs)

    return {
        "workload": "nginx",
        "scheduler": "nginx_aware",
        "runs": min(len(cfs_runs), len(custom_runs)),
        "baseline": {
            "throughput": cfs_avg["rps"],
            "latency_us": {
                "p50": cfs_avg.get("p50"),
                "p99": cfs_avg.get("p99"),
                "p99.9": cfs_avg.get("p99.9"),
                "p99.99": cfs_avg.get("p99.99"),
            },
        },
        "custom": {
            "throughput": custom_avg["rps"],
            "latency_us": {
                "p50": custom_avg.get("p50"),
                "p99": custom_avg.get("p99"),
                "p99.9": custom_avg.get("p99.9"),
                "p99.99": custom_avg.get("p99.99"),
            },
        },
    }


PARSERS = {
    "db_sim": parse_db_sim,
    "rocksdb": parse_rocksdb,
    "redis": parse_redis,
    "nginx": parse_nginx,
}


def compute_improvement(result):
    """Add improvement percentages to a result dict."""
    base = result["baseline"]
    custom = result["custom"]

    improvement = {}

    # Throughput improvement
    if base["throughput"] and base["throughput"] > 0:
        improvement["throughput_pct"] = (
            (custom["throughput"] - base["throughput"]) / base["throughput"] * 100
        )
    else:
        improvement["throughput_pct"] = None

    # Latency improvement (negative = improvement = lower latency)
    for key in ["p50", "p99", "p99.9", "p99.99"]:
        base_val = base["latency_us"].get(key)
        custom_val = custom["latency_us"].get(key)
        if base_val and custom_val and base_val > 0:
            improvement[f"{key}_pct"] = (
                (custom_val - base_val) / base_val * 100
            )
        else:
            improvement[f"{key}_pct"] = None

    result["improvement"] = improvement
    return result


def format_pct(val, invert=False):
    """Format a percentage value. Invert for latency (negative = good)."""
    if val is None:
        return "N/A"
    return f"{val:+.1f}%"


def print_summary(results):
    """Print a unified comparison table."""
    print("=" * 95)
    print("Stage 4: Validation Summary — CFS vs Custom Scheduler")
    print("=" * 95)
    print(f"{'Workload':<10} {'Scheduler':<14} {'P99 Change':>11} {'P99.9 Change':>13} "
          f"{'Throughput':>11} {'Runs':>5}")
    print("-" * 95)

    for r in results:
        imp = r.get("improvement", {})
        p99_str = format_pct(imp.get("p99_pct"))
        p999_str = format_pct(imp.get("p99.9_pct"))
        tput_str = format_pct(imp.get("throughput_pct"))
        print(f"{r['workload']:<10} {r['scheduler']:<14} {p99_str:>11} {p999_str:>13} "
              f"{tput_str:>11} {r['runs']:>5}")

    print("-" * 95)
    print()

    # Detailed per-workload breakdown
    for r in results:
        base = r["baseline"]
        custom = r["custom"]
        print(f"  {r['workload']} ({r['scheduler']}, {r['runs']} run(s)):")
        print(f"    {'':12} {'Baseline':>12} {'Custom':>12} {'Change':>12}")
        print(f"    {'Throughput':12} {base['throughput']:>12.0f} {custom['throughput']:>12.0f} "
              f"{format_pct(r['improvement'].get('throughput_pct')):>12}")
        for key in ["p50", "p99", "p99.9", "p99.99"]:
            bv = base["latency_us"].get(key)
            cv = custom["latency_us"].get(key)
            pct = r["improvement"].get(f"{key}_pct")
            if bv is not None and cv is not None:
                print(f"    {key + ' (us)':12} {bv:>12.1f} {cv:>12.1f} {format_pct(pct):>12}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Stage 4: Validation harness")
    parser.add_argument("--workload", choices=list(PARSERS.keys()),
                        help="Parse a specific workload")
    parser.add_argument("--results-dir", default=None,
                        help="Override results directory for --workload")
    parser.add_argument("--summary", action="store_true",
                        help="Parse and summarize all workloads")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of table")
    args = parser.parse_args()

    if not args.workload and not args.summary:
        parser.print_help()
        sys.exit(1)

    results = []

    if args.summary:
        for name, parse_fn in PARSERS.items():
            result = parse_fn()
            if result:
                results.append(compute_improvement(result))
            else:
                print(f"  Warning: no results found for {name}", file=sys.stderr)
    elif args.workload:
        parse_fn = PARSERS[args.workload]
        result = parse_fn(args.results_dir)
        if result:
            results.append(compute_improvement(result))
        else:
            print(f"Error: no results found for {args.workload}", file=sys.stderr)
            sys.exit(1)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if results:
            print_summary(results)
        else:
            print("No results found.")
            sys.exit(1)


if __name__ == "__main__":
    main()
