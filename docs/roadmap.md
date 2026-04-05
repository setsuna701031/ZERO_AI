# ZERO Roadmap

## Overview

ZERO is being developed as a local-first AI execution system that grows from a simple execution prototype into a full task runtime / orchestration platform.

This roadmap is organized by architectural capability rather than only by feature count.

---

## Evolution Path

### v0 — Script Runner
Initial stage focused on basic local command/script execution.

Characteristics:
- direct execution
- no runtime state
- no structured planner
- no task workspace

---

### v1 — Tool Calling Agent
ZERO begins acting like a tool-enabled agent.

Characteristics:
- prompt-based interaction
- basic tool usage
- lightweight task behavior
- still limited runtime structure

---

### v2 — Planner + Multi-Step Execution
ZERO begins planning tasks into explicit steps.

Characteristics:
- step-based execution
- planner output
- multi-step flow
- early plan-driven behavior

---

### v3 — Runtime State + Workspace Core
ZERO begins forming a true runtime core.

Characteristics:
- `runtime_state.json`
- `execution_log.json`
- `result.json`
- task workspace
- step executor
- status flow

This is the stage where ZERO starts becoming a real runtime system.

---

### v4 — Shared Workspace
ZERO adds support for shared task artifacts.

Characteristics:
- `workspace/shared/`
- cross-task resource sharing
- shared path model
- stronger workspace architecture

This is the stage where ZERO moves beyond isolated tasks.

---

### v5 — Scheduler + Queue
ZERO expands scheduling behavior.

Planned capabilities:
- task queue
- runnable task selection
- better scheduler tick behavior
- queue visibility

This is the stage where ZERO becomes closer to an orchestrator.

---

### v6 — Retry / Replan
ZERO begins handling failure more intelligently.

Planned capabilities:
- retry policies
- retry count enforcement
- replan trigger points
- self-healing flow
- failure recovery logic

This is the stage where ZERO becomes more resilient.

---

### v7 — Dependency / DAG Workflow
ZERO begins supporting workflow dependency logic.

Planned capabilities:
- `depends_on` enforcement
- task dependency graph
- waiting state
- DAG-like task flow

This is the stage where ZERO begins behaving like a workflow engine.

---

### v8 — Multi-Worker Execution
ZERO expands from single execution flow toward broader runtime scaling.

Planned capabilities:
- multiple workers
- parallel task execution
- better task dispatch
- worker-aware scheduling

---

### v9 — Dashboard / Web UI
ZERO gains better observability and operational usability.

Planned capabilities:
- task list UI
- runtime state dashboard
- execution log viewer
- result viewer
- workflow visibility

This is the stage where ZERO begins looking like a platform.

---

### v10 — Plugin / Tool Ecosystem
ZERO becomes more extensible.

Planned capabilities:
- plugin tools
- tool registration system
- standardized handler expansion
- external capability extension

---

### v11 — API / SDK
ZERO becomes easier to integrate with external systems.

Planned capabilities:
- public task submission API
- task query API
- SDK layer
- external automation integration

---

### v12 — Distributed Task Runtime / Agent Platform
Long-term direction.

Possible capabilities:
- distributed workers
- richer orchestration
- stronger runtime control
- platform-level execution system
- broader AI task infrastructure role

---

## Current Position

ZERO is currently around:

**v3 → v4 → v5**

Meaning:
- runtime core exists
- workspace model exists
- shared workspace direction exists
- scheduler direction exists
- queue / retry / DAG are the next major steps

---

## Current Priority Order

The next most important architectural priorities are:

1. queue system
2. priority handling
3. retry / replan
4. dependency scheduling
5. DAG workflow behavior
6. multi-worker execution
7. dashboard / web UI
8. plugin / tool ecosystem
9. API / SDK

---

## Summary

The roadmap for ZERO is not centered on making a prettier chatbot.

It is centered on evolving ZERO from:

- local execution prototype

into:

- local task runtime
- workflow engine
- orchestrator
- AI execution platform
- future task OS / agent platform
