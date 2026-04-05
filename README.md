# ZERO AI

## What is ZERO

ZERO is a local-first AI task execution system designed to turn user intent into structured, verifiable task execution.

Instead of only responding with text, ZERO can:
- plan tasks
- execute steps
- manage task state
- record execution logs
- isolate task workspaces
- produce structured results

ZERO is closer to a **Task Runtime / Agent Execution Engine** than a traditional chatbot.

---

## Project Positioning

ZERO is not primarily a consumer chatbot project.

ZERO is being built as:
- Local AI Agent Runtime
- Task Orchestrator
- Workflow Engine Prototype
- Execution System for AI-driven tasks
- Automation / Engineering Assistant Infrastructure

The long-term goal is to build a local-first execution platform where AI can reliably plan and execute real tasks, not just generate text.

---

## Core Concepts

### Task
A task is a unit of work created from user intent.

Each task has:
- plan.json
- runtime_state.json
- execution_log.json
- result.json
- its own workspace
- lifecycle status

### Planner
The planner converts a goal into structured steps.

Example steps:
- write_file
- read_file
- command
- tool
- respond
- llm

### Runtime State
Runtime state tracks the lifecycle of a task:

```
queued → ready → running → finished
```

or

```
queued → ready → running → failed
```

### Workspace
Each task runs inside its own workspace:

```
workspace/
  tasks/
    task_xxx/
      sandbox/
      plan.json
      runtime_state.json
      execution_log.json
      result.json
  shared/
```

This provides isolation and reproducibility.

### Execution Log
Each step execution is recorded in execution_log.json, making tasks inspectable and verifiable.

---

## Example Workflow

Typical ZERO task flow:

```
User command
    ↓
TaskManager
    ↓
Planner
    ↓
plan.json
    ↓
Scheduler
    ↓
TaskRuntime
    ↓
StepExecutor
    ↓
Workspace
    ↓
execution_log.json
    ↓
result.json
    ↓
Task finished
```

This structured flow is what makes ZERO different from simple agent demos.

---

## Current Capabilities

ZERO currently supports:
- Task creation
- Planner
- Runtime state machine
- Scheduler tick
- Step executor
- Step handlers
- Task workspace
- Shared workspace
- Execution logs
- Result output
- Task lifecycle management

This already forms the core of a **Task Runtime / Orchestrator prototype**.

---

## Roadmap Direction

Planned system expansion includes:
- Task queue
- Priority scheduling
- Retry / replan loop
- Dependency scheduling
- DAG workflow
- Multi-worker execution
- Dashboard / Web UI
- Plugin tool system
- API / SDK
- Distributed task runtime

---

## Project Vision

The long-term vision of ZERO is to evolve from:

```
Local Task Runner
        ↓
Task Runtime
        ↓
Workflow Engine
        ↓
Agent Execution Platform
        ↓
Task Operating System
```

ZERO is an ongoing system engineering project focused on building execution infrastructure for AI systems.

---

## Status

ZERO is currently in the **Task Runtime / Orchestrator Prototype** stage.
