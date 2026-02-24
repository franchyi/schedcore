#!/usr/bin/env python3
"""
Plot Total Bandwidth vs Read Ratio for different NUMA interleave configurations
Compares performance across numactl interleave=0, 2, and 3
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# Set style for better-looking plots
plt.style.use('seaborn-v0_8-darkgrid')

def load_and_filter_data(csv_file, buffer_size_gb=64.0):
    """Load CSV and filter for specific buffer size"""
    df = pd.read_csv(csv_file)
    # Filter for 64GB buffer size
    df_filtered = df[df['buffer_size_gb'] == buffer_size_gb].copy()
    return df_filtered

def plot_bandwidth_vs_datasize():
    """Create comparison plots for different data sizes with fixed thread count"""
    
    # Define file paths and labels
    numa_configs = [
        {'file': 'cxl_perf_parameter_sweep_numactl0.csv', 'label': 'NUMA Node 0 (DDR5) random', 'interleave': '0'},
        {'file': 'cxl_perf_parameter_sweep_numactl0_seq.csv', 'label': 'NUMA Node 0 (DDR5) sequential', 'interleave': '0_seq'},
        {'file': 'cxl_perf_parameter_sweep_numactl2.csv', 'label': 'NUMA Node 2 (CXL 256GB) random', 'interleave': '2'},
        {'file': 'cxl_perf_parameter_sweep_numactl2_seq.csv', 'label': 'NUMA Node 2 (CXL 256GB) sequential', 'interleave': '2_seq'},
        {'file': 'cxl_perf_parameter_sweep_numactl3.csv', 'label': 'NUMA Node 3 (CXL 512GB) random', 'interleave': '3'},
        {'file': 'cxl_perf_parameter_sweep_numactl3_seq.csv', 'label': 'NUMA Node 3 (CXL 512GB) sequential', 'interleave': '3_seq'},
    ]
    
    # Create figure with subplots (6 configs now in one row)
    fig, axes = plt.subplots(1, 6, figsize=(36, 6))
    fig.suptitle('Total Bandwidth vs Read Ratio (Thread Count = 172)', fontsize=20, fontweight='bold')
    
    # Color palette for different data sizes
    colors = plt.cm.viridis(np.linspace(0, 1, 10))
    markers = ['o', 's', '^', 'D', 'v', '<', '>', 'p', '*', 'h']
    
    for idx, config in enumerate(numa_configs):
        ax = axes[idx]
        
        # Check if file exists
        if not os.path.exists(config['file']):
            print(f"Warning: File {config['file']} not found, skipping...")
            ax.text(0.5, 0.5, f"Data file not found:\n{config['file']}", 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title(f"numactl interleave={config['interleave']}")
            continue
        
        # Load all data
        df = pd.read_csv(config['file'])
        # Filter for thread count = 172
        df_filtered = df[df['threads'] == 172].copy()
        
        if df_filtered.empty:
            print(f"Warning: No data for threads=172 in {config['file']}")
            ax.text(0.5, 0.5, f"No data for 172 threads", 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title(f"numactl interleave={config['interleave']}")
            continue
        
        # Get unique data sizes (1 to 64 GB)
        data_sizes = sorted(df_filtered['buffer_size_gb'].unique())
        data_sizes = [size for size in data_sizes if 1 <= size <= 64]
        
        # Plot each data size as a separate line
        for i, size in enumerate(data_sizes):
            df_size = df_filtered[df_filtered['buffer_size_gb'] == size].sort_values('read_ratio')
            
            # Use app_total_bandwidth_mbps if available, otherwise fall back
            bandwidth_col = 'app_total_bandwidth_mbps'
            if bandwidth_col not in df_size.columns:
                # Try alternative column names
                if 'bandwidth_mbps' in df_size.columns:
                    bandwidth_col = 'bandwidth_mbps'
                elif 'total_bandwidth_mbps' in df_size.columns:
                    bandwidth_col = 'total_bandwidth_mbps'
                else:
                    print(f"Warning: No bandwidth column found in {config['file']}")
                    continue
            
            ax.plot(df_size['read_ratio'], 
                   df_size[bandwidth_col],
                   marker=markers[i % len(markers)],
                   color=colors[i % len(colors)],
                   linewidth=2,
                   markersize=8,
                   label=f'{size:.0f} GB',
                   alpha=0.8)
        
        # Customize subplot
        ax.set_xlabel('Read Ratio', fontsize=16)
        ax.set_ylabel('Total Bandwidth (MB/s)', fontsize=16)
        ax.set_title(f"{config['label']}\n(numactl interleave={config['interleave']})", fontsize=16)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(bottom=0)
        ax.tick_params(axis='both', which='major', labelsize=14)
        
        # Add minor gridlines
        ax.minorticks_on()
        ax.grid(which='minor', alpha=0.1)
    
    # Add a single legend for all subplots
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, -0.05), 
               ncol=5, fontsize=14, title_fontsize=14)
    
    plt.tight_layout()
    
    # Save figure
    output_file = 'bandwidth_vs_read_ratio_datasize_comparison.pdf'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Figure saved as {output_file}")

def plot_bandwidth_comparison():
    """Create comparison plots for different NUMA configurations"""
    
    # Define file paths and labels
    numa_configs = [
        {'file': 'cxl_perf_parameter_sweep_numactl0.csv', 'label': 'NUMA Node 0 (DDR5) random', 'interleave': '0'},
        {'file': 'cxl_perf_parameter_sweep_numactl0_seq.csv', 'label': 'NUMA Node 0 (DDR5) sequential', 'interleave': '0_seq'},
        {'file': 'cxl_perf_parameter_sweep_numactl2.csv', 'label': 'NUMA Node 2 (CXL 256GB) random', 'interleave': '2'},
        {'file': 'cxl_perf_parameter_sweep_numactl2_seq.csv', 'label': 'NUMA Node 2 (CXL 256GB) sequential', 'interleave': '2_seq'},
        {'file': 'cxl_perf_parameter_sweep_numactl3.csv', 'label': 'NUMA Node 3 (CXL 512GB) random', 'interleave': '3'},
        {'file': 'cxl_perf_parameter_sweep_numactl3_seq.csv', 'label': 'NUMA Node 3 (CXL 512GB) sequential', 'interleave': '3_seq'}
    ]
    
    # Create figure with subplots (6 configs now in one row)
    fig, axes = plt.subplots(1, 6, figsize=(36, 6))
    fig.suptitle('Total Bandwidth vs Read Ratio (Buffer Size = 64GB)', fontsize=20, fontweight='bold')
    
    # Color palette for different thread counts
    colors = plt.cm.tab10(np.linspace(0, 0.8, 10))
    markers = ['o', 's', '^', 'D', 'v', '<', '>', 'p', '*', 'h']
    
    for idx, config in enumerate(numa_configs):
        ax = axes[idx]
        
        # Check if file exists
        if not os.path.exists(config['file']):
            print(f"Warning: File {config['file']} not found, skipping...")
            ax.text(0.5, 0.5, f"Data file not found:\n{config['file']}", 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title(f"numactl interleave={config['interleave']}")
            continue
        
        # Load data
        df = load_and_filter_data(config['file'])
        
        if df.empty:
            print(f"Warning: No data for buffer_size_gb=64.0 in {config['file']}")
            ax.text(0.5, 0.5, f"No data for 64GB buffer", 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title(f"numactl interleave={config['interleave']}")
            continue
        
        # Get unique thread counts
        thread_counts = sorted(df['threads'].unique())
        
        # Plot each thread count as a separate line
        for i, threads in enumerate(thread_counts):
            df_thread = df[df['threads'] == threads].sort_values('read_ratio')
            
            # Use app_total_bandwidth_mbps if available, otherwise fall back
            bandwidth_col = 'app_total_bandwidth_mbps'
            if bandwidth_col not in df_thread.columns:
                # Try alternative column names
                if 'bandwidth_mbps' in df_thread.columns:
                    bandwidth_col = 'bandwidth_mbps'
                elif 'total_bandwidth_mbps' in df_thread.columns:
                    bandwidth_col = 'total_bandwidth_mbps'
                else:
                    print(f"Warning: No bandwidth column found in {config['file']}")
                    continue
            
            ax.plot(df_thread['read_ratio'], 
                   df_thread[bandwidth_col],
                   marker=markers[i % len(markers)],
                   color=colors[i % len(colors)],
                   linewidth=2,
                   markersize=8,
                   label=f'{threads} threads',
                   alpha=0.8)
        
        # Customize subplot
        ax.set_xlabel('Read Ratio', fontsize=16)
        ax.set_ylabel('Total Bandwidth (MB/s)', fontsize=16)
        ax.set_title(f"{config['label']}\n(numactl interleave={config['interleave']})", fontsize=16)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(bottom=0)
        ax.tick_params(axis='both', which='major', labelsize=14)
        
        # Add minor gridlines
        ax.minorticks_on()
        ax.grid(which='minor', alpha=0.1)
    
    # Add a single legend for all subplots
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, -0.05), 
               ncol=5, fontsize=14, title_fontsize=14)
    
    plt.tight_layout()
    
    # Save figure
    output_file = 'bandwidth_vs_read_ratio_comparison.pdf'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Figure saved as {output_file}")
    
    # Also create a combined plot with all configurations on one graph
    create_combined_plot(numa_configs)
    
    plt.show()

def create_combined_plot(numa_configs):
    """Create a single plot with all NUMA configurations overlaid"""
    
    fig, ax = plt.subplots(figsize=(12, 8))
    fig.suptitle('Total Bandwidth Comparison Across NUMA Configurations\n(Buffer Size = 64GB, Threads = 172)', 
                 fontsize=20, fontweight='bold')
    
    # Use different line styles for different NUMA configs
    line_styles = ['-', '--', '-.', ':', '-', '--']
    # Use different colors for each config
    colors = ['blue', 'cyan', 'red', 'orange', 'green', 'purple']
    markers = ['o', 's', '^', 'D', 'v', 'p']
    
    for config_idx, config in enumerate(numa_configs):
        if not os.path.exists(config['file']):
            continue
        
        df = load_and_filter_data(config['file'])
        if df.empty:
            continue
        
        # Filter for thread count = 172 only
        df_thread = df[df['threads'] == 172].sort_values('read_ratio')
        
        if df_thread.empty:
            print(f"Warning: No data for 172 threads in {config['file']}")
            continue
        
        # Determine bandwidth column
        bandwidth_col = 'app_total_bandwidth_mbps'
        if bandwidth_col not in df_thread.columns:
            if 'bandwidth_mbps' in df_thread.columns:
                bandwidth_col = 'bandwidth_mbps'
            elif 'total_bandwidth_mbps' in df_thread.columns:
                bandwidth_col = 'total_bandwidth_mbps'
            else:
                continue
        
        label = f"Node {config['interleave']} ({config['label'].split('(')[1].split(')')[0]})"
        ax.plot(df_thread['read_ratio'], 
               df_thread[bandwidth_col],
               linestyle=line_styles[config_idx % len(line_styles)],
               marker=markers[config_idx % len(markers)],
               color=colors[config_idx % len(colors)],
               linewidth=2,
               markersize=8,
               label=label,
               alpha=0.8)
    
    ax.set_xlabel('Read Ratio', fontsize=18)
    ax.set_ylabel('Total Bandwidth (MB/s)', fontsize=18)
    ax.grid(True, alpha=0.3)
    ax.minorticks_on()
    ax.grid(which='minor', alpha=0.1)
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(bottom=0)
    ax.tick_params(axis='both', which='major', labelsize=16)
    
    # Position legend outside the plot
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=14, ncol=1)
    
    plt.tight_layout()
    
    # Save combined figure
    output_file = 'bandwidth_vs_read_ratio_combined.pdf'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Combined figure saved as {output_file}")

def print_summary_statistics():
    """Print summary statistics for each configuration"""
    
    numa_configs = [
        {'file': 'cxl_perf_parameter_sweep_numactl0.csv', 'label': 'NUMA Node 0 (DDR5) random', 'interleave': '0'},
        {'file': 'cxl_perf_parameter_sweep_numactl0_seq.csv', 'label': 'NUMA Node 0 (DDR5) sequential', 'interleave': '0_seq'},
        {'file': 'cxl_perf_parameter_sweep_numactl2.csv', 'label': 'NUMA Node 2 (CXL 256GB) random', 'interleave': '2'},
        {'file': 'cxl_perf_parameter_sweep_numactl2_seq.csv', 'label': 'NUMA Node 2 (CXL 256GB) sequential', 'interleave': '2_seq'},
        {'file': 'cxl_perf_parameter_sweep_numactl3.csv', 'label': 'NUMA Node 3 (CXL 512GB) random', 'interleave': '3'},
        {'file': 'cxl_perf_parameter_sweep_numactl3_seq.csv', 'label': 'NUMA Node 3 (CXL 512GB) sequential', 'interleave': '3_seq'}
    ]
    
    # First print thread scaling analysis
    print("\n" + "="*80)
    print("THREAD SCALING ANALYSIS (64GB Buffer)")
    print("="*80)
    
    for config in numa_configs:
        if not os.path.exists(config['file']):
            continue
        
        # Load full data
        df = pd.read_csv(config['file'])
        # Filter for 64GB buffer
        df_filtered = df[df['buffer_size_gb'] == 64.0].copy()
        
        if df_filtered.empty:
            print(f"\n{config['label']}: No data for 64GB buffer")
            continue
        
        print(f"\n{config['label']} (interleave={config['interleave']})")
        print("-" * 50)
        
        # Use appropriate bandwidth column
        bandwidth_col = 'app_total_bandwidth_mbps'
        if bandwidth_col not in df_filtered.columns:
            if 'bandwidth_mbps' in df_filtered.columns:
                bandwidth_col = 'bandwidth_mbps'
            elif 'total_bandwidth_mbps' in df_filtered.columns:
                bandwidth_col = 'total_bandwidth_mbps'
            else:
                continue
        
        # Get unique thread counts
        thread_counts = sorted(df_filtered['threads'].unique())
        print(f"  Thread counts tested: {thread_counts}")
        
        # Analyze bandwidth scaling with threads
        for threads in thread_counts:
            df_thread = df_filtered[df_filtered['threads'] == threads]
            avg_bw = df_thread[bandwidth_col].mean()
            max_bw = df_thread[bandwidth_col].max()
            
            # Find optimal read ratio for this thread count
            optimal_row = df_thread.loc[df_thread[bandwidth_col].idxmax()]
            optimal_ratio = optimal_row['read_ratio']
            
            print(f"  {threads:3d} threads: Avg={avg_bw:8.1f} MB/s, Max={max_bw:8.1f} MB/s @ read_ratio={optimal_ratio:.2f}")
        
        # Calculate scaling efficiency
        if len(thread_counts) > 1:
            base_threads = thread_counts[0]
            base_max = df_filtered[df_filtered['threads'] == base_threads][bandwidth_col].max()
            
            print(f"\n  Scaling Efficiency (relative to {base_threads} threads):")
            for threads in thread_counts[1:]:
                thread_max = df_filtered[df_filtered['threads'] == threads][bandwidth_col].max()
                scaling_factor = threads / base_threads
                ideal_bw = base_max * scaling_factor
                efficiency = (thread_max / ideal_bw) * 100 if ideal_bw > 0 else 0
                print(f"    {threads:3d} threads: {efficiency:.1f}% efficiency (actual: {thread_max:.1f} MB/s, ideal: {ideal_bw:.1f} MB/s)")
        
        # Find saturation point (where adding threads doesn't improve bandwidth significantly)
        if len(thread_counts) > 2:
            max_bws = []
            for threads in thread_counts:
                df_thread = df_filtered[df_filtered['threads'] == threads]
                max_bws.append(df_thread[bandwidth_col].max())
            
            # Find where bandwidth increase is less than 5%
            saturation_point = None
            for i in range(1, len(max_bws)):
                if i > 0:
                    improvement = ((max_bws[i] - max_bws[i-1]) / max_bws[i-1]) * 100
                    if improvement < 5:
                        saturation_point = thread_counts[i-1]
                        break
            
            if saturation_point:
                print(f"  Bandwidth saturation point: ~{saturation_point} threads")
            else:
                print(f"  Bandwidth continues to scale beyond {thread_counts[-1]} threads")
    
    # Print detailed statistics for 172 threads, 64GB
    print("\n" + "="*80)
    print("DETAILED STATISTICS (172 Threads, 64GB Buffer)")
    print("="*80)
    
    for config in numa_configs:
        if not os.path.exists(config['file']):
            continue
        
        # Load full data
        df = pd.read_csv(config['file'])
        # Filter for 172 threads and 64GB
        df_filtered = df[(df['threads'] == 172) & (df['buffer_size_gb'] == 64.0)].copy()
        
        if df_filtered.empty:
            print(f"\n{config['label']}: No data for 172 threads with 64GB buffer")
            continue
        
        print(f"\n{config['label']} (interleave={config['interleave']})")
        print("-" * 50)
        
        # Use appropriate bandwidth column
        bandwidth_col = 'app_total_bandwidth_mbps'
        if bandwidth_col not in df_filtered.columns:
            if 'bandwidth_mbps' in df_filtered.columns:
                bandwidth_col = 'bandwidth_mbps'
            elif 'total_bandwidth_mbps' in df_filtered.columns:
                bandwidth_col = 'total_bandwidth_mbps'
            else:
                continue
        
        # Calculate statistics
        avg_bandwidth = df_filtered[bandwidth_col].mean()
        max_bandwidth = df_filtered[bandwidth_col].max()
        
        # Get bandwidth at specific read ratios
        read_0 = df_filtered[df_filtered['read_ratio'] == 0.0]
        read_1 = df_filtered[df_filtered['read_ratio'] == 1.0]
        
        print(f"  Average Bandwidth: {avg_bandwidth:.2f} MB/s")
        print(f"  Max Bandwidth: {max_bandwidth:.2f} MB/s")
        
        if not read_0.empty:
            print(f"  Read Ratio 0.0 (100% Write): {read_0[bandwidth_col].iloc[0]:.2f} MB/s")
        else:
            print(f"  Read Ratio 0.0 (100% Write): No data")
            
        if not read_1.empty:
            print(f"  Read Ratio 1.0 (100% Read): {read_1[bandwidth_col].iloc[0]:.2f} MB/s")
        else:
            print(f"  Read Ratio 1.0 (100% Read): No data")
        
        # Find optimal read ratio
        optimal_row = df_filtered.loc[df_filtered[bandwidth_col].idxmax()]
        print(f"  Optimal Read Ratio: {optimal_row['read_ratio']:.2f} "
              f"(Bandwidth: {optimal_row[bandwidth_col]:.2f} MB/s)")
        
        # Calculate write vs read performance ratio
        if not read_0.empty and not read_1.empty:
            write_bw = read_0[bandwidth_col].iloc[0]
            read_bw = read_1[bandwidth_col].iloc[0]
            if read_bw > 0:
                ratio = write_bw / read_bw
                print(f"  Write/Read Ratio: {ratio:.2f} (Write is {ratio:.1f}x of Read)")
        
        # Show bandwidth range and improvement
        min_bw = df_filtered[bandwidth_col].min()
        print(f"  Bandwidth Range: {min_bw:.2f} - {max_bandwidth:.2f} MB/s")
        
        # Calculate percentage improvements from minimum
        if min_bw > 0:
            max_improvement = ((max_bandwidth - min_bw) / min_bw) * 100
            avg_improvement = ((avg_bandwidth - min_bw) / min_bw) * 100
            print(f"  Max Improvement from Min: {max_improvement:.1f}%")
            print(f"  Avg Improvement from Min: {avg_improvement:.1f}%")
            
            # Show improvement at specific read ratios if they exist
            if not read_0.empty:
                write_improvement = ((read_0[bandwidth_col].iloc[0] - min_bw) / min_bw) * 100
                print(f"  100% Write Improvement from Min: {write_improvement:.1f}%")
            if not read_1.empty:
                read_improvement = ((read_1[bandwidth_col].iloc[0] - min_bw) / min_bw) * 100
                print(f"  100% Read Improvement from Min: {read_improvement:.1f}%")
    
    # Print detailed statistics for 172 threads, 1GB
    print("\n" + "="*80)
    print("DETAILED STATISTICS (172 Threads, 1GB Buffer)")
    print("="*80)
    
    for config in numa_configs:
        if not os.path.exists(config['file']):
            continue
        
        # Load full data
        df = pd.read_csv(config['file'])
        # Filter for 172 threads and 1GB
        df_filtered = df[(df['threads'] == 172) & (df['buffer_size_gb'] == 1.0)].copy()
        
        if df_filtered.empty:
            print(f"\n{config['label']}: No data for 172 threads with 1GB buffer")
            continue
        
        print(f"\n{config['label']} (interleave={config['interleave']})")
        print("-" * 50)
        
        # Use appropriate bandwidth column
        bandwidth_col = 'app_total_bandwidth_mbps'
        if bandwidth_col not in df_filtered.columns:
            if 'bandwidth_mbps' in df_filtered.columns:
                bandwidth_col = 'bandwidth_mbps'
            elif 'total_bandwidth_mbps' in df_filtered.columns:
                bandwidth_col = 'total_bandwidth_mbps'
            else:
                continue
        
        # Calculate statistics
        avg_bandwidth = df_filtered[bandwidth_col].mean()
        max_bandwidth = df_filtered[bandwidth_col].max()
        
        # Get bandwidth at specific read ratios
        read_0 = df_filtered[df_filtered['read_ratio'] == 0.0]
        read_1 = df_filtered[df_filtered['read_ratio'] == 1.0]
        
        print(f"  Average Bandwidth: {avg_bandwidth:.2f} MB/s")
        print(f"  Max Bandwidth: {max_bandwidth:.2f} MB/s")
        
        if not read_0.empty:
            print(f"  Read Ratio 0.0 (100% Write): {read_0[bandwidth_col].iloc[0]:.2f} MB/s")
        else:
            print(f"  Read Ratio 0.0 (100% Write): No data")
            
        if not read_1.empty:
            print(f"  Read Ratio 1.0 (100% Read): {read_1[bandwidth_col].iloc[0]:.2f} MB/s")
        else:
            print(f"  Read Ratio 1.0 (100% Read): No data")
        
        # Find optimal read ratio
        optimal_row = df_filtered.loc[df_filtered[bandwidth_col].idxmax()]
        print(f"  Optimal Read Ratio: {optimal_row['read_ratio']:.2f} "
              f"(Bandwidth: {optimal_row[bandwidth_col]:.2f} MB/s)")
        
        # Calculate write vs read performance ratio
        if not read_0.empty and not read_1.empty:
            write_bw = read_0[bandwidth_col].iloc[0]
            read_bw = read_1[bandwidth_col].iloc[0]
            if read_bw > 0:
                ratio = write_bw / read_bw
                print(f"  Write/Read Ratio: {ratio:.2f} (Write is {ratio:.1f}x of Read)")
        
        # Show bandwidth range and improvement
        min_bw = df_filtered[bandwidth_col].min()
        print(f"  Bandwidth Range: {min_bw:.2f} - {max_bandwidth:.2f} MB/s")
        
        # Calculate percentage improvements from minimum
        if min_bw > 0:
            max_improvement = ((max_bandwidth - min_bw) / min_bw) * 100
            avg_improvement = ((avg_bandwidth - min_bw) / min_bw) * 100
            print(f"  Max Improvement from Min: {max_improvement:.1f}%")
            print(f"  Avg Improvement from Min: {avg_improvement:.1f}%")
            
            # Show improvement at specific read ratios if they exist
            if not read_0.empty:
                write_improvement = ((read_0[bandwidth_col].iloc[0] - min_bw) / min_bw) * 100
                print(f"  100% Write Improvement from Min: {write_improvement:.1f}%")
            if not read_1.empty:
                read_improvement = ((read_1[bandwidth_col].iloc[0] - min_bw) / min_bw) * 100
                print(f"  100% Read Improvement from Min: {read_improvement:.1f}%")

def plot_numactl_interleave_comparison():
    """Create comparison plots for numactl interleave 0,1 and 2,3 configurations (fixed buffer size)"""
    
    # File paths for the two configurations
    configs = [
        {'file': 'cxl_perf_parameter_sweep_numactl01.csv', 'label': 'Interleave 0,1', 'title': 'NUMA Interleave 0,1'},
        {'file': 'cxl_perf_parameter_sweep_numactl23.csv', 'label': 'Interleave 2,3', 'title': 'NUMA Interleave 2,3'}
    ]
    
    # Check if files exist
    for config in configs:
        if not os.path.exists(config['file']):
            print(f"Warning: File {config['file']} not found")
            return
    
    # Create figure with two subplots
    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    fig.suptitle('Random Access Total Bandwidth vs Read Ratio (Buffer Size = 64GB)', fontsize=20, fontweight='bold')
    
    # Color palette for different thread counts
    colors = plt.cm.tab10(np.linspace(0, 0.8, 10))
    markers = ['o', 's', '^', 'D', 'v', '<', '>', 'p', '*', 'h']
    
    for idx, config in enumerate(configs):
        ax = axes[idx]
        
        # Load data
        df = pd.read_csv(config['file'])
        # Filter for 64GB buffer
        df_64gb = df[df['buffer_size_gb'] == 64.0].copy()
        
        if not df_64gb.empty:
            thread_counts = sorted(df_64gb['threads'].unique())
            
            for i, threads in enumerate(thread_counts):
                df_thread = df_64gb[df_64gb['threads'] == threads].sort_values('read_ratio')
                ax.plot(df_thread['read_ratio'], 
                       df_thread['app_total_bandwidth_mbps'],
                       marker=markers[i % len(markers)],
                       color=colors[i % len(colors)],
                       linewidth=2,
                       markersize=8,
                       label=f'{threads} threads',
                       alpha=0.8)
            
            ax.set_xlabel('Read Ratio', fontsize=14)
            ax.set_ylabel('Total Bandwidth (MB/s)', fontsize=14)
            ax.set_title(config['title'], fontsize=16)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='best', fontsize=10)
            ax.set_xlim(-0.05, 1.05)
            ax.set_ylim(bottom=0)
            ax.minorticks_on()
            ax.grid(which='minor', alpha=0.1)
        else:
            ax.text(0.5, 0.5, f"No data for 64GB buffer size\nin {config['file']}", 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title(config['title'], fontsize=16)
    
    plt.tight_layout()
    
    # Save figure
    output_file = 'numa_interleave_01_vs_23_fixed_64gb_buffer.pdf'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Figure saved as {output_file}")

def plot_numactl_interleave_detailed():
    """Create detailed comparison plots for numactl interleave 0,1 and 2,3 configurations (fixed thread count)"""
    
    # File paths for the two configurations
    configs = [
        {'file': 'cxl_perf_parameter_sweep_numactl01.csv', 'label': 'Interleave 0,1', 'title': 'NUMA Interleave 0,1'},
        {'file': 'cxl_perf_parameter_sweep_numactl23.csv', 'label': 'Interleave 2,3', 'title': 'NUMA Interleave 2,3'}
    ]
    
    # Check if files exist
    for config in configs:
        if not os.path.exists(config['file']):
            print(f"Warning: File {config['file']} not found")
            return
    
    # Create figure with two subplots
    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    fig.suptitle('Random Access Total Bandwidth vs Read Ratio (Thread Count = 172)', fontsize=20, fontweight='bold')
    
    # Color palette for different buffer sizes
    colors = plt.cm.viridis(np.linspace(0, 1, 10))
    markers = ['o', 's', '^', 'D', 'v', '<', '>', 'p', '*', 'h']
    
    for idx, config in enumerate(configs):
        ax = axes[idx]
        
        # Load data
        df = pd.read_csv(config['file'])
        # Filter for 172 threads
        df_172t = df[df['threads'] == 172].copy()
        
        if not df_172t.empty:
            buffer_sizes = sorted(df_172t['buffer_size_gb'].unique())
            buffer_sizes = [size for size in buffer_sizes if 1 <= size <= 64]
            
            for i, size in enumerate(buffer_sizes):
                df_size = df_172t[df_172t['buffer_size_gb'] == size].sort_values('read_ratio')
                ax.plot(df_size['read_ratio'], 
                       df_size['app_total_bandwidth_mbps'],
                       marker=markers[i % len(markers)],
                       color=colors[i % len(colors)],
                       linewidth=2,
                       markersize=8,
                       label=f'{size:.0f} GB',
                       alpha=0.8)
            
            ax.set_xlabel('Read Ratio', fontsize=14)
            ax.set_ylabel('Total Bandwidth (MB/s)', fontsize=14)
            ax.set_title(config['title'], fontsize=16)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='best', fontsize=10, ncol=2)
            ax.set_xlim(-0.05, 1.05)
            ax.set_ylim(bottom=0)
            ax.minorticks_on()
            ax.grid(which='minor', alpha=0.1)
        else:
            ax.text(0.5, 0.5, f"No data for 172 threads\nin {config['file']}", 
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title(config['title'], fontsize=16)
    
    plt.tight_layout()
    
    # Save figure
    output_file = 'numa_interleave_01_vs_23_fixed_172_threads.pdf'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Figure saved as {output_file}")

if __name__ == "__main__":
    # Change to the numa_results directory
    os.chdir('/root/yunwei37/ai-os/workloads/cxl-micro/numa_results')
    
    # Print summary statistics
    print_summary_statistics()
    
    # Create plots with fixed buffer size (64GB) and varying thread counts
    plot_bandwidth_comparison()
    
    # Create plots with fixed thread count (172) and varying data sizes
    plot_bandwidth_vs_datasize()
    
    # Create interleave comparison plots
    plot_numactl_interleave_comparison()
    plot_numactl_interleave_detailed()
    
    print("\nAll plots have been generated successfully!")