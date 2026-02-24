# BPF Scheduler Framework Guide

## Overview

This framework provides a modular system for implementing and testing Linux kernel schedulers using BPF (Berkeley Packet Filter) technology via the sched-ext (scx) infrastructure.

## Framework Components

### 1. Core Infrastructure
- **loader.c**: Generic BPF scheduler loader
- **Makefile**: Build system for compiling schedulers
- **pid_filename_header.h**: Process tracking utilities

### 2. Example Schedulers
- **fifo.bpf.c**: Simple FIFO (First-In-First-Out) scheduler
- **vruntime.bpf.c**: Weighted fair scheduler using virtual runtime
- **ctest.bpf.c**: Priority scheduler with filename-based filtering

## How to Use Existing Schedulers

### 1. Build All Schedulers
```bash
make clean
make
```

### 2. List Available Schedulers
```bash
make list
# Output: Available schedulers: vruntime fifo ctest
```

### 3. Load a Scheduler
```bash
# Basic usage
sudo ./loader fifo.bpf.o

# With verbose output for debugging
sudo ./loader vruntime.bpf.o -v

# The scheduler will run until you press Ctrl+C
```

## How to Add a New Scheduler

### Step 1: Create Your Scheduler File

Create a new file `myscheduler.bpf.c`. read the example [fifo.bpf.c](fifo.bpf.c) and [vruntime.bpf.c](vruntime.bpf.c) for reference.

### Step 2: Add to Makefile

Edit the Makefile and add your scheduler name:

```makefile
# List of schedulers to build
SCHEDULERS := vruntime fifo myscheduler
```

### Step 3: Build Your Scheduler

```bash
make
```

### Step 4: Load and Test

```bash
sudo ./loader myscheduler.bpf.o
```

## Advanced Features

Deteck file name (for python program)

```c
#include "pid_filename_header.h"

/* Detect if task is a "long" task by checking filename */
static bool is_long_task(struct task_struct *p)
{
	pid_t pid = p->pid;
	struct filename_info *info;
	char local_filename[MAX_FILENAME_LEN];
	const char *basename;
	int last_slash = -1;
	
	/* Get filename info for this PID */
	info = bpf_map_lookup_elem(&pid_to_filename, &pid);
	if (!info)
		return false;
	
	int is_large = (info->filename[0] == '.' && info->filename[1] == '/' 
		&& info->filename[2] == 'l' && info->filename[3] == 'a' 
		&& info->filename[4] == 'r' && info->filename[5] == 'g' 
		&& info->filename[6] == 'e');
	if (is_large)
		bpf_printk("large task: %s\n", info->filename);
	return is_large;
}
```

Detect comm name (for C program)

```c
static bool is_long_task(struct task_struct *p)
{
	char comm[16];
	
	if (bpf_probe_read_kernel_str(comm, sizeof(comm), p->comm) < 0)
		return false;
	
	/* Check for start with "large" */
	return (comm[0] == 'l' && comm[1] == 'a' && comm[2] == 'r' && 
	        comm[3] == 'g' && comm[4] == 'e');
}
```
