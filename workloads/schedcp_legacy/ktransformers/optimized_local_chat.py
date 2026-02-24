#!/usr/bin/env python3
"""
Optimized local chat script that runs with LD_PRELOAD=./liba.so
This script wraps the ktransformers local_chat functionality with preloaded optimization library.
"""

import os
import sys
import subprocess
import argparse

def main():
    """Main function to run optimized local chat with LD_PRELOAD."""
    parser = argparse.ArgumentParser(description='Run optimized local chat with LD_PRELOAD')
    parser.add_argument('--model_path', type=str, default='unsloth/DeepSeek-R1', 
                       help='Path to the model')
    parser.add_argument('--gguf_path', type=str, default='/root/deepseek-gguf/',
                       help='Path to GGUF files')
    parser.add_argument('--optimize_config_path', type=str, 
                       default='optimize/optimize_rules/DeepSeek-V3-Chat-int8-fast.yaml',
                       help='Path to optimization config')
    parser.add_argument('--batch_size', type=int, default=32,
                       help='Batch size for processing')
    parser.add_argument('--speculative_length', type=int, default=6,
                       help='Speculative decoding length')
    
    args = parser.parse_args()
    
    # Prepare the command with LD_PRELOAD
    env = os.environ.copy()
    env['LD_PRELOAD'] = './liba.so'
    
    # Build the command
    cmd = [
        sys.executable,
        'optimized_local_chat.py',
        f'--model_path={args.model_path}',
        f'--gguf_path={args.gguf_path}',
        f'--optimize_config_path={args.optimize_config_path}',
        f'--batch_size={args.batch_size}',
        f'--speculative_length={args.speculative_length}'
    ]
    
    print(f"Running command with LD_PRELOAD=./liba.so:")
    print(f"Command: {' '.join(cmd)}")
    print(f"Environment: LD_PRELOAD={env.get('LD_PRELOAD', 'Not set')}")
    
    # Execute the command
    try:
        result = subprocess.run(cmd, env=env, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        return e.returncode
    except FileNotFoundError:
        print("Error: optimized_local_chat.py not found. Please ensure the script exists.")
        return 1

if __name__ == "__main__":
    sys.exit(main())