# Linux Kernel Build Benchmark

This directory contains a benchmark framework for testing Linux kernel compilation performance under different schedulers.

## Overview

The framework measures kernel build times with various scheduler configurations to evaluate scheduler performance under CPU-intensive compilation workloads. It supports multiple kernel configurations and parallel build options.

## Structure

- `linux_build_bench_start.py` - Main entry point for running benchmarks
- `linux_build_tester.py` - Core testing framework that manages kernel builds
- `requirements.txt` - Python dependencies
- `Makefile` - Helper for kernel configuration
- `results/` - Directory for storing test results and performance figures
- `linux/` - Linux kernel source directory (created after cloning)

## Prerequisites

1. Clone the Linux kernel (if not already done):
   ```bash
   git clone --depth=1 https://github.com/torvalds/linux.git
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

4. Install kernel build dependencies:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install build-essential bc kmod cpio flex bison libncurses5-dev libelf-dev libssl-dev

   # Fedora/RHEL
   sudo dnf install gcc gcc-c++ make bc openssl-devel elfutils-libelf-devel ncurses-devel
   ```

## Usage

### Basic Usage

Run benchmark with default settings (tinyconfig):
```bash
python linux_build_bench_start.py
```

### Advanced Options

```bash
# Use specific kernel config
python linux_build_bench_start.py --config defconfig

# Use specific number of parallel jobs
python linux_build_bench_start.py --jobs 8

# Clean between builds (ensures cold cache)
python linux_build_bench_start.py --clean-between

# Test specific schedulers only
python linux_build_bench_start.py --schedulers scx_rusty scx_lavd

# Multiple runs per scheduler for better statistics
python linux_build_bench_start.py --repeat 3

# Skip baseline test
python linux_build_bench_start.py --skip-baseline
```

### Command Line Options

- `--jobs`: Number of parallel build jobs (default: 0 = auto/nproc)
- `--config`: Kernel config to use (default: tinyconfig)
  - `tinyconfig`: Minimal kernel, fastest builds (~1-2 minutes)
  - `allnoconfig`: Very minimal config
  - `defconfig`: Default config for architecture (~5-10 minutes)
- `--clean-between`: Clean build artifacts between tests
- `--output`: Output file for results (default: results/linux_build_results.json)
- `--skip-baseline`: Skip the baseline test without scheduler
- `--schedulers`: Specific schedulers to test (default: all available)
- `--repeat`: Number of times to repeat each test (default: 1)
- `--kernel-dir`: Directory containing kernel source (default: linux)

## Kernel Configuration

Use the provided Makefile for kernel configuration:

```bash
# Configure with default config
make config

# Configure with minimal config (fastest builds)
make tinyconfig

# Configure with allnoconfig
make allnoconfig

# Clean build artifacts
make clean

# Deep clean including config
make distclean

# Show kernel version
make version
```

## Output

The framework generates:

1. **JSON Results** (`results/linux_build_results.json`):
   - Build times for each scheduler
   - Average, min, max, and standard deviation
   - Test configuration details

2. **Performance Figures**:
   - `linux_build_time_comparison.png`: Raw build times with error bars
   - `linux_build_normalized_performance.png`: Performance relative to baseline
   - `linux_build_speedup.png`: Speedup factors compared to baseline

3. **Console Summary**: Real-time progress and performance ranking

## Metrics

The primary metric is **build time in seconds**. Lower values indicate better performance. The framework also calculates:
- Average build time across multiple runs
- Standard deviation for consistency measurement
- Speedup factor relative to baseline
- Normalized performance percentage

## Examples

### Quick Test
```bash
# Fast test with tiny kernel config
python linux_build_bench_start.py --config tinyconfig --jobs 16
```

### Comprehensive Test
```bash
# Full test with multiple runs and statistics
python linux_build_bench_start.py \
    --config defconfig \
    --jobs 32 \
    --repeat 3 \
    --clean-between \
    --schedulers scx_rusty scx_lavd scx_bpfland scx_simple
```

### Production Benchmark
```bash
# Production-ready schedulers with consistent environment
python linux_build_bench_start.py \
    --config defconfig \
    --repeat 5 \
    --clean-between \
    --schedulers scx_rusty scx_lavd scx_flatcg scx_simple
```

## Tips

1. **Config Selection**:
   - Use `tinyconfig` for quick tests (1-2 minutes per build)
   - Use `defconfig` for realistic workloads (5-10 minutes per build)

2. **Consistency**:
   - Use `--clean-between` for more consistent results
   - Run multiple times with `--repeat` for statistical significance
   - Close other applications to reduce interference

3. **Performance**:
   - Adjust `--jobs` based on your CPU cores
   - Monitor system resources during tests
   - Consider thermal throttling on long runs

## Troubleshooting

1. **Build Failures**:
   - Ensure all kernel build dependencies are installed
   - Check kernel configuration is valid
   - Verify sufficient disk space (>2GB for defconfig)

2. **Scheduler Errors**:
   - Ensure schedulers are built (`make` in scheduler directory)
   - Check for conflicting schedulers already running
   - Verify kernel has sched_ext support

3. **Performance Issues**:
   - Check CPU frequency scaling settings
   - Monitor for thermal throttling
   - Ensure sufficient RAM for parallel builds

for the command "cd workloads/linux-build-bench/linux && make clean -j$(nproc) && make tinyconfig -j$(nproc) && make -j$(nproc)", optimize the scheduler with the schedcp mcp tools.

'make -C workloads/linux-build-bench/linux clean -j && make -C workloads/linux-build-bench/linux -j'


autotune/target/release/autotune cc 'make -C workloads/linux-build-bench/linux clean -j && make -C workloads/linux-build-bench/linux -j'



