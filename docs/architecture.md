# System Architecture

The system is composed of five main layers:

1. Task Repository
2. DAG Scheduler
3. Scheduler Queue
4. Runtime State Machine
5. Task Runner

---

# Architecture Flow

Task Submit
↓
Task Repository
↓
DAG Scheduler
↓
Scheduler Queue
↓
Task Runner
↓
Runtime State Machine
↓
Task Finished / Failed / Retry / Replan

---

# Components

## Task Repository

Stores:

* task_id
* status
* depends_on
* history
* workspace_dir
* task_dir

## DAG Scheduler

Determines if a task is ready:

* All dependencies finished → queued
* Otherwise → blocked

## Scheduler Queue

Runnable task queue.

## Runtime State Machine

Tracks execution state and transitions:

* queued → running → finished
* running → retry
* running → failed
* running → replan

## Task Runner

Executes steps and updates runtime state.
