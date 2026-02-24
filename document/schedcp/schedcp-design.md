# schedcp: System Control Plane for OS Optimization

## Overview

schedcp is a modular control plane that provides a stable and secure "API for OS optimization." It acts as the systems framework that enables AI agents to interact with the Linux kernel's scheduler without compromising stability. The framework exposes its services via the Model Context Protocol (MCP), cleanly separating high-level policy orchestration from low-level observation and execution.

## Design Principles

### 1. Decoupling and Role Separation
- **Goal**: Future-proof the framework by separating system responsibilities from AI capabilities
- **Approach**: Decouple "what to optimize" (AI's domain) from "how to observe and act" (system's domain)
- **Benefit**: Framework remains relevant as AI models evolve

### 2. Safety-First Interface Design
- **Goal**: Protect system stability from potentially incorrect or malicious agent-generated code
- **Approach**: Treat AI as a potentially non-cautious actor and design defensive interfaces
- **Benefit**: Prevents catastrophic failures by default rather than relying on agent caution

### 3. Context and Feedback Balance
- **Goal**: Optimize information flow given LLM context window and token cost constraints
- **Approach**: Adaptive context provisioning - start with minimal summaries and progressively provide details
- **Benefit**: Balances cost and precision while avoiding information overload

### 4. Composable Tool Architecture
- **Goal**: Leverage LLM's reasoning capabilities for novel solution generation
- **Approach**: Provide atomic tools following Unix philosophy, let agent compose complex workflows
- **Benefit**: Enables dynamic, creative optimization strategies

## Core Components

### 1. Workload Analysis Engine

**Purpose**: Acts as the agent's sensorium, providing adaptive system observation capabilities.

**Key Features**:
- **Multi-layered View**: Balances context richness against token costs
- **High-level APIs**: Pre-processed summaries of CPU load, memory usage, etc.
- **Profiling Tools**: Secure, sandboxed access to `perf`, `strace`, and other Linux tools
- **eBPF Probes**: Library of dynamically attachable probes for fine-grained, low-overhead data collection
- **Feedback Channel**: Delivers concise performance outcomes (e.g., % change in makespan/latency)

**Benefits**:
- Enables in-context reinforcement learning
- Supports iterative policy refinement
- Provides workload-specific instrumentation

### 2. Scheduler Policy Repository

**Purpose**: Persistent, evolving library of scheduling solutions to reduce policy generation costs.

**Key Features**:
- **Vector Database**: Stores eBPF scheduler code with rich metadata
- **Semantic Search**: Natural language queries for relevant schedulers/primitives
- **Metadata Storage**: 
  - Natural language descriptions
  - Target workload specifications
  - Historical performance metrics
- **Long-term Curation**: Asynchronously updates metrics from deployments
- **Knowledge Evolution**: Promotes successful novel policies to permanent library

**Benefits**:
- Reduces latency and cost of policy generation
- Enables code reuse and composition
- Builds collective system intelligence over time

### 3. Execution Verifier

**Purpose**: Multi-stage validation pipeline ensuring all agent-generated code is safe before deployment.

**Validation Stages**:

1. **Static Analysis Sandbox**
   - eBPF verifier simulation
   - Complexity analysis
   - Safety violation detection
   - Overhead estimation

2. **Dynamic Validation Sandbox**
   - Compilation and execution in micro-VMs
   - Correctness testing against synthetic workloads
   - Performance regression testing
   - Issues signed deployment token upon success

3. **Production Safeguards**
   - Canary deployment mechanism
   - Continuous KPI monitoring
   - Circuit breaker with automatic rollback
   - Preserves last known-good scheduler

**Benefits**:
- Non-negotiable safety guarantees
- Prevents system instability
- Enables safe experimentation

## Implementation Details

### API Design
- Exposed via Model Context Protocol (MCP)
- RESTful endpoints for each service
- Structured request/response formats
- Authentication and rate limiting

### Security Model
- No root privileges for agents
- Sandboxed execution environments
- Signed deployment tokens
- Audit logging for all actions

### Performance Considerations
- Low-overhead eBPF instrumentation
- Efficient vector database queries
- Parallel validation pipelines
- Minimal production deployment impact

## Integration Points

### Input Interfaces
- MCP protocol for agent communication
- Linux kernel eBPF subsystem
- Standard profiling tool APIs
- Performance monitoring hooks

### Output Interfaces
- Deployment tokens for verified policies
- Performance metrics and feedback
- Repository update mechanisms
- Rollback triggers

## Usage Example

```python
# Agent workflow using schedcp
# 1. Analyze workload
profile = workload_analysis_engine.analyze(
    workload_id="kernel_compile",
    tools=["perf", "strace"],
    probes=["sched_switch", "task_newtask"]
)

# 2. Search for relevant policies
candidates = policy_repository.search(
    query="parallel compilation throughput",
    limit=5
)

# 3. Generate and validate new policy
policy = generate_policy(profile, candidates)
token = execution_verifier.validate(policy)

# 4. Deploy with monitoring
if token:
    deployment = deploy_scheduler(token)
    monitor_performance(deployment)
```

## Future Extensions

- Support for additional kernel subsystems beyond scheduling
- Integration with cloud orchestration platforms
- Multi-node distributed optimization
- Enhanced ML-based policy synthesis