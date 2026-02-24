#!/bin/bash
# redis_bench_compare.sh — A/B comparison: CFS vs redis_aware scheduler
#
# Measures Redis GET/SET latency under background persistence pressure
# (BGSAVE + BGREWRITEAOF) to demonstrate the scheduler's ability to
# prioritize the latency-critical main event loop.
#
# Usage: sudo ./redis_bench_compare.sh [num_runs]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REDIS_SERVER="$SCRIPT_DIR/redis-src/src/redis-server"
REDIS_CLI="$SCRIPT_DIR/redis-src/src/redis-cli"
REDIS_BENCHMARK="$SCRIPT_DIR/redis-src/src/redis-benchmark"
LOADER="$SCRIPT_DIR/../../mcp/new_sched/loader"
SCHEDULER_OBJ="$SCRIPT_DIR/redis_aware.bpf.o"
RESULTS_DIR="$SCRIPT_DIR/results"

NUM_RUNS="${1:-3}"
REDIS_PORT=6399
BENCHMARK_CLIENTS=50
BENCHMARK_REQUESTS=500000
BENCHMARK_DATASIZE=256
BENCHMARK_KEYSPACE=100000
POPULATE_KEYS=1000000

# IO threads for Redis (creates contention with bio threads)
IO_THREADS=4

mkdir -p "$RESULTS_DIR"

cleanup() {
    echo "Cleaning up..."
    # Kill background pressure loop
    kill "$PRESSURE_PID" 2>/dev/null || true
    wait "$PRESSURE_PID" 2>/dev/null || true
    kill "$STRESS_PID" 2>/dev/null || true
    wait "$STRESS_PID" 2>/dev/null || true
    pkill -f "stress-ng" 2>/dev/null || true
    # Stop Redis
    "$REDIS_CLI" -p "$REDIS_PORT" shutdown nosave 2>/dev/null || true
    sleep 1
    pkill -f "redis-server.*:$REDIS_PORT" 2>/dev/null || true
    # Stop scheduler
    pkill -f "loader.*redis_aware" 2>/dev/null || true
    sleep 1
}
trap cleanup EXIT

PRESSURE_PID=""
STRESS_PID=""

# Number of stress-ng CPU workers to create oversubscription (threads > CPUs)
STRESS_WORKERS=12

start_redis() {
    echo "Starting Redis on port $REDIS_PORT..."
    # Kill any existing instance on this port
    "$REDIS_CLI" -p "$REDIS_PORT" shutdown nosave 2>/dev/null || true
    pkill -f "redis-server.*:$REDIS_PORT" 2>/dev/null || true
    sleep 1

    "$REDIS_SERVER" \
        --port "$REDIS_PORT" \
        --io-threads "$IO_THREADS" \
        --io-threads-do-reads yes \
        --appendonly yes \
        --appendfsync everysec \
        --save "" \
        --protected-mode no \
        --loglevel warning \
        --dir /tmp/redis_bench_test \
        --daemonize yes \
        --pidfile /tmp/redis_bench_test/redis.pid

    # Wait for Redis to be ready
    for i in $(seq 1 30); do
        if "$REDIS_CLI" -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; then
            echo "Redis is ready."
            return 0
        fi
        sleep 0.5
    done
    echo "ERROR: Redis failed to start"
    return 1
}

populate_data() {
    echo "Populating $POPULATE_KEYS keys (${BENCHMARK_DATASIZE}B values)..."
    "$REDIS_BENCHMARK" -p "$REDIS_PORT" -t set \
        -n "$POPULATE_KEYS" -d "$BENCHMARK_DATASIZE" \
        -r "$BENCHMARK_KEYSPACE" -q --threads 4 2>/dev/null
    echo "Population complete. DB size: $("$REDIS_CLI" -p "$REDIS_PORT" dbsize)"
}

# Background persistence pressure: continuously trigger BGSAVE + BGREWRITEAOF
start_pressure() {
    (
        while true; do
            "$REDIS_CLI" -p "$REDIS_PORT" bgsave 2>/dev/null || true
            sleep 0.5
            "$REDIS_CLI" -p "$REDIS_PORT" bgrewriteaof 2>/dev/null || true
            sleep 0.5
        done
    ) &
    PRESSURE_PID=$!
    echo "Background persistence pressure started (PID=$PRESSURE_PID)"

    # CPU stress workers to create oversubscription
    stress-ng --cpu "$STRESS_WORKERS" --cpu-method matrixprod --quiet &
    STRESS_PID=$!
    echo "CPU stress workers started ($STRESS_WORKERS workers, PID=$STRESS_PID)"
}

stop_pressure() {
    if [ -n "$PRESSURE_PID" ]; then
        kill "$PRESSURE_PID" 2>/dev/null || true
        wait "$PRESSURE_PID" 2>/dev/null || true
        PRESSURE_PID=""
    fi
    if [ -n "$STRESS_PID" ]; then
        kill "$STRESS_PID" 2>/dev/null || true
        wait "$STRESS_PID" 2>/dev/null || true
        STRESS_PID=""
    fi
}

run_benchmark() {
    local label="$1"
    local output_file="$2"

    echo "  Running benchmark ($label)..."
    "$REDIS_BENCHMARK" -p "$REDIS_PORT" \
        -t get,set \
        -c "$BENCHMARK_CLIENTS" \
        -n "$BENCHMARK_REQUESTS" \
        -r "$BENCHMARK_KEYSPACE" \
        -d "$BENCHMARK_DATASIZE" \
        --csv \
        2>/dev/null > "$output_file"

    echo "  Results saved to $output_file"
}

start_scheduler() {
    echo "Loading redis_aware scheduler..."
    "$LOADER" "$SCHEDULER_OBJ" &
    sleep 2
    local state
    state=$(cat /sys/kernel/sched_ext/state 2>/dev/null || echo "unknown")
    if [ "$state" = "enabled" ]; then
        echo "Scheduler loaded and enabled."
    else
        echo "WARNING: Scheduler state is '$state'"
    fi
}

stop_scheduler() {
    echo "Stopping redis_aware scheduler..."
    pkill -f "loader.*redis_aware" 2>/dev/null || true
    sleep 2
}

parse_csv_latency() {
    # redis-benchmark CSV format:
    # "test","rps","avg_latency_ms","min_latency_ms","p50_latency_ms","p95_latency_ms","p99_latency_ms","max_latency_ms"
    local file="$1"
    local test="$2"
    # Extract the line for the given test
    grep "\"$test\"" "$file" || echo "\"$test\",0,0,0,0,0,0,0"
}

echo "============================================="
echo "Redis Benchmark: CFS vs redis_aware scheduler"
echo "============================================="
echo "Configuration:"
echo "  Runs per scheduler: $NUM_RUNS"
echo "  Clients: $BENCHMARK_CLIENTS"
echo "  Requests: $BENCHMARK_REQUESTS"
echo "  Data size: ${BENCHMARK_DATASIZE}B"
echo "  IO threads: $IO_THREADS"
echo "  Stress workers: $STRESS_WORKERS (CPU oversubscription)"
echo "  Background pressure: BGSAVE + BGREWRITEAOF continuous"
echo ""

# Prepare working directory
rm -rf /tmp/redis_bench_test && mkdir -p /tmp/redis_bench_test

# --- CFS Baseline ---
echo "========== CFS BASELINE =========="
start_redis
populate_data

for run in $(seq 1 "$NUM_RUNS"); do
    echo ""
    echo "--- CFS Run $run/$NUM_RUNS ---"

    # Flush AOF to start fresh
    "$REDIS_CLI" -p "$REDIS_PORT" bgrewriteaof 2>/dev/null || true
    sleep 2

    start_pressure
    sleep 1  # Let pressure ramp up
    run_benchmark "CFS run $run" "$RESULTS_DIR/cfs_run${run}.csv"
    stop_pressure
    sleep 2
done

# Stop Redis for CFS
"$REDIS_CLI" -p "$REDIS_PORT" shutdown nosave 2>/dev/null || true
sleep 2

# --- redis_aware Scheduler ---
echo ""
echo "========== redis_aware SCHEDULER =========="

# Re-create working directory
rm -rf /tmp/redis_bench_test && mkdir -p /tmp/redis_bench_test

start_scheduler
start_redis
populate_data

for run in $(seq 1 "$NUM_RUNS"); do
    echo ""
    echo "--- redis_aware Run $run/$NUM_RUNS ---"

    "$REDIS_CLI" -p "$REDIS_PORT" bgrewriteaof 2>/dev/null || true
    sleep 2

    start_pressure
    sleep 1
    run_benchmark "redis_aware run $run" "$RESULTS_DIR/redis_aware_run${run}.csv"
    stop_pressure
    sleep 2
done

"$REDIS_CLI" -p "$REDIS_PORT" shutdown nosave 2>/dev/null || true
sleep 1
stop_scheduler

# --- Parse and summarize results ---
echo ""
echo "============================================="
echo "RESULTS SUMMARY"
echo "============================================="
echo ""

for test in GET SET; do
    echo "--- $test ---"
    printf "%-20s %10s %10s %10s %10s %10s %10s\n" \
        "Scheduler" "RPS" "Avg(ms)" "P50(ms)" "P95(ms)" "P99(ms)" "Max(ms)"
    printf "%-20s %10s %10s %10s %10s %10s %10s\n" \
        "---" "---" "---" "---" "---" "---" "---"

    for sched in cfs redis_aware; do
        total_rps=0
        total_avg=0
        total_p50=0
        total_p95=0
        total_p99=0
        total_max=0
        count=0

        for run in $(seq 1 "$NUM_RUNS"); do
            file="$RESULTS_DIR/${sched}_run${run}.csv"
            if [ -f "$file" ]; then
                line=$(parse_csv_latency "$file" "$test")
                rps=$(echo "$line" | cut -d',' -f2 | tr -d '"')
                avg=$(echo "$line" | cut -d',' -f3 | tr -d '"')
                p50=$(echo "$line" | cut -d',' -f5 | tr -d '"')
                p95=$(echo "$line" | cut -d',' -f6 | tr -d '"')
                p99=$(echo "$line" | cut -d',' -f7 | tr -d '"')
                max=$(echo "$line" | cut -d',' -f8 | tr -d '"')

                total_rps=$(echo "$total_rps + $rps" | bc 2>/dev/null || echo "0")
                total_avg=$(echo "$total_avg + $avg" | bc 2>/dev/null || echo "0")
                total_p50=$(echo "$total_p50 + $p50" | bc 2>/dev/null || echo "0")
                total_p95=$(echo "$total_p95 + $p95" | bc 2>/dev/null || echo "0")
                total_p99=$(echo "$total_p99 + $p99" | bc 2>/dev/null || echo "0")
                total_max=$(echo "$total_max + $max" | bc 2>/dev/null || echo "0")
                count=$((count + 1))
            fi
        done

        if [ "$count" -gt 0 ]; then
            avg_rps=$(echo "scale=1; $total_rps / $count" | bc 2>/dev/null || echo "0")
            avg_avg=$(echo "scale=3; $total_avg / $count" | bc 2>/dev/null || echo "0")
            avg_p50=$(echo "scale=3; $total_p50 / $count" | bc 2>/dev/null || echo "0")
            avg_p95=$(echo "scale=3; $total_p95 / $count" | bc 2>/dev/null || echo "0")
            avg_p99=$(echo "scale=3; $total_p99 / $count" | bc 2>/dev/null || echo "0")
            avg_max=$(echo "scale=3; $total_max / $count" | bc 2>/dev/null || echo "0")

            printf "%-20s %10s %10s %10s %10s %10s %10s\n" \
                "$sched" "$avg_rps" "$avg_avg" "$avg_p50" "$avg_p95" "$avg_p99" "$avg_max"
        fi
    done
    echo ""
done

# Save raw results for later analysis
echo "Raw CSV files saved to $RESULTS_DIR/"
ls -la "$RESULTS_DIR/"*.csv 2>/dev/null || true
echo ""
echo "Done."
