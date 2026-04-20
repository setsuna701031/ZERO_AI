# ZERO Demo Guide

## Overview

This document defines the current main demo paths for ZERO.

The goal is not to show isolated toy outputs, but to show that ZERO can run a real local agent workflow with stable execution, file outputs, task orchestration, and repeatable validation.

At the current stage, the strongest demo chain is:

1. Requirement Demo
2. Mini Build Demo
3. Document Flow Demo
4. Runtime / mainline smoke validation

These parts together show that ZERO is not just a chat wrapper. It can plan, execute, write artifacts, and preserve a stable runnable path.

---

## Demo 1: Requirement Demo

### Goal

Show that ZERO can take a real requirement file and turn it into multiple useful deliverables through the task pipeline.

This is the strongest planning-oriented mainline showcase because it demonstrates:

- task creation
- planner output entering task mode
- execution through the main path
- artifact generation
- stable end-to-end completion

### Input

- `workspace/shared/requirement.txt`

This file should contain a simple but realistic project requirement in English.

### Command

Run the demo from project root:

```powershell
python main.py requirement-demo
```

### Expected Outputs

The requirement demo should generate these shared artifacts:

- `workspace/shared/project_summary.txt`
- `workspace/shared/implementation_plan.txt`
- `workspace/shared/acceptance_checklist.txt`

### What This Demo Proves

This demo proves that ZERO can:

- read a requirement file
- create a task from it
- execute through the mainline path
- generate multiple downstream deliverables
- preserve task state and task artifacts
- complete without breaking runtime smoke / mainline validation

### What To Show On Screen

For a live demo or recording, show these in order:

1. the input requirement file
2. the command:
   - `python main.py requirement-demo`
3. terminal output showing task creation and submission
4. generated output files in `workspace/shared/`
5. the contents of:
   - `project_summary.txt`
   - `implementation_plan.txt`
   - `acceptance_checklist.txt`

### Success Criteria

The demo is successful when:

- the task is created successfully
- the task reaches finished state
- the three output files are generated
- the output files contain usable content
- the mainline smoke path remains stable after the run

### Why This Demo Matters

This is more valuable than a simple single-file rewrite demo because it shows multi-deliverable generation through the actual system path.

For external viewers, this is much closer to a real engineering assistant workflow:

requirement in → structured project outputs out

---

## Demo 2: Mini Build Demo

### Goal

Show that ZERO can go beyond planning-only outputs and complete a compact engineering flow:

requirement → planning → implementation → execution → verification

This is currently the strongest compact execution showcase because it demonstrates both planning artifacts and a runnable generated output.

### Inputs

- `workspace/shared/requirement.txt`
- `workspace/shared/numbers_input.txt`

The requirement file should define a small engineering build task.  
The numbers input file should contain one number per line.

### Command

Run the demo from project root:

```powershell
python main.py mini-build-demo
```

### Expected Outputs

The mini-build demo should generate these shared artifacts:

- `workspace/shared/project_summary.txt`
- `workspace/shared/implementation_plan.txt`
- `workspace/shared/acceptance_checklist.txt`
- `workspace/shared/number_stats.py`
- `workspace/shared/stats_result.txt`

### What This Demo Proves

This demo proves that ZERO can:

- read a fixed requirement input
- generate planning outputs
- generate a runnable Python artifact
- execute that artifact locally
- write a result file
- verify concrete output values

### What To Show On Screen

For a live demo or recording, show these in order:

1. `workspace/shared/requirement.txt`
2. `workspace/shared/numbers_input.txt`
3. the command:
   - `python main.py mini-build-demo`
4. terminal output showing:
   - task creation
   - task submission
   - generated script path
   - script stdout
   - PASS
5. the generated files:
   - `number_stats.py`
   - `stats_result.txt`

### Verification Focus

The strongest visible proof points are:

- `number_stats.py` exists
- `stats_result.txt` exists
- terminal stdout shows:
  - `sum`
  - `average`
  - `max`
  - `min`
- the demo ends with:
  - `[mini-build-demo] PASS`

### Success Criteria

The demo is successful when:

- the planning bundle is generated
- `number_stats.py` is created
- the script runs successfully
- `stats_result.txt` is written
- the result contains:
  - `sum`
  - `average`
  - `max`
  - `min`
- the terminal ends in PASS

### Why This Demo Matters

This pushes ZERO one step beyond requirement-to-planning delivery.

For external viewers, this is the clearest proof that ZERO can not only interpret a requirement, but also produce a runnable engineering artifact and verify its output.

---

## Demo 3: Document Flow Demo

### Goal

Show a practical local document-processing workflow inside ZERO.

Instead of only replying in chat, ZERO reads a real input file, processes it with a local LLM pipeline, writes a useful output file, and preserves a trace file that can be inspected later.

This makes the demo closer to a real local agent workflow than a simple text-generation example.

### Capability A: Action Items Extraction

Input:

- `workspace/shared/input.txt`

Output:

- `workspace/shared/action_items.txt`

Flow:

- `read_input`
- `extract_action_items`
- `write_action_items`

Purpose:

Convert meeting notes or raw project notes into clear action items with:

- Owner
- Task
- Due

### Capability B: Document Summary

Input:

- `workspace/shared/input.txt`

Output:

- `workspace/shared/summary.txt`

Flow:

- `read_input`
- `summarize_document`
- `write_summary`

Purpose:

Convert raw notes or documents into a concise English summary for review, reporting, or fast understanding.

---

## Trace Support

Document flow runs generate a structured trace file:

- `workspace/shared/document_flow_trace.json`

This allows the system to preserve the actual document-processing path instead of only showing a final file result.

### Action Items Trace

- `read_input`
- `extract_action_items`
- `write_action_items`

### Summary Trace

- `read_input`
- `summarize_document`
- `write_summary`

---

## Shared Workspace Files

Runtime demo files are typically written under:

- `workspace/shared/`

Common demo files include:

- `input.txt`
- `action_items.txt`
- `summary.txt`
- `document_flow_trace.json`
- `requirement.txt`
- `project_summary.txt`
- `implementation_plan.txt`
- `acceptance_checklist.txt`
- `numbers_input.txt`
- `number_stats.py`
- `stats_result.txt`

---

## Runtime Validation

The demo path is not considered complete unless runtime validation also passes.

Current validation focus:

- `test_step_executor.py`
- `test_executor_repair_rules.py`
- `test_executor_safe_path_repair.py`
- `run_agent_loop_smoke.py`
- `run_scheduler_smoke.py`

Mainline validation target:

- runtime smoke PASS
- mainline smoke PASS

### Why This Matters

This means the demos are not standing on a broken base.

The showcase is stronger because the system is not only producing artifacts — it is producing them on top of a validated mainline path.

---

## Demo Assets To Keep

Important assets worth preserving:

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

Recommended storage direction:

- `demos/07_requirement_demo/`
- `demos/08_mini_build_demo/`
- `docs/images/checkpoints/`

---

## Why These Demos Matter

These demos show that ZERO can do more than answer text prompts.

They demonstrate that ZERO can:

- read real files
- create tasks
- plan execution
- write deliverables back to disk
- preserve execution traces
- survive repeated smoke validation
- maintain a stable local-first workflow

That gives ZERO a more agent-like and system-like identity, instead of being only a chatbot shell.

---

## Current Demo Status

Current main demo status:

- Requirement demo: available
- Mini-build demo: available
- Document flow demo: available
- Runtime smoke: validated
- Mainline smoke: validated

Current recommendation:

Do not expand the demo surface too aggressively yet.

First keep the current demo chain stable, repeatable, and easy to present.

---

## Recommended Next Directions

After this stage, reasonable next steps are:

- unify requirement demo and mini-build demo under one cleaner demo family
- add a cleaner UI or remote-control layer later
- export deliverables in more structured formats
- connect generated outputs into downstream task workflows
- refine public-facing README and showcase wording

For the current stage, the priority is clear:

keep the mainline stable, keep the demos repeatable, and keep the evidence.
