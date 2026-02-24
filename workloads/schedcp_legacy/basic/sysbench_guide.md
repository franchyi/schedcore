# Sysbench User Guide

## Overview

Sysbench is a scriptable multi-threaded benchmark tool used for evaluating system performance. It provides benchmarks for CPU, memory, file I/O, mutex performance, and database operations.

## Installation

### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install sysbench
```

### RHEL/CentOS/Fedora
```bash
sudo yum install epel-release
sudo yum install sysbench
```

### From Source
```bash
git clone https://github.com/akopytov/sysbench.git
cd sysbench
./autogen.sh
./configure
make
sudo make install
```

## Basic Usage

### Command Structure
```bash
sysbench [options] testname [command]
```

Commands:
- `prepare`: Prepare the test (e.g., create test data)
- `run`: Run the actual test
- `cleanup`: Clean up after the test
- `help`: Show help for a specific test

### Common Options
- `--threads=N`: Number of worker threads (default: 1)
- `--time=N`: Test duration in seconds (default: 10)
- `--events=N`: Limit for total number of events
- `--rate=N`: Average transactions rate (0 = unlimited)
- `--report-interval=N`: Report intermediate statistics every N seconds

## CPU Benchmark

Tests CPU performance by calculating prime numbers. This simulates CPU-intensive workloads like scientific computing, cryptography, or video encoding.

```bash
# Basic CPU test
sysbench cpu run

# Advanced CPU test with custom parameters
sysbench cpu --threads=4 --cpu-max-prime=20000 --time=60 run
```

Parameters:
- `--cpu-max-prime=N`: Upper limit for prime number calculation

## Memory Benchmark

Tests memory transfer speed. This simulates memory-intensive workloads like in-memory databases, caching systems, or large data processing applications.

```bash
# Basic memory test
sysbench memory run

# Memory test with custom parameters
sysbench memory --threads=4 --memory-block-size=1K --memory-total-size=10G --memory-access-mode=seq run
```

Parameters:
- `--memory-block-size=SIZE`: Size of memory block (default: 1K)
- `--memory-total-size=SIZE`: Total size of data to transfer
- `--memory-scope=STRING`: Memory access scope (global, local)
- `--memory-oper=STRING`: Memory operation (read, write, none)
- `--memory-access-mode=STRING`: Access mode (seq, rnd)

## File I/O Benchmark

Tests file system performance. This simulates I/O-intensive workloads like database systems, file servers, logging systems, or video streaming applications.

```bash
# Prepare test files
sysbench fileio --file-total-size=2G prepare

# Run sequential read test
sysbench fileio --file-total-size=2G --file-test-mode=seqrd --time=300 --max-requests=0 run

# Cleanup
sysbench fileio --file-total-size=2G cleanup
```

Test modes and their workload simulations:
- `seqwr`: Sequential write (logging, video recording, backup operations)
- `seqrd`: Sequential read (media streaming, file copying, sequential scans)
- `rndrd`: Random read (database queries, web server static files)
- `rndwr`: Random write (database updates, OLTP workloads)
- `rndrw`: Combined random read/write (mixed database workloads)

Parameters:
- `--file-num=N`: Number of test files
- `--file-block-size=N`: Block size for I/O operations
- `--file-io-mode=STRING`: I/O mode (sync, async, mmap)
- `--file-fsync-freq=N`: fsync frequency
- `--file-rw-ratio=N`: Read/write ratio for combined test

## Thread/Mutex Benchmark

Tests thread synchronization performance. This simulates multi-threaded applications with high contention like web servers, application servers, or parallel processing systems.

```bash
# Mutex benchmark
sysbench mutex --threads=8 --mutex-num=4096 --mutex-locks=50000 --mutex-loops=10000 run
```

Parameters:
- `--mutex-num=N`: Number of mutexes
- `--mutex-locks=N`: Number of mutex locks per thread
- `--mutex-loops=N`: Number of loops inside mutex lock

## Database Benchmarks

### OLTP Read/Write

Simulates Online Transaction Processing workloads typical of e-commerce, banking, or ERP systems.

```bash
# Prepare database
sysbench oltp_read_write --db-driver=mysql --mysql-host=localhost --mysql-user=sbtest --mysql-password=password --mysql-db=sbtest --tables=10 --table-size=100000 prepare

# Run test
sysbench oltp_read_write --db-driver=mysql --mysql-host=localhost --mysql-user=sbtest --mysql-password=password --mysql-db=sbtest --tables=10 --table-size=100000 --threads=16 --time=300 --report-interval=10 run

# Cleanup
sysbench oltp_read_write --db-driver=mysql --mysql-host=localhost --mysql-user=sbtest --mysql-password=password --mysql-db=sbtest --tables=10 cleanup
```

Available OLTP tests and their workload simulations:
- `oltp_read_only`: Read-only transactions (reporting systems, analytics)
- `oltp_write_only`: Write-only transactions (logging systems, data ingestion)
- `oltp_read_write`: Mixed read/write transactions (e-commerce, banking applications)
- `oltp_insert`: INSERT-only workload (data collection, IoT systems)
- `oltp_delete`: DELETE-only workload (data purging, cleanup jobs)
- `oltp_update_index`: UPDATE on indexed columns (inventory systems, user profiles)
- `oltp_update_non_index`: UPDATE on non-indexed columns (status updates, counters)

## Custom Lua Scripts

Sysbench supports custom Lua scripts for complex benchmarks:

```lua
-- custom_test.lua
function event()
    -- Custom test logic here
    local val = math.random(1, 1000000)
    local result = 0
    for i = 1, 1000 do
        result = result + math.sqrt(val)
    end
end
```

Run custom script:
```bash
sysbench custom_test.lua \
  --threads=4 \
  --time=60 \
  run
```

## Output Interpretation

### Sample Output
```
sysbench 1.0.20 (using bundled LuaJIT 2.1.0-beta2)

Running the test with following options:
Number of threads: 4
Initializing random number generator from current time

Prime numbers limit: 10000

Initializing worker threads...

Threads started!

CPU speed:
    events per second:  2847.30

General statistics:
    total time:                          10.0014s
    total number of events:              28481

Latency (ms):
         min:                                    1.30
         avg:                                    1.40
         max:                                   13.46
         95th percentile:                        1.67
         sum:                                39954.93

Threads fairness:
    events (avg/stddev):           7120.2500/79.68
    execution time (avg/stddev):   9.9887/0.00
```

Key metrics:
- **Events per second**: Throughput metric
- **Latency**: Response time statistics
  - min/avg/max: Minimum, average, and maximum latency
  - 95th percentile: 95% of requests completed within this time
- **Threads fairness**: How evenly work was distributed

## Best Practices

1. **Warm-up Period**: Run tests for at least 60 seconds to get stable results
2. **Multiple Runs**: Execute tests multiple times and average results
3. **System State**: Ensure consistent system state between tests
4. **Background Processes**: Minimize background activity during tests
5. **Resource Monitoring**: Use tools like `iostat`, `vmstat`, `top` alongside sysbench

## Example Test Suite

```bash
#!/bin/bash
# Comprehensive system benchmark simulating various workloads

echo "=== CPU Benchmark (Scientific Computing Workload) ==="
sysbench cpu --threads=4 --time=60 run

echo "=== Memory Benchmark (In-Memory Database Workload) ==="
sysbench memory --threads=4 --memory-total-size=10G run

echo "=== File I/O Benchmark (Mixed Database Workload) ==="
sysbench fileio --file-total-size=4G prepare
sysbench fileio --file-total-size=4G --file-test-mode=rndrw --time=60 run
sysbench fileio --file-total-size=4G cleanup

echo "=== Thread Benchmark (Web Server Workload) ==="
sysbench threads --threads=64 --thread-yields=100 --thread-locks=2 run
```

## Troubleshooting

### Permission Issues
- File I/O tests may require write permissions in current directory
- Database tests need appropriate database permissions

### Resource Limits
```bash
# Check current limits
ulimit -a

# Increase open file limit
ulimit -n 65536
```

### Database Connection Issues
- Verify database is running and accessible
- Check credentials and connection parameters
- Ensure test database exists

## Further Resources

- [Official Documentation](https://github.com/akopytov/sysbench)
- [Database Testing Guide](https://www.percona.com/blog/sysbench-guide/)
- [Custom Lua Scripts](https://github.com/akopytov/sysbench/tree/master/src/lua)