# File Compression

**ID:** `compression`

**Category:** file_processing

**Description:** Compression of mixed-size files with severe load imbalance

## Workload Purpose & Characteristics

This workload simulates a parallel file compression scenario typical in batch processing systems. The workload exhibits extreme load imbalance with 39 small files (3M records each) and 1 large file (20M records), creating a 6.67:1 size ratio. The compression tasks are CPU-intensive with minimal I/O, making them ideal for demonstrating scheduler optimization opportunities.

## Key Performance Characteristics

- **CPU-bound workload**: Compression algorithm dominates execution time
- **Predictable resource usage**: Each task uses single-threaded compression with consistent CPU utilization
- **Severe load imbalance**: Large file takes ~6.67x longer than small files
- **No inter-task dependencies**: All compression tasks are independent
- **Memory requirements**: Moderate, scales with file size

## Optimization Goals

1. **Minimize total completion time**: Reduce wall-clock time from task start to all tasks complete
2. **Maximize CPU utilization**: Keep all cores busy until the last task completes
3. **Prioritize long-running task**: Ensure the large compression task gets sufficient CPU time early
4. **Fair resource distribution**: Balance CPU allocation when multiple compression tasks compete

## Scheduling Algorithm

The optimal scheduler for this workload should implement:

1. **Task identification**: Detect compression processes by matching "small_compression.py" and "large_compression.py" process names
2. **Priority assignment**: Give higher priority to "large_compression.py" to ensure it starts early and runs continuously
3. **Time slice allocation**:
   - Large task: 15ms time slices for sustained throughput
   - Small tasks: 3ms time slices for responsiveness
4. **Queue management**: Use separate dispatch queues for large and small tasks, always serving large task queue first
5. **CPU affinity**: Keep large task on same CPU to maximize cache efficiency

## Dependencies

- python3

## Small Setup Commands

```bash
mkdir -p test_data
seq 1 3000000 > test_data/short_file.dat
cp $ORIGINAL_CWD/assets/compression.py .
cp compression.py small_compression.py
chmod +x small_compression.py
```

## Large Setup Commands

```bash
mkdir -p test_data
seq 1 20000000 > test_data/large_file.dat
cp $ORIGINAL_CWD/assets/compression.py .
cp compression.py large_compression.py
chmod +x large_compression.py
```

## Small Execution Commands

```bash
./small_compression.py test_data/short_file.dat 9
```

## Large Execution Commands

```bash
./large_compression.py test_data/large_file.dat 9
```

## Cleanup Commands

```bash
rm -rf test_data/
rm -f *.gz
rm -f small_compression.py large_compression.py compression.py
```
