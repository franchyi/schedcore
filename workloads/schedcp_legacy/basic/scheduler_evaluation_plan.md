# Academic Evaluation Plan for LLM Agent-Based Auto-Tuning Scheduler

## Research Questions

### Primary Research Questions
1. **RQ1**: How effective is LLM-based auto-tuning compared to static scheduler configurations?
2. **RQ2**: What is the adaptation latency of the LLM agent when workload characteristics change?
3. **RQ3**: What is the overhead of LLM-based decision making on system performance?
4. **RQ4**: How does the LLM agent perform across diverse workload types (CPU-bound, I/O-bound, mixed)?

### Secondary Research Questions
5. **RQ5**: How does the quality of LLM prompts affect scheduler optimization outcomes?
6. **RQ6**: Can the LLM agent discover novel scheduling strategies not present in training data?
7. **RQ7**: How robust is the system to adversarial workloads or edge cases?

## Evaluation Metrics

### Performance Metrics
- **Throughput**: Operations/second, requests/second
- **Latency**: P50, P95, P99, P99.9 tail latencies
- **CPU Utilization**: Overall and per-core utilization
- **Context Switch Rate**: Frequency of thread migrations
- **Cache Performance**: L1/L2/L3 cache miss rates
- **Energy Efficiency**: Performance per watt

### LLM Agent Metrics
- **Decision Latency**: Time from workload change detection to parameter adjustment
- **Convergence Time**: Time to reach stable configuration
- **Decision Quality**: Distance from optimal configuration
- **Adaptation Frequency**: Number of parameter adjustments over time

## Benchmark Suite

### 1. Synthetic Workloads
```bash
# CPU-intensive workload with varying thread counts
./scheduler/sche_bin/scx_lavd &
python workloads/basic/scheduler_test/schbench_bench_start.py --threads 1,2,4,8,16,32,64

# Memory-intensive workload
python workloads/cxl-micro/cxl_micro_bench_start.py --pattern sequential,random
```

### 2. Real-world Workloads
```bash
# LLM inference workload
python workloads/llama.cpp/llamacpp_bench_start.py --model llama-7b --batch-size 1,4,8,16

# Database workload (if available)
# Web server workload (nginx/apache bench)
# Compilation workload (kernel build)
```

### 3. Dynamic Workloads
```bash
# Phase-changing workload (CPU → I/O → Memory)
# Bursty workload simulation
# Multi-tenant scenarios
```

## Experimental Design

### Baseline Comparisons
1. **Static Default**: Default scheduler parameters
2. **Manual Expert**: Hand-tuned parameters by domain expert
3. **Grid Search**: Exhaustive parameter search (offline)
4. **Random Search**: Random parameter sampling
5. **Rule-based**: Traditional heuristic-based adaptation

### Experimental Conditions
- **Warm-up Period**: 60 seconds
- **Measurement Period**: 300 seconds
- **Repetitions**: 5 runs per configuration
- **System State**: Isolated, no background tasks

## Figure Generation Plan

### Figure 1: Performance Comparison Across Workloads
- **Type**: Grouped bar chart
- **X-axis**: Workload types
- **Y-axis**: Normalized throughput
- **Groups**: Different scheduling approaches

### Figure 2: Adaptation Timeline
- **Type**: Time-series plot
- **X-axis**: Time (seconds)
- **Y-axis**: Performance metric + LLM decisions
- **Annotations**: Workload phase changes

### Figure 3: Latency Distribution (CDF)
- **Type**: Cumulative distribution function
- **X-axis**: Latency (microseconds)
- **Y-axis**: Percentile
- **Lines**: Different scheduling approaches

### Figure 4: Overhead Analysis
- **Type**: Stacked bar chart
- **Components**: Scheduler overhead, LLM inference time, parameter adjustment time

### Figure 5: Parameter Space Exploration
- **Type**: Heatmap or 3D surface plot
- **Axes**: Key scheduler parameters
- **Color**: Performance metric

### Figure 6: Convergence Analysis
- **Type**: Line plot with error bars
- **X-axis**: Time or iterations
- **Y-axis**: Distance from optimal/performance metric

## Data Collection Commands

```bash
# Performance monitoring during experiments
./scheduler/tools/scxtop > scxtop_output.log &

# System-wide performance collection
perf record -a -g -- python run_experiment.py
perf stat -a -- python run_experiment.py

# Detailed scheduler statistics
./scheduler/tools/scxctl stats > scheduler_stats.json

# BPF tracing for scheduler events
bpftrace -e 'tracepoint:sched:sched_switch { @[comm] = count(); }'

# Power monitoring (if available)
turbostat --interval 1 > power_stats.log &
```

## Evaluation Script Structure

```python
# evaluation_framework.py
import json
import time
import subprocess
from scheduler.scheduler_runner import SchedulerRunner

class SchedulerEvaluator:
    def __init__(self):
        self.runner = SchedulerRunner()
        self.metrics = []
    
    def run_baseline_experiment(self, scheduler, workload, duration=300):
        """Run experiment with static configuration"""
        pass
    
    def run_llm_experiment(self, scheduler, workload, llm_agent, duration=300):
        """Run experiment with LLM-based tuning"""
        pass
    
    def collect_metrics(self):
        """Collect performance metrics from various sources"""
        pass
    
    def generate_figures(self):
        """Generate publication-quality figures"""
        pass
```

## Statistical Analysis

### Required Statistical Tests
1. **Mann-Whitney U Test**: For comparing two approaches
2. **Kruskal-Wallis Test**: For comparing multiple approaches
3. **Cliff's Delta**: For effect size measurement
4. **Bootstrap Confidence Intervals**: For robust estimates

### Reporting Requirements
- Mean ± standard deviation
- Median and IQR for skewed distributions
- Statistical significance (p < 0.05)
- Effect sizes (small, medium, large)

## Reproducibility Checklist

- [ ] Document exact kernel version and configuration
- [ ] Record CPU model, memory configuration
- [ ] Save all scheduler configurations
- [ ] Version control for LLM prompts
- [ ] Containerize evaluation environment
- [ ] Provide random seeds for experiments
- [ ] Share raw data and analysis scripts

## Timeline

1. **Week 1-2**: Implement evaluation framework
2. **Week 3-4**: Run baseline experiments
3. **Week 5-6**: Run LLM agent experiments
4. **Week 7**: Statistical analysis and figure generation
5. **Week 8**: Paper writing and revision