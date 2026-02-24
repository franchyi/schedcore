#!/usr/bin/env python3
"""
RocksDB Benchmark Suite for Scheduler Performance Evaluation
"""
import subprocess
import time
import json
import psutil
import os
import sys
import re
from datetime import datetime
import tempfile
import shutil

class RocksDBBenchmark:
    def __init__(self, rocksdb_dir="rocksdb", results_dir="results"):
        self.rocksdb_dir = rocksdb_dir
        self.results_dir = results_dir
        self.db_bench = os.path.join(rocksdb_dir, "db_bench")
        self.db_path = "/tmp/rocksdb_data"
        
        os.makedirs(results_dir, exist_ok=True)
        
    def cleanup_db(self):
        """Clean up database directory"""
        if os.path.exists(self.db_path):
            shutil.rmtree(self.db_path)
        os.makedirs(self.db_path, exist_ok=True)
    
    def run_db_bench(self, test_name, benchmark_args):
        """Run a specific db_bench test"""
        print(f"Running {test_name} benchmark...")
        
        # Clean database before each test
        self.cleanup_db()
        
        # Start monitoring
        start_time = time.time()
        start_cpu = psutil.cpu_percent(interval=1)
        start_mem = psutil.virtual_memory().percent
        
        # Base arguments for minimal logging
        base_args = [
            self.db_bench,
            f"--db={self.db_path}",
            "--disable_wal=true",
            "--statistics=false",
            "--histogram=false"
        ]
        
        # Run benchmark
        cmd = base_args + benchmark_args
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # End monitoring
        end_time = time.time()
        end_cpu = psutil.cpu_percent(interval=1)
        end_mem = psutil.virtual_memory().percent
        
        return {
            "test_name": test_name,
            "command": " ".join(cmd),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "duration": end_time - start_time,
            "cpu_usage": {
                "start": start_cpu,
                "end": end_cpu,
                "average": (start_cpu + end_cpu) / 2
            },
            "memory_usage": {
                "start": start_mem,
                "end": end_mem,
                "average": (start_mem + end_mem) / 2
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def parse_db_bench_output(self, output):
        """Parse db_bench output for performance metrics"""
        metrics = {}
        
        # Parse micros/op
        micros_pattern = r'(\w+)\s*:\s*([\d.]+)\s*micros/op\s*(\d+)\s*ops/sec'
        for match in re.finditer(micros_pattern, output):
            operation = match.group(1).lower()
            micros_per_op = float(match.group(2))
            ops_per_sec = int(match.group(3))
            
            metrics[f"{operation}_micros_per_op"] = micros_per_op
            metrics[f"{operation}_ops_per_sec"] = ops_per_sec
        
        # Parse overall throughput
        throughput_pattern = r'(\d+)\s+ops/sec'
        throughput_matches = re.findall(throughput_pattern, output)
        if throughput_matches:
            metrics['overall_ops_per_sec'] = int(throughput_matches[-1])
        
        # Parse database size
        size_pattern = r'DB size:\s*([\d.]+)\s*([KMGT]?B)'
        size_match = re.search(size_pattern, output)
        if size_match:
            size_value = float(size_match.group(1))
            size_unit = size_match.group(2)
            
            # Convert to bytes
            multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
            if size_unit in multipliers:
                metrics['db_size_bytes'] = int(size_value * multipliers[size_unit])
        
        # Parse write amplification
        wa_pattern = r'Write amplification:\s*([\d.]+)'
        wa_match = re.search(wa_pattern, output)
        if wa_match:
            metrics['write_amplification'] = float(wa_match.group(1))
        
        # Parse read amplification  
        ra_pattern = r'Read amplification:\s*([\d.]+)'
        ra_match = re.search(ra_pattern, output)
        if ra_match:
            metrics['read_amplification'] = float(ra_match.group(1))
        
        return metrics
    
    def run_comprehensive_benchmark(self):
        """Run comprehensive RocksDB benchmarks"""
        benchmarks = [
            {
                "name": "sequential_write",
                "args": [
                    "--benchmarks=fillseq",
                    "--num=1000000",
                    "--value_size=100"
                ]
            },
            {
                "name": "random_write", 
                "args": [
                    "--benchmarks=fillrandom",
                    "--num=500000",
                    "--value_size=100"
                ]
            },
            {
                "name": "sequential_read",
                "args": [
                    "--benchmarks=fillseq,readseq",
                    "--num=500000",
                    "--value_size=100",
                    "--use_existing_db=true"
                ]
            },
            {
                "name": "random_read",
                "args": [
                    "--benchmarks=fillrandom,readrandom", 
                    "--num=500000",
                    "--reads=1000000",
                    "--value_size=100"
                ]
            },
            {
                "name": "mixed_workload",
                "args": [
                    "--benchmarks=fillrandom,readwhilewriting",
                    "--num=300000",
                    "--reads=500000",
                    "--value_size=100",
                    "--threads=4"
                ]
            },
            {
                "name": "compression_test",
                "args": [
                    "--benchmarks=fillrandom,stats",
                    "--num=200000",
                    "--value_size=1000",
                    "--compression_type=lz4"
                ]
            },
            {
                "name": "bulk_load",
                "args": [
                    "--benchmarks=bulkload",
                    "--num=1000000",
                    "--value_size=100",
                    "--batch_size=1000"
                ]
            },
            {
                "name": "range_scan",
                "args": [
                    "--benchmarks=fillrandom,seekrandom",
                    "--num=200000", 
                    "--seeks=100000",
                    "--value_size=100"
                ]
            }
        ]
        
        results = []
        
        for benchmark in benchmarks:
            result = self.run_db_bench(benchmark["name"], benchmark["args"])
            
            # Parse metrics from output
            if result["return_code"] == 0:
                metrics = self.parse_db_bench_output(result["stdout"])
                result["metrics"] = metrics
                result["config"] = {
                    "args": benchmark["args"]
                }
            
            results.append(result)
            time.sleep(1)  # Brief pause between tests
        
        return results
    
    def save_results(self, results):
        """Save benchmark results to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rocksdb_benchmark_{timestamp}.json"
        filepath = os.path.join(self.results_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"Results saved to {filepath}")
        return filepath
    
    def generate_summary(self, results):
        """Generate benchmark summary"""
        summary = {
            "total_tests": len(results),
            "successful_tests": sum(1 for r in results if r["return_code"] == 0),
            "failed_tests": sum(1 for r in results if r["return_code"] != 0),
            "total_duration": sum(r["duration"] for r in results),
            "average_cpu_usage": sum(r["cpu_usage"]["average"] for r in results) / len(results),
            "average_memory_usage": sum(r["memory_usage"]["average"] for r in results) / len(results),
            "test_summary": []
        }
        
        for result in results:
            test_summary = {
                "test_name": result["test_name"],
                "status": "success" if result["return_code"] == 0 else "failed",
                "duration": result["duration"],
                "metrics": result.get("metrics", {}),
                "config": result.get("config", {})
            }
            summary["test_summary"].append(test_summary)
        
        return summary

def main():
    benchmark = RocksDBBenchmark()
    
    print("Starting RocksDB benchmark suite...")
    print("=" * 50)
    
    results = benchmark.run_comprehensive_benchmark()
    
    if results:
        # Save detailed results
        results_file = benchmark.save_results(results)
        
        # Generate and display summary
        summary = benchmark.generate_summary(results)
        
        print("\n" + "=" * 50)
        print("BENCHMARK SUMMARY")
        print("=" * 50)
        print(f"Total tests: {summary['total_tests']}")
        print(f"Successful: {summary['successful_tests']}")
        print(f"Failed: {summary['failed_tests']}")
        print(f"Total duration: {summary['total_duration']:.2f} seconds")
        print(f"Average CPU usage: {summary['average_cpu_usage']:.2f}%")
        print(f"Average memory usage: {summary['average_memory_usage']:.2f}%")
        
        print("\nTest Results:")
        for test in summary['test_summary']:
            status_symbol = "✓" if test['status'] == 'success' else "✗"
            print(f"  {status_symbol} {test['test_name']}: {test['duration']:.2f}s")
            
            # Find any ops_per_sec metrics
            for key, value in test['metrics'].items():
                if 'ops_per_sec' in key and not key.startswith('overall'):
                    print(f"    {key}: {value:,.0f}")
            
            if 'overall_ops_per_sec' in test['metrics']:
                print(f"    Overall OPS: {test['metrics']['overall_ops_per_sec']:,.0f}")
            
            if 'write_amplification' in test['metrics']:
                print(f"    Write Amp: {test['metrics']['write_amplification']:.2f}")
    
    else:
        print("Failed to run benchmarks")
        sys.exit(1)

if __name__ == "__main__":
    main()