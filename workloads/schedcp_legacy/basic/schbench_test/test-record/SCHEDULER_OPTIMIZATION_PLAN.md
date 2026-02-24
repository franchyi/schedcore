# Scheduler Optimization Plan for Schbench Workload

## Executive Summary

This document provides a comprehensive plan for selecting and optimizing schedulers for the schbench workload, which simulates web server characteristics with mixed CPU-intensive and I/O operations.

## Schbench Workload Profile

- **Workload Type**: Mixed CPU-intensive and I/O simulation with request/response pattern
- **Thread Model**: Producer-consumer with message threads and worker threads
- **Key Characteristics**:
  - Alternating compute (matrix multiplication) and sleep phases
  - 100μs input sleep + 5 matrix operations + 10μs output sleep per request
  - Per-CPU spinlocks modeling preemption costs
  - Cache footprint: ~256KB per worker thread
  - Sensitive to wakeup latency and CPU affinity

## Available Scheduler Options

### Option 1: scx_bpfland (Primary Recommendation)

**Rationale**: Best match for schbench's mixed CPU/IO pattern with interactive characteristics

**Key Features**:
- Interactive task prioritization based on voluntary context switches
- Weighted runtime queuing with time slice budget carryover
- Cache topology awareness (L2/L3)
- Optimized for low latency and interactive responsiveness

**Tuning Configurations**:

```bash
# Conservative baseline
scx_bpfland --slice-us 5000 --slice-us-min 500

# Aggressive latency optimization
sudo ./scx_bpfland --slice-us 2000 --slice-us-min 200 --no-wake-sync

# Cache-optimized configuration
scx_bpfland --slice-us 4000 --slice-us-min 400 --primary-domain performance

# Maximum responsiveness
scx_bpfland --slice-us 1000 --slice-us-min 100 --no-preempt
```

### Option 2: scx_flash (Low Latency Focus)

**Rationale**: EDF-based scheduling ideal for predictable latency requirements

**Key Features**:
- Dynamic latency weights based on CPU usage patterns
- Prioritizes tasks that release CPU early (matches schbench's sleep phases)
- Voluntary context switch credits benefit schbench's I/O simulation

**Tuning Configurations**:

```bash
# Latency-focused configuration
scx_flash --slice-us 2048 --slice-us-min 128 --max-avg-nvcsw 256

# With CPU frequency optimization
scx_flash --slice-us 4096 --cpufreq --sticky-cpu

# Aggressive latency mode
scx_flash --slice-us 1024 --slice-us-min 64 --run-us-lag 16384

# Balanced configuration
scx_flash --slice-us 4096 --slice-us-lag 4096 --native-priority
```

### Option 3: scx_lavd (Gaming/Interactive Optimized)

**Rationale**: Sophisticated latency-aware scheduling with autopilot capabilities

**Key Features**:
- LAVD algorithm measures task latency criticality
- Virtual deadline scheduling
- Autopilot mode for dynamic optimization
- Per-LLC domains with NUMA awareness

**Tuning Configurations**:

```bash
# Balanced mode with autopilot
scx_lavd --balanced --autopilot

# Performance mode for lowest latency
scx_lavd --performance --slice-min-us 250 --slice-max-us 2000

# Custom tuning for schbench
scx_lavd --slice-min-us 300 --slice-max-us 3000 --preempt-shift 5

# No preemption mode
scx_lavd --no-preemption --performance
```

### Option 4: scx_rusty (General Purpose Baseline)

**Rationale**: Production-ready scheduler for comparison and stability

**Key Features**:
- Multi-domain round-robin with load balancing
- Greedy task stealing for better CPU utilization
- Architecture-flexible design
- Proven stability in production

**Tuning Configurations**:

```bash
# Low latency configuration
scx_rusty --slice-us-underutil 5000 --slice-us-overutil 500 --greedy-threshold 2

# With direct greedy for aggressive balancing
scx_rusty --slice-us-underutil 10000 --direct-greedy-under 50.0

# NUMA-aware configuration
scx_rusty --greedy-threshold-x-numa 2 --direct-greedy-numa

# Minimum latency focus
scx_rusty --slice-us-underutil 2000 --slice-us-overutil 200 --load-half-life 0.5
```

### Option 5: scx_simple (Control Baseline)

**Rationale**: Minimal overhead baseline for establishing performance bounds

**Key Features**:
- Simple vtime or FIFO scheduling
- Minimal complexity and overhead
- Good for establishing baseline performance

**Tuning Configurations**:

```bash
# Vtime mode (default)
scx_simple --slice-us 5000

# FIFO mode for comparison
scx_simple --fifo --slice-us 5000

# Short slice for responsiveness
scx_simple --slice-us 1000

# Long slice for throughput
scx_simple --slice-us 20000
```

## Testing Strategy

### Phase 1: Baseline Establishment
1. Run with default Linux CFS scheduler
2. Test scx_simple (both vtime and FIFO modes)
3. Record baseline metrics for comparison

### Phase 2: Latency-Optimized Testing
1. Test scx_bpfland with various slice configurations
2. Test scx_flash with EDF optimizations
3. Test scx_lavd in different power modes

### Phase 3: Production Scheduler Testing
1. Test scx_rusty with different domain configurations
2. Compare with latency-optimized schedulers
3. Evaluate stability and consistency

### Phase 4: Parameter Tuning
1. For top 2 performers, conduct parameter sweep
2. Test slice duration variations (1ms to 20ms)
3. Test cache awareness settings
4. Test wake synchronization options

## Key Metrics to Monitor

### Primary Metrics
- **Wakeup Latency**: 50th, 90th, 99th, 99.9th percentiles
- **Request Latency**: End-to-end completion time percentiles
- **Throughput**: Requests per second (RPS)
- **CPU Utilization**: Ensure full saturation without idle time

### Secondary Metrics
- **Context Switches**: Voluntary vs involuntary ratio
- **Cache Misses**: L2/L3 cache hit rates
- **Thread Migrations**: Frequency and impact
- **Scheduling Overhead**: Time spent in scheduler

## Expected Results

Based on schbench characteristics:

1. **Best Latency**: scx_bpfland or scx_flash (10-30% improvement over CFS)
2. **Best Throughput**: scx_rusty or scx_bpfland (5-15% improvement)
3. **Most Consistent**: scx_flash with EDF guarantees
4. **Lowest Overhead**: scx_simple

## Recommendations

1. **Start with**: scx_bpfland as primary candidate
2. **Compare against**: scx_flash for latency-critical scenarios
3. **Fallback to**: scx_rusty for production stability
4. **Use scx_simple**: As performance baseline

## Implementation Commands

```bash
# Quick test sequence
./scheduler/sche_bin/scx_simple --slice-us 5000 &
python workloads/basic/scheduler_test/schbench_bench_start.py

./scheduler/sche_bin/scx_bpfland --slice-us 2000 --slice-us-min 200 &
python workloads/basic/scheduler_test/schbench_bench_start.py

./scheduler/sche_bin/scx_flash --slice-us 2048 --slice-us-min 128 &
python workloads/basic/scheduler_test/schbench_bench_start.py

# Monitor with scxtop
./scheduler/tools/scxtop
```

## Conclusion

The schbench workload's mixed CPU/IO pattern with latency sensitivity makes it ideal for testing modern schedulers. The recommended approach focuses on schedulers that can identify and prioritize interactive behavior while maintaining high CPU utilization.


  cd /home/yunwei37/ai-os/workloads/basic/schbench_test && ./schbench_simple_collect.py
  scx_bpfland_aggressive.json scx_bpfland_aggressive

  ### Test 2: scx_flash (Latency-focused with EDF)
  ```bash
  # Test 2 command:
  cd /home/yunwei37/ai-os/workloads/basic/schbench_test && ./schbench_simple_collect.py
  scx_flash_latency.json scx_flash_latency

  Test 3: scx_rusty (Low latency configuration)

  # Test 3 command:
  cd /home/yunwei37/ai-os/workloads/basic/schbench_test && ./schbench_simple_collect.py
  scx_rusty_lowlat.json scx_rusty_lowlat

  To run the complete test sequence:
  1. First run test 1 with scx_bpfland (already started above)
  2. Stop scx_bpfland and start sudo ./scx_flash --slice-us 2048 --slice-us-min 128 --max-avg-nvcsw 256
  3. Stop scx_flash and start sudo ./scx_rusty --slice-us-underutil 5000 --slice-us-overutil 500 --greedy-threshold 2
