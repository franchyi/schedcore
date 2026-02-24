# Testing and Benchmarking Infrastructure

## Table of Contents
1. [Overview](#overview)
2. [Testing Framework](#testing-framework)
3. [Unit Testing](#unit-testing)
4. [Integration Testing](#integration-testing)
5. [Stress Testing](#stress-testing)
6. [Performance Analysis](#performance-analysis)
7. [CI/CD Integration](#cicd-integration)
8. [Debugging and Validation](#debugging-and-validation)

## Overview

The SCX project provides a comprehensive testing infrastructure designed to ensure scheduler correctness, performance, and stability. The testing framework covers everything from unit tests for individual BPF functions to full system stress tests under various workloads.

### Testing Philosophy

1. **Safety First**: All potentially dangerous tests run in isolated VMs
2. **Comprehensive Coverage**: Multiple testing levels from unit to system
3. **Performance Awareness**: Continuous monitoring for regressions
4. **Automation**: CI/CD integration for every commit
5. **Debugging Support**: Rich artifacts and logging for failure analysis

## Testing Framework

### scxtest Library

The `scxtest` library enables userspace testing of BPF code:

```c
// Example test using scxtest
#include <scx_test.h>

static void test_cpu_selection(void)
{
    struct task_struct mock_task = {
        .pid = 1234,
        .prio = 120,
    };
    
    s32 cpu = select_cpu(&mock_task, 0, 0);
    scx_test_assert(cpu >= 0 && cpu < nr_cpus, 
                    "Invalid CPU selection: %d", cpu);
}
```

### Mock Infrastructure

```c
// Mocked BPF helpers
void *bpf_map_lookup_elem(void *map, const void *key)
{
    return scx_test_map_lookup((struct scx_test_map *)map, key);
}

// Mocked kernel functions  
u64 bpf_ktime_get_ns(void)
{
    return scx_test_ktime_get_ns();
}
```

### Test Organization

```
lib/
├── scxtest/          # Testing framework
│   ├── scx_test.h    # Test assertions
│   ├── overrides.*   # Function mocks
│   └── scx_test_*    # Mock implementations
└── selftests/        # Self-tests
    ├── st_atq.bpf.c  # ATQ tests
    ├── st_bitmap.bpf.c # Bitmap tests
    └── st_minheap.bpf.c # Heap tests
```

## Unit Testing

### Writing Unit Tests

#### 1. BPF Library Tests
```c
// lib/selftests/st_bitmap.bpf.c
SEC("test")
int test_bitmap_operations(void)
{
    struct bitmap bm = {};
    
    // Test set/clear operations
    bitmap_set(&bm, 5);
    SCX_SELFTEST(bitmap_test(&bm, 5), "Bit 5 should be set");
    
    bitmap_clear(&bm, 5);
    SCX_SELFTEST(!bitmap_test(&bm, 5), "Bit 5 should be clear");
    
    return 0;
}
```

#### 2. Scheduler Function Tests
```c
// scheds/rust/scx_p2dq/src/bpf/main.test.bpf.c
SEC("test")
int test_pick_idle_cpu(void)
{
    // Setup test environment
    setup_cpu_contexts();
    
    // Test CPU selection logic
    s32 cpu = pick_idle_cpu(task_domain, &test_task);
    SCX_SELFTEST(cpu >= 0, "Should find idle CPU");
    
    // Verify CPU is actually idle
    struct cpu_ctx *ctx = lookup_cpu_ctx(cpu);
    SCX_SELFTEST(ctx && ctx->state == CPU_IDLE, 
                 "Selected CPU should be idle");
    
    return 0;
}
```

### Running Unit Tests

```bash
# Run all unit tests
meson test -C build

# Run specific test suite
meson test -C build scxtest

# Verbose output
meson test -v -C build

# Run with specific timeout
meson test -C build --timeout-multiplier=2
```

## Integration Testing

### Test Scheduler Script

The `test_sched` script provides comprehensive scheduler testing:

```bash
#!/bin/bash
# meson-scripts/test_sched

# Test basic scheduler operations
test_scheduler() {
    local sched=$1
    
    # Start scheduler
    timeout 30 $sched || exit_err "Failed to run $sched"
    
    # Check for kernel errors
    if dmesg | grep -E 'BUG:|WARNING:|RCU stall'; then
        exit_err "Kernel errors detected"
    fi
}
```

### VM-based Testing

```bash
# Run scheduler in virtme-ng VM
meson-scripts/test_sched scx_rusty --vm

# Test with custom kernel
meson-scripts/test_sched scx_lavd --kernel /path/to/bzImage

# Test all schedulers
for sched in build/scheds/*/scx_*; do
    meson-scripts/test_sched "$sched"
done
```

### Integration Test Patterns

```python
# Example from scheduler_runner.py
def test_scheduler_lifecycle():
    """Test scheduler start/stop/restart"""
    runner = SchedulerRunner()
    
    # Start scheduler
    proc = runner.start_scheduler("scx_simple", ["--slice-us", "20000"])
    assert proc.poll() is None, "Scheduler should be running"
    
    # Run workload
    exit_code, stdout, stderr = runner.run_command_with_scheduler(
        "scx_simple", ["stress-ng", "--cpu", "4", "--timeout", "10s"]
    )
    assert exit_code == 0, "Workload should complete successfully"
    
    # Stop scheduler
    runner.stop_scheduler("scx_simple")
    assert proc.poll() is not None, "Scheduler should be stopped"
```

## Stress Testing

### Stress Test Configuration

```ini
# meson-scripts/stress_tests.ini
[scx_rusty]
sched_bin = scx_rusty
stress_cmd = stress-ng --matrix 0 --times --timestamp --perf
timeout = 45
bpftrace = scripts/dsq_lat.bt

[scx_lavd]
sched_bin = scx_lavd
sched_args = --performance
stress_cmd = stress-ng --cpu 8 --io 4 --vm 2 --vm-bytes 128M
timeout = 45
```

### Running Stress Tests

```bash
# Run stress test for specific scheduler
meson-scripts/run_stress_tests -s scx_rusty

# Run all stress tests
meson-scripts/run_stress_tests -a

# Run in VM with custom kernel
meson-scripts/run_stress_tests -s scx_lavd -k /path/to/kernel

# Generate detailed output
meson-scripts/run_stress_tests -s scx_bpfland -o results/
```

### Custom Stress Tests

```bash
#!/bin/bash
# Custom stress test script

# Define workload mix
run_mixed_workload() {
    local duration=$1
    
    # CPU-intensive workload
    stress-ng --cpu 4 --cpu-method matrixprod &
    
    # Memory-intensive workload  
    stress-ng --vm 2 --vm-bytes 1G --vm-method all &
    
    # I/O-intensive workload
    stress-ng --io 4 --hdd 2 &
    
    # Interactive workload simulation
    while true; do
        sleep 0.1
        echo "Interactive ping" > /dev/null
    done &
    
    sleep $duration
    killall stress-ng
}

# Test scheduler under mixed workload
scxctl start -s scx_lavd -m gaming
run_mixed_workload 60
scxctl stop
```

## Performance Analysis

### BPFtrace Scripts

#### 1. DSQ Latency Analysis
```bpftrace
// scripts/dsq_lat.bt
tracepoint:sched:sched_wakeup {
    @qtime[pid] = nsecs;
}

kprobe:scx_dispatch_from_dsq {
    $pid = ((struct task_struct *)arg0)->pid;
    if (@qtime[$pid]) {
        $lat = nsecs - @qtime[$pid];
        @dsq_lat = hist($lat);
        delete(@qtime[$pid]);
    }
}
```

#### 2. CPU Frequency Monitoring
```bpftrace
// scripts/freq_trace.bt
tracepoint:power:cpu_frequency {
    @freq[cpu] = args->new_freq;
    printf("%llu CPU%d freq: %u kHz\n", nsecs, cpu, args->new_freq);
}
```

### Performance Benchmarking

```python
# Example benchmark script
def benchmark_scheduler(scheduler, workload):
    """Run performance benchmark"""
    
    # Start monitoring
    monitor = subprocess.Popen(["scxtop", "trace", "-o", f"{scheduler}.pftrace"])
    
    # Run scheduler with workload
    runner = SchedulerRunner()
    start_time = time.time()
    
    exit_code, stdout, stderr = runner.run_command_with_scheduler(
        scheduler, workload
    )
    
    duration = time.time() - start_time
    
    # Stop monitoring
    monitor.terminate()
    
    # Parse results
    return {
        "scheduler": scheduler,
        "duration": duration,
        "exit_code": exit_code,
        "trace_file": f"{scheduler}.pftrace"
    }
```

### Veristat Analysis

```bash
# Run veristat on scheduler BPF programs
meson-scripts/run_veristat scx_rusty

# Compare two versions
veristat compare baseline.csv updated.csv

# Check specific metrics
veristat --emit file,prog,insns,states scx_lavd.bpf.o
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    strategy:
      matrix:
        scheduler: [scx_simple, scx_rusty, scx_lavd]
    
    steps:
      - name: Run integration test
        run: |
          meson setup build
          meson compile -C build ${{ matrix.scheduler }}
          meson test -C build test_sched_${{ matrix.scheduler }}
      
      - name: Run stress test
        run: |
          meson-scripts/run_stress_tests -s ${{ matrix.scheduler }}
      
      - name: Upload artifacts
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: test-artifacts-${{ matrix.scheduler }}
          path: |
            build/meson-logs/
            *.pftrace
            dmesg.log
```

### Pre-commit Hooks

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Run unit tests
meson test -C build || exit 1

# Check BPF verification
for bpf in build/scheds/*/*.bpf.o; do
    veristat "$bpf" || exit 1
done

# Run quick stress test
timeout 30 meson-scripts/test_sched scx_simple || exit 1
```

## Debugging and Validation

### Kernel Debug Options

```bash
# Enable scheduler debugging
echo 1 > /sys/kernel/debug/sched/debug_enabled
echo 1 > /sys/kernel/debug/sched_ext/stats

# Trace scheduler events
echo 1 > /sys/kernel/debug/tracing/events/sched_ext/enable
cat /sys/kernel/debug/tracing/trace_pipe
```

### Debugging Failed Tests

```bash
# Collect debug information
collect_debug_info() {
    local test_name=$1
    local output_dir="debug_${test_name}_$(date +%Y%m%d_%H%M%S)"
    
    mkdir -p "$output_dir"
    
    # Kernel logs
    dmesg > "$output_dir/dmesg.log"
    
    # Scheduler stats
    cat /sys/kernel/debug/sched_ext/stats > "$output_dir/sched_stats.log"
    
    # BPF programs
    bpftool prog list > "$output_dir/bpf_progs.log"
    
    # CPU info
    cat /proc/cpuinfo > "$output_dir/cpuinfo.log"
    
    # Create archive
    tar czf "${output_dir}.tar.gz" "$output_dir"
}
```

### Validation Checklist

1. **Correctness**:
   - No kernel panics or warnings
   - All tasks get scheduled
   - No starvation or deadlocks

2. **Performance**:
   - Acceptable latency distribution
   - Reasonable CPU utilization
   - No excessive migrations

3. **Compatibility**:
   - Works across kernel versions
   - Handles all CPU topologies
   - Supports cgroup operations

4. **Stress Resistance**:
   - Survives stress-ng workloads
   - Handles CPU hotplug
   - Manages memory pressure

### Test Result Analysis

```python
# Analyze test results
def analyze_test_results(results_dir):
    """Analyze and summarize test results"""
    
    summary = {
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "errors": []
    }
    
    for result_file in Path(results_dir).glob("*.json"):
        with open(result_file) as f:
            result = json.load(f)
            
        summary["total_tests"] += 1
        
        if result["exit_code"] == 0:
            summary["passed"] += 1
        else:
            summary["failed"] += 1
            summary["errors"].append({
                "test": result["test_name"],
                "error": result["stderr"]
            })
    
    # Generate report
    print(f"Test Summary: {summary['passed']}/{summary['total_tests']} passed")
    
    if summary["errors"]:
        print("\nFailures:")
        for error in summary["errors"]:
            print(f"  - {error['test']}: {error['error']}")
    
    return summary["failed"] == 0
```

The testing infrastructure provides comprehensive validation of scheduler implementations, ensuring both correctness and performance across a wide range of scenarios and system configurations.