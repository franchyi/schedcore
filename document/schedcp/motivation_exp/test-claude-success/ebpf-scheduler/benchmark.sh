#!/bin/bash

# Benchmark script for eBPF scheduler

set -e

echo "=== eBPF Scheduler Benchmark ==="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Error: This script must be run as root"
    exit 1
fi

# Function to run benchmark with a scheduler
run_benchmark() {
    local scheduler_name=$1
    local enable_cmd=$2
    local disable_cmd=$3
    
    echo "Testing with $scheduler_name scheduler..."
    
    # Enable scheduler if needed
    eval "$enable_cmd"
    
    # Run sysbench CPU benchmark
    echo "  CPU benchmark (single-threaded):"
    sysbench cpu --cpu-max-prime=20000 --time=10 run | grep -E "events per second|total time" | sed 's/^/    /'
    
    echo "  CPU benchmark (multi-threaded):"
    sysbench cpu --cpu-max-prime=20000 --threads=4 --time=10 run | grep -E "events per second|total time" | sed 's/^/    /'
    
    # Run memory benchmark
    echo "  Memory benchmark:"
    sysbench memory --memory-total-size=1G run | grep -E "transferred|total time" | sed 's/^/    /'
    
    # Disable scheduler if needed
    eval "$disable_cmd"
    
    echo
}

# Install sysbench if not available
if ! command -v sysbench &> /dev/null; then
    echo "Installing sysbench..."
    apt-get update && apt-get install -y sysbench
fi

# Kill any existing scheduler
pkill simple_scheduler 2>/dev/null || true

# Benchmark with default scheduler
run_benchmark "Default (CFS)" "true" "true"

# Start our eBPF scheduler
echo "Loading eBPF scheduler..."
./simple_scheduler &
SCHED_PID=$!
sleep 2

if ! kill -0 $SCHED_PID 2>/dev/null; then
    echo "Error: Scheduler failed to load"
    exit 1
fi

# Benchmark with eBPF scheduler
run_benchmark "Simple eBPF" "echo 1 > /sys/kernel/sched_ext/enabled" "echo 0 > /sys/kernel/sched_ext/enabled"

# Clean up
kill -SIGINT $SCHED_PID 2>/dev/null
wait $SCHED_PID 2>/dev/null

echo "=== Benchmark Complete ==="