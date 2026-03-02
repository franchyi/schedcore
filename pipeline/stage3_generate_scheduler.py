#!/usr/bin/env python3
"""
Stage 3: BPF Skeleton Generator

Generates a .bpf.c scheduler skeleton from a Thread Manifest and a scheduling
pattern (from Stage 2). The output is a starting point for a developer to
refine — not a finished product.

What the generator does:
  1. Reads manifest → extracts background thread entries with (comm_prefix, comm_length)
  2. Generates classification function — byte-by-byte comm comparison
  3. Selects pattern template (A, B, or C)
  4. Assembles .bpf.c via str.format()

Pattern templates (derived from real schedulers):
  A: Simple dual DSQ (db_aware.bpf.c)
  B: Selective preemption (redis_aware.bpf.c)
  C: Asymmetric + task storage (nginx_aware.bpf.c)

Usage:
  python3 stage3_generate_scheduler.py <manifest.json> \\
      --pattern selective_preemption \\
      --name redis_aware \\
      --output workloads/redis/redis_aware_generated.bpf.c
"""

import argparse
import json
import os
import sys


def load_json(path):
    with open(path) as f:
        return json.load(f)


def extract_bg_prefixes(manifest):
    """Extract unique (comm_prefix, comm_length, name_pattern) tuples for background threads."""
    seen = set()
    prefixes = []
    for t in manifest.get("threads", []):
        if t["role"] != "background":
            continue
        ident = t.get("identification", {})
        prefix = ident.get("comm_prefix", "")
        length = ident.get("comm_length", len(prefix))
        key = (prefix, length)
        if key not in seen:
            seen.add(key)
            prefixes.append((prefix, length, t["name_pattern"]))
    return prefixes


def extract_fg_prefixes(manifest):
    """Extract unique (comm_prefix, comm_length, name_pattern) tuples for foreground threads."""
    seen = set()
    prefixes = []
    for t in manifest.get("threads", []):
        if t["role"] != "foreground":
            continue
        ident = t.get("identification", {})
        prefix = ident.get("comm_prefix", "")
        length = ident.get("comm_length", len(prefix))
        key = (prefix, length)
        if key not in seen:
            seen.add(key)
            prefixes.append((prefix, length, t["name_pattern"]))
    return prefixes


def generate_comm_check(prefix, length, indent="\t"):
    """Generate byte-by-byte comm comparison for a single prefix.

    Returns a C expression like: comm[0] == 'r' && comm[1] == 'e' && ...
    """
    # Use the actual prefix characters, limited to length
    chars = prefix[:length]
    parts = []
    for i, ch in enumerate(chars):
        parts.append(f"comm[{i}] == '{ch}'")
    return f" &&\n{indent}    ".join(parts)


def generate_classification_fn(name, bg_prefixes):
    """Generate the is_<name>_background() classification function."""
    lines = []
    lines.append(f"static bool is_{name}_background(struct task_struct *p)")
    lines.append("{")
    lines.append("\tchar comm[16];")
    lines.append("")
    lines.append("\tif (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)")
    lines.append("\t\treturn false;")

    for prefix, length, name_pattern in bg_prefixes:
        lines.append("")
        lines.append(f"\t/* {name_pattern} — match \"{prefix}\" prefix */")
        check = generate_comm_check(prefix, length)
        lines.append(f"\tif ({check})")
        lines.append("\t\treturn true;")

    lines.append("")
    lines.append("\treturn false;")
    lines.append("}")
    return "\n".join(lines)


def generate_classify_task_fn(name, bg_prefixes, fg_prefixes):
    """Generate the classify_task() function for Pattern C (task storage)."""
    lines = []
    lines.append("static u8 classify_task(struct task_struct *p)")
    lines.append("{")
    lines.append("\tstruct task_class *tc;")
    lines.append("")
    lines.append("\ttc = bpf_task_storage_get(&task_class_map, p, 0, 0);")
    lines.append("\tif (tc && tc->class != TASK_UNKNOWN)")
    lines.append("\t\treturn tc->class;")
    lines.append("")
    lines.append("\t/* First time seeing this task — read comm and classify */")
    lines.append("\tchar comm[16];")
    lines.append("\tu8 result = TASK_NORMAL;")
    lines.append("")
    lines.append("\tif (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) >= 0) {")

    first = True
    # Foreground thread patterns
    for prefix, length, name_pattern in fg_prefixes:
        keyword = "if" if first else "else if"
        first = False
        check = generate_comm_check(prefix, length, indent="\t\t")
        lines.append(f"\t\t/* \"{name_pattern}\" */")
        lines.append(f"\t\t{keyword} ({check})")
        lines.append(f"\t\t\tresult = TASK_FOREGROUND;")

    # Background thread patterns
    for prefix, length, name_pattern in bg_prefixes:
        keyword = "if" if first else "else if"
        first = False
        check = generate_comm_check(prefix, length, indent="\t\t")
        lines.append(f"\t\t/* \"{name_pattern}\" — CPU hog */")
        lines.append(f"\t\t{keyword} ({check})")
        lines.append(f"\t\t\tresult = TASK_CPU_HOG;")

    lines.append("\t}")
    lines.append("")
    lines.append("\t/* Cache for future calls */")
    lines.append("\ttc = bpf_task_storage_get(&task_class_map, p, 0,")
    lines.append("\t\t\t\t  BPF_LOCAL_STORAGE_GET_F_CREATE);")
    lines.append("\tif (tc)")
    lines.append("\t\ttc->class = result;")
    lines.append("")
    lines.append("\treturn result;")
    lines.append("}")
    return "\n".join(lines)


# ── Pattern Templates ────────────────────────────────────────────────────────

# Pattern A: Simple dual DSQ (derived from db_aware.bpf.c)
TEMPLATE_A = """\
/* SPDX-License-Identifier: GPL-2.0 */
/*
 * {sched_name} - Thread-aware BPF scheduler (simple dual DSQ)
 *
 * Generated by Stage 3 of the schedcp framework.
 * This is a skeleton — refine slice values and classification as needed.
 *
 * Pattern A: Simple dual DSQ with priority drain ordering.
 *   Foreground → FOREGROUND_DSQ (high priority, 3ms slice)
 *   Background → BACKGROUND_DSQ (low priority, 20ms slice)
 *   Idle CPU fast path: all threads → SCX_DSQ_LOCAL
 *
 * Background threads:
{bg_thread_comments}
 */
#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

UEI_DEFINE(uei);

#define FOREGROUND_DSQ  0x100
#define BACKGROUND_DSQ  0x101

#define FOREGROUND_SLICE_NS  3000000ULL   /* 3ms */
#define BACKGROUND_SLICE_NS  20000000ULL  /* 20ms */

{classification_fn}

s32 BPF_STRUCT_OPS({sched_name}_select_cpu, struct task_struct *p,
\t\t   s32 prev_cpu, u64 wake_flags)
{{
\tbool is_idle = false;
\ts32 cpu;

\tcpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);
\tif (is_idle) {{
\t\tu64 slice = is_{fn_name}_background(p) ?
\t\t\t    BACKGROUND_SLICE_NS : FOREGROUND_SLICE_NS;
\t\tscx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, 0);
\t}}

\treturn cpu;
}}

void BPF_STRUCT_OPS({sched_name}_enqueue, struct task_struct *p,
\t\t    u64 enq_flags)
{{
\tif (is_{fn_name}_background(p)) {{
\t\tscx_bpf_dsq_insert(p, BACKGROUND_DSQ, BACKGROUND_SLICE_NS,
\t\t\t\t    enq_flags);
\t}} else {{
\t\tscx_bpf_dsq_insert(p, FOREGROUND_DSQ, FOREGROUND_SLICE_NS,
\t\t\t\t    enq_flags);
\t}}
}}

void BPF_STRUCT_OPS({sched_name}_dispatch, s32 cpu, struct task_struct *prev)
{{
\t/* Priority order: foreground first, then background */
\tif (!scx_bpf_dsq_move_to_local(FOREGROUND_DSQ)) {{
\t\tscx_bpf_dsq_move_to_local(BACKGROUND_DSQ);
\t}}
}}

s32 BPF_STRUCT_OPS_SLEEPABLE({sched_name}_init)
{{
\ts32 ret;

\tret = scx_bpf_create_dsq(FOREGROUND_DSQ, -1);
\tif (ret)
\t\treturn ret;

\treturn scx_bpf_create_dsq(BACKGROUND_DSQ, -1);
}}

void BPF_STRUCT_OPS({sched_name}_exit, struct scx_exit_info *ei)
{{
\tUEI_RECORD(uei, ei);
}}

SCX_OPS_DEFINE({sched_name}_ops,
\t       .select_cpu\t= (void *){sched_name}_select_cpu,
\t       .enqueue\t\t= (void *){sched_name}_enqueue,
\t       .dispatch\t= (void *){sched_name}_dispatch,
\t       .init\t\t= (void *){sched_name}_init,
\t       .exit\t\t= (void *){sched_name}_exit,
\t       .name\t\t= "{sched_name}");
"""

# Pattern B: Selective preemption (derived from redis_aware.bpf.c)
TEMPLATE_B = """\
/* SPDX-License-Identifier: GPL-2.0 */
/*
 * {sched_name} - Thread-aware BPF scheduler with selective preemption
 *
 * Generated by Stage 3 of the schedcp framework.
 * This is a skeleton — refine slice values and classification as needed.
 *
 * Pattern B: Dual DSQ with selective preemption.
 *   Foreground → FOREGROUND_DSQ (high priority, 5ms slice)
 *   Background → BACKGROUND_DSQ (low priority, 20ms slice)
 *   Idle CPU fast path: all threads → SCX_DSQ_LOCAL
 *   When foreground wakes with no idle CPU, kick a CPU running a bg thread ≥ 2ms
 *
 * Background threads:
{bg_thread_comments}
 */
#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

UEI_DEFINE(uei);

#define FOREGROUND_DSQ  0x200
#define BACKGROUND_DSQ  0x201

#define DEFAULT_SLICE_NS     5000000ULL   /* 5ms */
#define BACKGROUND_SLICE_NS  20000000ULL  /* 20ms */
#define BG_MIN_RUN_NS        2000000ULL   /* 2ms minimum before preemption */
#define MAX_CPUS 256

/*
 * bg_running: per-CPU flag indicating whether a background thread is running.
 */
struct {{
\t__uint(type, BPF_MAP_TYPE_ARRAY);
\t__uint(max_entries, MAX_CPUS);
\t__type(key, u32);
\t__type(value, u8);
}} bg_running SEC(".maps");

/*
 * bg_start_ns: per-CPU timestamp when current background thread started.
 */
struct {{
\t__uint(type, BPF_MAP_TYPE_ARRAY);
\t__uint(max_entries, MAX_CPUS);
\t__type(key, u32);
\t__type(value, u64);
}} bg_start_ns SEC(".maps");

{classification_fn}

s32 BPF_STRUCT_OPS({sched_name}_select_cpu, struct task_struct *p,
\t\t   s32 prev_cpu, u64 wake_flags)
{{
\tbool is_idle = false;
\ts32 cpu;

\tcpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);

\tif (is_idle) {{
\t\tu64 slice = is_{fn_name}_background(p) ?
\t\t\t    BACKGROUND_SLICE_NS : DEFAULT_SLICE_NS;
\t\tscx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, 0);
\t\treturn cpu;
\t}}

\t/*
\t * No idle CPU. If this is a foreground thread, try to preempt a CPU
\t * that's running a background thread that has run long enough.
\t */
\tif (!is_{fn_name}_background(p)) {{
\t\tu64 now = bpf_ktime_get_ns();
\t\tu32 i;

\t\tbpf_for(i, 0, MAX_CPUS) {{
\t\t\tu32 key = i;
\t\t\tu8 *running = bpf_map_lookup_elem(&bg_running, &key);
\t\t\tif (!running || !*running)
\t\t\t\tcontinue;

\t\t\tu64 *start = bpf_map_lookup_elem(&bg_start_ns, &key);
\t\t\tif (start && (now - *start) >= BG_MIN_RUN_NS) {{
\t\t\t\tscx_bpf_kick_cpu(i, SCX_KICK_PREEMPT);
\t\t\t\tbreak;
\t\t\t}}
\t\t}}
\t}}

\treturn cpu;
}}

void BPF_STRUCT_OPS({sched_name}_enqueue, struct task_struct *p,
\t\t    u64 enq_flags)
{{
\tif (is_{fn_name}_background(p)) {{
\t\tscx_bpf_dsq_insert(p, BACKGROUND_DSQ, BACKGROUND_SLICE_NS,
\t\t\t\t    enq_flags);
\t}} else {{
\t\tscx_bpf_dsq_insert(p, FOREGROUND_DSQ, DEFAULT_SLICE_NS,
\t\t\t\t    enq_flags);
\t}}
}}

void BPF_STRUCT_OPS({sched_name}_dispatch, s32 cpu, struct task_struct *prev)
{{
\t/* Priority order: foreground first, then background */
\tif (scx_bpf_dsq_move_to_local(FOREGROUND_DSQ))
\t\treturn;
\tscx_bpf_dsq_move_to_local(BACKGROUND_DSQ);
}}

void BPF_STRUCT_OPS({sched_name}_running, struct task_struct *p)
{{
\tif (is_{fn_name}_background(p)) {{
\t\tu32 key = bpf_get_smp_processor_id();
\t\tu8 val = 1;
\t\tu64 now = bpf_ktime_get_ns();
\t\tbpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
\t\tbpf_map_update_elem(&bg_start_ns, &key, &now, BPF_ANY);
\t}}
}}

void BPF_STRUCT_OPS({sched_name}_stopping, struct task_struct *p,
\t\t    bool runnable)
{{
\tif (is_{fn_name}_background(p)) {{
\t\tu32 key = bpf_get_smp_processor_id();
\t\tu8 val = 0;
\t\tbpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
\t}}
}}

s32 BPF_STRUCT_OPS_SLEEPABLE({sched_name}_init)
{{
\ts32 ret;

\tret = scx_bpf_create_dsq(FOREGROUND_DSQ, -1);
\tif (ret)
\t\treturn ret;
\treturn scx_bpf_create_dsq(BACKGROUND_DSQ, -1);
}}

void BPF_STRUCT_OPS({sched_name}_exit, struct scx_exit_info *ei)
{{
\tUEI_RECORD(uei, ei);
}}

SCX_OPS_DEFINE({sched_name}_ops,
\t       .select_cpu\t= (void *){sched_name}_select_cpu,
\t       .enqueue\t\t= (void *){sched_name}_enqueue,
\t       .dispatch\t= (void *){sched_name}_dispatch,
\t       .running\t\t= (void *){sched_name}_running,
\t       .stopping\t= (void *){sched_name}_stopping,
\t       .init\t\t= (void *){sched_name}_init,
\t       .exit\t\t= (void *){sched_name}_exit,
\t       .name\t\t= "{sched_name}");
"""

# Pattern C: Asymmetric + task storage (derived from nginx_aware.bpf.c)
TEMPLATE_C = """\
/* SPDX-License-Identifier: GPL-2.0 */
/*
 * {sched_name} - Low-overhead process-aware BPF scheduler (asymmetric)
 *
 * Generated by Stage 3 of the schedcp framework.
 * This is a skeleton — refine slice values and classification as needed.
 *
 * Pattern C: Asymmetric + task storage.
 *   CPU hogs → BACKGROUND_DSQ (deprioritized, 20ms slice)
 *   Everything else → SCX_DSQ_GLOBAL (framework fast path)
 *   Idle CPU fast path: all threads → SCX_DSQ_LOCAL
 *   Foreground threads can kick CPU hog threads that ran ≥ 2ms
 *   Task storage caches classification per-task lifetime
 *
 * Background threads (CPU hogs):
{bg_thread_comments}
 * Foreground threads:
{fg_thread_comments}
 */
#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

UEI_DEFINE(uei);

#define BACKGROUND_DSQ  0x201

#define DEFAULT_SLICE_NS     5000000ULL   /* 5ms */
#define BACKGROUND_SLICE_NS  20000000ULL  /* 20ms */
#define BG_MIN_RUN_NS        2000000ULL   /* 2ms minimum before preemption */
#define MAX_CPUS 256

/* Task classification values */
#define TASK_UNKNOWN    0
#define TASK_FOREGROUND 1
#define TASK_CPU_HOG    2
#define TASK_NORMAL     3

/*
 * Per-task cached classification. Avoids reading comm on every scheduling event.
 */
struct task_class {{
\tu8 class;
}};

struct {{
\t__uint(type, BPF_MAP_TYPE_TASK_STORAGE);
\t__uint(map_flags, BPF_F_NO_PREALLOC);
\t__type(key, int);
\t__type(value, struct task_class);
}} task_class_map SEC(".maps");

/*
 * bg_running: per-CPU flag indicating whether a CPU hog thread is running.
 */
struct {{
\t__uint(type, BPF_MAP_TYPE_ARRAY);
\t__uint(max_entries, MAX_CPUS);
\t__type(key, u32);
\t__type(value, u8);
}} bg_running SEC(".maps");

/*
 * bg_start_ns: per-CPU timestamp when current CPU hog thread started.
 */
struct {{
\t__uint(type, BPF_MAP_TYPE_ARRAY);
\t__uint(max_entries, MAX_CPUS);
\t__type(key, u32);
\t__type(value, u64);
}} bg_start_ns SEC(".maps");

/* Actual number of CPUs, set in init */
static u32 nr_cpus;

/*
 * Classify task once, cache the result.
 */
{classify_task_fn}

s32 BPF_STRUCT_OPS({sched_name}_select_cpu, struct task_struct *p,
\t\t   s32 prev_cpu, u64 wake_flags)
{{
\tbool is_idle = false;
\ts32 cpu;
\tu8 cls;

\tcpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);
\tcls = classify_task(p);

\tif (is_idle) {{
\t\tu64 slice = (cls == TASK_CPU_HOG) ?
\t\t\t    BACKGROUND_SLICE_NS : DEFAULT_SLICE_NS;
\t\tscx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, slice, 0);
\t\treturn cpu;
\t}}

\t/*
\t * No idle CPU. If this is a foreground thread, try to preempt a CPU
\t * running a CPU hog thread that has run >= 2ms.
\t */
\tif (cls == TASK_FOREGROUND) {{
\t\tu64 now = bpf_ktime_get_ns();
\t\tu32 limit = nr_cpus;
\t\tu32 i;

\t\tif (limit > MAX_CPUS)
\t\t\tlimit = MAX_CPUS;

\t\tbpf_for(i, 0, limit) {{
\t\t\tu32 key = i;
\t\t\tu8 *running = bpf_map_lookup_elem(&bg_running, &key);
\t\t\tif (!running || !*running)
\t\t\t\tcontinue;

\t\t\tu64 *start = bpf_map_lookup_elem(&bg_start_ns, &key);
\t\t\tif (start && (now - *start) >= BG_MIN_RUN_NS) {{
\t\t\t\tscx_bpf_kick_cpu(i, SCX_KICK_PREEMPT);
\t\t\t\tbreak;
\t\t\t}}
\t\t}}
\t}}

\treturn cpu;
}}

void BPF_STRUCT_OPS({sched_name}_enqueue, struct task_struct *p,
\t\t    u64 enq_flags)
{{
\tif (classify_task(p) == TASK_CPU_HOG) {{
\t\tscx_bpf_dsq_insert(p, BACKGROUND_DSQ, BACKGROUND_SLICE_NS,
\t\t\t\t    enq_flags);
\t}} else {{
\t\tscx_bpf_dsq_insert(p, SCX_DSQ_GLOBAL, DEFAULT_SLICE_NS,
\t\t\t\t    enq_flags);
\t}}
}}

void BPF_STRUCT_OPS({sched_name}_dispatch, s32 cpu, struct task_struct *prev)
{{
\t/* Background DSQ drained only when GLOBAL is empty */
\tscx_bpf_dsq_move_to_local(BACKGROUND_DSQ);
}}

void BPF_STRUCT_OPS({sched_name}_running, struct task_struct *p)
{{
\tif (classify_task(p) == TASK_CPU_HOG) {{
\t\tu32 key = bpf_get_smp_processor_id();
\t\tu8 val = 1;
\t\tu64 now = bpf_ktime_get_ns();
\t\tbpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
\t\tbpf_map_update_elem(&bg_start_ns, &key, &now, BPF_ANY);
\t}}
}}

void BPF_STRUCT_OPS({sched_name}_stopping, struct task_struct *p,
\t\t    bool runnable)
{{
\tif (classify_task(p) == TASK_CPU_HOG) {{
\t\tu32 key = bpf_get_smp_processor_id();
\t\tu8 val = 0;
\t\tbpf_map_update_elem(&bg_running, &key, &val, BPF_ANY);
\t}}
}}

s32 BPF_STRUCT_OPS_SLEEPABLE({sched_name}_init)
{{
\tnr_cpus = scx_bpf_nr_cpu_ids();
\treturn scx_bpf_create_dsq(BACKGROUND_DSQ, -1);
}}

void BPF_STRUCT_OPS({sched_name}_exit, struct scx_exit_info *ei)
{{
\tUEI_RECORD(uei, ei);
}}

SCX_OPS_DEFINE({sched_name}_ops,
\t       .select_cpu\t= (void *){sched_name}_select_cpu,
\t       .enqueue\t\t= (void *){sched_name}_enqueue,
\t       .dispatch\t= (void *){sched_name}_dispatch,
\t       .running\t\t= (void *){sched_name}_running,
\t       .stopping\t= (void *){sched_name}_stopping,
\t       .init\t\t= (void *){sched_name}_init,
\t       .exit\t\t= (void *){sched_name}_exit,
\t       .name\t\t= "{sched_name}");
"""

PATTERN_MAP = {
    "simple_dual_dsq": TEMPLATE_A,
    "selective_preemption": TEMPLATE_B,
    "asymmetric_task_storage": TEMPLATE_C,
}


def generate_scheduler(manifest, pattern, sched_name):
    """Generate a .bpf.c scheduler from manifest and pattern.

    Returns: generated C source code as a string.
    """
    bg_prefixes = extract_bg_prefixes(manifest)
    fg_prefixes = extract_fg_prefixes(manifest)

    if not bg_prefixes:
        print("Warning: no background threads in manifest. "
              "Generated scheduler will classify everything as foreground.",
              file=sys.stderr)

    # Generate thread comment block
    bg_comments = "\n".join(
        f" *   {name_pattern} (prefix=\"{prefix}\", len={length})"
        for prefix, length, name_pattern in bg_prefixes
    ) if bg_prefixes else " *   (none)"

    fg_comments = "\n".join(
        f" *   {name_pattern} (prefix=\"{prefix}\", len={length})"
        for prefix, length, name_pattern in fg_prefixes
    ) if fg_prefixes else " *   (default: all non-background)"

    # Use a sanitized function name (replace hyphens, etc.)
    fn_name = sched_name.replace("-", "_")

    template = PATTERN_MAP.get(pattern)
    if template is None:
        print(f"Error: unknown pattern '{pattern}'. "
              f"Available: {', '.join(PATTERN_MAP.keys())}",
              file=sys.stderr)
        sys.exit(1)

    if pattern == "asymmetric_task_storage":
        # Pattern C uses classify_task() instead of is_*_background()
        classify_fn = generate_classify_task_fn(fn_name, bg_prefixes, fg_prefixes)
        return template.format(
            sched_name=sched_name,
            fn_name=fn_name,
            bg_thread_comments=bg_comments,
            fg_thread_comments=fg_comments,
            classify_task_fn=classify_fn,
        )
    else:
        # Pattern A and B use is_*_background()
        class_fn = generate_classification_fn(fn_name, bg_prefixes)
        return template.format(
            sched_name=sched_name,
            fn_name=fn_name,
            bg_thread_comments=bg_comments,
            classification_fn=class_fn,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Stage 3: Generate BPF scheduler skeleton from manifest")
    parser.add_argument("manifest", help="Path to Thread Manifest JSON")
    parser.add_argument("--pattern", required=True,
                        choices=list(PATTERN_MAP.keys()),
                        help="Scheduling pattern to use")
    parser.add_argument("--name", required=True,
                        help="Scheduler name (e.g., redis_aware)")
    parser.add_argument("--output", default="",
                        help="Output .bpf.c file path (default: stdout)")
    args = parser.parse_args()

    if not os.path.exists(args.manifest):
        print(f"Error: manifest not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    manifest = load_json(args.manifest)
    source = generate_scheduler(manifest, args.pattern, args.name)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w") as f:
            f.write(source)
        print(f"Generated: {args.output}", file=sys.stderr)
        print(f"Pattern: {args.pattern}", file=sys.stderr)
        print(f"Background thread prefixes: "
              f"{len(extract_bg_prefixes(manifest))}", file=sys.stderr)
    else:
        print(source)


if __name__ == "__main__":
    main()
