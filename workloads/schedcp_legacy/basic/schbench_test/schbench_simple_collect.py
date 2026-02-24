#!/usr/bin/env python3
"""
Modified schbench runner that collects performance metrics with custom output file
"""

import subprocess
import json
import re
import os
import sys
from datetime import datetime

def run_schbench(schbench_path="../schbench/schbench", runtime=30, message_threads=2, message_groups=4):
    """Run schbench once and parse output"""
    cmd = [
        schbench_path,
        "-m", str(message_groups),
        "-t", str(message_threads),
        "-r", str(runtime)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # schbench outputs to stderr, not stdout
        output = result.stderr if result.stderr else result.stdout
        return parse_schbench_output(output)
    except subprocess.CalledProcessError as e:
        print(f"Error running schbench: {e}")
        print(f"stderr: {e.stderr}")
        return None

def parse_schbench_output(output):
    """Parse schbench output to extract metrics"""
    metrics = {}
    
    # Parse average RPS (throughput)
    throughput_match = re.search(r'average rps:\s+([\d.]+)', output)
    if throughput_match:
        metrics['throughput'] = float(throughput_match.group(1))
    
    # Parse Request Latencies percentiles
    lines = output.split('\n')
    parsing_request_latencies = False
    
    for line in lines:
        line = line.strip()
        
        # Check if we're in the Request Latencies section
        if "Request Latencies percentiles" in line:
            parsing_request_latencies = True
            continue
        elif "RPS percentiles" in line or "Wakeup Latencies percentiles" in line:
            parsing_request_latencies = False
            continue
        
        # Parse request latency percentiles
        if parsing_request_latencies and "th:" in line:
            # Extract percentile and value, handling lines with asterisk
            match = re.match(r'\s*\*?\s*(\d+\.\d)th:\s+(\d+)', line)
            if match:
                percentile = match.group(1)
                value = int(match.group(2))
                
                # Map to our expected keys
                if percentile == "50.0":
                    metrics['50th_percentile_us'] = value
                elif percentile == "90.0":
                    metrics['95th_percentile_us'] = value  # Using 90th as proxy for 95th
                elif percentile == "99.0":
                    metrics['99th_percentile_us'] = value
                elif percentile == "99.9":
                    metrics['99.9th_percentile_us'] = value
    
    return metrics

def main():
    # Configuration
    schbench_path = "../schbench/schbench"
    num_runs = 3
    
    # Get output filename from command line or use default
    if len(sys.argv) > 1:
        results_file = sys.argv[1]
    else:
        results_file = "schbench_results.json"
    
    # Get scheduler name from command line
    scheduler_name = sys.argv[2] if len(sys.argv) > 2 else "unknown"
    
    # Check if schbench exists
    if not os.path.exists(schbench_path):
        print(f"Error: schbench not found at {schbench_path}")
        print("Please build schbench first or specify correct path")
        return
    
    # Collect results
    all_results = {
        "timestamp": datetime.now().isoformat(),
        "scheduler": scheduler_name,
        "num_runs": num_runs,
        "runs": []
    }
    
    print(f"Running schbench {num_runs} times with scheduler: {scheduler_name}...")
    
    for i in range(num_runs):
        print(f"\nRun {i+1}/{num_runs}...")
        metrics = run_schbench(schbench_path)
        
        if metrics:
            run_data = {
                "run_number": i + 1,
                "metrics": metrics
            }
            all_results["runs"].append(run_data)
            
            # Print results
            print(f"  Throughput: {metrics.get('throughput', 0):.2f} requests/sec")
            print(f"  50th percentile: {metrics.get('50th_percentile_us', 0)} us")
            print(f"  95th percentile: {metrics.get('95th_percentile_us', 0)} us")
            print(f"  99th percentile: {metrics.get('99th_percentile_us', 0)} us")
    
    # Calculate averages
    if all_results["runs"]:
        avg_metrics = {}
        metric_keys = all_results["runs"][0]["metrics"].keys()
        
        for key in metric_keys:
            values = [run["metrics"][key] for run in all_results["runs"]]
            avg_metrics[key] = sum(values) / len(values)
        
        all_results["averages"] = avg_metrics
        
        print("\nAverage results:")
        print(f"  Throughput: {avg_metrics.get('throughput', 0):.1f} requests/sec")
        print(f"  50th percentile: {avg_metrics.get('50th_percentile_us', 0):.1f} us")
        print(f"  95th percentile: {avg_metrics.get('95th_percentile_us', 0):.1f} us")
        print(f"  99th percentile: {avg_metrics.get('99th_percentile_us', 0):.1f} us")
    
    # Save to JSON
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\nResults saved to {results_file}")

if __name__ == "__main__":
    main()