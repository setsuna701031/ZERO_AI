# ZERO Proof / Checkpoint Map

## Purpose

This file maps the current public-facing proof assets for ZERO.

It answers:

1. Which video belongs to which demo?
2. Which checkpoint image supports which README section?
3. Which assets are suitable for public use?
4. Which assets should stay internal?

---

## 🔥 Core Showcase Positioning (Updated)

Current public-facing hierarchy:

1. **Mini Build Demo (Primary Showcase)**
2. Requirement Demo (Planning / multi-artifact showcase)
3. Document Flow Demo (practical workflow)
4. Runtime / mainline validation (stability proof)

This aligns with README positioning:

Mini Build = strongest execution proof  
Requirement Demo = strongest planning proof  

---

## 🎬 Public Demo Video Map

### 1. Mini Build Demo — Execution Proof (PRIMARY)

File:
- demos/08_mini_build_demo/mini_build_demo_execution_pass_2026-04-20.mp4

What it shows:

- requirement input
- numbers input
- python main.py mini-build-demo execution
- planning outputs
- generated number_stats.py
- script execution
- stats_result.txt output
- PASS

Use:

- README main showcase
- GitHub demo
- investor proof
- execution capability proof

Public status:
- safe

---

### 2. Requirement Demo — Execution Proof

File:
- demos/07_requirement_demo/requirement_demo_execution_pass_2026-04-20.mp4

What it shows:

- requirement input
- execution through mainline
- PASS
- artifact paths

Use:

- planning capability demo
- README secondary showcase

Public status:
- safe

---

### 3. Requirement Demo — Outputs Showcase

File:
- demos/07_requirement_demo/requirement_demo_outputs_2026-04-20.mp4

What it shows:

- generated outputs
- project_summary.txt
- implementation_plan.txt
- acceptance_checklist.txt

Use:

- visual explanation
- artifact proof

Public status:
- safe

---

## 🖼️ Public Checkpoint Image Map

### A. Mini Build Demo (PRIMARY)

- docs/images/checkpoints/checkpoint_mini_build_demo_pass.png

Role:
- main execution proof

---

### B. Requirement Demo

- checkpoint_requirement_demo_pass.png
- checkpoint_requirement_demo_outputs.png

Role:
- planning + artifact proof

---

### C. Stability

- checkpoint_mainline_smoke_all_pass.png
- checkpoint_runtime_smoke_pass.png

Role:
- system reliability proof

---

### D. Supporting

- checkpoint_execution_demo_pass.png
- checkpoint_task_os_integration_tests_passed.png

Role:
- additional confidence

---

## 📊 Public vs Internal

### Public-safe

Videos:
- mini_build_demo_execution_pass_2026-04-20.mp4
- requirement_demo_execution_pass_2026-04-20.mp4
- requirement_demo_outputs_2026-04-20.mp4

Images:
- mainline_smoke_all_pass
- runtime_smoke_pass
- requirement_demo_pass
- requirement_demo_outputs
- execution_demo_pass
- mini_build_demo_pass
- task_os_integration

---

### Internal / secondary

- detailed task screenshots
- DAG internals
- debug logs
- intermediate runs

---

## 🧭 Final External Story

When presenting ZERO:

1. Start with Mini Build Demo (execution)
2. Show Requirement Demo (planning)
3. Mention document flow (practical use)
4. Back it with smoke validation

This creates a clean narrative:

- system is stable
- system can plan
- system can execute
- system produces real artifacts
- system verifies results

---

## Current Status

Aligned with:

- README (Mini Build = primary)
- demo.md structure
- devlog checkpoints

Update this file when:

- new demo assets added
- new execution capabilities added
- positioning changes again
