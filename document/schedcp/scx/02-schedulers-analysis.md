# Detailed Scheduler Analysis

## Table of Contents
1. [Scheduler Categories](#scheduler-categories)
2. [C Schedulers](#c-schedulers)
3. [Rust Schedulers](#rust-schedulers)
4. [Scheduler Comparison](#scheduler-comparison)
5. [Selection Guide](#selection-guide)

## Scheduler Categories

The SCX framework provides schedulers optimized for different use cases:

### 1. Interactive/Gaming Schedulers
- **scx_lavd**: Latency-aware virtual deadline scheduler
- **scx_bpfland**: Interactive workload prioritization
- **scx_flash**: EDF-based low-latency scheduler

### 2. Server/Throughput Schedulers
- **scx_central**: Centralized scheduling for virtualization
- **scx_tickless**: Reduced OS noise for servers
- **scx_simple**: Basic but effective for simple topologies

### 3. Container/Cloud Schedulers
- **scx_flatcg**: Cgroup-aware for containers
- **scx_layered**: Multi-layer configurable scheduler
- **scx_rusty**: Multi-domain general purpose

### 4. Specialized Schedulers
- **scx_nest**: Frequency optimization
- **scx_pair**: Security-focused sibling scheduler
- **scx_userland**: Educational userspace scheduler

## C Schedulers

### 1. scx_simple
**Purpose**: Minimal scheduler demonstrating basic concepts
**Production Ready**: Yes

**Features**:
- Weighted vtime scheduling mode
- FIFO scheduling mode
- Global scheduling queue
- Simple and predictable behavior

**Use Cases**:
- Single socket systems
- Uniform cache topology
- Learning sched_ext basics
- Simple workloads

**Key Parameters**:
- `--fifo`: Enable FIFO mode
- `--slice-us`: Time slice in microseconds

### 2. scx_central
**Purpose**: Centralized scheduling with one decision-making CPU
**Production Ready**: No

**Features**:
- Central CPU makes all scheduling decisions
- Other CPUs run with infinite time slices
- Reduced timer interrupts
- Lower scheduling overhead

**Use Cases**:
- Virtual machines
- Low-latency applications
- Workloads with few context switches

**Architecture**:
```
┌─────────────────────────────────────┐
│         Central CPU (CPU 0)         │
│  ┌─────────────────────────────┐   │
│  │   Makes all scheduling      │   │
│  │      decisions             │   │
│  └──────────┬─────────────────┘   │
│             │                      │
│    Assigns tasks to:               │
│             │                      │
│  ┌──────────▼─────────────────┐   │
│  │   Worker CPUs (1-N)        │   │
│  │   - Run assigned tasks     │   │
│  │   - No scheduling overhead │   │
│  └───────────────────────────┘   │
└─────────────────────────────────────┘
```

### 3. scx_flatcg
**Purpose**: High-performance cgroup scheduling
**Production Ready**: Yes

**Features**:
- Flattened cgroup hierarchy
- Weight-based CPU distribution
- Efficient for deep cgroup trees
- Container workload optimization

**Use Cases**:
- Kubernetes/Docker environments
- Multi-tenant systems
- Resource isolation
- Cloud computing

**Cgroup Handling**:
- Flattens nested cgroups for performance
- Maintains proportional shares
- Efficient weight calculations

### 4. scx_nest
**Purpose**: Keep tasks on warm cores for frequency optimization
**Production Ready**: Yes

**Features**:
- Warm core detection
- Frequency-aware scheduling
- Reduced core migrations
- Energy efficiency

**Use Cases**:
- Low CPU utilization scenarios
- Battery-powered devices
- Thermal-constrained systems
- Single CCX/socket systems

**Algorithm**:
1. Track core frequencies
2. Prefer warmer (higher frequency) cores
3. Minimize frequency transitions
4. Batch task placement

### 5. scx_pair
**Purpose**: Security through core isolation
**Production Ready**: No

**Features**:
- Sibling-aware scheduling
- Same-cgroup co-location only
- L1TF mitigation
- Hyper-threading security

**Use Cases**:
- Security-sensitive workloads
- Multi-tenant with isolation
- Environments with untrusted code

### 6. scx_qmap
**Purpose**: Demonstrating BPF features
**Production Ready**: No

**Features**:
- Weighted FIFO queuing
- Core-scheduling support
- Sleepable BPF operations
- Example implementation

**Educational Value**:
- Shows BPF map usage
- Demonstrates per-task storage
- Example of core-sched integration

### 7. scx_prev
**Purpose**: OLTP-optimized variant of scx_simple
**Production Ready**: Yes

**Features**:
- Prefers previous CPU over fully idle
- Optimized for cache locality
- Simple topology support
- OLTP workload optimization

**Use Cases**:
- Database workloads
- Transaction processing
- Cache-sensitive applications

### 8. scx_userland
**Purpose**: Educational fully userspace scheduler
**Production Ready**: No

**Features**:
- All decisions in userspace
- Maximum flexibility
- High overhead
- Learning tool

**Architecture**:
- BPF side: Minimal, just queues tasks
- User side: Full scheduling logic
- Communication via BPF maps

## Rust Schedulers

### 1. scx_rusty
**Purpose**: Production-ready multi-domain scheduler
**Production Ready**: Yes

**Features**:
- Per-LLC scheduling domains
- Userspace load balancing
- NUMA awareness
- Dynamic domain adjustment
- Comprehensive statistics

**Architecture**:
```
┌─────────────────────────────────────────┐
│           Global Load Balancer          │
│                                         │
├────────────┬────────────┬──────────────┤
│  Domain 0  │  Domain 1  │   Domain N   │
│   (LLC 0)  │   (LLC 1)  │   (LLC N)   │
│            │            │              │
│  ┌──────┐  │  ┌──────┐  │  ┌──────┐  │
│  │Queue │  │  │Queue │  │  │Queue │  │
│  └──────┘  │  └──────┘  │  └──────┘  │
└────────────┴────────────┴──────────────┘
```

**Use Cases**:
- General purpose computing
- Mixed workloads
- NUMA systems
- Production servers

### 2. scx_lavd
**Purpose**: Sophisticated latency-aware scheduler
**Production Ready**: Yes

**Features**:
- Virtual deadline scheduling
- Latency criticality detection
- Per-task latency tracking
- NUMA optimization
- Gaming/interactive focus

**Algorithm**:
1. Calculate task virtual deadlines
2. Consider latency criticality
3. Schedule based on deadlines
4. Adjust for fairness

**Use Cases**:
- Gaming systems
- Interactive applications
- Low-latency requirements
- Desktop environments

### 3. scx_bpfland
**Purpose**: Interactive workload prioritization
**Production Ready**: Yes

**Features**:
- Voluntary preemption detection
- Interactive task identification
- vruntime-based fairness
- Dynamic priority adjustment

**Detection Mechanism**:
- Tracks voluntary context switches
- Identifies interactive patterns
- Boosts interactive tasks
- Maintains overall fairness

**Use Cases**:
- Desktop computing
- Multimedia applications
- Live streaming
- Gaming

### 4. scx_layered
**Purpose**: Highly configurable multi-layer scheduler
**Production Ready**: Yes

**Features**:
- User-defined layers
- Per-layer scheduling policies
- CPU allocation guarantees
- Topology awareness
- Dynamic configuration

**Configuration Example**:
```json
{
  "layers": [
    {
      "name": "interactive",
      "policy": "preemptive",
      "cpus": "0-7",
      "weight": 100
    },
    {
      "name": "batch",
      "policy": "weighted",
      "cpus": "8-15",
      "weight": 50
    }
  ]
}
```

**Use Cases**:
- Complex workload mixes
- Multi-tier applications
- Custom scheduling requirements
- Research and experimentation

### 5. scx_flash
**Purpose**: EDF scheduler with dynamic weights
**Production Ready**: Yes

**Features**:
- Earliest Deadline First
- CPU usage-based weights
- Predictable latency
- Real-time characteristics

**Algorithm**:
1. Assign deadlines based on priority
2. Adjust weights by CPU usage
3. Schedule earliest deadline
4. Prevent starvation

**Use Cases**:
- Real-time audio
- Multimedia processing
- Soft real-time applications
- Predictable workloads

### 6. scx_p2dq
**Purpose**: Versatile multi-layer queuing scheduler
**Production Ready**: Yes

**Features**:
- Pick-two load balancing
- Interactive task detection
- Per-cache locality optimization
- Resilient task classification

**Queue System**:
- Multiple priority levels
- Per-CPU local queues
- Global overflow queue
- Dynamic classification

**Use Cases**:
- Mixed interactive/batch
- Server workloads
- General purpose
- Adaptive systems

### 7. scx_tickless
**Purpose**: Reduce OS noise for servers
**Production Ready**: No

**Features**:
- Minimize timer ticks
- Core isolation
- Reduced interrupts
- Server optimization

**Requirements**:
- nohz_full kernel support
- Dedicated housekeeping cores
- Careful configuration

### 8. scx_rlfifo
**Purpose**: Template userspace scheduler
**Production Ready**: No

**Features**:
- Simple round-robin
- Userspace decisions
- Minimal implementation
- Learning example

### 9. scx_chaos
**Purpose**: Chaos testing scheduler
**Production Ready**: No

**Features**:
- Controlled randomness
- Stress testing
- Fault injection
- Testing framework

## Scheduler Comparison

### Performance Characteristics

| Scheduler | Latency | Throughput | Fairness | Overhead |
|-----------|---------|------------|----------|----------|
| scx_simple | Medium | High | High | Low |
| scx_rusty | Low | High | High | Medium |
| scx_lavd | Very Low | Medium | Medium | Medium |
| scx_bpfland | Low | Medium | High | Low |
| scx_layered | Variable | High | High | Medium |
| scx_flatcg | Medium | High | High | Low |
| scx_flash | Very Low | Medium | Medium | Medium |

### Feature Matrix

| Scheduler | NUMA | Cgroups | Topology | Gaming | Server | Container |
|-----------|------|---------|----------|---------|---------|-----------|
| scx_simple | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ |
| scx_rusty | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| scx_lavd | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| scx_bpfland | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| scx_layered | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| scx_flatcg | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |

## Selection Guide

### By Workload Type

**Gaming/Interactive Desktop**:
1. **scx_lavd** - Best overall for gaming
2. **scx_bpfland** - Good for mixed desktop use
3. **scx_flash** - For audio/multimedia

**Server/Cloud**:
1. **scx_rusty** - General purpose production
2. **scx_flatcg** - Container environments
3. **scx_layered** - Complex requirements

**Embedded/Constrained**:
1. **scx_simple** - Minimal overhead
2. **scx_nest** - Power efficiency
3. **scx_prev** - Cache optimization

**Development/Testing**:
1. **scx_userland** - Maximum flexibility
2. **scx_qmap** - BPF examples
3. **scx_chaos** - Stress testing

### By System Topology

**Single Socket**:
- scx_simple
- scx_prev
- scx_nest

**Multi-Socket/NUMA**:
- scx_rusty
- scx_lavd
- scx_layered

**Virtual Machines**:
- scx_central
- scx_simple
- scx_flatcg

### By Requirements

**Low Latency**:
- scx_lavd
- scx_flash
- scx_bpfland

**High Throughput**:
- scx_rusty
- scx_layered
- scx_simple

**Resource Isolation**:
- scx_flatcg
- scx_layered
- scx_pair

**Power Efficiency**:
- scx_nest
- scx_tickless
- scx_central