# ZERO Project Overview

## What ZERO Is

ZERO is a local-first AI execution system focused on turning user intent into structured, verifiable task execution.

At its current stage, ZERO is no longer just a chatbot shell or a simple tool-calling demo. It has already evolved into a **mini Task OS / Agent Runtime prototype** with a planner, runtime state, workspace model, step executor, and task lifecycle management.

In practical terms, ZERO is designed to move from:

- can talk  
to
- can do

And more importantly:

- can plan
- can execute
- can record
- can verify
- can recover
- can be extended

---

## Core Positioning

ZERO is best described as:

- **Local-first Agent Runtime**
- **Task Orchestrator**
- **Mini Task Operating System**
- **Execution-focused AI infrastructure prototype**

It is not primarily positioned as a general consumer chatbot.

Instead, it is being built as a foundational execution system for:

- AI task automation
- engineering workflows
- file and command execution pipelines
- local autonomous agents
- reproducible step-based task execution
- future workflow / orchestration systems

---

## Why ZERO Exists

A large portion of current AI agent projects fall into two extremes:

### 1. Heavy workflow frameworks
Examples include systems similar in spirit to LangGraph, Temporal, or large orchestration stacks.

These systems are powerful, but often come with substantial boilerplate and infrastructure overhead. They are usually designed for larger engineering teams and server-side workflow systems.

### 2. Lightweight demo agents
Examples include many GitHub agent demos or LLM wrappers that can call tools.

These systems are lightweight, but usually lack:

- true runtime state
- task workspace isolation
- execution logs
- scheduler concepts
- structured task lifecycle
- recoverable task state

---

## What ZERO Tries to Fill

ZERO attempts to occupy the middle layer between those two extremes.

It introduces a local-first execution system with:

- deterministic planning
- JSON-driven runtime state
- per-task workspaces
- shared workspace support
- execution logging
- structured result output
- task lifecycle transitions
- scheduler-oriented architecture
- future retry / replan / dependency expansion

This makes ZERO closer to a **task execution runtime** than a typical AI demo project.

---

## Key Design Direction

ZERO is being built around several principles:

### 1. Local-first
The system is designed to run locally and preserve user control.

### 2. State-centric
Important state is written to structured files such as:

- `plan.json`
- `runtime_state.json`
- `execution_log.json`
- `result.json`
- `tasks.json`

This makes task behavior inspectable and debuggable.

### 3. Workspace-based execution
Each task has its own isolated workspace, and shared artifacts can be stored in a shared workspace.

### 4. Planner-first execution
Instead of jumping directly from prompt to tool call, ZERO first generates structured task steps and then executes them.

### 5. Verifiable runtime behavior
ZERO is designed so that execution can be checked through files, logs, state transitions, and outputs.

---

## Current Stage

At the current milestone, ZERO already includes the core shape of a runtime system:

- Task creation
- Planner
- Runtime state machine
- Scheduler tick model
- Step executor
- Step handlers
- Task workspace
- Shared workspace
- Execution log
- Result output
- Status flow
- Basic dependency fields

This means ZERO is already beyond the "chatbot demo" stage and has entered the **runtime / orchestrator prototype** stage.

---

## What ZERO Can Become

As more infrastructure is added, ZERO can grow toward:

- workflow engine
- AI task runtime
- local automation platform
- engineering execution assistant
- plugin-based execution framework
- multi-worker orchestration system
- future task OS / agent platform

---

## Current Focus

The current development focus is not on UI polish or consumer-facing chat features.

The current focus is on building the execution core:

- planner reliability
- workspace rules
- runtime state correctness
- task lifecycle clarity
- step execution consistency
- scheduler / queue / retry expansion

---

## Summary

ZERO is a local-first task execution runtime designed to convert natural language goals into structured steps, execute them inside isolated workspaces, record state and logs, and evolve toward a full task orchestration system.

It is not just an AI assistant project.

It is an execution system.
