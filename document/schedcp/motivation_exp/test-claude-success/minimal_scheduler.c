// SPDX-License-Identifier: GPL-2.0
/*
 * User-space loader for the minimal eBPF scheduler
 * 
 * This program loads the BPF scheduler and monitors its operation
 */

#include <stdio.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <sys/stat.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>

static volatile int exit_req = 0;

static void sig_handler(int sig)
{
    exit_req = 1;
}

static int read_stats(struct bpf_map *map)
{
    __u32 key = 0;
    __u64 total = 0;
    __u64 val;
    int cpu, nr_cpus;

    nr_cpus = libbpf_num_possible_cpus();
    if (nr_cpus < 0) {
        fprintf(stderr, "Failed to get number of CPUs\n");
        return -1;
    }

    __u64 vals[nr_cpus];
    
    if (bpf_map_lookup_elem(bpf_map__fd(map), &key, vals) == 0) {
        for (cpu = 0; cpu < nr_cpus; cpu++)
            total += vals[cpu];
        printf("Total enqueues: %llu\n", total);
    }

    return 0;
}

int main(int argc, char **argv)
{
    struct bpf_object *obj;
    struct bpf_link *link;
    struct bpf_map *stats_map;
    int err;

    /* Set up signal handler for clean exit */
    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    /* Open and load the BPF object file */
    obj = bpf_object__open_file("minimal_scheduler.bpf.o", NULL);
    if (!obj) {
        fprintf(stderr, "Failed to open BPF object\n");
        return 1;
    }

    err = bpf_object__load(obj);
    if (err) {
        fprintf(stderr, "Failed to load BPF object: %d\n", err);
        goto cleanup;
    }

    /* Get the stats map */
    stats_map = bpf_object__find_map_by_name(obj, "stats");
    if (!stats_map) {
        fprintf(stderr, "Failed to find stats map\n");
        err = -ENOENT;
        goto cleanup;
    }

    /* Link the scheduler struct_ops */
    link = bpf_map__attach_struct_ops(bpf_object__find_map_by_name(obj, "minimal_scheduler"));
    if (!link) {
        fprintf(stderr, "Failed to attach struct_ops\n");
        err = -errno;
        goto cleanup;
    }

    printf("Minimal scheduler loaded and running. Press Ctrl+C to exit.\n");

    /* Main loop - print statistics */
    while (!exit_req) {
        sleep(1);
        read_stats(stats_map);
    }

    printf("\nShutting down scheduler...\n");

    /* Detach the scheduler */
    bpf_link__destroy(link);

cleanup:
    bpf_object__close(obj);
    return err != 0;
}