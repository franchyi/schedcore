# PyVSAG ANN Benchmark

numactl --interleave=3 python /root/yunwei37/ai-os/workloads/pyvsag/pyvsag_bench_start.py

This benchmark tests different Linux schedulers with PyVSAG (VSAG Python bindings) to compare Approximate Nearest Neighbor (ANN) search performance.

## Overview

PyVSAG is the Python binding for VSAG, a high-performance vector indexing library designed for similarity search. This benchmark evaluates how different schedulers affect the performance of:

- Vector index building (HNSW algorithm)
- ANN search queries (k-nearest neighbor searches)
- Overall throughput and latency characteristics

## Features

- **Multiple ANN algorithms**: Currently supports HNSW (Hierarchical Navigable Small World)
- **Comprehensive metrics**: QPS, latency percentiles, recall, build time
- **Scheduler comparison**: Tests all available production schedulers
- **Visualization**: Generates performance comparison charts
- **Configurable parameters**: Vector dimensions, dataset size, search parameters

## Requirements

- Python 3.8+
- PyVSAG >= 0.15.0
- NumPy, pandas, matplotlib, seaborn
- Linux with sched-ext support

## Installation

```bash
# Install PyVSAG and dependencies
pip install -r requirements.txt

# Or install PyVSAG directly
pip install pyvsag
```

## Usage

### Basic benchmark run
```bash
python pyvsag_bench_start.py
```

### Test specific scheduler
```bash
python pyvsag_bench_start.py --scheduler scx_rusty
```

### Customize benchmark parameters
```bash
python pyvsag_bench_start.py \
    --dim 256 \
    --num-elements 100000 \
    --num-queries 2000 \
    --k 20 \
    --ef-construction 400 \
    --ef-search 200
```

### Production schedulers only
```bash
python pyvsag_bench_start.py --production-only
```

## Parameters

- `--dim`: Vector dimension (default: 128)
- `--num-elements`: Number of vectors in index (default: 50,000)
- `--num-queries`: Number of search queries (default: 1,000)
- `--k`: Number of nearest neighbors to find (default: 10)
- `--max-degree`: HNSW max degree parameter (default: 16)
- `--ef-construction`: HNSW construction parameter (default: 200)
- `--ef-search`: HNSW search parameter (default: 100)
- `--timeout`: Timeout in seconds (default: 300)

## Metrics

The benchmark reports several key metrics:

### Throughput
- **QPS (Queries Per Second)**: Number of search queries processed per second
- **Build Time**: Time to construct the vector index

### Latency
- **Average Query Time**: Mean time per search query
- **P95 Latency**: 95th percentile query time
- **P99 Latency**: 99th percentile query time

### Accuracy
- **Recall**: Fraction of true nearest neighbors found in search results

### Combined Score
- Weighted combination of QPS (40%), Recall (40%), and Latency (20%)

## Output

The benchmark generates:

1. **JSON results**: `results/pyvsag_scheduler_results.json`
2. **Performance plots**: `results/pyvsag_scheduler_performance.png`
3. **Console summary**: Detailed performance breakdown

## Algorithm Details

### HNSW (Hierarchical Navigable Small World)
- **Type**: Graph-based ANN algorithm
- **Characteristics**: High recall, fast search, moderate memory usage
- **Parameters**:
  - `max_degree`: Maximum connections per node (affects recall/memory trade-off)
  - `ef_construction`: Search width during index building (affects build time/recall)
  - `ef_search`: Search width during queries (affects search time/recall)

## Scheduler Impact

Different schedulers can significantly affect ANN search performance due to:

1. **CPU cache locality**: Graph traversal benefits from cache-friendly scheduling
2. **Memory bandwidth**: Large vector operations are memory-intensive
3. **Thread synchronization**: Multi-threaded index building requires coordination
4. **Interactive vs. batch workloads**: Search queries vs. index construction have different characteristics

### Expected Scheduler Behavior

- **scx_rusty**: Good general-purpose performance, balanced CPU/memory scheduling
- **scx_lavd**: May improve search latency for interactive queries
- **scx_layered**: Can optimize for different workload phases (build vs. search)
- **scx_bpfland**: May prioritize search queries as interactive workloads

## Integration with schedcp

This benchmark integrates with the schedcp framework, allowing you to:

1. **Profile workloads**: Create workload profiles for different ANN scenarios
2. **Track history**: Store and compare results across scheduler configurations
3. **Automate testing**: Use the MCP server for AI-assisted optimization
4. **Generate reports**: Export results for analysis and reporting

## Troubleshooting

### PyVSAG Import Error
```bash
pip install pyvsag
# Or build from source if binary wheels aren't available
```

### Memory Issues
- Reduce `--num-elements` for large vector dimensions
- Monitor system memory usage during index building

### Performance Variations
- Run multiple iterations and average results
- Ensure system is not under load during benchmarking
- Consider CPU frequency scaling and thermal throttling

## Related Benchmarks

- **ann-benchmarks/**: Industry-standard ANN benchmarking suite
- **llama.cpp/**: LLM inference with vector similarity
- **cxl-micro/**: Memory bandwidth optimization
- **basic/schbench**: General scheduler latency testing

## References

- [VSAG GitHub Repository](https://github.com/antgroup/vsag)
- [PyVSAG Documentation](https://pypi.org/project/pyvsag/)
- [HNSW Algorithm Paper](https://arxiv.org/abs/1603.09320)
- [ANN Benchmarks](https://ann-benchmarks.com/)