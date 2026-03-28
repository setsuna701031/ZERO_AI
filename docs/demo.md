# ZERO Demo Guide

This document describes the current demo flows for ZERO.

The purpose of these demos is to show that ZERO is not just a chatbot or script runner,
but a task-oriented runtime that is moving toward a Task Operating System.

Current visible strengths include:

- queue-based task flow
- scheduler-driven execution
- task runtime state control
- retry / failure convergence
- workspace-driven execution behavior

---

## Demo 1 — Task OS Runtime Skeleton

This demo shows that ZERO now behaves more like a task runtime than a simple command wrapper.

### What to Highlight

- task queue exists
- priority queue exists
- scheduler exists
- runtime exists
- workspace state exists
- pause / resume / finish behavior exists

### Concept Flow

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

### What This Demonstrates

- runtime architecture exists
- scheduling layer exists
- execution is no longer just direct one-shot tool invocation
- ZERO is moving toward a workflow-engine / Task OS model

---

## Demo 2 — Retry / Failure Closure

This demo shows the retry/failure path that is now working.

### Goal

Show that a failed task no longer silently breaks or incorrectly reports success.

### Expected Flow

```text
queued → running → retrying → queued → running → retrying → queued → running → failed
```

### What to Verify

- `retry_count` increments correctly
- `max_retries` is enforced
- `last_error` is preserved
- final status becomes `failed`
- task does not incorrectly end as `finished`

### What This Demonstrates

- runtime failure detection
- scheduler retry accounting
- correct terminal failure convergence
- Task OS failure-path closure

---

## Demo 3 — Successful Completion Path

This demo verifies the clean success path.

### Goal

Show that a normal runnable task ends in a clean final success state.

### Example Concept

Use a known-success workspace operation or a simple existing file target.

### Expected Flow

```text
queued → running → finished
```

### What to Verify

- task starts normally
- runtime executes without false retry
- task ends in `finished`
- final result is stable and inspectable

### What This Demonstrates

- success-path closure
- runtime correctness in normal execution
- balance between failure handling and normal completion

---

## Demo 4 — Task History / Event Visibility

This demo is about observability.

### Goal

Show not only the final state, but the full state/event path of a task.

### Example Desired Visibility

```text
queued → running → retrying → queued → running → failed
```

or

```text
queued → running → finished
```

### What This Demonstrates

- inspectable runtime history
- easier debugging
- better confidence in scheduler/runtime behavior
- transition from "black box execution" toward visible workflow execution

---

## Recommended Demo Order

If you want to present ZERO to others, use this order:

1. Task OS Runtime Skeleton
2. Retry / Failure Closure
3. Successful Completion Path
4. Task History / Event Visibility

This sequence shows the progression from:

**runtime skeleton → failure closure → success closure → observability**

---

## Current Limitations

ZERO is still an early-stage engineering prototype.

Current limitations include:

- task history visibility is still being improved
- success-path validation still needs cleaner demonstration
- reflection / replanning path still needs more structured demo proof
- memory-aware planning is not complete
- long-term memory is not complete
- advanced multi-agent behavior is not complete
- web interface is not the current priority
- one-click deployment is not the current priority

---

## Summary

ZERO is currently positioned as:

**an early local-first Task Operating System prototype with queueing, scheduling, runtime control, and retry/failure closure**

This repository currently prioritizes the execution core first,
with broader product and UI layers coming later.
