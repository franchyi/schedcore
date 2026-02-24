#!/usr/bin/env python3
"""
Flink-like join simulation without Flink dependency
Simulates retail analytics with popular items creating join skew
"""

import pandas as pd
import time
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Flink-like join test')
    parser.add_argument('data_file', type=str, help='Path to CSV data file')
    
    args = parser.parse_args()
    
    print(f"Processing join on {args.data_file}...")
    start_time = time.time()
    
    # Load transaction data
    df = pd.read_csv(args.data_file, names=['product_id', 'price', 'timestamp'])
    print(f"Loaded {len(df)} transactions")
    
    # Simulate product dimension table
    unique_products = df['product_id'].unique()
    product_dim = pd.DataFrame({
        'product_id': unique_products,
        'category': ['electronics' if 'product_999' in str(p) else 'general' for p in unique_products],
        'discount': [0.1 if 'product_999' in str(p) else 0.05 for p in unique_products]
    })
    
    # Perform join operation
    result = df.merge(product_dim, on='product_id', how='inner')
    
    # Calculate aggregations after join
    # 1. Total sales by product
    product_sales = result.groupby('product_id').agg({
        'price': ['sum', 'mean', 'count'],
        'discount': 'first',
        'category': 'first'
    })
    
    # 2. Sales by category
    category_sales = result.groupby('category')['price'].sum()
    
    # 3. Hourly sales (convert timestamp to hour)
    result['hour'] = pd.to_datetime(result['timestamp'], unit='s', errors='coerce').dt.hour
    hourly_sales = result.groupby('hour')['price'].sum()
    
    # 4. Apply discounts and calculate final revenue
    result['discounted_price'] = result['price'] * (1 - result['discount'])
    total_revenue = result['discounted_price'].sum()
    
    end_time = time.time()
    
    print(f"Join complete in {end_time - start_time:.2f}s")
    print(f"Total transactions joined: {len(result)}")
    print(f"Total products: {len(unique_products)}")
    print(f"Total revenue (after discounts): ${total_revenue:.2f}")
    print(f"Sales by category: {dict(category_sales)}")
    
    # Show top products
    top_products = product_sales.sort_values(('price', 'sum'), ascending=False).head()
    print(f"Top 5 products by revenue:")
    print(top_products[('price', 'sum')])