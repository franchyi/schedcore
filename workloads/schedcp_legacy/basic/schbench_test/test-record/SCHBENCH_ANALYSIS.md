# Schbench Analysis

## Overview

Schbench is a scheduler benchmark designed to reproduce the scheduler characteristics of production web workloads. It simulates a complex multi-threaded workload that targets three key scheduler behaviors:

1. **CPU Saturation** - Ensures all CPUs on the system are utilized
2. **Long Timeslices** - Minimizes involuntary context switches
3. **Low Scheduling Delays** - Reduces wakeup latencies

## Command Line Parameters

For the command `../schbench/schbench -m 2 -t 4 -r 30 -n 5`, the parameters mean:

- **`-m 2` (message-threads)**: Creates 2 message threads
  - Default: 1
  - Recommendation: One message thread per NUMA node
  - Message threads act as dispatchers that queue work for worker threads

- **`-t 4` (threads)**: Creates 4 worker threads per message thread
  - Default: num_cpus (automatically calculated)
  - Total worker threads = message_threads × worker_threads = 2 × 4 = 8 workers
  - Worker threads perform the actual computational work

- **`-r 30` (runtime)**: Runs the benchmark for 30 seconds
  - Default: 30 seconds
  - After warmup period, statistics are collected for this duration

- **`-n 5` (operations)**: Performs 5 matrix multiplication operations per request
  - Default: 5
  - Controls the computational intensity of each work unit
  - More operations = longer CPU-bound work per request

## Workload Pattern

Schbench generates a workload that mimics real-world web server behavior:

### 1. **Request Processing Model**
- Message threads receive and dispatch work requests
- Worker threads process requests consisting of:
  - Initial sleep (simulating network/disk I/O) - default 100μs
  - Matrix multiplication operations (CPU-intensive work)
  - Another sleep (simulating response preparation)

### 2. **Matrix Operations**
- Uses 256KB cache footprint by default (configurable with -F)
- Performs naive matrix multiplication to stress CPU and cache
- Matrix size calculated as: sqrt(cache_footprint_kb × 1024 / 3 / sizeof(unsigned long))

### 3. **Preemption Penalty**
- Uses per-CPU spinlocks during matrix operations
- If a thread is preempted and moved to another CPU, the next thread on that CPU must wait
- This models the real-world cost of cache misses and context switches
- Can be disabled with `--no-locking` flag

## Performance Characteristics

### Metrics Collected

1. **Wakeup Latencies**
   - Time between when work is posted and when worker starts running
   - Measures scheduler responsiveness
   - Reported in percentiles (50th, 90th, 99th, 99.9th)

2. **Request Latencies**
   - Total time to complete a request (including sleeps and computation)
   - Measures end-to-end performance
   - Critical for understanding user-visible latency

3. **Requests Per Second (RPS)**
   - Total throughput of completed requests
   - Key metric for web workload performance

### Resource Usage Patterns

1. **CPU Usage**
   - Attempts to saturate all available CPUs
   - Worker threads perform CPU-intensive matrix operations
   - Message threads have lighter CPU usage (mainly dispatching)

2. **Memory Access**
   - 256KB cache footprint per worker thread by default
   - Three matrices allocated per worker (3 × matrix_size²)
   - Memory access pattern stresses L1/L2 cache

3. **Synchronization**
   - Uses futexes for message/worker communication
   - Per-CPU locks for modeling preemption costs
   - Lock contention increases with thread migration

## Typical Usage Scenarios

### Basic Saturation Test
```bash
# Uses all CPUs with default settings
./schbench
```

### NUMA-Aware Configuration
```bash
# 2 message threads (one per NUMA node), auto-calculate workers
./schbench -m 2 -r 60
```

### Calibration Mode
```bash
# Find optimal operations count for ~20ms timeslice
./schbench -F 256 -n 5 --calibrate -r 10
```

### Low-Latency Testing
```bash
# Reduce sleep time and operations for latency-sensitive testing
./schbench -s 50 -n 2 -r 30
```

## Key Insights

1. **Scheduler Evaluation**: Schbench is excellent for evaluating scheduler policies regarding:
   - Wake-up efficiency
   - CPU affinity decisions
   - Timeslice allocation
   - Load balancing effectiveness

2. **Realistic Workload**: Unlike synthetic benchmarks, schbench models:
   - Mixed I/O and CPU work
   - Inter-thread communication patterns
   - Cache effects of thread migration
   - Variable request processing times

3. **Tuning Considerations**:
   - Adjust `-n` to match your system's timeslice
   - Use `-F` to control cache pressure
   - Set `-m` based on NUMA topology
   - Use `--calibrate` to find optimal parameters

4. **Production Relevance**: The benchmark effectively simulates:
   - Web server request handling
   - Database query processing
   - Application server workloads
   - Any workload with request/response patterns