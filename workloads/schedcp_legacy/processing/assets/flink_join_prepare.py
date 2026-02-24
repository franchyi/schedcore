#!/usr/bin/env python3
"""
Prepare data for flink_join_test.py
Creates CSV files with retail transaction data showing popular product skew
"""

import argparse
import random
import time

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare data for Flink join test')
    parser.add_argument('--regular-transactions', type=int, default=1000,
                        help='Number of transactions per regular product (default: 1000)')
    parser.add_argument('--hot-transactions', type=int, default=100000,
                        help='Number of transactions for popular product (default: 100000)')
    parser.add_argument('--num-products', type=int, default=99,
                        help='Number of regular products (default: 99)')
    parser.add_argument('--time-window', type=int, default=86400,
                        help='Time window in seconds for transactions (default: 86400 = 24h)')
    parser.add_argument('--hot-window', type=int, default=7200,
                        help='Time window in seconds for hot product (default: 7200 = 2h)')
    parser.add_argument('--output', type=str, default='flink_transactions.csv',
                        help='Output CSV file')
    
    args = parser.parse_args()
    
    print(f"Generating transaction data for Flink join test...")
    print(f"  Regular products: {args.num_products} with ~{args.regular_transactions} transactions each")
    print(f"  Hot product: 1 with {args.hot_transactions} transactions")
    
    base_timestamp = int(time.time())
    total_transactions = 0
    
    with open(args.output, 'w') as f:
        # Regular products
        for product_id in range(args.num_products):
            # Add some variance (±10%)
            num_transactions = random.randint(
                int(args.regular_transactions * 0.9),
                int(args.regular_transactions * 1.1)
            )
            for _ in range(num_transactions):
                price = random.randint(10, 50)
                # Spread transactions over time window
                timestamp = base_timestamp - random.randint(0, args.time_window)
                f.write(f"product_{product_id},{price},{timestamp}\n")
            total_transactions += num_transactions
        
        # Popular product (ID 999) - e.g., trending item or flash sale
        for _ in range(args.hot_transactions):
            price = random.randint(40, 80)  # Premium/trending product
            # Concentrated in shorter time window (viral effect)
            timestamp = base_timestamp - random.randint(0, args.hot_window)
            f.write(f"product_999,{price},{timestamp}\n")
        total_transactions += args.hot_transactions
    
    skew_ratio = args.hot_transactions / args.regular_transactions if args.regular_transactions > 0 else float('inf')
    print(f"Generated {total_transactions} transactions with {skew_ratio:.1f}x skew")
    print(f"Transaction data saved to {args.output}")