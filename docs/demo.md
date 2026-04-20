# ZERO Demo Guide

## Overview

This document defines the current main demo paths for ZERO.

The goal is not to show isolated toy outputs, but to show that ZERO can run a real local agent workflow with stable execution, file outputs, task orchestration, and repeatable validation.

At the current stage, the strongest demo chain is:

1. Requirement Demo
2. Document Flow Demo
3. Runtime / mainline smoke validation

These three parts together show that ZERO is not just a chat wrapper. It can plan, execute, write artifacts, and preserve a stable runnable path.

---

## Demo 1: Requirement Demo

### Goal

Show that ZERO can take a real requirement file and turn it into multiple useful deliverables through the task pipeline.

This is currently the strongest mainline showcase because it demonstrates:

- task creation
- planner output entering task mode
- execution through the main path
- artifact generation
- stable end-to-end completion

### Input

- `workspace/shared/requirement.txt`

This file should contain a simple but realistic project requirement in English.

Example idea:

- a small product concept
- a lightweight internal tool
- a simple engineering request
- a feature requirement with scope and expected outcome

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

This is currently more valuable than a simple single-file rewrite demo because it shows multi-deliverable generation through the actual system path.

For external viewers, this is much closer to a real engineering assistant workflow:

requirement in → structured project outputs out

---

## Demo 2: Document Flow Demo

### Goal

Show a practical local document-processing workflow inside ZERO.

Instead of only replying in chat, ZERO reads a real input file, processes it with a local LLM pipeline, writes a useful output file, and preserves a trace file that can be inspected later.

This makes the demo closer to a real local agent workflow than a simple text-generation example.

---

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

Example result characteristics:

- identify named owners
- assign `Unassigned` when no explicit owner exists
- preserve due phrases such as:
  - `By Monday`
  - `Today`
  - `This afternoon`
  - `Tomorrow`

---

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

Example result characteristics:

- executive summary
- key takeaways
- concise structured output suitable for demos and technical review

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
- successful document flow terminal screenshots
- generated `action_items.txt`
- generated `summary.txt`
- `document_flow_trace.json`
- runtime smoke PASS screenshot
- mainline ALL PASS screenshot
- task summary / artifact proof screenshots

Recommended storage direction:

- `demo_assets/requirement_demo/`
- `demo_assets/document_flow_demo/`
- `docs/images/`

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
- Document flow demo: available
- Runtime smoke: validated
- Mainline smoke: validated

Current recommendation:

Do not expand the demo surface too aggressively yet.

First keep the current demo chain stable, repeatable, and easy to present.

---

## Recommended Next Directions

After this stage, reasonable next steps are:

- unify requirement demo and document demo under one clean demo entry structure
- add a cleaner UI or remote-control layer later
- export deliverables in more structured formats
- connect generated outputs into downstream task workflows
- refine public-facing README and showcase wording

For the current stage, the priority is clear:

keep the mainline stable, keep the demos repeatable, and keep the evidence.
