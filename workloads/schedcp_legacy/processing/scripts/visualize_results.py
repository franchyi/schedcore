#!/usr/bin/env python3
"""
Visualization script to create figures comparing scheduler performance.
Reads the JSON results from scheduler tests and creates comparative charts.
"""

import json
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import argparse
import sys

class SchedulerVisualizer:
    def __init__(self):
        self.results = {}
        self.scheduler_names = []
        
    def load_results(self, result_files):
        """Load results from JSON files."""
        for file in result_files:
            if not Path(file).exists():
                print(f"Warning: {file} not found, skipping...")
                continue
                
            with open(file, 'r') as f:
                data = json.load(f)
                
            # Extract scheduler name from filename
            scheduler_name = Path(file).stem.replace('results_', '')
            self.results[scheduler_name] = data
        
        self.scheduler_names = list(self.results.keys())
        print(f"Loaded results for schedulers: {', '.join(self.scheduler_names)}")
    
    def create_comparison_figure(self, output_file="scheduler_comparison.png"):
        """Create a comprehensive comparison figure showing test cases with 3 bars each."""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Scheduler Performance Comparison', fontsize=16, fontweight='bold')
        
        # 1. Wall clock time comparison by test case
        self.plot_test_case_comparison(ax1, 'wall_clock_time', 'Wall Clock Time (seconds)')
        
        # 2. Imbalance ratio by test case
        self.plot_test_case_comparison(ax2, 'imbalance_ratio', 'Imbalance Ratio')
        
        # 3. Parallel efficiency by test case
        self.plot_test_case_comparison(ax3, 'parallel_efficiency', 'Parallel Efficiency')
        
        # 4. Overall summary metrics
        self.plot_summary_metrics(ax4)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Figure saved to {output_file}")
        
    def plot_test_case_comparison(self, ax, metric_name, ylabel):
        """Plot comparison of a specific metric across test cases with 3 bars per case."""
        # Get common test cases across all schedulers
        test_cases = set()
        for scheduler_name in self.scheduler_names:
            if 'results' in self.results[scheduler_name]:
                test_cases.update(self.results[scheduler_name]['results'].keys())
        
        test_cases = sorted(list(test_cases))
        
        if not test_cases:
            ax.text(0.5, 0.5, f'No test case data for {metric_name}', ha='center', va='center')
            ax.set_title(f'{ylabel} by Test Case')
            return
        
        # Color map for schedulers
        color_map = {
            'default': '#808080',  # Gray
            'fifo': '#3498db',     # Blue  
            'ctest': '#e74c3c',    # Red
        }
        
        n_schedulers = len(self.scheduler_names)
        n_tests = len(test_cases)
        bar_width = 0.25
        
        x = np.arange(n_tests)
        
        for i, scheduler_name in enumerate(self.scheduler_names):
            values = []
            for test_case in test_cases:
                value = 0
                if ('results' in self.results[scheduler_name] and 
                    test_case in self.results[scheduler_name]['results'] and
                    'parallel_execution' in self.results[scheduler_name]['results'][test_case]):
                    
                    pe = self.results[scheduler_name]['results'][test_case]['parallel_execution']
                    value = pe.get(metric_name, 0)
                    
                values.append(value)
            
            color = color_map.get(scheduler_name, '#95a5a6')
            bars = ax.bar(x + i * bar_width, values, bar_width, 
                         label=scheduler_name.upper(), color=color, alpha=0.8, 
                         edgecolor='black', linewidth=0.5)
            
            # Add value labels on bars (only if not too crowded)
            if n_tests <= 6:
                for bar, value in zip(bars, values):
                    height = bar.get_height()
                    if height > 0:
                        ax.text(bar.get_x() + bar.get_width()/2., height,
                               f'{value:.2f}' if value < 10 else f'{value:.1f}',
                               ha='center', va='bottom', fontsize=8, rotation=90 if n_tests > 4 else 0)
        
        ax.set_xlabel('Test Cases', fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(f'{ylabel} by Test Case', fontsize=12, fontweight='bold')
        ax.set_xticks(x + bar_width * (n_schedulers - 1) / 2)
        ax.set_xticklabels([case.replace('_', '\n') for case in test_cases], rotation=45, ha='right')
        ax.legend()
        ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    def plot_summary_metrics(self, ax):
        """Plot overall summary metrics comparison."""
        schedulers = []
        avg_imbalance = []
        success_rates = []
        
        for scheduler_name in self.scheduler_names:
            if 'summary' in self.results[scheduler_name]:
                summary = self.results[scheduler_name]['summary']
                schedulers.append(scheduler_name.upper())
                avg_imbalance.append(summary.get('avg_imbalance_ratio', 0))
                success_rates.append(summary.get('success_rate', 0) * 100)  # Convert to percentage
        
        if not schedulers:
            ax.text(0.5, 0.5, 'No summary data available', ha='center', va='center')
            ax.set_title('Summary Metrics')
            return
        
        x = np.arange(len(schedulers))
        width = 0.35
        
        # Create bars for average imbalance ratio
        bars1 = ax.bar(x - width/2, avg_imbalance, width, label='Avg Imbalance Ratio',
                       color='#e74c3c', alpha=0.7)
        
        # Create secondary y-axis for success rate
        ax2 = ax.twinx()
        bars2 = ax2.bar(x + width/2, success_rates, width, label='Success Rate (%)',
                        color='#2ecc71', alpha=0.7)
        
        # Add value labels
        for bar, value in zip(bars1, avg_imbalance):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{value:.2f}', ha='center', va='bottom', fontsize=8)
        
        for bar, value in zip(bars2, success_rates):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{value:.0f}%', ha='center', va='bottom', fontsize=8)
        
        ax.set_xlabel('Schedulers')
        ax.set_ylabel('Average Imbalance Ratio', color='#e74c3c')
        ax2.set_ylabel('Success Rate (%)', color='#2ecc71')
        ax.set_title('Summary Metrics Comparison', fontsize=12, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(schedulers)
        
        # Combine legends
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    
    
    def create_detailed_report(self, output_file="scheduler_report.txt"):
        """Create a detailed text report of the results."""
        with open(output_file, 'w') as f:
            f.write("="*80 + "\n")
            f.write("SCHEDULER PERFORMANCE COMPARISON REPORT\n")
            f.write("="*80 + "\n\n")
            
            # Summary table
            f.write("SUMMARY\n")
            f.write("-"*80 + "\n")
            f.write(f"{'Scheduler':<15} {'Total Tests':<12} {'Success Rate':<12} {'Avg Imbalance':<15} {'Max Imbalance':<15}\n")
            f.write("-"*80 + "\n")
            
            for name in self.scheduler_names:
                if 'summary' in self.results[name]:
                    summary = self.results[name]['summary']
                    total_tests = summary.get('total_tests', 0)
                    success_rate = f"{summary.get('success_rate', 0)*100:.1f}%"
                    avg_imbalance = f"{summary.get('avg_imbalance_ratio', 0):.2f}"
                    max_imbalance = f"{summary.get('max_imbalance_ratio', 0):.2f}"
                    
                    f.write(f"{name:<15} {total_tests:<12} {success_rate:<12} {avg_imbalance:<15} {max_imbalance:<15}\n")
            
            f.write("\n")
            
            # Detailed results for each scheduler
            for name in self.scheduler_names:
                f.write("="*80 + "\n")
                f.write(f"SCHEDULER: {name.upper()}\n")
                f.write("="*80 + "\n")
                
                result = self.results[name]
                
                # Summary info
                if 'summary' in result:
                    summary = result['summary']
                    f.write(f"Total Tests: {summary.get('total_tests', 'N/A')}\n")
                    f.write(f"Successful Tests: {summary.get('successful_tests', 'N/A')}\n")
                    f.write(f"Success Rate: {summary.get('success_rate', 0)*100:.1f}%\n")
                    f.write(f"Average Imbalance Ratio: {summary.get('avg_imbalance_ratio', 'N/A'):.2f}\n")
                    f.write(f"Maximum Imbalance Ratio: {summary.get('max_imbalance_ratio', 'N/A'):.2f}\n")
                
                # Individual test results
                if 'results' in result:
                    f.write("\nTest Case Results:\n")
                    f.write("-"*60 + "\n")
                    
                    for test_name, test_data in result['results'].items():
                        f.write(f"\n  {test_name.upper()}:\n")
                        f.write(f"    Status: {test_data.get('status', 'N/A')}\n")
                        
                        if 'parallel_execution' in test_data:
                            pe = test_data['parallel_execution']
                            f.write(f"    Wall Clock Time: {pe.get('wall_clock_time', 'N/A'):.2f} seconds\n")
                            f.write(f"    Imbalance Ratio: {pe.get('imbalance_ratio', 'N/A'):.2f}\n")
                            f.write(f"    Parallel Efficiency: {pe.get('parallel_efficiency', 'N/A'):.3f}\n")
                
                f.write("\n")
        
        print(f"Detailed report saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Visualize scheduler test results")
    parser.add_argument("--input", nargs='+', 
                       default=["results_ctest.json", "results_fifo.json", "results_default.json",
                               "scheduler_comparison_results.json"],
                       help="Input JSON files (default: all result files)")
    parser.add_argument("--output", default="scheduler_comparison.png",
                       help="Output figure file (default: scheduler_comparison.png)")
    parser.add_argument("--report", action='store_true',
                       help="Generate detailed text report")
    args = parser.parse_args()
    
    visualizer = SchedulerVisualizer()
    
    # Load results
    visualizer.load_results(args.input)
    
    if not visualizer.results:
        print("Error: No valid results loaded")
        sys.exit(1)
    
    # Create visualization
    visualizer.create_comparison_figure(args.output)
    
    # Create text report if requested
    if args.report:
        visualizer.create_detailed_report()

if __name__ == "__main__":
    main()