#!/usr/bin/env python3
"""
Pandas ETL simulation without heavy dependencies
Simulates log processing with DDoS spike creating large file
"""

import pandas as pd
import gzip
import time
import argparse
import re
from collections import Counter

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pandas ETL test')
    parser.add_argument('log_file', type=str, help='Log file to process')
    
    args = parser.parse_args()
    
    print(f"Processing ETL on {args.log_file}...")
    start_time = time.time()
    
    # Read and parse the gzipped log file
    with gzip.open(args.log_file, 'rt') as f:
        lines = f.readlines()
    
    print(f"Loaded {len(lines)} log lines")
    
    # Parse all lines into structured data
    data = []
    ip_pattern = re.compile(r'\d+\.\d+\.\d+\.\d+')
    
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 4:
            # Extract IP addresses
            ips = ip_pattern.findall(line)
            data.append({
                'timestamp': parts[0] + ' ' + parts[1],
                'level': parts[2],
                'ip': ips[0] if ips else 'unknown',
                'message': ' '.join(parts[3:])
            })
    
    # Create DataFrame for analysis
    df = pd.DataFrame(data)
    
    # Perform ETL transformations
    # 1. Count by log level
    level_counts = df['level'].value_counts()
    
    # 2. Count by IP address
    ip_counts = df['ip'].value_counts()
    
    # 3. Extract hour from timestamp and count
    df['hour'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.hour
    hourly_counts = df['hour'].value_counts().sort_index()
    
    # 4. Find error patterns
    error_df = df[df['level'] == '[ERROR]']
    error_patterns = Counter()
    for msg in error_df['message']:
        # Simple pattern extraction
        words = msg.split()
        if len(words) >= 2:
            pattern = f"{words[0]} {words[1]}"
            error_patterns[pattern] += 1
    
    end_time = time.time()
    
    print(f"ETL complete in {end_time - start_time:.2f}s")
    print(f"Total records processed: {len(df)}")
    print(f"Log levels: {dict(level_counts)}")
    print(f"Top 5 IPs: {dict(ip_counts.head())}")
    print(f"Hourly distribution: {dict(hourly_counts.head())}")
    if error_patterns:
        print(f"Top error patterns: {dict(error_patterns.most_common(5))}")