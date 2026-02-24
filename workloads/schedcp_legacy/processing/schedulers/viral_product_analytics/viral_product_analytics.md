# Viral Product Analytics

**ID:** `viral_product_analytics`

**Category:** data_processing

**Description:** Retail analytics with temporal hot product pattern (trending item simulation)

## Workload Purpose & Characteristics

This workload simulates e-commerce analytics during viral product events, where certain items experience massive popularity spikes. The scenario includes 39 processes analyzing moderate transaction volumes (8K regular + 12K hot product transactions) and 1 process handling viral surge data (100K regular + 700K hot product transactions). This represents real-world retail analytics where trending products create severe processing imbalances.

## Key Performance Characteristics

- **Join-heavy operations**: Product-transaction joins dominate processing
- **Skewed data distribution**: Hot products create join key imbalance
- **Memory-intensive joins**: Large hash tables for product lookups
- **Complex aggregations**: Sales metrics, inventory tracking, recommendation calculations
- **Time-window analytics**: Trending detection requires temporal processing

## Optimization Goals

1. **Minimize analytics latency**: Ensure viral product insights are generated quickly
2. **Optimize join performance**: Efficient handling of skewed join keys
3. **Maximize throughput**: Process maximum transactions per second
4. **Prevent memory exhaustion**: Manage memory usage during large joins
5. **Maintain real-time analytics**: Keep dashboard metrics current despite load spikes

## Scheduling Algorithm

The optimal scheduler for viral product analytics should implement:

1. **Process identification**: Match "small_flink_join_test.py" and "large_flink_join_test.py" processes
2. **Viral surge prioritization**: Give large_flink_join_test.py highest priority
3. **Resource allocation strategy**:
   - Large analytics: 25ms time slices for complex joins
   - Small analytics: 5ms time slices for regular processing
4. **Memory-aware scheduling**: Monitor and manage memory pressure from large joins
5. **Cache optimization**: Keep hot product data in CPU cache for repeated access

## Dependencies

- python3
- awk

## Small Setup Commands

```bash
cp $ORIGINAL_CWD/assets/flink_join_prepare.py $ORIGINAL_CWD/assets/flink_join_test.py .
cp flink_join_test.py small_flink_join_test.py
chmod +x flink_join_prepare.py small_flink_join_test.py
python3 flink_join_prepare.py --regular-transactions 8000 --hot-transactions 12000 --output flink_small.csv
```

## Large Setup Commands

```bash
cp $ORIGINAL_CWD/assets/flink_join_prepare.py $ORIGINAL_CWD/assets/flink_join_test.py .
cp flink_join_test.py large_flink_join_test.py
chmod +x flink_join_prepare.py large_flink_join_test.py
python3 flink_join_prepare.py --regular-transactions 100000 --hot-transactions 700000 --output flink_large.csv
```

## Small Execution Commands

```bash
./small_flink_join_test.py flink_small.csv
```

## Large Execution Commands

```bash
./large_flink_join_test.py flink_large.csv
```

## Cleanup Commands

```bash
rm -f flink_small.csv flink_large.csv
rm -f /tmp/flink_*
rm -f small_flink_join_test.py large_flink_join_test.py flink_join_prepare.py flink_join_test.py
```
