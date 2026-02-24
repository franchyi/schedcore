#!/usr/bin/env python3
"""
Dask-like groupby simulation without Dask dependency
Simulates customer analytics with power-law distribution
"""

import pandas as pd
import time
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Dask-like groupby test')
    parser.add_argument('data_file', type=str, help='Path to CSV data file')
    
    args = parser.parse_args()
    
    print(f"Processing groupby on {args.data_file}...")
    start_time = time.time()
    
    # Load data from file
    data = pd.read_csv(args.data_file, names=['k', 'v'])
    print(f"Loaded {len(data)} rows")
    
    # Perform multiple groupby operations to simulate complex analytics
    # Customer analytics: sum, mean, count, std
    result_sum = data.groupby('k')['v'].sum()
    result_mean = data.groupby('k')['v'].mean()
    result_count = data.groupby('k')['v'].count()
    result_std = data.groupby('k')['v'].std()
    
    # Additional aggregations
    result_min = data.groupby('k')['v'].min()
    result_max = data.groupby('k')['v'].max()
    
    # Combine all results
    final_result = pd.DataFrame({
        'sum': result_sum,
        'mean': result_mean,
        'count': result_count,
        'std': result_std,
        'min': result_min,
        'max': result_max
    })
    
    # Sort by sum descending
    final_result = final_result.sort_values('sum', ascending=False)
    
    end_time = time.time()
    
    print(f"Groupby complete in {end_time - start_time:.2f}s")
    print(f"Total groups: {len(final_result)}")
    print(f"Total sum: {result_sum.sum()}")
    print(f"Top 5 groups by sum:")
    print(final_result.head())