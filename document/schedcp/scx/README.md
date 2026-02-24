# SCX (Sched_ext) Framework Documentation

## Overview

This directory contains comprehensive documentation for the sched_ext (SCX) framework, a revolutionary Linux kernel scheduling infrastructure that enables safe, dynamic implementation of custom schedulers using BPF technology.

## Documentation Structure

### 1. [Framework Overview](01-overview.md)
- Introduction to sched_ext
- Architecture and core components
- Key features and benefits
- Project structure
- Use cases and getting started

### 2. [Schedulers Analysis](02-schedulers-analysis.md)
- Detailed analysis of all 20 schedulers
- C scheduler implementations (8 schedulers)
- Rust scheduler implementations (12 schedulers)
- Performance characteristics comparison
- Selection guide by workload type

### 3. [Tools and Utilities](03-tools-and-utilities.md)
- scxtop - Real-time performance monitor
- scxctl - Command-line control interface
- scx_loader - DBUS service for scheduler management
- Additional utilities and development tools
- System integration and automation

### 4. [Build System Infrastructure](04-build-system-infrastructure.md)
- Dependencies and requirements
- Meson build system architecture
- Building C and Rust schedulers
- Installation and packaging
- Advanced configuration options
- Troubleshooting guide

### 5. [BPF Framework and Kernel Integration](05-bpf-framework-kernel-integration.md)
- BPF programming model
- Kernel interfaces (kfuncs)
- BPF libraries and utilities
- Safety and verification mechanisms
- Data structures and maps
- Advanced features and best practices

### 6. [Testing and Benchmarking](06-testing-benchmarking-infrastructure.md)
- Testing framework (scxtest)
- Unit and integration testing
- Stress testing infrastructure
- Performance analysis tools
- CI/CD integration
- Debugging and validation

### 7. [Summary and Conclusions](07-summary-and-conclusions.md)
- Executive summary
- Key capabilities overview
- Production readiness assessment
- Use case recommendations
- Future directions
- Final conclusions and recommendations

## Quick Start Guide

### For Users

1. **Check Requirements**:
   - Linux kernel 6.12+ with CONFIG_SCHED_EXT
   - Root privileges for scheduler operations

2. **Install Schedulers**:
   ```bash
   # Build and install
   meson setup build
   meson compile -C build
   sudo meson install -C build
   ```

3. **Start a Scheduler**:
   ```bash
   # For gaming/interactive use
   sudo scxctl start -s scx_lavd -m gaming
   
   # For general server use
   sudo scxctl start -s scx_rusty -m server
   ```

4. **Monitor Performance**:
   ```bash
   sudo scxtop
   ```

### For Developers

1. **Set Up Development Environment**:
   - Install Clang 16+ and Rust toolchain
   - Clone the repository
   - Review the [BPF Framework documentation](05-bpf-framework-kernel-integration.md)

2. **Study Existing Schedulers**:
   - Start with `scx_simple` for basic concepts
   - Review [Schedulers Analysis](02-schedulers-analysis.md)

3. **Develop and Test**:
   - Use the testing framework described in [Testing Infrastructure](06-testing-benchmarking-infrastructure.md)
   - Follow best practices from the BPF documentation

## Key Resources

### Documentation
- [Official README](https://github.com/sched-ext/scx)
- [Kernel Documentation](https://docs.kernel.org/scheduler/sched-ext.html)
- [BPF Documentation](https://docs.kernel.org/bpf/)

### Tools
- **scxtop**: Real-time monitoring
- **scxctl**: Scheduler control
- **bpftool**: BPF program inspection

### Community
- GitHub: https://github.com/sched-ext/scx
- Mailing List: linux-kernel@vger.kernel.org
- Bug Reports: GitHub Issues

## Production-Ready Schedulers

| Scheduler | Type | Best For |
|-----------|------|----------|
| scx_rusty | Rust | General purpose, mixed workloads |
| scx_lavd | Rust | Gaming, interactive desktop |
| scx_bpfland | Rust | Desktop responsiveness |
| scx_layered | Rust | Complex configurations |
| scx_flatcg | C | Container workloads |
| scx_simple | C | Simple workloads, baseline |

## License

The SCX framework is licensed under GPL-2.0. See the LICENSE file in the repository for details.

## Contributing

Contributions are welcome! Please:
1. Read the developer documentation
2. Test thoroughly using the provided infrastructure
3. Follow the coding standards
4. Submit pull requests with clear descriptions

## Acknowledgments

The sched_ext framework is the result of collaboration between kernel developers, BPF experts, and the broader Linux community. Special thanks to all contributors who have made this innovative scheduling framework possible.