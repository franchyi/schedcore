#!/bin/bash

# Load the eBPF scheduler program
echo "Loading eBPF scheduler..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Load the program using bpftool
echo "Loading sched.bpf.o..."
bpftool prog load sched.bpf.o /sys/fs/bpf/sched_prog

# List loaded programs
echo -e "\nLoaded BPF programs:"
bpftool prog list | grep -E "sched|tracepoint|kprobe"

# Attach to tracepoints
echo -e "\nAttaching to tracepoints..."

# Get program IDs
SCHED_SWITCH_ID=$(bpftool prog list | grep "sched_switch" | awk '{print $1}' | tr -d ':')
SCHED_WAKEUP_ID=$(bpftool prog list | grep "sched_wakeup" | awk '{print $1}' | tr -d ':')
FINISH_TASK_ID=$(bpftool prog list | grep "finish_task_switch" | awk '{print $1}' | tr -d ':')

echo "Program IDs: switch=$SCHED_SWITCH_ID, wakeup=$SCHED_WAKEUP_ID, finish=$FINISH_TASK_ID"

# Watch the trace pipe
echo -e "\nMonitoring scheduler events (Ctrl+C to stop)..."
echo "Check /sys/kernel/debug/tracing/trace_pipe for output"
timeout 10 cat /sys/kernel/debug/tracing/trace_pipe || true

# Show map contents
echo -e "\nChecking BPF maps..."
bpftool map list | grep -E "sched_stats|cpu_switch_count"

echo -e "\nScheduler monitoring is running. Check trace_pipe for events."