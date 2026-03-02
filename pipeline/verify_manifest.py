#!/usr/bin/env python3
"""
Verify a Stage 1 Thread Manifest against a ground-truth manifest.

Checks:
  1. Schema conformance (if jsonschema is installed)
  2. All ground-truth background threads are discovered
  3. No foreground threads are misclassified as background
  4. comm_prefix and comm_length match for each thread

Usage:
  python3 verify_manifest.py <generated_manifest> <ground_truth_manifest>

Example:
  python3 verify_manifest.py /tmp/rocksdb_manifest.json pipeline/examples/rocksdb_manifest.json
"""

import json
import sys
import os


def load_json(path):
    with open(path) as f:
        return json.load(f)


def validate_schema(manifest, schema_path):
    """Validate manifest against JSON schema. Returns list of errors."""
    try:
        from jsonschema import validate, ValidationError
        schema = load_json(schema_path)
        try:
            validate(instance=manifest, schema=schema)
            return []
        except ValidationError as e:
            return [f"Schema validation error: {e.message}"]
    except ImportError:
        return ["SKIP: jsonschema not installed, schema validation skipped"]


def normalize_threads(manifest):
    """Build a lookup of background thread identification patterns."""
    bg_threads = {}
    fg_threads = {}
    for t in manifest.get("threads", []):
        ident = t.get("identification", {})
        key = (ident.get("type"), ident.get("comm_prefix"), ident.get("comm_length"))
        if t["role"] == "background":
            bg_threads[key] = t
        else:
            fg_threads[key] = t
    return bg_threads, fg_threads


def compute_metrics(generated, ground_truth):
    """Compute precision/recall/F1 for background thread classification.

    Returns dict with:
      - true_positives: bg threads correctly identified
      - false_negatives: gt bg threads not discovered
      - safety_violations: gt foreground threads misclassified as bg (critical)
      - extra_discoveries: bg threads not in gt at all (non-critical)
      - precision, recall, f1: standard metrics
    """
    gen_bg, gen_fg = normalize_threads(generated)
    gt_bg, gt_fg = normalize_threads(ground_truth)

    # Deduplicate (e.g., redis has 3 bio_* entries with same key)
    gt_bg_unique = {k: v for k, v in gt_bg.items()}

    # True positives: bg in both generated and ground truth
    tp = len(set(gen_bg.keys()) & set(gt_bg_unique.keys()))

    # False negatives: gt bg not discovered
    fn = len(set(gt_bg_unique.keys()) - set(gen_bg.keys()))

    # Safety violations: gt foreground misclassified as bg
    safety = len(set(gt_fg.keys()) & set(gen_bg.keys()))

    # Extra discoveries: gen bg not in gt at all (not fg either)
    all_gt_keys = set(gt_bg_unique.keys()) | set(gt_fg.keys())
    extra = len(set(gen_bg.keys()) - all_gt_keys)

    # Precision = TP / (TP + FP), where FP = safety_violations + extra
    fp = safety + extra
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "true_positives": tp,
        "false_negatives": fn,
        "safety_violations": safety,
        "extra_discoveries": extra,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def compare_manifests(generated, ground_truth):
    """Compare generated manifest against ground truth. Returns (pass_count, fail_count, messages)."""
    passes = 0
    fails = 0
    warnings = 0
    messages = []

    # Check application name
    if generated.get("application") == ground_truth.get("application"):
        passes += 1
        messages.append(("PASS", f"Application name matches: {generated['application']}"))
    else:
        fails += 1
        messages.append(("FAIL", f"Application name mismatch: got '{generated.get('application')}', expected '{ground_truth.get('application')}'"))

    # Check identification method
    if generated.get("identification_method") == ground_truth.get("identification_method"):
        passes += 1
        messages.append(("PASS", f"Identification method matches: {generated['identification_method']}"))
    else:
        fails += 1
        messages.append(("FAIL", f"Identification method mismatch: got '{generated.get('identification_method')}', expected '{ground_truth.get('identification_method')}'"))

    # Check rationale exists
    if generated.get("rationale") and len(generated["rationale"]) > 20:
        passes += 1
        messages.append(("PASS", "Rationale provided"))
    else:
        fails += 1
        messages.append(("FAIL", "Rationale missing or too short"))

    # Check default_role
    gen_default = generated.get("default_role")
    gt_default = ground_truth.get("default_role")
    if gt_default:
        if gen_default == gt_default:
            passes += 1
            messages.append(("PASS", f"default_role matches: {gen_default}"))
        elif gen_default is None:
            warnings += 1
            messages.append(("WARN", f"default_role not set (expected '{gt_default}')"))
        else:
            fails += 1
            messages.append(("FAIL", f"default_role mismatch: got '{gen_default}', expected '{gt_default}'"))
    elif gen_default:
        passes += 1
        messages.append(("PASS", f"default_role set: {gen_default}"))

    # Build thread lookups
    gen_bg, gen_fg = normalize_threads(generated)
    gt_bg, gt_fg = normalize_threads(ground_truth)

    # Deduplicate ground truth background patterns (e.g., redis has 3 bio_* entries with same key)
    gt_bg_unique = {}
    for key, t in gt_bg.items():
        gt_bg_unique[key] = t

    # Check: all ground-truth background threads are discovered
    messages.append(("INFO", "--- Background Thread Discovery ---"))
    for key, gt_thread in gt_bg_unique.items():
        ident_type, prefix, length = key
        if key in gen_bg:
            passes += 1
            messages.append(("PASS", f"Background thread found: prefix='{prefix}' length={length} ({gt_thread['name_pattern']})"))
        else:
            # Check if there's a partial match (same prefix, different length)
            partial = False
            for gk, gt in gen_bg.items():
                if gk[1] and prefix and gk[1].startswith(prefix[:3]):
                    partial = True
                    warnings += 1
                    messages.append(("WARN", f"Partial match for '{prefix}': found prefix='{gk[1]}' length={gk[2]} (expected length={length})"))
                    break
            if not partial:
                fails += 1
                messages.append(("FAIL", f"Background thread MISSING: prefix='{prefix}' length={length} ({gt_thread['name_pattern']})"))

    # Check: no foreground threads misclassified as background
    messages.append(("INFO", "--- Foreground Thread Safety ---"))
    for key, gt_thread in gt_fg.items():
        ident_type, prefix, length = key
        if key in gen_bg:
            fails += 1
            messages.append(("FAIL", f"MISCLASSIFIED: foreground thread '{prefix}' classified as background (would hurt latency!)"))
        else:
            passes += 1
            messages.append(("PASS", f"Foreground thread not misclassified: '{prefix}' ({gt_thread['name_pattern']})"))

    # Check for extra background threads (not in ground truth)
    messages.append(("INFO", "--- Extra Discoveries ---"))
    extra_bg = set(gen_bg.keys()) - set(gt_bg_unique.keys())
    if extra_bg:
        for key in extra_bg:
            gen_thread = gen_bg[key]
            warnings += 1
            messages.append(("WARN", f"Extra background thread (not in ground truth): '{gen_thread['name_pattern']}' prefix='{key[1]}'"))
    else:
        messages.append(("INFO", "No extra background threads discovered"))

    # Summary of generated threads
    messages.append(("INFO", "--- Generated Manifest Summary ---"))
    for t in generated.get("threads", []):
        ident = t.get("identification", {})
        messages.append(("INFO", f"  [{t['role'].upper():10s}] {t['name_pattern']:25s} type={ident.get('type')} prefix='{ident.get('comm_prefix')}' len={ident.get('comm_length')}"))

    # Compute and append quantitative metrics
    metrics = compute_metrics(generated, ground_truth)
    messages.append(("INFO", "--- Quantitative Metrics ---"))
    messages.append(("INFO", f"  True Positives:    {metrics['true_positives']}"))
    messages.append(("INFO", f"  False Negatives:   {metrics['false_negatives']}"))
    messages.append(("INFO", f"  Safety Violations: {metrics['safety_violations']} (foreground→background misclassification)"))
    messages.append(("INFO", f"  Extra Discoveries: {metrics['extra_discoveries']} (unknown→background, non-critical)"))
    messages.append(("INFO", f"  Precision: {metrics['precision']:.3f}  Recall: {metrics['recall']:.3f}  F1: {metrics['f1']:.3f}"))
    if metrics["safety_violations"] > 0:
        messages.append(("FAIL", f"  {metrics['safety_violations']} SAFETY VIOLATION(S): foreground threads would be deprioritized!"))

    return passes, fails, warnings, messages


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    generated_path = sys.argv[1]
    ground_truth_path = sys.argv[2]
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thread_manifest.schema.json")

    if not os.path.exists(generated_path):
        print(f"Error: generated manifest not found: {generated_path}")
        sys.exit(1)
    if not os.path.exists(ground_truth_path):
        print(f"Error: ground truth manifest not found: {ground_truth_path}")
        sys.exit(1)

    generated = load_json(generated_path)
    ground_truth = load_json(ground_truth_path)

    print(f"=== Thread Manifest Verification ===")
    print(f"Generated:    {generated_path}")
    print(f"Ground Truth: {ground_truth_path}")
    print()

    # Schema validation
    if os.path.exists(schema_path):
        schema_errors = validate_schema(generated, schema_path)
        for err in schema_errors:
            if err.startswith("SKIP"):
                print(f"  SKIP  {err[6:]}")
            else:
                print(f"  FAIL  {err}")
    print()

    # Compare manifests
    passes, fails, warnings, messages = compare_manifests(generated, ground_truth)

    for level, msg in messages:
        if level == "PASS":
            print(f"  PASS  {msg}")
        elif level == "FAIL":
            print(f"  FAIL  {msg}")
        elif level == "WARN":
            print(f"  WARN  {msg}")
        elif level == "INFO":
            print(f"        {msg}")

    print()
    print(f"=== Results: {passes} passed, {fails} failed, {warnings} warnings ===")

    if fails > 0:
        print("VERDICT: FAIL — generated manifest does not match ground truth")
        sys.exit(1)
    elif warnings > 0:
        print("VERDICT: PASS (with warnings)")
        sys.exit(0)
    else:
        print("VERDICT: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
