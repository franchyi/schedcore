#!/usr/bin/env python3
import os
import json
import time
import subprocess
import sys
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import multiprocessing
import shutil

# Add scheduler module to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scheduler')))
from scheduler_runner import SchedulerRunner, SchedulerBenchmark

class LinuxBuildTester(SchedulerBenchmark):
    def __init__(self, jobs=0, config='tinyconfig', clean_between=False, 
                 output_file='results/linux_build_results.json', repeat=1, kernel_dir='linux'):
        super().__init__()
        self.jobs = jobs if jobs > 0 else multiprocessing.cpu_count()
        self.config = config
        self.clean_between = clean_between
        self.output_file = output_file
        self.repeat = repeat
        self.kernel_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), kernel_dir))
        self.results = {}
        
        # Create results directory if it doesn't exist
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        
        # Check if kernel directory exists
        if not os.path.exists(self.kernel_dir):
            raise FileNotFoundError(f"Kernel directory not found: {self.kernel_dir}")
    
    def check_kernel_configured(self):
        """Check if kernel is configured"""
        config_file = os.path.join(self.kernel_dir, '.config')
        return os.path.exists(config_file)
    
    def configure_kernel(self):
        """Configure the kernel with specified config"""
        print(f"Configuring kernel with {self.config}...")
        cmd = ['make', '-C', self.kernel_dir, self.config]
        
        result = subprocess.run(cmd, capture_output=False, text=True)
        if result.returncode != 0:
            print(f"Failed to configure kernel with return code: {result.returncode}")
            return False
        
        print("Kernel configuration complete.")
        return True
    
    def clean_kernel_build(self):
        """Clean kernel build artifacts"""
        print("Cleaning kernel build...")
        cmd = ['make', '-C', self.kernel_dir, 'clean']
        subprocess.run(cmd, capture_output=False, text=True)
    
    def run_kernel_build(self, scheduler_name=None):
        """Run kernel build with optional scheduler"""
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
            
            # Always clean before build to ensure consistent results
            self.clean_kernel_build()
            
            # Build kernel
            cmd = ['make', '-C', self.kernel_dir, f'-j{self.jobs}', 'vmlinux']
            print(f"Running: {' '.join(cmd)}")
            
            # Run build and measure time
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=False, text=True)
            end_time = time.time()
            
            build_time = end_time - start_time
            
            if result.returncode != 0:
                print(f"Build failed with return code {result.returncode}")
                return None
            
            # Collect metrics
            metrics = {
                'build_time': build_time,
                'scheduler': scheduler_name or 'baseline',
                'jobs': self.jobs,
                'config': self.config,
                'success': True
            }
            
            # Parse additional metrics from output if available (skip since we're not capturing output)
            if False:
                # Some make versions output timing info
                for line in result.stderr.split('\n'):
                    if 'real' in line and 'm' in line and 's' in line:
                        # Parse time format like "real    1m23.456s"
                        try:
                            time_str = line.split()[1]
                            if 'm' in time_str:
                                minutes, seconds = time_str.split('m')
                                seconds = seconds.rstrip('s')
                                metrics['reported_time'] = float(minutes) * 60 + float(seconds)
                        except:
                            pass
            
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
            baseline_times = []
            for i in range(self.repeat):
                if self.repeat > 1:
                    print(f"  Run {i+1}/{self.repeat}")
                result = self.run_kernel_build()
                if result:
                    baseline_times.append(result['build_time'])
            
            if baseline_times:
                self.results['baseline'] = {
                    'build_times': baseline_times,
                    'avg_build_time': np.mean(baseline_times),
                    'std_build_time': np.std(baseline_times),
                    'min_build_time': np.min(baseline_times),
                    'max_build_time': np.max(baseline_times),
                    'scheduler': 'baseline',
                    'jobs': self.jobs,
                    'config': self.config,
                    'runs': len(baseline_times)
                }
            print("-" * 60)
        
        # Run tests with each scheduler
        for scheduler in schedulers:
            print(f"\nTesting with scheduler: {scheduler}")
            build_times = []
            
            for i in range(self.repeat):
                if self.repeat > 1:
                    print(f"  Run {i+1}/{self.repeat}")
                result = self.run_kernel_build(scheduler)
                if result:
                    build_times.append(result['build_time'])
                else:
                    print(f"  Run {i+1} failed")
            
            if build_times:
                self.results[scheduler] = {
                    'build_times': build_times,
                    'avg_build_time': np.mean(build_times),
                    'std_build_time': np.std(build_times),
                    'min_build_time': np.min(build_times),
                    'max_build_time': np.max(build_times),
                    'scheduler': scheduler,
                    'jobs': self.jobs,
                    'config': self.config,
                    'runs': len(build_times)
                }
            else:
                print(f"All runs failed for scheduler: {scheduler}")
            print("-" * 60)
        
        # Save results
        self.save_results()
    
    def save_results(self):
        """Save test results to JSON file"""
        output_data = {
            'test_info': {
                'timestamp': datetime.now().isoformat(),
                'kernel_dir': self.kernel_dir,
                'config': self.config,
                'jobs': self.jobs,
                'repeat': self.repeat,
                'clean_between': self.clean_between
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
        avg_times = [self.results[s]['avg_build_time'] for s in schedulers]
        std_times = [self.results[s]['std_build_time'] for s in schedulers]
        
        # Create bar plot with error bars
        fig, ax = plt.subplots(figsize=(12, 8))
        
        bars = ax.bar(schedulers, avg_times, yerr=std_times, capsize=5)
        
        # Add value labels on bars
        for bar, avg_time in zip(bars, avg_times):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{avg_time:.1f}s', ha='center', va='bottom')
        
        ax.set_xlabel('Scheduler')
        ax.set_ylabel('Build Time (seconds)')
        ax.set_title(f'Linux Kernel Build Time Comparison\n'
                    f'Config: {self.config}, Jobs: {self.jobs}')
        ax.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('results/linux_build_time_comparison.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # Create normalized performance plot
        if 'baseline' in self.results:
            fig, ax = plt.subplots(figsize=(12, 8))
            
            baseline_time = self.results['baseline']['avg_build_time']
            normalized_times = [(baseline_time / self.results[s]['avg_build_time']) * 100 
                               for s in schedulers]
            
            bars = ax.bar(schedulers, normalized_times)
            ax.axhline(y=100, color='r', linestyle='--', label='Baseline')
            
            # Add value labels
            for bar, norm_time in zip(bars, normalized_times):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{norm_time:.1f}%', ha='center', va='bottom')
            
            ax.set_xlabel('Scheduler')
            ax.set_ylabel('Performance (% of baseline)')
            ax.set_title(f'Linux Kernel Build Performance (Normalized)\n'
                        f'Config: {self.config}, Jobs: {self.jobs}')
            ax.tick_params(axis='x', rotation=45)
            ax.legend()
            
            plt.tight_layout()
            plt.savefig('results/linux_build_normalized_performance.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        # Create speedup plot
        if 'baseline' in self.results:
            fig, ax = plt.subplots(figsize=(12, 8))
            
            baseline_time = self.results['baseline']['avg_build_time']
            speedups = [baseline_time / self.results[s]['avg_build_time'] for s in schedulers]
            
            bars = ax.bar(schedulers, speedups)
            ax.axhline(y=1.0, color='r', linestyle='--', label='No speedup')
            
            # Add value labels
            for bar, speedup in zip(bars, speedups):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{speedup:.2f}x', ha='center', va='bottom')
            
            ax.set_xlabel('Scheduler')
            ax.set_ylabel('Speedup Factor')
            ax.set_title(f'Linux Kernel Build Speedup\n'
                        f'Config: {self.config}, Jobs: {self.jobs}')
            ax.tick_params(axis='x', rotation=45)
            ax.legend()
            
            plt.tight_layout()
            plt.savefig('results/linux_build_speedup.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        print("Performance figures saved to results/ directory")
    
    def generate_summary(self):
        """Generate a text summary of the results"""
        if not self.results:
            return "No results available"
        
        summary = []
        summary.append("Linux Kernel Build Benchmark Results Summary")
        summary.append("=" * 50)
        summary.append(f"Config: {self.config}")
        summary.append(f"Parallel Jobs: {self.jobs}")
        summary.append(f"Runs per scheduler: {self.repeat}")
        summary.append("")
        
        # Sort by average build time
        sorted_results = sorted(self.results.items(), 
                              key=lambda x: x[1]['avg_build_time'])
        
        summary.append("Performance Ranking (by average build time):")
        for rank, (scheduler, result) in enumerate(sorted_results, 1):
            avg_time = result['avg_build_time']
            std_time = result['std_build_time']
            runs = result['runs']
            
            summary.append(f"{rank}. {scheduler}: {avg_time:.1f}s ± {std_time:.1f}s ({runs} runs)")
            
            if 'baseline' in self.results and scheduler != 'baseline':
                speedup = self.results['baseline']['avg_build_time'] / avg_time
                summary.append(f"   Speedup: {speedup:.2f}x")
        
        return "\n".join(summary)