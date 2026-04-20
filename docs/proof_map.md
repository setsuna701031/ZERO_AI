# ZERO Proof / Checkpoint Map

## Purpose

This file maps the current public-facing proof assets for ZERO.

It is meant to answer four practical questions:

1. Which video belongs to which demo?
2. Which checkpoint image supports which README section?
3. Which assets are suitable for public use?
4. Which assets should stay internal-only for now?

This is not a deep engineering log.  
It is a presentation / proof indexing document.

---

## Public Demo Video Map

### 1. Requirement Demo — Execution Proof

File:
- `demos/07_requirement_demo/requirement_demo_execution_pass_2026-04-20.mp4`

What it shows:
- fixed requirement input exists
- `python main.py requirement-demo` is executed
- requirement demo runs through the mainline path
- terminal ends with PASS
- output artifact paths are shown

Use:
- public demo
- README support
- investor / operator proof
- GitHub demo reference

Public status:
- safe to show publicly

---

### 2. Requirement Demo — Outputs Showcase

File:
- `demos/07_requirement_demo/requirement_demo_outputs_2026-04-20.mp4`

What it shows:
- generated requirement outputs are opened directly
- `project_summary.txt`
- `implementation_plan.txt`
- `acceptance_checklist.txt`

Use:
- public demo
- README support
- capability explanation
- product/showcase material

Public status:
- safe to show publicly

---

## Public Checkpoint Image Map

### A. Mainline Stability

File:
- `docs/images/checkpoints/checkpoint_mainline_smoke_all_pass.png`

README role:
- mainline stability proof
- validation checkpoint support

Use:
- public README
- public proof
- technical checkpoint support

Public status:
- safe to show publicly

---

### B. Runtime Stability

File:
- `docs/images/checkpoints/checkpoint_runtime_smoke_pass.png`

README role:
- runtime validation proof
- stability checkpoint support

Use:
- public README
- public proof
- technical checkpoint support

Public status:
- safe to show publicly

---

### C. Requirement Demo Pass

File:
- `docs/images/checkpoints/checkpoint_requirement_demo_pass.png`

README role:
- requirement demo representative checkpoint
- unified entrypoint proof

Use:
- public README
- public proof
- showcase support

Public status:
- safe to show publicly

---

### D. Requirement Demo Outputs

File:
- `docs/images/checkpoints/checkpoint_requirement_demo_outputs.png`

README role:
- requirement demo output proof
- multi-deliverable evidence

Use:
- public README
- public proof
- showcase support

Public status:
- safe to show publicly

---

### E. Execution Demo Pass

File:
- `docs/images/checkpoints/checkpoint_execution_demo_pass.png`

README role:
- execution-proof scenario checkpoint
- artifact generation proof

Use:
- public README
- public proof
- showcase support

Public status:
- safe to show publicly

---

### F. Task OS Integration Tests Passed

File:
- `docs/images/checkpoints/checkpoint_task_os_integration_tests_passed.png`

README role:
- broader system confidence checkpoint
- supporting engineering proof

Use:
- public technical support proof
- internal review
- optional public README support

Public status:
- generally safe to show publicly

---

## Secondary Support Images

These are useful, but they are not the primary public checkpoint set.

### Secondary images

- `docs/images/checkpoints/checkpoint_requirement_pack_task_show.png`
- `docs/images/checkpoints/checkpoint_task_result_action_items_finished.png`
- `docs/images/checkpoints/checkpoint_task_result_action_items_mainline.png`
- `docs/images/checkpoints/checkpoint_task_result_and_show_summary_mainline.png`

Use:
- deeper technical walkthroughs
- internal explanation
- devlog support
- appendix material
- follow-up proof when someone asks for more detail

Public status:
- mostly safe, but better used selectively instead of as front-page proof

---

## Internal-Only / Lower-Priority Proof

These are useful engineering records, but they should not be prioritized for public-facing README use.

Examples:
- DAG intermediate-state screenshots
- temporary rename / migration screenshots
- queue-unblock snapshots
- one-off repair screenshots
- duplicate pass screenshots with weaker naming or older context

Reason:
- too implementation-specific
- lower presentation value
- can distract from the stronger story
- better kept for internal debugging history

Public status:
- keep internal unless needed

---

## README Mapping

Current README proof structure should mainly point to these:

### Primary README checkpoint set

- `checkpoint_mainline_smoke_all_pass.png`
- `checkpoint_runtime_smoke_pass.png`
- `checkpoint_requirement_demo_pass.png`
- `checkpoint_requirement_demo_outputs.png`
- `checkpoint_execution_demo_pass.png`
- `checkpoint_task_os_integration_tests_passed.png`

### README support role by section

**Validation / stability sections**
- `checkpoint_mainline_smoke_all_pass.png`
- `checkpoint_runtime_smoke_pass.png`

**Requirement demo sections**
- `checkpoint_requirement_demo_pass.png`
- `checkpoint_requirement_demo_outputs.png`

**Execution demo sections**
- `checkpoint_execution_demo_pass.png`

**Whole-system support / confidence**
- `checkpoint_task_os_integration_tests_passed.png`

---

## Public vs Internal Summary

### Public-safe assets

Videos:
- `requirement_demo_execution_pass_2026-04-20.mp4`
- `requirement_demo_outputs_2026-04-20.mp4`

Images:
- `checkpoint_mainline_smoke_all_pass.png`
- `checkpoint_runtime_smoke_pass.png`
- `checkpoint_requirement_demo_pass.png`
- `checkpoint_requirement_demo_outputs.png`
- `checkpoint_execution_demo_pass.png`
- `checkpoint_task_os_integration_tests_passed.png`

### Better kept as internal/supporting material

- requirement pack task-show detail image
- action-items result/show detail images
- summary task result/show detail images
- DAG intermediate workflow screenshots
- migration / rename / unblock proof screenshots
- duplicate or older smoke proof screenshots

---

## Current Recommendation

For public-facing use right now:

1. Lead with requirement demo proof
2. Support with mainline + runtime stability proof
3. Show execution demo as a second representative scenario
4. Keep the more detailed task-result screenshots as secondary appendix material

This keeps the external story clean:

- the system is stable
- the system can run
- the system can generate artifacts
- the system can show proof
- the system is not only a chat wrapper

---

## Current Status

This proof map matches the current repository state after:

- mainline stabilization
- execution-path stabilization
- requirement demo showcase setup
- README alignment
- checkpoint naming cleanup
- devlog update

It should be updated again when:

- new public demo videos are added
- new checkpoint images replace current ones
- some assets move from internal-only to public-safe
- the public README proof structure changes
