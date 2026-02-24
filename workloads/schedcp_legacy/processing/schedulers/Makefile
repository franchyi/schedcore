# Simplified config-driven Makefile for loader-based scheduler template
# To add new scheduler: just add name to SCHEDULERS variable

# Configuration - Add new schedulers here
SCHEDULERS = vruntime fifo example compression ctest_suite ddos_log_analysis file_checksum git_add_different hotkey_aggregation video_transcode viral_product_analytics

# Build targets
LOADER = loader
BPF_TARGETS = $(addsuffix .bpf.o,$(SCHEDULERS))

# Compiler and tools
CLANG = clang
CC = gcc
BPFTOOL = bpftool

# Include paths - matching the main scx build system
PROJECT_ROOT = $(shell git rev-parse --show-toplevel)
SCX_INCLUDES = \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/include \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/include/scx \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/include/bpf-compat \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/include/lib \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/vmlinux \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/vmlinux/arch/x86

# System includes
SYS_INCLUDES = \
	-idirafter /usr/lib/llvm-19/lib/clang/19/include \
	-idirafter /usr/local/include \
	-idirafter /usr/include/x86_64-linux-gnu \
	-idirafter /usr/include

# BPF compilation flags
BPF_CFLAGS = -g -O2 -Wall -Wno-compare-distinct-pointer-types \
	-D__TARGET_ARCH_x86 -mcpu=v3 -mlittle-endian \
	$(SYS_INCLUDES) \
	$(SCX_INCLUDES)

# User space compilation flags
USER_CFLAGS = -O2 -g -Wall -Werror \
	$(shell pkg-config --cflags libbpf) \
	-I. \
	$(SCX_INCLUDES)

USER_LDFLAGS = $(shell pkg-config --libs libbpf) -lelf -lz -lzstd

# Default target
all: $(LOADER) $(BPF_TARGETS)

# Compile BPF programs
%.bpf.o: %.bpf.c
	@echo "Compiling BPF scheduler: $<"
	$(CLANG) $(BPF_CFLAGS) -target bpf -c $< -o $@

# Compile loader
$(LOADER): $(LOADER).c
	@echo "Compiling loader: $<"
	$(CC) $(USER_CFLAGS) $< -o $@ $(USER_LDFLAGS)

# Clean build artifacts
clean:
	rm -f $(LOADER) $(BPF_TARGETS)

# Install to scheduler bin directory
install: all
	mkdir -p ../sche_bin/
	cp $(LOADER) $(BPF_TARGETS) ../sche_bin/

# List available schedulers
list:
	@echo "Available schedulers:"
	@for sched in $(SCHEDULERS); do \
		echo "  $$sched"; \
	done
	@echo ""
	@echo "Usage:"
	@echo "  ./loader        - Load vruntime scheduler (default)"
	@echo "  ./loader -f     - Load FIFO scheduler"

# Help target
help:
	@echo "Configuration-driven scheduler template"
	@echo ""
	@echo "To add new scheduler:"
	@echo "  1. Create <name>.bpf.c file"
	@echo "  2. Add <name> to SCHEDULERS variable in this Makefile"
	@echo "  3. Update loader.c to handle new scheduler selection"
	@echo ""
	@echo "Available targets:"
	@echo "  make         - Build loader and all BPF schedulers"
	@echo "  make clean   - Clean build artifacts"
	@echo "  make install - Install to ../sche_bin/"
	@echo "  make list    - List available schedulers"
	@echo "  make help    - Show this help"

# Show current configuration
config:
	@echo "Current configuration:"
	@echo "  Schedulers: $(SCHEDULERS)"
	@echo "  BPF targets: $(BPF_TARGETS)"
	@echo "  Loader: $(LOADER)"

.PHONY: all clean install list help config