#!/usr/bin/env python3
"""
Redis Benchmark Suite for Scheduler Performance Evaluation
"""
import subprocess
import time
import json
import os
import sys
import csv
import io
from datetime import datetime
import signal
import atexit
import traceback
from pathlib import Path

# Import utility functions
from utils import (
    RedisCleanup,
    RedisConfig,
    BenchmarkParser,
    ProcessManager,
    BenchmarkSummary
)

class RedisBenchmark:
    def __init__(self, redis_dir="redis-src", results_dir="results", config_options=None):
        print(f"[INFO] Initializing RedisBenchmark with redis_dir={redis_dir}, results_dir={results_dir}")
        
        self.redis_dir = redis_dir
        self.results_dir = results_dir
        self.redis_cli = os.path.join(redis_dir, "src", "redis-cli")
        self.redis_benchmark = os.path.join(redis_dir, "src", "redis-benchmark")
        self.redis_server = os.path.join(redis_dir, "src", "redis-server")
        self.redis_process = None
        self.config_file = None
        self.config_options = config_options or {}
        
        print(f"[INFO] Redis configuration options: {self.config_options}")
        
        # Check if binaries exist
        binaries = [self.redis_server, self.redis_cli, self.redis_benchmark]
        missing_binaries = []
        
        for binary in binaries:
            if not os.path.exists(binary):
                missing_binaries.append(binary)
                print(f"[ERROR] Missing Redis binary: {binary}")
        
        if missing_binaries:
            error_msg = f"Redis binaries not found in {redis_dir}/src/: {missing_binaries}"
            print(f"[ERROR] {error_msg}")
            print("[ERROR] Please run 'make build' first to compile Redis")
            print(f"Error: Redis binaries not found in {redis_dir}/src/")
            print("Please run 'make build' first to compile Redis")
            sys.exit(1)
        
        print("[INFO] All Redis binaries found successfully")
        
        # Validate and create results directory
        try:
            os.makedirs(results_dir, exist_ok=True)
            print(f"[INFO] Results directory ensured: {results_dir}")
        except Exception as e:
            print(f"[ERROR] Failed to create results directory {results_dir}: {e}")
            raise
        
        # Register cleanup on exit
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        print("[INFO] Signal handlers and cleanup registered")
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals gracefully"""
        print(f"[INFO] Signal {signum} received, initiating cleanup")
        print("\nInterrupt received, cleaning up...")
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self):
        """Ensure Redis is stopped on exit and clean up all temporary files"""
        print("[INFO] Starting cleanup process")
        
        if hasattr(self, 'redis_process') and self.redis_process:
            print("[INFO] Stopping Redis process during cleanup")
            self.stop_redis()
        
        # Clean up temporary config file
        if self.config_file and os.path.exists(self.config_file):
            try:
                os.remove(self.config_file)
                print(f"[INFO] Removed temporary config file: {self.config_file}")
            except Exception as e:
                print(f"[WARNING] Failed to remove config file {self.config_file}: {e}")
        
        # Use utility function for comprehensive cleanup
        RedisCleanup.cleanup_redis_files()
        
        print("[INFO] Cleanup completed")
        
    def generate_config(self):
        """Generate Redis configuration file"""
        print("[INFO] Generating Redis configuration file")
        
        # Use utility function to generate config
        self.config_file = RedisConfig.generate_config_file(self.config_options)
        return self.config_file
    
    def start_redis(self):
        """Start Redis server"""
        print("[INFO] Attempting to start Redis server")
        
        # First ensure no Redis is running
        self.stop_redis()
        time.sleep(1)
        
        print("Starting Redis server...")
        print("[INFO] Starting Redis server...")
        
        # Generate configuration file
        try:
            config_path = self.generate_config()
            print(f"[INFO] Generated Redis config file: {config_path}")
        except Exception as e:
            print(f"[ERROR] Failed to generate Redis configuration: {e}")
            return False
        
        # Print configuration being used
        print(f"Redis configuration:")
        if self.config_options:
            for key, value in self.config_options.items():
                print(f"  {key}: {value}")
                print(f"[INFO] Config option: {key} = {value}")
        else:
            print("  Using default Redis configuration")
            print("[INFO] Using default Redis configuration")
        print(f"  Config file: {config_path}")
        
        cmd = [self.redis_server, config_path]
        print(f"[INFO] Starting Redis with command: {' '.join(cmd)}")
        
        try:
            self.redis_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            print(f"[INFO] Redis process started with PID: {self.redis_process.pid}")
        except Exception as e:
            print(f"[ERROR] Failed to start Redis process: {e}")
            return False
        
        # Wait for Redis to start with retries
        max_retries = 10
        print(f"[INFO] Waiting for Redis to start (max {max_retries} retries)")
        
        for i in range(max_retries):
            time.sleep(0.5)
            if ProcessManager.check_redis_running(self.redis_cli):
                print(f"[INFO] Redis server started successfully after {i+1} attempts")
                print("Redis server started successfully")
                return True
            else:
                print(f"[DEBUG] Redis ping attempt {i+1} failed")
                if i == max_retries - 1:
                    print("[ERROR] Failed to start Redis server after multiple attempts")
                    print("Failed to start Redis server after multiple attempts")
                    if self.redis_process:
                        # Check if process is still running
                        if self.redis_process.poll() is None:
                            print("[INFO] Redis process is still running, but not responding to ping")
                            try:
                                # Try to get any available output without killing the process
                                stdout, stderr = self.redis_process.communicate(timeout=2)
                                stdout_str = stdout.decode() if stdout else 'No stdout'
                                stderr_str = stderr.decode() if stderr else 'No stderr'
                                print(f"[ERROR] Redis stdout: {stdout_str}")
                                print(f"[ERROR] Redis stderr: {stderr_str}")
                                print(f"Redis stdout: {stdout_str}")
                                print(f"Redis stderr: {stderr_str}")
                            except subprocess.TimeoutExpired:
                                print("[ERROR] Redis process not responding, forcing termination")
                                try:
                                    self.redis_process.kill()
                                    stdout, stderr = self.redis_process.communicate(timeout=1)
                                    stdout_str = stdout.decode() if stdout else 'No stdout'
                                    stderr_str = stderr.decode() if stderr else 'No stderr'
                                    print(f"[ERROR] Redis stdout (after kill): {stdout_str}")
                                    print(f"[ERROR] Redis stderr (after kill): {stderr_str}")
                                except:
                                    print("[ERROR] Could not get Redis process output")
                        else:
                            print(f"[ERROR] Redis process exited with code: {self.redis_process.returncode}")
                            try:
                                stdout, stderr = self.redis_process.communicate(timeout=1)
                                stdout_str = stdout.decode() if stdout else 'No stdout'
                                stderr_str = stderr.decode() if stderr else 'No stderr'
                                print(f"[ERROR] Redis stdout: {stdout_str}")
                                print(f"[ERROR] Redis stderr: {stderr_str}")
                                print(f"Redis stdout: {stdout_str}")
                                print(f"Redis stderr: {stderr_str}")
                            except:
                                print("[ERROR] Could not get Redis process output")
                    
                    # Also check if Redis config file exists and show its content
                    if hasattr(self, 'config_file') and self.config_file and os.path.exists(self.config_file):
                        print(f"[INFO] Redis config file content ({self.config_file}):")
                        try:
                            with open(self.config_file, 'r') as f:
                                print(f.read())
                        except Exception as e:
                            print(f"[ERROR] Could not read config file: {e}")
                    
                    return False
                continue
        return False
    
    def stop_redis(self):
        """Stop Redis server"""
        print("[INFO] Stopping Redis server")
        
        # Try graceful shutdown first
        ProcessManager.stop_redis_gracefully(self.redis_cli)
        time.sleep(0.5)
        
        # Kill the process if it's still running
        if hasattr(self, 'redis_process') and self.redis_process:
            try:
                print(f"[INFO] Terminating Redis process (PID: {self.redis_process.pid})")
                self.redis_process.terminate()
                self.redis_process.wait(timeout=2)
                print("[INFO] Redis process terminated successfully")
            except subprocess.TimeoutExpired:
                print("[WARNING] Redis process termination timed out, forcing kill")
                try:
                    self.redis_process.kill()
                    self.redis_process.wait(timeout=1)
                    print("[INFO] Redis process killed successfully")
                except Exception as e:
                    print(f"[ERROR] Failed to kill Redis process: {e}")
            except Exception as e:
                print(f"[ERROR] Error terminating Redis process: {e}")
            self.redis_process = None
        
        # Final cleanup - kill any remaining redis-server processes
        RedisCleanup.kill_redis_processes()
    
    def parse_csv_output(self, csv_output):
        """Parse CSV output into structured JSON"""
        return BenchmarkParser.parse_csv_output(csv_output)
    
    def run_benchmark(self, test_name, command_args):
        """Run a specific benchmark test"""
        print(f"[INFO] Starting benchmark test: {test_name}")
        print(f"[INFO] Benchmark command: {self.redis_benchmark} {' '.join(command_args)}")
        
        print(f"Running {test_name} benchmark...")
        print(f"Benchmark command: {self.redis_benchmark} {' '.join(command_args)}")
        
        start_time = time.time()
        
        # Run benchmark
        cmd = [self.redis_benchmark] + command_args
        try:
            print(f"[INFO] Executing benchmark command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            end_time = time.time()
            duration = end_time - start_time
            
            print(f"[INFO] Benchmark {test_name} completed in {duration:.2f}s with return code {result.returncode}")
            
            if result.returncode != 0:
                print(f"[ERROR] Benchmark {test_name} failed with return code {result.returncode}")
                print(f"[ERROR] Stderr: {result.stderr}")
            else:
                print(f"[INFO] Benchmark {test_name} completed successfully")
                
        except subprocess.TimeoutExpired:
            end_time = time.time()
            duration = end_time - start_time
            print(f"[ERROR] Benchmark {test_name} timed out after {duration:.2f}s")
            result = subprocess.CompletedProcess(cmd, -1, "Benchmark timed out", "Timeout")
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            print(f"[ERROR] Benchmark {test_name} failed with exception after {duration:.2f}s: {e}")
            result = subprocess.CompletedProcess(cmd, -1, f"Exception: {str(e)}", str(e))
        
        if result.stdout:
            print(f"Benchmark result: {result.stdout}")
            print(f"[DEBUG] Benchmark stdout ({len(result.stdout)} chars): {result.stdout[:500]}..." if len(result.stdout) > 500 else f"Benchmark stdout: {result.stdout}")
        else:
            print(f"[WARNING] Benchmark {test_name} produced no stdout")
        
        if result.stderr:
            print(f"[WARNING] Benchmark stderr: {result.stderr}")
        
        # Parse CSV output if present
        parsed_metrics = None
        if "--csv" in command_args and result.stdout:
            try:
                parsed_metrics = self.parse_csv_output(result.stdout)
                if parsed_metrics:
                    print(f"[INFO] Successfully parsed {len(parsed_metrics)} CSV metrics")
                else:
                    print("[WARNING] CSV parsing returned no metrics")
            except Exception as e:
                print(f"[ERROR] Failed to parse CSV output: {e}")
        
        # Parse results
        result_dict = {
            "test_name": test_name,
            "command": " ".join(cmd),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "duration": end_time - start_time,
            "parsed_metrics": parsed_metrics,
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"[INFO] Benchmark {test_name} result: duration={result_dict['duration']:.2f}s, return_code={result_dict['return_code']}, parsed_metrics={len(parsed_metrics) if parsed_metrics else 0}")
        
        return result_dict
    
    def parse_benchmark_output(self, output):
        """Parse Redis benchmark output for metrics"""
        return BenchmarkParser.parse_benchmark_output(output)
    
    
    def run_comprehensive_benchmark(self, clients=50, requests=100000, data_size=3, pipeline=1, 
                                   keyspace=None, tests=None, threads=None, cluster=False, 
                                   precision=0, seed=None):
        """Run comprehensive Redis benchmarks"""
        print(f"[INFO] Starting comprehensive benchmark: clients={clients}, requests={requests}, data_size={data_size}, pipeline={pipeline}")
        print(f"[INFO] Additional params: keyspace={keyspace}, tests={tests}, threads={threads}, cluster={cluster}")
        
        if not self.start_redis():
            print("[ERROR] Failed to start Redis for comprehensive benchmark")
            return None
        
        # Build base arguments
        base_args = ["-c", str(clients), "-P", str(pipeline), "--csv"]
        
        if data_size != 3:
            base_args.extend(["-d", str(data_size)])
        if keyspace:
            base_args.extend(["-r", str(keyspace)])
        if threads:
            base_args.extend(["--threads", str(threads)])
        if cluster:
            base_args.append("--cluster")
        if precision != 0:
            base_args.extend(["--precision", str(precision)])
        if seed:
            base_args.extend(["--seed", str(seed)])
        
        # Define test configurations
        if tests:
            # Use specific tests provided
            test_list = [t.strip() for t in tests.split(',')]
            benchmarks = []
            for test in test_list:
                benchmarks.append({
                    "name": f"{test.upper()}_operations",
                    "args": ["-t", test] + base_args + ["-n", str(requests)]
                })
        else:
            # Use default comprehensive test suite
            benchmarks = [
                {
                    "name": "SET_operations",
                    "args": ["-t", "set"] + base_args + ["-n", str(requests)]
                },
                {
                    "name": "GET_operations", 
                    "args": ["-t", "get"] + base_args + ["-n", str(requests)]
                },
                {
                    "name": "INCR_operations",
                    "args": ["-t", "incr"] + base_args + ["-n", str(requests)]
                },
                {
                    "name": "LPUSH_operations",
                    "args": ["-t", "lpush"] + base_args + ["-n", str(requests)]
                },
                {
                    "name": "LPOP_operations",
                    "args": ["-t", "lpop"] + base_args + ["-n", str(requests)]
                },
                {
                    "name": "SADD_operations",
                    "args": ["-t", "sadd"] + base_args + ["-n", str(requests)]
                },
                {
                    "name": "HSET_operations",
                    "args": ["-t", "hset"] + base_args + ["-n", str(requests)]
                },
                {
                    "name": "LRANGE_100_operations",
                    "args": ["-t", "lrange_100"] + base_args + ["-n", str(requests / 20)]
                },
                {
                    "name": "LRANGE_300_operations",
                    "args": ["-t", "lrange_300"] + base_args + ["-n", str(requests / 20)]
                },
                {
                    "name": "LRANGE_500_operations",
                    "args": ["-t", "lrange_500"] + base_args + ["-n", str(requests / 50)]
                },
                {
                    "name": "LRANGE_600_operations",
                    "args": ["-t", "lrange_600"] + base_args + ["-n", str(requests / 50)]
                },
                {
                    "name": "MSET_operations",
                    "args": ["-t", "mset"] + base_args + ["-n", str(requests)]
                }
            ]
        
        results = []
        print(f"[INFO] Prepared {len(benchmarks)} benchmark tests")
        
        try:
            for i, benchmark in enumerate(benchmarks, 1):
                print(f"[INFO] Running benchmark {i}/{len(benchmarks)}: {benchmark['name']}")
                
                try:
                    result = self.run_benchmark(benchmark["name"], benchmark["args"])
                    
                    # Parse metrics from output
                    if result["return_code"] == 0:
                        try:
                            metrics = self.parse_benchmark_output(result["stdout"])
                            result["metrics"] = metrics
                            print(f"[INFO] Successfully parsed metrics for {benchmark['name']}")
                        except Exception as e:
                            print(f"[ERROR] Failed to parse metrics for {benchmark['name']}: {e}")
                            result["metrics"] = {}
                    else:
                        print(f"[WARNING] Benchmark {benchmark['name']} failed with return code {result['return_code']}")
                        result["metrics"] = {}
                    
                    results.append(result)
                    print(f"[INFO] Completed benchmark {i}/{len(benchmarks)}: {benchmark['name']}")
                    
                except Exception as e:
                    print(f"[ERROR] Exception during benchmark {benchmark['name']}: {e}")
                    error_result = {
                        "test_name": benchmark["name"],
                        "command": " ".join([self.redis_benchmark] + benchmark["args"]),
                        "stdout": "",
                        "stderr": str(e),
                        "return_code": -1,
                        "duration": 0,
                        "parsed_metrics": None,
                        "metrics": {},
                        "timestamp": datetime.now().isoformat()
                    }
                    results.append(error_result)
                
                time.sleep(1)  # Brief pause between tests
                
        except Exception as e:
            print(f"[ERROR] Critical error during comprehensive benchmark: {e}")
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            print(f"Error during benchmark: {e}")
            return None
        finally:
            print("[INFO] Stopping Redis after comprehensive benchmark")
            self.stop_redis()
        
        print(f"[INFO] Comprehensive benchmark completed with {len(results)} results")
        successful_tests = sum(1 for r in results if r.get('return_code') == 0)
        print(f"[INFO] Successful tests: {successful_tests}/{len(results)}")
        
        return results
    
    def save_results(self, results):
        """Save benchmark results to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"redis_benchmark_{timestamp}.json"
        filepath = os.path.join(self.results_dir, filename)
        
        print(f"[INFO] Saving {len(results) if results else 0} results to {filepath}")
        
        try:
            # Ensure results directory exists
            os.makedirs(self.results_dir, exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(results, f, indent=2)
            
            print(f"[INFO] Results successfully saved to {filepath}")
            print(f"Results saved to {filepath}")
            return filepath
        except Exception as e:
            print(f"[ERROR] Failed to save results to {filepath}: {e}")
            print(f"Error saving results: {e}")
            return None
    
    def generate_summary(self, results):
        """Generate benchmark summary"""
        return BenchmarkSummary.generate_summary(results, self.config_options)

    def run_quick_benchmark(self, clients=50, requests=10000, data_size=3, pipeline=16, 
                           keyspace=None, tests="set,get", threads=None, cluster=False, 
                           precision=0, seed=None):
        """Run a quick benchmark test"""
        print(f"[INFO] Starting quick benchmark: clients={clients}, requests={requests}, tests={tests}")
        
        if not self.start_redis():
            print("[ERROR] Failed to start Redis for quick benchmark")
            return None
        
        try:
            print("\nRunning quick benchmark test...")
            print("-" * 40)
            print("[INFO] Building quick benchmark command")
            
            # Build command arguments
            cmd = [self.redis_benchmark, "-t", tests, "-n", str(requests), "-c", str(clients), "-P", str(pipeline), "--csv"]
            print(f"[INFO] Base command: {' '.join(cmd)}")
            
            if data_size != 3:
                cmd.extend(["-d", str(data_size)])
            if keyspace:
                cmd.extend(["-r", str(keyspace)])
            if threads:
                cmd.extend(["--threads", str(threads)])
            if cluster:
                cmd.append("--cluster")
            if precision != 0:
                cmd.extend(["--precision", str(precision)])
            if seed:
                cmd.extend(["--seed", str(seed)])
            
            print(f"[INFO] Executing quick benchmark: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print("[INFO] Quick benchmark completed successfully")
                print("Quick benchmark results:")
                print(result.stdout)
                
                # Parse CSV output
                try:
                    parsed_metrics = self.parse_csv_output(result.stdout)
                    print(f"[INFO] Parsed {len(parsed_metrics) if parsed_metrics else 0} CSV metrics")
                except Exception as e:
                    print(f"[ERROR] Failed to parse CSV output: {e}")
                    parsed_metrics = None
                
                try:
                    metrics = self.parse_benchmark_output(result.stdout)
                    print("[INFO] Successfully parsed benchmark output")
                except Exception as e:
                    print(f"[ERROR] Failed to parse benchmark output: {e}")
                    metrics = {}
                
                return {
                    "status": "success",
                    "output": result.stdout,
                    "metrics": metrics,
                    "parsed_metrics": parsed_metrics,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                print(f"[ERROR] Quick benchmark failed with return code {result.returncode}")
                print(f"[ERROR] Stderr: {result.stderr}")
                print(f"Benchmark failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print("[ERROR] Quick benchmark timed out after 30 seconds")
            print("Benchmark timed out")
            return None
        except Exception as e:
            print(f"[ERROR] Exception during quick benchmark: {e}")
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            print(f"Error during benchmark: {e}")
            return None
        finally:
            print("[INFO] Stopping Redis after quick benchmark")
            self.stop_redis()

def main():
    import argparse
    
    print("[INFO] Starting Redis Benchmark Suite main function")
    print(f"[INFO] Python version: {sys.version}")
    print(f"[INFO] Working directory: {os.getcwd()}")
    
    parser = argparse.ArgumentParser(description='Redis Benchmark Suite')
    parser.add_argument('--quick', action='store_true', help='Run quick benchmark only')
    parser.add_argument('--redis-dir', default='redis-src', help='Redis source directory')
    parser.add_argument('--results-dir', default='results', help='Results output directory')
    parser.add_argument('--io-threads', type=int, help='Number of I/O threads (1-128)', default=64)
    parser.add_argument('--io-threads-do-reads', choices=['yes', 'no'], help='Enable I/O threads for reads', default='yes')
    parser.add_argument('--maxmemory', help='Maximum memory usage (e.g., 1gb, 512mb)', default='256gb')
    parser.add_argument('--maxmemory-policy', choices=['noeviction', 'allkeys-lru', 'volatile-lru', 'allkeys-random', 'volatile-random', 'volatile-ttl'], help='Memory eviction policy')
    parser.add_argument('--hz', type=int, help='Background task frequency (1-500)', default=100)
    parser.add_argument('--explore-configs', action='store_true', help='Run benchmarks with different configurations')
    
    # Redis benchmark parameters
    parser.add_argument('-c', '--clients', type=int, help='Number of parallel connections', default=50)
    parser.add_argument('-n', '--requests', type=int, help='Total number of requests', default=1000000)
    parser.add_argument('-d', '--data-size', type=int, help='Data size of SET/GET value in bytes', default=4096)
    parser.add_argument('-P', '--pipeline', type=int, help='Pipeline requests', default=1)
    parser.add_argument('-r', '--keyspace', type=int, help='Use random keys in specified range')
    parser.add_argument('-t', '--tests', help='Specific tests to run (comma-separated: set,get,incr,lpush,lpop,sadd,hset)')
    parser.add_argument('--threads', type=int, help='Enable multi-thread mode')
    parser.add_argument('--cluster', action='store_true', help='Enable cluster mode')
    parser.add_argument('--precision', type=int, help='Decimal places in latency output', default=0)
    parser.add_argument('--seed', type=int, help='Random number generator seed')
    
    args = parser.parse_args()
    
    print(f"[INFO] Parsed arguments: {vars(args)}")
    
    # Build config options
    config_options = {}
    if args.io_threads:
        config_options['io_threads'] = args.io_threads
    if args.io_threads_do_reads:
        config_options['io_threads_do_reads'] = args.io_threads_do_reads
    if args.maxmemory:
        config_options['maxmemory'] = args.maxmemory
    if args.maxmemory_policy:
        config_options['maxmemory_policy'] = args.maxmemory_policy
    if args.hz:
        config_options['hz'] = args.hz
    
    # Build benchmark parameters
    benchmark_params = {
        'clients': args.clients,
        'requests': args.requests,
        'data_size': args.data_size,
        'pipeline': args.pipeline,
        'precision': args.precision,
        'cluster': args.cluster
    }
    
    # Only add optional parameters if they are specified
    if args.keyspace:
        benchmark_params['keyspace'] = args.keyspace
    if args.tests:
        benchmark_params['tests'] = args.tests
    if args.threads:
        benchmark_params['threads'] = args.threads
    if args.seed:
        benchmark_params['seed'] = args.seed
    
    if args.explore_configs:
        print("[INFO] Starting configuration exploration mode")
        # Test different configurations
        configs_to_test = [
            {},  # Default
            {'io_threads': 4},
            {'io_threads': 8},
            {'io_threads': 4, 'io_threads_do_reads': 'yes'},
            {'hz': 100},
            {'maxmemory': '512mb', 'maxmemory_policy': 'allkeys-lru'}
        ]
        
        print(f"[INFO] Testing {len(configs_to_test)} different configurations")
        
        for i, config in enumerate(configs_to_test):
            print(f"[INFO] Testing configuration {i+1}/{len(configs_to_test)}: {config}")
            print(f"\n{'='*50}")
            print(f"Testing configuration {i+1}/{len(configs_to_test)}: {config}")
            print('='*50)
            
            try:
                benchmark = RedisBenchmark(redis_dir=args.redis_dir, results_dir=args.results_dir, config_options=config)
                result = benchmark.run_quick_benchmark(**benchmark_params)
                
                if result and result.get('parsed_metrics'):
                    print(f"[INFO] Configuration {i+1} completed successfully")
                    print("\nParsed Metrics:")
                    for metric in result['parsed_metrics']:
                        print(f"  Test: {metric.get('test', 'N/A')}")
                        print(f"  RPS: {metric.get('rps', 'N/A'):,.0f}")
                        if 'avg_latency_ms' in metric:
                            print(f"  Avg Latency: {metric['avg_latency_ms']:.3f}ms")
                        if 'p99_latency_ms' in metric:
                            print(f"  P99 Latency: {metric['p99_latency_ms']:.3f}ms")
                else:
                    print(f"[ERROR] Configuration {i+1} failed or produced no results")
                    print(f"Configuration {i+1} failed")
            except Exception as e:
                print(f"[ERROR] Exception during configuration {i+1}: {e}")
                print(f"Error testing configuration {i+1}: {e}")
        
        print("[INFO] Configuration exploration completed")
        return
    
    try:
        benchmark = RedisBenchmark(redis_dir=args.redis_dir, results_dir=args.results_dir, config_options=config_options)
        print("[INFO] RedisBenchmark instance created successfully")
    except Exception as e:
        print(f"[ERROR] Failed to create RedisBenchmark instance: {e}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        print(f"Error: Failed to create benchmark instance: {e}")
        sys.exit(1)
    
    print("Redis Benchmark Suite")
    print("=" * 50)
    
    if args.quick:
        print("[INFO] Running quick benchmark mode")
        try:
            result = benchmark.run_quick_benchmark(**benchmark_params)
            
            if result and result.get('parsed_metrics'):
                print("[INFO] Quick benchmark completed with parsed metrics")
                print("\nParsed Metrics:")
                for metric in result['parsed_metrics']:
                    print(f"  Test: {metric.get('test', 'N/A')}")
                    print(f"  RPS: {metric.get('rps', 'N/A'):,.0f}")
                    if 'avg_latency_ms' in metric:
                        print(f"  Avg Latency: {metric['avg_latency_ms']:.3f}ms")
                    if 'p99_latency_ms' in metric:
                        print(f"  P99 Latency: {metric['p99_latency_ms']:.3f}ms")
                    print()
            else:
                print("[ERROR] Quick benchmark failed or produced no results")
                print("Quick benchmark failed")
        except Exception as e:
            print(f"[ERROR] Exception during quick benchmark: {e}")
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            print(f"Error during quick benchmark: {e}")
    else:
        print("[INFO] Running comprehensive benchmark mode")
        try:
            results = benchmark.run_comprehensive_benchmark(**benchmark_params)
            
            if results:
                print("[INFO] Comprehensive benchmark completed successfully")
                # Save detailed results
                results_file = benchmark.save_results(results)
                
                # Generate and display summary
                try:
                    summary = benchmark.generate_summary(results)
                    print("[INFO] Generated benchmark summary")
                except Exception as e:
                    print(f"[ERROR] Failed to generate summary: {e}")
                    summary = {"total_tests": len(results), "successful_tests": 0, "failed_tests": 0, "total_duration": 0}
                
                print("\n" + "=" * 50)
                print("BENCHMARK SUMMARY")
                print("=" * 50)
                print(f"Total tests: {summary['total_tests']}")
                print(f"Successful: {summary['successful_tests']}")
                print(f"Failed: {summary['failed_tests']}")
                print(f"Total duration: {summary['total_duration']:.2f} seconds")
                if summary.get('redis_config'):
                    print(f"Redis config: {summary['redis_config']}")
                
                print("\nTest Results:")
                for test in summary.get('test_summary', []):
                    status_symbol = "✓" if test['status'] == 'success' else "✗"
                    print(f"  {status_symbol} {test['test_name']}: {test['duration']:.2f}s")
                    
                    metrics = test.get('metrics', {})
                    if isinstance(metrics, dict):
                        for key, value in metrics.items():
                            if isinstance(value, dict):
                                for k, v in value.items():
                                    print(f"      {k}: {v}")
                            elif 'requests_per_second' in key:
                                print(f"    RPS: {value:,.0f}")
                            elif 'latency' in key:
                                print(f"    {key}: {value:.2f}ms")
            else:
                print("[ERROR] Comprehensive benchmark failed or produced no results")
                print("Failed to run benchmarks")
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Exception during comprehensive benchmark: {e}")
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            print(f"Error during comprehensive benchmark: {e}")
            sys.exit(1)

if __name__ == "__main__":
    try:
        main()
        print("[INFO] Redis benchmark completed successfully")
    except KeyboardInterrupt:
        print("[INFO] Redis benchmark interrupted by user")
        print("\nBenchmark interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"[ERROR] Unhandled exception in main: {e}")
        print(f"[ERROR] Full traceback: {traceback.format_exc()}")
        print(f"Fatal error: {e}")
        sys.exit(1)