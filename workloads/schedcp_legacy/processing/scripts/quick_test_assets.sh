#!/bin/bash
# Quick test script for assets - tests basic functionality only

echo "Quick Asset Test Script"
echo "======================"
echo "Testing basic functionality of all assets..."
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Function to test a command
test_cmd() {
    local description="$1"
    local command="$2"
    
    echo -n "Testing $description... "
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        echo "  Command: $command"
        return 1
    fi
}

# Change to correct directory
cd "$(dirname "$0")"

# Test C programs
echo -e "\n1. C Programs:"
test_cmd "compile short.c" "gcc -O2 assets/short.c -lm -o /tmp/short_test"
test_cmd "compile long.c" "gcc -O2 assets/long.c -lm -o /tmp/long_test"
test_cmd "run short" "/tmp/short_test"
test_cmd "run long" "/tmp/long_test"
rm -f /tmp/short_test /tmp/long_test

# Test Python scripts exist and have correct syntax
echo -e "\n2. Python Scripts Syntax Check:"
for script in assets/*_prepare.py assets/*_test.py; do
    if [ -f "$script" ]; then
        test_cmd "$(basename $script)" "python3 -m py_compile $script"
    fi
done

# Test data preparation with minimal datasets
echo -e "\n3. Data Preparation (minimal):"
test_cmd "dask_groupby_prepare" "python3 assets/dask_groupby_prepare.py --regular-size 10 --hot-size 100 --num-customers 5 --output /tmp/dask_quick.csv"
test_cmd "pandas_etl_prepare" "python3 assets/pandas_etl_prepare.py --normal-logs 100 --error-logs 200 --num-servers 5 --output /tmp/etl_quick.gz"
test_cmd "flink_join_prepare" "python3 assets/flink_join_prepare.py --regular-transactions 10 --hot-transactions 100 --num-products 5 --output /tmp/flink_quick.csv"
test_cmd "spark_skew_prepare" "python3 assets/spark_skew_prepare.py --regular-keys 10 --hot-keys 100 --num-partitions 5 --output /tmp/spark_quick.csv"

# Test data processing
echo -e "\n4. Data Processing:"
test_cmd "dask_groupby_test" "python3 assets/dask_groupby_test.py /tmp/dask_quick.csv"
test_cmd "pandas_etl_test" "python3 assets/pandas_etl_test.py /tmp/etl_quick.gz"
test_cmd "flink_join_test" "python3 assets/flink_join_test.py /tmp/flink_quick.csv"
test_cmd "spark_skew_test" "python3 assets/spark_skew_test.py /tmp/spark_quick.csv"

# Cleanup
echo -e "\n5. Cleanup:"
rm -f /tmp/dask_quick.csv /tmp/etl_quick.gz /tmp/flink_quick.csv /tmp/spark_quick.csv
echo "Temporary files cleaned up"

echo -e "\nQuick test completed!"
echo "For comprehensive testing, run: python3 test_assets.py"