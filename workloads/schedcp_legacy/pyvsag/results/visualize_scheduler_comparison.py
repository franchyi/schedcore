#!/usr/bin/env python3

import json
import matplotlib.pyplot as plt
import matplotlib.backends.backend_pdf
import numpy as np

# Set default font size
plt.rcParams.update({'font.size': 16})

# Read the JSON data
with open('/root/yunwei37/ai-os/workloads/pyvsag/results/pyvsag_scheduler_results.json', 'r') as f:
    data = json.load(f)

# Extract scheduler names and performance metrics
schedulers = []
display_names = []
qps_values = []
avg_query_time_values = []

# We'll focus on comparing default vs scx_bpfland (renamed to DuplexOS)
target_schedulers = ['default', 'scx_bpfland']
name_mapping = {'default': 'default', 'scx_bpfland': 'DuplexOS'}

for scheduler in target_schedulers:
    if scheduler in data and 'qps' in data[scheduler]:
        schedulers.append(scheduler)
        display_names.append(name_mapping[scheduler])
        qps_values.append(data[scheduler]['qps'])
        avg_query_time_values.append(data[scheduler]['avg_query_time_ms'])

# Define consistent colors for each scheduler
colors = ['#1f77b4', '#ff7f0e']  # Blue for default, Orange for DuplexOS

# Create PDF with both figures
pdf_pages = matplotlib.backends.backend_pdf.PdfPages('/root/yunwei37/ai-os/workloads/pyvsag/results/pyvsag_scheduler_comparison.pdf')

# Figure 1: Throughput (QPS) Performance
fig1, ax1 = plt.subplots(figsize=(12, 3))
y_pos = np.arange(len(display_names))
bars1 = ax1.barh(y_pos, qps_values, color=colors, height=0.6)
ax1.set_yticks(y_pos)
ax1.set_yticklabels(display_names, fontsize=20)
ax1.set_xlabel('Queries per Second (QPS)', fontsize=20)
ax1.set_title('Vector Search Throughput Performance', fontsize=22, fontweight='bold')
ax1.grid(axis='x', alpha=0.3)
ax1.tick_params(axis='x', labelsize=18)

# Add value labels on bars
for i, (bar, value) in enumerate(zip(bars1, qps_values)):
    ax1.text(value + 50, bar.get_y() + bar.get_height()/2, f'{value:.1f}', 
             ha='left', va='center',  fontsize=18)

plt.tight_layout()
pdf_pages.savefig(fig1)
plt.close(fig1)

# Figure 2: Query Latency Performance
fig2, ax2 = plt.subplots(figsize=(12, 3))
bars2 = ax2.barh(y_pos, avg_query_time_values, color=colors, height=0.6)
ax2.set_yticks(y_pos)
ax2.set_yticklabels(display_names, fontsize=20)
ax2.set_xlabel('Average Query Time (ms)', fontsize=20)
ax2.set_title('Vector Search Latency Performance', fontsize=22)
ax2.grid(axis='x', alpha=0.3)
ax2.tick_params(axis='x', labelsize=18)

# Add value labels on bars
for i, (bar, value) in enumerate(zip(bars2, avg_query_time_values)):
    ax2.text(value + 0.002, bar.get_y() + bar.get_height()/2, f'{value:.4f}', 
             ha='left', va='center', fontweight='bold', fontsize=18)

plt.tight_layout()
pdf_pages.savefig(fig2)
plt.close(fig2)

# Close the PDF
pdf_pages.close()

# Calculate percent improvements
qps_improvement = ((qps_values[1] - qps_values[0]) / qps_values[0] * 100)
latency_improvement = ((avg_query_time_values[0] - avg_query_time_values[1]) / avg_query_time_values[0] * 100)

print("Visualization complete! PDF saved at: /root/yunwei37/ai-os/workloads/pyvsag/results/scheduler_comparison.pdf")
print("\nPerformance Summary:")
print(f"Throughput (QPS):")
print(f"  default: {qps_values[0]:.2f}")
print(f"  DuplexOS: {qps_values[1]:.2f}")
print(f"  Improvement: {qps_improvement:.1f}%")
print(f"\nAverage Query Latency (ms):")
print(f"  default: {avg_query_time_values[0]:.6f}")
print(f"  DuplexOS: {avg_query_time_values[1]:.6f}")
print(f"  Improvement: {latency_improvement:.1f}% (lower is better)")