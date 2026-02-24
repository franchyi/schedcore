#!/usr/bin/env python3
"""
Scheduler Test Runner

This script automates running test cases with both default and custom BPF schedulers.
For each test case:
1. Runs with default Linux scheduler
2. Runs with custom BPF scheduler (if available)
3. Collects and parses the results
"""

import json
import subprocess
import time
import signal
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

class SchedulerTestRunner:
    def __init__(self, test_cases_file, schedulers_dir, output_dir):
        self.test_cases_file = Path(test_cases_file)
        self.schedulers_dir = Path(schedulers_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load test cases
        with open(self.test_cases_file, 'r') as f:
            self.test_config = json.load(f)
        
        self.test_cases = self.test_config.get('test_cases', [])
        self.results = {}
        
    def get_scheduler_path(self, test_id):
        """Get the path to the scheduler binary for a test case"""
        scheduler_name = f"{test_id}.bpf.o"
        scheduler_path = self.schedulers_dir / scheduler_name
        
        if not scheduler_path.exists():
            print(f"Warning: Scheduler {scheduler_path} not found")
            return None
            
        return scheduler_path
    
    def start_scheduler(self, scheduler_path):
        """Start a scheduler and return the process handle"""
        loader_path = self.schedulers_dir / "loader"
        
        if not loader_path.exists():
            print(f"Error: Loader {loader_path} not found")
            return None
            
        print(f"Starting scheduler: {scheduler_path}")
        
        # Start scheduler with sudo
        cmd = ["sudo", str(loader_path), str(scheduler_path)]
        
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Give scheduler time to initialize
            time.sleep(2)
            
            # Check if process is still running
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                print(f"Scheduler failed to start: {stderr}")
                return None
                
            return proc
            
        except Exception as e:
            print(f"Failed to start scheduler: {e}")
            return None
    
    def stop_scheduler(self, proc):
        """Stop a running scheduler process"""
        if proc is None:
            return
            
        print("Stopping scheduler...")
        
        try:
            # Send SIGINT (Ctrl+C) to scheduler
            proc.send_signal(signal.SIGINT)
            
            # Wait for graceful shutdown
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Scheduler didn't stop gracefully, forcing termination...")
                proc.terminate()
                proc.wait(timeout=2)
                
        except Exception as e:
            print(f"Error stopping scheduler: {e}")
            # Force kill if needed
            try:
                proc.kill()
            except:
                pass
    
    def run_test_case(self, test_case):
        """Run a single test case with evaluate_workloads_parallel.py"""
        test_id = test_case['id']
        print(f"\nRunning test: {test_id}")
        
        # Build command
        cmd = [
            "python3",
            "evaluate_workloads_parallel.py",
            "--test", test_id
        ]
        
        try:
            # Run the test
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                print(f"Test failed with return code {result.returncode}")
                print(f"stderr: {result.stderr}")
                return None
                
            # Parse JSON output from stdout
            # The script prints JSON to stdout at the end
            output_lines = result.stdout.strip().split('\n')
            
            # Find the JSON output (usually the last part after other print statements)
            json_start = -1
            for i in range(len(output_lines) - 1, -1, -1):
                if output_lines[i].strip().startswith('{'):
                    json_start = i
                    break
                    
            if json_start == -1:
                print("No JSON output found in test results")
                return None
                
            # Extract JSON part
            json_output = '\n'.join(output_lines[json_start:])
            
            try:
                return json.loads(json_output)
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON output: {e}")
                print(f"Output was: {json_output}")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"Test timed out after 300 seconds")
            return None
        except Exception as e:
            print(f"Error running test: {e}")
            return None
    
    def run_test_with_scheduler(self, test_case, scheduler_type, scheduler_path=None):
        """Run a test case with a specific scheduler"""
        test_id = test_case['id']
        timestamp = datetime.now().isoformat()
        
        if scheduler_type == "custom":
            # Start custom scheduler
            scheduler_proc = self.start_scheduler(scheduler_path)
            if scheduler_proc is None:
                return {
                    'test_id': test_id,
                    'timestamp': timestamp,
                    'status': 'scheduler_start_failed',
                    'scheduler_type': scheduler_type,
                    'scheduler_path': str(scheduler_path),
                    'results': None
                }
        else:
            # Default scheduler - no need to start anything
            scheduler_proc = None
        
        try:
            # Run test
            test_results = self.run_test_case(test_case)
            
            if test_results is None:
                status = 'test_failed'
            else:
                status = 'success'
                
            return {
                'test_id': test_id,
                'timestamp': timestamp,
                'status': status,
                'scheduler_type': scheduler_type,
                'scheduler_path': str(scheduler_path) if scheduler_path else 'default',
                'results': test_results
            }
            
        finally:
            # Stop custom scheduler if running
            if scheduler_proc:
                self.stop_scheduler(scheduler_proc)
                
            # Wait a bit before next test
            time.sleep(2)
    
    def run_all_tests(self, run_default=True, run_custom=True, runs_per_scheduler=2):
        """Run all test cases with specified schedulers"""
        all_results = []
        
        for test_case in self.test_cases:
            test_id = test_case['id']
            print(f"\n{'=' * 60}")
            print(f"Test Case: {test_id} - {test_case.get('name', 'Unnamed')}")
            print(f"{'=' * 60}")
            
            # Run with default scheduler
            if run_default:
                print(f"\n--- Running with DEFAULT scheduler ---")
                for run_num in range(runs_per_scheduler):
                    print(f"\n--- Default scheduler - Run {run_num + 1} of {runs_per_scheduler} ---")
                    
                    result = self.run_test_with_scheduler(test_case, "default")
                    result['run_number'] = run_num + 1
                    result['scheduler'] = 'default'
                    all_results.append(result)
                    
                    # Save individual result
                    self.save_result(result, test_id, f"default_run{run_num + 1}")
            
            # Run with custom scheduler
            if run_custom:
                scheduler_path = self.get_scheduler_path(test_id)
                
                if scheduler_path is None:
                    print(f"Skipping custom scheduler test for {test_id} - no scheduler found")
                else:
                    print(f"\n--- Running with CUSTOM scheduler: {scheduler_path} ---")
                    for run_num in range(runs_per_scheduler):
                        print(f"\n--- Custom scheduler - Run {run_num + 1} of {runs_per_scheduler} ---")
                        
                        result = self.run_test_with_scheduler(test_case, "custom", scheduler_path)
                        result['run_number'] = run_num + 1
                        result['scheduler'] = 'custom'
                        all_results.append(result)
                        
                        # Save individual result
                        self.save_result(result, test_id, f"custom_run{run_num + 1}")
        
        # Save all results
        self.save_all_results(all_results)
        
        return all_results
    
    def save_result(self, result, test_id, run_label):
        """Save individual test result"""
        filename = f"{test_id}_{run_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(result, f, indent=2)
            
        print(f"Saved result to: {filepath}")
        
        # Also save log file if we have stdout/stderr
        if result.get('results') and isinstance(result['results'], dict):
            log_filename = f"{test_id}_{run_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            log_filepath = self.output_dir / log_filename
            
            with open(log_filepath, 'w') as f:
                f.write(f"Test: {test_id}\n")
                f.write(f"Run: {run_label}\n")
                f.write(f"Timestamp: {result['timestamp']}\n")
                f.write(f"Scheduler Type: {result['scheduler_type']}\n")
                f.write(f"Scheduler Path: {result.get('scheduler_path', 'N/A')}\n")
                f.write(f"Status: {result['status']}\n")
                f.write("\n" + "="*60 + "\n\n")
                f.write("Results:\n")
                f.write(json.dumps(result['results'], indent=2))
    
    def save_all_results(self, results):
        """Save all results to a summary file"""
        summary_file = self.output_dir / f"test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        summary = {
            'test_config': str(self.test_cases_file),
            'schedulers_dir': str(self.schedulers_dir),
            'timestamp': datetime.now().isoformat(),
            'total_tests': len(results),
            'results': results
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
            
        print(f"\n\nSaved summary to: {summary_file}")
        
        # Print summary statistics
        print("\n" + "="*60)
        print("Test Summary")
        print("="*60)
        
        test_counts = {}
        for result in results:
            test_id = result['test_id']
            scheduler_type = result['scheduler_type']
            status = result['status']
            
            if test_id not in test_counts:
                test_counts[test_id] = {
                    'default': {'success': 0, 'failed': 0},
                    'custom': {'success': 0, 'failed': 0}
                }
            
            if status == 'success':
                test_counts[test_id][scheduler_type]['success'] += 1
            else:
                test_counts[test_id][scheduler_type]['failed'] += 1
        
        for test_id, counts in test_counts.items():
            print(f"\n{test_id}:")
            print(f"  Default scheduler: {counts['default']['success']} successful, {counts['default']['failed']} failed")
            print(f"  Custom scheduler: {counts['custom']['success']} successful, {counts['custom']['failed']} failed")

def main():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROCESSING_DIR = os.path.join(BASE_DIR, '..')

    parser = argparse.ArgumentParser(description='Run scheduler tests')
    parser.add_argument('--test-cases', 
                        default=f'{PROCESSING_DIR}/test_cases_parallel.json',
                        help='Path to test cases JSON file')
    parser.add_argument('--schedulers-dir',
                        default=f'{PROCESSING_DIR}/schedulers',
                        help='Path to schedulers directory')
    parser.add_argument('--output-dir',
                        default=f'{PROCESSING_DIR}/scripts/scheduler_test_results',
                        help='Directory to save results')
    parser.add_argument('--no-default', action='store_true',
                        help='Skip tests with default scheduler')
    parser.add_argument('--no-custom', action='store_true',
                        help='Skip tests with custom schedulers')
    parser.add_argument('--runs', type=int, default=3,
                        help='Number of runs per scheduler (default: 2)')
    
    args = parser.parse_args()
    
    # Change to processing directory
    os.chdir(PROCESSING_DIR)
    runner = SchedulerTestRunner(
        args.test_cases,
        args.schedulers_dir,
        args.output_dir
    )
    
    try:
        runner.run_all_tests(
            run_default=not args.no_default,
            run_custom=not args.no_custom,
            runs_per_scheduler=args.runs
        )
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()