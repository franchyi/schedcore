// SPDX-License-Identifier: GPL-2.0
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>

/* Include the generated skeleton header */
#include "simple_scheduler.skel.h"

static volatile int exiting = 0;

struct stats {
    __u64 cnt[4];  /* Match __NR_STATS from BPF program */
};

static const char *stat_names[] = {
    "enqueue",
    "dispatch",
    "dequeue",
    "select_cpu",
};

static void sig_handler(int sig)
{
    exiting = 1;
}


static void disable_scheduler(void)
{
    int fd;
    
    fd = open("/sys/kernel/sched_ext/enabled", O_WRONLY);
    if (fd < 0)
        return;
    
    write(fd, "0", 1);
    close(fd);
}

static void print_stats(struct simple_scheduler_bpf *skel)
{
    struct stats total_stats = {};
    struct stats *percpu_stats;
    __u32 key = 0;
    int nr_cpus = libbpf_num_possible_cpus();
    int i, j;
    
    /* Allocate buffer for per-CPU values */
    percpu_stats = calloc(nr_cpus, sizeof(struct stats));
    if (!percpu_stats)
        return;
    
    /* Get per-CPU stats and accumulate */
    if (bpf_map_lookup_elem(bpf_map__fd(skel->maps.stats_map), 
                            &key, percpu_stats) == 0) {
        for (i = 0; i < nr_cpus; i++) {
            for (j = 0; j < 4; j++) {
                total_stats.cnt[j] += percpu_stats[i].cnt[j];
            }
        }
    }
    
    free(percpu_stats);
    
    /* Print stats */
    printf("\n=== Scheduler Statistics ===\n");
    for (i = 0; i < 4; i++) {
        printf("%-12s: %llu\n", stat_names[i], total_stats.cnt[i]);
    }
    printf("===========================\n");
}

int main(int argc, char **argv)
{
    struct simple_scheduler_bpf *skel;
    int err = 0;
    
    /* Set up signal handlers */
    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);
    
    /* Open BPF skeleton */
    skel = simple_scheduler_bpf__open();
    if (!skel) {
        fprintf(stderr, "Failed to open BPF skeleton\n");
        return 1;
    }
    
    /* Load & verify BPF programs */
    err = simple_scheduler_bpf__load(skel);
    if (err) {
        fprintf(stderr, "Failed to load and verify BPF skeleton: %d\n", err);
        goto cleanup;
    }
    
    /* Attach BPF programs */
    err = simple_scheduler_bpf__attach(skel);
    if (err) {
        fprintf(stderr, "Failed to attach BPF skeleton: %d\n", err);
        goto cleanup;
    }
    
    printf("Simple eBPF scheduler loaded successfully!\n");
    printf("The scheduler is registered but not yet active.\n");
    printf("To activate: echo 1 > /sys/kernel/sched_ext/enabled\n");
    printf("To check status: cat /sys/kernel/sched_ext/state\n");
    printf("Press Ctrl+C to exit and unload the scheduler.\n\n");
    
    /* Main loop - print stats every 2 seconds */
    while (!exiting) {
        sleep(2);
        if (!exiting) {
            print_stats(skel);
        }
    }
    
    printf("\nShutting down scheduler...\n");
    
    /* Disable scheduler if it was enabled */
    disable_scheduler();
    
cleanup:
    simple_scheduler_bpf__destroy(skel);
    return err;
}