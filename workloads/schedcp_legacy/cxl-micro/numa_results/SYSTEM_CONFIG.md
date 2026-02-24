# System Configuration Documentation

## CPU Configuration

### Processor Information
- **Model**: Intel(R) Xeon(R) 6787P @ 2.0GHz
- **Architecture**: x86_64
- **CPU Family**: 6, Model: 173
- **Total CPU Cores**: 86
- **Threads per Core**: 1 (Hyperthreading disabled)
- **Sockets**: 1
- **CPU Frequency Range**: 800 MHz - 3800 MHz

### Cache Hierarchy
- **L1d Cache**: 4 MiB (86 instances, ~48 KiB per core)
- **L1i Cache**: 5.4 MiB (86 instances, ~64 KiB per core)
- **L2 Cache**: 172 MiB (86 instances, 2 MiB per core)
- **L3 Cache**: 336 MiB (shared)

### Key CPU Features
- AVX-512 Extensions (F, DQ, CD, BW, VL, VBMI, VNNI, BITALG, VPOPCNTDQ, FP16)
- Intel AMX (BF16, TILE, INT8)
- Intel SGX (Software Guard Extensions)
- Intel PT (Processor Trace)
- Enhanced IBRS for Spectre mitigation

## NUMA Architecture

### NUMA Topology Overview
The system has **4 NUMA nodes** with the following configuration:

| NUMA Node | CPU Cores | Memory Size | Memory Type | Status |
|-----------|-----------|-------------|-------------|---------|
| Node 0 | 0-42 (43 cores) | 64 GB | DDR5 (Local) | Active with CPUs |
| Node 1 | 43-85 (43 cores) | 64 GB | DDR5 (Local) | Active with CPUs |
| Node 2 | None | 256 GB | CXL Memory | Memory-only node |
| Node 3 | None | 512 GB | CXL Memory | Memory-only node |

### NUMA Distance Matrix
```
      Node 0  Node 1  Node 2  Node 3
Node 0:  10     12      14      14
Node 1:  12     10      14      14
Node 2:  14     14      10      16
Node 3:  14     14      16      10
```

**Distance Interpretation:**
- 10: Local memory access (same node)
- 12: Adjacent CPU socket (cross-socket for CPU nodes)
- 14: CXL memory from CPU nodes
- 16: Inter-CXL memory access

## Memory Configuration

### Total System Memory
- **Total Memory**: 914 GB (934,494,196 KB)
  - DDR5 Memory: 128 GB (Nodes 0 & 1)
  - CXL Memory: 768 GB (Nodes 2 & 3)

### Memory Distribution by NUMA Node

#### Node 0 (DDR5 - CPU Local)
- **Total**: 63.7 GB
- **Free**: ~23.7 GB
- **CPU Affinity**: Cores 0-42

#### Node 1 (DDR5 - CPU Local)
- **Total**: 62.4 GB
- **Free**: ~34.1 GB
- **CPU Affinity**: Cores 43-85

#### Node 2 (CXL Memory)
- **Total**: 256 GB
- **Free**: ~261.8 GB (mostly unused)
- **CPU Affinity**: None (memory-only node)
- **Access Pattern**: Uniform access from both CPU nodes

#### Node 3 (CXL Memory)
- **Total**: 512 GB
- **Free**: ~523.2 GB (mostly unused)
- **CPU Affinity**: None (memory-only node)
- **Access Pattern**: Uniform access from both CPU nodes

## CXL Configuration

### CXL Devices
The system has **4 CXL devices** installed:

1. **Montage Technology CXL Devices** (2 devices)
   - PCI Address: 15:00.0 and 16:00.0
   - Device ID: c002 (rev 03)
   - These likely provide the CXL memory expansion

2. **Astera Labs CXL Devices** (2 devices)
   - PCI Address: 8a:00.0 and 8b:00.0
   - Device ID: 01e2 (rev 01)
   - These likely serve as CXL switches/retimers

### CXL to NUMA Mapping

Based on the system configuration:

- **NUMA Node 2** (256 GB) → Likely mapped to CXL device at 15:00.0
- **NUMA Node 3** (512 GB) → Likely mapped to CXL device at 16:00.0

The CXL memory appears as memory-only NUMA nodes without CPU affinity, which is the standard configuration for CXL Type 3 memory expanders.

## Performance Characteristics

### Memory Access Latency (Relative)
Based on NUMA distances:
- **Local DDR5 Access**: Baseline (distance 10)
- **Cross-Socket DDR5**: ~1.2x slower (distance 12)
- **CXL Memory from CPU**: ~1.4x slower (distance 14)
- **Inter-CXL Access**: ~1.6x slower (distance 16)

### Bandwidth Considerations
1. **DDR5 Local Memory**: Maximum bandwidth with lowest latency
2. **CXL Memory**: Lower bandwidth and higher latency compared to local DDR5
3. **NUMA Effects**: Cross-node access incurs additional latency

## Optimization Recommendations

### For CXL Memory Usage

1. **Thread Placement**:
   - Bind threads to specific CPU nodes (0 or 1) for consistent performance
   - Default binding in benchmarks uses Node 1 (cores 43-85)

2. **Memory Allocation**:
   - Use `numactl --membind=2` for CXL Node 2 (256 GB)
   - Use `numactl --membind=3` for CXL Node 3 (512 GB)
   - Use `numactl --interleave=2,3` for balanced CXL usage

3. **Benchmark Configuration**:
   ```bash
   # Example: Force allocation on CXL Node 2
   numactl --membind=2 ./double_bandwidth --buffer-size 64G
   
   # Example: Bind threads to Node 1, memory to CXL Node 3
   numactl --cpubind=1 --membind=3 ./double_bandwidth
   ```

4. **Performance Testing**:
   - Test with different NUMA policies (local, bind, interleave)
   - Monitor with `numastat` during benchmarks
   - Use `pcm-memory` for detailed bandwidth analysis

## System Capabilities

### CXL Features Supported
- CXL 1.1 Port Register Access
- CXL 2.0 Port Device Register Access
- CXL Protocol Error Reporting
- CXL Native Hotplug

### CXL Features NOT Supported
- CXL Memory Error Reporting (platform limitation)

## Monitoring Commands

```bash
# Check NUMA memory usage
numastat -m

# Monitor per-node memory bandwidth
pcm-memory

# Check CXL device status
ls /sys/bus/cxl/devices/

# Monitor memory allocation per node
watch -n 1 'numactl --hardware | grep "node [0-3] free"'

# Check process NUMA binding
numastat -p <pid>
```

## Notes

1. The system uses a single-socket Intel Xeon 6787P with 86 cores
2. CXL memory adds 768 GB to the system (3x DDR5 capacity)
3. NUMA distances suggest CXL memory has ~40% higher latency than local DDR5
4. The configuration is optimized for memory-intensive workloads that can benefit from large memory capacity despite higher latency