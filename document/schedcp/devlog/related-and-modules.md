# Ecosystem & Inspiration

| Project | Focus | Why it matters to SchedCP |
|---------|-------|--------------------------|
| **bpftune** (Oracle) | Always-on autotuning of TCP buffers & other sysctls with BPF | Proven pattern for "observe → tune → verify" loops. |
| **tuned** (Red Hat/SUSE) | Daemon that switches profiles and tweaks CPU / I/O / VM / power on the fly | Shows demand for profile-based tuning and plug-in architecture. |
| **sched_ext / scx** | Framework for writing BPF-backed schedulers and loading them at run-time | SchedCP can load & auto-parametrize these schedulers. |
| **KernelOracle** | Deep-learning model that predicts CFS decisions | Evidence that ML can improve scheduling; potential policy engine. |
| **SchedViz** (Google) | Collects & visualises kernel scheduling traces | Useful companion for debugging SchedCP policies. |
| **eBPF Energy Monitor** | Process-level power telemetry via eBPF | Feeds power-aware signals into SchedCP RL loops. |

---

# Beyond Scheduler & Sysctl – Candidate Modules

| Area | First shipping module idea | Quick win & data source |
|------|---------------------------|--------------------------|
| **CPU frequency / C-states** | Smart governor that biases P-cores vs E-cores based on latency SLA | `perf`, `intel_pstate`, sched_ext hooks |
| **Memory management** | Adaptive `vm.swappiness` + DAMON-aware reclaim policy | DAMON stats via `damon_reclaim` events |
| **Block-I/O** | Per-device IO-scheduler selector (`mq-deadline`, `bfq`, `kyber`) | `blk_iolatency` tracepoints |
| **Networking** | Autoselect congestion control (`bbr2` vs `cubic`) & tune socket queues | `tcp:tcp_probe` + bpftune net-buffer lessons |
| **IRQ / NUMA** | Automatic IRQ affinity & page migration to minimise remote-access stalls | `irqbalance` data + `sched:sched_stat_runtime` |
| **Cgroups & QoS** | RL agent that rewrites weight/limit knobs for bursty workloads | cgroup v2 stats + container labels |
| **Thermals / power** | DVFS policy that respects battery or data-centre carbon budget | RAPL / ACPI telemetry + eBPF energy monitor |
| **Observability glue** | Unified ring-buffer exporter (Prometheus/OpenTelemetry) | Standard gRPC/OTLP for dashboards |
| **Safety net** | A/B rollback & "flight-recorder" for every knob change | Git-style history + `bpftune-sysctl` guard rails |

Each module follows the same pattern: **collect metrics → decide via RL/LLM or heuristics → apply with eBPF/`sysfs` → verify**.  Start with scheduler + sysctl, then iterate down the list as the feedback-loop library stabilises.