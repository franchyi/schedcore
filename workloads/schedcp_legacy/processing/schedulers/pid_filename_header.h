// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
#ifndef PID_FILENAME_HEADER_H
#define PID_FILENAME_HEADER_H

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>

#define MAX_FILENAME_LEN 256
#define MAX_PID_ENTRIES 10240

/* Structure to hold filename information */
struct filename_info {
	char filename[MAX_FILENAME_LEN];
};

/* BPF hash map: PID -> filename */
struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, MAX_PID_ENTRIES);
	__type(key, pid_t);
	__type(value, struct filename_info);
} pid_to_filename SEC(".maps");

/* Tracepoint: capture filename when process exec's */
SEC("tp/sched/sched_process_exec")
int pid_filename_handle_exec(struct trace_event_raw_sched_process_exec *ctx)
{
	struct filename_info info = {};
	unsigned fname_off;
	pid_t pid;

	/* Get PID of the process */
	pid = bpf_get_current_pid_tgid() >> 32;

	/* Extract filename offset from the tracepoint data */
	fname_off = ctx->__data_loc_filename & 0xFFFF;
	
	/* Read the filename from the tracepoint context */
	bpf_probe_read_str(&info.filename, sizeof(info.filename), (void *)ctx + fname_off);

	/* Store PID->filename mapping */
	bpf_map_update_elem(&pid_to_filename, &pid, &info, BPF_ANY);

	return 0;
}

/* Tracepoint: cleanup when process exits */
SEC("tp/sched/sched_process_exit")
int pid_filename_handle_exit(struct trace_event_raw_sched_process_template *ctx)
{
	pid_t pid, tid;
	u64 id;

	/* Get PID and TID of exiting thread/process */
	id = bpf_get_current_pid_tgid();
	pid = id >> 32;
	tid = (u32)id;

	/* Only cleanup for process exits, not thread exits */
	if (pid != tid)
		return 0;

	/* Remove the PID entry from our map */
	bpf_map_delete_elem(&pid_to_filename, &pid);

	return 0;
}

/* Helper function to get filename from PID
 * Returns: pointer to filename string, or NULL if PID not found
 */
static __always_inline const char* get_filename_from_pid(pid_t pid)
{
	struct filename_info *info;
	
	info = bpf_map_lookup_elem(&pid_to_filename, &pid);
	if (!info)
		return NULL;
	
	return info->filename;
}

/* Helper function to store filename for a PID manually
 * Returns: 0 on success, negative error code on failure
 */
static __always_inline int store_filename_for_pid(pid_t pid, const char *filename, u32 filename_len)
{
	struct filename_info info = {};
	u32 len = filename_len;
	
	/* Ensure we don't overflow the buffer */
	if (len >= MAX_FILENAME_LEN)
		len = MAX_FILENAME_LEN - 1;
	
	/* Copy filename to our structure */
	if (bpf_probe_read_kernel_str(info.filename, len + 1, filename) < 0)
		return -1;
	
	/* Store in map */
	return bpf_map_update_elem(&pid_to_filename, &pid, &info, BPF_ANY);
}

/* Helper function to remove PID entry manually
 * Returns: 0 on success, negative error code on failure
 */
static __always_inline int remove_pid_entry(pid_t pid)
{
	return bpf_map_delete_elem(&pid_to_filename, &pid);
}

/* Helper function to check if PID exists in map
 * Returns: true if PID has filename entry, false otherwise
 */
static __always_inline bool pid_has_filename(pid_t pid)
{
	return bpf_map_lookup_elem(&pid_to_filename, &pid) != NULL;
}

/* Optional: Get filename for current process */
static __always_inline const char* get_current_filename(void)
{
	pid_t pid = bpf_get_current_pid_tgid() >> 32;
	return get_filename_from_pid(pid);
}

#endif /* PID_FILENAME_HEADER_H */