#!/usr/bin/env python3
import argparse
import sys
import os

# Add the scheduler module to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scheduler')))

from linux_build_tester import LinuxBuildTester

def main():
    parser = argparse.ArgumentParser(description='Run Linux kernel build benchmark with different schedulers')
    parser.add_argument('--jobs', type=int, default=172, 
                        help='Number of parallel build jobs (default: 0 = auto/nproc)')
    parser.add_argument('--config', type=str, default='allyesconfig', 
                        help='Kernel config to use (default: tinyconfig, options: defconfig, tinyconfig, allnoconfig)')
    parser.add_argument('--clean-between', action='store_true', 
                        help='Clean build artifacts between scheduler tests')
    parser.add_argument('--output', type=str, default='results/linux_build_results.json', 
                        help='Output file for results (default: results/linux_build_results.json)')
    parser.add_argument('--skip-baseline', action='store_true', 
                        help='Skip baseline test without scheduler')
    parser.add_argument('--schedulers', nargs='+', 
                        help='Specific schedulers to test (default: all)')
    parser.add_argument('--repeat', type=int, default=1, 
                        help='Number of times to repeat each test (default: 1)')
    parser.add_argument('--kernel-dir', type=str, default='linux', 
                        help='Directory containing Linux kernel source (default: linux)')
    
    args = parser.parse_args()
    
    # Create tester instance
    tester = LinuxBuildTester(
        jobs=args.jobs,
        config=args.config,
        clean_between=args.clean_between,
        output_file=args.output,
        repeat=args.repeat,
        kernel_dir=args.kernel_dir
    )
    
    # Run tests
    print(f"Starting Linux kernel build benchmark...")
    print(f"Config: {args.config}")
    print(f"Jobs: {args.jobs or 'auto (nproc)'}")
    print(f"Clean between tests: {args.clean_between}")
    print(f"Repeat count: {args.repeat}")
    print("-" * 60)
    
    # Configure kernel if needed
    if not tester.check_kernel_configured():
        print("Configuring kernel first...")
        tester.configure_kernel()
    
    # Run benchmark tests
    tester.run_all_tests(skip_baseline=args.skip_baseline, specific_schedulers=args.schedulers)
    
    # Generate performance figures
    print("\nGenerating performance comparison figures...")
    tester.generate_performance_figures()
    
    print(f"\nResults saved to: {args.output}")
    print(f"Performance figures saved to: results/")

if __name__ == "__main__":
    main()