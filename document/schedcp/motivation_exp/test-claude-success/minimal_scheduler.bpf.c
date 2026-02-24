// SPDX-License-Identifier: GPL-2.0
/*
 * Minimal eBPF scheduler using sched_ext
 * 
 * This is a simple global FIFO scheduler that demonstrates the basic
 * structure of an eBPF scheduler using the sched_ext framework.
 */

#include <vmlinux.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

char _license[] SEC("license") = "GPL";

/*
 * Global FIFO queue ID - tasks will be enqueued here
 * SCX_DSQ_GLOBAL is a predefined global dispatch queue
 */
#define SHARED_DSQ 0

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(key_size, sizeof(u32));
    __uint(value_size, sizeof(u64));
    __uint(max_entries, 2);
} stats SEC(".maps");

/*
 * Initialize the scheduler
 * This is called when the scheduler is loaded
 */
SEC("struct_ops/minimal_init")
s32 BPF_PROG(minimal_init)
{
    return 0;
}

/*
 * Exit handler - cleanup when scheduler is unloaded
 */
SEC("struct_ops/minimal_exit")
void BPF_PROG(minimal_exit, struct scx_exit_info *ei)
{
    /* Can add cleanup code here if needed */
}

/*
 * Task enqueue - called when a task becomes runnable
 * 
 * This is where we decide which dispatch queue (DSQ) to place the task in.
 * For this simple scheduler, we just use a global FIFO queue.
 */
SEC("struct_ops/minimal_enqueue")
void BPF_PROG(minimal_enqueue, struct task_struct *p, u64 enq_flags)
{
    u32 key = 0;
    u64 *cnt;

    /* Update statistics */
    cnt = bpf_map_lookup_elem(&stats, &key);
    if (cnt)
        (*cnt)++;

    /*
     * Dispatch task to the global queue with slice (time quantum)
     * SCX_SLICE_DFL is the default time slice
     */
    scx_bpf_dispatch(p, SHARED_DSQ, SCX_SLICE_DFL, enq_flags);
}

/*
 * CPU dispatch - called when a CPU needs work
 * 
 * This function tells the CPU which dispatch queue to consume tasks from.
 */
SEC("struct_ops/minimal_dispatch")
void BPF_PROG(minimal_dispatch, s32 cpu, struct task_struct *prev)
{
    /*
     * Consume tasks from the global queue
     * This will dequeue and run the next task in FIFO order
     */
    scx_bpf_consume(SHARED_DSQ);
}

/*
 * Optional: Select CPU for task
 * 
 * This can be used to implement CPU affinity or load balancing.
 * If not implemented, the default behavior is used.
 */
SEC("struct_ops/minimal_select_cpu")
s32 BPF_PROG(minimal_select_cpu, struct task_struct *p, s32 prev_cpu, u64 wake_flags)
{
    /* 
     * Return negative value to use default CPU selection
     * Or return a specific CPU number to pin the task
     */
    return -1;
}

/*
 * Define the scheduler operations structure
 * This tells the kernel which functions to call for scheduling events
 */
SEC(".struct_ops.link")
struct sched_ext_ops minimal_scheduler = {
    .enqueue        = (void *)minimal_enqueue,
    .dispatch       = (void *)minimal_dispatch,
    .select_cpu     = (void *)minimal_select_cpu,
    .init           = (void *)minimal_init,
    .exit           = (void *)minimal_exit,
    .name           = "minimal_scheduler",
};