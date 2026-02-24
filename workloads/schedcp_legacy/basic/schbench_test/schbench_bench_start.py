#!/usr/bin/env python3
"""
Scheduler Performance Testing Script using schbench
Tests all available schedulers in the schedcp project and generates performance figures.
"""

import os
import sys
import argparse
from pathlib import Path

# Add the scheduler module to the path (relative to repository root)
repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(repo_root))

from schbench_tester import SchbenchTester

def main():
    parser = argparse.ArgumentParser(description="Test schedulers with schbench")
    parser.add_argument("--schbench-path", default="../schbench/schbench", 
                       help="Path to schbench binary")
    parser.add_argument("--results-dir", default="results", 
                       help="Directory to store results")
    parser.add_argument("--production-only", action="store_true", 
                       help="Test only production schedulers")
    parser.add_argument("--runtime", type=int, default=30, 
                       help="Test runtime in seconds")
    parser.add_argument("--message-threads", type=int, default=2, 
                       help="Number of message threads")
    parser.add_argument("--message-groups", type=int, default=4, 
                       help="Number of message groups")
    
    args = parser.parse_args()
    
    # Create tester instance
    tester = SchbenchTester(args.schbench_path, args.results_dir)
    
    # Update test parameters
    tester.set_test_params(
        runtime=args.runtime,
        message_threads=args.message_threads,
        message_groups=args.message_groups,
    )
    
    # Check if schbench exists
    if not os.path.exists(args.schbench_path):
        print(f"Error: schbench not found at {args.schbench_path}")
        print("Please build schbench first or specify correct path with --schbench-path")
        sys.exit(1)
    
    # Run tests
    print("Starting scheduler performance tests...")
    results = tester.run_all_schbench_tests(production_only=args.production_only)
    
    # Generate figures
    tester.generate_performance_figures(results)
    
    print("\nTesting complete!")

if __name__ == "__main__":
    main()