### What’s out there?

| Purpose                                         | Project / Mechanism                 | “DSL” level                                                                   | Status                               | How it works                                                                                                                                                                         |
| ----------------------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| *Research‑grade scheduler description language* | **Bossa**                           | True DSL (event‑driven syntax)                                                | Research, not upstream (2001‑2005)   | You write scheduling policies in a small, C‑like language; the Bossa compiler turns them into a kernel module.                                                                       |
| *Pluggable schedulers in mainline*              | **sched\_ext / SCX** (Linux ≥ 6.12) | eBPF programs (C/Rust/Java → BPF byte‑code). Not a high‑level DSL, but close. | In‑tree & actively developed         | A set of BPF hooks (`enqueue`, `dequeue`, `pick_next`, …). You can load, swap or stop a scheduler at run‑time; examples live in `tools/sched_ext`. ([Linux Kernel Documentation][1]) |
| *Real‑time research playground*                 | **LITMUS^RT**                       | C plug‑in API; no separate DSL                                                | Out‑of‑tree, widely used in academia | Add new multiprocessor RT schedulers as “plugins”; managed via `/proc/litmus` or liblitmus tools. ([Litmus-RT][2])                                                                   |
| *User‑space priority rules*                     | **ananicy‑cpp** and similar daemons | Simple JSON/TOML rule files                                                   | Production (desktop distros)         | Match processes by name/UID and apply `nice`, `ionice`, cgroup weight, etc. Good for tuning, but doesn’t touch the kernel’s core scheduler. ([GitHub][3])                            |

---

### So, is there a *general* DSL today?

* **Mainline Linux** still has no official, universal DSL for describing or tuning the core CPU scheduler.

  * Day‑to‑day tuning is done through sysfs/procfs knobs (`/proc/sys/kernel/sched_*`), cgroup v2 (`cpu.weight`, `cpu.max`), or libs like `sched_setattr()`.
  * Projects such as *tuned* or *systemd‑udev rules* wrap these knobs, but they’re just config files, not languages.

* **Bossa** was the closest thing to a real DSL. It proved the idea works, but the codebase never merged and is now largely dormant. Still worth reading if you’re looking for language ideas or static verification tricks.

* **sched\_ext (SCX)** has effectively become *the* experimental path:

  * You can prototype in a few hundred lines of C or Rust, compile to BPF, and swap it in without rebooting.
  * Several helper libraries (`scx_rustland_core`, `scx_utils`) raise the abstraction a bit, but it’s still “code” rather than “declarative DSL.” ([GitHub][4])

* **Real‑time kernels** (PREEMPT\_RT, LITMUS^RT) prefer a plugin API in C. Their focus is determinism, not generic configuration.

---

### If you want to build your own DSL

1. **Pick a substrate**

   * For upstream friendliness, target *sched\_ext* hooks—your compiler could emit eBPF C skeletons.
   * For deep RT work, generate LITMUS^RT plugins.

2. **Expose the right primitives**

   * Events: `task_wake`, `yield`, timer tick, IRQ entry…
   * State: run‑queues, per‑CPU load, vruntime, deadlines.
   * Actions: pick next, preempt, migrate.

3. **Safety checks in the compiler**

   * Ensure progress (no empty run‑queue stalls).
   * BPF verifier already guards memory safety; your DSL compiler can add policy‑specific sanity checks (e.g., “each task must eventually enqueue”).

4. **Hot‑reload & metrics**

   * Emit BPF maps or perf counters so a userspace agent can debug and live‑tune parameters without recompiling the DSL program.

---

### Quick takeaway

*For everyday tuning, stick with sysctl / cgroups or a daemon like ananicy‑cpp.*
If you need *new* policies, today’s practical path is: **write an eBPF scheduler with sched\_ext**. A true, high‑level, declarative DSL is still a research topic—Bossa shows it’s doable, but nobody has carried a DSL into mainline yet.

[1]: https://docs.kernel.org/scheduler/sched-ext.html "Extensible Scheduler Class - The Linux Kernel documentation"
[2]: https://www.litmus-rt.org/create_plugin/create_plugin.html "Writing a LITMUS^RT Scheduler Plugin"
[3]: https://github.com/nefelim4ag/Ananicy "Ananicy - is Another auto nice daemon, with community rules ..."
[4]: https://github.com/arighi/scx_rust_scheduler "arighi/scx_rust_scheduler: Template to implement Linux kernel ..."

#### Quick background

* **Who made it & when?**  A small INRIA/École des Mines Nantes team (Gilles Muller, Julia Lawall, etc.) started Bossa around 2001–2005 to let app developers write their *own* Linux schedulers without digging into thousands of lines of kernel C.&#x20;
* **Core idea.**  Split “*policy*” (which task to run) from “*mechanism*” (context‑switch, timers). They rewired the kernel so scheduling points fire **events**, and a mini runtime forwards those events to code you write in a little domain‑specific language (DSL).

---

### What the DSL looks like

```bossa
states = {
  RUNNING  running : process;
  READY    ready   : select queue;
  BLOCKED  blocked : queue;
}

ordering_criteria = { lowest deadline }  // EDF in 1 line
handler(event e) {
  On unblock.preemptive {
    if (e.target in blocked && e.target > running)
        running => ready;
    e.target => ready;
  }
  On bossa.schedule {
    select() => running;
  }
}
```

* **Declarations** say which per‑task fields you need, the READY/BLOCKED queues, etc.
* **Handlers** are little C‑ish functions that run when an event fires (task wakes, tick, schedule, …).
* A full EDF scheduler was **≈ 160 lines** of DSL instead of \~1000 lines of kernel C.&#x20;

---

### Tool‑chain & run‑time

1. **Compiler** → turns the DSL into C, links it with a small library, then builds a kernel module.
2. **Verifier** → before codegen it checks simple safety rules (e.g. you never pick a task that’s blocked).&#x20;
3. **Event bus in the kernel** (added by patching Linux 2.4) sends `processBlock.*`, `processUnblock.*`, `clockTick`, `schedule`, etc. to your module. Table of events in the original paper shows about a dozen of them.&#x20;
4. **Hot‑plug** – you can insmod a new policy or build a tree of “virtual schedulers” that slice CPU time among children.

---

### What Bossa promised

| Claim                                                                              | Evidence in the papers                  |
| ---------------------------------------------------------------------------------- | --------------------------------------- |
| **Easier prototyping** – “non‑kernel” students coded schedulers in a few hours     | 2005 LSM paper, §1 & §2                 |
| **Tiny code** – most real policies **< 200 DSL lines**                             | same source                             |
| **Compile‑time safety** – static checks on states/events                           | verifier discussed in DSL design paper  |
| **Low overhead** – kernel patches + runtime **< 5 %** slowdown in micro‑benchmarks | AOP/DSL paper, §2.1                     |
| **Portability** – they ported to Linux 2.4 and an RTOS called Jaluna               | LSM paper, §5                           |

---

### How it actually works in practice

1. **Patch the kernel once** to add the runtime + event hooks.
2. **Write policy in DSL**, run `bossa-cc`, get a `.ko`.
3. **Load** it: `insmod my_edf.ko root_sched=1` (their demo).
4. **Runtime** queues events, calls your handler; you manipulate process states with `x => READY` instead of messing with `task_struct` directly.

---

### Why it never hit mainline

* Built on Linux 2.4; needs heavy patching to newer kernels.
* Interest moved to CFS and later eBPF‑based sched\_ext; Bossa team shifted to other research.
* No SMP support in early versions; today’s multi‑socket machines would need extra work.

---

### Take‑away for you

* If you just want **quick experiments** on a modern kernel, sched\_ext + eBPF is the path.
* If you’re hunting for **language ideas** (static checks, event model, state transfer syntax) Bossa’s papers are a goldmine—you can mine the grammar and maybe retarget its compiler to spit out eBPF skeletons.
* Performance claims (≤ 5 % overhead) are for early‑2000s hardware; still, the structure is lightweight and could map well to BPF maps/tail calls today.

