#!/usr/bin/env python3
"""
Batch accuracy evaluation for Stage 1 Thread Discovery.

Scans pipeline/examples/ for ground-truth manifests, matches with generated
manifests in pipeline/results/, and prints a summary table with per-app and
aggregate precision/recall/F1.

Usage:
  python3 evaluate_accuracy.py
  python3 evaluate_accuracy.py --examples-dir pipeline/examples --results-dir pipeline/results
"""

import argparse
import glob
import json
import os
import sys

# Import compute_metrics from verify_manifest (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_manifest import compute_metrics, load_json


def find_latest_generated(results_dir, app_name):
    """Find the most recent generated manifest for an application."""
    pattern = os.path.join(results_dir, f"{app_name}_generated*.json")
    candidates = []
    for path in sorted(glob.glob(pattern)):
        # Skip stats files
        if path.endswith("_stats.json"):
            continue
        # Skip non-manifest files (e.g., thread reports)
        if "thread_report" in path:
            continue
        candidates.append(path)
    if not candidates:
        return None
    # Return the latest (sorted alphabetically, timestamps sort correctly)
    return candidates[-1]


def main():
    parser = argparse.ArgumentParser(description="Batch accuracy evaluation for thread discovery")
    parser.add_argument("--examples-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples"),
                        help="Directory containing ground-truth manifests")
    parser.add_argument("--results-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"),
                        help="Directory containing generated manifests")
    args = parser.parse_args()

    # Find all ground-truth manifests
    gt_pattern = os.path.join(args.examples_dir, "*_manifest.json")
    gt_files = sorted(glob.glob(gt_pattern))

    if not gt_files:
        print(f"No ground-truth manifests found in {args.examples_dir}")
        sys.exit(1)

    results = []
    total_tp, total_fn, total_safety, total_extra = 0, 0, 0, 0

    for gt_path in gt_files:
        gt = load_json(gt_path)
        app_name = gt.get("application", os.path.basename(gt_path).replace("_manifest.json", ""))

        gen_path = find_latest_generated(args.results_dir, app_name)
        if gen_path is None:
            results.append({
                "app": app_name,
                "gt_path": gt_path,
                "gen_path": None,
                "metrics": None,
            })
            continue

        gen = load_json(gen_path)
        metrics = compute_metrics(gen, gt)
        results.append({
            "app": app_name,
            "gt_path": gt_path,
            "gen_path": gen_path,
            "metrics": metrics,
        })
        total_tp += metrics["true_positives"]
        total_fn += metrics["false_negatives"]
        total_safety += metrics["safety_violations"]
        total_extra += metrics["extra_discoveries"]

    # Print summary table
    print("=" * 85)
    print("Stage 1 Thread Discovery — Accuracy Evaluation")
    print("=" * 85)
    print(f"{'Application':<12} {'Precision':>9} {'Recall':>8} {'F1':>8} {'TP':>4} {'FN':>4} {'Safety':>7} {'Extra':>6}  Generated From")
    print("-" * 85)

    evaluated = 0
    for r in results:
        if r["metrics"] is None:
            print(f"{r['app']:<12} {'—':>9} {'—':>8} {'—':>8} {'—':>4} {'—':>4} {'—':>7} {'—':>6}  (no generated manifest)")
            continue
        m = r["metrics"]
        evaluated += 1
        gen_basename = os.path.basename(r["gen_path"])
        print(f"{r['app']:<12} {m['precision']:>9.3f} {m['recall']:>8.3f} {m['f1']:>8.3f} {m['true_positives']:>4} {m['false_negatives']:>4} {m['safety_violations']:>7} {m['extra_discoveries']:>6}  {gen_basename}")

    # Aggregate
    if evaluated > 0:
        total_fp = total_safety + total_extra
        agg_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
        agg_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
        agg_f1 = 2 * agg_precision * agg_recall / (agg_precision + agg_recall) if (agg_precision + agg_recall) > 0 else 0.0

        print("-" * 85)
        print(f"{'AGGREGATE':<12} {agg_precision:>9.3f} {agg_recall:>8.3f} {agg_f1:>8.3f} {total_tp:>4} {total_fn:>4} {total_safety:>7} {total_extra:>6}")
        print()
        if total_safety > 0:
            print(f"WARNING: {total_safety} safety violation(s) — foreground threads misclassified as background!")
        else:
            print("No safety violations (0 foreground→background misclassifications)")
    else:
        print()
        print("No generated manifests found to evaluate.")

    print()
    sys.exit(1 if total_safety > 0 else 0)


if __name__ == "__main__":
    main()
