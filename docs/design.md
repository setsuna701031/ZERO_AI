# ZERO Design Notes

## Design Philosophy

ZERO is designed around one central idea:

> AI execution should be structured, inspectable, and recoverable.

This means ZERO does not treat task execution as a single hidden LLM response.

Instead, it treats execution as a stateful runtime process with:
- explicit planning
- explicit steps
- explicit workspace
- explicit logs
- explicit result files
- explicit runtime state

---

## Why Planner-First Instead of Direct Tool Calling

A common pattern in lightweight agent projects is:

```text
User Prompt → LLM → Tool Call → Response
```

This is fast, but it often has problems:
- hard to inspect
- hard to reproduce
- hard to debug
- hard to recover after failure
- difficult to verify

ZERO instead prefers:

```text
User Prompt → Planner → plan.json → Executor → Logs / State / Result
```

Advantages:
- task behavior becomes visible
- steps can be checked before or after execution
- logs and state become inspectable
- future retry / replan is easier
- execution is more suitable for safety and engineering workflows

---

## JSON-Driven Runtime State

ZERO externalizes important runtime information into JSON files.

This includes:
- `plan.json`
- `runtime_state.json`
- `execution_log.json`
- `result.json`
- `tasks.json`

This design has several advantages.

### Benefits
1. Inspectable state  
   The current task state can be viewed directly from files.

2. Better debugging  
   When something fails, it is easier to locate which stage failed.

3. Recoverability  
   A runtime that stores its state explicitly is easier to resume or replan.

4. Verifiability  
   Execution can be checked through step logs and outputs.

5. Lower coupling  
   State is not trapped entirely in memory.

---

## Task Workspace Model

ZERO uses a workspace-per-task model.

Typical structure:

```text
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

### Why this matters
This gives each task:
- its own local execution area
- isolated artifacts
- local logs
- local result files
- safer file behavior

This is closer to a true runtime system than a simple script runner.

---

## Shared Workspace Model

ZERO also introduces a shared workspace:

```text
workspace/shared/
```

This is used for:
- shared artifacts
- cross-task resources
- reusable outputs
- future workflow handoff

Without a shared workspace, tasks remain completely isolated.

With a shared workspace, ZERO begins to support:
- coordination across tasks
- pipeline-like workflows
- artifact reuse
- future dependency chains

---

## Path Resolution Rules

Path handling is a foundational part of the Task OS model.

Current intended rules are:

### Rule 1 — Shared path
`shared/a.py`
→ `workspace/shared/a.py`

### Rule 2 — Explicit sandbox path
`sandbox/a.py`
→ `workspace/tasks/<task_id>/sandbox/a.py`

### Rule 3 — Default relative path
`a.py`
→ default to `workspace/tasks/<task_id>/sandbox/a.py`

### Rule 4 — Path traversal protection
`../xxx`
→ rejected

### Why these rules matter
These rules define:
- workspace boundary policy
- predictable file behavior
- shared vs task-local resource separation
- path safety
- protection against accidental or unsafe escape from workspace

This is one of the most important infrastructure decisions in ZERO.

---

## Runtime Status Flow

ZERO treats task execution as a lifecycle, not a one-shot event.

Typical state flow:

```text
queued → ready → running → finished
```

or

```text
queued → ready → running → failed
```

This is important because it provides:
- a scheduler-compatible state model
- future retry support
- future replan support
- visible lifecycle transitions
- better debugging of where a task stopped

---

## Step Executor and Handler Model

ZERO uses a handler-based execution system.

Instead of hardcoding all step behavior in one file, step types are delegated to specific handlers.

Examples:
- write_file
- read_file
- command
- tool
- respond
- llm

### Why this matters
This makes the system:
- more modular
- easier to extend
- easier to test
- less likely to accumulate execution logic in one giant file

This is an important design choice for keeping the runtime extensible.

---

## Execution Logs as System Evidence

Execution logs are not just debug output.

In ZERO, `execution_log.json` is part of the system contract.

It acts as:
- step history
- execution evidence
- runtime observability
- debugging surface
- verification surface

A successful task is not only "something happened" — it is something that can be checked.

---

## Result-Oriented Output

ZERO produces structured outputs such as `result.json`.

This is important because future systems need more than console text:
- downstream tasks may need machine-readable results
- users may need stable output structures
- retries and replans may depend on previous results

Result files push ZERO closer to a proper workflow engine.

---

## Why ZERO Is Not Just a Demo Agent

A demo agent often has:
- a loop
- a prompt
- a tool call
- an answer

ZERO already has:
- planner
- runtime state
- scheduler logic
- task workspace
- shared workspace
- step executor
- step handlers
- execution logs
- results
- task status flow

This moves it into the category of:
- runtime prototype
- workflow prototype
- task orchestration system

---

## Design Direction Going Forward

The next major design expansion areas are:

- queue system
- priority handling
- retry / replan loop
- dependency scheduling
- DAG-style workflow
- multi-worker execution
- dashboard / observability UI
- plugin tool ecosystem

---

## Summary

ZERO is intentionally designed as a structured, state-centric, workspace-based execution runtime.

Its core design choices are aimed at making AI task execution:
- visible
- inspectable
- reproducible
- safer
- extensible
- suitable for future orchestration
