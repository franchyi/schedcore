# SCX (Sched_ext) Framework Overview

## Table of Contents
1. [Introduction](#introduction)
2. [Architecture](#architecture)
3. [Key Features](#key-features)
4. [Project Structure](#project-structure)
5. [Benefits](#benefits)

## Introduction

The SCX (sched_ext) project is a revolutionary Linux kernel scheduling framework that enables the development and deployment of custom schedulers as BPF (Berkeley Packet Filter) programs. This framework represents a significant advancement in Linux scheduling, allowing rapid experimentation and deployment of custom scheduling policies without modifying the kernel itself.

### What is sched_ext?

Sched_ext is a Linux kernel feature that provides a safe and flexible way to implement custom CPU schedulers using BPF. It allows developers to:
- Write schedulers in C or Rust
- Load them dynamically at runtime
- Switch between different scheduling policies without rebooting
- Experiment with novel scheduling algorithms safely

## Architecture

### Core Components

1. **Kernel Framework**
   - BPF hooks for scheduling decisions
   - Safety guarantees through BPF verification
   - Fallback mechanisms to prevent system hangs
   - Integration with existing Linux scheduling infrastructure

2. **BPF Schedulers**
   - Kernel-side BPF programs implementing scheduling logic
   - Access to kernel scheduling data structures
   - Event-driven programming model
   - Per-CPU and global scheduling queues

3. **Userspace Components**
   - Loader programs that manage BPF schedulers
   - Configuration and tuning interfaces
   - Statistics collection and monitoring
   - Dynamic parameter adjustment

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Space                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Scheduler   │  │   scxtop     │  │   scxctl     │     │
│  │   Loader     │  │ (monitoring) │  │  (control)   │     │
│  └──────┬───────┘  └──────────────┘  └──────────────┘     │
│         │                                                    │
├─────────┼───────────────────────────────────────────────────┤
│         │              Kernel Space                          │
│         │                                                    │
│    ┌────▼─────────────────────────────────────┐            │
│    │         BPF Scheduler Program             │            │
│    │  ┌─────────────┐  ┌─────────────┐       │            │
│    │  │   Enqueue   │  │   Dispatch  │       │            │
│    │  │   Logic     │  │   Logic     │       │            │
│    │  └─────────────┘  └─────────────┘       │            │
│    └────────────────┬─────────────────────────┘            │
│                     │                                        │
│    ┌────────────────▼─────────────────────────┐            │
│    │          sched_ext Framework             │            │
│    │  ┌─────────────┐  ┌─────────────┐       │            │
│    │  │  BPF Hooks  │  │  Safety     │       │            │
│    │  │             │  │  Checks     │       │            │
│    │  └─────────────┘  └─────────────┘       │            │
│    └──────────────────────────────────────────┘            │
│                                                             │
│    ┌──────────────────────────────────────────┐            │
│    │       Linux Kernel Scheduler Core        │            │
│    └──────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Safety and Reliability
- **BPF Verification**: All scheduler code is verified before loading
- **Automatic Fallback**: System falls back to default scheduler on errors
- **Watchdog Protection**: Prevents scheduler from hanging the system
- **Resource Limits**: BPF programs have bounded execution time

### 2. Flexibility
- **Runtime Loading**: Switch schedulers without rebooting
- **Hot Reloading**: Update scheduler parameters on the fly
- **Multiple Languages**: Support for C and Rust implementations
- **Custom Policies**: Implement any scheduling algorithm

### 3. Performance
- **Low Overhead**: BPF JIT compilation for native performance
- **Direct Kernel Access**: No context switching to userspace
- **Efficient Data Structures**: Optimized BPF maps and arrays
- **Per-CPU Operations**: Minimize cache contention

### 4. Observability
- **Built-in Statistics**: Comprehensive scheduling metrics
- **Real-time Monitoring**: Tools like scxtop for live analysis
- **Tracing Integration**: BPF tracing for deep insights
- **Custom Metrics**: Define scheduler-specific statistics

## Project Structure

### Directory Organization

```
scx/
├── scheds/              # Scheduler implementations
│   ├── c/              # C-based schedulers
│   ├── rust/           # Rust-based schedulers
│   └── include/        # Shared headers
├── rust/               # Rust support libraries
│   ├── scx_utils/      # Common utilities
│   ├── scx_stats/      # Statistics framework
│   └── scx_loader/     # DBUS loader interface
├── tools/              # Management utilities
│   ├── scxtop/         # Performance monitor
│   └── scxctl/         # Control utility
├── lib/                # BPF libraries
│   └── scxtest/        # Testing framework
├── services/           # System service files
└── scripts/            # Utility scripts
```

### Core Libraries

1. **scx_utils**: Common utilities for Rust schedulers
2. **libbpf-rs**: Rust bindings for libbpf
3. **scx_stats**: Statistics collection framework
4. **scx_rustland_core**: Userspace scheduling support

### Build System

- **Meson**: Primary build system for C components
- **Cargo**: Rust package manager and build tool
- **Hybrid Build**: Unified build process for both languages

## Benefits

### 1. Rapid Development
- Iterate on scheduling algorithms quickly
- Test in production-like environments
- No kernel recompilation needed

### 2. Workload Optimization
- Tailor scheduling to specific workloads
- Optimize for latency, throughput, or fairness
- Domain-specific scheduling policies

### 3. Research and Experimentation
- Implement academic scheduling algorithms
- A/B test different policies
- Gather real-world performance data

### 4. Production Deployment
- Several schedulers are production-ready
- Safe rollback mechanisms
- Gradual rollout capabilities

### 5. Community Innovation
- Open source development model
- Contributions from industry and academia
- Shared knowledge and best practices

## Use Cases

1. **Gaming and Interactive Workloads**
   - Low-latency scheduling for better responsiveness
   - Prioritize foreground applications
   - Reduce input lag

2. **Server and Cloud Computing**
   - Optimize for throughput
   - Container-aware scheduling
   - NUMA optimization

3. **Real-time Applications**
   - Predictable latency guarantees
   - Deadline-based scheduling
   - Priority inheritance

4. **Energy Efficiency**
   - Frequency-aware scheduling
   - Core parking strategies
   - Thermal management

5. **Security and Isolation**
   - Prevent side-channel attacks
   - Core isolation for sensitive workloads
   - Cgroup enforcement

## Getting Started

To start using sched_ext schedulers:

1. Ensure kernel support (Linux 6.12+)
2. Install required dependencies
3. Build the schedulers
4. Load a scheduler with appropriate parameters
5. Monitor performance with scxtop

The framework provides a gentle learning curve, from simple FIFO schedulers to complex multi-domain implementations, making it accessible to both beginners and experts in kernel scheduling.