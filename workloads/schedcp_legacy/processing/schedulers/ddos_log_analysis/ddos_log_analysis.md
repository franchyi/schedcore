# DDoS Log Analysis

**ID:** `ddos_log_analysis`

**Category:** data_processing

**Description:** Security log analysis with temporal spike pattern (DDoS simulation)

## Workload Purpose & Characteristics

This workload simulates security log analysis during a DDoS attack, where log volumes spike dramatically. The scenario includes 39 processes analyzing normal traffic logs (30K normal + 8K error logs) and 1 process handling the DDoS spike (1M normal + 500K error logs). This 50:1 volume ratio represents real-world security monitoring where attack detection must process massive log surges.

## Key Performance Characteristics

- **I/O and CPU mixed workload**: Decompression, parsing, and pattern analysis
- **Memory-intensive processing**: Large log volumes require substantial memory
- **Compressed data handling**: Works with gzipped log files
- **Complex analytics**: Pattern detection, aggregation, and statistical analysis
- **Temporal data processing**: Time-series analysis of security events

## Optimization Goals

1. **Minimize attack detection latency**: Ensure DDoS spike analysis completes quickly
2. **Maintain baseline monitoring**: Keep normal log analysis responsive
3. **Optimize memory usage**: Efficient handling of large compressed datasets
4. **Maximize throughput**: Process maximum log volume per unit time
5. **Prevent resource starvation**: Balance resources between normal and spike analysis

## Scheduling Algorithm

The optimal scheduler for DDoS log analysis should implement:

1. **Process detection**: Identify "small_pandas_etl_test.py" (normal) and "large_pandas_etl_test.py" (spike) processes
2. **Priority assignment**: Highest priority to large_pandas_etl_test.py for critical attack analysis
3. **Resource allocation**:
   - Large process: 20ms time slices for sustained analysis
   - Small processes: 5ms time slices for responsive monitoring
4. **Memory-aware scheduling**: Consider memory pressure when dispatching tasks
5. **I/O optimization**: Group processes to minimize disk contention during log reading

## Dependencies

- python3
- gzip
- awk

## Small Setup Commands

```bash
cp $ORIGINAL_CWD/assets/pandas_etl_prepare.py $ORIGINAL_CWD/assets/pandas_etl_test.py .
cp pandas_etl_test.py small_pandas_etl_test.py
chmod +x pandas_etl_prepare.py small_pandas_etl_test.py
python3 pandas_etl_prepare.py --normal-logs 30000 --error-logs 8000 --output etl_small.gz
```

## Large Setup Commands

```bash
cp $ORIGINAL_CWD/assets/pandas_etl_prepare.py $ORIGINAL_CWD/assets/pandas_etl_test.py .
cp pandas_etl_test.py large_pandas_etl_test.py
chmod +x pandas_etl_prepare.py large_pandas_etl_test.py
python3 pandas_etl_prepare.py --normal-logs 1000000 --error-logs 500000 --output etl_large.gz
```

## Small Execution Commands

```bash
./small_pandas_etl_test.py etl_small.gz
```

## Large Execution Commands

```bash
./large_pandas_etl_test.py etl_large.gz
```

## Cleanup Commands

```bash
rm -f etl_small.gz etl_large.gz
rm -f /tmp/pandas_*
rm -f small_pandas_etl_test.py large_pandas_etl_test.py pandas_etl_prepare.py pandas_etl_test.py
```
