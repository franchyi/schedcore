#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>

static volatile bool exiting;

static void sig_handler(int sig)
{
    exiting = true;
}

static int libbpf_print_fn(enum libbpf_print_level level, const char *format, va_list args)
{
    return vfprintf(stderr, format, args);
}

int main(int argc, char **argv)
{
    struct bpf_object *obj;
    struct bpf_program *prog;
    struct bpf_link *links[10];
    int link_count = 0;
    int err;

    // Set up libbpf errors and debug info callback
    libbpf_set_print(libbpf_print_fn);

    // Load BPF object file
    obj = bpf_object__open_file("sched.bpf.o", NULL);
    if (libbpf_get_error(obj)) {
        fprintf(stderr, "ERROR: opening BPF object file failed\n");
        return 1;
    }

    // Load BPF object into kernel
    if (bpf_object__load(obj)) {
        fprintf(stderr, "ERROR: loading BPF object file failed\n");
        goto cleanup;
    }

    // Attach all programs
    bpf_object__for_each_program(prog, obj) {
        links[link_count] = bpf_program__attach(prog);
        if (libbpf_get_error(links[link_count])) {
            fprintf(stderr, "ERROR: attaching BPF program %s failed: %s\n",
                    bpf_program__name(prog), strerror(errno));
            links[link_count] = NULL;
        } else {
            printf("Successfully attached: %s\n", bpf_program__name(prog));
            link_count++;
        }
    }

    if (link_count == 0) {
        fprintf(stderr, "ERROR: no programs were attached\n");
        goto cleanup;
    }

    // Set up signal handlers
    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    printf("\nScheduler monitoring is running. Press Ctrl-C to stop.\n");
    printf("Check /sys/kernel/debug/tracing/trace_pipe for output\n\n");

    // Sleep until interrupted
    while (!exiting) {
        sleep(1);
    }

cleanup:
    // Detach all links
    for (int i = 0; i < link_count; i++) {
        if (links[i])
            bpf_link__destroy(links[i]);
    }
    bpf_object__close(obj);

    return 0;
}