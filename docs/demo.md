# ZERO_AI Demo

A simplified execution story of ZERO_AI.

---

## System Execution Flow

        ┌──────────────┐
        │  User Task   │
        └──────┬───────┘
               ↓
        ┌──────────────┐
        │   Planner    │
        │ (task split) │
        └──────┬───────┘
               ↓
        ┌──────────────┐
        │   Executor   │
        └──────┬───────┘
               ↓
        ┌──────────────┐
        │   Result     │
        └──────┬───────┘
               ↓
        ┌──────────────┐
        │   Failure?   │
        └──────┬───────┘
         Yes ↓       ↓ No
     ┌──────────┐     Done
     │  Repair  │
     └────┬─────┘
          ↓
       Retry
          ↓
       Executor

---

## Step-by-Step Execution Story

### Step 1 — Task Input
User provides a task.

The system receives and prepares execution.

---

### Step 2 — Planning
The task is broken into smaller steps.

Dependencies between steps are defined.

---

### Step 3 — Execution
The system starts executing tasks step-by-step.

Each step is monitored and logged.

---

### Step 4 — Failure Detection
If a step fails:
- the system detects the error
- stops the current flow

---

### Step 5 — Self-healing
The system attempts to fix the problem:
- adjust parameters
- retry execution
- apply repair logic

---

### Step 6 — Continue Execution
After fixing:
- execution resumes
- remaining steps continue

---

### Step 7 — Completion
All tasks are completed successfully.

---

## Example Runs

### Agent Loop Trace
![agent_loop](docs/images/demo/agent_loop_trace_overview.png)

---

### Safe Path Repair
![repair](docs/images/demo/executor_safe_path_repair.png)

---

### Multi-task Self-healing
![self_healing](docs/images/demo/multi_task_self_healing_all_success.png)

---

## Summary

ZERO_AI is not just generating text.

It is designed to:
- execute tasks
- handle failures
- and complete workflows autonomously
