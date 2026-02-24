#!/usr/bin/env python3
"""
Prepare data for pandas_etl_test.py
Creates gzipped log files with DDoS spike pattern
"""

import argparse
import gzip
import random
from datetime import datetime, timedelta

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare data for Pandas ETL test')
    parser.add_argument('--normal-logs', type=int, default=10000,
                        help='Number of normal log entries (default: 10000)')
    parser.add_argument('--error-logs', type=int, default=100000,
                        help='Number of error log entries for DDoS spike (default: 100000)')
    parser.add_argument('--num-servers', type=int, default=39,
                        help='Number of normal servers (default: 39)')
    parser.add_argument('--time-window', type=int, default=86400,
                        help='Time window in seconds for normal logs (default: 86400 = 24h)')
    parser.add_argument('--spike-window', type=int, default=300,
                        help='Time window in seconds for DDoS spike (default: 300 = 5min)')
    parser.add_argument('--output', type=str, default='etl_logs.gz',
                        help='Output gzipped log file')
    
    args = parser.parse_args()
    
    print(f"Generating log file for Pandas ETL test...")
    print(f"  Normal logs: {args.normal_logs} over {args.time_window}s")
    print(f"  Error logs (DDoS): {args.error_logs} over {args.spike_window}s")
    
    base_time = datetime.now()
    
    with gzip.open(args.output, 'wt') as f:
        # Normal logs distributed across multiple servers
        for i in range(args.normal_logs):
            timestamp = (base_time - timedelta(seconds=random.randint(0, args.time_window))).strftime('%Y-%m-%d %H:%M:%S')
            ip = f"192.168.{random.randint(1, 10)}.{random.randint(1, 254)}"
            server = f"server{random.randint(1, args.num_servers)}"
            latency = random.randint(10, 100)
            f.write(f"{timestamp} [INFO] {server} Request from {ip} processed in {latency} ms\n")
        
        # DDoS spike - error logs from specific server (server40)
        for i in range(args.error_logs):
            timestamp = (base_time - timedelta(seconds=random.randint(0, args.spike_window))).strftime('%Y-%m-%d %H:%M:%S')
            ip = f"10.0.0.{random.randint(1, 50)}"  # Suspicious IP range
            f.write(f"{timestamp} [ERROR] server40 DDoS attack detected from {ip} - connection refused\n")
    
    total_logs = args.normal_logs + args.error_logs
    spike_ratio = args.error_logs / args.normal_logs if args.normal_logs > 0 else float('inf')
    print(f"Generated {total_logs} log entries with {spike_ratio:.1f}x spike")
    print(f"Log data saved to {args.output}")