#!/usr/bin/env python3

import json
import os
import glob
from collections import defaultdict
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_json_results(directory):
    """Load all JSON result files from the specified directory."""
    results = defaultdict(lambda: defaultdict(list))
    json_files = glob.glob(os.path.join(directory, "*.json"))
    
    for file_path in json_files:
        filename = Path(file_path).stem
        if filename == "test_summary_20250731_220223":
            continue
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            test_id = data.get('test_id', '')
            scheduler_type = data.get('scheduler_type', '')
            
            # Extract wall clock time from different possible locations
            wall_time = None
            
            if 'results' in data:
                results_data = data['results']
                
                # Check for direct wall_clock_time field
                if 'wall_clock_time' in results_data:
                    wall_time = results_data['wall_clock_time']
                
                # Check for parallel execution wall clock time
                elif 'parallel_execution' in results_data:
                    parallel_data = results_data['parallel_execution']
                    if 'wall_clock_time' in parallel_data:
                        wall_time = parallel_data['wall_clock_time']
                
                # Check for end_time - start_time
                elif 'end_time' in results_data and 'start_time' in results_data:
                    wall_time = results_data['end_time'] - results_data['start_time']
            
            if wall_time is not None:
                results[test_id][scheduler_type].append(wall_time)
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    return results

def calculate_averages(results):
    """Calculate average wall clock times for each test case and scheduler."""
    averages = defaultdict(dict)
    
    for test_id, schedulers in results.items():
        for scheduler, times in schedulers.items():
            if times:
                avg_time = sum(times) / len(times)
                averages[test_id][scheduler] = avg_time
                print(f"{test_id} - {scheduler}: avg wall clock time = {avg_time:.2f}s")
    
    # Calculate improvement rates
    print("\nImprovement Analysis:")
    print("-" * 50)
    improvements = []
    
    for test_id in sorted(averages.keys()):
        if 'default' in averages[test_id] and 'custom' in averages[test_id]:
            default_time = averages[test_id]['default']
            custom_time = averages[test_id]['custom']
            improvement = ((default_time - custom_time) / default_time) * 100
            improvements.append(improvement)
            print(f"{test_id}: {improvement:.1f}% improvement (default: {default_time:.2f}s → custom: {custom_time:.2f}s)")
    
    if improvements:
        avg_improvement = sum(improvements) / len(improvements)
        print(f"\nAverage improvement rate: {avg_improvement:.1f}%")
    
    return averages

def plot_results(averages):
    """Create a bar chart comparing average wall clock times."""
    test_cases = sorted(averages.keys())
    
    # Set much larger default font size
    plt.rcParams.update({'font.size': 20})
    
    fig, ax = plt.subplots(figsize=(16, 12))
    
    x = np.arange(len(test_cases))
    width = 0.35
    
    default_times = []
    custom_times = []
    
    for test in test_cases:
        default_times.append(averages[test].get('default', 0))
        custom_times.append(averages[test].get('custom', 0))
    
    # Use light blue and light orange colors
    bars1 = ax.bar(x - width/2, default_times, width, label='Default Scheduler', color='lightblue')
    bars2 = ax.bar(x + width/2, custom_times, width, label='Custom Scheduler', color='lightsalmon')
    
    ax.set_xlabel('Test Cases', fontsize=30)
    ax.set_ylabel('Average Wall Clock Time (seconds)', fontsize=30)
    # Remove title
    ax.set_xticks(x)
    ax.set_xticklabels(test_cases, rotation=45, ha='right', fontsize=26)
    ax.legend(fontsize=28)
    
    # Set tick label font size
    ax.tick_params(axis='y', labelsize=26)
    
    # Add value labels on bars
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            if height > 0:
                ax.annotate(f'{height:.1f}',
                          xy=(rect.get_x() + rect.get_width() / 2, height),
                          xytext=(0, 3),
                          textcoords="offset points",
                          ha='center', va='bottom',
                          fontsize=22,
                          fontweight='bold')
    
    autolabel(bars1)
    autolabel(bars2)
    
    plt.tight_layout()
    plt.savefig(f'{BASE_DIR}/scheduler_performance_comparison.pdf', dpi=300, format='pdf')
    plt.close()

def main():
    results_dir = f'{BASE_DIR}/scheduler_test_results'
    print("Loading scheduler test results...")
    results = load_json_results(results_dir)
    
    print("\nCalculating average wall clock times:")
    print("-" * 50)
    averages = calculate_averages(results)
    
    print("\nGenerating comparison chart...")
    plot_results(averages)
    
    print("\nAnalysis complete. Chart saved to: scheduler_performance_comparison.pdf")

if __name__ == "__main__":
    main()