#! /bin/bash

mkdir -p numa_results

# python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_perf_bandwidth_bench.py --parameter-sweep > numa_results/numa_results_numact_none.log 2>&1
# cp /root/yunwei37/ai-os/workloads/cxl-micro/results/cxl_perf_parameter_sweep.csv numa_results/cxl_perf_parameter_sweep_numact_none.csv

# numactl --interleave=2 python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_perf_bandwidth_bench.py --parameter-sweep > numa_results/numa_results_numactl2_seq.log 2>&1
# cp /root/yunwei37/ai-os/workloads/cxl-micro/results/cxl_perf_parameter_sweep.csv numa_results/cxl_perf_parameter_sweep_numactl2_seq.csv

# numactl --interleave=3 python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_perf_bandwidth_bench.py --parameter-sweep > numa_results/numa_results_numactl3_seq.log 2>&1
# cp /root/yunwei37/ai-os/workloads/cxl-micro/results/cxl_perf_parameter_sweep.csv numa_results/cxl_perf_parameter_sweep_numactl3_seq.csv

numactl --interleave=0 python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_perf_bandwidth_bench.py --parameter-sweep > numa_results/numa_results_numactl0_seq.log 2>&1
cp /root/yunwei37/ai-os/workloads/cxl-micro/results/cxl_perf_parameter_sweep.csv numa_results/cxl_perf_parameter_sweep_numactl0_seq.csv

numactl --interleave=0,1 python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_perf_bandwidth_bench.py --parameter-sweep > numa_results/numa_results_numactl01_seq.log 2>&1
cp /root/yunwei37/ai-os/workloads/cxl-micro/results/cxl_perf_parameter_sweep.csv numa_results/cxl_perf_parameter_sweep_numactl01_seq.csv

numactl --interleave=2,3 python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_perf_bandwidth_bench.py --parameter-sweep > numa_results/numa_results_numactl23_seq.log 2>&1
cp /root/yunwei37/ai-os/workloads/cxl-micro/results/cxl_perf_parameter_sweep.csv numa_results/cxl_perf_parameter_sweep_numactl23_seq.csv

# numactl --interleave=0,1,2,3 python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_perf_bandwidth_bench.py --parameter-sweep > numa_results/numa_results_numactl0123.log 2>&1
# cp /root/yunwei37/ai-os/workloads/cxl-micro/results/cxl_perf_parameter_sweep.csv numa_results/cxl_perf_parameter_sweep_numactl0123.csv

