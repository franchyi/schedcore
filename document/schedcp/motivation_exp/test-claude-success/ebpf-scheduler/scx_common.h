/* SPDX-License-Identifier: GPL-2.0 */
#ifndef __SCX_COMMON_H
#define __SCX_COMMON_H

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

/* BPF_STRUCT_OPS macro for sched_ext */
#define BPF_STRUCT_OPS(name, args...) \
    SEC("struct_ops/"#name) \
    BPF_PROG(name, ##args)

#define BPF_STRUCT_OPS_SLEEPABLE(name, args...) \
    SEC("struct_ops.s/"#name) \
    BPF_PROG(name, ##args)

/* Default time slice */
#define SCX_SLICE_DFL   20000000ULL    /* 20ms */

/* Helper function declarations */
s32 scx_bpf_create_dsq(u64 dsq_id, s32 node) __ksym;
void scx_bpf_destroy_dsq(u64 dsq_id) __ksym;
void scx_bpf_dispatch(struct task_struct *p, u64 dsq_id, u64 slice, u64 enq_flags) __ksym;
void scx_bpf_dispatch_vtime(struct task_struct *p, u64 dsq_id, u64 slice, u64 vtime, u64 enq_flags) __ksym;
bool scx_bpf_consume(u64 dsq_id) __ksym;
s32 scx_bpf_select_cpu_dfl(struct task_struct *p, s32 prev_cpu, u64 wake_flags, bool *found) __ksym;
s32 scx_bpf_pick_idle_cpu(const struct cpumask *cpus_allowed, u64 flags) __ksym;
s32 scx_bpf_pick_any_cpu(const struct cpumask *cpus_allowed, u64 flags) __ksym;
bool scx_bpf_test_and_clear_cpu_idle(s32 cpu) __ksym;
void scx_bpf_kick_cpu(s32 cpu, u64 flags) __ksym;
s32 scx_bpf_dsq_nr_queued(u64 dsq_id) __ksym;
void scx_bpf_exit(s64 exit_code, const char *reason, u64 reason_len) __ksym;

#endif /* __SCX_COMMON_H */