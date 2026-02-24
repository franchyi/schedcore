CLANG ?= clang
LLVM_STRIP ?= llvm-strip
BPFTOOL ?= bpftool
ARCH := $(shell uname -m | sed 's/x86_64/x86/' | sed 's/aarch64/arm64/')

INCLUDES := -I/usr/include -I/usr/include/$(ARCH)-linux-gnu
CFLAGS := -g -O2 -Wall -target bpf -D__TARGET_ARCH_$(ARCH)

all: sched.bpf.o

sched.bpf.o: sched.bpf.c
	$(CLANG) $(CFLAGS) $(INCLUDES) -c $< -o $@
	$(LLVM_STRIP) -g $@

clean:
	rm -f *.o

.PHONY: all clean