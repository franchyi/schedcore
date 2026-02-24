# Sched-Agent: Multi-Agent Framework for OS Optimization

## Overview

Sched-Agent is a multi-agent AI framework built on top of schedcp, where specialized agents collaborate to perform end-to-end scheduler optimization. The framework decomposes the complex reasoning process into manageable roles, mirroring an expert human team. Each agent corresponds to one of the four stages in the optimization loop: observation, planning, execution, and learning.

## Architecture

The framework uses Claude Code's subagent architecture, enabling:
- Specialized AI assistants for specific tasks
- Customized system prompts per agent
- Task-specific tools and capabilities
- Separate context windows for focused reasoning

## Agent Roles and Responsibilities

### 1. Observation & Analysis Agent

**Purpose**: Performs deep semantic analysis of workloads and synthesizes findings into structured Workload Profiles.

**Capabilities**:
- **Multi-modal Sensing**:
  - File system access (source code, Makefiles, configs)
  - Diagnostic commands (`git log`, `make`, `perf stat`, `strace`)
  - Real-time performance metrics via APIs
  - Custom analysis script generation

- **Analysis Sandbox Features**:
  - Containerized secure environment
  - Atomic tools (`get_cpu_stats()`, `set_scheduler_param()`)
  - Dynamic tool composition for novel scenarios
  - No fixed workflows - agent decides sequences

- **Output**: Structured Workload Profile containing:
  - Natural language workload summary
  - Key performance characteristics
  - Resource requirements
  - Explicit optimization goals

- **Proactive Monitoring**:
  - Registers callback URLs with schedcp
  - Receives notifications for performance drops
  - Triggers new analysis cycles on workload changes

### 2. Planning Agent

**Purpose**: Synthesizes concrete optimization plans using Workload Profiles to guide strategy.

**Decision Process**:
1. **Repository Query**: Searches Policy Repository using profile keywords
2. **Strategy Selection** (autonomous choice):
   - **Reconfigure**: Adjust parameters of perfect-fit scheduler
   - **Revise**: Patch close-match scheduler for adaptation
   - **Generate**: Create new scheduler from algorithm primitives

**Key Features**:
- Pluggable agent architecture (works with any capable LLM)
- Semantic search capabilities
- Access to:
  - Production scheduler collection
  - Algorithm primitive library
  - RL algorithms for parameter tuning
  - Rich performance metadata

### 3. Execution Agent

**Purpose**: Validates and deploys proposed policies with strict safety guarantees.

**Workflow**:

1. **Code Synthesis**:
   - Generates patches or new eBPF programs
   - Leverages code generation pipeline:
     - Template selection based on workload patterns
     - Workload-specific parameter injection
     - Incremental compilation with feedback loops

2. **Validation Gauntlet** (Three Layers):
   
   a. **Static Pre-flight Checks**:
      - Kernel BPF verifier simulation
      - Instruction count analysis
      - Overhead estimation
      - Additional static analysis tools
   
   b. **Dynamic Sandbox Validation**:
      - Secure compilation and execution
      - Unit, integration, and stress testing
      - Performance measurement vs. goals
      - Logical correctness verification
   
   c. **Production Rollout**:
      - Deployment token issuance
      - Explicit deployment call
      - Continuous monitoring
      - Automatic rollback on degradation

**Safety Philosophy**: Treats AI as potentially non-cautious actor with non-negotiable validation.

### 4. Learning Agent

**Purpose**: Translates action outcomes into durable, reusable knowledge for system improvement.

**Learning Mechanisms**:

1. **Short-term In-Context Learning**:
   - Calls `get_feedback` tool for outcome summaries
   - Uses feedback to inform next decisions
   - Performs in-context reinforcement learning

2. **Long-term System Evolution**:
   - Updates Policy Repository with performance data
   - Refines historical metrics
   - Contributes successful novel schedulers
   - Builds collective system intelligence

**Feedback Processing**:
- Accesses reward signals via Feedback Channel
- Structures data for repository updates
- Identifies patterns for future optimization

## Example Workflow: Kernel Compilation

### Stage 1: Observation
```
Observation Agent:
- Analyzes Linux kernel source tree
- Executes `make -j` to understand build process
- Runs `perf stat` for resource profiling
- Produces Profile: "CPU-intensive parallel compilation with short-lived processes"
```

### Stage 2: Planning
```
Planning Agent:
- Queries repository with "throughput", "compilation"
- Retrieves `scx_rusty` as baseline
- Decides to revise: adds dependency-awareness
- Generates patch specification
```

### Stage 3: Execution
```
Execution Agent:
- Synthesizes patched scheduler code
- Submits to Execution Verifier
- Passes validation gauntlet
- Receives deployment token
- Deploys to production
```

### Stage 4: Learning
```
Learning Agent:
- Receives feedback: 45% makespan reduction
- Updates repository metrics
- Contributes improved scheduler
- Enhances future optimization capability
```

## Inter-Agent Communication

### Information Flow
1. **Workload Profile**: Observation → Planning
2. **Optimization Plan**: Planning → Execution
3. **Deployment Results**: Execution → Learning
4. **Performance Feedback**: Learning → All agents

### Coordination Mechanisms
- Structured data formats between agents
- Asynchronous message passing
- Event-driven triggers
- Shared access to schedcp services

## Implementation Details

### Technology Stack
- Claude Code subagent architecture
- Model Context Protocol (MCP)
- Separate LLM contexts per agent
- Specialized prompting strategies

### Agent Capabilities
| Agent | Primary Tools | Context Focus |
|-------|--------------|---------------|
| Observation | Profiling tools, code analysis | Workload understanding |
| Planning | Repository search, strategy selection | Policy synthesis |
| Execution | Code generation, validation | Safe deployment |
| Learning | Feedback analysis, knowledge curation | System improvement |

## Benefits of Multi-Agent Design

1. **Specialization**: Each agent optimized for its specific task
2. **Scalability**: Parallel agent execution possible
3. **Modularity**: Easy to update/replace individual agents
4. **Reliability**: Failure isolation between stages
5. **Interpretability**: Clear separation of concerns

## Future Enhancements

- Additional specialized agents (e.g., Security Agent, Cost Optimization Agent)
- Cross-workload learning and transfer
- Distributed multi-node coordination
- Advanced RL algorithms for policy evolution
- Human-in-the-loop validation options