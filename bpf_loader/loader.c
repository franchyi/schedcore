/* SPDX-License-Identifier: GPL-2.0 */
/*
 * General BPF scheduler loader - dynamically loads any .bpf.o file
 *
 * Copyright (c) 2022 Meta Platforms, Inc. and affiliates.
 * Copyright (c) 2022 Tejun Heo <tj@kernel.org>
 * Copyright (c) 2022 David Vernet <dvernet@meta.com>
 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <assert.h>
#include <libgen.h>
#include <string.h>
#include <errno.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <bpf/btf.h>
#include <scx/common.h>

const char help_fmt[] =
"A general BPF scheduler loader.\n"
"\n"
"Loads any BPF scheduler from .bpf.o file.\n"
"\n"
"Usage: %s <bpf_object_file> [-v]\n"
"\n"
"  <bpf_object_file>  Path to the .bpf.o file to load\n"
"  -v                 Print libbpf debug messages\n"
"  -h                 Display this help and exit\n";

static bool verbose;
static volatile int exit_req;

static struct {
	struct bpf_object *obj;
	struct bpf_link *link;
	char *sched_name;
	struct bpf_map *uei_map;
} current_sched;

static int libbpf_print_fn(enum libbpf_print_level level, const char *format, va_list args)
{
	if (level == LIBBPF_DEBUG && !verbose)
		return 0;
	return vfprintf(stderr, format, args);
}

static void sigint_handler(int sig)
{
	exit_req = 1;
}

/* Enum entries to resolve from kernel BTF and set in .rodata */
struct enum_entry {
	const char *type;       /* BTF enum type name */
	const char *name;       /* enum value name */
	const char *var_name;   /* .rodata variable name (e.g., "__SCX_DSQ_GLOBAL") */
};

static const struct enum_entry scx_enums[] = {
	{ "scx_public_consts", "SCX_OPS_NAME_LEN", "__SCX_OPS_NAME_LEN" },
	{ "scx_public_consts", "SCX_SLICE_DFL", "__SCX_SLICE_DFL" },
	{ "scx_public_consts", "SCX_SLICE_INF", "__SCX_SLICE_INF" },
	{ "scx_dsq_id_flags", "SCX_DSQ_FLAG_BUILTIN", "__SCX_DSQ_FLAG_BUILTIN" },
	{ "scx_dsq_id_flags", "SCX_DSQ_FLAG_LOCAL_ON", "__SCX_DSQ_FLAG_LOCAL_ON" },
	{ "scx_dsq_id_flags", "SCX_DSQ_INVALID", "__SCX_DSQ_INVALID" },
	{ "scx_dsq_id_flags", "SCX_DSQ_GLOBAL", "__SCX_DSQ_GLOBAL" },
	{ "scx_dsq_id_flags", "SCX_DSQ_LOCAL", "__SCX_DSQ_LOCAL" },
	{ "scx_dsq_id_flags", "SCX_DSQ_LOCAL_ON", "__SCX_DSQ_LOCAL_ON" },
	{ "scx_dsq_id_flags", "SCX_DSQ_LOCAL_CPU_MASK", "__SCX_DSQ_LOCAL_CPU_MASK" },
	{ "scx_kick_flags", "SCX_KICK_IDLE", "__SCX_KICK_IDLE" },
	{ "scx_kick_flags", "SCX_KICK_PREEMPT", "__SCX_KICK_PREEMPT" },
	{ "scx_kick_flags", "SCX_KICK_WAIT", "__SCX_KICK_WAIT" },
	{ "scx_enq_flags", "SCX_ENQ_WAKEUP", "__SCX_ENQ_WAKEUP" },
	{ "scx_enq_flags", "SCX_ENQ_HEAD", "__SCX_ENQ_HEAD" },
	{ "scx_enq_flags", "SCX_ENQ_PREEMPT", "__SCX_ENQ_PREEMPT" },
	{ "scx_enq_flags", "SCX_ENQ_REENQ", "__SCX_ENQ_REENQ" },
	{ "scx_enq_flags", "SCX_ENQ_LAST", "__SCX_ENQ_LAST" },
	{ "scx_enq_flags", "SCX_ENQ_CLEAR_OPSS", "__SCX_ENQ_CLEAR_OPSS" },
	{ "scx_enq_flags", "SCX_ENQ_DSQ_PRIQ", "__SCX_ENQ_DSQ_PRIQ" },
	{ "scx_ent_flags", "SCX_TASK_QUEUED", "__SCX_TASK_QUEUED" },
	{ "scx_ent_flags", "SCX_TASK_RESET_RUNNABLE_AT", "__SCX_TASK_RESET_RUNNABLE_AT" },
	{ "scx_ent_flags", "SCX_TASK_DEQD_FOR_SLEEP", "__SCX_TASK_DEQD_FOR_SLEEP" },
	{ "scx_ent_flags", "SCX_TASK_STATE_SHIFT", "__SCX_TASK_STATE_SHIFT" },
	{ "scx_ent_flags", "SCX_TASK_STATE_BITS", "__SCX_TASK_STATE_BITS" },
	{ "scx_ent_flags", "SCX_TASK_STATE_MASK", "__SCX_TASK_STATE_MASK" },
	{ "scx_ent_flags", "SCX_TASK_CURSOR", "__SCX_TASK_CURSOR" },
	{ "scx_task_state", "SCX_TASK_NONE", "__SCX_TASK_NONE" },
	{ "scx_task_state", "SCX_TASK_INIT", "__SCX_TASK_INIT" },
	{ "scx_task_state", "SCX_TASK_READY", "__SCX_TASK_READY" },
	{ "scx_task_state", "SCX_TASK_ENABLED", "__SCX_TASK_ENABLED" },
	{ "scx_task_state", "SCX_TASK_NR_STATES", "__SCX_TASK_NR_STATES" },
	{ "scx_ent_dsq_flags", "SCX_TASK_DSQ_ON_PRIQ", "__SCX_TASK_DSQ_ON_PRIQ" },
	{ "scx_rq_flags", "SCX_RQ_ONLINE", "__SCX_RQ_ONLINE" },
	{ "scx_rq_flags", "SCX_RQ_CAN_STOP_TICK", "__SCX_RQ_CAN_STOP_TICK" },
	{ "scx_rq_flags", "SCX_RQ_BAL_PENDING", "__SCX_RQ_BAL_PENDING" },
	{ "scx_rq_flags", "SCX_RQ_BAL_KEEP", "__SCX_RQ_BAL_KEEP" },
	{ "scx_rq_flags", "SCX_RQ_BYPASSING", "__SCX_RQ_BYPASSING" },
	{ "scx_rq_flags", "SCX_RQ_CLK_VALID", "__SCX_RQ_CLK_VALID" },
	{ "scx_rq_flags", "SCX_RQ_IN_WAKEUP", "__SCX_RQ_IN_WAKEUP" },
	{ "scx_rq_flags", "SCX_RQ_IN_BALANCE", "__SCX_RQ_IN_BALANCE" },
};

#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))

static bool read_btf_enum(struct btf *btf, const char *type, const char *name, uint64_t *v)
{
	const struct btf_type *t;
	int tid, i;

	tid = btf__find_by_name(btf, type);
	if (tid < 0)
		return false;

	t = btf__type_by_id(btf, tid);
	if (!t)
		return false;

	if (btf_is_enum(t)) {
		const struct btf_enum *e = btf_enum(t);
		for (i = 0; i < btf_vlen(t); i++) {
			const char *n = btf__name_by_offset(btf, e[i].name_off);
			if (n && !strcmp(n, name)) {
				*v = (uint64_t)(uint32_t)e[i].val;
				return true;
			}
		}
	} else if (btf_is_enum64(t)) {
		const struct btf_enum64 *e = btf_enum64(t);
		for (i = 0; i < btf_vlen(t); i++) {
			const char *n = btf__name_by_offset(btf, e[i].name_off);
			if (n && !strcmp(n, name)) {
				*v = btf_enum64_value(&e[i]);
				return true;
			}
		}
	}

	return false;
}

/*
 * Resolve SCX enum constants from kernel BTF and set them in the BPF
 * object's .rodata section before loading. This is required because
 * sched-ext enum values (like SCX_DSQ_GLOBAL) are defined as weak
 * volatile variables in the BPF program that must be initialized by
 * the loader from the running kernel's BTF.
 */
static int resolve_scx_enums(struct bpf_object *obj)
{
	struct btf *vmlinux_btf;
	struct bpf_map *rodata_map = NULL;
	struct bpf_map *map;
	size_t i;
	int set_count = 0;

	vmlinux_btf = btf__load_vmlinux_btf();
	if (!vmlinux_btf) {
		fprintf(stderr, "Warning: Failed to load vmlinux BTF, enum resolution skipped\n");
		return 0;
	}

	/* Find the .rodata map */
	bpf_object__for_each_map(map, obj) {
		const char *name = bpf_map__name(map);
		if (name && strstr(name, ".rodata")) {
			rodata_map = map;
			break;
		}
	}

	if (!rodata_map) {
		if (verbose)
			fprintf(stderr, "No .rodata map found, skipping enum resolution\n");
		btf__free(vmlinux_btf);
		return 0;
	}

	/*
	 * Get the BTF of the BPF object to find variable offsets in .rodata.
	 * We iterate the BTF to find each __SCX_* variable and its offset,
	 * then write the resolved value at that offset in the initial data.
	 */
	const struct btf *obj_btf = bpf_object__btf(obj);
	if (!obj_btf) {
		fprintf(stderr, "Warning: No BTF in BPF object\n");
		btf__free(vmlinux_btf);
		return 0;
	}

	/* Find the .rodata datasec in the object BTF */
	int rodata_id = 0;
	int nr_types = btf__type_cnt(obj_btf);
	const struct btf_type *rodata_type = NULL;

	for (int id = 1; id < nr_types; id++) {
		const struct btf_type *t = btf__type_by_id(obj_btf, id);
		if (!btf_is_datasec(t))
			continue;
		const char *sec_name = btf__name_by_offset(obj_btf, t->name_off);
		if (sec_name && strstr(sec_name, ".rodata")) {
			rodata_type = t;
			rodata_id = id;
			break;
		}
	}

	if (!rodata_type) {
		if (verbose)
			fprintf(stderr, "No .rodata datasec in BTF\n");
		btf__free(vmlinux_btf);
		return 0;
	}

	(void)rodata_id;

	/* Get initial value of the rodata map */
	size_t rodata_sz = bpf_map__value_size(rodata_map);
	void *rodata = malloc(rodata_sz);
	if (!rodata) {
		btf__free(vmlinux_btf);
		return -1;
	}

	/* Get initial data - this is the mmap'd initial value */
	void *init_data = bpf_map__initial_value(rodata_map, &rodata_sz);
	if (!init_data) {
		fprintf(stderr, "Warning: Cannot get .rodata initial value\n");
		free(rodata);
		btf__free(vmlinux_btf);
		return 0;
	}
	memcpy(rodata, init_data, rodata_sz);

	/* Iterate datasec variables to find __SCX_* entries */
	const struct btf_var_secinfo *vsi = btf_var_secinfos(rodata_type);
	int nr_vars = btf_vlen(rodata_type);

	for (int v = 0; v < nr_vars; v++) {
		const struct btf_type *var_type = btf__type_by_id(obj_btf, vsi[v].type);
		if (!var_type || !btf_is_var(var_type))
			continue;

		const char *var_name = btf__name_by_offset(obj_btf, var_type->name_off);
		if (!var_name || strncmp(var_name, "__SCX_", 6) != 0)
			continue;

		/* Find matching enum entry */
		for (i = 0; i < ARRAY_SIZE(scx_enums); i++) {
			if (strcmp(var_name, scx_enums[i].var_name) != 0)
				continue;

			uint64_t val = 0;
			if (read_btf_enum(vmlinux_btf, scx_enums[i].type,
					  scx_enums[i].name, &val)) {
				/* Write the value at the variable's offset in .rodata */
				if (vsi[v].offset + sizeof(uint64_t) <= rodata_sz) {
					memcpy((char *)rodata + vsi[v].offset, &val, sizeof(val));
					set_count++;
					if (verbose)
						printf("  Set %s = 0x%lx\n", var_name, val);
				}
			} else if (verbose) {
				fprintf(stderr, "  Warning: Could not resolve %s from BTF\n", var_name);
			}
			break;
		}
	}

	/* Write back the modified rodata */
	if (set_count > 0) {
		memcpy(init_data, rodata, rodata_sz);
		printf("Resolved %d SCX enum constants from kernel BTF\n", set_count);
	}

	free(rodata);
	btf__free(vmlinux_btf);
	return 0;
}

static int load_bpf_scheduler(const char *obj_path)
{
	struct bpf_object *obj;
	struct bpf_link *link;
	struct bpf_map *ops_map = NULL;
	struct bpf_program *prog;
	int err;

	obj = bpf_object__open(obj_path);
	if (!obj) {
		fprintf(stderr, "Failed to open BPF object: %s\n", strerror(errno));
		return -1;
	}

	/* Resolve SCX enum constants from kernel BTF before loading */
	err = resolve_scx_enums(obj);
	if (err) {
		fprintf(stderr, "Failed to resolve SCX enums\n");
		bpf_object__close(obj);
		return -1;
	}

	err = bpf_object__load(obj);
	if (err) {
		fprintf(stderr, "Failed to load BPF object: %s\n", strerror(-err));
		bpf_object__close(obj);
		return -1;
	}

	/* Attach any tracepoint programs (for pid_filename tracking) */
	bpf_object__for_each_program(prog, obj) {
		const char *prog_name = bpf_program__name(prog);
		
		/* Check if this is one of our pid_filename tracepoint handlers */
		if (strstr(prog_name, "pid_filename_handle_exec") ||
		    strstr(prog_name, "pid_filename_handle_exit")) {
			struct bpf_link *tp_link = bpf_program__attach(prog);
			if (!tp_link) {
				fprintf(stderr, "Warning: Failed to attach tracepoint %s: %s\n",
				        prog_name, strerror(errno));
				/* Continue anyway - not critical for scheduler operation */
			} else {
				printf("Attached tracepoint: %s\n", prog_name);
				/* Note: We're not storing these links, they'll be cleaned up
				 * when the object is closed */
			}
		}
	}

	bpf_object__for_each_map(ops_map, obj) {
		if (bpf_map__type(ops_map) == BPF_MAP_TYPE_STRUCT_OPS) {
			break;
		}
	}
	
	if (!ops_map) {
		fprintf(stderr, "Failed to find struct_ops map\n");
		bpf_object__close(obj);
		return -1;
	}

	link = bpf_map__attach_struct_ops(ops_map);
	if (!link) {
		fprintf(stderr, "Failed to attach struct_ops: %s\n", strerror(errno));
		bpf_object__close(obj);
		return -1;
	}

	current_sched.obj = obj;
	current_sched.link = link;
	current_sched.sched_name = strdup(basename((char *)obj_path));

	printf("BPF scheduler %s loaded successfully\n", current_sched.sched_name);
	
	/* Check if pid_to_filename map exists */
	if (bpf_object__find_map_by_name(obj, "pid_to_filename")) {
		printf("Note: This scheduler uses PID-to-filename tracking\n");
	}
	
	return 0;
}

int main(int argc, char **argv)
{
	const char *obj_path = NULL;
	int opt;

	libbpf_set_print(libbpf_print_fn);
	signal(SIGINT, sigint_handler);
	signal(SIGTERM, sigint_handler);

	while ((opt = getopt(argc, argv, "vh")) != -1) {
		switch (opt) {
		case 'v':
			verbose = true;
			break;
		default:
			fprintf(stderr, help_fmt, basename(argv[0]));
			return opt != 'h';
		}
	}

	if (optind >= argc) {
		fprintf(stderr, "Error: BPF object file path is required\n\n");
		fprintf(stderr, help_fmt, basename(argv[0]));
		return 1;
	}

	obj_path = argv[optind];

	if (access(obj_path, R_OK) != 0) {
		fprintf(stderr, "Error: Cannot access BPF object file: %s\n", obj_path);
		return 1;
	}

	if (load_bpf_scheduler(obj_path) < 0) {
		return 1;
	}

	printf("Press Ctrl+C to unload scheduler\n");
	while (!exit_req) {
		sleep(1);
	}

	bpf_link__destroy(current_sched.link);
	bpf_object__close(current_sched.obj);
	if (current_sched.sched_name) {
		printf("Scheduler %s unloaded\n", current_sched.sched_name);
		free(current_sched.sched_name);
	}
	return 0;
}