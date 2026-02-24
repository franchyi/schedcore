#!/usr/bin/env python3
import matplotlib.pyplot as plt
import numpy as np
import json

def load_json_data(filename):
    with open(filename, 'r') as f:
        return json.load(f)

def parse_scheduler_name(filename):
    if 'default.json' in filename:
        return 'Default Linux'
    elif 'scx_bpfland_aggressive.json' in filename:
        return 'First Attempt'
    elif 'scx_rusty_lowlat.json' in filename:
        return 'Iter 3 times'
    return filename

def create_grouped_bar_chart():
    json_files = [
        'default.json',
        'scx_bpfland_aggressive.json',
        'scx_rusty_lowlat.json'
    ]
    
    schedulers = []
    throughputs = []
    p99_latencies = []
    
    for json_file in json_files:
        data = load_json_data(json_file)
        scheduler_name = parse_scheduler_name(json_file)
        schedulers.append(scheduler_name)
        throughputs.append(data['averages']['throughput'])
        p99_latencies.append(data['averages']['99th_percentile_us'])  # Keep in microseconds
    
    # Create figure with less height (matching Linux build benchmark style)
    fig, ax = plt.subplots(figsize=(16, 4))
    
    # Create horizontal bars for throughput
    y = np.arange(len(schedulers))
    width = 0.35
    
    # Use the same colors as in Linux build benchmark
    bars1 = ax.barh(y - width/2, throughputs, width, label='Throughput (req/s)', 
                    color='#1f77b4', alpha=0.8)
    bars2 = ax.barh(y + width/2, [lat/1000 for lat in p99_latencies], width, 
                    label='P99 Latency (ms)', color='#ff7f0e', alpha=0.8)
    
    # Customize the plot with even bigger text, no title
    ax.set_ylabel('Scheduler', fontsize=26, fontweight='bold')
    ax.set_xlabel('Throughput (req/s) / P99 Latency (ms)', fontsize=26, fontweight='bold')
    ax.set_yticks(y)
    ax.set_yticklabels(schedulers, fontsize=24)
    ax.tick_params(axis='x', labelsize=22)
    
    # No grid for cleaner look
    ax.grid(False)
    
    # Add value labels and improvement relative to baseline
    baseline_throughput = throughputs[0]
    baseline_latency = p99_latencies[0]
    
    for i, (bar1, bar2, throughput, latency) in enumerate(zip(bars1, bars2, throughputs, p99_latencies)):
        # Throughput bar
        bar1_width = bar1.get_width()
        if i == 0:  # Baseline
            ax.text(bar1_width + 10, bar1.get_y() + bar1.get_height()/2.,
                    f'{throughput:.0f} req/s', ha='left', va='center', fontsize=24, fontweight='bold')
        else:  # With improvement
            throughput_improvement = throughput / baseline_throughput
            ax.text(bar1_width + 10, bar1.get_y() + bar1.get_height()/2.,
                    f'{throughput:.0f} req/s ({throughput_improvement:.2f}×)', 
                    ha='left', va='center', fontsize=24, fontweight='bold')
        
        # Latency bar
        bar2_width = bar2.get_width()
        if i == 0:  # Baseline
            ax.text(bar2_width + 0.5, bar2.get_y() + bar2.get_height()/2.,
                    f'{latency/1000:.1f} ms', ha='left', va='center', fontsize=24, fontweight='bold')
        else:  # With improvement
            latency_improvement = baseline_latency / latency
            ax.text(bar2_width + 0.5, bar2.get_y() + bar2.get_height()/2.,
                    f'{latency/1000:.1f} ms ({latency_improvement:.2f}×)', 
                    ha='left', va='center', fontsize=24, fontweight='bold')
    
    # Legend
    ax.legend(loc='lower right', fontsize=20, framealpha=0.9)
    
    # Adjust x-axis limits to accommodate all text
    ax.set_xlim(0, max(max(throughputs), max([lat/1000 for lat in p99_latencies])) * 1.3)
    
    plt.tight_layout()
    plt.savefig('schbench_performance_comparison.pdf', format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig('schbench_performance_comparison.png', dpi=300, bbox_inches='tight')

if __name__ == "__main__":
    print("Schbench Performance Summary:")
    print("-" * 60)
    
    json_files = [
        'default.json',
        'scx_bpfland_aggressive.json',
        'scx_rusty_lowlat.json'
    ]
    
    for json_file in json_files:
        data = load_json_data(json_file)
        scheduler_name = parse_scheduler_name(json_file)
        throughput = data['averages']['throughput']
        p99_latency = data['averages']['99th_percentile_us'] / 1000
        print(f"{scheduler_name:25} - Throughput: {throughput:7.1f} req/s, P99 Latency: {p99_latency:5.1f} ms")
    
    create_grouped_bar_chart()