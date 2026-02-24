## Motivation
 In modern infrastructure, especially cloud platforms or serverless, the system manager who optimze the system is not the person who deploy the system, thus don't know the requirements and the behavior of their workload. Also, understand the workload requires deep domain knowledge, e.g. a traditional devops person cannot easily optimize the ML workload. LLM Agent can help better understanding the workload pattern and requirements, and provide spec/suggestions for further optimizations.
 It requires deep domain knowledge to design and implement new schedulers for the Linux kernel. LLM domain knowledge can help bridge the gap.
 The workload of target system may change overtime, it's impossible for human to redesign the scheduler algorithm every hour, but AI can.
Recently many RL algorithms for Linux schedulers on top conferences have been proposed, and also applied in production. However, RL algorithms cannot understand the requirements of target workload, especially applications level: e.g. is it a latency critical or a throughput critical application? What if our optimization goal is pure application level, e.g in the building process of software, if our scheduler can prioritize based on code dependency, we can have huge wins compared to baseline. No one will design a kernel schedule for such a specific case, but an AI agent can do it.

## Motivation experiments:
I run motivation experiments with the most advanced fully automatic coding agent, claude code, with prompt"write a scheduler in eBPF". Although it can successfully sync a basic FIFO scheduler without any human help, the generating process takes 33mins, including 221 LLM api calls, many try and error, multiple browser the web and search in the Linux source code, cost around $6. Compare to that, a experienced human only takes 5 min to do same thing.
This long process, wide privilege and high cost is unacceptable in production, especially when the scheduler gets more complex.

So, applying LLM Agent for optimizing Linux schedulers is challenging:

 How to ensure the generated code will not break the system or cause soft‑lockup, stalls, starves, or has a negative impact on the target workload?
 How to ensure the generation process requires reasonable time and cost?

## design 

Our key design ideas are:
To build systems that remain effective as AI models evolve, we separate concerns by letting AI handle decision-making while the system focuses on exposing the right signals, tools, and abstractions—so that future, more capable models and AI Agents can immediately perform better without redesigning the underlying system.

So, our system involved 3 components:
 A multi-layer DSL for configuring existing schedulers and programming new schedulers. The DSL should be simple and easy to use, like the one line DSL of bpftrace.
 A tool set interface and knowledge database to help AI understand the current system, understand target workload and dynamic config or programming the OS scheduler, design as MCP server(https://modelcontextprotocol.io/introduction)
 A daemon for monitoring the performance and invoke the AI Agents.

## basic experiments 

My preliminary experiments show that llm agetnt can generate the application profile, choose and config the Right scheduler to make schbench(A benchmark recommended by the sched_ext project) has 50% lower latency and 30% more throughput.
