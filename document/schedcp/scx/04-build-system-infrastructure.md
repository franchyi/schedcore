# Build System and Infrastructure

## Table of Contents
1. [Overview](#overview)
2. [Dependencies and Requirements](#dependencies-and-requirements)
3. [Build System Architecture](#build-system-architecture)
4. [Building Schedulers](#building-schedulers)
5. [Installation and Packaging](#installation-and-packaging)
6. [Advanced Build Configuration](#advanced-build-configuration)
7. [Troubleshooting](#troubleshooting)

## Overview

The SCX project uses a sophisticated hybrid build system that combines Meson for C components and Cargo for Rust components. This system handles the complexity of building BPF programs, generating skeleton headers, and creating userspace binaries for both C and Rust schedulers.

### Key Features

- **Unified Build**: Single command builds all schedulers
- **Automatic Dependencies**: Downloads and builds libbpf/bpftool if needed
- **Cross-language Support**: Seamlessly builds C and Rust components
- **BPF Integration**: Handles BPF compilation and skeleton generation
- **Distribution Support**: Packaging for multiple Linux distributions

## Dependencies and Requirements

### Mandatory Dependencies

| Component | Version | Purpose |
|-----------|---------|---------|
| Linux Kernel | 6.12+ | sched_ext support |
| Clang/LLVM | 16+ (17 recommended) | BPF compilation |
| Meson | 1.2.0+ | Build system |
| Python | 3.6+ | Build scripts |
| libelf | Any | ELF manipulation |
| zlib | Any | Compression |
| pkg-config | Any | Library detection |

### Optional Dependencies

| Component | Version | Purpose |
|-----------|---------|---------|
| Rust | 1.82+ | Rust schedulers |
| libbpf | 1.4+ | BPF library (auto-built if missing) |
| bpftool | 7.5+ | BPF tool (auto-built if missing) |
| systemd | Any | Service integration |
| openrc | Any | Service integration |
| libzstd | Any | Additional compression |

### Installing Dependencies

**Ubuntu/Debian**:
```bash
sudo apt install meson clang llvm libelf-dev zlib1g-dev pkg-config cargo
```

**Fedora/RHEL**:
```bash
sudo dnf install meson clang llvm elfutils-libelf-devel zlib-devel pkgconfig cargo
```

**Arch Linux**:
```bash
sudo pacman -S meson clang llvm libelf zlib pkgconf rust
```

## Build System Architecture

### Directory Structure

```
scx/
├── meson.build              # Main build configuration
├── meson.options            # Build options
├── Cargo.toml              # Rust workspace
├── meson-scripts/          # Custom build scripts
│   ├── fetch_libbpf        # Download libbpf
│   ├── build_libbpf        # Build libbpf
│   ├── fetch_bpftool       # Download bpftool
│   ├── build_bpftool       # Build bpftool
│   └── bpftool_build_skel  # Generate BPF skeletons
├── scheds/                 # Scheduler sources
│   ├── c/                  # C schedulers
│   └── rust/               # Rust schedulers
└── rust/                   # Rust libraries
```

### Build Flow

```
┌─────────────────┐
│  meson setup    │
│   build dir     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Detect/Build    │     │   Configure     │
│ Dependencies    │────►│   Compilers     │
│ (libbpf, etc)   │     │   and Flags     │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  Process Each   │
                        │   Scheduler     │
                        └────────┬────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Compile BPF     │     │ Generate BPF    │     │ Build Userspace │
│ (.bpf.c → .o)   │────►│ Skeleton        │────►│    Binary       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### BPF Compilation Process

1. **BPF Object Compilation**:
   ```bash
   clang -g -O2 -Wall -mcpu=v3 \
         -D__TARGET_ARCH_x86 \
         -I/include \
         -target bpf \
         -c scheduler.bpf.c -o scheduler.bpf.o
   ```

2. **Skeleton Generation**:
   ```bash
   # First pass
   bpftool gen object scheduler.bpf.l1o.o scheduler.bpf.o
   
   # Second pass
   bpftool gen object scheduler.bpf.l2o.o scheduler.bpf.l1o.o
   
   # Final skeleton
   bpftool gen skeleton scheduler.bpf.l2o.o > scheduler.skel.h
   ```

3. **Userspace Compilation**:
   ```bash
   gcc -o scheduler scheduler.c -lbpf -lelf -lz
   ```

## Building Schedulers

### Basic Build Commands

```bash
# Setup build directory
meson setup build

# Build all schedulers
meson compile -C build

# Install schedulers
sudo meson install -C build
```

### Build Options

```bash
# Disable Rust schedulers
meson setup build -Denable_rust=false

# Use system libbpf
meson setup build -Dlibbpf_a=/usr/lib/libbpf.a

# Offline build (no downloads)
meson setup build -Doffline=true

# Custom clang for BPF
meson setup build -Dbpf_clang=clang-17
```

### Building Individual Components

```bash
# Build specific C scheduler
meson compile -C build scx_simple

# Build specific Rust scheduler
cd scheds/rust/scx_rusty && cargo build --release

# Build only tools
meson compile -C build scxtop scxctl
```

### Rust-specific Build

The Rust components use a workspace configuration:

```toml
# Root Cargo.toml
[workspace]
members = [
    "rust/*",
    "scheds/rust/*",
]

[profile.release]
lto = "thin"

[profile.release-fast]
inherits = "release"
opt-level = 3
lto = "fat"
codegen-units = 1
```

Build commands:
```bash
# Build all Rust components
cargo build --release

# Build with native CPU optimization
cargo build --profile release-fast

# Build specific scheduler
cargo build -p scx_rusty --release
```

## Installation and Packaging

### Installation Paths

| Component | Default Path |
|-----------|--------------|
| Scheduler binaries | `/usr/local/bin/` |
| Development headers | `/usr/local/include/scx/` |
| Systemd services | `/usr/lib/systemd/system/` |
| D-Bus services | `/usr/share/dbus-1/system-services/` |
| Default config | `/etc/default/scx` |

### Manual Installation

```bash
# Standard installation
sudo meson install -C build

# Custom prefix
meson setup build --prefix=/opt/scx
sudo meson install -C build

# Development installation
meson setup build --prefix=$HOME/.local
meson install -C build
```

### Distribution Packages

**Creating DEB package**:
```bash
# Install packaging tools
sudo apt install devscripts debhelper

# Build package
debuild -us -uc -b
```

**Creating RPM package**:
```bash
# Install packaging tools
sudo dnf install rpm-build

# Build package
rpmbuild -bb scx.spec
```

**Arch Linux PKGBUILD**:
```bash
# In PKGBUILD directory
makepkg -si
```

### Service Integration

**Systemd**:
```bash
# Enable default scheduler at boot
sudo systemctl enable scx.service

# Configure default scheduler
sudo cat > /etc/default/scx << EOF
SCX_SCHEDULER="scx_rusty"
SCX_FLAGS="--slice-us 20000"
EOF
```

**OpenRC**:
```bash
# Add to default runlevel
sudo rc-update add scx default

# Configure
sudo vi /etc/conf.d/scx
```

## Advanced Build Configuration

### Cross-compilation

```bash
# Setup cross-compilation
meson setup build \
    --cross-file cross-aarch64.txt \
    -Dbpf_clang=clang \
    -Denable_rust=false
```

Cross-file example (`cross-aarch64.txt`):
```ini
[binaries]
c = 'aarch64-linux-gnu-gcc'
ar = 'aarch64-linux-gnu-ar'
strip = 'aarch64-linux-gnu-strip'

[host_machine]
system = 'linux'
cpu_family = 'aarch64'
cpu = 'aarch64'
endian = 'little'
```

### Custom BPF Flags

Edit `meson.build` or use environment variables:
```bash
# Extra BPF flags
export BPF_CFLAGS="-DDEBUG -DVERBOSE"
meson setup build

# Custom optimization
meson setup build -Dbpf_clang_flags="-O3 -mcpu=v4"
```

### Development Build

```bash
# Debug build with sanitizers
meson setup build \
    --buildtype=debug \
    -Db_sanitize=address,undefined

# Generate compile_commands.json for IDEs
meson setup build
ln -s build/compile_commands.json .
```

### Building with Custom libbpf

```bash
# Build custom libbpf
git clone https://github.com/libbpf/libbpf
cd libbpf/src
make

# Use in SCX build
meson setup build \
    -Dlibbpf_a=/path/to/libbpf/src/libbpf.a \
    -Dlibbpf_h=/path/to/libbpf/src
```

## Troubleshooting

### Common Build Issues

**1. BPF Compilation Errors**
```bash
# Error: unknown target triple 'bpf'
# Solution: Install newer clang
sudo apt install clang-17

# Use specific clang
meson setup build -Dbpf_clang=clang-17
```

**2. Missing vmlinux.h**
```bash
# Error: fatal error: 'vmlinux.h' file not found
# Solution: Check architecture
uname -m  # Should match available vmlinux.h files
```

**3. Rust Build Failures**
```bash
# Error: could not compile `scx_utils`
# Solution: Update Rust toolchain
rustup update
rustup default stable
```

**4. libbpf Version Mismatch**
```bash
# Error: libbpf version too old
# Solution: Let build system fetch it
meson setup build -Dlibbpf_a='' -Dbpftool=''
```

### Build System Debugging

```bash
# Verbose build output
meson compile -C build -v

# Check configuration
meson configure build

# Clean rebuild
meson setup --wipe build
meson compile -C build

# Check dependencies
meson introspect build --dependencies
```

### Performance Optimization

```bash
# LTO build for better performance
meson setup build \
    --buildtype=release \
    -Db_lto=true

# Native CPU optimization
RUSTFLAGS="-C target-cpu=native" \
    meson setup build

# Profile-guided optimization
meson setup build --buildtype=release
meson compile -C build
# Run workloads to generate profile
meson setup --reconfigure build -Db_pgo=use
meson compile -C build
```

## Build System Internals

### Meson Custom Functions

The build system defines several custom functions:

1. **`gen_bpf_o`**: Compiles `.bpf.c` to BPF object
2. **`gen_bpf_skel`**: Generates skeleton headers
3. **`fetch_libbpf_commit`**: Downloads specific libbpf version
4. **`build_libbpf`**: Builds libbpf library

### Architecture Detection

```python
arch_dict = {
    'x86_64': 'x86',
    'aarch64': 'arm64',
    's390x': 's390',
    'ppc64': 'powerpc',
}
```

### Dependency Resolution

1. Check for system packages
2. Fall back to building from source
3. Cache built dependencies
4. Validate versions

The build system provides a robust, flexible infrastructure for building complex BPF-based schedulers while maintaining ease of use for developers and packagers.