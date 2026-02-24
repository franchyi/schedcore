# Workload Processing Test Scripts

This directory contains Python scripts that simulate different distributed computing workloads with long-tail/skewed data patterns. Each workload consists of a data preparation script and a processing script.

## Overview

The scripts simulate four different distributed computing patterns:
1. **Dask GroupBy** - Customer analytics with skewed customer data
2. **Pandas ETL** - Log processing with DDoS spike pattern
3. **Flink Join** - Retail analytics with popular product skew
4. **Spark Shuffle** - Key-value processing with partition skew

## Scripts

### 1. Dask GroupBy Test

Simulates customer analytics where one customer has significantly more transactions than others.

#### Data Preparation
```bash
python3 dask_groupby_prepare.py [options]

Options:
  --regular-size NUM      Number of transactions per regular customer (default: 1000)
  --hot-size NUM          Number of transactions for hot customer (default: 100000)
  --num-customers NUM     Number of regular customers (default: 99)
  --output FILE           Output CSV file (default: dask_data.csv)

Examples:
  # Small dataset (~10K rows)
  python3 dask_groupby_prepare.py --regular-size 100 --hot-size 5000

  # Large dataset (~600K rows)
  python3 dask_groupby_prepare.py --regular-size 1000 --hot-size 500000

  # Custom configuration
  python3 dask_groupby_prepare.py --num-customers 50 --regular-size 500 --hot-size 50000
```

#### Processing
```bash
python3 dask_groupby_test.py data_file

Example:
  python3 dask_groupby_test.py dask_data.csv
```

### 2. Pandas ETL Test

Simulates log file processing with a DDoS attack creating a spike in error logs from one server.

#### Data Preparation
```bash
python3 pandas_etl_prepare.py [options]

Options:
  --normal-logs NUM       Number of normal log entries (default: 10000)
  --error-logs NUM        Number of error log entries for DDoS spike (default: 100000)
  --num-servers NUM       Number of normal servers (default: 39)
  --time-window SEC       Time window in seconds for normal logs (default: 86400 = 24h)
  --spike-window SEC      Time window in seconds for DDoS spike (default: 300 = 5min)
  --output FILE           Output gzipped log file (default: etl_logs.gz)

Examples:
  # Small dataset (~11K logs)
  python3 pandas_etl_prepare.py --normal-logs 10000 --error-logs 1000

  # Large dataset (~200K logs)
  python3 pandas_etl_prepare.py --normal-logs 100000 --error-logs 100000

  # Custom time windows
  python3 pandas_etl_prepare.py --time-window 3600 --spike-window 60
```

#### Processing
```bash
python3 pandas_etl_test.py log_file

Example:
  python3 pandas_etl_test.py etl_logs.gz
```

### 3. Flink Join Test

Simulates retail transaction processing where one product (e.g., trending item) has significantly more transactions.

#### Data Preparation
```bash
python3 flink_join_prepare.py [options]

Options:
  --regular-transactions NUM   Number of transactions per regular product (default: 1000)
  --hot-transactions NUM       Number of transactions for popular product (default: 100000)
  --num-products NUM           Number of regular products (default: 99)
  --time-window SEC            Time window in seconds for transactions (default: 86400 = 24h)
  --hot-window SEC             Time window in seconds for hot product (default: 7200 = 2h)
  --output FILE                Output CSV file (default: flink_transactions.csv)

Examples:
  # Small dataset (~20K transactions)
  python3 flink_join_prepare.py --regular-transactions 100 --hot-transactions 10000

  # Large dataset (~200K transactions)
  python3 flink_join_prepare.py --regular-transactions 1000 --hot-transactions 100000

  # Flash sale scenario
  python3 flink_join_prepare.py --hot-transactions 50000 --hot-window 1800
```

#### Processing
```bash
python3 flink_join_test.py data_file

Example:
  python3 flink_join_test.py flink_transactions.csv
```

### 4. Spark Shuffle Test

Simulates key-value shuffle operations where one key has significantly more values (hot key problem).

#### Data Preparation
```bash
python3 spark_skew_prepare.py [options]

Options:
  --regular-keys NUM      Number of values per regular key (default: 1000)
  --hot-keys NUM          Number of values for hot key (default: 1000000)
  --num-partitions NUM    Number of regular partitions/keys (default: 99)
  --output FILE           Output CSV file (default: spark_data.csv)

Examples:
  # Small dataset (~100K rows)
  python3 spark_skew_prepare.py --regular-keys 100 --hot-keys 10000

  # Large dataset (~1.1M rows)
  python3 spark_skew_prepare.py --regular-keys 1000 --hot-keys 1000000

  # Extreme skew
  python3 spark_skew_prepare.py --regular-keys 100 --hot-keys 100000
```

#### Processing
```bash
python3 spark_skew_test.py data_file

Example:
  python3 spark_skew_test.py spark_data.csv
```

## Workload Characteristics

All workloads demonstrate the "long-tail problem" where:
- Most tasks/keys/customers have small amounts of data
- One or few entities have disproportionately large amounts of data
- This creates processing bottlenecks in distributed systems

### Skew Ratios

Default configurations create these skew ratios:
- **Dask GroupBy**: 100x skew (100K vs 1K transactions)
- **Pandas ETL**: 10x skew (100K error logs vs 10K normal logs)
- **Flink Join**: 100x skew (100K vs 1K transactions)
- **Spark Shuffle**: 1000x skew (1M vs 1K values)

## Performance Testing

To test scheduler performance with these workloads:

1. Generate test data with desired size
2. Run the processing script multiple times in parallel
3. Measure completion times to identify long-tail tasks
4. Compare performance with different schedulers

Example workflow:
```bash
# Prepare data
python3 dask_groupby_prepare.py --regular-size 1000 --hot-size 100000 --output dask_small.csv
python3 dask_groupby_prepare.py --regular-size 100 --hot-size 5000000 --output dask_large.csv

# Run tests (39 small + 1 large in parallel)
for i in {1..39}; do
    python3 dask_groupby_test.py dask_small.csv &
done
python3 dask_groupby_test.py dask_large.csv &
wait
```

## Requirements

All scripts require:
- Python 3.6+
- pandas
- Standard library modules (time, argparse, random, gzip, re, math)

No external big data frameworks (Spark, Flink, Dask) are required - the scripts simulate their workload patterns.