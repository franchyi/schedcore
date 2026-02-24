#!/usr/bin/env python3
"""
Prepare data for spark_skew_test.py
Creates CSV files with key-value pairs showing partition skew
"""

import argparse
import random

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare data for Spark shuffle test')
    parser.add_argument('--regular-keys', type=int, default=1000,
                        help='Number of values per regular key (default: 1000)')
    parser.add_argument('--hot-keys', type=int, default=1000000,
                        help='Number of values for hot key (default: 1000000)')
    parser.add_argument('--num-partitions', type=int, default=99,
                        help='Number of regular partitions/keys (default: 99)')
    parser.add_argument('--output', type=str, default='spark_data.csv',
                        help='Output CSV file')
    
    args = parser.parse_args()
    
    print(f"Generating data for Spark shuffle test...")
    print(f"  Regular keys: {args.num_partitions} with ~{args.regular_keys} values each")
    print(f"  Hot key: 1 with {args.hot_keys} values")
    
    total_rows = 0
    with open(args.output, 'w') as f:
        # Regular keys/partitions
        for key_id in range(args.num_partitions):
            # Add some variance (±10%)
            num_values = random.randint(
                int(args.regular_keys * 0.9),
                int(args.regular_keys * 1.1)
            )
            for i in range(num_values):
                value = random.randint(1, 1000)
                f.write(f"{key_id},{value}\n")
            total_rows += num_values
        
        # Hot key (ID 999) - simulating data skew in shuffle
        for i in range(args.hot_keys):
            value = random.randint(1, 1000)
            f.write(f"999,{value}\n")
        total_rows += args.hot_keys
    
    skew_ratio = args.hot_keys / args.regular_keys if args.regular_keys > 0 else float('inf')
    print(f"Generated {total_rows} key-value pairs with {skew_ratio:.1f}x skew")
    print(f"Data saved to {args.output}")