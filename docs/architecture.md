# ZERO Architecture

## High-Level View

ZERO is structured as a task-oriented execution system.

A simplified architecture view looks like this:

```text
User Command
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
StepHandlers
    ↓
Workspace / Shared Workspace
    ↓
execution_log.json
    ↓
result.json
    ↓
runtime_state.json
    ↓
tasks.json
```

This architecture means ZERO does not directly jump from user input to a one-shot tool call.

Instead, it follows a structured execution model:
1. create task
2. generate plan
3. schedule task
4. execute steps
5. record logs and state
6. produce result
7. update task registry

---

## Main Modules

### 1. TaskManager
Responsible for task creation and task registration.

Main responsibilities:
- create task identity
- initialize task metadata
- write task records
- connect user task submission to planner/runtime flow

### 2. Planner
Responsible for converting natural language goals into structured steps.

Planner output is typically stored in:
- `plan.json`

Current planner direction:
- deterministic planner
- explicit step generation
- write_file / command / read_file style tasks
- planner-first execution model

### 3. Scheduler
Responsible for task selection and runtime triggering.

Current direction:
- scheduler tick model
- task selection
- future queue / priority / dependency expansion

### 4. TaskRuntime
Responsible for lifecycle and runtime state management.

Runtime state is stored in:
- `runtime_state.json`

Typical state flow:
- queued
- ready
- running
- finished
- failed

### 5. StepExecutor
Responsible for executing each step in the plan.

This is the core execution engine that runs step-by-step task behavior.

### 6. StepHandlers
Handler-based execution model for different step types.

Current handler set includes concepts such as:
- WriteFileStepHandler
- ReadFileStepHandler
- CommandStepHandler
- ToolStepHandler
- RespondStepHandler
- LLMStepHandler

This architecture keeps execution extensible.

---

## Workspace Architecture

ZERO uses a workspace-based execution model.

A typical structure looks like this:

```text
workspace/
  tasks/
    task_xxx/
      sandbox/
      plan.json
      runtime_state.json
      execution_log.json
      result.json
      task.json
      task.log
      task_runner.trace.log
      task_runtime.trace.log
  shared/
```

### Task Workspace
Each task has its own local execution area.

Task workspace responsibilities:
- task-local file output
- runtime state storage
- execution logs
- result artifacts
- task-specific traces

### Shared Workspace
Shared workspace is used for cross-task shared artifacts.

This enables:
- shared configuration files
- reusable generated outputs
- task-to-task handoff
- future pipeline-like workflows

---

## Runtime Files and Their Roles

### `plan.json`
Contains the planned step sequence for a task.

Role:
- workflow definition
- executor input
- planner output record

### `runtime_state.json`
Contains lifecycle and runtime state.

Typical fields may include:
- status
- retry_count
- depends_on
- timeout
- created_tick
- last_run_tick
- finished_tick
- runtime_status_history
- workspace_root
- task_dir
- shared_dir

Role:
- task lifecycle manager
- runtime state persistence
- scheduling and recovery foundation

### `execution_log.json`
Contains step execution history.

Role:
- step-by-step execution trace
- observability
- debugging
- verification

### `result.json`
Contains structured task output.

Role:
- final task artifact
- output summary
- downstream input candidate

### `tasks.json`
Contains task registry information.

Role:
- task index
- task lookup
- task tracking

---

## Task Lifecycle

A typical task lifecycle looks like this:

```text
task_submit
    ↓
TaskManager
    ↓
Planner generates steps
    ↓
plan.json saved
    ↓
Scheduler selects task
    ↓
TaskRuntime enters running state
    ↓
StepExecutor executes steps
    ↓
execution_log.json updated
    ↓
result.json produced
    ↓
runtime_state.json updated
    ↓
tasks.json status updated
    ↓
finished / failed
```

This lifecycle is one of the reasons ZERO is better described as a runtime system rather than a chatbot shell.

---

## Path Resolution and Workspace Boundary

ZERO is moving toward explicit workspace path rules.

Expected behavior:

- `shared/a.py` → `workspace/shared/a.py`
- `sandbox/a.py` → `workspace/tasks/<task_id>/sandbox/a.py`
- `a.py` → default to task sandbox
- `../xxx` → rejected

This is important because it defines:
- sandbox boundary
- shared artifact boundary
- path safety policy
- predictable file behavior

---

## Architectural Identity

At the current stage, ZERO is best understood as a hybrid of:

- local task runtime
- step-based execution engine
- workflow prototype
- agent runtime prototype
- task orchestration core

It is not yet a full platform, but it already has the core architecture of one.

---

## Summary

ZERO currently implements the essential shape of a task execution architecture:

- planner
- runtime
- scheduler
- executor
- workspace
- logs
- state
- result
- task registry

This is the foundation for a future local-first workflow engine / agent runtime platform.
