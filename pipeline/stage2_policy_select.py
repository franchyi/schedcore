#!/usr/bin/env python3
"""
Stage 2: Policy Selection

Reads a Thread Manifest (from Stage 1) and recommends a scheduling pattern
based on contention level and workload characteristics.

Decision logic (from design.md Section 2.3 + 3.5):

  Pattern A: Simple dual DSQ (db_aware-like)
    - Low contention: threads ≤ CPUs
    - Foreground → FOREGROUND_DSQ, Background → BACKGROUND_DSQ
    - Priority drain ordering, no preemption

  Pattern B: Selective preemption (rocksdb_aware v7, redis_aware-like)
    - High contention: threads > 1.5× CPUs with active background work
    - Dual DSQ + per-CPU bg_running maps
    - select_cpu kicks background CPUs when foreground wakes

  Pattern C: Asymmetric + task storage (nginx_aware-like)
    - External CPU hogs co-located with application
    - Only 1 custom DSQ (BACKGROUND_DSQ), foreground uses SCX_DSQ_GLOBAL
    - Task storage caching for repeated classification

Usage:
  python3 stage2_policy_select.py <manifest.json> [--threads N] [--cpus N] [--external]

Examples:
  python3 stage2_policy_select.py pipeline/examples/redis_manifest.json --threads 70 --cpus 16
  python3 stage2_policy_select.py pipeline/examples/nginx_manifest.json --external
"""

import argparse
import json
import os
import sys


def load_json(path):
    with open(path) as f:
        return json.load(f)


def count_thread_types(manifest):
    """Count background and foreground thread types in the manifest."""
    bg_count = 0
    fg_count = 0
    bg_names = []
    fg_names = []
    for t in manifest.get("threads", []):
        if t["role"] == "background":
            bg_count += 1
            bg_names.append(t["name_pattern"])
        else:
            fg_count += 1
            fg_names.append(t["name_pattern"])
    return bg_count, fg_count, bg_names, fg_names


def select_policy(manifest, threads=None, cpus=None, external=False):
    """Select a scheduling pattern based on manifest and workload parameters.

    Returns: (pattern_name, config_dict, reasoning)
    """
    bg_count, fg_count, bg_names, fg_names = count_thread_types(manifest)

    if cpus is None:
        cpus = os.cpu_count() or 16

    if threads is None:
        # Estimate: assume at least 1 instance per thread type
        threads = bg_count + fg_count

    ratio = threads / cpus if cpus > 0 else 1.0

    reasoning = []
    reasoning.append(f"Application: {manifest.get('application', 'unknown')}")
    reasoning.append(f"Background thread types: {bg_count} ({', '.join(bg_names)})")
    reasoning.append(f"Foreground thread types: {fg_count} ({', '.join(fg_names)})")
    reasoning.append(f"Thread/CPU ratio: {threads}/{cpus} = {ratio:.1f}")

    # Pattern C: external CPU hogs
    if external:
        reasoning.append("External CPU hogs detected (--external flag)")
        reasoning.append("→ Pattern C: Asymmetric + task storage")
        reasoning.append("  Only deprioritize known CPU hogs to BACKGROUND_DSQ")
        reasoning.append("  Everything else uses SCX_DSQ_GLOBAL (framework fast path)")
        reasoning.append("  Task storage caches classification per-task lifetime")
        return "asymmetric_task_storage", {
            "pattern": "asymmetric_task_storage",
            "fg_dsq": False,
            "bg_dsq": True,
            "preemption": True,
            "task_storage": True,
        }, reasoning

    # Pattern B: selective preemption (high contention)
    if ratio > 1.5:
        reasoning.append(f"High contention: ratio {ratio:.1f} > 1.5")
        reasoning.append("→ Pattern B: Selective preemption")
        reasoning.append("  Dual DSQ (FOREGROUND + BACKGROUND)")
        reasoning.append("  Per-CPU bg_running maps track background threads")
        reasoning.append("  select_cpu kicks background CPUs when foreground wakes")
        return "selective_preemption", {
            "pattern": "selective_preemption",
            "fg_dsq": True,
            "bg_dsq": True,
            "preemption": True,
            "task_storage": False,
        }, reasoning

    # Pattern A: simple dual DSQ (low contention)
    reasoning.append(f"Low contention: ratio {ratio:.1f} ≤ 1.5")
    reasoning.append("→ Pattern A: Simple dual DSQ")
    reasoning.append("  Foreground → FOREGROUND_DSQ, Background → BACKGROUND_DSQ")
    reasoning.append("  Priority drain ordering (foreground first)")
    reasoning.append("  No preemption needed — idle CPUs available")
    return "simple_dual_dsq", {
        "pattern": "simple_dual_dsq",
        "fg_dsq": True,
        "bg_dsq": True,
        "preemption": False,
        "task_storage": False,
    }, reasoning


def main():
    parser = argparse.ArgumentParser(description="Stage 2: Policy selection for BPF scheduler")
    parser.add_argument("manifest", help="Path to Thread Manifest JSON")
    parser.add_argument("--threads", type=int, default=None,
                        help="Expected total thread count at runtime")
    parser.add_argument("--cpus", type=int, default=None,
                        help="Number of CPUs (default: auto-detect)")
    parser.add_argument("--external", action="store_true",
                        help="External CPU hogs are co-located (Pattern C)")
    parser.add_argument("--json", action="store_true",
                        help="Output only JSON (for Stage 3 consumption)")
    args = parser.parse_args()

    if not os.path.exists(args.manifest):
        print(f"Error: manifest not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    manifest = load_json(args.manifest)
    pattern, config, reasoning = select_policy(
        manifest, threads=args.threads, cpus=args.cpus, external=args.external)

    if args.json:
        print(json.dumps(config, indent=2))
    else:
        print("=" * 60)
        print("Stage 2: Policy Selection")
        print("=" * 60)
        for line in reasoning:
            print(f"  {line}")
        print()
        print(f"Selected pattern: {pattern}")
        print()
        print("Configuration (JSON for Stage 3):")
        print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
