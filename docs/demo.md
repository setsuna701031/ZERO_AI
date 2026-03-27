# ZERO Demo Guide

This document describes the current demo flows for ZERO.

The purpose of these demos is to show that ZERO is not just a chatbot or script runner,
but a task-oriented agent runtime with retry, reflection, replanning, and memory summaries.

---

## Demo 1 — Basic Task Execution

This demo shows the normal task-tree execution flow.

### Commands

```bash
task new build a simple homepage
task run
task tree
memory task
```

### Expected Flow

1. A root task is created
2. The planner generates subtasks
3. The agent executes runnable leaf tasks in sequence
4. Runtime events are recorded
5. A task summary is written into memory

### What This Demonstrates

- task creation
- task-tree execution
- runtime event tracking
- task memory summary

---

## Demo 2 — Retry Recovery

This demo shows retry behavior after a step fails once.

### Commands

```bash
task new fail_first retry test
task run
runtime events
task tree
memory task
```

### Expected Flow

1. A step fails on the first attempt
2. The retry mechanism is triggered
3. The step succeeds on retry
4. The task continues normally
5. Memory records the retry history

### What This Demonstrates

- step failure detection
- automatic retry
- retry event logging
- memory summary including retry history

---

## Demo 3 — Reflection + Replan Recovery

This demo shows the full recovery loop:

**retry → reflection → replan → recovery → continue**

### Commands

```bash
task new always_fail reflection test
task run
runtime events
task tree
memory task
```

### Expected Flow

1. A task fails repeatedly
2. Retry attempts are exhausted
3. Reflection is triggered
4. Reflection generates recovery subtasks
5. New subtasks are inserted into the task tree
6. The recovery subtasks are executed
7. The root task completes successfully
8. Memory records retry, reflection, replanning, and lessons learned

### What This Demonstrates

- retry exhaustion
- reflection engine activation
- dynamic replanning
- task-tree modification during execution
- recovery execution
- lesson recording into memory

---

## What These Demos Prove

The current ZERO prototype already demonstrates:

- task-tree execution
- runtime event logging
- retry handling
- reflection after repeated failures
- dynamic replanning
- recovery-step insertion
- memory summaries with lessons learned

This means ZERO already behaves like an **early autonomous task-execution kernel**,
not just a chat wrapper.

---

## Recommended Demo Order

If you want to present ZERO to others, use this order:

1. Basic Task Execution
2. Retry Recovery
3. Reflection + Replan Recovery

This sequence shows the progression from:

**task runner → resilient executor → self-recovering agent kernel**

---

## Current Limitations

ZERO is still an early-stage engineering prototype.

Current focus areas include:

- local-first agent execution
- task runtime behavior
- reflection and replanning loop
- memory-aware summaries
- agent loop architecture

Not implemented or not yet complete:

- memory-aware planning
- long-term memory system
- tool auto-selection
- advanced multi-step planning
- multi-agent workers
- web interface
- one-click deployment

---

## Summary

ZERO is currently positioned as:

**a local-first task execution kernel with retry, reflection, replanning, and memory-based task summaries.**

This repository prioritizes the execution core first,
with UI, deployment, and broader product layers coming later.
