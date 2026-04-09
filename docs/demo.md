# ZERO Demo

This document showcases the core capabilities of ZERO.

Instead of assuming correctness, ZERO continuously validates and adjusts its behavior.

---

## Core Loop

Plan → Execute → Verify → Correct → Retry / Replan → Re-execute

This is the foundation of ZERO.

---

## What ZERO Can Do

In practice, ZERO can:

- run structured multi-step tasks
- detect failures through verification
- retry transient failures
- replan when retry is not enough
- repair invalid plans before execution

---

# Demo Overview

---

## 1. Agent Loop Overview

![Agent Loop](images/demo/agent_loop_trace_overview.png)

---

## 2. Executor Forced Repair (Basic)

![Forced Repair](images/demo/executor_forced_repair_terminal.png)

---

## 3. Executor Auto Dependency Repair (Advanced)

![Auto Dependency Repair](images/demo/executor_auto_dependency_repair.png)

---

## Summary

ZERO is a runtime-controlled agent system.
