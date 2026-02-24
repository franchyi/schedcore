#!/usr/bin/env python3
"""
Redis Scheduler Testing Script
Tests different schedulers with Redis benchmarks to compare performance.
"""

import os
import sys
import subprocess
import json
import time
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse
import traceback
from pathlib import Path

# Import utility functions
from utils import (
    RedisCleanup,
    ProcessManager,
    BenchmarkSummary
)

# Add the scheduler module to the path (relative to repository root)
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

try:
    from scheduler import SchedulerRunner, SchedulerBenchmark
    from redis_benchmark import RedisBenchmark
    print("[INFO] Successfully imported scheduler and redis_benchmark modules")
except ImportError as e:
    print(f"[ERROR] Failed to import required modules: {e}")
    print("[ERROR] Ensure the scheduler module and redis_benchmark.py are accessible")
    sys.exit(1)


class RedisBenchmarkTester(SchedulerBenchmark):
    """
    Specialized class for testing schedulers with Redis benchmarks.
    
    This class extends SchedulerBenchmark to provide Redis-specific
    functionality including performance testing and result visualization.
    """
    
    def __init__(self, redis_dir: str = "redis-src", results_dir: str = "results",
                 scheduler_runner: SchedulerRunner = None):
        """
        Initialize the RedisBenchmarkTester.
        
        Args:
            redis_dir: Path to Redis source directory
            results_dir: Directory to store results
            scheduler_runner: SchedulerRunner instance to use
        """
        print(f"[INFO] Initializing RedisBenchmarkTester with redis_dir={redis_dir}, results_dir={results_dir}")
        
        try:
            super().__init__(scheduler_runner)
            print("[INFO] Successfully initialized parent SchedulerBenchmark class")
        except Exception as e:
            print(f"[ERROR] Failed to initialize parent class: {e}")
            raise
        
        self.redis_dir = redis_dir
        self.results_dir = results_dir
        
        # Validate Redis directory
        redis_path = Path(redis_dir)
        if not redis_path.exists():
            print(f"[ERROR] Redis directory does not exist: {redis_dir}")
            raise FileNotFoundError(f"Redis directory not found: {redis_dir}")
        
        # Check for Redis binaries
        redis_server = redis_path / "src" / "redis-server"
        redis_benchmark = redis_path / "src" / "redis-benchmark"
        redis_cli = redis_path / "src" / "redis-cli"
        
        missing_binaries = []
        for binary in [redis_server, redis_benchmark, redis_cli]:
            if not binary.exists():
                missing_binaries.append(str(binary))
        
        if missing_binaries:
            print(f"[ERROR] Missing Redis binaries: {missing_binaries}")
            print("[ERROR] Please build Redis first with 'make build' in the Redis directory")
            raise FileNotFoundError(f"Redis binaries not found: {missing_binaries}")
        
        print("[INFO] Redis binaries validated successfully")
        
        # Create results directory
        try:
            os.makedirs(self.results_dir, exist_ok=True)
            print(f"[INFO] Results directory created/verified: {self.results_dir}")
        except Exception as e:
            print(f"[ERROR] Failed to create results directory {self.results_dir}: {e}")
            raise
        
        # Default test parameters
        self.test_params = {
            "clients": 50,
            "requests": 1000000,
            "data_size": 1,
            "pipeline": 16,
            "keyspace": None,
            "timeout": 300,
        }
        
        # Redis configuration options
        self.redis_config = {
            "io_threads": 64,
            "io_threads_do_reads": "yes",
            "maxmemory": "256gb",
            "hz": 100
        }
    
    def set_test_params(self, **kwargs):
        """
        Update test parameters.
        
        Args:
            **kwargs: Test parameters to update
        """
        self.test_params.update(kwargs)
    
    def set_redis_config(self, **kwargs):
        """
        Update Redis configuration.
        
        Args:
            **kwargs: Redis config parameters to update
        """
        self.redis_config.update(kwargs)
    
    def cleanup_redis_files(self):
        """Clean up Redis temporary files including .rdb and config files"""
        RedisCleanup.cleanup_redis_files()
    
    def run_redis_benchmark(self, scheduler_name: str = None) -> dict:
        """
        Run Redis benchmark with specified scheduler.
        
        Args:
            scheduler_name: Name of the scheduler to test (None for default)
            
        Returns:
            Dictionary containing benchmark results
        """
        print(f"[INFO] Starting Redis benchmark with scheduler: {scheduler_name or 'default'}")
        tests_display = self.test_params.get('tests') or 'all default tests'
        print(f"[INFO] Benchmark parameters: clients={self.test_params['clients']}, "
                   f"requests={self.test_params['requests']}, "
                   f"tests={tests_display}, "
                   f"data_size={self.test_params.get('data_size', 3)}, "
                   f"pipeline={self.test_params.get('pipeline', 1)}")
        
        print(f"Running Redis benchmark with scheduler: {scheduler_name or 'default'}")
        print(f"Parameters: clients={self.test_params['clients']}, "
              f"requests={self.test_params['requests']}, "
              f"tests={tests_display}")
        
        try:
            print("[INFO] Preparing to run benchmark")
            print(f"[INFO] Redis configuration: {self.redis_config}")
            
            # Function to run benchmark - creates a new Redis instance each time
            def run_benchmark():
                # Create Redis benchmark instance with current configuration
                # This ensures fresh start for each scheduler test
                redis_bench = RedisBenchmark(
                    redis_dir=self.redis_dir,
                    results_dir=self.results_dir,
                    config_options=self.redis_config
                )
                print("[INFO] RedisBenchmark instance created successfully")
                
                # Remove timeout from test_params for run_comprehensive_benchmark
                benchmark_params = {k: v for k, v in self.test_params.items() if k != 'timeout'}
                results = redis_bench.run_comprehensive_benchmark(**benchmark_params)
                
                # Ensure cleanup
                redis_bench.cleanup()
                
                return results
            
            if scheduler_name:
                # Run with specific scheduler
                print(f"[INFO] Preparing to start scheduler: {scheduler_name}")
                print(f"Starting scheduler: {scheduler_name}")
                
                # First ensure no other scheduler is running
                print("[INFO] Stopping any existing schedulers")
                try:
                    self.runner.stop_all_schedulers()
                    print("[INFO] Stopped existing schedulers via runner")
                except Exception as e:
                    print(f"[WARNING] Error stopping schedulers via runner: {e}")
                
                # Also kill any lingering scx schedulers
                ProcessManager.kill_scheduler_processes()
                
                time.sleep(2)
                
                try:
                    print(f"[INFO] Attempting to start scheduler: {scheduler_name}")
                    proc = self.runner.start_scheduler(scheduler_name)
                    
                    # Check if scheduler started successfully
                    if proc is None:
                        error_msg = f"Failed to start scheduler {scheduler_name}: start_scheduler returned None"
                        print(f"[ERROR] {error_msg}")
                        return {
                            "scheduler": scheduler_name,
                            "error": error_msg,
                            "exit_code": -1
                        }
                    
                    # Give scheduler a moment to initialize
                    time.sleep(1)
                    
                    if proc.poll() is not None:
                        try:
                            stdout, stderr = proc.communicate(timeout=5)
                            stdout_str = stdout.decode() if stdout else "No stdout"
                            stderr_str = stderr.decode() if stderr else "No stderr"
                            error_msg = f"Scheduler {scheduler_name} exited prematurely. Exit code: {proc.returncode}. Stdout: {stdout_str}. Stderr: {stderr_str}"
                            print(f"[ERROR] {error_msg}")
                        except subprocess.TimeoutExpired:
                            error_msg = f"Scheduler {scheduler_name} failed to start and communication timed out"
                            print(f"[ERROR] {error_msg}")
                        
                        return {
                            "scheduler": scheduler_name,
                            "error": error_msg,
                            "exit_code": proc.returncode if proc.returncode is not None else -1
                        }
                    
                    print(f"[INFO] Scheduler {scheduler_name} started successfully (PID: {proc.pid})")
                    
                except Exception as e:
                    error_msg = f"Exception while starting scheduler {scheduler_name}: {str(e)}"
                    print(f"[ERROR] {error_msg}")
                    print(f"[ERROR] Exception traceback: {traceback.format_exc()}")
                    return {
                        "scheduler": scheduler_name,
                        "error": error_msg,
                        "exit_code": -1
                    }
                
                # Small delay to ensure scheduler is running
                time.sleep(2)
                
                try:
                    print(f"[INFO] Running benchmark with scheduler {scheduler_name} active")
                    # Run benchmark while scheduler is active
                    results = run_benchmark()
                    
                    print(f"[INFO] Benchmark completed, stopping scheduler {scheduler_name}")
                    # Stop scheduler
                    try:
                        self.runner.stop_scheduler()
                        print(f"[INFO] Successfully stopped scheduler {scheduler_name}")
                    except Exception as e:
                        print(f"[WARNING] Error stopping scheduler {scheduler_name}: {e}")
                    
                    if not results:
                        error_msg = "Benchmark failed to produce results"
                        print(f"[ERROR] {error_msg}")
                        return {
                            "scheduler": scheduler_name,
                            "error": error_msg,
                            "exit_code": -1
                        }
                    
                    print(f"[INFO] Benchmark with scheduler {scheduler_name} completed successfully. Found {len(results)} result entries.")
                    
                    # Add scheduler info to results
                    for result in results:
                        result["scheduler"] = scheduler_name
                    
                    # Generate summary using RedisBenchmark's method
                    summary = self._generate_summary_from_results(results)
                    
                    # Clean up Redis files after test
                    self.cleanup_redis_files()
                    
                    return {
                        "scheduler": scheduler_name,
                        "results": results,
                        "summary": summary,
                        "exit_code": 0
                    }
                    
                except Exception as e:
                    error_msg = f"Error during benchmark with scheduler {scheduler_name}: {str(e)}"
                    print(f"[ERROR] {error_msg}")
                    print(f"[ERROR] Benchmark exception traceback: {traceback.format_exc()}")
                    print(f"Error during benchmark: {e}")
                    
                    try:
                        self.runner.stop_scheduler()
                        print("[INFO] Stopped scheduler after benchmark error")
                    except Exception as stop_e:
                        print(f"[ERROR] Failed to stop scheduler after benchmark error: {stop_e}")
                    
                    # Clean up Redis files even on error
                    self.cleanup_redis_files()
                    
                    return {
                        "scheduler": scheduler_name,
                        "error": error_msg,
                        "exit_code": -1
                    }
            else:
                print("[INFO] Running benchmark with default scheduler")
                # Run with default scheduler
                results = run_benchmark()
                if not results:
                    error_msg = "Benchmark with default scheduler failed to produce results"
                    print(f"[ERROR] {error_msg}")
                    return {
                        "scheduler": "default",
                        "error": error_msg,
                        "exit_code": -1
                    }
                
                print(f"[INFO] Benchmark with default scheduler completed successfully. Found {len(results)} result entries.")
                
                # Add scheduler info to results
                for result in results:
                    result["scheduler"] = "default"
                
                # Generate summary
                summary = self._generate_summary_from_results(results)
                
                # Clean up Redis files after test
                self.cleanup_redis_files()
                
                return {
                    "scheduler": "default",
                    "results": results,
                    "summary": summary,
                    "exit_code": 0
                }
        
        except Exception as e:
            error_msg = f"Unexpected error in run_redis_benchmark: {str(e)}"
            print(f"[ERROR] {error_msg}")
            print(f"[ERROR] Full traceback: {traceback.format_exc()}")
            return {
                "scheduler": scheduler_name or "default",
                "error": error_msg,
                "exit_code": -1
            }
    
    def _generate_summary_from_results(self, results):
        """Generate summary from benchmark results"""
        return BenchmarkSummary.generate_summary(results, self.redis_config)
    
    def extract_metrics_from_results(self, benchmark_result: dict) -> dict:
        """Extract key metrics from Redis benchmark results"""
        metrics = {
            "scheduler": benchmark_result.get("scheduler", "unknown"),
            "latency_p50": [],
            "latency_p95": [],
            "latency_p99": [],
            "latency_avg": [],
            "throughput_rps": [],
            "test_names": []
        }
        
        if "error" in benchmark_result:
            return metrics
        
        results = benchmark_result.get("results", [])
        
        # Process each test result
        for result in results:
            test_name = result.get("test_name", "unknown")
            parsed_metrics = result.get("parsed_metrics", [])
            
            # Use parsed_metrics as primary source (more detailed)
            if parsed_metrics:
                for metric in parsed_metrics:
                    test = metric.get("test", test_name.replace("_operations", ""))
                    rps = metric.get("rps", 0)
                    
                    if rps > 0:  # Only include valid metrics
                        metrics["test_names"].append(test)
                        metrics["throughput_rps"].append(rps)
                        
                        # Extract latency metrics
                        metrics["latency_avg"].append(metric.get("avg_latency_ms", 0))
                        metrics["latency_p50"].append(metric.get("p50_latency_ms", 0))
                        metrics["latency_p95"].append(metric.get("p95_latency_ms", 0))
                        metrics["latency_p99"].append(metric.get("p99_latency_ms", 0))
            
            # Fallback to regular metrics if parsed_metrics is empty
            elif result.get("metrics"):
                test_metrics = result.get("metrics", {})
                for test_name_key, test_data in test_metrics.items():
                    if isinstance(test_data, dict):
                        rps = test_data.get("requests_per_second", 0)
                        if rps > 0:
                            metrics["test_names"].append(test_name_key)
                            metrics["throughput_rps"].append(rps)
                            
                            # For fallback, we don't have detailed latency info
                            metrics["latency_avg"].append(0)
                            metrics["latency_p50"].append(0)
                            metrics["latency_p95"].append(0)
                            metrics["latency_p99"].append(0)
        
        return metrics
    
    def run_all_redis_benchmarks(self, production_only: bool = True) -> dict:
        """
        Run Redis benchmarks for all schedulers.
        
        Args:
            production_only: Only test production-ready schedulers
            
        Returns:
            Dictionary mapping scheduler names to benchmark results
        """
        print(f"[INFO] Starting comprehensive Redis benchmark suite (production_only={production_only})")
        results = {}
        
        # Test default scheduler first
        print("[INFO] Testing default scheduler...")
        print("Testing default scheduler...")
        try:
            results["default"] = self.run_redis_benchmark()
            if "error" in results["default"]:
                print(f"[ERROR] Default scheduler test failed: {results['default']['error']}")
            else:
                print("[INFO] Default scheduler test completed successfully")
        except Exception as e:
            print(f"[ERROR] Exception during default scheduler test: {e}")
            results["default"] = {
                "scheduler": "default",
                "error": f"Exception during test: {str(e)}",
                "exit_code": -1
            }
        
        # Test each scheduler
        try:
            schedulers = self.runner.get_available_schedulers(production_only)
            print(f"[INFO] Found {len(schedulers)} schedulers to test: {schedulers}")
        except Exception as e:
            print(f"[ERROR] Failed to get available schedulers: {e}")
            return results
        
        for i, scheduler_name in enumerate(schedulers, 1):
            try:
                print(f"[INFO] Testing scheduler {i}/{len(schedulers)}: {scheduler_name}")
                print(f"\nTesting scheduler: {scheduler_name}")
                
                start_time = time.time()
                results[scheduler_name] = self.run_redis_benchmark(scheduler_name)
                duration = time.time() - start_time
                
                if "error" in results[scheduler_name]:
                    print(f"[ERROR] Scheduler {scheduler_name} test failed after {duration:.1f}s: {results[scheduler_name]['error']}")
                else:
                    print(f"[INFO] Scheduler {scheduler_name} test completed successfully in {duration:.1f}s")
                
                # Save intermediate results
                try:
                    self.save_results(results)
                    print("[INFO] Intermediate results saved")
                except Exception as e:
                    print(f"[WARNING] Failed to save intermediate results: {e}")
                
                # Brief pause between tests
                print("[INFO] Pausing between tests...")
                time.sleep(3)
                
            except Exception as e:
                error_msg = f"Exception testing scheduler {scheduler_name}: {str(e)}"
                print(f"[ERROR] {error_msg}")
                print(f"[ERROR] Scheduler test exception traceback: {traceback.format_exc()}")
                print(f"Error testing scheduler {scheduler_name}: {e}")
                results[scheduler_name] = {
                    "scheduler": scheduler_name,
                    "error": error_msg,
                    "exit_code": -1
                }
        
        print(f"[INFO] Comprehensive benchmark suite completed. Tested {len(results)} configurations.")
        
        return results
    
    def save_results(self, results: dict):
        """Save results to JSON file"""
        try:
            # Use a single file name without timestamp
            results_file = os.path.join(self.results_dir, "redis_scheduler_results.json")
            
            # Ensure results directory exists
            os.makedirs(self.results_dir, exist_ok=True)
            
            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            print(f"[INFO] Results saved to {results_file}")
            print(f"Results saved to {results_file}")
        except Exception as e:
            print(f"[ERROR] Failed to save results: {e}")
            print(f"Error saving results: {e}")
    
    def generate_performance_figures(self, results: dict):
        """Generate performance comparison figures"""
        
        # Extract metrics from all results
        all_metrics = {}
        for scheduler_name, result in results.items():
            if "error" not in result:
                all_metrics[scheduler_name] = self.extract_metrics_from_results(result)
        
        if not all_metrics:
            print("No valid results to plot")
            return
        
        # Create separate figures for different metrics
        self._plot_throughput_comparison(all_metrics)
        self._plot_latency_comparison(all_metrics)
    
    def _plot_throughput_comparison(self, all_metrics: dict):
        """Plot throughput comparison across schedulers"""
        fig, ax = plt.subplots(figsize=(15, 8))
        
        # Prepare data for plotting
        schedulers = []
        test_types = set()
        
        # Collect all test types
        for metrics in all_metrics.values():
            test_types.update(metrics["test_names"])
        
        test_types = sorted(list(test_types))
        
        # Create data matrix
        data = []
        for scheduler_name, metrics in all_metrics.items():
            scheduler_data = []
            for test_type in test_types:
                # Find throughput for this test type
                if test_type in metrics["test_names"]:
                    idx = metrics["test_names"].index(test_type)
                    throughput = metrics["throughput_rps"][idx]
                else:
                    throughput = 0
                scheduler_data.append(throughput)
            data.append(scheduler_data)
            schedulers.append(scheduler_name)
        
        # Create grouped bar chart
        x = np.arange(len(test_types))
        width = 0.8 / len(schedulers)
        
        colors = plt.cm.Set3(np.linspace(0, 1, len(schedulers)))
        
        for i, (scheduler, color) in enumerate(zip(schedulers, colors)):
            offset = (i - len(schedulers)/2 + 0.5) * width
            bars = ax.bar(x + offset, data[i], width, label=scheduler, color=color, alpha=0.8)
            
            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{height:.0f}',
                           ha='center', va='bottom', fontsize=8, rotation=90)
        
        ax.set_xlabel('Redis Operations')
        ax.set_ylabel('Throughput (Requests/Second)')
        ax.set_title('Redis Throughput Performance by Scheduler')
        ax.set_xticks(x)
        ax.set_xticklabels(test_types, rotation=45)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save figure
        figure_path = os.path.join(self.results_dir, "redis_throughput_comparison.png")
        plt.savefig(figure_path, dpi=300, bbox_inches='tight')
        print(f"Throughput comparison figure saved to {figure_path}")
        plt.close()
    
    def _plot_latency_comparison(self, all_metrics: dict):
        """Plot latency comparison across schedulers"""
        latency_types = ["latency_avg", "latency_p50", "latency_p95", "latency_p99"]
        latency_labels = ["Average Latency", "P50 Latency", "P95 Latency", "P99 Latency"]
        
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Redis Latency Performance by Scheduler', fontsize=16)
        axes = axes.flatten()
        
        for idx, (latency_type, latency_label) in enumerate(zip(latency_types, latency_labels)):
            ax = axes[idx]
            
            # Collect data for this latency metric
            scheduler_names = []
            avg_latencies = []
            
            for scheduler_name, metrics in all_metrics.items():
                if metrics[latency_type]:  # If we have latency data
                    # Calculate average latency across all operations
                    valid_latencies = [l for l in metrics[latency_type] if l > 0]
                    if valid_latencies:
                        avg_latency = np.mean(valid_latencies)
                        scheduler_names.append(scheduler_name)
                        avg_latencies.append(avg_latency)
            
            if scheduler_names and avg_latencies:
                colors = plt.cm.Set3(np.linspace(0, 1, len(scheduler_names)))
                bars = ax.bar(scheduler_names, avg_latencies, color=colors, alpha=0.8)
                ax.set_xlabel('Scheduler')
                ax.set_ylabel('Latency (ms)')
                ax.set_title(f'{latency_label} (Lower is Better)')
                ax.tick_params(axis='x', rotation=45)
                ax.grid(True, alpha=0.3)
                
                # Add value labels on bars
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{height:.2f}',
                           ha='center', va='bottom', fontsize=8)
            else:
                ax.text(0.5, 0.5, 'No latency data available', 
                       ha='center', va='center', transform=ax.transAxes)
                ax.set_title(f'{latency_label} (No Data)')
        
        plt.tight_layout()
        
        # Save figure
        figure_path = os.path.join(self.results_dir, "redis_latency_comparison.png")
        plt.savefig(figure_path, dpi=300, bbox_inches='tight')
        print(f"Latency comparison figure saved to {figure_path}")
        plt.close()
    
    

    def run_parameter_sweep_multi_schedulers(self, schedulers: list = None,
                                            data_sizes: list = None,
                                            production_only: bool = False):
        """
        Run data size parameter sweep for multiple schedulers and generate comparison plots.
        
        Args:
            schedulers: List of scheduler names to test (None for all + default)
            data_sizes: List of data sizes to test (in bytes)
            production_only: Only test production-ready schedulers if schedulers is None
        """
        data_sizes = data_sizes or [1, 16, 64, 256, 1024, 2048]  # bytes
        # data_sizes = data_sizes or [1, 64]  # bytes
        # Get schedulers to test
        if schedulers is None:
            schedulers = ['default'] + self.runner.get_available_schedulers(production_only)
        elif 'default' not in schedulers:
            schedulers = ['default'] + schedulers
                
        print(f"Running data size parameter sweep for schedulers: {schedulers}")
        print(f"Data sizes: {data_sizes} bytes")
        
        all_results = []
        total_tests = len(schedulers) * len(data_sizes)
        test_count = 0
        
        for scheduler_name in schedulers:
            print(f"\n{'='*50}")
            print(f"Testing scheduler: {scheduler_name}")
            print(f"{'='*50}")
            
            for data_size in data_sizes:
                test_count += 1
                print(f"\nTest {test_count}/{total_tests}: "
                      f"scheduler={scheduler_name}, data_size={data_size}B")
                
                # Update test parameters
                self.set_test_params(
                    data_size=data_size,
                    requests=self.test_params["requests"],
                    timeout=self.test_params["timeout"]
                )
                
                # Run benchmark
                scheduler_to_test = None if scheduler_name == 'default' else scheduler_name
                result = self.run_redis_benchmark(scheduler_to_test)
                
                if "error" not in result:
                    # Extract metrics from the result
                    metrics = self.extract_metrics_from_results(result)
                    
                    # Add each test result as a separate row
                    for i, test_name in enumerate(metrics["test_names"]):
                        all_results.append({
                            'scheduler': scheduler_name,
                            'data_size': data_size,
                            'test_name': test_name,
                            'throughput_rps': metrics["throughput_rps"][i] if i < len(metrics["throughput_rps"]) else 0,
                            'latency_avg': metrics["latency_avg"][i] if i < len(metrics["latency_avg"]) else 0,
                            'latency_p50': metrics["latency_p50"][i] if i < len(metrics["latency_p50"]) else 0,
                            'latency_p95': metrics["latency_p95"][i] if i < len(metrics["latency_p95"]) else 0,
                            'latency_p99': metrics["latency_p99"][i] if i < len(metrics["latency_p99"]) else 0,
                            'requests': self.test_params["requests"],
                            'clients': self.test_params["clients"],
                            'pipeline': self.test_params["pipeline"]
                        })
                    
                    # Calculate average throughput for this configuration
                    avg_throughput = np.mean([t for t in metrics["throughput_rps"] if t > 0]) if metrics["throughput_rps"] else 0
                    print(f"  Avg Throughput: {avg_throughput:.0f} req/s")
                else:
                    print(f"  Failed: {result['error']}")
                    # Add failure record
                    all_results.append({
                        'scheduler': scheduler_name,
                        'data_size': data_size,
                        'test_name': 'failed',
                        'throughput_rps': 0,
                        'latency_avg': 0,
                        'latency_p50': 0,
                        'latency_p95': 0,
                        'latency_p99': 0,
                        'requests': self.test_params["requests"],
                        'clients': self.test_params["clients"],
                        'pipeline': self.test_params["pipeline"]
                    })
                
                time.sleep(2)  # Brief pause between tests
        
        if all_results:
            # Save results
            df = pd.DataFrame(all_results)
            results_file = os.path.join(self.results_dir, "redis_data_size_sweep.csv")
            df.to_csv(results_file, index=False)
            print(f"\nData size parameter sweep results saved to {results_file}")
            
            # Generate visualization
            self._plot_data_size_sweep(df)
    
    def _plot_data_size_sweep(self, df):
        """Plot performance vs data size for each scheduler"""
        data_sizes = sorted(df['data_size'].unique())
        schedulers = sorted(df['scheduler'].unique())
        
        # Color palette for different schedulers
        colors = plt.cm.tab10(np.linspace(0, 1, len(schedulers)))
        scheduler_colors = {sched: colors[i] for i, sched in enumerate(schedulers)}
        
        # Create dual plot
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        fig.suptitle('Redis Performance vs Data Size', fontsize=16)
        
        # Plot throughput and latency for each scheduler
        for scheduler in schedulers:
            sched_data = df[df['scheduler'] == scheduler]
            color = scheduler_colors[scheduler]
            
            # Aggregate data by data size
            avg_throughput = []
            avg_latency = []
            
            for data_size in data_sizes:
                size_data = sched_data[sched_data['data_size'] == data_size]
                
                # Average throughput for this data size
                avg_tput = size_data['throughput_rps'].mean() if not size_data.empty else 0
                avg_throughput.append(avg_tput)
                
                # Average latency (prefer P95, fallback to average)
                if not size_data.empty:
                    latency_values = size_data['latency_p95']
                    if latency_values.sum() == 0:
                        latency_values = size_data['latency_avg']
                    avg_lat = latency_values.mean() if latency_values.sum() > 0 else 0
                else:
                    avg_lat = 0
                avg_latency.append(avg_lat)
            
            # Plot throughput
            ax1.plot(data_sizes, avg_throughput, 'o-', 
                    color=color, label=scheduler, linewidth=2, markersize=6)
            
            # Plot latency  
            ax2.plot(data_sizes, avg_latency, 'o-',
                    color=color, label=scheduler, linewidth=2, markersize=6)
        
        # Configure throughput plot
        ax1.set_xlabel('Data Size (bytes)')
        ax1.set_ylabel('Average Throughput (req/s)')
        ax1.set_title('Throughput vs Data Size')
        ax1.set_xscale('log')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Configure latency plot
        ax2.set_xlabel('Data Size (bytes)')
        ax2.set_ylabel('Average P95 Latency (ms)')
        ax2.set_title('P95 Latency vs Data Size')
        ax2.set_xscale('log')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save figure
        figure_path = os.path.join(self.results_dir, "redis_data_size_sweep.png")
        plt.savefig(figure_path, dpi=300, bbox_inches='tight')
        print(f"Data size sweep figure saved to {figure_path}")
        plt.close()


def main():
    """Main function for Redis scheduler testing"""
    print("[INFO] Starting Redis scheduler testing script")
    print(f"[INFO] Python version: {sys.version}")
    print(f"[INFO] Working directory: {os.getcwd()}")
    
    parser = argparse.ArgumentParser(description="Test schedulers with Redis benchmarks")
    parser.add_argument("--redis-dir", default="redis-src",
                       help="Path to Redis source directory")
    parser.add_argument("--results-dir", default="results", 
                       help="Directory to store results")
    parser.add_argument("--production-only", action="store_true", 
                       help="Test only production schedulers")
    parser.add_argument("--clients", type=int, default=50, 
                       help="Number of Redis clients")
    parser.add_argument("--requests", type=int, default=1000000, 
                       help="Number of requests per test")
    parser.add_argument("--data-size", type=int, default=16,
                       help="Data size in bytes")
    parser.add_argument("--pipeline", type=int, default=16,
                       help="Pipeline requests")
    parser.add_argument("--tests", default=None,
                       help="Comma-separated list of tests to run")
    parser.add_argument("--io-threads", type=int, default=64,
                       help="Redis I/O threads")
    parser.add_argument("--maxmemory", default="256gb",
                       help="Redis max memory")
    parser.add_argument("--timeout", type=int, default=300,
                       help="Timeout in seconds")
    parser.add_argument("--scheduler", type=str, default=None,
                       help="Test specific scheduler only")
    parser.add_argument("--parameter-sweep", action="store_true",
                       help="Run parameter sweep comparing all schedulers with different data sizes")
    
    args = parser.parse_args()
    
    # Create tester instance
    print("[INFO] Creating RedisBenchmarkTester instance")
    try:
        tester = RedisBenchmarkTester(args.redis_dir, args.results_dir)
        print("[INFO] RedisBenchmarkTester created successfully")
    except Exception as e:
        print(f"[ERROR] Failed to create RedisBenchmarkTester: {e}")
        print(f"[ERROR] Exception traceback: {traceback.format_exc()}")
        print(f"Error: Failed to create benchmark tester: {e}")
        sys.exit(1)
    
    # Update test parameters
    tester.set_test_params(
        clients=args.clients,
        requests=args.requests,
        data_size=args.data_size,
        pipeline=args.pipeline,
        tests=args.tests,
        timeout=args.timeout
    )
    
    # Update Redis configuration
    tester.set_redis_config(
        io_threads=args.io_threads,
        maxmemory=args.maxmemory
    )
    
    # Check if Redis binaries exist
    redis_server = os.path.join(args.redis_dir, "src", "redis-server")
    print(f"[INFO] Checking for Redis server at: {redis_server}")
    
    if not os.path.exists(redis_server):
        error_msg = f"Redis server not found at {redis_server}"
        print(f"[ERROR] {error_msg}")
        print("[ERROR] Please ensure Redis is built in the specified directory")
        print("[ERROR] Build Redis with: cd redis-src && make")
        print(f"Error: Redis not found at {args.redis_dir}")
        print("Please ensure Redis is built in the specified directory")
        sys.exit(1)
    
    print("[INFO] Redis binaries found successfully")
    
    if args.parameter_sweep:
        print("[INFO] Starting parameter sweep mode")
        print("Running data size parameter sweep...")
        schedulers = None
        if args.scheduler:
            schedulers = [args.scheduler]
            print(f"[INFO] Parameter sweep limited to scheduler: {args.scheduler}")
        
        try:
            tester.run_parameter_sweep_multi_schedulers(
                schedulers=schedulers,
                production_only=args.production_only
            )
            print("[INFO] Parameter sweep completed successfully")
        except Exception as e:
            print(f"[ERROR] Parameter sweep failed: {e}")
            print(f"[ERROR] Exception traceback: {traceback.format_exc()}")
            print(f"Error during parameter sweep: {e}")
            sys.exit(1)
    else:
        if args.scheduler:
            print(f"[INFO] Testing single scheduler: {args.scheduler}")
            print(f"Testing scheduler: {args.scheduler}")
            try:
                result = tester.run_redis_benchmark(args.scheduler)
                results = {args.scheduler: result}
                
                if "error" in result:
                    print(f"[ERROR] Single scheduler test failed: {result['error']}")
                else:
                    print("[INFO] Single scheduler test completed successfully")
            except Exception as e:
                print(f"[ERROR] Single scheduler test failed with exception: {e}")
                print(f"[ERROR] Exception traceback: {traceback.format_exc()}")
                print(f"Error testing scheduler: {e}")
                sys.exit(1)
        else:
            print("[INFO] Starting comprehensive scheduler performance tests")
            print("Starting Redis scheduler performance tests...")
            try:
                results = tester.run_all_redis_benchmarks(production_only=args.production_only)
                print("[INFO] All scheduler tests completed")
            except Exception as e:
                print(f"[ERROR] Comprehensive tests failed with exception: {e}")
                print(f"[ERROR] Exception traceback: {traceback.format_exc()}")
                print(f"Error during comprehensive tests: {e}")
                sys.exit(1)
        
        # Generate figures
        print("[INFO] Generating performance figures")
        try:
            tester.generate_performance_figures(results)
            print("[INFO] Performance figures generated successfully")
        except Exception as e:
            print(f"[ERROR] Failed to generate performance figures: {e}")
            print(f"[ERROR] Figure generation traceback: {traceback.format_exc()}")
            print(f"Warning: Failed to generate performance figures: {e}")
    
    print("[INFO] Redis scheduler testing completed successfully")
    print("\nTesting complete!")
    
    # Final cleanup - processes and files
    try:
        RedisCleanup.kill_redis_processes()
        ProcessManager.kill_scheduler_processes()
        print("[INFO] Final process cleanup completed")
        
        # Clean up any remaining Redis files
        RedisCleanup.cleanup_redis_files()
        print("[INFO] Final file cleanup completed")
    except Exception as e:
        print(f"[WARNING] Final cleanup had issues: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[INFO] Testing interrupted by user")
        print("\nTesting interrupted by user")
        # Cleanup on interrupt
        try:
            RedisCleanup.kill_redis_processes()
            ProcessManager.kill_scheduler_processes()
            # Also clean up files
            RedisCleanup.cleanup_redis_files()
        except:
            pass
        sys.exit(130)
    except Exception as e:
        print(f"[ERROR] Unhandled exception in main: {e}")
        print(f"[ERROR] Full traceback: {traceback.format_exc()}")
        print(f"Fatal error: {e}")
        sys.exit(1)