#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import math

# Set style for better-looking plots
plt.style.use('seaborn-v0_8-darkgrid')

# Function to create comparison plots
def create_comparison_figure(df, access_type, output_file):
    # Get default scheduler data
    default_data = df[df['scheduler'] == 'default'].copy()
    default_data = default_data.sort_values('read_ratio')
    
    # Calculate number of subplots needed
    n_schedulers = len(schedulers)
    n_cols = 4  # 4 columns
    n_rows = math.ceil(n_schedulers / n_cols)
    
    # Create figure with subplots
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(20, n_rows * 4))
    
    # Flatten axes array for easier iteration
    if n_rows == 1:
        axes = axes.reshape(1, -1)
    axes = axes.flatten()
    
    # Plot each scheduler comparison
    for idx, scheduler in enumerate(schedulers):
        ax = axes[idx]
        
        # Get scheduler data
        scheduler_data = df[df['scheduler'] == scheduler].copy()
        scheduler_data = scheduler_data.sort_values('read_ratio')
        
        # Convert read_ratio to percentage
        x_default = default_data['read_ratio'] * 100
        x_scheduler = scheduler_data['read_ratio'] * 100
        
        # Plot lines
        ax.plot(x_default, default_data['bandwidth_mbps'], 'o-', 
                label='default', linewidth=2, markersize=8, color='tab:blue')
        ax.plot(x_scheduler, scheduler_data['bandwidth_mbps'], 's-', 
                label=scheduler, linewidth=2, markersize=8, color='tab:orange')
        
        # Labels and title
        ax.set_xlabel('Read Ratio (%)', fontsize=12)
        ax.set_ylabel('Bandwidth (MB/s)', fontsize=12)
        ax.set_title(f'{scheduler} vs default', fontsize=14, fontweight='bold')
        ax.legend(fontsize=10, loc='best')
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-5, 105)
        ax.tick_params(labelsize=10)
    
    # Hide unused subplots
    for idx in range(n_schedulers, len(axes)):
        axes[idx].set_visible(False)
    
    # Overall title
    fig.suptitle(f'{access_type} Access: Scheduler Comparisons (172 threads, 32GB)', 
                 fontsize=18, fontweight='bold', y=1.02)
    
    plt.tight_layout()
    
    # Save as PDF
    plt.savefig(output_file, format='pdf', dpi=300, bbox_inches='tight')
    print(f"Figure saved to: {output_file}")
    plt.close()

# Function to create random vs sequential comparison
def create_random_vs_seq_comparison(random_df, seq_df, scheduler='default'):
    """Create comparison figure and text report for random vs sequential access"""
    
    # Filter for specified scheduler
    random_data = random_df[random_df['scheduler'] == scheduler].copy()
    seq_data = seq_df[seq_df['scheduler'] == scheduler].copy()
    
    # Sort by read_ratio for consistent plotting
    random_data = random_data.sort_values('read_ratio')
    seq_data = seq_data.sort_values('read_ratio')
    
    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Convert read_ratio to percentage
    x_random = random_data['read_ratio'] * 100
    x_seq = seq_data['read_ratio'] * 100
    
    # Plot with consistent style
    ax.plot(x_random, random_data['bandwidth_mbps'], 'o-', label='Random Access', 
            linewidth=3, markersize=12, color='tab:orange')
    ax.plot(x_seq, seq_data['bandwidth_mbps'], 's-', label='Sequential Access', 
            linewidth=3, markersize=12, color='tab:blue')
    
    # Labels and title with larger font sizes
    ax.set_xlabel('Read Ratio (%)', fontsize=20)
    ax.set_ylabel('Bandwidth (MB/s)', fontsize=20)
    ax.set_title(f'Memory Bandwidth: Random vs Sequential Access\n({scheduler.capitalize()} Scheduler, 172 threads, 32GB)', 
                 fontsize=22, fontweight='bold')
    
    # Legend with larger font
    ax.legend(fontsize=18, loc='best')
    
    # Grid
    ax.grid(True, alpha=0.3)
    
    # Tick parameters
    ax.tick_params(labelsize=16)
    
    # Set x-axis limits
    ax.set_xlim(-5, 105)
    
    # Tight layout
    plt.tight_layout()
    
    # Save as PDF
    output_path = f'/root/yunwei37/ai-os/workloads/cxl-micro/results/{scheduler}_random_vs_seq_comparison.pdf'
    plt.savefig(output_path, format='pdf', dpi=300, bbox_inches='tight')
    print(f"Figure saved to: {output_path}")
    plt.close()
    
    # Generate text report
    report_lines = []
    report_lines.append(f"{'='*60}")
    report_lines.append(f"Random vs Sequential Access Comparison Report")
    report_lines.append(f"Scheduler: {scheduler}")
    report_lines.append(f"Configuration: 172 threads, 32GB")
    report_lines.append(f"{'='*60}\n")
    
    # Random Access Statistics
    report_lines.append("RANDOM ACCESS STATISTICS:")
    report_lines.append(f"  Average Bandwidth: {random_data['bandwidth_mbps'].mean():.2f} MB/s")
    report_lines.append(f"  Max Bandwidth: {random_data['bandwidth_mbps'].max():.2f} MB/s")
    report_lines.append(f"  Min Bandwidth: {random_data['bandwidth_mbps'].min():.2f} MB/s")
    
    # Get specific read ratios for random
    random_0 = random_data[random_data['read_ratio'] == 0.0]['bandwidth_mbps'].values
    random_50 = random_data[random_data['read_ratio'] == 0.5]['bandwidth_mbps'].values
    random_100 = random_data[random_data['read_ratio'] == 1.0]['bandwidth_mbps'].values
    
    if len(random_0) > 0:
        report_lines.append(f"  Read Ratio 0.0 (100% Write): {random_0[0]:.2f} MB/s")
    if len(random_50) > 0:
        report_lines.append(f"  Read Ratio 0.5 (50% Read/Write): {random_50[0]:.2f} MB/s")
    if len(random_100) > 0:
        report_lines.append(f"  Read Ratio 1.0 (100% Read): {random_100[0]:.2f} MB/s")
    
    # Find optimal read ratio for random
    random_max_idx = random_data['bandwidth_mbps'].idxmax()
    random_optimal_ratio = random_data.loc[random_max_idx, 'read_ratio']
    random_optimal_bw = random_data.loc[random_max_idx, 'bandwidth_mbps']
    report_lines.append(f"  Optimal Read Ratio: {random_optimal_ratio:.2f} (Bandwidth: {random_optimal_bw:.2f} MB/s)")
    
    # Calculate improvement metrics for random
    random_min = random_data['bandwidth_mbps'].min()
    random_max = random_data['bandwidth_mbps'].max()
    random_improvement = ((random_max - random_min) / random_min) * 100
    report_lines.append(f"  Bandwidth Range: {random_min:.2f} - {random_max:.2f} MB/s")
    report_lines.append(f"  Max Improvement from Min: {random_improvement:.1f}%")
    
    # Sequential Access Statistics
    report_lines.append("\nSEQUENTIAL ACCESS STATISTICS:")
    report_lines.append(f"  Average Bandwidth: {seq_data['bandwidth_mbps'].mean():.2f} MB/s")
    report_lines.append(f"  Max Bandwidth: {seq_data['bandwidth_mbps'].max():.2f} MB/s")
    report_lines.append(f"  Min Bandwidth: {seq_data['bandwidth_mbps'].min():.2f} MB/s")
    
    # Get specific read ratios for sequential
    seq_0 = seq_data[seq_data['read_ratio'] == 0.0]['bandwidth_mbps'].values
    seq_50 = seq_data[seq_data['read_ratio'] == 0.5]['bandwidth_mbps'].values
    seq_100 = seq_data[seq_data['read_ratio'] == 1.0]['bandwidth_mbps'].values
    
    if len(seq_0) > 0:
        report_lines.append(f"  Read Ratio 0.0 (100% Write): {seq_0[0]:.2f} MB/s")
    if len(seq_50) > 0:
        report_lines.append(f"  Read Ratio 0.5 (50% Read/Write): {seq_50[0]:.2f} MB/s")
    if len(seq_100) > 0:
        report_lines.append(f"  Read Ratio 1.0 (100% Read): {seq_100[0]:.2f} MB/s")
    
    # Find optimal read ratio for sequential
    seq_max_idx = seq_data['bandwidth_mbps'].idxmax()
    seq_optimal_ratio = seq_data.loc[seq_max_idx, 'read_ratio']
    seq_optimal_bw = seq_data.loc[seq_max_idx, 'bandwidth_mbps']
    report_lines.append(f"  Optimal Read Ratio: {seq_optimal_ratio:.2f} (Bandwidth: {seq_optimal_bw:.2f} MB/s)")
    
    # Calculate improvement metrics for sequential
    seq_min = seq_data['bandwidth_mbps'].min()
    seq_max = seq_data['bandwidth_mbps'].max()
    seq_improvement = ((seq_max - seq_min) / seq_min) * 100
    report_lines.append(f"  Bandwidth Range: {seq_min:.2f} - {seq_max:.2f} MB/s")
    report_lines.append(f"  Max Improvement from Min: {seq_improvement:.1f}%")
    
    # Comparison Statistics
    report_lines.append("\nSEQUENTIAL vs RANDOM COMPARISON:")
    
    # Overall comparison
    avg_improvement = ((seq_data['bandwidth_mbps'].mean() - random_data['bandwidth_mbps'].mean()) / random_data['bandwidth_mbps'].mean()) * 100
    report_lines.append(f"  Average Sequential Improvement over Random: {avg_improvement:.1f}%")
    
    # Specific read ratio comparisons
    if len(random_0) > 0 and len(seq_0) > 0:
        improvement_0 = ((seq_0[0] - random_0[0]) / random_0[0]) * 100
        report_lines.append(f"  Read Ratio 0.0 Improvement: {improvement_0:.1f}% (Seq: {seq_0[0]:.0f} vs Random: {random_0[0]:.0f} MB/s)")
    
    if len(random_50) > 0 and len(seq_50) > 0:
        improvement_50 = ((seq_50[0] - random_50[0]) / random_50[0]) * 100
        report_lines.append(f"  Read Ratio 0.5 Improvement: {improvement_50:.1f}% (Seq: {seq_50[0]:.0f} vs Random: {random_50[0]:.0f} MB/s)")
    
    if len(random_100) > 0 and len(seq_100) > 0:
        improvement_100 = ((seq_100[0] - random_100[0]) / random_100[0]) * 100
        report_lines.append(f"  Read Ratio 1.0 Improvement: {improvement_100:.1f}% (Seq: {seq_100[0]:.0f} vs Random: {random_100[0]:.0f} MB/s)")
    
    # Peak comparison
    peak_improvement = ((seq_optimal_bw - random_optimal_bw) / random_optimal_bw) * 100
    report_lines.append(f"  Peak Performance Improvement: {peak_improvement:.1f}%")
    report_lines.append(f"    Sequential Peak: {seq_optimal_bw:.0f} MB/s at read ratio {seq_optimal_ratio:.2f}")
    report_lines.append(f"    Random Peak: {random_optimal_bw:.0f} MB/s at read ratio {random_optimal_ratio:.2f}")
    
    # Write/Read comparison
    if len(random_0) > 0 and len(random_100) > 0:
        random_write_read_ratio = random_0[0] / random_100[0]
        report_lines.append(f"\n  Random Access Write/Read Ratio: {random_write_read_ratio:.2f} (Write is {random_write_read_ratio:.1f}x of Read)")
    
    if len(seq_0) > 0 and len(seq_100) > 0:
        seq_write_read_ratio = seq_0[0] / seq_100[0]
        report_lines.append(f"  Sequential Access Write/Read Ratio: {seq_write_read_ratio:.2f} (Write is {seq_write_read_ratio:.1f}x of Read)")
    
    report_lines.append(f"\n{'='*60}")
    
    # Save report to file
    report_path = f'/root/yunwei37/ai-os/workloads/cxl-micro/results/{scheduler}_random_vs_seq_comparison.txt'
    with open(report_path, 'w') as f:
        f.write('\n'.join(report_lines))
    print(f"Report saved to: {report_path}")
    
    return report_lines

# Read CSV files
seq_df = pd.read_csv('/root/yunwei37/ai-os/workloads/cxl-micro/results/parameter_sweep_multi_schedulers_numactl3_seq_32g_172t.csv')


# Get all unique schedulers (excluding default)
schedulers = sorted([s for s in seq_df['scheduler'].unique() if s != 'default'])


# Create sequential access comparison figure
create_comparison_figure(seq_df, 'Sequential', 
                        '/root/yunwei37/ai-os/workloads/cxl-micro/results/sequential_schedulers_comparison.pdf')

random_df = pd.read_csv('/root/yunwei37/ai-os/workloads/cxl-micro/results/parameter_sweep_multi_schedulers_numactl3_random_32g_172t.csv')

# Create random access comparison figure
create_comparison_figure(random_df, 'Random', 
                        '/root/yunwei37/ai-os/workloads/cxl-micro/results/random_schedulers_comparison.pdf')


# Comment out raw_df processing
# raw_df = seq_df  # Using sequential data for raw comparison
# create_comparison_figure(raw_df, 'Raw', 
#                         '/root/yunwei37/ai-os/workloads/cxl-micro/results/raw_schedulers_comparison.pdf')

# Load the 16GB 256 threads random data
random_16g_df = pd.read_csv('/root/yunwei37/ai-os/workloads/cxl-micro/results/parameter_sweep_multi_schedulers_numactl3_random_16g_256t.csv')

def create_rustland_vs_default_comparison(seq_df, random_16g_df):
    """Create comparison plot of scx_rustland vs default with sequential and random as subplots"""
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    # Subplot 1: Sequential Access
    ax = axes[0]
    
    # Get data for sequential access
    seq_default = seq_df[seq_df['scheduler'] == 'default'].copy().sort_values('read_ratio')
    seq_rustland = seq_df[seq_df['scheduler'] == 'scx_rustland'].copy().sort_values('read_ratio')
    
    # Convert read_ratio to percentage
    x_default = seq_default['read_ratio'] * 100
    x_rustland = seq_rustland['read_ratio'] * 100
    
    # Plot sequential access
    ax.plot(x_default, seq_default['bandwidth_mbps'], 'o-', 
            label='default', linewidth=2.5, markersize=10, color='tab:blue')
    ax.plot(x_rustland, seq_rustland['bandwidth_mbps'], 's-', 
            label='duplexOS', linewidth=2.5, markersize=10, color='tab:orange')
    
    ax.set_xlabel('Read Ratio (%)', fontsize=14)
    ax.set_ylabel('Bandwidth (MB/s)', fontsize=14)
    ax.set_title('Sequential Access (32GB, 172 threads)', fontsize=16, fontweight='bold')
    ax.legend(fontsize=12, loc='best')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-5, 105)
    ax.tick_params(labelsize=12)
    
    # Subplot 2: Random 16GB 256 threads Access
    ax = axes[1]
    
    # Use random_16g_df for the second subplot
    random16_default = random_16g_df[random_16g_df['scheduler'] == 'default'].copy().sort_values('read_ratio')
    random16_rustland = random_16g_df[random_16g_df['scheduler'] == 'scx_rustland'].copy().sort_values('read_ratio')
    
    # Convert read_ratio to percentage
    x_default = random16_default['read_ratio'] * 100
    x_rustland = random16_rustland['read_ratio'] * 100
    
    # Plot random 16GB access
    ax.plot(x_default, random16_default['bandwidth_mbps'], 'o-', 
            label='default', linewidth=2.5, markersize=10, color='tab:blue')
    ax.plot(x_rustland, random16_rustland['bandwidth_mbps'], 's-', 
            label='duplexOS', linewidth=2.5, markersize=10, color='tab:orange')
    
    ax.set_xlabel('Read Ratio (%)', fontsize=14)
    ax.set_ylabel('Bandwidth (MB/s)', fontsize=14)
    ax.set_title('Random Access (16GB, 256 threads)', fontsize=16, fontweight='bold')
    ax.legend(fontsize=12, loc='best')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-5, 105)
    ax.tick_params(labelsize=12)
    
    # Overall title
    fig.suptitle('duplexOS vs Default Scheduler: Bandwidth Comparison', 
                 fontsize=18, fontweight='bold', y=1.02)
    
    plt.tight_layout()
    
    # Save as PDF
    output_path = '/root/yunwei37/ai-os/workloads/cxl-micro/results/rustland_vs_default_comparison.pdf'
    plt.savefig(output_path, format='pdf', dpi=300, bbox_inches='tight')
    print(f"Figure saved to: {output_path}")
    plt.close()
    
    # Print comparison statistics
    print("\n" + "="*60)
    print("duplexOS vs Default Scheduler Performance Comparison")
    print("="*60)
    
    # Sequential Access Statistics
    print("\nSEQUENTIAL ACCESS (32GB, 172 threads):")
    seq_default_avg = seq_default['bandwidth_mbps'].mean()
    seq_rustland_avg = seq_rustland['bandwidth_mbps'].mean()
    seq_default_max = seq_default['bandwidth_mbps'].max()
    seq_rustland_max = seq_rustland['bandwidth_mbps'].max()
    
    seq_avg_improvement = ((seq_rustland_avg - seq_default_avg) / seq_default_avg) * 100
    seq_max_improvement = ((seq_rustland_max - seq_default_max) / seq_default_max) * 100
    
    print(f"  Default Average: {seq_default_avg:.2f} MB/s")
    print(f"  duplexOS Average: {seq_rustland_avg:.2f} MB/s")
    print(f"  Average Improvement: {seq_avg_improvement:.1f}%")
    print(f"  Default Max: {seq_default_max:.2f} MB/s")
    print(f"  duplexOS Max: {seq_rustland_max:.2f} MB/s")
    print(f"  Max Improvement: {seq_max_improvement:.1f}%")
    
    # Random Access Statistics
    print("\nRANDOM ACCESS (16GB, 256 threads):")
    random16_default_avg = random16_default['bandwidth_mbps'].mean()
    random16_rustland_avg = random16_rustland['bandwidth_mbps'].mean()
    random16_default_max = random16_default['bandwidth_mbps'].max()
    random16_rustland_max = random16_rustland['bandwidth_mbps'].max()
    
    random_avg_improvement = ((random16_rustland_avg - random16_default_avg) / random16_default_avg) * 100
    random_max_improvement = ((random16_rustland_max - random16_default_max) / random16_default_max) * 100
    
    print(f"  Default Average: {random16_default_avg:.2f} MB/s")
    print(f"  duplexOS Average: {random16_rustland_avg:.2f} MB/s")
    print(f"  Average Improvement: {random_avg_improvement:.1f}%")
    print(f"  Default Max: {random16_default_max:.2f} MB/s")
    print(f"  duplexOS Max: {random16_rustland_max:.2f} MB/s")
    print(f"  Max Improvement: {random_max_improvement:.1f}%")
    
    # Overall comparison
    print("\nOVERALL COMPARISON:")
    overall_avg_improvement = (seq_avg_improvement + random_avg_improvement) / 2
    overall_max_improvement = (seq_max_improvement + random_max_improvement) / 2
    print(f"  Overall Average Improvement: {overall_avg_improvement:.1f}%")
    print(f"  Overall Max Improvement: {overall_max_improvement:.1f}%")
    print("="*60)

# Create random vs sequential comparison for default scheduler
report = create_random_vs_seq_comparison(random_16g_df, seq_df, 'default')

# Create scx_rustland vs default comparison
create_rustland_vs_default_comparison(seq_df, random_16g_df)