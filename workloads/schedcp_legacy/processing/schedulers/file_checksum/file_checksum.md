# Parallel File System Operations

**ID:** `file_checksum`

**Category:** file_processing

**Description:** Checksum operations with one large file blocking completion

## Workload Purpose & Characteristics

This workload represents parallel file integrity checking operations common in backup systems, data verification pipelines, and storage management. The scenario involves 39 processes computing checksums for 200MB files and 1 process handling a 1GB file, creating a 5:1 size imbalance that leads to significant completion time variance.

## Key Performance Characteristics

- **I/O-bound with CPU processing**: Sequential file reading combined with hash computation
- **Memory-mapped I/O patterns**: Efficient file access through system buffers
- **Predictable disk access**: Sequential reads with minimal seeking
- **Hash computation overhead**: MD5/SHA calculation adds CPU component
- **Cache-friendly for small files**: 200MB files may fit in page cache

## Optimization Goals

1. **Minimize total checksum computation time**: Reduce overall completion time for all files
2. **Prioritize large file processing**: Ensure 1GB file checksum starts early and runs continuously
3. **Optimize I/O scheduling**: Minimize disk contention between parallel reads
4. **Maintain system responsiveness**: Balance I/O load to prevent system sluggishness
5. **Efficient cache utilization**: Maximize buffer cache hits for repeated access patterns

## Scheduling Algorithm

The optimal scheduler for file checksum operations should implement:

1. **Process identification**: Match "small_file_checksum.py" and "large_file_checksum.py" by name
2. **I/O-aware prioritization**: Give large_file_checksum.py priority for both CPU and I/O resources
3. **Time slice tuning**:
   - Large file process: 20ms slices for sustained I/O and computation
   - Small file processes: 5ms slices for quick completion
4. **I/O batching strategy**: Group small file operations to reduce context switching overhead
5. **NUMA awareness**: Keep processes near their file data in memory for optimal access

## Dependencies

- python3

## Small Setup Commands

```bash
mkdir -p large-dir
dd if=/dev/urandom of=large-dir/short_file.dat bs=1M count=200 2>/dev/null
cp $ORIGINAL_CWD/assets/file_checksum.py .
cp file_checksum.py small_file_checksum.py
chmod +x small_file_checksum.py
```

## Large Setup Commands

```bash
mkdir -p large-dir
dd if=/dev/urandom of=large-dir/long_file.dat bs=1M count=1000 2>/dev/null
cp $ORIGINAL_CWD/assets/file_checksum.py .
cp file_checksum.py large_file_checksum.py
chmod +x large_file_checksum.py
```

## Small Execution Commands

```bash
./small_file_checksum.py large-dir/short_file.dat
```

## Large Execution Commands

```bash
./large_file_checksum.py large-dir/long_file.dat
```

## Cleanup Commands

```bash
rm -rf large-dir/
rm -f checksums.txt
rm -f small_file_checksum.py large_file_checksum.py file_checksum.py
```
