#!/bin/bash
# Install dependencies for long-tail workload tests

set -e

echo "Installing dependencies for long-tail workload tests..."

# Update package lists
echo "Updating package lists..."
sudo apt-get update -qq

# Core utilities (usually already installed)
echo "Installing core utilities..."
sudo apt-get install -y \
    coreutils \
    git \
    parallel \
    gzip

# Media processing
echo "Installing media processing tools..."
sudo apt-get install -y \
    ffmpeg \
    pigz

# Compression tools
echo "Installing compression tools..."
sudo apt-get install -y \
    zstd

# Python and testing tools
echo "Installing Python and testing tools..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-pytest \
    python3-pytest-xdist \
    python3-pandas \
    python3-numpy

# Development tools
echo "Installing development tools..."
sudo apt-get install -y \
    g++ \
    make \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libgit2-dev

# Optional: DuckDB (if available in repos)
echo "Attempting to install DuckDB..."
if apt-cache search duckdb | grep -q duckdb; then
    sudo apt-get install -y duckdb
else
    echo "DuckDB not available in repositories, skipping..."
fi

# Optional: Install missing Python packages via pip
echo "Installing additional Python packages..."
python3 -m pip install --user --upgrade \
    psutil \
    multiprocess || echo "Some pip packages install failed, continuing..."

echo ""
echo "Dependency installation complete!"
echo ""
echo "Installed packages:"
echo "✓ Core utilities: coreutils, git, parallel, gzip"
echo "✓ Media processing: ffmpeg, pigz"
echo "✓ Compression: zstd"
echo "✓ Python: python3, pytest, pandas, numpy"
echo "✓ Development: g++, make, FFmpeg libraries (libavcodec-dev, libavformat-dev, libavutil-dev, libswscale-dev), libgit2-dev"
echo ""
echo "Optional packages attempted:"
echo "- DuckDB (may not be available)"
echo ""
echo "You can now run the test framework with:"
echo "  python3 evaluate_workloads.py"