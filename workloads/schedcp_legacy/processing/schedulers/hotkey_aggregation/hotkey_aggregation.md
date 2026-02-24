# Hot Key Aggregation

**ID:** `hotkey_aggregation`

**Category:** data_processing

**Description:** Analytics with skewed data distribution (hot key problem)

## Workload Purpose & Characteristics

This workload simulates distributed analytics scenarios where data exhibits severe key skew, a common problem in big data processing. The scenario includes 39 processes handling moderately skewed data (8K regular keys, 15K hot keys) and 1 process dealing with extreme skew (100K regular keys, 800K hot keys). This represents real-world analytics where certain keys (users, products, regions) dominate the dataset.

## Key Performance Characteristics

- **Memory-intensive aggregation**: In-memory hash tables for key-value accumulation
- **CPU-bound computation**: Heavy aggregation and statistical calculations
- **Data skew handling**: Extreme imbalance in key distribution
- **Cache pressure**: Hot keys create memory access hotspots
- **Non-uniform processing time**: Skewed partitions take significantly longer

## Optimization Goals

1. **Minimize aggregation completion time**: Reduce total time for all analytics tasks
2. **Handle data skew efficiently**: Ensure heavily skewed partition gets adequate resources
3. **Optimize memory access patterns**: Improve cache utilization for hot keys
4. **Balance CPU utilization**: Prevent idle cores while skewed partition processes
5. **Maintain throughput**: Process maximum records per second across all tasks

## Scheduling Algorithm

The optimal scheduler for hot key aggregation should implement:

1. **Process identification**: Match "small_spark_skew_test.py" and "large_spark_skew_test.py" processes
2. **Skew-aware prioritization**: Give large_spark_skew_test.py highest priority
3. **Time slice optimization**:
   - Large skewed task: 20ms slices for sustained processing
   - Small skewed tasks: 5ms slices for fair progress
4. **Memory-aware scheduling**: Consider cache locality and memory bandwidth
5. **CPU affinity**: Pin large task to specific cores to maximize cache reuse

## Dependencies

- python3

## Small Setup Commands

```bash
cp $ORIGINAL_CWD/assets/spark_skew_prepare.py $ORIGINAL_CWD/assets/spark_skew_test.py .
cp spark_skew_test.py small_spark_skew_test.py
chmod +x spark_skew_prepare.py small_spark_skew_test.py
python3 spark_skew_prepare.py --regular-keys 8000 --hot-keys 15000 --output spark_small.csv
```

## Large Setup Commands

```bash
cp $ORIGINAL_CWD/assets/spark_skew_prepare.py $ORIGINAL_CWD/assets/spark_skew_test.py .
cp spark_skew_test.py large_spark_skew_test.py
chmod +x spark_skew_prepare.py large_spark_skew_test.py
python3 spark_skew_prepare.py --regular-keys 100000 --hot-keys 800000 --output spark_large.csv
```

## Small Execution Commands

```bash
./small_spark_skew_test.py spark_small.csv
```

## Large Execution Commands

```bash
./large_spark_skew_test.py spark_large.csv
```

## Cleanup Commands

```bash
rm -f spark_small.csv spark_large.csv
rm -f small_spark_skew_test.py large_spark_skew_test.py spark_skew_prepare.py spark_skew_test.py
```
