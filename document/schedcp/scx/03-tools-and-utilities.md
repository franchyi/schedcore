# SCX Tools and Utilities

## Table of Contents
1. [Overview](#overview)
2. [scxtop - Performance Monitor](#scxtop---performance-monitor)
3. [scxctl - Command Line Control](#scxctl---command-line-control)
4. [scx_loader - DBUS Service](#scx_loader---dbus-service)
5. [Additional Utilities](#additional-utilities)
6. [Tool Integration](#tool-integration)

## Overview

The SCX framework provides a comprehensive set of tools for managing, monitoring, and controlling BPF-based schedulers. These tools form a complete ecosystem that enables users to effectively deploy and operate custom schedulers in production environments.

### Tool Categories

1. **Control Tools**: Start, stop, and switch schedulers
2. **Monitoring Tools**: Real-time performance analysis
3. **Service Infrastructure**: System integration via DBUS
4. **Development Tools**: Helper utilities for scheduler development

## scxtop - Performance Monitor

### Overview

`scxtop` is a sophisticated terminal-based monitoring tool specifically designed for sched_ext schedulers. It provides real-time insights into scheduler behavior, performance metrics, and system-wide scheduling statistics.

### Features

#### 1. Real-time Monitoring
- **Live Statistics**: Updates every second by default
- **BPF Integration**: Direct kernel metrics via BPF
- **Low Overhead**: Minimal impact on system performance
- **Multiple Views**: Different perspectives on scheduler behavior

#### 2. View Modes
- **Bar Chart View**: Visual representation of CPU utilization
- **Sparkline View**: Time-series visualization
- **Per-CPU View**: Individual CPU statistics
- **LLC View**: Last-Level Cache aggregated stats
- **NUMA View**: NUMA node aggregated metrics
- **Scheduler Stats**: Custom scheduler-specific metrics

#### 3. Advanced Features
- **Perfetto Tracing**: Generate detailed trace files
- **Configuration**: Customizable via config files
- **Keybindings**: User-defined shortcuts
- **Theme Support**: Visual customization

### Usage Examples

```bash
# Basic usage (requires root)
sudo scxtop

# Specify update interval (500ms)
sudo scxtop -i 500

# Generate trace file
sudo scxtop trace -d 1000 -w 5000 -o scheduler_trace.pftrace

# Generate shell completions
scxtop generate-completions --shell bash > /etc/bash_completion.d/scxtop

# Use custom config file
scxtop --config ~/.config/scxtop/custom.toml
```

### Key Bindings

| Key | Action |
|-----|--------|
| `h` | Show help menu |
| `q` | Quit |
| `v` | Switch view mode |
| `s` | Toggle scheduler stats |
| `l` | LLC aggregated view |
| `n` | NUMA node view |
| `P` | Start/stop trace recording |
| `S` | Save current configuration |
| `↑/↓` | Navigate CPU list |
| `PgUp/PgDn` | Page navigation |

### Configuration

Location: `~/.config/scxtop/config.toml`

```toml
[app]
update_interval = 1000  # milliseconds

[theme]
style = "dark"

[keybindings]
quit = "q"
help = "h"
switch_view = "v"
```

### Metrics Displayed

1. **System Metrics**:
   - Total CPU utilization
   - Scheduler overhead
   - Context switch rate
   - Migration count

2. **Per-CPU Metrics**:
   - Utilization percentage
   - Task count
   - Dispatch latency
   - Queue depth

3. **Scheduler-Specific**:
   - Custom statistics via scx_stats
   - Scheduler-defined counters
   - Performance indicators

## scxctl - Command Line Control

### Overview

`scxctl` is the primary command-line interface for controlling sched_ext schedulers. It communicates with the `scx_loader` service via DBUS to manage scheduler lifecycle.

### Features

1. **Scheduler Management**:
   - Start/stop schedulers
   - Switch between schedulers
   - Query current status

2. **Mode Support**:
   - Auto mode
   - Gaming mode
   - Power save mode
   - Low latency mode
   - Server mode

3. **Argument Passing**:
   - Custom scheduler parameters
   - Mode-specific configurations
   - Debug options

### Command Reference

#### Get Current Scheduler
```bash
scxctl get
# Output: Current scheduler: scx_rusty
```

#### List Available Schedulers
```bash
scxctl list
# Output:
# Available schedulers:
#   scx_simple
#   scx_rusty
#   scx_lavd
#   scx_bpfland
#   ...
```

#### Start Scheduler
```bash
# Start with default mode
scxctl start -s scx_rusty

# Start with specific mode
scxctl start -s scx_lavd -m gaming

# Start with custom arguments
scxctl start -s scx_bpfland -a "-v,--slice-us=5000"
```

#### Switch Scheduler
```bash
# Switch to different scheduler
scxctl switch -s scx_flash

# Switch mode on current scheduler
scxctl switch -m lowlatency

# Switch with arguments
scxctl switch -s scx_layered -a "--config=/etc/scx/layers.json"
```

#### Stop Scheduler
```bash
scxctl stop
```

### Scheduler Modes

| Mode | Value | Description | Use Case |
|------|-------|-------------|----------|
| Auto | 0 | Default behavior | General use |
| Gaming | 1 | Low latency, interactive | Gaming, desktop |
| PowerSave | 2 | Energy efficiency | Laptops, battery |
| LowLatency | 3 | Minimal latency | Real-time apps |
| Server | 4 | Throughput focus | Server workloads |

### Error Handling

```bash
# Check if scheduler is supported
if ! scxctl list | grep -q "scx_myscheduler"; then
    echo "Scheduler not available"
    exit 1
fi

# Start with error checking
if scxctl start -s scx_rusty; then
    echo "Scheduler started successfully"
else
    echo "Failed to start scheduler"
fi
```

## scx_loader - DBUS Service

### Overview

`scx_loader` is a system service that provides a DBUS interface for managing sched_ext schedulers. It runs as a daemon and handles the actual process management of schedulers.

### Architecture

```
┌──────────────┐     DBUS      ┌─────────────┐
│    scxctl    │ ◄────────────► │ scx_loader  │
└──────────────┘                └──────┬──────┘
                                       │
                                       │ Process
                                       │ Management
                                       ▼
                               ┌───────────────┐
                               │  Scheduler    │
                               │  Process      │
                               └───────────────┘
```

### DBUS Interface

**Service**: `org.scx.Loader`
**Object Path**: `/org/scx/Loader`
**Interface**: `org.scx.Loader`

#### Methods

1. **StartScheduler**
   ```
   StartScheduler(in s scx_name, in u sched_mode)
   ```

2. **StartSchedulerWithArgs**
   ```
   StartSchedulerWithArgs(in s scx_name, in as scx_args)
   ```

3. **StopScheduler**
   ```
   StopScheduler()
   ```

4. **SwitchScheduler**
   ```
   SwitchScheduler(in s scx_name, in u sched_mode)
   ```

5. **SwitchSchedulerWithArgs**
   ```
   SwitchSchedulerWithArgs(in s scx_name, in as scx_args)
   ```

#### Properties

- **CurrentScheduler** (string): Active scheduler name
- **SchedulerMode** (uint32): Current mode (0-4)
- **SupportedSchedulers** (array of strings): Available schedulers

### Direct DBUS Usage

```bash
# Start scheduler via DBUS
dbus-send --system --print-reply \
    --dest=org.scx.Loader \
    /org/scx/Loader \
    org.scx.Loader.StartScheduler \
    string:"scx_rusty" uint32:0

# Get current scheduler
dbus-send --system --print-reply \
    --dest=org.scx.Loader \
    /org/scx/Loader \
    org.freedesktop.DBus.Properties.Get \
    string:"org.scx.Loader" \
    string:"CurrentScheduler"

# Monitor scheduler changes
dbus-monitor --system \
    "type='signal',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',path='/org/scx/Loader'"
```

### Service Configuration

**Systemd Service**: `/etc/systemd/system/scx_loader.service`
```ini
[Unit]
Description=SCX Scheduler Loader Service
After=multi-user.target

[Service]
Type=dbus
BusName=org.scx.Loader
ExecStart=/usr/bin/scx_loader
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Security

- Requires root privileges to load BPF programs
- DBUS policy restricts access to authorized users
- Validates scheduler binaries before execution

## Additional Utilities

### 1. vmlinux_docify

**Purpose**: Enhances vmlinux.h headers with kernel documentation

**Usage**:
```bash
vmlinux_docify \
    --kernel-dir /usr/src/linux \
    --vmlinux-h vmlinux.h \
    --output vmlinux_documented.h
```

**Benefits**:
- Adds inline documentation to kernel structures
- Improves developer experience
- Helps understand kernel APIs

### 2. scheduler_runner.py

**Purpose**: Python module for programmatic scheduler control

**Features**:
- Direct scheduler management (bypasses DBUS)
- Benchmark integration
- Testing automation
- Configuration parsing

**Example Usage**:
```python
from scheduler_runner import SchedulerRunner

runner = SchedulerRunner()

# List schedulers
schedulers = runner.get_available_schedulers()

# Start scheduler
runner.start_scheduler("scx_rusty", slice_us=20000)

# Run benchmark
results = runner.run_benchmark("schbench", duration=60)

# Stop scheduler
runner.stop_scheduler()
```

### 3. scx_stats Framework

**Purpose**: Standardized statistics collection for schedulers

**Features**:
- Common metrics interface
- Efficient data collection
- Integration with scxtop
- Custom metric support

**Implementation**:
```rust
use scx_stats::{StatsCollection, StatsField};

#[derive(StatsCollection)]
struct SchedStats {
    #[stat(desc = "Total dispatches")]
    dispatches: u64,
    
    #[stat(desc = "Average latency")]
    avg_latency: f64,
}
```

## Tool Integration

### 1. Workflow Example

```bash
# 1. Check available schedulers
scxctl list

# 2. Start a scheduler
scxctl start -s scx_lavd -m gaming

# 3. Monitor performance
scxtop

# 4. Adjust parameters
scxctl switch -m lowlatency

# 5. Generate trace for analysis
scxtop trace -d 5000 -o gaming_trace.pftrace

# 6. Stop when done
scxctl stop
```

### 2. Automation Script

```bash
#!/bin/bash
# Automated scheduler testing

SCHEDULERS=("scx_simple" "scx_rusty" "scx_lavd")
MODES=(0 1 3)  # auto, gaming, lowlatency

for sched in "${SCHEDULERS[@]}"; do
    for mode in "${MODES[@]}"; do
        echo "Testing $sched in mode $mode"
        
        # Start scheduler
        scxctl start -s "$sched" -m "$mode"
        
        # Let it run
        sleep 30
        
        # Collect trace
        scxtop trace -d 1000 -w 10000 -o "${sched}_mode${mode}.pftrace"
        
        # Stop
        scxctl stop
        
        sleep 5
    done
done
```

### 3. System Integration

**Boot-time Loading**:
```bash
# /etc/systemd/system/scx-default.service
[Unit]
Description=Default SCX Scheduler
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/scxctl start -s scx_rusty -m auto
RemainAfterExit=yes
ExecStop=/usr/bin/scxctl stop

[Install]
WantedBy=multi-user.target
```

**Desktop Environment Integration**:
- GNOME extension for mode switching
- KDE widget for scheduler selection
- System tray indicator

### 4. Monitoring Stack

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│   scxtop    │────►│ Prometheus   │────►│   Grafana     │
│  (metrics)  │     │  Exporter    │     │ (dashboards)  │
└─────────────┘     └──────────────┘     └───────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │  AlertManager│
                    │   (alerts)   │
                    └──────────────┘
```

## Best Practices

### 1. Production Deployment
- Always test schedulers in development first
- Monitor key metrics with scxtop
- Have fallback procedures ready
- Use appropriate modes for workloads

### 2. Performance Tuning
- Start with default parameters
- Monitor with scxtop to identify issues
- Adjust parameters incrementally
- Document successful configurations

### 3. Troubleshooting
- Check kernel logs: `dmesg | grep scx`
- Verify BPF programs: `bpftool prog list`
- Monitor DBUS: `dbus-monitor --system`
- Use debug flags: `-v` or `--debug`

### 4. Security Considerations
- Limit access to scheduler controls
- Audit scheduler changes
- Monitor for abnormal behavior
- Keep schedulers updated

The SCX tools provide a robust infrastructure for deploying and managing custom schedulers, from simple command-line control to sophisticated real-time monitoring and system integration.