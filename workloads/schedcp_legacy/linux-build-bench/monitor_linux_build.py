#!/usr/bin/env python3

import os
import sys
import time
import json
import subprocess
import threading
import signal
from datetime import datetime
from pathlib import Path
import psutil
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from collections import defaultdict
import numpy as np
from typing import Dict, List, Optional, Tuple

class LinuxBuildMonitor:
    def __init__(self, linux_dir="/root/yunwei37/ai-os/workloads/linux-build-bench/linux", 
                 jobs=172, output_dir=None, results_dir="results"):
        self.linux_dir = Path(linux_dir)
        self.jobs = jobs
        base_dir = Path("/root/yunwei37/ai-os/workloads/linux-build-bench")
        self.results_dir = base_dir / results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Keep monitoring data in subdirectory of results
        monitor_subdir = output_dir or f"monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.output_dir = self.results_dir / monitor_subdir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.monitoring = False
        self.threads = []
        self.data = {
            'cpu': [],
            'memory': [],
            'io': [],
            'scheduler': [],
            'processes': []
        }
        
    def start_bpf_monitoring(self):
        """Start BPF-based scheduler monitoring"""
        bpf_script = """
        BEGIN {
            printf("timestamp,event,value\\n");
        }
        
        tracepoint:sched:sched_switch {
            @switches = count();
        }
        
        tracepoint:sched:sched_process_fork {
            @forks = count();
        }
        
        tracepoint:sched:sched_wakeup {
            @wakeups = count();
        }
        
        tracepoint:block:block_rq_issue {
            @io_requests = count();
            @io_bytes = sum(args->bytes);
        }
        
        interval:s:1 {
            printf("%ld,context_switches,%ld\\n", nsecs, @switches);
            printf("%ld,process_forks,%ld\\n", nsecs, @forks);
            printf("%ld,wakeups,%ld\\n", nsecs, @wakeups);
            printf("%ld,io_requests,%ld\\n", nsecs, @io_requests);
            printf("%ld,io_bytes,%ld\\n", nsecs, @io_bytes);
            
            clear(@switches);
            clear(@forks);
            clear(@wakeups);
            clear(@io_requests);
            clear(@io_bytes);
        }
        """
        
        bpf_file = self.output_dir / "monitor.bt"
        bpf_file.write_text(bpf_script)
        
        output_file = self.output_dir / "bpf_metrics.csv"
        
        def run_bpf():
            with open(output_file, 'w') as f:
                proc = subprocess.Popen(
                    ['sudo', 'bpftrace', str(bpf_file)],
                    stdout=f,
                    stderr=subprocess.DEVNULL
                )
                while self.monitoring:
                    time.sleep(0.1)
                proc.terminate()
                proc.wait(timeout=5)
        
        thread = threading.Thread(target=run_bpf)
        thread.start()
        self.threads.append(thread)
        
    def monitor_system_resources(self):
        """Monitor CPU, memory, and I/O usage"""
        def collect_metrics():
            while self.monitoring:
                timestamp = time.time()
                
                # CPU metrics
                cpu_percent = psutil.cpu_percent(interval=None, percpu=True)
                cpu_freq = psutil.cpu_freq()
                loadavg = os.getloadavg()
                
                self.data['cpu'].append({
                    'timestamp': timestamp,
                    'overall': sum(cpu_percent) / len(cpu_percent),
                    'per_cpu': cpu_percent,
                    'frequency': cpu_freq.current if cpu_freq else 0,
                    'load_1m': loadavg[0],
                    'load_5m': loadavg[1],
                    'load_15m': loadavg[2]
                })
                
                # Memory metrics
                mem = psutil.virtual_memory()
                swap = psutil.swap_memory()
                
                self.data['memory'].append({
                    'timestamp': timestamp,
                    'used_gb': mem.used / (1024**3),
                    'available_gb': mem.available / (1024**3),
                    'percent': mem.percent,
                    'swap_used_gb': swap.used / (1024**3),
                    'swap_percent': swap.percent,
                    'buffers_gb': mem.buffers / (1024**3) if hasattr(mem, 'buffers') else 0,
                    'cached_gb': mem.cached / (1024**3) if hasattr(mem, 'cached') else 0
                })
                
                # I/O metrics
                io_counters = psutil.disk_io_counters()
                net_io = psutil.net_io_counters()
                
                self.data['io'].append({
                    'timestamp': timestamp,
                    'disk_read_mb': io_counters.read_bytes / (1024**2),
                    'disk_write_mb': io_counters.write_bytes / (1024**2),
                    'disk_read_count': io_counters.read_count,
                    'disk_write_count': io_counters.write_count,
                    'net_sent_mb': net_io.bytes_sent / (1024**2),
                    'net_recv_mb': net_io.bytes_recv / (1024**2)
                })
                
                # Process tree metrics for make
                try:
                    make_procs = []
                    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                        if 'make' in proc.info['name'] or 'cc' in proc.info['name'] or 'gcc' in proc.info['name']:
                            make_procs.append(proc.info)
                    
                    self.data['processes'].append({
                        'timestamp': timestamp,
                        'count': len(make_procs),
                        'processes': make_procs
                    })
                except:
                    pass
                
                time.sleep(1)
        
        thread = threading.Thread(target=collect_metrics)
        thread.start()
        self.threads.append(thread)
    
    def run_build(self, make_cmd=None, clean_first=True):
        """Run the Linux kernel build"""
        original_dir = os.getcwd()
        os.chdir(self.linux_dir)
        
        try:
            clean_time = 0
            if clean_first:
                # Clean build
                print(f"Cleaning build directory...")
                clean_start = time.time()
                clean_result = subprocess.run(
                    ['make', 'clean', f'-j{self.jobs}'],
                    capture_output=True,
                    text=True
                )
                clean_time = time.time() - clean_start
            
            # Build kernel
            if make_cmd is None:
                make_cmd = ['make', f'-j{self.jobs}']
            
            print(f"Starting kernel build: {' '.join(make_cmd)}")
            build_start = time.time()
            
            # Use time command for additional metrics
            build_cmd = ['/usr/bin/time', '-v'] + make_cmd
            build_result = subprocess.run(
                build_cmd,
                capture_output=True,
                text=True
            )
            build_time = time.time() - build_start
        
            # Parse time output
            time_metrics = {}
            for line in build_result.stderr.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    time_metrics[key.strip()] = value.strip()
            
            return {
                'clean_time': clean_time,
                'build_time': build_time,
                'total_time': clean_time + build_time,
                'time_metrics': time_metrics,
                'exit_code': build_result.returncode
            }
        finally:
            os.chdir(original_dir)
    
    def analyze_bottlenecks(self):
        """Analyze collected data to identify bottlenecks"""
        analysis = {}
        
        # CPU analysis
        cpu_df = pd.DataFrame(self.data['cpu'])
        if not cpu_df.empty:
            analysis['cpu'] = {
                'avg_utilization': cpu_df['overall'].mean(),
                'max_utilization': cpu_df['overall'].max(),
                'avg_load': cpu_df['load_1m'].mean(),
                'max_load': cpu_df['load_1m'].max()
            }
        
        # Memory analysis
        mem_df = pd.DataFrame(self.data['memory'])
        if not mem_df.empty:
            analysis['memory'] = {
                'avg_used_gb': mem_df['used_gb'].mean(),
                'max_used_gb': mem_df['used_gb'].max(),
                'avg_percent': mem_df['percent'].mean(),
                'max_percent': mem_df['percent'].max()
            }
        
        # I/O analysis
        io_df = pd.DataFrame(self.data['io'])
        if not io_df.empty:
            # Calculate rates
            io_df['disk_read_rate'] = io_df['disk_read_mb'].diff()
            io_df['disk_write_rate'] = io_df['disk_write_mb'].diff()
            
            analysis['io'] = {
                'total_read_gb': (io_df['disk_read_mb'].iloc[-1] - io_df['disk_read_mb'].iloc[0]) / 1024,
                'total_write_gb': (io_df['disk_write_mb'].iloc[-1] - io_df['disk_write_mb'].iloc[0]) / 1024,
                'avg_read_rate_mb': io_df['disk_read_rate'].mean(),
                'avg_write_rate_mb': io_df['disk_write_rate'].mean(),
                'max_read_rate_mb': io_df['disk_read_rate'].max(),
                'max_write_rate_mb': io_df['disk_write_rate'].max()
            }
        
        # Determine bottleneck
        bottleneck = "balanced"
        reasons = []
        
        if analysis.get('cpu', {}).get('avg_utilization', 0) > 90:
            bottleneck = "CPU"
            reasons.append(f"High CPU utilization: {analysis['cpu']['avg_utilization']:.1f}%")
        
        if analysis.get('memory', {}).get('max_percent', 0) > 90:
            bottleneck = "Memory"
            reasons.append(f"High memory usage: {analysis['memory']['max_percent']:.1f}%")
        
        if analysis.get('cpu', {}).get('avg_load', 0) > self.jobs * 1.5:
            if bottleneck == "balanced":
                bottleneck = "CPU/Scheduler"
            reasons.append(f"High load average: {analysis['cpu']['avg_load']:.1f} (jobs: {self.jobs})")
        
        # Check for I/O bottleneck (heuristic: low CPU but high wait)
        if analysis.get('cpu', {}).get('avg_utilization', 100) < 70 and \
           analysis.get('io', {}).get('avg_write_rate_mb', 0) > 100:
            bottleneck = "I/O"
            reasons.append(f"High I/O with low CPU usage")
        
        analysis['bottleneck'] = {
            'type': bottleneck,
            'reasons': reasons
        }
        
        return analysis
    
    def generate_plots(self, build_metrics, analysis):
        """Generate visualization plots"""
        fig, axes = plt.subplots(3, 2, figsize=(15, 12))
        fig.suptitle(f'Linux Kernel Build Analysis - {self.jobs} jobs', fontsize=16)
        
        # CPU utilization over time
        cpu_df = pd.DataFrame(self.data['cpu'])
        if not cpu_df.empty:
            cpu_df['time'] = (cpu_df['timestamp'] - cpu_df['timestamp'].iloc[0])
            axes[0, 0].plot(cpu_df['time'], cpu_df['overall'], label='CPU %', color='blue')
            axes[0, 0].plot(cpu_df['time'], cpu_df['load_1m'] / self.jobs * 100, 
                           label='Load/Jobs %', color='red', alpha=0.7)
            axes[0, 0].set_xlabel('Time (s)')
            axes[0, 0].set_ylabel('Percentage')
            axes[0, 0].set_title('CPU Utilization and Load')
            axes[0, 0].legend()
            axes[0, 0].grid(True, alpha=0.3)
        
        # Memory usage over time
        mem_df = pd.DataFrame(self.data['memory'])
        if not mem_df.empty:
            mem_df['time'] = (mem_df['timestamp'] - mem_df['timestamp'].iloc[0])
            axes[0, 1].plot(mem_df['time'], mem_df['used_gb'], label='Used', color='green')
            axes[0, 1].plot(mem_df['time'], mem_df['cached_gb'], label='Cached', color='orange')
            axes[0, 1].set_xlabel('Time (s)')
            axes[0, 1].set_ylabel('Memory (GB)')
            axes[0, 1].set_title('Memory Usage')
            axes[0, 1].legend()
            axes[0, 1].grid(True, alpha=0.3)
        
        # I/O rates over time
        io_df = pd.DataFrame(self.data['io'])
        if not io_df.empty:
            io_df['time'] = (io_df['timestamp'] - io_df['timestamp'].iloc[0])
            io_df['read_rate'] = io_df['disk_read_mb'].diff()
            io_df['write_rate'] = io_df['disk_write_mb'].diff()
            
            axes[1, 0].plot(io_df['time'], io_df['read_rate'], label='Read', color='cyan')
            axes[1, 0].plot(io_df['time'], io_df['write_rate'], label='Write', color='magenta')
            axes[1, 0].set_xlabel('Time (s)')
            axes[1, 0].set_ylabel('I/O Rate (MB/s)')
            axes[1, 0].set_title('Disk I/O Rates')
            axes[1, 0].legend()
            axes[1, 0].grid(True, alpha=0.3)
        
        # Process count over time
        proc_counts = [len(p['processes']) for p in self.data['processes']]
        if proc_counts:
            proc_times = [(p['timestamp'] - self.data['processes'][0]['timestamp']) 
                         for p in self.data['processes']]
            axes[1, 1].plot(proc_times, proc_counts, color='purple')
            axes[1, 1].set_xlabel('Time (s)')
            axes[1, 1].set_ylabel('Active Processes')
            axes[1, 1].set_title('Compiler Process Count')
            axes[1, 1].grid(True, alpha=0.3)
        
        # BPF metrics if available
        bpf_file = self.output_dir / "bpf_metrics.csv"
        if bpf_file.exists():
            try:
                bpf_df = pd.read_csv(bpf_file, names=['timestamp', 'event', 'value'])
                if not bpf_df.empty and len(bpf_df) > 1:
                    # Group by event type
                    events = bpf_df.groupby('event')
                    
                    for event_name, event_data in events:
                        if len(event_data) > 0:
                            event_data = event_data.sort_values('timestamp')
                            rel_time = (event_data['timestamp'] - event_data['timestamp'].iloc[0]) / 1e9
                            axes[2, 0].plot(rel_time, event_data['value'], label=event_name)
                    
                    axes[2, 0].set_xlabel('Time (s)')
                    axes[2, 0].set_ylabel('Count/s')
                    axes[2, 0].set_title('Scheduler Events (BPF)')
                    axes[2, 0].legend()
                    axes[2, 0].grid(True, alpha=0.3)
            except Exception as e:
                print(f"Warning: Could not process BPF metrics: {e}")
        
        # Summary metrics
        summary_text = f"""Build Performance Summary:
        
Total Time: {build_metrics['total_time']:.1f}s
Clean Time: {build_metrics['clean_time']:.1f}s
Build Time: {build_metrics['build_time']:.1f}s

Resource Usage:
CPU Avg: {analysis.get('cpu', {}).get('avg_utilization', 0):.1f}%
CPU Max: {analysis.get('cpu', {}).get('max_utilization', 0):.1f}%
Memory Max: {analysis.get('memory', {}).get('max_used_gb', 0):.1f} GB
I/O Read: {analysis.get('io', {}).get('total_read_gb', 0):.2f} GB
I/O Write: {analysis.get('io', {}).get('total_write_gb', 0):.2f} GB

Bottleneck Analysis:
Type: {analysis.get('bottleneck', {}).get('type', 'Unknown')}
"""
        for reason in analysis.get('bottleneck', {}).get('reasons', []):
            summary_text += f"- {reason}\\n"
        
        axes[2, 1].text(0.1, 0.5, summary_text, transform=axes[2, 1].transAxes,
                       fontsize=10, verticalalignment='center', family='monospace')
        axes[2, 1].axis('off')
        
        plt.tight_layout()
        
        # Save to both output_dir and results root for easy access
        plot_file = self.output_dir / 'build_analysis.png'
        plt.savefig(plot_file, dpi=150)
        plt.close()
        
        print(f"Monitor plots saved to: {plot_file}")
        
        return plot_file
    
    def run(self, make_cmd=None, clean_first=True):
        """Main execution function"""
        print(f"Starting Linux kernel build monitoring...")
        print(f"Output directory: {self.output_dir}")
        
        # Start monitoring
        self.monitoring = True
        self.start_bpf_monitoring()
        self.monitor_system_resources()
        
        # Give monitors time to start
        time.sleep(2)
        
        # Run build
        build_metrics = self.run_build(make_cmd=make_cmd, clean_first=clean_first)
        
        # Stop monitoring
        self.monitoring = False
        for thread in self.threads:
            thread.join(timeout=5)
        
        # Analyze results
        analysis = self.analyze_bottlenecks()
        
        # Save raw data
        with open(self.output_dir / 'metrics.json', 'w') as f:
            json.dump({
                'build_metrics': build_metrics,
                'analysis': analysis,
                'cpu_data': self.data['cpu'][-100:],  # Last 100 samples
                'memory_data': self.data['memory'][-100:],
                'io_data': self.data['io'][-100:]
            }, f, indent=2, default=str)
        
        # Generate plots
        self.generate_plots(build_metrics, analysis)
        
        # Print summary
        print("\\n" + "="*60)
        print("BUILD PERFORMANCE SUMMARY")
        print("="*60)
        print(f"Total Time: {build_metrics['total_time']:.1f}s")
        print(f"Clean Time: {build_metrics['clean_time']:.1f}s")
        print(f"Build Time: {build_metrics['build_time']:.1f}s")
        print(f"\\nBottleneck: {analysis['bottleneck']['type']}")
        for reason in analysis['bottleneck']['reasons']:
            print(f"  - {reason}")
        
        print(f"\\nDetailed metrics saved to: {self.output_dir}/")
        
        return analysis

# Compare schedulers functionality moved to linux_build_tester.py
# Use LinuxBuildTester.run_all_tests() for scheduler comparisons

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Monitor Linux kernel build performance')
    parser.add_argument('--compare', action='store_true', 
                       help='Compare different schedulers')
    parser.add_argument('--schedulers', nargs='+', 
                       help='Schedulers to test (for --compare)')
    parser.add_argument('--jobs', type=int, default=172,
                       help='Number of parallel jobs (default: 172)')
    parser.add_argument('--output', type=str,
                       help='Output directory name')
    
    args = parser.parse_args()
    
    if args.compare:
        # Scheduler comparison moved to linux_build_tester.py
        print("Scheduler comparison functionality has been moved to linux_build_tester.py")
        print("Use: python linux_build_tester.py --enable-monitoring")
    else:
        monitor = LinuxBuildMonitor(jobs=args.jobs, output_dir=args.output)
        monitor.run()