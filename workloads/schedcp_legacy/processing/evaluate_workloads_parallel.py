#!/usr/bin/env python3
"""
Enhanced Long-tail Workload Evaluation Framework with Parallel Task Tracking

This framework executes workloads with proper parallel task execution and
tracks completion times for short vs long tasks separately.
"""

import json
import subprocess
import time
import sys
import argparse
from typing import Dict, List, Tuple
import threading
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

class ParallelTaskTracker:
    """Track execution times of parallel tasks"""
    
    def __init__(self):
        self.short_task_times = []
        self.long_task_times = []
        self.lock = threading.Lock()
        
    def add_short_task(self, duration):
        with self.lock:
            self.short_task_times.append(duration)
            
    def add_long_task(self, duration):
        with self.lock:
            self.long_task_times.append(duration)
            
    def get_stats(self):
        with self.lock:
            short_times = self.short_task_times.copy()
            long_times = self.long_task_times.copy()
            
        stats = {
            'short_tasks': {
                'count': len(short_times),
                'total_time': sum(short_times) if short_times else 0,
                'avg_time': sum(short_times) / len(short_times) if short_times else 0,
                'min_time': min(short_times) if short_times else 0,
                'max_time': max(short_times) if short_times else 0,
                'times': short_times
            },
            'long_tasks': {
                'count': len(long_times),
                'total_time': sum(long_times) if long_times else 0,
                'avg_time': sum(long_times) / len(long_times) if long_times else 0,
                'min_time': min(long_times) if long_times else 0,
                'max_time': max(long_times) if long_times else 0,
                'times': long_times
            },
            'imbalance_ratio': max(long_times) / max(short_times) if short_times and long_times and max(short_times) > 0 else 1
        }
        
        return stats

def run_single_task(task_info: Tuple[str, int, str, str]) -> Tuple[str, float, str]:
    """Execute a single task in its own directory and return its type, duration, and output"""
    task_type, task_id, cmd, work_dir = task_info
    start_time = time.time()
    try:
        # Change to task-specific directory
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=work_dir)
        duration = time.time() - start_time
        output = f"{task_type}_{task_id}: {result.stdout[:100]}" if result.stdout else f"{task_type}_{task_id}: completed"
        return task_type, duration, output
    except Exception as e:
        duration = time.time() - start_time
        return task_type, duration, f"{task_type}_{task_id}: error - {str(e)}"

class EnhancedWorkloadEvaluator:
    """Enhanced evaluation framework with parallel execution tracking"""
    
    def __init__(self, config_file: str = "test_cases.json", sequential: bool = False):
        self.config_file = config_file
        self.config = self._load_config()
        self.results = {}
        self.sequential = sequential
        # Load task counts from configuration
        if 'configuration' in self.config:
            cfg = self.config['configuration']
            self.short_tasks = cfg.get('short_tasks', 39)
            self.long_tasks = cfg.get('long_tasks', 1)
        else:
            self.short_tasks = 39
            self.long_tasks = 1
        
    def _load_config(self) -> Dict:
        """Load test configuration from JSON file"""
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Error: Configuration file {self.config_file} not found!")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON configuration: {e}")
            sys.exit(1)
            
    def list_tests(self):
        """List all available tests"""
        print("Available test cases:")
        print("=" * 50)
        
        for test in self.config['test_cases']:
            print(f"ID: {test['id']}")
            print(f"Name: {test['name']}")
            print(f"Category: {test['category']}")
            print(f"Description: {test['description']}")
            print(f"Expected improvement: {test['expected_improvement']*100:.0f}%")
            print(f"Small tasks: {self.short_tasks}")
            print(f"Large tasks: {self.long_tasks}")
            print("-" * 50)
            
    def check_dependencies(self, test_case: Dict) -> Tuple[bool, List[str]]:
        """Check if test dependencies are available"""
        missing_deps = []
        
        for dep in test_case.get('dependencies', []):
            try:
                result = subprocess.run(['which', dep], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode != 0:
                    # Try checking if it's a Python package
                    if dep.startswith('python3-'):
                        package = dep.replace('python3-', '').replace('-', '_')
                        try:
                            import importlib
                            importlib.import_module(package)
                        except ImportError:
                            missing_deps.append(dep)
                    else:
                        missing_deps.append(dep)
            except subprocess.TimeoutExpired:
                missing_deps.append(dep)
                
        return len(missing_deps) == 0, missing_deps
        
    def _run_parallel_workload(self, test_case: Dict) -> Dict:
        """Run workload with proper parallel execution and tracking"""
        import os
        import shutil
        import tempfile
        
        # Use configured values instead of reading from characteristics
        small_tasks = self.short_tasks
        large_tasks = self.long_tasks
        
        # Check if parallel commands are defined in JSON
        if 'small_commands' not in test_case or 'large_commands' not in test_case:
            error_msg = f"Test case '{test_case['id']}' is missing 'small_commands' or 'large_commands' in configuration"
            print(f"ERROR: {error_msg}")
            return {
                'status': 'error',
                'error': error_msg,
                'wall_clock_time': 0
            }
        
        # Create a base temporary directory for this test
        base_dir = tempfile.mkdtemp(prefix=f"test_{test_case['id']}_")
        created_dirs = []
        
        # Store the original working directory
        original_cwd = os.getcwd()
        
        try:
            # Setup phase - create directories and run setup for each task
            all_tasks = []
            
            
            # Setup for small tasks
            small_setup_cmds = test_case.get('small_setup', test_case.get('setup_commands', []))
            for i in range(small_tasks):
                task_dir = os.path.join(base_dir, f"small_{i}")
                os.makedirs(task_dir, exist_ok=True)
                created_dirs.append(task_dir)
                
                # Run setup commands in this directory
                for setup_cmd in small_setup_cmds:
                    if setup_cmd.strip():
                        # Replace $ORIGINAL_CWD with actual path
                        setup_cmd = setup_cmd.replace('$ORIGINAL_CWD', original_cwd)
                        result = subprocess.run(setup_cmd, shell=True, cwd=task_dir, capture_output=True, text=True)
                        if result.returncode != 0:
                            print(f"  Setup failed for small_{i}: {setup_cmd}")
                            print(f"  Error: {result.stderr}")
                
                # Add task with its directory
                for cmd in test_case['small_commands']:
                    all_tasks.append(('small', i, cmd, task_dir))
            
            # Setup for large tasks
            large_setup_cmds = test_case.get('large_setup', test_case.get('setup_commands', []))
            for i in range(large_tasks):
                task_dir = os.path.join(base_dir, f"large_{i}")
                os.makedirs(task_dir, exist_ok=True)
                created_dirs.append(task_dir)
                
                # Run setup commands in this directory
                for setup_cmd in large_setup_cmds:
                    if setup_cmd.strip():
                        # Replace $ORIGINAL_CWD with actual path
                        setup_cmd = setup_cmd.replace('$ORIGINAL_CWD', original_cwd)
                        result = subprocess.run(setup_cmd, shell=True, cwd=task_dir, capture_output=True, text=True)
                        if result.returncode != 0:
                            print(f"  Setup failed for large_{i}: {setup_cmd}")
                            print(f"  Error: {result.stderr}")
                
                # Add task with its directory
                for cmd in test_case['large_commands']:
                    all_tasks.append(('large', i, cmd, task_dir))
            
            # Execute tasks in parallel and track times
            tracker = ParallelTaskTracker()
            
            # Run all tasks in parallel using process pool
            if self.sequential:
                max_workers = 1
            else:
                max_workers = len(all_tasks)
            wall_start = time.time()
            
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_task = {}
                for task_info in all_tasks:
                    task_type, task_id, _, _ = task_info
                    future = executor.submit(run_single_task, task_info)
                    future_to_task[future] = (task_type, task_id)
                    
                # Collect results as they complete
                for future in as_completed(future_to_task):
                    task_type, task_id = future_to_task[future]
                    try:
                        result_type, duration, _ = future.result()
                        if result_type == 'small':
                            tracker.add_short_task(duration)
                        else:
                            tracker.add_long_task(duration)
                        print(f"  Completed {result_type} task {task_id} in {duration:.2f}s")
                    except Exception as e:
                        print(f"  Task {task_type}_{task_id} failed: {e}")
                        
            wall_end = time.time()
            wall_time = wall_end - wall_start
            
            # Get statistics
            stats = tracker.get_stats()
            stats['wall_clock_time'] = wall_time
            stats['execution_mode'] = 'sequential' if self.sequential else 'parallel'
            
            # Calculate completion times
            if stats['short_tasks']['times'] and stats['long_tasks']['times']:
                # All short tasks should complete around the same time in parallel
                # The long task dominates the total completion time
                stats['short_tasks_completion_time'] = max(stats['short_tasks']['times'])
                stats['long_tasks_completion_time'] = max(stats['long_tasks']['times'])
                if not self.sequential:
                    stats['parallel_efficiency'] = (stats['short_tasks']['total_time'] + stats['long_tasks']['total_time']) / (wall_time * max_workers)
            
            return stats
            
        finally:
            # Cleanup all created directories
            print("\nCleaning up task directories...")
            shutil.rmtree(base_dir, ignore_errors=True)
        
    def _run_original_command(self, test_case: Dict) -> Dict:
        """Fallback to run original command when parallel execution not implemented"""
        start_time = time.time()
        try:
            result = subprocess.run(test_case['test_command'], 
                                  shell=True, 
                                  capture_output=True, 
                                  text=True,
                                  timeout=test_case['workload_characteristics']['expected_runtime_seconds'] * 3)
            duration = time.time() - start_time
            return {
                'wall_clock_time': duration,
                'status': 'success' if result.returncode == 0 else 'failed',
                'output': result.stdout[:500] if result.stdout else 'No output',
                'note': 'Parallel tracking not implemented for this test'
            }
        except subprocess.TimeoutExpired:
            return {
                'wall_clock_time': time.time() - start_time,
                'status': 'timeout',
                'note': 'Test timed out'
            }
        except Exception as e:
            return {
                'wall_clock_time': time.time() - start_time,
                'status': 'error',
                'error': str(e)
            }
            
    def run_test(self, test_id: str) -> Dict:
        """Run a specific test case with parallel tracking"""
        # Find test case
        test_case = None
        for test in self.config['test_cases']:
            if test['id'] == test_id:
                test_case = test
                break
                
        if not test_case:
            return {'error': f"Test case '{test_id}' not found"}
            
        print(f"\nRunning test: {test_case['name']}")
        print(f"Description: {test_case['description']}")
        print(f"Tasks: {self.short_tasks} small + {self.long_tasks} large (mode: {'sequential' if self.sequential else 'parallel'})")
        
        # Check dependencies
        deps_ok, missing_deps = self.check_dependencies(test_case)
        if not deps_ok:
            return {
                'error': f"Missing dependencies: {', '.join(missing_deps)}",
                'missing_dependencies': missing_deps
            }
            
        result = {
            'test_id': test_id,
            'test_name': test_case['name'],
            'start_time': time.time(),
        }
        
        # Setup phase
        print("\nRunning setup...")
        setup_start = time.time()
        for cmd in test_case.get('setup_commands', []):
            if cmd.strip():
                print(f"  Setup: {cmd[:80]}...")
                try:
                    subprocess.run(cmd, shell=True, check=True, capture_output=True)
                except subprocess.CalledProcessError as e:
                    result['status'] = 'failed'
                    result['error'] = f"Setup failed: {e}"
                    result['setup_time'] = time.time() - setup_start
                    return result
                    
        result['setup_time'] = time.time() - setup_start
        
        # Main test execution with parallel tracking
        print("\nRunning parallel workload...")
        try:
            parallel_stats = self._run_parallel_workload(test_case)
            result.update({
                'status': 'success',
                'parallel_execution': parallel_stats
            })
        except Exception as e:
            result.update({
                'status': 'error',
                'error': str(e)
            })
            
        # Cleanup is handled in _run_parallel_workload's finally block
        result['total_time'] = time.time() - result['start_time']
        
        return result
        
    def run_all_tests(self) -> Dict:
        """Run all test cases"""
        mode = "sequential" if self.sequential else "parallel"
        print(f"Running all {len(self.config['test_cases'])} test cases in {mode} mode...")
        print("=" * 80)
        
        all_results = {}
        
        for test_case in self.config['test_cases']:
            test_id = test_case['id']
            print(f"\n[{test_id}] Starting test...")
            
            result = self.run_test(test_id)
            all_results[test_id] = result
            
            if result.get('status') == 'success' and 'parallel_execution' in result:
                pe = result['parallel_execution']
                if 'short_tasks_completion_time' in pe and 'long_tasks_completion_time' in pe:
                    print(f"[{test_id}] Short tasks completed in: {pe['short_tasks_completion_time']:.2f}s")
                    print(f"[{test_id}] Long tasks completed in: {pe['long_tasks_completion_time']:.2f}s")
                    print(f"[{test_id}] Imbalance ratio: {pe.get('imbalance_ratio', 0):.1f}x")
                    print(f"[{test_id}] Total wall time: {pe['wall_clock_time']:.2f}s")
                else:
                    print(f"[{test_id}] Completed in {result.get('total_time', 0):.2f}s")
            else:
                print(f"[{test_id}] Status: {result.get('status', 'unknown')}")
                if 'error' in result:
                    print(f"[{test_id}] Error: {result['error']}")
                    
        # Generate summary
        summary = self._generate_summary(all_results)
        
        return {
            'summary': summary,
            'results': all_results
        }
        
    def _generate_summary(self, results: Dict) -> Dict:
        """Generate summary statistics from test results"""
        successful_tests = [r for r in results.values() if r.get('status') == 'success']
        parallel_tests = [r for r in successful_tests if 'parallel_execution' in r and 'short_tasks_completion_time' in r.get('parallel_execution', {})]
        
        summary = {
            'total_tests': len(results),
            'successful_tests': len(successful_tests),
            'parallel_tracked_tests': len(parallel_tests),
            'success_rate': len(successful_tests) / len(results) if results else 0,
        }
        
        if parallel_tests:
            imbalance_ratios = []
            for test in parallel_tests:
                pe = test['parallel_execution']
                if 'imbalance_ratio' in pe:
                    imbalance_ratios.append(pe['imbalance_ratio'])
                    
            if imbalance_ratios:
                summary['avg_imbalance_ratio'] = sum(imbalance_ratios) / len(imbalance_ratios)
                summary['max_imbalance_ratio'] = max(imbalance_ratios)
                
        return summary
        
    def save_results(self, results: Dict, filename: str = None):
        """Save test results to JSON file"""
        if filename is None:
            timestamp = int(time.time())
            filename = f"parallel_test_results_{timestamp}.json"
            
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
            
        print(f"\nResults saved to: {filename}")

def main():
    parser = argparse.ArgumentParser(description='Enhanced Long-tail Workload Evaluation with Parallel Tracking')
    parser.add_argument('--config', default='test_cases_parallel.json', 
                       help='Test configuration file (default: test_cases_parallel.json)')
    parser.add_argument('--list', action='store_true', 
                       help='List all available test cases')
    parser.add_argument('--test', metavar='TEST_ID', 
                       help='Run a specific test case')
    parser.add_argument('--all', action='store_true', 
                       help='Run all test cases')
    parser.add_argument('--save', metavar='FILENAME', 
                       help='Save results to specified file')
    parser.add_argument('--sequential', action='store_true',
                       help='Run tasks sequentially instead of in parallel')
    
    args = parser.parse_args()
    
    evaluator = EnhancedWorkloadEvaluator(args.config, sequential=args.sequential)
    
    if args.list:
        evaluator.list_tests()
        return
        
    if args.test:
        result = evaluator.run_test(args.test)
        print("\nTest Result:")
        print("=" * 40)
        print(json.dumps(result, indent=2))
        
        if args.save:
            evaluator.save_results({'single_test': result}, args.save)
            
    elif args.all:
        results = evaluator.run_all_tests()
        
        print("\n\nSummary:")
        print("=" * 60)
        summary = results['summary']
        print(f"Total tests: {summary['total_tests']}")
        print(f"Successful: {summary['successful_tests']}")
        print(f"With parallel tracking: {summary['parallel_tracked_tests']}")
        print(f"Success rate: {summary['success_rate']*100:.1f}%")
        
        if 'avg_imbalance_ratio' in summary:
            print(f"Average imbalance ratio: {summary['avg_imbalance_ratio']:.1f}x")
            print(f"Maximum imbalance ratio: {summary['max_imbalance_ratio']:.1f}x")
            
        if args.save:
            evaluator.save_results(results, args.save)
        else:
            evaluator.save_results(results)
            
    else:
        # Default to running all tests
        results = evaluator.run_all_tests()
        
        print("\n\nSummary:")
        print("=" * 60)
        summary = results['summary']
        print(f"Total tests: {summary['total_tests']}")
        print(f"Successful: {summary['successful_tests']}")
        print(f"With parallel tracking: {summary['parallel_tracked_tests']}")
        print(f"Success rate: {summary['success_rate']*100:.1f}%")
        
        if 'avg_imbalance_ratio' in summary:
            print(f"Average imbalance ratio: {summary['avg_imbalance_ratio']:.1f}x")
            print(f"Maximum imbalance ratio: {summary['max_imbalance_ratio']:.1f}x")
            
        if args.save:
            evaluator.save_results(results, args.save)
        else:
            evaluator.save_results(results)

if __name__ == '__main__':
    main()