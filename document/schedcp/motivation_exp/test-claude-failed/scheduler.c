#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <linux/bpf.h>
#include <sys/resource.h>
#include <argp.h>

#include "scheduler.h"
#include "scheduler.skel.h"

static volatile sig_atomic_t exiting = 0;

static struct env {
    bool verbose;
    bool stats;
    int interval;
} env = {
    .verbose = false,
    .stats = false,
    .interval = 1,
};

const char *argp_program_version = "ebpf-scheduler 1.0";
const char *argp_program_bug_address = "<user@example.com>";
const char argp_program_doc[] =
"eBPF-based Linux scheduler\n"
"\n"
"This program implements a simple eBPF-based scheduler using sched_ext.\n"
"\n"
"USAGE: ./scheduler [OPTIONS]\n";

static const struct argp_option opts[] = {
    { "verbose", 'v', NULL, 0, "Verbose output" },
    { "stats", 's', NULL, 0, "Show scheduler statistics" },
    { "interval", 'i', "SECONDS", 0, "Stats interval (default: 1)" },
    { NULL, 'h', NULL, OPTION_HIDDEN, "Show the full help" },
    {},
};

static error_t parse_arg(int key, char *arg, struct argp_state *state)
{
    switch (key) {
    case 'v':
        env.verbose = true;
        break;
    case 's':
        env.stats = true;
        break;
    case 'i':
        env.interval = atoi(arg);
        if (env.interval <= 0) {
            fprintf(stderr, "Invalid interval: %s\n", arg);
            argp_usage(state);
        }
        break;
    case 'h':
        argp_state_help(state, stderr, ARGP_HELP_STD_HELP);
        break;
    default:
        return ARGP_ERR_UNKNOWN;
    }
    return 0;
}

static const struct argp argp = {
    .options = opts,
    .parser = parse_arg,
    .doc = argp_program_doc,
};

static void sig_handler(int sig)
{
    exiting = 1;
}

static int libbpf_print_fn(enum libbpf_print_level level, const char *format, va_list args)
{
    if (level == LIBBPF_DEBUG && !env.verbose)
        return 0;
    return vfprintf(stderr, format, args);
}

static void bump_memlock_rlimit(void)
{
    struct rlimit rlim_new = {
        .rlim_cur = RLIM_INFINITY,
        .rlim_max = RLIM_INFINITY,
    };

    if (setrlimit(RLIMIT_MEMLOCK, &rlim_new)) {
        fprintf(stderr, "Failed to increase RLIMIT_MEMLOCK limit!\n");
        exit(1);
    }
}

static void print_stats(struct scheduler_bpf *skel)
{
    struct task_stats value;
    __u32 key, prev_key = 0;
    int fd = bpf_map__fd(skel->maps.task_info);
    time_t now;
    
    time(&now);
    printf("\n=== Scheduler Statistics at %s", ctime(&now));
    printf("%-8s %-20s %-15s %-10s\n", "PID", "vruntime", "CPU", "Priority");
    printf("--------------------------------------------------------------\n");
    
    while (bpf_map_get_next_key(fd, &prev_key, &key) == 0) {
        if (bpf_map_lookup_elem(fd, &key, &value) == 0) {
            printf("%-8u %-20llu %-15u %-10u\n",
                   key, value.vruntime, value.cpu, value.priority);
        }
        prev_key = key;
    }
}

int main(int argc, char **argv)
{
    struct scheduler_bpf *skel;
    int err;

    err = argp_parse(&argp, argc, argv, 0, NULL, NULL);
    if (err)
        return err;

    libbpf_set_print(libbpf_print_fn);

    bump_memlock_rlimit();

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    skel = scheduler_bpf__open();
    if (!skel) {
        fprintf(stderr, "Failed to open BPF skeleton\n");
        return 1;
    }

    err = scheduler_bpf__load(skel);
    if (err) {
        fprintf(stderr, "Failed to load BPF skeleton: %d\n", err);
        goto cleanup;
    }

    err = scheduler_bpf__attach(skel);
    if (err) {
        fprintf(stderr, "Failed to attach BPF skeleton: %d\n", err);
        goto cleanup;
    }

    printf("eBPF scheduler loaded and attached. Press Ctrl-C to exit.\n");

    while (!exiting) {
        if (env.stats) {
            print_stats(skel);
        }
        sleep(env.interval);
    }

    printf("\nShutting down scheduler...\n");

cleanup:
    scheduler_bpf__destroy(skel);
    return err != 0;
}