# SPDX-License-Identifier: GPL-2.0

# Compiler and tools
CC = clang
CLANG = clang
LLC = llc
BPFTOOL = bpftool

# Flags
CFLAGS = -g -O2 -Wall
BPF_CFLAGS = -g -O2 -target bpf -D__TARGET_ARCH_x86_64 -I.
LDFLAGS = -lbpf -lelf -lz

# Files
BPF_PROG = simple_scheduler
TARGETS = $(BPF_PROG)

.PHONY: all clean

all: $(TARGETS)

# Generate vmlinux.h if it doesn't exist
vmlinux.h:
	$(BPFTOOL) btf dump file /sys/kernel/btf/vmlinux format c > $@

# Compile BPF program
$(BPF_PROG).bpf.o: $(BPF_PROG).bpf.c vmlinux.h
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@

# Generate BPF skeleton
$(BPF_PROG).skel.h: $(BPF_PROG).bpf.o
	$(BPFTOOL) gen skeleton $< > $@

# Compile userspace program
$(BPF_PROG): $(BPF_PROG).c $(BPF_PROG).skel.h
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)

clean:
	rm -f *.o *.skel.h $(TARGETS) vmlinux.h

# Helper targets
load: $(BPF_PROG)
	@echo "Loading scheduler..."
	@sudo ./$(BPF_PROG)

status:
	@echo "Scheduler status:"
	@cat /sys/kernel/sched_ext/state 2>/dev/null || echo "sched_ext not available"
	@echo "Enabled:"
	@cat /sys/kernel/sched_ext/enabled 2>/dev/null || echo "0"

enable:
	@echo "Enabling scheduler..."
	@echo 1 | sudo tee /sys/kernel/sched_ext/enabled

disable:
	@echo "Disabling scheduler..."
	@echo 0 | sudo tee /sys/kernel/sched_ext/enabled