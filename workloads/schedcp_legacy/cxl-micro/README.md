# command


numactl --interleave=0,1,2  python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_micro_bench_start.py

numactl --interleave=0,1,2  python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_micro_bench_start.py --parameter-sweep

numactl --interleave=3  python /root/yunwei37/ai-os/workloads/cxl-micro/cxl_micro_bench_start.py --parameter-sweep --production-only


