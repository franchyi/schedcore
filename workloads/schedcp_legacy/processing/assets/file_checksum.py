#!/usr/bin/env python3
"""
File checksum calculator for parallel file system operations test.
Calculates SHA256 checksum of a specified file.
"""

import sys
import hashlib
import os
import time

def calculate_sha256(filepath):
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    
    # Read file in chunks to handle large files efficiently
    with open(filepath, "rb") as f:
        # Read in 64KB chunks
        for chunk in iter(lambda: f.read(65536), b""):
            sha256_hash.update(chunk)
    
    return sha256_hash.hexdigest()

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <filepath>", file=sys.stderr)
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    # Check if file exists
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found", file=sys.stderr)
        sys.exit(1)
    
    # Get file size for reporting
    file_size = os.path.getsize(filepath)
    
    # Calculate checksum
    start_time = time.time()
    checksum1 = calculate_sha256(filepath)
    checksum2 = calculate_sha256(filepath)
    end_time = time.time()
    
    # Output in same format as sha256sum command
    print(f"{checksum1} {checksum2}  {filepath}")
    
    # Report processing time to stderr (optional, for debugging)
    # print(f"# Processed {file_size / (1024*1024):.2f} MB in {end_time - start_time:.2f} seconds", file=sys.stderr)

if __name__ == "__main__":
    main()