# ZERO AI

> A self-correcting agent runtime, not just an LLM pipeline.

---

## What is ZERO?

ZERO is an autonomous AI system designed to **execute, verify, and fix its own behavior**.

Instead of assuming success, ZERO continuously loops until the task is correct.

---

## Core Loop

Plan → Execute → Verify → Correct → Retry / Replan → Re-execute

This is not optional — it is the system.

---

## Why ZERO is Different

Most AI systems:

Plan → Execute → Done

ZERO:

- assumes plans can be wrong  
- detects failures automatically  
- repairs execution before retrying  
- converges through iteration  

---

## Key Capability

### Executor-Level Repair (Not LLM-Dependent)

ZERO does not rely only on the planner.

It has a **deterministic execution layer** that can fix problems directly.

Example:

Planner:
read hello.txt

ZERO:
create hello.txt → read hello.txt

---

## Advanced Repair: Dependency Fix

ZERO can resolve multi-step dependencies automatically:

- missing folder → auto mkdir  
- missing file → auto create  
- invalid order → auto reorder  

![Dependency Repair](docs/images/demo/executor_auto_dependency_repair.png)

---

## Agent Loop (Observed)

![Agent Loop](docs/images/demo/agent_loop_trace_overview.png)

This shows:

- execution
- verification
- correction
- iteration

---

## What ZERO Already Does

- multi-step task execution  
- verification-driven correction  
- retry & replanning  
- executor-level forced repair  
- dependency-aware execution  
- full trace visibility  

---

## What This Means

ZERO is not a script runner.

It is an **early-stage agent runtime** with:

- control over execution  
- observable behavior  
- deterministic correction  

---

## Status

Actively evolving.

Focus:
- stability  
- repair logic  
- execution correctness  

---

## License

MIT
