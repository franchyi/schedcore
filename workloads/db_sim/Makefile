# Makefile for db_sim workload and db_aware BPF scheduler

# Compiler and tools
CC = gcc
CLANG = clang

# Project root (for SCX includes)
PROJECT_ROOT = $(shell git rev-parse --show-toplevel)
LOADER_DIR = $(PROJECT_ROOT)/bpf_loader

# SCX include paths (same as bpf_loader/Makefile)
SCX_INCLUDES = \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/include \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/include/scx \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/include/arch/x86 \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/include/bpf-compat \
	-I$(PROJECT_ROOT)/scheduler/scx/scheds/include/lib

SYS_INCLUDES = \
	-idirafter /usr/lib/llvm-18/lib/clang/18/include \
	-idirafter /usr/local/include \
	-idirafter /usr/include/x86_64-linux-gnu \
	-idirafter /usr/include

BPF_CFLAGS = -g -O2 -Wall -Wno-compare-distinct-pointer-types \
	-D__TARGET_ARCH_x86 -mcpu=v3 -mlittle-endian \
	$(SYS_INCLUDES) \
	$(SCX_INCLUDES)

# User space flags
USER_CFLAGS = -O2 -g -Wall -pthread
USER_LDFLAGS = -lpthread -lm

# Targets
all: db_sim db_aware.bpf.o

db_sim: db_sim.c
	@echo "Compiling db_sim workload..."
	$(CC) $(USER_CFLAGS) $< -o $@ $(USER_LDFLAGS)

db_aware.bpf.o: db_aware.bpf.c
	@echo "Compiling db_aware BPF scheduler..."
	$(CLANG) $(BPF_CFLAGS) -target bpf -c $< -o $@

clean:
	rm -f db_sim db_aware.bpf.o

.PHONY: all clean
