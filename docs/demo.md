# ZERO Demo

## Core Demo: Git Pipeline Replay

https://github.com/setsuna701031/ZERO_AI/blob/main/demos/00_git_pipeline_replay_demo.mp4

ZERO analyzes real git changes, generates PR artifacts into a controlled outbox, and provides a read-only replay of the execution trace.

- No repository mutation
- Full traceability
- Replayable execution

---

## Demo Videos

### 1. Git Pipeline Replay (Core Demo)

This demo shows ZERO analyzing real git changes, generating PR artifacts into a controlled outbox, and replaying the execution trace without modifying the repository.

- No repository mutation
- Full traceability
- Replayable execution

### 2. Task OS Runtime

Demonstrates ZERO task scheduling, execution flow, and lifecycle management.

### 3. Trace Viewer (Local)

Demonstrates local trace inspection and debugging capability.

---

## Overview

This document defines the current main demo paths for ZERO.

The goal is not to show isolated toy outputs, but to show that ZERO can run a real local agent workflow with stable execution, file outputs, task orchestration, repeatable validation, and a presentable local UI layer.

At the current stage, the strongest demo chain is:

1. Git Pipeline Replay Demo
2. Task OS Runtime Demo
3. Trace Viewer Demo
4. Requirement Demo
5. Mini Build Demo
6. Document Flow Demo
7. Web UI Persona Bridge Demo
8. Runtime / mainline smoke validation

These parts together show that ZERO is not just a chat wrapper. It can plan, execute, write artifacts, preserve task state, expose runtime status, and present system state through a local Web UI.

---

## Demo 1: Git Pipeline Replay Demo

### Goal

Show that ZERO can analyze real Git changes, generate review artifacts, write them into a controlled outbox, and replay the execution trace without mutating the repository.

### Video

```text
demos/00_git_pipeline_replay_demo.mp4
```

### What This Demo Proves

- ZERO can read real Git state.
- ZERO can generate commit and PR artifacts.
- Generated artifacts are written only to `workspace/github_outbox`.
- The replay path is read-only.
- No `git commit`, `git push`, or PR creation occurs.
- The execution is traceable and replayable.

### Expected Outputs

```text
workspace/github_outbox/commit_message.txt
workspace/github_outbox/pr_description.md
```

### Safety Boundary

```text
read_only input -> generate_only artifact -> workspace_write outbox -> read_only replay
```

Forbidden actions:

```text
git commit
git push
create PR
external_write
```

---

## Demo 2: Task OS Runtime Demo

### Goal

Show task scheduling, task lifecycle, execution flow, and runtime state visibility.

### Video

```text
demos/01_zero_task_os_runtime_demo.mp4
```

### What This Demo Proves

- ZERO has a task-oriented runtime.
- Tasks can be created, queued, executed, and inspected.
- Runtime state is visible through task records and outputs.

---

## Demo 3: Trace Viewer Demo

### Goal

Show local trace inspection and debugging capability.

### Video

```text
demos/02_trace_viewer_local.mp4
```

### What This Demo Proves

- ZERO preserves execution traces.
- Trace output can be inspected after execution.
- The system can explain what happened after a run.

---

## Demo 4: Requirement Demo

### Goal

Show that ZERO can take a real requirement file and turn it into multiple useful deliverables through the task pipeline.

This is a planning-oriented showcase because it demonstrates:

- task creation
- planner output entering task mode
- execution through the main path
- artifact generation
- stable end-to-end completion

### Input

```text
workspace/shared/requirement.txt
```

### Command

```powershell
python main.py requirement-demo
```

### Expected Outputs

```text
workspace/shared/project_summary.txt
workspace/shared/implementation_plan.txt
workspace/shared/acceptance_checklist.txt
```

### What This Demo Proves

- ZERO can read a requirement file.
- ZERO can create a task from it.
- ZERO can execute through the mainline path.
- ZERO can generate multiple downstream deliverables.
- ZERO can preserve task state and task artifacts.
- ZERO can complete without breaking runtime smoke / mainline validation.

---

## Demo 5: Mini Build Demo

### Goal

Show that ZERO can go beyond planning-only outputs and complete a compact engineering flow:

```text
requirement -> planning -> implementation -> execution -> verification
```

### Inputs

```text
workspace/shared/requirement.txt
workspace/shared/numbers_input.txt
```

### Command

```powershell
python main.py mini-build-demo
```

### Expected Outputs

```text
workspace/shared/project_summary.txt
workspace/shared/implementation_plan.txt
workspace/shared/acceptance_checklist.txt
workspace/shared/number_stats.py
workspace/shared/stats_result.txt
```

### What This Demo Proves

- ZERO can read a fixed requirement input.
- ZERO can generate planning outputs.
- ZERO can generate a runnable Python artifact.
- ZERO can execute that artifact locally.
- ZERO can write a result file.
- ZERO can verify concrete output values.

---

## Demo 6: Document Flow Demo

### Goal

Show a practical local document-processing workflow inside ZERO.

Instead of only replying in chat, ZERO reads a real input file, processes it with a local LLM pipeline, writes a useful output file, and preserves a trace file that can be inspected later.

### Capability A: Action Items Extraction

Input:

```text
workspace/shared/input.txt
```

Output:

```text
workspace/shared/action_items.txt
```

Flow:

```text
read_input -> extract_action_items -> write_action_items
```

### Capability B: Document Summary

Input:

```text
workspace/shared/input.txt
```

Output:

```text
workspace/shared/summary.txt
```

Flow:

```text
read_input -> summarize_document -> write_summary
```

### Trace Support

```text
workspace/shared/document_flow_trace.json
```

---

## Demo 7: Web UI Persona Bridge Demo

### Goal

Show that ZERO has a local Web UI display path connected to real runtime workspace state.

This demo is not meant to prove full agent execution by itself. Its purpose is to show that the UI layer can read and display the current ZERO workspace state through a local bridge.

Current bridge path:

```text
ui/index.html
-> /api/chat
-> ui/server.py
-> core/display/ui_bridge.py
-> workspace/shared + workspace/tasks
```

### Command

```powershell
python .\ui\server.py
```

Then open:

```text
http://127.0.0.1:7860
```

### Test Inputs

```text
status
summary
tasks
files
```

### What This Demo Proves

- ZERO can start a local Web UI server.
- ZERO can serve the main `index.html` UI.
- ZERO can expose `/api/chat`.
- ZERO can read runtime state through `core/display/ui_bridge.py`.
- ZERO can display current status from `workspace/tasks`.
- ZERO can display recent files from `workspace/shared`.

### Current Scope

```text
Web UI -> status display bridge
```

Not yet:

```text
Web UI -> full agent execution controller
```

---

## Safe Engineering Output Path

ZERO has a guarded engineering-output path for producing review artifacts without performing Git or GitHub mutations.

### Tool Capability Model

```text
read_only
generate_only
workspace_write
external_write disabled
```

### Core Rules

Generated artifacts are not actions.

Only approved executor steps can create side effects.

### Current Safe Pipeline

```text
real git_diff/status
-> analyze
-> commit_message_generator
-> pr_description_generator
-> github_outbox.write
-> trace
-> replay
```

### Allowed Outbox Files

```text
workspace/github_outbox/commit_message.txt
workspace/github_outbox/pr_description.md
workspace/github_outbox/devlog.md
workspace/github_outbox/review_report.md
```

### Forbidden

```text
git commit
git push
create PR
external_write
```

### Validation

Current smoke coverage:

```text
run_readonly_tools_smoke.py
run_commit_message_generator_smoke.py
run_pr_description_generator_smoke.py
run_github_outbox_smoke.py
run_github_outbox_pipeline_smoke.py
run_git_pipeline_planner_smoke.py
run_trace_replay_smoke.py
run_tool_policy_smoke.py
```

---

## Runtime Validation

The demo path is not considered complete unless runtime validation also passes.

Current validation focus:

```text
test_step_executor.py
test_executor_repair_rules.py
test_executor_safe_path_repair.py
run_agent_loop_smoke.py
run_scheduler_smoke.py
```

Mainline validation target:

```text
runtime smoke PASS
mainline smoke PASS
```

---

## Demo Assets To Keep

Important assets worth preserving:

- successful Git Pipeline Replay video
- successful trace replay terminal screenshot
- generated `commit_message.txt`
- generated `pr_description.md`
- successful requirement demo terminal screenshots
- generated requirement demo output files
- successful mini-build demo terminal screenshots
- generated `number_stats.py`
- generated `stats_result.txt`
- successful document flow terminal screenshots
- generated `action_items.txt`
- generated `summary.txt`
- `document_flow_trace.json`
- runtime smoke PASS screenshot
- mainline ALL PASS screenshot
- task summary / artifact proof screenshots
- Web UI persona bridge screenshots
- Web UI `status` success screenshot
- Web UI `tasks` success screenshot

Recommended storage direction:

```text
demos/
docs/images/checkpoints/
docs/demo_assets/persona_runtime/
```

---

## Why These Demos Matter

These demos show that ZERO can do more than answer text prompts.

They demonstrate that ZERO can:

- read real files
- create tasks
- plan execution
- write deliverables back to disk
- preserve execution traces
- replay execution evidence
- expose runtime status
- display workspace state through a local Web UI
- survive repeated smoke validation
- maintain a stable local-first workflow

ZERO is not a chat wrapper. It is a controlled, traceable, local-first agent system.

---

## Current Demo Status

- Git Pipeline Replay demo: available
- Task OS Runtime demo: available
- Trace Viewer demo: available
- Requirement demo: available
- Mini-build demo: available
- Document flow demo: available
- Web UI persona bridge demo: available
- Runtime smoke: validated
- Mainline smoke: validated

---

## Recommended Next Directions

After this stage, reasonable next steps are:

- keep the Git Pipeline Replay demo as the first public-facing demo
- improve the Web UI status page without over-expanding control authority
- keep Web UI as a display bridge before making it a full remote-control layer
- export deliverables in more structured formats
- connect generated outputs into downstream task workflows
- refine public-facing README and showcase wording

For the current stage, the priority is clear:

```text
keep the mainline stable
keep the demos repeatable
keep the evidence
```
