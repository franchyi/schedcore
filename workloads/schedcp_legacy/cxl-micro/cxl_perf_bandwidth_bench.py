#!/usr/bin/env python3
"""
CXL-Micro Perf Bandwidth Benchmark
Integrates perf counters with double_bandwidth testing to calculate various bandwidth metrics.
Based on bandwidth_analysis.md methodology.
"""

import os
import sys
import subprocess
import json
import time
import argparse
import re
import pandas as pd
from typing import Dict, List


class PerfBandwidthCalculator:
    """Calculate bandwidth metrics from perf counters using cache line methodology"""
    
    CACHE_LINE_SIZE = 64  # bytes
    MB = 1024 * 1024
    
    # L3 and DRAM focused perf counters
    PERF_COUNTERS = [
        "instructions",
        "cycles",
        # L3 cache performance
        "cache-references",
        "cache-misses",
        "longest_lat_cache.miss",
        # Memory instructions for L3 miss rate calculation
        "mem_inst_retired.all_loads", 
        "mem_inst_retired.all_stores",
        # L3 hit/miss analysis
        "mem_load_retired.l3_hit",
        "mem_load_retired.l3_miss", 
        # L3 miss breakdown by destination
        # "mem_load_l3_miss_retired.local_dram",
        # "mem_load_l3_miss_retired.remote_dram",
        # "mem_load_l3_miss_retired.remote_fwd",
        # "mem_load_l3_miss_retired.remote_hitm",
        # Offcore requests (L3 miss traffic)
        "offcore_requests.l3_miss_demand_data_rd",
        "offcore_requests.demand_data_rd",
        "offcore_requests.demand_rfo", 
        # Memory controller counters (actual DRAM bandwidth)
        "uncore_imc/cas_count_read/",
        "uncore_imc/cas_count_write/",
        # Memory stalls
        "cycle_activity.stalls_l3_miss",
        "memory_activity.stalls_l3_miss"
    ]
    
    @classmethod
    def calculate_bandwidth_from_counter(cls, counter_value: int, wall_time: float) -> float:
        """
        Calculate bandwidth from perf counter value.
        
        Args:
            counter_value: Counter value from perf
            wall_time: Wall clock time in seconds
            
        Returns:
            Bandwidth in MB/s
        """
        return (counter_value * cls.CACHE_LINE_SIZE) / wall_time / cls.MB
    
    @classmethod
    def parse_perf_output(cls, perf_output: str) -> Dict[str, float]:
        """
        Parse perf stat output to extract counter values and timing.
        
        Args:
            perf_output: Raw perf stat output
            
        Returns:
            Dictionary with counter values and timing information
        """
        results = {}
        
        # Parse counter values
        for line in perf_output.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            # Look for counter pattern: "value counter_name"
            parts = line.split()
            if len(parts) >= 2:
                try:
                    # Remove commas from numbers
                    value_str = parts[0].replace(',', '')
                    counter_name = parts[1]
                    
                    # Skip if value is not a number
                    if value_str.replace('.', '').isdigit():
                        results[counter_name] = float(value_str)
                except (ValueError, IndexError):
                    continue
        
        # Parse timing information
        time_match = re.search(r'(\d+\.?\d*)\s+seconds time elapsed', perf_output)
        if time_match:
            results['wall_time'] = float(time_match.group(1))
        
        return results
    
    @classmethod
    def calculate_all_bandwidths(cls, perf_data: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate bandwidth or instruction rates for all perf counters.
        
        Args:
            perf_data: Dictionary with perf counter values and wall_time
            
        Returns:
            Dictionary with calculated metrics (bandwidth for cache-line events, rates for others)
        """
        if 'wall_time' not in perf_data:
            raise ValueError("Wall time not found in perf data")
        
        wall_time = perf_data['wall_time']
        metrics = {}
        
        # Basic performance counters (rates)
        if 'instructions' in perf_data:
            metrics['instructions_rate'] = perf_data['instructions'] / wall_time
        if 'cycles' in perf_data:
            metrics['cycles_rate'] = perf_data['cycles'] / wall_time
        
        # Cache counters (bandwidth - cache line level)
        if 'cache-references' in perf_data:
            metrics['cache_references_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['cache-references'], wall_time
            )
        if 'cache-misses' in perf_data:
            metrics['cache_misses_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['cache-misses'], wall_time
            )
        if 'longest_lat_cache.miss' in perf_data:
            metrics['longest_lat_cache_miss_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['longest_lat_cache.miss'], wall_time
            )
        
        # Memory instruction counters (bandwidth - assuming each instruction touches a cache line)
        if 'mem_inst_retired.all_loads' in perf_data:
            metrics['mem_loads_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['mem_inst_retired.all_loads'], wall_time
            )
        if 'mem_inst_retired.all_stores' in perf_data:
            metrics['mem_stores_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['mem_inst_retired.all_stores'], wall_time
            )
        
        # L3 hit/miss counters (instruction rates)
        if 'mem_load_retired.l3_hit' in perf_data:
            metrics['l3_hit_instructions_rate'] = perf_data['mem_load_retired.l3_hit'] / wall_time
        if 'mem_load_retired.l3_miss' in perf_data:
            metrics['l3_miss_instructions_rate'] = perf_data['mem_load_retired.l3_miss'] / wall_time
        
        # L3 miss destination counters (instruction rates)
        if 'mem_load_l3_miss_retired.local_dram' in perf_data:
            metrics['l3_miss_local_dram_instructions_rate'] = perf_data['mem_load_l3_miss_retired.local_dram'] / wall_time
        if 'mem_load_l3_miss_retired.remote_dram' in perf_data:
            metrics['l3_miss_remote_dram_instructions_rate'] = perf_data['mem_load_l3_miss_retired.remote_dram'] / wall_time
        if 'mem_load_l3_miss_retired.remote_fwd' in perf_data:
            metrics['l3_miss_remote_fwd_instructions_rate'] = perf_data['mem_load_l3_miss_retired.remote_fwd'] / wall_time
        if 'mem_load_l3_miss_retired.remote_hitm' in perf_data:
            metrics['l3_miss_remote_hitm_instructions_rate'] = perf_data['mem_load_l3_miss_retired.remote_hitm'] / wall_time
        
        # Offcore request counters (bandwidth - cache line level)
        if 'offcore_requests.l3_miss_demand_data_rd' in perf_data:
            metrics['offcore_l3_miss_data_rd_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['offcore_requests.l3_miss_demand_data_rd'], wall_time
            )
        if 'offcore_requests.demand_data_rd' in perf_data:
            metrics['offcore_data_read_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['offcore_requests.demand_data_rd'], wall_time
            )
        if 'offcore_requests.demand_rfo' in perf_data:
            metrics['offcore_rfo_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['offcore_requests.demand_rfo'], wall_time
            )
        
        # Memory controller counters (bandwidth - cache line level)
        if 'uncore_imc/cas_count_read/' in perf_data:
            metrics['dram_read_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['uncore_imc/cas_count_read/'], wall_time
            )
        if 'uncore_imc/cas_count_write/' in perf_data:
            metrics['dram_write_bandwidth_mbps'] = cls.calculate_bandwidth_from_counter(
                perf_data['uncore_imc/cas_count_write/'], wall_time
            )
        
        # Memory stall counters (rates)
        if 'cycle_activity.stalls_l3_miss' in perf_data:
            metrics['stalls_l3_miss_cycles_rate'] = perf_data['cycle_activity.stalls_l3_miss'] / wall_time
        if 'memory_activity.stalls_l3_miss' in perf_data:
            metrics['memory_stalls_l3_miss_cycles_rate'] = perf_data['memory_activity.stalls_l3_miss'] / wall_time
        
        # Derived metrics
        if 'instructions' in perf_data and 'cycles' in perf_data:
            metrics['instructions_per_cycle'] = perf_data['instructions'] / perf_data['cycles']
        
        if 'cache-references' in perf_data and 'cache-misses' in perf_data:
            metrics['cache_miss_rate_pct'] = (perf_data['cache-misses'] / perf_data['cache-references']) * 100
        
        if 'mem_load_retired.l3_hit' in perf_data and 'mem_load_retired.l3_miss' in perf_data:
            l3_hits = perf_data['mem_load_retired.l3_hit']
            l3_misses = perf_data['mem_load_retired.l3_miss']
            total_l3_accesses = l3_hits + l3_misses
            if total_l3_accesses > 0:
                metrics['l3_hit_rate_pct'] = (l3_hits / total_l3_accesses) * 100
                metrics['l3_miss_rate_pct'] = (l3_misses / total_l3_accesses) * 100
        
        return metrics


class CXLPerfBandwidthTester:
    """
    Simple CXL benchmark tester with perf counter integration.
    """
    
    def __init__(self, double_bandwidth_path: str, results_dir: str = "results"):
        """
        Initialize the CXLPerfBandwidthTester.
        
        Args:
            double_bandwidth_path: Path to double_bandwidth binary
            results_dir: Directory to store results
        """
        self.double_bandwidth_path = double_bandwidth_path
        self.results_dir = results_dir
        self.perf_calc = PerfBandwidthCalculator()
        
        # Create results directory
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Default test parameters
        self.test_params = {
            "buffer_size": 1073741824,  # 1GB default  
            "threads": 4,
            "duration": 10,
            "read_ratio": 0.5,
            "timeout": 300,
            "random": True,
        }
        
        # Environment setup
        self.env = os.environ.copy()
    
    def set_test_params(self, **kwargs):
        """Update test parameters"""
        self.test_params.update(kwargs)
    
    def _build_perf_command(self, target_cmd: List[str]) -> List[str]:
        """
        Build perf stat command with enhanced counters.
        
        Args:
            target_cmd: Command to run under perf
            
        Returns:
            Complete perf stat command
        """
        perf_cmd = [
            'sudo', 'perf', 'stat',
            '-e', ','.join(self.perf_calc.PERF_COUNTERS)
        ] + target_cmd
        
        return perf_cmd
    
    def _build_double_bandwidth_command(self) -> List[str]:
        """Build double_bandwidth command with current parameters"""
        cmd = [
            self.double_bandwidth_path,
            "--buffer-size", str(self.test_params["buffer_size"]),
            "--threads", str(self.test_params["threads"]),
            "--duration", str(self.test_params["duration"]),
            "--read-ratio", str(self.test_params["read_ratio"]),
            "--json"  # Use JSON output for easier parsing
        ]
        
        # Add access pattern flag
        if self.test_params.get("random", False):
            cmd.append("--random")
        else:
            cmd.append("--sequential")
        
        return cmd
    
    def _parse_combined_output(self, stdout: str, stderr: str) -> Dict:
        """
        Parse combined output from perf + double_bandwidth.
        
        Args:
            stdout: Standard output (contains JSON from double_bandwidth)
            stderr: Standard error (contains perf stat output)
            
        Returns:
            Combined results dictionary
        """
        results = {}
        
        # Parse application output (JSON)
        try:
            app_metrics = json.loads(stdout.strip())
            results['application'] = app_metrics
            
            # Rename some fields for compatibility
            if "total_bandwidth_mbps" in app_metrics:
                results['application']['bandwidth_mbps'] = app_metrics["total_bandwidth_mbps"]
            if "test_duration" in app_metrics:
                results['application']['execution_time'] = app_metrics["test_duration"]
                
        except json.JSONDecodeError as e:
            results['application'] = {"error": f"Failed to parse JSON: {e}", "raw_output": stdout}
        
        # Parse perf output
        try:
            perf_data = self.perf_calc.parse_perf_output(stderr)
            results['perf_counters'] = perf_data
            
            # Calculate bandwidth metrics from perf counters
            if perf_data:
                bandwidth_metrics = self.perf_calc.calculate_all_bandwidths(perf_data)
                results['perf_bandwidths'] = bandwidth_metrics
            else:
                results['perf_bandwidths'] = {"error": "No perf data parsed"}
                
        except Exception as e:
            results['perf_counters'] = {"error": f"Failed to parse perf output: {e}"}
            results['perf_bandwidths'] = {"error": str(e)}
        
        # Add test parameters
        results['test_params'] = self.test_params.copy()
        
        return results
    
    def run_perf_bandwidth_benchmark(self) -> Dict:
        """
        Run double_bandwidth with perf counters.
        
        Returns:
            Dictionary containing combined benchmark and perf results
        """
        print(f"Running perf + double_bandwidth")
        print(f"Parameters: buffer_size={self.test_params['buffer_size']}, "
              f"threads={self.test_params['threads']}, "
              f"duration={self.test_params['duration']}, "
              f"read_ratio={self.test_params['read_ratio']}")
        
        # Build commands
        target_cmd = self._build_double_bandwidth_command()
        perf_cmd = self._build_perf_command(target_cmd)
        timeout = self.test_params["timeout"]
        
        print(f"Running command: {' '.join(perf_cmd)}")
        
        try:
            result = subprocess.run(
                perf_cmd, 
                capture_output=True, 
                text=True, 
                timeout=timeout,
                env=self.env
            )
            exit_code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            exit_code, stdout, stderr = -1, "", "Command timed out"
        except Exception as e:
            exit_code, stdout, stderr = -1, "", str(e)
        
        if exit_code != 0:
            print(f"Warning: perf command exited with code {exit_code}")
            print(f"stderr: {stderr}")
            return {
                "error": stderr or f"Exit code: {exit_code}",
                "exit_code": exit_code,
                "raw_stdout": stdout,
                "raw_stderr": stderr
            }
        
        # Parse combined results
        results = self._parse_combined_output(stdout, stderr)
        results["exit_code"] = exit_code
        
        return results
    
    def run_parameter_sweep(self, 
                           thread_counts: List[int] = None,
                           read_ratios: List[float] = None, 
                           buffer_sizes: List[int] = None) -> List[Dict]:
        """
        Run parameter sweep with different combinations of threads, read ratios, and buffer sizes.
        
        Args:
            thread_counts: List of thread counts to test
            read_ratios: List of read ratios to test (0.0-1.0)
            buffer_sizes: List of buffer sizes to test (in bytes)
            
        Returns:
            List of dictionaries containing results for each parameter combination
        """
        # Default parameter ranges
        thread_counts = thread_counts or [4, 16, 64, 172, 256]
        read_ratios = read_ratios or [0, 0.15, 0.25, 0.35, 0.45, 0.5, 0.55, 0.65, 0.75, 0.85, 0.95, 1]
        buffer_sizes = buffer_sizes or [
            1 * 1024**3,    # 1GB
            4 * 1024**3,    # 4GB  
            16 * 1024**3,   # 16GB
            64 * 1024**3,   # 64GB
        ]
        # buffer_sizes = [64 * 1024**3]
        # thread_counts = [64]
        # read_ratios = [0, 0.5, 1]
        
        print(f"Running parameter sweep:")
        print(f"  Thread counts: {thread_counts}")
        print(f"  Read ratios: {read_ratios}")
        print(f"  Buffer sizes: {[f'{size/(1024**3):.0f}GB' for size in buffer_sizes]}")
        
        all_results = []
        total_tests = len(thread_counts) * len(read_ratios) * len(buffer_sizes)
        test_count = 0
        
        for buffer_size in buffer_sizes:
            for threads in thread_counts:
                for read_ratio in read_ratios:
                    test_count += 1
                    print(f"\nTest {test_count}/{total_tests}: "
                          f"buffer_size={buffer_size/(1024**3):.1f}GB, "
                          f"threads={threads}, read_ratio={read_ratio:.2f}")
                    
                    # Update test parameters
                    self.set_test_params(
                        threads=threads,
                        buffer_size=buffer_size,
                        read_ratio=read_ratio
                    )
                    
                    # Run benchmark
                    result = self.run_perf_bandwidth_benchmark()
                    
                    if "error" not in result:
                        # Extract key metrics
                        app_metrics = result.get('application', {})
                        perf_metrics = result.get('perf_bandwidths', {})
                        
                        sweep_result = {
                            'buffer_size_gb': buffer_size / (1024**3),
                            'buffer_size_bytes': buffer_size,
                            'threads': threads,
                            'read_ratio': read_ratio,
                            'duration': self.test_params['duration'],
                            
                            # Application metrics
                            'app_total_bandwidth_mbps': app_metrics.get('bandwidth_mbps', 0),
                            'app_read_bandwidth_mbps': app_metrics.get('read_bandwidth_mbps', 0),
                            'app_write_bandwidth_mbps': app_metrics.get('write_bandwidth_mbps', 0),
                            'app_total_iops': app_metrics.get('total_iops', 0),
                            'app_execution_time': app_metrics.get('execution_time', 0),
                            
                            # Key perf bandwidth metrics
                            'perf_cache_references_bandwidth_mbps': perf_metrics.get('cache_references_bandwidth_mbps', 0),
                            'perf_cache_misses_bandwidth_mbps': perf_metrics.get('cache_misses_bandwidth_mbps', 0),
                            'perf_dram_read_bandwidth_mbps': perf_metrics.get('dram_read_bandwidth_mbps', 0),
                            'perf_dram_write_bandwidth_mbps': perf_metrics.get('dram_write_bandwidth_mbps', 0),
                            'perf_mem_loads_bandwidth_mbps': perf_metrics.get('mem_loads_bandwidth_mbps', 0),
                            'perf_mem_stores_bandwidth_mbps': perf_metrics.get('mem_stores_bandwidth_mbps', 0),
                            'perf_offcore_data_read_bandwidth_mbps': perf_metrics.get('offcore_data_read_bandwidth_mbps', 0),
                            'perf_offcore_rfo_bandwidth_mbps': perf_metrics.get('offcore_rfo_bandwidth_mbps', 0),
                            
                            # Key efficiency metrics
                            'perf_cache_miss_rate_pct': perf_metrics.get('cache_miss_rate_pct', 0),
                            'perf_l3_hit_rate_pct': perf_metrics.get('l3_hit_rate_pct', 0),
                            'perf_l3_miss_rate_pct': perf_metrics.get('l3_miss_rate_pct', 0),
                            'perf_instructions_per_cycle': perf_metrics.get('instructions_per_cycle', 0),
                            
                            # Status
                            'status': 'success'
                        }
                        
                        all_results.append(sweep_result)
                        print(f"  App Bandwidth: {app_metrics.get('bandwidth_mbps', 0):.1f} MB/s, "
                              f"Cache Refs: {perf_metrics.get('cache_references_bandwidth_mbps', 0):.1f} MB/s")
                    else:
                        print(f"  Failed: {result.get('error', 'Unknown error')}")
                        # Add failed result with zeros
                        failed_result = {
                            'buffer_size_gb': buffer_size / (1024**3),
                            'buffer_size_bytes': buffer_size,
                            'threads': threads,
                            'read_ratio': read_ratio,
                            'duration': self.test_params['duration'],
                            'status': 'failed',
                            'error': result.get('error', 'Unknown error')
                        }
                        # Add all metric fields with 0 values
                        for key in ['app_total_bandwidth_mbps', 'app_read_bandwidth_mbps', 'app_write_bandwidth_mbps', 
                                   'app_total_iops', 'app_execution_time', 'perf_cache_references_bandwidth_mbps',
                                   'perf_cache_misses_bandwidth_mbps', 'perf_dram_read_bandwidth_mbps', 
                                   'perf_dram_write_bandwidth_mbps', 'perf_mem_loads_bandwidth_mbps',
                                   'perf_mem_stores_bandwidth_mbps', 'perf_offcore_data_read_bandwidth_mbps',
                                   'perf_offcore_rfo_bandwidth_mbps', 'perf_cache_miss_rate_pct',
                                   'perf_l3_hit_rate_pct', 'perf_l3_miss_rate_pct', 'perf_instructions_per_cycle']:
                            failed_result[key] = 0
                        all_results.append(failed_result)
                    
                    # Brief pause between tests
                    time.sleep(1)
        
        return all_results
    
    def save_parameter_sweep_results(self, results: List[Dict]):
        """Save parameter sweep results to CSV and JSON files"""
        if not results:
            print("No results to save")
            return
        
        # Save to CSV
        df = pd.DataFrame(results)
        csv_file = os.path.join(self.results_dir, "cxl_perf_parameter_sweep.csv")
        df.to_csv(csv_file, index=False)
        print(f"Parameter sweep results saved to CSV: {csv_file}")
        
        # Also save to JSON for compatibility
        json_file = os.path.join(self.results_dir, "cxl_perf_parameter_sweep.json")
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Parameter sweep results saved to JSON: {json_file}")
        
        # Print summary statistics
        self.print_parameter_sweep_summary(df)
    
    def print_parameter_sweep_summary(self, df: pd.DataFrame):
        """Print summary statistics for parameter sweep results"""
        print("\n" + "="*80)
        print("CXL PERF BANDWIDTH PARAMETER SWEEP SUMMARY")
        print("="*80)
        
        successful_results = df[df['status'] == 'success']
        if successful_results.empty:
            print("No successful test results found!")
            return
        
        print(f"\nSuccessful tests: {len(successful_results)}/{len(df)}")
        
        # Best performing configurations
        print("\nTOP 5 CONFIGURATIONS BY APPLICATION BANDWIDTH:")
        print("-" * 60)
        top_app_bw = successful_results.nlargest(5, 'app_total_bandwidth_mbps')
        for _, row in top_app_bw.iterrows():
            print(f"  {row['buffer_size_gb']:4.0f}GB, {row['threads']:3d} threads, "
                  f"ratio {row['read_ratio']:4.2f}: {row['app_total_bandwidth_mbps']:8.1f} MB/s")
        
        print("\nTOP 5 CONFIGURATIONS BY CACHE REFERENCES BANDWIDTH:")
        print("-" * 60)
        top_cache_bw = successful_results.nlargest(5, 'perf_cache_references_bandwidth_mbps')
        for _, row in top_cache_bw.iterrows():
            print(f"  {row['buffer_size_gb']:4.0f}GB, {row['threads']:3d} threads, "
                  f"ratio {row['read_ratio']:4.2f}: {row['perf_cache_references_bandwidth_mbps']:8.1f} MB/s")
        
        # Summary statistics
        print(f"\nSUMMARY STATISTICS:")
        print("-" * 40)
        print(f"Application Bandwidth (MB/s):")
        print(f"  Mean:    {successful_results['app_total_bandwidth_mbps'].mean():8.1f}")
        print(f"  Median:  {successful_results['app_total_bandwidth_mbps'].median():8.1f}")
        print(f"  Max:     {successful_results['app_total_bandwidth_mbps'].max():8.1f}")
        print(f"  Min:     {successful_results['app_total_bandwidth_mbps'].min():8.1f}")
        
        print(f"\nCache References Bandwidth (MB/s):")
        print(f"  Mean:    {successful_results['perf_cache_references_bandwidth_mbps'].mean():8.1f}")
        print(f"  Median:  {successful_results['perf_cache_references_bandwidth_mbps'].median():8.1f}")
        print(f"  Max:     {successful_results['perf_cache_references_bandwidth_mbps'].max():8.1f}")
        print(f"  Min:     {successful_results['perf_cache_references_bandwidth_mbps'].min():8.1f}")
        
        print(f"\nCache Miss Rate (%):")
        print(f"  Mean:    {successful_results['perf_cache_miss_rate_pct'].mean():8.2f}")
        print(f"  Median:  {successful_results['perf_cache_miss_rate_pct'].median():8.2f}")
        print(f"  Max:     {successful_results['perf_cache_miss_rate_pct'].max():8.2f}")
        print(f"  Min:     {successful_results['perf_cache_miss_rate_pct'].min():8.2f}")

    def save_results(self, results: Dict):
        """Save results to JSON file"""
        results_file = os.path.join(self.results_dir, "cxl_perf_bandwidth_results.json")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {results_file}")
    
    def print_raw_data(self, results: Dict):
        """Print raw performance data and calculated metrics"""
        print("\n" + "="*80)
        print("RAW DATA OUTPUT")
        print("="*80)
        
        if "error" in results:
            print(f"ERROR: {results['error']}")
            if "raw_stdout" in results:
                print(f"\nRAW STDOUT:\n{results['raw_stdout']}")
            if "raw_stderr" in results:
                print(f"\nRAW STDERR:\n{results['raw_stderr']}")
            return
        
        # Print calculation methodology
        print("CALCULATION METHODOLOGY:")
        print("-" * 40)
        print("Bandwidth (MB/s) = (counter_value * 64 bytes) / wall_time / 1048576")
        print("Rate (events/s) = counter_value / wall_time")
        print()
        
        # Show all calculated metrics if perf data exists
        if "perf_counters" in results and "perf_bandwidths" in results:
            perf_counters = results["perf_counters"]
            metrics = results["perf_bandwidths"]
            wall_time = perf_counters.get("wall_time", 0)
            
            print("PERFORMANCE METRICS:")
            print("-" * 40)
            print(f"Wall Time: {wall_time:.6f} seconds")
            print()
            
            # Group metrics by type with proper units
            bandwidth_metrics = {k: v for k, v in metrics.items() if k.endswith('_bandwidth_mbps')}
            instruction_rate_metrics = {k: v for k, v in metrics.items() if 'instructions_rate' in k}
            cycle_rate_metrics = {k: v for k, v in metrics.items() if 'cycles_rate' in k}
            percentage_metrics = {k: v for k, v in metrics.items() if k.endswith('_pct')}
            other_metrics = {k: v for k, v in metrics.items() 
                           if not any(x in k for x in ['_bandwidth_mbps', 'instructions_rate', 'cycles_rate', '_pct'])}
            
            if bandwidth_metrics:
                print("BANDWIDTH METRICS (MB/s):")
                for name, value in sorted(bandwidth_metrics.items()):
                    print(f"  {name:<45}: {value:>10.2f}")
                print()
            
            if instruction_rate_metrics:
                print("INSTRUCTION RATE METRICS (instructions/sec):")
                for name, value in sorted(instruction_rate_metrics.items()):
                    print(f"  {name:<45}: {value:>12,.0f}")
                print()
            
            if cycle_rate_metrics:
                print("CYCLE RATE METRICS (cycles/sec):")
                for name, value in sorted(cycle_rate_metrics.items()):
                    print(f"  {name:<45}: {value:>12,.0f}")
                print()
            
            if percentage_metrics:
                print("PERCENTAGE METRICS (%):")
                for name, value in sorted(percentage_metrics.items()):
                    print(f"  {name:<45}: {value:>10.2f}")
                print()
            
            if other_metrics:
                print("OTHER METRICS:")
                for name, value in sorted(other_metrics.items()):
                    print(f"  {name:<45}: {value:>10.6f}")
                print()
        
        # Print complete JSON results
        print("COMPLETE JSON RESULTS:")
        print("=" * 40)
        print(json.dumps(results, indent=2))
    
    def print_detailed_summary(self, results: Dict):
        """Print detailed performance summary with perf metrics"""
        print("\n" + "="*80)
        print("CXL PERF BANDWIDTH ANALYSIS SUMMARY")
        print("="*80)
        
        if "error" in results:
            print(f"ERROR: {results['error']}")
            return
        
        print("-" * 60)
        
        # Application metrics
        if "application" in results:
            app = results["application"]
            print(f"APPLICATION BANDWIDTH:")
            print(f"  Total:           {app.get('bandwidth_mbps', 0):8.1f} MB/s")
            if "execution_time" in app:
                print(f"  Duration:        {app.get('execution_time', 0):8.2f} seconds")
            if "total_read_bytes" in app and "total_write_bytes" in app:
                total_gb = (app["total_read_bytes"] + app["total_write_bytes"]) / (1024**3)
                print(f"  Total Data:      {total_gb:8.2f} GB")
        
        # Perf bandwidth metrics
        if "perf_bandwidths" in results and not "error" in results["perf_bandwidths"]:
            perf_bw = results["perf_bandwidths"]
            print(f"\nPERF BANDWIDTH METRICS:")
            print(f"  Cache Refs:      {perf_bw.get('cache_references_bandwidth_mbps', 0):8.1f} MB/s")
            print(f"  Cache Misses:    {perf_bw.get('cache_misses_bandwidth_mbps', 0):8.1f} MB/s")
            print(f"  Offcore Data Rd: {perf_bw.get('offcore_data_read_bandwidth_mbps', 0):8.1f} MB/s")
            print(f"  Offcore RFO:     {perf_bw.get('offcore_rfo_bandwidth_mbps', 0):8.1f} MB/s")
            print(f"  DRAM Read:       {perf_bw.get('dram_read_bandwidth_mbps', 0):8.1f} MB/s")
            print(f"  DRAM Write:      {perf_bw.get('dram_write_bandwidth_mbps', 0):8.1f} MB/s")
            print(f"  Mem Loads:       {perf_bw.get('mem_loads_bandwidth_mbps', 0):8.1f} MB/s")
            print(f"  Mem Stores:      {perf_bw.get('mem_stores_bandwidth_mbps', 0):8.1f} MB/s")
            
            print(f"\nEFFICIENCY METRICS:")
            print(f"  Cache Miss Rate: {perf_bw.get('cache_miss_rate_pct', 0):8.1f} %")
            print(f"  L3 Hit Rate:     {perf_bw.get('l3_hit_rate_pct', 0):8.1f} %")
            print(f"  L3 Miss Rate:    {perf_bw.get('l3_miss_rate_pct', 0):8.1f} %")
            print(f"  IPC:             {perf_bw.get('instructions_per_cycle', 0):8.3f}")
            
            # Validation: Compare app bandwidth with cache references
            if "application" in results and "bandwidth_mbps" in results["application"]:
                app_bw = results["application"]["bandwidth_mbps"]
                cache_ref_bw = perf_bw.get('cache_references_bandwidth_mbps', 0)
                if cache_ref_bw > 0:
                    correlation = cache_ref_bw / app_bw
                    print(f"\nVALIDATION:")
                    print(f"  Cache/App Ratio: {correlation:8.3f} (expect ~1.0)")


def main():
    """Main function for CXL perf bandwidth testing"""
    parser = argparse.ArgumentParser(description="Test CXL-micro double_bandwidth with perf counters")
    parser.add_argument("--double-bandwidth-path", 
                       default="/root/yunwei37/ai-os/workloads/cxl-micro/double_bandwidth",
                       help="Path to double_bandwidth binary")
    parser.add_argument("--results-dir", default="results", 
                       help="Directory to store results")
    parser.add_argument("--threads", type=int, default=128, 
                       help="Number of threads for testing")
    parser.add_argument("--buffer-size", type=int, default=64*1024*1024*1024, 
                       help="Buffer size in bytes (default 256GB)")
    parser.add_argument("--duration", type=int, default=20, 
                       help="Test duration in seconds")
    parser.add_argument("--read-ratio", type=float, default=0.5,
                       help="Ratio of readers (0.0-1.0, default: 0.5)")
    parser.add_argument("--timeout", type=int, default=300, 
                       help="Timeout in seconds")
    parser.add_argument("--raw", action="store_true", default=True,
                       help="Print raw data output instead of summary")
    parser.add_argument("--parameter-sweep", action="store_true", 
                       help="Run parameter sweep across threads, read ratios, and buffer sizes")
    parser.add_argument("--random", "-R", action="store_true", default=False,
                       help="Use random memory access pattern instead of sequential")
    
    args = parser.parse_args()
    
    # Create tester instance
    tester = CXLPerfBandwidthTester(args.double_bandwidth_path, args.results_dir)
    
    # Validate read_ratio
    if args.read_ratio < 0.0 or args.read_ratio > 1.0:
        print("Error: read-ratio must be between 0.0 and 1.0")
        sys.exit(1)
    
    # Update test parameters
    tester.set_test_params(
        threads=args.threads,
        buffer_size=args.buffer_size,
        duration=args.duration,
        timeout=args.timeout,
        read_ratio=args.read_ratio,
        random=args.random
    )
    
    # Check if binary exists
    if not os.path.exists(args.double_bandwidth_path):
        print(f"Error: double_bandwidth not found at {args.double_bandwidth_path}")
        sys.exit(1)
    
    # Check if we can run perf
    try:
        subprocess.run(['sudo', 'perf', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: Cannot run 'sudo perf'. Make sure perf is installed and you have sudo access.")
        sys.exit(1)
    
    if args.parameter_sweep:
        print("Starting CXL perf bandwidth parameter sweep...")
        print(f"Perf counters: {', '.join(tester.perf_calc.PERF_COUNTERS)}")
        
        # Run parameter sweep with default ranges
        sweep_results = tester.run_parameter_sweep()
        
        # Save sweep results  
        tester.save_parameter_sweep_results(sweep_results)
        
        print("\nParameter sweep complete!")
    else:
        print("Starting CXL perf bandwidth analysis...")
        print(f"Perf counters: {', '.join(tester.perf_calc.PERF_COUNTERS)}")
        
        # Run the benchmark
        results = tester.run_perf_bandwidth_benchmark()
        
        # Save and display results
        tester.save_results(results)
        
        if args.raw:
            tester.print_raw_data(results)
        else:
            tester.print_detailed_summary(results)
        
        print("\nTesting complete!")


if __name__ == "__main__":
    main()