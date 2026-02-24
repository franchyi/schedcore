#!/bin/bash
# nginx_bench_compare.sh — A/B comparison: CFS vs nginx_aware scheduler
#
# Measures Nginx HTTP latency under CPU oversubscription (stress-ng competing
# with nginx workers) to demonstrate the scheduler's ability to prioritize
# nginx worker processes.
#
# Usage: sudo ./nginx_bench_compare.sh [num_runs]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LEGACY_DIR="$SCRIPT_DIR/../schedcp_legacy/nginx"
NGINX_SRC="$LEGACY_DIR/nginx"
NGINX_BIN="$NGINX_SRC/objs/nginx"
WRK2_DIR="$SCRIPT_DIR/wrk2"
WRK2_BIN="$WRK2_DIR/wrk"
LOADER="$SCRIPT_DIR/../../mcp/new_sched/loader"
SCHEDULER_OBJ="$SCRIPT_DIR/nginx_aware.bpf.o"
RESULTS_DIR="$SCRIPT_DIR/results"

NUM_RUNS="${1:-3}"
NGINX_PORT=8080
NGINX_WORKERS=16
STRESS_WORKERS=24
WRK_THREADS=8
WRK_CONNECTIONS=200
WRK_DURATION=30
WRK_RATE=50000

# Working directories
NGINX_WORK="$SCRIPT_DIR/nginx-work"
HTML_DIR="$NGINX_WORK/html"
NGINX_CONF="$NGINX_WORK/nginx.conf"
NGINX_PID="$NGINX_WORK/nginx.pid"

mkdir -p "$RESULTS_DIR"

STRESS_PID=""

cleanup() {
    echo "Cleaning up..."
    # Stop stress-ng
    if [ -n "$STRESS_PID" ]; then
        kill "$STRESS_PID" 2>/dev/null || true
        wait "$STRESS_PID" 2>/dev/null || true
    fi
    pkill -f "stress-ng" 2>/dev/null || true
    # Stop nginx
    "$NGINX_BIN" -s quit -c "$NGINX_CONF" 2>/dev/null || true
    sleep 1
    pkill -f "nginx.*$NGINX_PORT" 2>/dev/null || true
    # Stop scheduler
    pkill -f "loader.*nginx_aware" 2>/dev/null || true
    sleep 1
}
trap cleanup EXIT

# ============ BUILD DEPENDENCIES ============

build_nginx() {
    if [ -f "$NGINX_BIN" ]; then
        echo "Nginx already built at $NGINX_BIN"
        return 0
    fi

    echo "Building Nginx..."

    # Init submodule if needed
    if [ ! -f "$NGINX_SRC/auto/configure" ]; then
        echo "Initializing nginx submodule..."
        cd "$SCRIPT_DIR/../.."
        git submodule update --init workloads/schedcp_legacy/nginx/nginx
        cd "$SCRIPT_DIR"
    fi

    # Install build deps
    apt-get install -y build-essential zlib1g-dev libpcre3-dev libssl-dev 2>/dev/null || true

    cd "$NGINX_SRC"
    ./auto/configure \
        --prefix="$NGINX_WORK/install" \
        --sbin-path="$NGINX_SRC/objs/nginx" \
        --conf-path="$NGINX_CONF" \
        --pid-path="$NGINX_PID" \
        --lock-path="$NGINX_WORK/nginx.lock" \
        --error-log-path="$NGINX_WORK/error.log" \
        --http-log-path="$NGINX_WORK/access.log" \
        --with-http_stub_status_module \
        --with-threads \
        --http-client-body-temp-path="$NGINX_WORK/client_temp" \
        --http-proxy-temp-path="$NGINX_WORK/proxy_temp" \
        --http-fastcgi-temp-path="$NGINX_WORK/fastcgi_temp" \
        --http-uwsgi-temp-path="$NGINX_WORK/uwsgi_temp" \
        --http-scgi-temp-path="$NGINX_WORK/scgi_temp"
    make -j"$(nproc)"
    cd "$SCRIPT_DIR"
    echo "Nginx built successfully."
}

build_wrk2() {
    if [ -f "$WRK2_BIN" ]; then
        echo "wrk2 already built at $WRK2_BIN"
        return 0
    fi

    echo "Building wrk2..."
    if [ ! -d "$WRK2_DIR" ]; then
        git clone --depth=1 https://github.com/giltene/wrk2.git "$WRK2_DIR"
    fi
    cd "$WRK2_DIR"
    make -j"$(nproc)"
    cd "$SCRIPT_DIR"
    echo "wrk2 built successfully."
}

compile_scheduler() {
    if [ -f "$SCHEDULER_OBJ" ]; then
        echo "Scheduler already compiled at $SCHEDULER_OBJ"
        return 0
    fi

    echo "Compiling nginx_aware BPF scheduler..."
    make -C "$SCRIPT_DIR" -f "$SCRIPT_DIR/../../mcp/new_sched/Makefile" \
        BPF_SRC=nginx_aware.bpf.c BPF_OBJ=nginx_aware.bpf.o nginx_aware.bpf.o
    echo "Scheduler compiled successfully."
}

setup_nginx_workdir() {
    mkdir -p "$NGINX_WORK" "$HTML_DIR"
    mkdir -p "$NGINX_WORK/client_temp" "$NGINX_WORK/proxy_temp"
    mkdir -p "$NGINX_WORK/fastcgi_temp" "$NGINX_WORK/uwsgi_temp" "$NGINX_WORK/scgi_temp"

    # Create test HTML page
    echo "<html><body><h1>Nginx Benchmark Test Page</h1><p>$(head -c 4096 /dev/urandom | base64)</p></body></html>" > "$HTML_DIR/index.html"

    # Copy mime.types
    cp "$LEGACY_DIR/mime.types" "$NGINX_WORK/mime.types"

    # Generate nginx.conf with correct paths
    sed "s|NGINX_HTML_ROOT|$HTML_DIR|g" "$SCRIPT_DIR/nginx.conf" > "$NGINX_CONF"
}

# ============ NGINX CONTROL ============

start_nginx() {
    echo "Starting Nginx on port $NGINX_PORT with $NGINX_WORKERS workers..."
    # Kill any existing instance
    "$NGINX_BIN" -s quit -c "$NGINX_CONF" 2>/dev/null || true
    pkill -f "nginx.*master" 2>/dev/null || true
    sleep 1

    "$NGINX_BIN" -c "$NGINX_CONF"

    # Wait for nginx to be ready
    for i in $(seq 1 30); do
        if curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$NGINX_PORT/" 2>/dev/null | grep -q "200"; then
            echo "Nginx is ready."
            return 0
        fi
        sleep 0.5
    done
    echo "ERROR: Nginx failed to start"
    return 1
}

stop_nginx() {
    "$NGINX_BIN" -s quit -c "$NGINX_CONF" 2>/dev/null || true
    sleep 2
    pkill -f "nginx.*master" 2>/dev/null || true
    sleep 1
}

# ============ STRESS / SCHEDULER ============

start_stress() {
    echo "Starting stress-ng: $STRESS_WORKERS CPU workers (matrixprod)..."
    stress-ng --cpu "$STRESS_WORKERS" --cpu-method matrixprod --quiet &
    STRESS_PID=$!
    echo "  stress-ng PID=$STRESS_PID"
}

stop_stress() {
    if [ -n "$STRESS_PID" ]; then
        kill "$STRESS_PID" 2>/dev/null || true
        wait "$STRESS_PID" 2>/dev/null || true
        STRESS_PID=""
    fi
    pkill -f "stress-ng" 2>/dev/null || true
}

start_scheduler() {
    echo "Loading nginx_aware scheduler..."
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
    echo "Stopping nginx_aware scheduler..."
    pkill -f "loader.*nginx_aware" 2>/dev/null || true
    sleep 2
}

# ============ BENCHMARK ============

run_wrk2() {
    local label="$1"
    local output_file="$2"

    echo "  Running wrk2 ($label): ${WRK_THREADS}T, ${WRK_CONNECTIONS}C, ${WRK_DURATION}s, ${WRK_RATE} req/s..."
    "$WRK2_BIN" -t"$WRK_THREADS" -c"$WRK_CONNECTIONS" -d"${WRK_DURATION}s" \
        -R"$WRK_RATE" --latency \
        "http://127.0.0.1:$NGINX_PORT/" \
        > "$output_file" 2>&1

    echo "  Results saved to $output_file"
}

parse_wrk2_latency() {
    # Extract latency percentiles from wrk2 output
    local file="$1"
    local pct="$2"

    # wrk2 --latency output format:
    #   50.000%    1.23ms
    #   99.000%    5.67ms
    grep -E "^\s+${pct}" "$file" | awk '{print $2}' | head -1
}

parse_wrk2_rps() {
    local file="$1"
    grep "Requests/sec:" "$file" | awk '{print $2}'
}

latency_to_us() {
    # Convert wrk2 latency string (e.g. "1.23ms", "456.00us", "1.20s") to microseconds
    local val="$1"
    if [ -z "$val" ]; then
        echo "0"
        return
    fi

    local num unit
    num=$(echo "$val" | sed 's/[a-zA-Z]*$//')
    unit=$(echo "$val" | sed 's/[0-9.]*//')

    case "$unit" in
        us) echo "$num" ;;
        ms) echo "$num * 1000" | bc ;;
        s)  echo "$num * 1000000" | bc ;;
        *)  echo "0" ;;
    esac
}

# ============ MAIN ============

echo "============================================="
echo "Nginx Benchmark: CFS vs nginx_aware scheduler"
echo "============================================="
echo "Configuration:"
echo "  Runs per scheduler: $NUM_RUNS"
echo "  Nginx workers: $NGINX_WORKERS"
echo "  Stress workers: $STRESS_WORKERS (CPU oversubscription)"
echo "  wrk2: ${WRK_THREADS}T, ${WRK_CONNECTIONS}C, ${WRK_DURATION}s, ${WRK_RATE} req/s"
echo ""

# Build everything
build_nginx
build_wrk2
compile_scheduler
setup_nginx_workdir

# --- CFS Baseline ---
echo ""
echo "========== CFS BASELINE =========="
start_nginx

for run in $(seq 1 "$NUM_RUNS"); do
    echo ""
    echo "--- CFS Run $run/$NUM_RUNS ---"
    start_stress
    sleep 2  # Let stress ramp up
    run_wrk2 "CFS run $run" "$RESULTS_DIR/cfs_run${run}.txt"
    stop_stress
    sleep 2
done

stop_nginx

# --- nginx_aware Scheduler ---
echo ""
echo "========== nginx_aware SCHEDULER =========="
start_scheduler
start_nginx

for run in $(seq 1 "$NUM_RUNS"); do
    echo ""
    echo "--- nginx_aware Run $run/$NUM_RUNS ---"
    start_stress
    sleep 2
    run_wrk2 "nginx_aware run $run" "$RESULTS_DIR/nginx_aware_run${run}.txt"
    stop_stress
    sleep 2
done

stop_nginx
stop_scheduler

# --- Parse and summarize results ---
echo ""
echo "============================================="
echo "RESULTS SUMMARY"
echo "============================================="
echo ""

printf "%-20s %12s %12s %12s %12s %12s\n" \
    "Scheduler" "RPS" "P50" "P99" "P99.9" "Max"
printf "%-20s %12s %12s %12s %12s %12s\n" \
    "---" "---" "---" "---" "---" "---"

for sched in cfs nginx_aware; do
    total_rps=0
    count=0
    # Collect latency values
    declare -a p50_vals=() p99_vals=() p999_vals=() max_vals=()

    for run in $(seq 1 "$NUM_RUNS"); do
        file="$RESULTS_DIR/${sched}_run${run}.txt"
        if [ -f "$file" ]; then
            rps=$(parse_wrk2_rps "$file")
            p50=$(parse_wrk2_latency "$file" "50.000%")
            p99=$(parse_wrk2_latency "$file" "99.000%")
            p999=$(parse_wrk2_latency "$file" "99.900%")
            max_lat=$(parse_wrk2_latency "$file" "99.999%")

            if [ -n "$rps" ]; then
                total_rps=$(echo "$total_rps + $rps" | bc 2>/dev/null || echo "0")
                count=$((count + 1))
            fi

            # Store last run values for display (representative)
            last_p50="$p50"
            last_p99="$p99"
            last_p999="$p999"
            last_max="$max_lat"
        fi
    done

    if [ "$count" -gt 0 ]; then
        avg_rps=$(echo "scale=1; $total_rps / $count" | bc 2>/dev/null || echo "0")
        printf "%-20s %12s %12s %12s %12s %12s\n" \
            "$sched" "$avg_rps" "${last_p50:-N/A}" "${last_p99:-N/A}" "${last_p999:-N/A}" "${last_max:-N/A}"
    fi
done

echo ""

# Show per-run detail
echo "--- Per-run Detail ---"
for sched in cfs nginx_aware; do
    echo ""
    echo "[$sched]"
    for run in $(seq 1 "$NUM_RUNS"); do
        file="$RESULTS_DIR/${sched}_run${run}.txt"
        if [ -f "$file" ]; then
            rps=$(parse_wrk2_rps "$file")
            p50=$(parse_wrk2_latency "$file" "50.000%")
            p99=$(parse_wrk2_latency "$file" "99.000%")
            p999=$(parse_wrk2_latency "$file" "99.900%")
            printf "  Run %d: RPS=%-10s P50=%-10s P99=%-10s P99.9=%-10s\n" \
                "$run" "${rps:-N/A}" "${p50:-N/A}" "${p99:-N/A}" "${p999:-N/A}"
        fi
    done
done

echo ""
echo "Raw wrk2 output files saved to $RESULTS_DIR/"
ls -la "$RESULTS_DIR/"*.txt 2>/dev/null || true
echo ""
echo "Done."
