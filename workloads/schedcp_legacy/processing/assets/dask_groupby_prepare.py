#!/usr/bin/env python3
"""
Prepare data for dask_groupby_test.py
Creates CSV files with skewed customer data
"""

import argparse
import random

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare data for Dask groupby test')
    parser.add_argument('--regular-size', type=int, default=1000,
                        help='Number of transactions per regular customer (default: 1000)')
    parser.add_argument('--hot-size', type=int, default=100000,
                        help='Number of transactions for hot customer (default: 100000)')
    parser.add_argument('--num-customers', type=int, default=99,
                        help='Number of regular customers (default: 99)')
    parser.add_argument('--output', type=str, default='dask_data.csv',
                        help='Output CSV file')
    
    args = parser.parse_args()
    
    print(f"Generating dataset for Dask groupby test...")
    print(f"  Regular customers: {args.num_customers} with ~{args.regular_size} transactions each")
    print(f"  Hot customer: 1 with {args.hot_size} transactions")
    
    total_rows = 0
    with open(args.output, 'w') as f:
        # Regular customers
        for customer_id in range(args.num_customers):
            # Add some variance (±10%)
            num_transactions = random.randint(
                int(args.regular_size * 0.9), 
                int(args.regular_size * 1.1)
            )
            for _ in range(num_transactions):
                value = random.randint(100, 500)
                f.write(f"customer_{customer_id},{value}\n")
            total_rows += num_transactions
        
        # Hot customer (ID 999)
        for _ in range(args.hot_size):
            value = random.randint(100, 500)
            f.write(f"customer_999,{value}\n")
        total_rows += args.hot_size
    
    skew_ratio = args.hot_size / args.regular_size if args.regular_size > 0 else float('inf')
    print(f"Generated {total_rows} rows with {skew_ratio:.1f}x skew")
    print(f"Data saved to {args.output}")