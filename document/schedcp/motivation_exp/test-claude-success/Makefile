# Makefile for building eBPF scheduler

# Compiler and tools
CC := gcc
CLANG := clang
BPFTOOL := bpftool

# Paths
LIBBPF_DIR := /usr/include/bpf
VMLINUX := vmlinux.h

# Flags
CFLAGS := -g -O2 -Wall
BPF_CFLAGS := -g -O2 -target bpf -D__TARGET_ARCH_x86_64
LDFLAGS := -lbpf -lelf -lz

# Targets
BPF_OBJS := minimal_scheduler.bpf.o
USER_TARGETS := minimal_scheduler

.PHONY: all clean vmlinux

all: vmlinux $(BPF_OBJS) $(USER_TARGETS)

# Generate vmlinux.h if it doesn't exist
vmlinux:
	@if [ ! -f $(VMLINUX) ]; then \
		echo "Generating vmlinux.h..."; \
		$(BPFTOOL) btf dump file /sys/kernel/btf/vmlinux format c > $(VMLINUX); \
	fi

# Build BPF object
%.bpf.o: %.bpf.c $(VMLINUX)
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@

# Build user-space program
%: %.c
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

# Load scheduler (requires root)
load: all
	@echo "Loading minimal scheduler..."
	@sudo ./minimal_scheduler

# Check if scheduler is loaded
status:
	@if [ -f /sys/kernel/sched_ext/root/ops ]; then \
		echo "Current scheduler: $$(cat /sys/kernel/sched_ext/root/ops)"; \
	else \
		echo "sched_ext not available or no custom scheduler loaded"; \
	fi

clean:
	rm -f $(BPF_OBJS) $(USER_TARGETS) $(VMLINUX)