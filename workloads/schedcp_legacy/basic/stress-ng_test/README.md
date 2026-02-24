# stress-ng Benchmark Test Framework

This directory contains a test framework for running stress-ng benchmarks with different Linux kernel schedulers.

## Overview

The framework tests various stress workloads (CPU, memory, I/O) under different scheduler configurations to evaluate scheduler performance under system stress.

## Structure

- `stress_ng_bench_start.py` - Main entry point for running benchmarks
- `stress_ng_tester.py` - Core testing framework that manages stress-ng execution
- `requirements.txt` - Python dependencies
- `results/` - Directory for storing test results and performance figures

## Prerequisites

1. Build stress-ng first:
   ```bash
   cd ../stress-ng
   make
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Ensure schedulers are built:
   ```bash
   cd ../../../scheduler
   make
   ```

## Usage

### Basic Usage

Run all stress tests with default settings:
```bash
python stress_ng_bench_start.py
```

### Advanced Options

```bash
# Run for 60 seconds per scheduler
python stress_ng_bench_start.py --duration 60

# Test only CPU and memory stress
python stress_ng_bench_start.py --stress-tests cpu vm

# Use specific number of workers
python stress_ng_bench_start.py --cpu-workers 4 --vm-workers 4 --io-workers 2

# Test specific schedulers only
python stress_ng_bench_start.py --schedulers scx_rusty scx_lavd

# Skip baseline test
python stress_ng_bench_start.py --skip-baseline
```

### Command Line Options

- `--duration`: Test duration for each scheduler in seconds (default: 30)
- `--cpu-workers`: Number of CPU stress workers (default: 0 = auto)
- `--vm-workers`: Number of VM/memory stress workers (default: 2)
- `--io-workers`: Number of I/O stress workers (default: 2)
- `--stress-tests`: Which stress tests to run (default: cpu vm io)
- `--output`: Output file for results (default: results/stress_ng_results.json)
- `--skip-baseline`: Skip the baseline test without any scheduler
- `--schedulers`: Specific schedulers to test (default: all available)

## Stress Tests

The framework supports three main stress test types:

1. **CPU Stress** (`cpu`): Tests CPU-intensive workloads with various algorithms
2. **Memory Stress** (`vm`): Tests virtual memory operations and allocation
3. **I/O Stress** (`io`): Tests I/O operations and filesystem stress

## Output

The framework generates:

1. **JSON Results** (`results/stress_ng_results.json`): Detailed metrics including:
   - Bogo-operations per second for each stressor
   - CPU time (user and system)
   - Real time elapsed
   - Aggregate performance metrics

2. **Performance Figures**:
   - `stress_ng_performance_comparison.png`: Per-stressor and aggregate performance
   - `stress_ng_normalized_performance.png`: Performance relative to baseline

3. **Console Summary**: Real-time progress and performance ranking

## Metrics

The primary metric is **bogo-operations per second** (bogo-ops/s), which represents the throughput of stress operations. Higher values indicate better performance under stress.

## Example

```bash
# Run a comprehensive test with custom settings
python stress_ng_bench_start.py \
    --duration 45 \
    --cpu-workers 8 \
    --vm-workers 4 \
    --io-workers 4 \
    --stress-tests cpu vm io \
    --schedulers scx_rusty scx_lavd scx_bpfland
```

This will:
- Run each scheduler for 45 seconds
- Use 8 CPU workers, 4 VM workers, and 4 I/O workers
- Test all three stress types
- Only test the specified schedulers
- Generate performance comparison figures