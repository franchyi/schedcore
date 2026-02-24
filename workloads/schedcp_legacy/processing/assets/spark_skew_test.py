#!/usr/bin/env python3
"""
Spark-like skewed workload simulation without Spark dependency
Simulates the hot key problem in distributed processing
"""

import pandas as pd
import time
import argparse
import math

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Spark-like shuffle test')
    parser.add_argument('data_file', type=str, help='Path to data file')
    
    args = parser.parse_args()
    
    print(f"Processing shuffle on {args.data_file}...")
    start_time = time.time()
    
    # Load data
    df = pd.read_csv(args.data_file, names=['key', 'value'])
    print(f"Loaded {len(df)} records")
    
    # Simulate shuffle operation with multiple transformations
    # 1. Map phase: apply transformations
    df['mapped_value'] = df['value'].apply(lambda x: x * 2 + 1)
    df['sqrt_value'] = df['value'].apply(lambda x: math.sqrt(abs(x)))
    df['log_value'] = df['value'].apply(lambda x: math.log(abs(x) + 1))
    
    # 2. Shuffle phase: group by key and aggregate
    shuffled = df.groupby('key').agg({
        'mapped_value': ['sum', 'mean', 'count', 'std'],
        'sqrt_value': ['sum', 'mean'],
        'log_value': ['sum', 'mean'],
        'value': ['min', 'max', 'median']
    })
    
    # 3. Reduce phase: final aggregations
    # Calculate percentiles
    percentiles = df.groupby('key')['value'].quantile([0.25, 0.5, 0.75, 0.95])
    
    # Calculate unique values per key
    unique_counts = df.groupby('key')['value'].nunique()
    
    # Sort by total sum to find hot keys
    key_totals = shuffled[('mapped_value', 'sum')].sort_values(ascending=False)
    
    end_time = time.time()
    
    print(f"Shuffle complete in {end_time - start_time:.2f}s")
    print(f"Total keys: {len(shuffled)}")
    print(f"Total values processed: {df['mapped_value'].sum()}")
    
    # Show hot keys
    print(f"\nTop 5 keys by sum:")
    for key, total in key_totals.head().items():
        count = shuffled.loc[key, ('mapped_value', 'count')]
        print(f"  Key {key}: sum={total:.0f}, count={count}")
    
    # Show skew ratio
    if len(key_totals) > 1:
        max_count = shuffled[('mapped_value', 'count')].max()
        avg_count = shuffled[('mapped_value', 'count')].mean()
        print(f"\nSkew ratio: {max_count/avg_count:.1f}x (max/avg)")