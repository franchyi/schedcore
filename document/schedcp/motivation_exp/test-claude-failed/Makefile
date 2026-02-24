CC = clang
CFLAGS = -g -O2 -Wall
INCLUDES = -I/usr/include/bpf -I.
LIBS = -lbpf -lelf -lz

ARCH := $(shell uname -m | sed 's/x86_64/x86/' | sed 's/aarch64/arm64/')
VMLINUX_BTF := /sys/kernel/btf/vmlinux

BPF_CFLAGS = -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) $(INCLUDES)

all: scheduler

vmlinux.h:
	bpftool btf dump file $(VMLINUX_BTF) format c > vmlinux.h

scheduler.skel.h: scheduler.bpf.o
	bpftool gen skeleton scheduler.bpf.o > scheduler.skel.h

scheduler.bpf.o: scheduler.bpf.c vmlinux.h scheduler.h
	$(CC) $(BPF_CFLAGS) -c scheduler.bpf.c -o scheduler.bpf.o

scheduler: scheduler.c scheduler.skel.h scheduler.h
	$(CC) $(CFLAGS) $(INCLUDES) scheduler.c -o scheduler $(LIBS)

clean:
	rm -f *.o scheduler scheduler.skel.h vmlinux.h

install: scheduler
	install -m 755 scheduler /usr/local/bin/

uninstall:
	rm -f /usr/local/bin/scheduler

.PHONY: all clean install uninstall