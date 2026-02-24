# Schbench Application Profile

## Executive Summary
**Application**: schbench - Scheduler benchmark simulating web server workloads  
**Command**: `../schbench/schbench -m 2 -t 4 -r 30 -n 5`  
**Workload Type**: Mixed CPU-intensive and I/O simulation with request/response pattern  
**Duration**: 30 seconds  
**Total Threads**: 10 (2 message threads + 8 worker threads)  

## Workload Characteristics

### Thread Model
- **Message Threads**: 2 dispatcher threads that queue work requests
- **Worker Threads**: 8 threads (4 per message thread) that process requests
- **Communication**: Producer-consumer pattern using futexes

### Execution Pattern
1. **Request Generation**: Message threads continuously generate work requests
2. **Request Processing**: Each request involves:
   - Sleep phase: 100μs (simulating network/disk I/O)
   - Compute phase: 5 matrix multiplications (64x64 matrices)
   - Response phase: 10μs sleep
3. **Synchronization**: Per-CPU spinlocks model preemption costs

### Resource Usage Profile

#### CPU Usage
- **Pattern**: Bursty CPU usage alternating with sleep periods
- **Intensity**: High during matrix multiplication phases
- **Distribution**: Attempts to utilize all available CPUs
- **Context Switches**: Frequent due to sleep/wake cycles

#### Memory Access
- **Working Set**: ~256KB per worker thread (2MB total)
- **Access Pattern**: Sequential during matrix operations
- **Cache Behavior**: 
  - Hot data fits in L2 cache
  - Sensitive to thread migration effects
  - Per-CPU lock data creates cache line bouncing

#### I/O Characteristics
- **Type**: Simulated via sleep() calls
- **Pattern**: Regular, predictable delays
- **Latency**: 100μs input simulation + 10μs output simulation

## Performance Metrics

### Key Performance Indicators
1. **Wakeup Latency**: Time from futex_wake to thread execution
2. **Request Latency**: End-to-end request processing time
3. **Throughput**: Requests processed per second
4. **CPU Efficiency**: Ratio of compute time to total time

### Expected Behavior
- **Optimal**: Low wakeup latencies (<10μs), high throughput
- **Degraded**: High scheduling delays, poor CPU utilization
- **Pathological**: Thread starvation, excessive migrations

## Scheduler Optimization Opportunities

### Critical Scheduling Decisions
1. **Wake-up Target**: Which CPU to wake sleeping threads on
2. **Migration Policy**: When to move threads between CPUs
3. **Timeslice Allocation**: How long to run compute phases
4. **Load Balancing**: Distribution of threads across CPUs

### Optimization Goals
- Minimize wakeup latency
- Maximize CPU utilization
- Reduce unnecessary thread migrations
- Maintain cache locality

## System Requirements

### Hardware
- **CPUs**: Benefits from multiple cores (8+ recommended)
- **Memory**: Minimal (~2MB working set)
- **Cache**: L2 cache size impacts performance

### Software
- **OS**: Linux with scheduling statistics support
- **Libraries**: pthread, standard C library
- **Privileges**: None required (userspace only)

## Use Cases

### Primary Use Case
Evaluating scheduler performance for web server-like workloads with:
- Mixed CPU and I/O operations
- Request/response communication patterns
- Moderate thread counts
- Latency-sensitive operations

### Scheduler Evaluation
Particularly effective for testing:
- Wakeup efficiency
- CPU affinity policies
- Timeslice decisions
- Cross-CPU communication costs

## Configuration Impact

### Parameter Sensitivity
- **Message Threads (-m)**: Increases contention and communication overhead
- **Worker Threads (-t)**: Affects CPU saturation and scheduling complexity
- **Matrix Operations (-n)**: Controls compute intensity and timeslice pressure
- **Runtime (-r)**: Longer runs reveal steady-state behavior

### Scaling Behavior
- Linear scaling with worker threads up to CPU count
- Message thread scaling limited by synchronization overhead
- Cache effects become prominent with thread migration

## Limitations

1. **Simplified I/O Model**: Sleep-based simulation doesn't capture real I/O complexity
2. **Fixed Workload**: Doesn't model variable request sizes or types
3. **Synthetic Compute**: Matrix multiplication may not match real application patterns
4. **No Network Effects**: Doesn't model network stack interactions

## Recommendations

### For Scheduler Testing
1. Start with default parameters to establish baseline
2. Vary thread counts to test scaling behavior
3. Monitor both latency percentiles and throughput
4. Use with other benchmarks for comprehensive evaluation

### For Production Correlation
- Results correlate well with web server scheduling behavior
- Latency improvements typically translate to real workload gains
- Consider alongside application-specific benchmarks