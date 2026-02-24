# Redis Performance Measurement Guide

numactl --interleave=0,1,2   python redis_bench_start.py --parameter-sweep > redis_test.log

numactl --interleave=3 python redis_bench_start.py

numactl --interleave=3 python memtier_bench_start.py > memtier_test.log

## Overview

This guide provides comprehensive information on measuring Redis performance, including built-in tools, benchmarking methodologies, key metrics, and best practices for performance evaluation.

## Table of Contents

1. [Redis Architecture & Performance Factors](#redis-architecture--performance-factors)
2. [Built-in Benchmarking Tools](#built-in-benchmarking-tools)
3. [Key Performance Metrics](#key-performance-metrics)
4. [Benchmarking Methodologies](#benchmarking-methodologies)
5. [Performance Monitoring](#performance-monitoring)
6. [Optimization Strategies](#optimization-strategies)
7. [Scheduler Integration](#scheduler-integration)

## Redis Architecture & Performance Factors

Redis is an in-memory data structure store that operates as a single-threaded server with optional I/O threading support. Key architectural components affecting performance include:

- **Event Loop**: Uses epoll/kqueue/select for efficient I/O multiplexing
- **Memory Management**: Custom allocator (jemalloc by default) for efficient memory usage
- **Persistence**: AOF (Append Only File) and RDB (Redis Database) snapshots
- **Replication**: Master-slave architecture for scaling reads
- **Clustering**: Horizontal scaling through data sharding

### Performance-Critical Components

Based on the source code analysis:

1. **Networking Layer** (`src/networking.c`, `src/ae.c`): Handles client connections and I/O operations
2. **Command Processing** (`src/server.c`): Single-threaded command execution
3. **Data Structures** (`src/t_*.c` files): Optimized implementations for different data types
4. **Memory Management** (`src/zmalloc.c`): Custom memory allocation and tracking

## Built-in Benchmarking Tools

### 1. redis-benchmark

The primary benchmarking tool (`src/redis-benchmark.c`) provides comprehensive performance testing capabilities:

```bash
# Basic usage
./redis-benchmark -h <host> -p <port> -c <clients> -n <requests>

# Common benchmark parameters
-t <test>      # Specify test (SET, GET, INCR, etc.)
-P <pipeline>  # Pipeline requests (default: 1)
-q            # Quiet mode (only show QPS)
--csv         # Output in CSV format
-d <size>     # Data size in bytes (default: 3)
-r <keyspace> # Use random keys
--threads <n> # Number of threads (max: 500)
```

#### Advanced Features

- **Latency Histograms**: HDR histogram support for accurate latency percentiles
- **Cluster Mode**: Built-in cluster testing support
- **Custom Scripts**: Run custom Redis commands or scripts
- **Multi-threaded**: Support for up to 500 concurrent threads

### 2. redis-cli --latency

Monitor real-time latency:

```bash
redis-cli --latency          # Sample latency continuously
redis-cli --latency-history  # Show latency history
redis-cli --latency-dist     # Show latency distribution
redis-cli --intrinsic-latency 100  # Test system intrinsic latency
```

## Key Performance Metrics

### Primary Metrics

1. **Throughput (Operations/sec)**
   - Requests per second (RPS/QPS)
   - Commands processed per second

2. **Latency**
   - Average response time
   - Percentiles (P50, P95, P99, P99.9)
   - Maximum latency

3. **Resource Utilization**
   - CPU usage (single-core bound)
   - Memory consumption
   - Network bandwidth
   - Disk I/O (for persistence)

### Secondary Metrics

4. **Connection Metrics**
   - Connected clients
   - Blocked clients
   - Connection establishment time

5. **Memory Metrics**
   - Used memory
   - Memory fragmentation ratio
   - Evicted keys

6. **Persistence Metrics**
   - AOF rewrite time
   - RDB save time
   - Background save status

## Benchmarking Methodologies

### Standard Benchmark Suite

The included `redis_benchmark.py` provides a comprehensive test suite:

```python
# Test categories
1. SET operations     - Write performance
2. GET operations     - Read performance
3. INCR operations    - Atomic counter performance
4. LPUSH/LPOP        - List operations
5. SADD operations   - Set operations
6. HSET operations   - Hash operations
7. Mixed workload    - Combined operations
```

### Running Benchmarks

```bash
# Quick benchmark
make quick-benchmark

# Comprehensive benchmark
make benchmark

# Custom benchmark with Python suite
python3 redis_benchmark.py
```

### Benchmark Configuration

Key parameters to adjust:

- **Clients (-c)**: Number of parallel connections (default: 50)
- **Pipeline (-P)**: Number of pipelined requests (default: 1)
- **Data size (-d)**: Size of SET/GET values in bytes
- **Key space (-r)**: Random key range for testing
- **Duration**: Total test duration or request count

## Performance Monitoring

### INFO Command Categories

```bash
redis-cli INFO              # All information
redis-cli INFO server       # Server details
redis-cli INFO clients      # Client connections
redis-cli INFO memory       # Memory usage
redis-cli INFO stats        # General statistics
redis-cli INFO commandstats # Per-command statistics
```

### Key Monitoring Metrics

```
# Throughput
instantaneous_ops_per_sec    # Current ops/sec
total_commands_processed     # Total commands

# Memory
used_memory_human            # Human-readable memory usage
mem_fragmentation_ratio      # Memory fragmentation
evicted_keys                 # Keys evicted due to maxmemory

# Latency
redis-cli --latency-history  # Historical latency
redis-cli CONFIG GET slowlog-log-slower-than
```

### Continuous Monitoring

```bash
# Monitor performance in real-time
watch -n 1 'redis-cli INFO stats | grep instantaneous'

# Track slow queries
redis-cli SLOWLOG GET 10

# Monitor client connections
redis-cli CLIENT LIST
```

## Optimization Strategies

### Configuration Tuning

Key configuration parameters for performance:

```conf
# Memory Management
maxmemory <bytes>            # Maximum memory limit
maxmemory-policy allkeys-lru # Eviction policy

# Persistence
save ""                      # Disable RDB snapshots
appendonly no                # Disable AOF for max performance
appendfsync no               # No fsync (fastest, least safe)

# Networking
tcp-backlog 511              # TCP listen backlog
tcp-keepalive 300            # TCP keepalive

# Threading (Redis 6.0+)
io-threads 4                 # Number of I/O threads
io-threads-do-reads yes      # Enable threaded reads
```

### Performance Best Practices

1. **Use Pipelining**: Batch multiple commands to reduce RTT
2. **Optimize Data Structures**: Choose appropriate data types
3. **Avoid Large Keys**: Keep key sizes reasonable
4. **Use Connection Pooling**: Reuse connections
5. **Monitor Slow Queries**: Identify and optimize slow commands
6. **Tune Kernel Parameters**: Adjust TCP and memory settings

### System-Level Optimization

```bash
# Disable transparent huge pages
echo never > /sys/kernel/mm/transparent_hugepage/enabled

# Increase TCP backlog
echo 511 > /proc/sys/net/core/somaxconn

# Tune network parameters
sysctl -w net.ipv4.tcp_max_syn_backlog=512
sysctl -w net.core.netdev_max_backlog=1000
```

## Scheduler Integration

### Impact of Kernel Schedulers

Different Linux schedulers affect Redis performance:

1. **CFS (Default)**: General-purpose, may not be optimal for Redis
2. **Real-time schedulers**: Can provide lower latency
3. **Custom BPF schedulers**: Fine-tuned for Redis workload patterns

### Testing with Different Schedulers

```bash
# Example: Testing with scx schedulers
cd /root/yunwei37/ai-os

# Run with default scheduler
python workloads/redis/redis_benchmark.py

# Run with scx_rusty
./scheduler/sche_bin/scx_rusty &
python workloads/redis/redis_benchmark.py

# Compare results
```

### Scheduler Performance Metrics

Key metrics to compare:

- **Latency reduction**: P99 and P99.9 improvements
- **Throughput increase**: Operations per second
- **CPU efficiency**: CPU utilization patterns
- **Jitter reduction**: Consistency of response times

## Automated Testing

### Makefile Targets

```bash
make deps          # Install dependencies
make clone         # Clone Redis repository (if needed)
make build         # Build Redis from source
make configure     # Apply configuration
make benchmark     # Run full benchmark suite
make clean         # Clean build artifacts
```

### Python Benchmark Suite

The `redis_benchmark.py` script provides:

- Automated Redis server management
- Multiple benchmark scenarios
- Resource monitoring (CPU, memory)
- JSON result output
- Performance summary generation

### Integration with CI/CD

```yaml
# Example GitHub Actions workflow
- name: Run Redis Benchmarks
  run: |
    make build
    make benchmark
    python3 -c "import json; print(json.load(open('results/*.json')))"
```

## Result Interpretation

### Understanding Benchmark Output

```
====== SET ======
  100000 requests completed in 1.23 seconds
  50 parallel clients
  3 bytes payload
  keep alive: 1

99.00% <= 1 milliseconds
99.50% <= 2 milliseconds
99.90% <= 3 milliseconds
100.00% <= 5 milliseconds
81300.81 requests per second
```

Key insights:
- **Request rate**: 81,300 ops/sec indicates good throughput
- **Latency percentiles**: P99 at 1ms shows consistent performance
- **Parallel clients**: 50 concurrent connections

### Performance Baselines

Typical performance on modern hardware:

| Operation | Expected Throughput | P99 Latency |
|-----------|-------------------|-------------|
| SET       | 80,000-120,000 ops/s | < 2ms |
| GET       | 100,000-150,000 ops/s | < 1ms |
| INCR      | 90,000-130,000 ops/s | < 1ms |
| LPUSH     | 80,000-120,000 ops/s | < 2ms |
| SADD      | 80,000-120,000 ops/s | < 2ms |

## Troubleshooting Performance Issues

### Common Bottlenecks

1. **CPU Bound**: Single-threaded nature limits CPU utilization
   - Solution: Use Redis Cluster for horizontal scaling

2. **Memory Pressure**: Swapping or eviction overhead
   - Solution: Increase memory or optimize data structures

3. **Network Latency**: High RTT between client and server
   - Solution: Use pipelining or move clients closer

4. **Disk I/O**: Persistence operations blocking main thread
   - Solution: Tune persistence settings or use background saving

### Diagnostic Commands

```bash
# Check slow queries
redis-cli SLOWLOG GET 10

# Monitor real-time commands
redis-cli MONITOR

# Check memory usage
redis-cli MEMORY DOCTOR

# Analyze latency events
redis-cli LATENCY DOCTOR
```

## Conclusion

Measuring Redis performance requires understanding both the tool's architecture and the available benchmarking utilities. The combination of built-in tools like `redis-benchmark`, monitoring through INFO commands, and custom benchmark suites provides comprehensive performance evaluation capabilities.

For scheduler evaluation in the ai-os project, Redis serves as an excellent workload for testing:
- Single-threaded CPU-bound operations
- Latency-sensitive operations
- Mixed read/write patterns
- Memory-intensive workloads

Regular benchmarking with different scheduler configurations will help identify the optimal scheduler for Redis workloads in your specific environment.