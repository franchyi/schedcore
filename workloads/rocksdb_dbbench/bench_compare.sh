#!/bin/bash
# A/B comparison: CFS vs v7 rocksdb_aware scheduler
# Each run gets a fresh DB to eliminate state divergence

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DB_PATH="/tmp/rocksdb_bench_test"
DB_BENCH="$SCRIPT_DIR/rocksdb/db_bench"
LOADER="$PROJECT_ROOT/bpf_loader/loader"
SCHED="$SCRIPT_DIR/rocksdb_aware.bpf.o"
RESULTS_DIR="$SCRIPT_DIR/results"
RUNS=3

mkdir -p "$RESULTS_DIR"

populate_db() {
    rm -rf "$DB_PATH" && mkdir -p "$DB_PATH"
    $DB_BENCH --benchmarks=fillrandom --db="$DB_PATH" \
        --num=5000000 --max_background_compactions=0 \
        --level0_file_num_compaction_trigger=1000 --value_size=256 \
        2>&1 > /dev/null
    echo "DB populated"
}

run_bench() {
    $DB_BENCH \
        --benchmarks=readrandomwriterandom \
        --db="$DB_PATH" \
        --use_existing_db=1 \
        --threads=16 \
        --readwritepercent=90 \
        --max_background_compactions=32 \
        --max_background_flushes=4 \
        --cache_size=1048576 \
        --value_size=4096 \
        --level0_file_num_compaction_trigger=4 \
        --duration=30 \
        --statistics=1 \
        --histogram=1 \
        2>&1
}

echo "=== RocksDB Scheduler Comparison ==="
echo "Config: 16 reader threads, 32 bg compactions, 1MB cache, 4KB values"
echo "Duration: 30s per run, $RUNS runs each"
echo ""

# CFS runs
for i in $(seq 1 $RUNS); do
    echo "--- CFS Run $i ---"
    populate_db
    run_bench | grep -E "Percentiles|readrandomwriterandom" | tee "$RESULTS_DIR/cfs_run${i}.txt"
    echo ""
done

# v7 runs
for i in $(seq 1 $RUNS); do
    echo "--- v7 Run $i ---"
    populate_db
    sudo "$LOADER" "$SCHED" 2>&1 &
    LOADER_PID=$!
    sleep 3
    state=$(sudo cat /sys/kernel/sched_ext/state)
    if [ "$state" != "enabled" ]; then
        echo "ERROR: Scheduler not enabled (state=$state)"
        sudo kill $LOADER_PID 2>/dev/null
        continue
    fi
    run_bench | grep -E "Percentiles|readrandomwriterandom" | tee "$RESULTS_DIR/v7_run${i}.txt"
    sudo kill $LOADER_PID 2>/dev/null
    wait $LOADER_PID 2>/dev/null
    sleep 2
    echo ""
done

echo "=== Results saved to $RESULTS_DIR ==="
