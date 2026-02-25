#!/usr/bin/env bash
# Run Stage 1 Thread Discovery (hybrid static analysis + LLM classification).
#
# Stage 1a: Tree-sitter static analysis (deterministic, free)
# Stage 1b: LLM classification (semantic, cheap)
#
# Usage:
#   ./run_stage1.sh <app_name> <source_path> <language> <description> [output_file]
#
# Example:
#   ./run_stage1.sh rocksdb workloads/rocksdb/rocksdb/ cpp \
#     "Embedded key-value store with LSM-tree architecture"
#
# Output: pipeline/results/<app_name>_generated_<timestamp>.json

set -euo pipefail

if [ $# -lt 4 ]; then
    echo "Usage: $0 <app_name> <source_path> <language> <description> [output_file]"
    echo ""
    echo "Arguments:"
    echo "  app_name     - Application name (e.g., rocksdb, redis, nginx)"
    echo "  source_path  - Path to application source code"
    echo "  language      - Primary language (c, cpp, java, go, rust)"
    echo "  description  - One-line description of the application"
    echo "  output_file  - Output JSON path (default: pipeline/results/<app_name>_generated_<timestamp>.json)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SCRIPT_DIR/stage1_thread_discovery.prompt.md"
STAGE1A="$SCRIPT_DIR/stage1a_static_analysis.py"

APP_NAME="$1"
SOURCE_PATH="$2"
LANGUAGE="$3"
DESCRIPTION="$4"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_FILE="${5:-${SCRIPT_DIR}/results/${APP_NAME}_generated_${TIMESTAMP}.json}"
CLAUDE_OUTPUT="/tmp/claude_stage1_${APP_NAME}_${TIMESTAMP}.json"
THREAD_REPORT="${SCRIPT_DIR}/results/${APP_NAME}_thread_report_${TIMESTAMP}.json"

if [ ! -f "$TEMPLATE" ]; then
    echo "Error: template not found at $TEMPLATE"
    exit 1
fi

if [ ! -f "$STAGE1A" ]; then
    echo "Error: stage1a script not found at $STAGE1A"
    exit 1
fi

if [ ! -d "$SOURCE_PATH" ]; then
    echo "Error: source path $SOURCE_PATH does not exist or is not a directory"
    exit 1
fi

echo "=== Stage 1: Thread Discovery for ${APP_NAME} ==="
echo "Source: ${SOURCE_PATH}"
echo "Output: ${OUTPUT_FILE}"
echo ""

# ─── Stage 1a: Static Analysis (deterministic, free) ───
echo "--- Stage 1a: Static Analysis ---"
STAGE1A_START=$(date +%s%N)

python3 "$STAGE1A" "$SOURCE_PATH" "$LANGUAGE" --summary > "$THREAD_REPORT"

STAGE1A_END=$(date +%s%N)
STAGE1A_MS=$(( (STAGE1A_END - STAGE1A_START) / 1000000 ))
echo "  Completed in ${STAGE1A_MS}ms"

# Extract summary counts from the report
NAMES_COUNT=$(python3 -c "import json; r=json.load(open('$THREAD_REPORT')); print(len(r['thread_names']))")
CREATES_COUNT=$(python3 -c "import json; r=json.load(open('$THREAD_REPORT')); print(len(r['thread_creates']))")
FILES_COUNT=$(python3 -c "import json; r=json.load(open('$THREAD_REPORT')); print(r['files_analyzed'])")
echo "  Files analyzed: ${FILES_COUNT}"
echo "  Thread naming sites: ${NAMES_COUNT}"
echo "  Thread creation sites: ${CREATES_COUNT}"
echo ""

# ─── Stage 1b: LLM Classification (semantic) ───
echo "--- Stage 1b: LLM Classification ---"

# Read the thread report JSON for template insertion
THREAD_REPORT_CONTENT=$(cat "$THREAD_REPORT")

# Fill template placeholders
FILLED_PROMPT=$(sed \
    -e "s|{{APP_NAME}}|${APP_NAME}|g" \
    -e "s|{{SOURCE_PATH}}|${SOURCE_PATH}|g" \
    -e "s|{{LANGUAGE}}|${LANGUAGE}|g" \
    -e "s|{{DESCRIPTION}}|${DESCRIPTION}|g" \
    "$TEMPLATE")

# Replace {{THREAD_REPORT}} placeholder with actual report content
# Use python for this since the report may contain characters that break sed
FILLED_PROMPT=$(python3 -c "
import sys
template = sys.stdin.read()
with open('$THREAD_REPORT') as f:
    report = f.read()
print(template.replace('{{THREAD_REPORT}}', report))
" <<< "$FILLED_PROMPT")

# Append instruction to output only JSON
FILLED_PROMPT="${FILLED_PROMPT}

---

**IMPORTANT: Output Instructions**

1. Analyze the static analysis report above — do NOT search the codebase yourself.
2. Classify each thread type based on the context snippets provided.
3. Output the Thread Manifest as a single JSON code block.
4. The JSON must conform to the schema in \`pipeline/thread_manifest.schema.json\`.
5. Write the final manifest JSON to: \`${OUTPUT_FILE}\`
"

# Run Claude Code in non-interactive mode
#   -p                            → print mode (non-interactive, exits when done)
#   --output-format json          → JSON envelope with usage stats
#   --permission-mode bypassPermissions → auto-approve all tool calls
#   --max-turns 10                → cap agentic loop (classification is simple)
# Output goes to temp file to avoid stdout capture issues in nested sessions
claude -p \
    --output-format json \
    --permission-mode bypassPermissions \
    --max-turns 10 \
    "$FILLED_PROMPT" > "$CLAUDE_OUTPUT" 2>/dev/null

# Parse results and save usage stats alongside the manifest
STATS_FILE="${OUTPUT_FILE%.json}_stats.json"

python3 -c "
import json, sys

try:
    data = json.load(open('$CLAUDE_OUTPUT'))
except (json.JSONDecodeError, FileNotFoundError) as e:
    print(f'Error parsing Claude output: {e}', file=sys.stderr)
    sys.exit(1)

# Print the text result
result = data.get('result', '')
print(result)
print()

# Extract usage stats
usage = data.get('usage', {})
input_tokens = usage.get('input_tokens', 0)
output_tokens = usage.get('output_tokens', 0)
cache_read = usage.get('cache_read_input_tokens', 0)
cache_create = usage.get('cache_creation_input_tokens', 0)
cost_usd = data.get('total_cost_usd', 0)
num_turns = data.get('num_turns', 0)
duration_ms = data.get('duration_ms', 0)

stats = {
    'stage1a_ms': $STAGE1A_MS,
    'stage1a_files_analyzed': $FILES_COUNT,
    'stage1a_thread_names': $NAMES_COUNT,
    'stage1a_thread_creates': $CREATES_COUNT,
    'input_tokens': input_tokens,
    'output_tokens': output_tokens,
    'total_tokens': input_tokens + output_tokens,
    'cache_read_tokens': cache_read,
    'cache_create_tokens': cache_create,
    'cost_usd': cost_usd,
    'num_turns': num_turns,
    'duration_seconds': round(duration_ms / 1000, 1),
}

# Save stats to file
with open('$STATS_FILE', 'w') as f:
    json.dump(stats, f, indent=2)

# Print usage stats
print('=== Usage Stats ===')
print(f'  Stage 1a:      {$STAGE1A_MS}ms (static analysis)')
print(f'  Input tokens:  {input_tokens:>10,}')
print(f'  Output tokens: {output_tokens:>10,}')
print(f'  Total tokens:  {input_tokens + output_tokens:>10,}')
if cache_read:
    print(f'  Cache read:    {cache_read:>10,}')
if cache_create:
    print(f'  Cache create:  {cache_create:>10,}')
print(f'  Cost (USD):       \${cost_usd:.4f}')
print(f'  Turns:            {num_turns}')
print(f'  Duration:         {duration_ms / 1000:.1f}s')
print(f'  Stats saved to:   $STATS_FILE')
"

echo ""
if [ -f "$OUTPUT_FILE" ]; then
    echo "=== Manifest written to ${OUTPUT_FILE} ==="
    echo ""
    python3 -m json.tool "$OUTPUT_FILE" 2>/dev/null || cat "$OUTPUT_FILE"
else
    echo "WARNING: Output file ${OUTPUT_FILE} was not created."
    echo "Check $CLAUDE_OUTPUT for the raw Claude response."
fi

# Clean up temp files (keep thread report in results/)
rm -f "$CLAUDE_OUTPUT"
echo "  Thread report: ${THREAD_REPORT}"
