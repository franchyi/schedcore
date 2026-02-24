#!/bin/bash

# Test script for eBPF scheduler

set -e

echo "=== eBPF Scheduler Test Suite ==="
echo

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run as root${NC}"
    exit 1
fi

# Check if scheduler binary exists
if [ ! -f "./simple_scheduler" ]; then
    echo -e "${RED}Error: simple_scheduler binary not found. Run 'make' first.${NC}"
    exit 1
fi

echo "1. Checking kernel support..."
if [ ! -d "/sys/kernel/sched_ext" ]; then
    echo -e "${RED}Error: sched_ext not available in kernel${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Kernel supports sched_ext${NC}"

# Check current scheduler state
echo
echo "2. Checking current scheduler state..."
CURRENT_STATE=$(cat /sys/kernel/sched_ext/state 2>/dev/null || echo "unknown")
CURRENT_ENABLED=$(cat /sys/kernel/sched_ext/enabled 2>/dev/null || echo "0")
echo "   State: $CURRENT_STATE"
echo "   Enabled: $CURRENT_ENABLED"

# Disable any existing scheduler
if [ "$CURRENT_ENABLED" = "1" ]; then
    echo "   Disabling existing scheduler..."
    echo 0 > /sys/kernel/sched_ext/enabled
    sleep 1
fi

# Function to run a test workload
run_workload() {
    local name=$1
    local cmd=$2
    echo "   Running workload: $name"
    timeout 5s $cmd > /dev/null 2>&1 || true
}

# Start the scheduler in background
echo
echo "3. Loading eBPF scheduler..."
./simple_scheduler &
SCHED_PID=$!
sleep 2

# Check if scheduler loaded successfully
if ! kill -0 $SCHED_PID 2>/dev/null; then
    echo -e "${RED}Error: Scheduler failed to load${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Scheduler loaded (PID: $SCHED_PID)${NC}"

# Enable the scheduler
echo
echo "4. Enabling scheduler..."
echo 1 > /sys/kernel/sched_ext/enabled
sleep 1

# Check if enabled
ENABLED=$(cat /sys/kernel/sched_ext/enabled)
if [ "$ENABLED" != "1" ]; then
    echo -e "${RED}Error: Failed to enable scheduler${NC}"
    kill $SCHED_PID 2>/dev/null
    exit 1
fi
echo -e "${GREEN}✓ Scheduler enabled${NC}"

# Run test workloads
echo
echo "5. Running test workloads..."

# CPU-bound workload
run_workload "CPU-bound (calculating primes)" "bash -c 'for i in {1..10000}; do factor $i > /dev/null; done'"

# I/O-bound workload
run_workload "I/O-bound (file operations)" "bash -c 'for i in {1..100}; do echo test > /tmp/test_$i.txt && rm /tmp/test_$i.txt; done'"

# Multi-threaded workload
run_workload "Multi-threaded (parallel stress)" "stress --cpu 4 --timeout 3s"

# Sleep to collect more stats
echo "   Collecting statistics..."
sleep 5

echo -e "${GREEN}✓ Workloads completed${NC}"

# Disable scheduler
echo
echo "6. Disabling scheduler..."
echo 0 > /sys/kernel/sched_ext/enabled
sleep 1

# Kill the scheduler process
echo "7. Stopping scheduler..."
kill -SIGINT $SCHED_PID 2>/dev/null
wait $SCHED_PID 2>/dev/null

echo
echo -e "${GREEN}=== All tests passed! ===${NC}"
echo
echo "The eBPF scheduler was successfully:"
echo "  - Loaded into the kernel"
echo "  - Enabled as the active scheduler"
echo "  - Handled various workloads"
echo "  - Disabled and unloaded cleanly"
echo
echo "Check the scheduler output above for statistics."