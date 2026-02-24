# Scheduler Test - schbench Performance Testing

This directory contains the schbench-based performance testing framework for schedcp schedulers.

## Overview

The `schbench_bench_start.py` script automates the process of testing all available schedulers using schbench (scheduler benchmark), a tool designed to measure scheduler performance under messaging workload patterns.

## What Commands Are Actually Run

### Core schbench Command

The script runs schbench with the following command structure for each scheduler:

```bash
../schbench/schbench -m <message_threads> -t <message_groups> -r <runtime> -s <sleeptime> -n <operations>
```

Default parameters:
- `-m 2`: 2 message threads per group
- `-t 4`: 4 message thread groups (total threads = 2 * 4 = 8)
- `-r 30`: Run for 30 seconds
- `-s 10000`: Sleep for 10,000 microseconds (10ms) between requests
- `-n 5`: 5 operations per request

### Example Command
```bash
../schbench/schbench -m 2 -t 4 -r 30 -n 5
```

### Testing Process

1. **Default Scheduler Test**: First runs schbench without any custom scheduler
2. **Custom Scheduler Tests**: For each available scheduler, the script:
   - Starts the scheduler (e.g., `./scheduler/sche_bin/scx_rusty`)
   - Runs schbench with the same parameters
   - Stops the scheduler after the test completes
   - Collects performance metrics

## Usage

### Basic Usage
```bash
python schbench_bench_start.py
```

### Command-line Options
```bash
python schbench_bench_start.py [OPTIONS]

Options:
  --schbench-path PATH     Path to schbench binary (default: ../schbench/schbench)
  --results-dir DIR        Directory to store results (default: results)
  --production-only        Test only production-ready schedulers
  --runtime SECONDS        Test runtime in seconds (default: 30)
  --message-threads NUM    Number of message threads per group (default: 2)
  --message-groups NUM     Number of message thread groups (default: 4)
```

### Examples

Test all schedulers with default settings:
```bash
python schbench_bench_start.py
```

Test only production schedulers with longer runtime:
```bash
python schbench_bench_start.py --production-only --runtime 60
```

Test with higher thread count:
```bash
python schbench_bench_start.py --message-threads 4 --message-groups 8
```

## Output

The script generates:

1. **Console Output**: Real-time test progress and performance summary
2. **JSON Results**: `results/schbench_results.json` containing detailed metrics
3. **Performance Figures**: `results/schbench_performance_comparison.png` with:
   - Latency percentiles comparison (50th, 95th, 99th)
   - Throughput comparison
   - Latency vs Throughput scatter plot
   - Overall performance score

## Metrics Collected

- **Request Latencies**: 50th, 95th, and 99th percentile latencies in microseconds
- **Throughput**: Average requests per second
- **Exit Code**: Success/failure status of each test

## Prerequisites

1. **Build schbench**:
   ```bash
   cd ../schbench
   make
   ```

2. **Build schedulers**:
   ```bash
   cd /root/yunwei37/ai-os
   make
   ```

3. **Required permissions**: Root access is needed to load/unload schedulers

## Understanding the Results

- **Lower latencies** indicate better responsiveness
- **Higher throughput** indicates better overall performance
- The **combined performance score** normalizes both metrics for easy comparison
- Production schedulers (scx_rusty, scx_lavd, etc.) typically show better performance

## Troubleshooting

1. **"schbench not found"**: Build schbench first or specify correct path with `--schbench-path`
2. **"Permission denied"**: Run with sudo for scheduler loading/unloading
3. **"Scheduler failed to start"**: Check kernel compatibility and sched-ext support