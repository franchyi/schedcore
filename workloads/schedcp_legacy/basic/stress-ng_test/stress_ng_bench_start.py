#!/usr/bin/env python3
import argparse
import sys
import os

# Add the scheduler module to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scheduler')))

from stress_ng_tester import StressNgTester

def main():
    parser = argparse.ArgumentParser(description='Run stress-ng benchmark tests with different schedulers')
    parser.add_argument('--duration', type=int, default=30, help='Test duration for each scheduler in seconds (default: 30)')
    parser.add_argument('--cpu-workers', type=int, default=0, help='Number of CPU workers (default: 0 = auto)')
    parser.add_argument('--vm-workers', type=int, default=2, help='Number of VM workers (default: 2)')
    parser.add_argument('--io-workers', type=int, default=2, help='Number of IO workers (default: 2)')
    parser.add_argument('--stress-tests', nargs='+', default=['cpu', 'vm', 'io'], 
                        help='Stress tests to run (default: cpu vm io)')
    parser.add_argument('--output', type=str, default='results/stress_ng_results.json', 
                        help='Output file for results (default: results/stress_ng_results.json)')
    parser.add_argument('--skip-baseline', action='store_true', help='Skip baseline test without scheduler')
    parser.add_argument('--schedulers', nargs='+', help='Specific schedulers to test (default: all)')
    
    args = parser.parse_args()
    
    # Create tester instance
    tester = StressNgTester(
        duration=args.duration,
        cpu_workers=args.cpu_workers,
        vm_workers=args.vm_workers,
        io_workers=args.io_workers,
        stress_tests=args.stress_tests,
        output_file=args.output
    )
    
    # Run tests
    print(f"Starting stress-ng benchmark tests...")
    print(f"Duration: {args.duration}s per scheduler")
    print(f"Stress tests: {', '.join(args.stress_tests)}")
    print(f"Workers - CPU: {args.cpu_workers or 'auto'}, VM: {args.vm_workers}, IO: {args.io_workers}")
    print("-" * 60)
    
    tester.run_all_tests(skip_baseline=args.skip_baseline, specific_schedulers=args.schedulers)
    
    # Generate performance figures
    print("\nGenerating performance comparison figures...")
    tester.generate_performance_figures()
    
    print(f"\nResults saved to: {args.output}")
    print(f"Performance figures saved to: results/")

if __name__ == "__main__":
    main()