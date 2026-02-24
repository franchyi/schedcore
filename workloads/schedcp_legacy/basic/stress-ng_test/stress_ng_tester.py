#!/usr/bin/env python3
import os
import json
import time
import subprocess
import re
import sys
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# Add scheduler module to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scheduler')))
from scheduler_runner import SchedulerRunner, SchedulerBenchmark

class StressNgTester(SchedulerBenchmark):
    def __init__(self, duration=30, cpu_workers=0, vm_workers=2, io_workers=2, 
                 stress_tests=['cpu', 'vm', 'io'], output_file='results/stress_ng_results.json'):
        super().__init__()
        self.duration = duration
        self.cpu_workers = cpu_workers
        self.vm_workers = vm_workers
        self.io_workers = io_workers
        self.stress_tests = stress_tests
        self.output_file = output_file
        self.results = {}
        self.stress_ng_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'stress-ng', 'stress-ng'))
        
        # Create results directory if it doesn't exist
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        
    def build_stress_ng_command(self):
        """Build stress-ng command with specified parameters"""
        cmd = [self.stress_ng_path]
        
        # Add timeout
        cmd.extend(['--timeout', f'{self.duration}s'])
        
        # Add metrics output
        cmd.append('--metrics')
        
        # Add stress tests
        if 'cpu' in self.stress_tests:
            workers = self.cpu_workers if self.cpu_workers > 0 else 0
            cmd.extend(['--cpu', str(workers)])
            cmd.append('--cpu-method')
            cmd.append('all')
            
        if 'vm' in self.stress_tests:
            cmd.extend(['--vm', str(self.vm_workers)])
            cmd.extend(['--vm-bytes', '512M'])
            
        if 'io' in self.stress_tests:
            cmd.extend(['--io', str(self.io_workers)])
            
        return cmd
    
    def parse_stress_ng_output(self, output):
        """Parse stress-ng output to extract metrics"""
        metrics = {}
        
        # Parse bogo-ops metrics - look for lines starting with "stress-ng: metrc:"
        # Format: stressor bogo_ops real_time usr_time sys_time bogo_ops/s_real bogo_ops/s_usr+sys cpu_percent rss_max
        metric_pattern = r'stress-ng: metrc:.*?(\w+)\s+(\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+)'
        
        for line in output.split('\n'):
            # Look for metrics lines
            match = re.search(metric_pattern, line)
            if match and match.group(1) != 'stressor':  # Skip header line
                stressor = match.group(1)
                bogo_ops = float(match.group(2))
                real_time = float(match.group(3))
                usr_time = float(match.group(4))
                sys_time = float(match.group(5))
                bogo_ops_per_sec_real = float(match.group(6))
                bogo_ops_per_sec_usr_sys = float(match.group(7))
                cpu_percent = float(match.group(8))
                rss_max = int(match.group(9))
                
                metrics[stressor] = {
                    'bogo_ops': bogo_ops,
                    'real_time': real_time,
                    'usr_time': usr_time,
                    'sys_time': sys_time,
                    'bogo_ops_per_sec_real': bogo_ops_per_sec_real,
                    'bogo_ops_per_sec_usr_sys': bogo_ops_per_sec_usr_sys,
                    'cpu_percent': cpu_percent,
                    'rss_max_kb': rss_max
                }
                
        # Also capture summary metrics
        summary_pattern = r'stress-ng:\s+info:\s+\[(.*?)\]\s+(.*)'
        for line in output.split('\n'):
            if 'successful run completed' in line:
                metrics['completed'] = True
            elif 'metrics' in line.lower() and 'bogo-ops' in line.lower():
                # Extract total bogo-ops if available
                match = re.search(r'(\d+\.\d+)\s+bogo-ops', line)
                if match:
                    metrics['total_bogo_ops'] = float(match.group(1))
                    
        return metrics
    
    def run_stress_ng_test(self, scheduler_name=None):
        """Run stress-ng test with optional scheduler"""
        scheduler = None
        
        try:
            # Start scheduler if specified
            if scheduler_name:
                print(f"Starting scheduler: {scheduler_name}")
                scheduler = self.runner.start_scheduler(scheduler_name)
                if not scheduler:
                    print(f"Failed to start scheduler {scheduler_name}")
                    return None
                time.sleep(2)  # Give scheduler time to initialize
            
            # Build and run stress-ng command
            cmd = self.build_stress_ng_command()
            print(f"Running: {' '.join(cmd)}")
            
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True)
            end_time = time.time()
            
            if result.returncode != 0:
                print(f"stress-ng failed with return code {result.returncode}")
                print(f"stderr: {result.stderr}")
                return None
            
            # Parse output
            metrics = self.parse_stress_ng_output(result.stdout)
            metrics['duration'] = end_time - start_time
            metrics['scheduler'] = scheduler_name or 'baseline'
            
            # Calculate aggregate performance
            total_bogo_ops_per_sec = 0
            for stressor, data in metrics.items():
                if isinstance(data, dict) and 'bogo_ops_per_sec_real' in data:
                    total_bogo_ops_per_sec += data['bogo_ops_per_sec_real']
            
            metrics['aggregate_bogo_ops_per_sec'] = total_bogo_ops_per_sec
            
            return metrics
            
        finally:
            # Stop scheduler if it was started
            if scheduler:
                print(f"Stopping scheduler: {scheduler_name}")
                self.runner.stop_scheduler(scheduler_name)
                time.sleep(2)
    
    def run_all_tests(self, skip_baseline=False, specific_schedulers=None):
        """Run tests with all schedulers"""
        schedulers = self.runner.get_available_schedulers()
        
        if specific_schedulers:
            schedulers = [s for s in schedulers if s in specific_schedulers]
        
        # Run baseline test
        if not skip_baseline:
            print("\nRunning baseline test (no scheduler)...")
            baseline_result = self.run_stress_ng_test()
            if baseline_result:
                self.results['baseline'] = baseline_result
            print("-" * 60)
        
        # Run tests with each scheduler
        for scheduler in schedulers:
            print(f"\nTesting with scheduler: {scheduler}")
            result = self.run_stress_ng_test(scheduler)
            if result:
                self.results[scheduler] = result
            else:
                print(f"Test failed for scheduler: {scheduler}")
            print("-" * 60)
        
        # Save results
        self.save_results()
        
    def save_results(self):
        """Save test results to JSON file"""
        output_data = {
            'test_info': {
                'timestamp': datetime.now().isoformat(),
                'duration': self.duration,
                'stress_tests': self.stress_tests,
                'cpu_workers': self.cpu_workers,
                'vm_workers': self.vm_workers,
                'io_workers': self.io_workers
            },
            'results': self.results
        }
        
        with open(self.output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\nResults saved to: {self.output_file}")
    
    def generate_performance_figures(self):
        """Generate performance comparison figures"""
        if not self.results:
            print("No results to plot")
            return
        
        # Prepare data for plotting
        schedulers = list(self.results.keys())
        aggregate_performance = []
        stressor_performance = {}
        
        for scheduler in schedulers:
            result = self.results[scheduler]
            aggregate_performance.append(result.get('aggregate_bogo_ops_per_sec', 0))
            
            # Collect per-stressor performance
            for key, value in result.items():
                if isinstance(value, dict) and 'bogo_ops_per_sec_real' in value:
                    if key not in stressor_performance:
                        stressor_performance[key] = []
                    stressor_performance[key].append(value['bogo_ops_per_sec_real'])
        
        # Create figure with subplots
        num_stressors = len(stressor_performance)
        fig, axes = plt.subplots(1, num_stressors + 1, figsize=(15, 6))
        
        if num_stressors == 0:
            axes = [axes]
        elif num_stressors == 1:
            axes = [axes[0], axes[1]]
        
        # Plot aggregate performance
        ax = axes[0]
        bars = ax.bar(schedulers, aggregate_performance)
        ax.set_xlabel('Scheduler')
        ax.set_ylabel('Bogo-ops/s')
        ax.set_title('Aggregate Performance')
        ax.tick_params(axis='x', rotation=45)
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.0f}', ha='center', va='bottom')
        
        # Plot per-stressor performance
        for idx, (stressor, values) in enumerate(stressor_performance.items()):
            ax = axes[idx + 1]
            bars = ax.bar(schedulers, values)
            ax.set_xlabel('Scheduler')
            ax.set_ylabel('Bogo-ops/s')
            ax.set_title(f'{stressor} Performance')
            ax.tick_params(axis='x', rotation=45)
            
            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.0f}', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig('results/stress_ng_performance_comparison.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # Create a summary plot
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Normalize performance relative to baseline
        if 'baseline' in self.results:
            baseline_perf = self.results['baseline'].get('aggregate_bogo_ops_per_sec', 1)
            if baseline_perf == 0:
                baseline_perf = 1  # Avoid division by zero
            normalized_perf = [perf / baseline_perf * 100 for perf in aggregate_performance]
            
            bars = ax.bar(schedulers, normalized_perf)
            ax.axhline(y=100, color='r', linestyle='--', label='Baseline')
            ax.set_xlabel('Scheduler')
            ax.set_ylabel('Performance (% of baseline)')
            ax.set_title('stress-ng Performance Comparison')
            ax.tick_params(axis='x', rotation=45)
            ax.legend()
            
            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.1f}%', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig('results/stress_ng_normalized_performance.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("Performance figures saved to results/ directory")
    
    def generate_summary(self):
        """Generate a text summary of the results"""
        if not self.results:
            return "No results available"
        
        summary = []
        summary.append("stress-ng Benchmark Results Summary")
        summary.append("=" * 50)
        summary.append(f"Test Duration: {self.duration}s")
        summary.append(f"Stress Tests: {', '.join(self.stress_tests)}")
        summary.append(f"Workers - CPU: {self.cpu_workers or 'auto'}, VM: {self.vm_workers}, IO: {self.io_workers}")
        summary.append("")
        
        # Sort by aggregate performance
        sorted_results = sorted(self.results.items(), 
                              key=lambda x: x[1].get('aggregate_bogo_ops_per_sec', 0), 
                              reverse=True)
        
        summary.append("Performance Ranking (by aggregate bogo-ops/s):")
        for rank, (scheduler, result) in enumerate(sorted_results, 1):
            perf = result.get('aggregate_bogo_ops_per_sec', 0)
            summary.append(f"{rank}. {scheduler}: {perf:.2f} bogo-ops/s")
        
        return "\n".join(summary)