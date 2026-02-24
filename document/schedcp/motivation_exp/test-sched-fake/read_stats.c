#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>

int main(int argc, char **argv)
{
    int switch_map_fd, wakeup_map_fd, cpu_map_fd;
    __u32 key = 0;
    __u64 switch_count = 0, wakeup_count = 0;
    __u64 cpu_counts[16] = {0};
    
    // Find BPF maps by name
    switch_map_fd = bpf_obj_get("/sys/fs/bpf/sched_switch_count");
    if (switch_map_fd < 0) {
        // Try to find by ID
        struct bpf_map_info info = {};
        __u32 info_len = sizeof(info);
        int fd;
        
        for (int id = 1; id < 1000; id++) {
            fd = bpf_map_get_fd_by_id(id);
            if (fd < 0) continue;
            
            if (bpf_obj_get_info_by_fd(fd, &info, &info_len) == 0) {
                if (strstr(info.name, "sched_switch_count")) {
                    switch_map_fd = fd;
                } else if (strstr(info.name, "sched_wakeup_count")) {
                    wakeup_map_fd = fd;
                } else if (strstr(info.name, "cpu_switch_count")) {
                    cpu_map_fd = fd;
                } else {
                    close(fd);
                }
            }
        }
    }
    
    printf("eBPF Scheduler Statistics\n");
    printf("========================\n\n");
    
    // Read scheduler switch count
    if (switch_map_fd >= 0) {
        if (bpf_map_lookup_elem(switch_map_fd, &key, &switch_count) == 0) {
            printf("Total scheduler switches: %llu\n", switch_count);
        }
    }
    
    // Read wakeup count
    if (wakeup_map_fd >= 0) {
        if (bpf_map_lookup_elem(wakeup_map_fd, &key, &wakeup_count) == 0) {
            printf("Total wakeup events: %llu\n", wakeup_count);
        }
    }
    
    // Read per-CPU statistics
    if (cpu_map_fd >= 0) {
        printf("\nPer-CPU switch counts:\n");
        for (int cpu = 0; cpu < 16; cpu++) {
            __u32 cpu_key = cpu;
            __u64 count = 0;
            if (bpf_map_lookup_elem(cpu_map_fd, &cpu_key, &count) == 0 && count > 0) {
                printf("  CPU %2d: %llu switches\n", cpu, count);
            }
        }
    }
    
    return 0;
}