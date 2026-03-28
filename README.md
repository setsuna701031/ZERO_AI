# ZERO AI

ZERO is a local-first autonomous task runtime that is evolving toward a **Task Operating System**.

It is not designed as a chatbot-first system.
It is designed as an execution-first system that can manage tasks, runtime flow, retry logic, failure convergence, and future recovery mechanisms.

---

## Current Position

ZERO is currently in an **early Task OS prototype** stage.

The project already includes meaningful progress in:

- task queue
- priority queue
- preemptive scheduling
- task runtime
- step execution
- workspace state tracking
- pause / resume behavior
- retry / failure closure
- CLI-driven execution flow
- logging and runtime state transitions

At the current stage, ZERO is closer to a:

- job scheduler
- workflow engine
- task execution kernel

than to a simple assistant wrapper.

---

## What Is Working Now

### Runtime / Task OS Foundations
- queue-based task flow
- scheduler-driven execution
- runtime state control
- workspace-linked task behavior
- execution path structured around task state

### Retry / Failure Closure
The current prototype already proves a working failure path:

```text
queued → running → retrying → queued → running → retrying → queued → running → failed
```

This means:

- runtime can detect failure
- scheduler can increment retry count
- retry limit is enforced
- `last_error` can be preserved
- tasks converge to real `failed` state
- tasks do not incorrectly appear as `finished`

### Task OS Direction
The current architecture is no longer only:

```text
user → prompt → tool → reply
```

It is moving toward:

```text
CLI
↓
Queue API
↓
Priority Queue
↓
Preemptive Scheduler
↓
Task Runtime
↓
Workspace State
↓
Pause / Resume / Finish
```

---

## Project Philosophy

ZERO follows a task-oriented design philosophy:

- tasks instead of conversations
- steps instead of responses
- execution instead of chatting
- scheduling instead of naive sequential dispatch
- recovery instead of stopping
- memory instead of forgetting
- lessons instead of raw logs

The core idea is simple:

**The user gives a goal.  
The runtime manages execution.**

---

## Current Priorities

Current engineering priorities are:

1. improve runtime observability
2. expose task history / event visibility
3. verify clean success-path closure
4. continue stabilizing scheduler/runtime/task-state behavior
5. preserve clean architecture while expanding capability

---

## Current Limitations

ZERO is still an early-stage engineering prototype.

Not yet complete or still being stabilized:

- task history visibility
- success-path validation
- reflection / replanning structured verification
- memory-aware planning
- long-term memory
- tool auto-selection
- web interface
- one-click deployment

---

## Docs

See the `docs/` folder for more detailed project documents:

- `project_overview.md`
- `current_status.md`
- `architecture.md`
- `design.md`
- `roadmap.md`
- `demo.md`

---

## Long-Term Vision

ZERO is being built toward a personal autonomous engineering assistant.

Example future directions:

- build engineering task flows
- recover from failed execution
- continue interrupted work
- use tools under runtime control
- learn from execution history
- improve through memory and lessons

The long-term goal is not just to answer.
The goal is to **execute, recover, and evolve**.

---

## Status

Current status:

**early local-first Task Operating System prototype**
