#!/usr/bin/env python3
"""
Schbench Testing Module - Specialized testing utilities for schbench benchmarking
Provides schbench-specific functionality for testing scheduler performance.
"""

import os
import sys
import json
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, List, Tuple
from pathlib import Path

# Add the scheduler module to the path (relative to repository root)
repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(repo_root))

from scheduler import SchedulerRunner, SchedulerBenchmark


class SchbenchTester(SchedulerBenchmark):
    """
    Specialized class for testing schedulers with schbench.
    
    This class extends SchedulerBenchmark to provide schbench-specific
    functionality including output parsing and result visualization.
    """
    
    def __init__(self, schbench_path: str, results_dir: str = "results", 
                 scheduler_runner: SchedulerRunner = None):
        """
        Initialize the SchbenchTester.
        
        Args:
            schbench_path: Path to schbench binary
            results_dir: Directory to store results
            scheduler_runner: SchedulerRunner instance to use
        """
        super().__init__(scheduler_runner)
        
        self.schbench_path = schbench_path
        self.results_dir = results_dir
        
        # Create results directory
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Default test parameters
        self.test_params = {
            "message_threads": 2,
            "message_groups": 4,
            "runtime": 30,  # seconds
            "sleeptime": 10000,  # microseconds
            "operations": 5,   # operations per request
        }
    
    def set_test_params(self, **kwargs):
        """
        Update test parameters.
        
        Args:
            **kwargs: Test parameters to update
        """
        self.test_params.update(kwargs)
    
    def _parse_schbench_output(self, output: str) -> Dict:
        """Parse schbench output to extract performance metrics"""
        results = {
            "latency_percentiles": {},
            "throughput": 0,
            "cpu_utilization": 0,
            "raw_output": output
        }
        
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
            
            # Parse request latency percentiles (these are the main latency metrics)
            if parsing_request_latencies and "th:" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.endswith("th:"):
                        percentile = part[:-3]
                        if i + 1 < len(parts):
                            value_str = parts[i + 1]
                            try:
                                # Convert to microseconds if needed
                                value = float(value_str)
                                results["latency_percentiles"][percentile] = value
                            except ValueError:
                                pass
            
            # Parse throughput (average rps)
            elif "average rps:" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "rps:" and i + 1 < len(parts):
                        try:
                            results["throughput"] = float(parts[i + 1])
                        except ValueError:
                            pass
        
        return results
    
    def _build_schbench_command(self) -> List[str]:
        """Build schbench command with current parameters"""
        return [
            self.schbench_path,
            "-m", str(self.test_params["message_threads"]),
            "-t", str(self.test_params["message_groups"]),
            "-r", str(self.test_params["runtime"]),
            "-s", str(self.test_params["sleeptime"]),
            "-n", str(self.test_params["operations"]),
        ]
    
    def run_schbench_test(self, scheduler_name: str = None) -> Dict:
        """
        Run schbench test with specified scheduler.
        
        Args:
            scheduler_name: Name of the scheduler to test (None for default)
            
        Returns:
            Dictionary containing test results
        """
        print(f"Running schbench test with scheduler: {scheduler_name or 'default'}")
        
        # Build schbench command
        cmd = self._build_schbench_command()
        timeout = self.test_params["runtime"] + 30
        
        if scheduler_name:
            # Run with specific scheduler
            exit_code, stdout, stderr = self.runner.run_command_with_scheduler(
                scheduler_name, cmd, timeout=timeout
            )
        else:
            # Run with default scheduler
            import subprocess
            try:
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=timeout
                )
                exit_code, stdout, stderr = result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                exit_code, stdout, stderr = -1, "", "Command timed out"
            except Exception as e:
                exit_code, stdout, stderr = -1, "", str(e)
        
        if exit_code != 0:
            print(f"Warning: schbench exited with code {exit_code}")
            print(f"stderr: {stderr}")
        
        # Parse results (schbench outputs to stderr)
        output_to_parse = stderr if stderr.strip() else stdout
        results = self._parse_schbench_output(output_to_parse)
        results["scheduler"] = scheduler_name or "default"
        results["exit_code"] = exit_code
        
        return results
    
    def run_all_schbench_tests(self, production_only: bool = True) -> Dict:
        """
        Run schbench tests for all schedulers.
        
        Args:
            production_only: Only test production-ready schedulers
            
        Returns:
            Dictionary mapping scheduler names to test results
        """
        results = {}
        
        # Test default scheduler first
        print("Testing default scheduler...")
        results["default"] = self.run_schbench_test()
        
        # Test each scheduler
        schedulers = self.runner.get_available_schedulers(production_only)
        for scheduler_name in schedulers:
            try:
                print(f"Testing scheduler: {scheduler_name}")
                results[scheduler_name] = self.run_schbench_test(scheduler_name)
                
                # Save intermediate results
                self.save_results(results)
                
                # Brief pause between tests
                import time
                time.sleep(2)
                
            except Exception as e:
                print(f"Error testing scheduler {scheduler_name}: {e}")
                results[scheduler_name] = {
                    "scheduler": scheduler_name,
                    "error": str(e),
                    "latency_percentiles": {},
                    "throughput": 0
                }
        
        return results
    
    def save_results(self, results: Dict):
        """Save results to JSON file"""
        results_file = os.path.join(self.results_dir, "schbench_results.json")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {results_file}")
    
    def generate_performance_figures(self, results: Dict):
        """Generate performance comparison figures"""
        
        # Extract data for plotting
        schedulers = []
        latency_50th = []
        latency_95th = []
        latency_99th = []
        throughput = []
        
        for scheduler_name, result in results.items():
            if "error" in result:
                continue
            
            schedulers.append(scheduler_name)
            
            # Get latency percentiles
            percentiles = result.get("latency_percentiles", {})
            latency_50th.append(percentiles.get("50.0", 0))
            latency_95th.append(percentiles.get("95.0", 0))
            latency_99th.append(percentiles.get("99.0", 0))
            
            # Get throughput
            throughput.append(result.get("throughput", 0))
        
        if not schedulers:
            print("No valid results to plot")
            return
        
        # Create figure with subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Scheduler Performance Comparison with schbench', fontsize=16)
        
        # Plot 1: Latency Percentiles
        x = np.arange(len(schedulers))
        width = 0.25
        
        ax1.bar(x - width, latency_50th, width, label='50th percentile', alpha=0.8)
        ax1.bar(x, latency_95th, width, label='95th percentile', alpha=0.8)
        ax1.bar(x + width, latency_99th, width, label='99th percentile', alpha=0.8)
        
        ax1.set_xlabel('Scheduler')
        ax1.set_ylabel('Latency (us)')
        ax1.set_title('Latency Percentiles')
        ax1.set_xticks(x)
        ax1.set_xticklabels(schedulers, rotation=45, ha='right')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Throughput
        ax2.bar(schedulers, throughput, color='skyblue', alpha=0.8)
        ax2.set_xlabel('Scheduler')
        ax2.set_ylabel('Throughput (requests/sec)')
        ax2.set_title('Throughput Comparison')
        ax2.tick_params(axis='x', rotation=45)
        ax2.grid(True, alpha=0.3)
        
        # Plot 3: 95th Percentile Latency vs Throughput
        ax3.scatter(throughput, latency_95th, s=100, alpha=0.7)
        for i, scheduler in enumerate(schedulers):
            ax3.annotate(scheduler, (throughput[i], latency_95th[i]), 
                        xytext=(5, 5), textcoords='offset points', fontsize=8)
        ax3.set_xlabel('Throughput (requests/sec)')
        ax3.set_ylabel('95th Percentile Latency (us)')
        ax3.set_title('Latency vs Throughput')
        ax3.grid(True, alpha=0.3)
        
        # Plot 4: Performance Summary (Normalized)
        if len(schedulers) > 1:
            # Normalize metrics (higher is better for throughput, lower is better for latency)
            norm_throughput = np.array(throughput) / max(throughput) if max(throughput) > 0 else np.zeros(len(throughput))
            norm_latency = (max(latency_95th) - np.array(latency_95th)) / max(latency_95th) if max(latency_95th) > 0 else np.zeros(len(latency_95th))
            
            # Combined score (simple average)
            combined_score = (norm_throughput + norm_latency) / 2
            
            bars = ax4.bar(schedulers, combined_score, color='lightgreen', alpha=0.8)
            ax4.set_xlabel('Scheduler')
            ax4.set_ylabel('Combined Performance Score')
            ax4.set_title('Overall Performance Score\n(Higher is Better)')
            ax4.tick_params(axis='x', rotation=45)
            ax4.grid(True, alpha=0.3)
            
            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                ax4.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.2f}',
                        ha='center', va='bottom', fontsize=8)
        
        plt.tight_layout()
        
        # Save figure
        figure_path = os.path.join(self.results_dir, "schbench_performance_comparison.png")
        plt.savefig(figure_path, dpi=300, bbox_inches='tight')
        print(f"Performance figure saved to {figure_path}")
        
        # Print summary
        self.print_performance_summary(results)
    
    def print_performance_summary(self, results: Dict):
        """Print performance summary"""
        print("\n" + "="*60)
        print("SCHEDULER PERFORMANCE SUMMARY")
        print("="*60)
        
        for scheduler_name, result in results.items():
            if "error" in result:
                print(f"\n{scheduler_name:15} ERROR: {result['error']}")
                continue
            
            print(f"\n{scheduler_name:15}")
            print(f"  Throughput:     {result.get('throughput', 0):8.1f} requests/sec")
            
            percentiles = result.get("latency_percentiles", {})
            print(f"  50th percentile: {percentiles.get('50.0', 0):7.1f} us")
            print(f"  95th percentile: {percentiles.get('95.0', 0):7.1f} us")
            print(f"  99th percentile: {percentiles.get('99.0', 0):7.1f} us")