# Stage 1: Thread Discovery for {{APP_NAME}}

## Task

You are classifying threads in **{{APP_NAME}}** ({{DESCRIPTION}}) based on a static analysis report from the source code at `{{SOURCE_PATH}}`.

A static analyzer has already found all thread naming and creation sites. Your job: **classify** each thread type as **FOREGROUND** (latency-critical, serves user requests) or **BACKGROUND** (can tolerate scheduling delay, does maintenance/bulk work).

The output is a **Thread Manifest** — a JSON document that maps each thread type to its scheduling role and identification method. This manifest will be consumed by Stage 2 to generate a BPF kernel scheduler.

## Static Analysis Report

The following thread naming and creation sites were found by tree-sitter static analysis:

```json
{{THREAD_REPORT}}
```

## Classification Instructions

For each thread naming site in the report above:

### Step 1: Understand Thread Purpose

Read the `context_snippet` for each entry to understand:
- **What work does this thread do?** (serve requests, compact data, flush logs, etc.)
- **Is it on the request path?** (directly handles user/client operations)
- **What happens if it's delayed?** (request latency increases vs. background task takes longer)

For thread naming sites with `is_constant: false` (dynamic names), determine the **prefix pattern** — the fixed bytes that are common across all instances. For example, if the name is constructed as `"rocksdb:" + priority`, the prefix is `"rocksdb:"` (8 bytes).

### Step 2: Cross-Reference Creation and Naming

Match `thread_creates` entries with `thread_names` entries:
- A `pthread_create` with `start_routine: "worker_func"` may call `pthread_setname_np` inside that function
- The `context_snippet` usually reveals what the thread does

### Step 3: Classify Each Thread Type

Classify each thread:
- **FOREGROUND**: Thread is on the latency-critical path. Delaying it increases user-visible latency (e.g., query handlers, event loop threads, worker threads serving requests).
- **BACKGROUND**: Thread does maintenance, bulk, or asynchronous work. Delaying it does not directly affect request latency (e.g., compaction, log flushing, checkpointing, garbage collection).

### Step 4: Determine Identification

For each thread type, determine how to identify it at runtime via `task_struct->comm`:
- **comm_prefix**: Thread name starts with a fixed prefix (e.g., `"rocksdb:"` → prefix length 8). Use when threads have dynamic suffixes.
- **comm_exact**: Thread name is a fixed string (e.g., `"redis-server"` → exact match, length 12). Use when the name is always the same.

### Step 5: Determine Default Role

Decide what role unmatched threads should receive:
- `"foreground"` (recommended): Unmatched threads use the kernel default fast path. This is safe because the BPF scheduler only intervenes for explicitly matched threads.
- `"background"`: Only if the application has a very clear foreground/background split where most threads are background.

## Output Format

Produce a **Thread Manifest** as a JSON document conforming to the schema in `pipeline/thread_manifest.schema.json`.

```json
{
  "application": "{{APP_NAME}}",
  "source_path": "{{SOURCE_PATH}}",
  "language": "{{LANGUAGE}}",
  "identification_method": "comm",
  "default_role": "foreground",
  "rationale": "One paragraph explaining why these threads have different latency requirements and how deprioritizing background threads will reduce tail latency.",
  "threads": [
    {
      "name_pattern": "human-readable pattern (e.g., 'rocksdb:low*', 'bio_*')",
      "role": "foreground | background",
      "purpose": "What this thread does",
      "identification": {
        "type": "comm_prefix | comm_exact",
        "comm_prefix": "the fixed prefix bytes to match",
        "comm_length": 8
      }
    }
  ]
}
```

### Classification Rules

1. **When in doubt, classify as FOREGROUND.** The BPF scheduler only intervenes for BACKGROUND threads; FOREGROUND threads use the kernel's default fast path. Mis-classifying a foreground thread as background will hurt latency.
2. **Look for asymmetry.** If all threads do the same work (e.g., a pure worker pool with no background tasks), there is no scheduling opportunity — report this in the rationale and produce an empty `threads` array.
3. **Prefer comm_prefix over comm_exact** when threads have dynamic suffixes (e.g., `"rocksdb:low0"`, `"rocksdb:low1"` → prefix `"rocksdb:"`, length 8).
4. **Include all background thread types.** Missing a background thread type means it will be treated as foreground and receive priority — this is safe but suboptimal.
5. **Set default_role to "foreground"** unless you have a specific reason to default to background.
