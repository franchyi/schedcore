#!/usr/bin/env python3
"""
File compression utility for parallel compression test.
Compresses a file using gzip with maximum compression level.
"""

import sys
import gzip
import os
import shutil
import time

def compress_file(input_path, compression_level=9):
    """Compress a file using gzip with specified compression level."""
    output_path = input_path + '.gz'
    
    # Read and compress the file
    with open(input_path, 'rb') as f_in:
        with gzip.open(output_path, 'wb', compresslevel=compression_level) as f_out:
            # Copy in chunks to handle large files efficiently
            shutil.copyfileobj(f_in, f_out, length=65536)
    
    return output_path

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <filepath> [compression_level]", file=sys.stderr)
        print("compression_level: 1-9 (default: 9 for maximum compression)", file=sys.stderr)
        sys.exit(1)
    
    filepath = sys.argv[1]
    compression_level = 9  # Default to maximum compression like pigz -9
    
    if len(sys.argv) > 2:
        try:
            compression_level = int(sys.argv[2])
            if not 1 <= compression_level <= 9:
                raise ValueError
        except ValueError:
            print(f"Error: Compression level must be between 1 and 9", file=sys.stderr)
            sys.exit(1)
    
    # Check if file exists
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found", file=sys.stderr)
        sys.exit(1)
    
    # Get file size for reporting
    file_size = os.path.getsize(filepath)
    
    # Compress the file
    start_time = time.time()
    try:
        output_path = compress_file(filepath, compression_level)
        end_time = time.time()
        
        # Get compressed file size
        compressed_size = os.path.getsize(output_path)
        compression_ratio = (1 - compressed_size / file_size) * 100
        
        # Output similar to pigz
        print(f"Compressed {filepath} -> {output_path}")
        print(f"Original: {file_size:,} bytes, Compressed: {compressed_size:,} bytes")
        print(f"Compression ratio: {compression_ratio:.1f}%")
        
    except Exception as e:
        print(f"Error compressing file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()