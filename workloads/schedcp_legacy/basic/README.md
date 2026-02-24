# Basic Workloads and Benchmarks

This directory contains fundamental benchmarking tools for testing and evaluating Linux kernel schedulers and system performance under various workloads.

## Available Benchmarks

### 1. schbench
**Purpose**: Scheduler benchmark that simulates common application patterns  
**Focus**: Latency measurement under various thread counts and workload patterns  
**Key Features**:
- Measures scheduling latency percentiles
- Simulates message passing workloads
- Tests wakeup latency and context switching overhead
- Ideal for evaluating scheduler responsiveness

**Usage**:
```bash
./schbench -m 2 -t 16 -r 10
# -m: number of message threads
# -t: number of worker threads per message thread
# -r: runtime in seconds
```

### 2. stress-ng
**Purpose**: Comprehensive stress testing framework  
**Focus**: System-wide stress testing with 300+ stress methods  
**Key Features**:
- CPU, memory, I/O, network stress testing
- Scheduler stress tests (context switching, priority inversion)
- Real-time scheduling tests
- Power and thermal stress capabilities
- Detailed metrics collection

**Usage**:
```bash
# CPU stress with 4 workers for 60 seconds
./stress-ng --cpu 4 --timeout 60s

# Scheduler stress test
./stress-ng --sched 8 --sched-ops 1000000

# Memory pressure test
./stress-ng --vm 2 --vm-bytes 1G --timeout 30s
```

### 3. cachyos-benchmarker
**Purpose**: Automated system benchmarking suite  
**Focus**: Comprehensive performance evaluation across multiple subsystems  
**Key Features**:
- Gaming and desktop responsiveness tests
- Compilation benchmark suite
- Memory bandwidth and latency tests
- Storage I/O performance
- Integrated result comparison and reporting

**Usage**:
```bash
# Run full benchmark suite
./cachyos-benchmarker

# Run specific benchmark
./cachyos-benchmarker --benchmark cpu

# Compare results
./cachyos-benchmarker --compare baseline.json current.json
```

## Building

Build all benchmarks:
```bash
make all
```

Build individual benchmarks:
```bash
make schbench
make stress-ng
make cachyos-benchmarker
```

Clean build artifacts:
```bash
make clean
```

## Integration with schedcp

These benchmarks are designed to work with schedcp's scheduler testing framework:

1. **Automated Testing**: Use `scheduler_test/schbench_bench_start.py` for automated schbench runs
2. **Scheduler Comparison**: Test different sched_ext schedulers with consistent workloads
3. **Performance Metrics**: Collect latency percentiles, throughput, and system metrics
4. **Real-time Monitoring**: Use with `scxtop` to observe scheduler behavior during tests

## Recommended Test Scenarios

### Interactive Desktop Workload
```bash
# Test scheduling latency under light load
./schbench -m 1 -t 4 -r 30
./stress-ng --cpu 2 --io 2 --timeout 30s
```

### Server Throughput Workload
```bash
# High thread count throughput test
./schbench -m 8 -t 16 -r 60
./stress-ng --cpu $(nproc) --cpu-method matrixprod --timeout 60s
```

### Memory-Intensive Workload
```bash
# Memory bandwidth and latency stress
./stress-ng --vm 4 --vm-bytes 2G --vm-method all --timeout 60s
./cachyos-benchmarker --benchmark memory
```

### Real-time Workload
```bash
# Test real-time scheduling capabilities
./stress-ng --cyclic 1 --cyclic-policy rr --cyclic-prio 80 --timeout 60s
./schbench -m 1 -t 2 -r 30 -p 99
```

### Sysbench Test Suite (30 seconds)
```bash
# CPU benchmark
sysbench cpu --threads=4 --time=30 run

# Memory benchmark
sysbench memory --threads=4 --time=30 run

# File I/O benchmark
sysbench fileio --file-total-size=1G prepare
sysbench fileio --file-total-size=1G --file-test-mode=rndrw --threads=4 --time=30 run
sysbench fileio cleanup

# Threads benchmark
sysbench threads --threads=64 --time=30 run

# Mutex benchmark
sysbench mutex --threads=4 --time=30 run
```

## Tips for Scheduler Evaluation

1. **Baseline First**: Always establish baseline metrics with the default scheduler
2. **Consistent Environment**: Disable CPU frequency scaling and turbo boost for consistent results
3. **Multiple Runs**: Perform multiple test runs to account for variance
4. **Monitor System State**: Use `scxtop`, `perf`, and system monitors during tests
5. **Gradual Load**: Start with light loads and gradually increase to find breaking points

## Output and Analysis

- **schbench**: Outputs latency percentiles (50th, 75th, 90th, 95th, 99th, 99.5th, 99.9th)
- **stress-ng**: Provides operations per second, CPU usage, and detailed stressor metrics
- **cachyos-benchmarker**: Generates JSON reports with comparative analysis capabilities

Results can be fed into schedcp's learning algorithms to optimize scheduler parameters for specific workload patterns.