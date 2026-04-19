# ZERO Devlog

## 2026-04 Mainline Stabilization Pass

This pass focused on stabilizing the inner execution path before pushing farther into broader capability expansion.

### Completed

* Tool layer first-pass stabilization

  * `core/tools/tool\\\_registry.py`
  * `core/tools/command\\\_tool.py`
  * `core/tools/file\\\_tool.py`
  * `core/tools/workspace\\\_tool.py`
  * `core/tasks/task\\\_paths.py`
* Step executor first-pass outer-envelope stabilization

  * `core/runtime/step\\\_executor.py`
* Step handlers first-pass normalization

  * `core/runtime/step\\\_handlers.py`
* Executor first-pass internal responsibility cleanup

  * `core/runtime/executor.py`
* Scheduler first-pass internal responsibility cleanup

  * `core/tasks/scheduler.py`

### Validation Added

Tool layer validation:

* `tests/test\\\_file\\\_tool.py`
* `tests/test\\\_workspace\\\_tool.py`
* `tests/test\\\_tool\\\_registry.py`
* `tests/run\\\_tool\\\_layer\\\_smoke.py`

Runtime / execution validation:

* `tests/test\\\_step\\\_executor.py`
* `tests/test\\\_executor\\\_repair\\\_rules.py`
* `tests/test\\\_executor\\\_safe\\\_path\\\_repair.py`
* `tests/test\\\_executor\\\_smoke.py`
* `tests/test\\\_agent\\\_loop.py`
* `tests/test\\\_scheduler\\\_smoke.py`
* `tests/run\\\_runtime\\\_smoke.py`

### Current Validation Status

Confirmed passing during this stabilization pass:

* `python tests/run\\\_tool\\\_layer\\\_smoke.py`
* `python tests/run\\\_runtime\\\_smoke.py`
* `python tests/test\\\_executor\\\_smoke.py`
* `python tests/test\\\_scheduler\\\_smoke.py`

### Why This Matters

This stage moved the project from “it worked in a few manual runs” toward a repeatable validation path for the main local execution chain.

The main value of this pass is not only capability. It is reduced fragility while changing internals.

### Current Mainline Status

Current stable checkpoint:

* Tool layer smoke: PASS
* Runtime smoke: PASS
* Executor smoke: PASS
* Scheduler smoke: PASS

### Notes

This pass prioritized:

* local-first execution
* inspectable runtime state
* stable task lifecycle behavior
* safer internal refactoring boundaries
* repeatable smoke validation

It did **not** prioritize polished UI or broad public packaging yet.



\## 2026-04 Scheduler Consolidation Pass



This pass focused on reducing scheduler responsibility mixing before pushing farther into new capability work.



\### Completed



Scheduler internal responsibility split completed across helper layers:



\- `core/tasks/scheduler\\\_core/queue\\\_sync\\\_helpers.py`

\- `core/tasks/scheduler\\\_core/dispatch\\\_helpers.py`

\- `core/tasks/scheduler\\\_core/repo\\\_state\\\_helpers.py`

\- `core/tasks/scheduler\\\_core/trace\\\_helpers.py`

\- `core/tasks/scheduler\\\_core/simple\\\_runner\\\_helpers.py`

\- `core/tasks/scheduler\\\_core/step\\\_path\\\_helpers.py`

\- `core/tasks/scheduler\\\_core/simple\\\_step\\\_executor\\\_helpers.py`

\- `core/tasks/scheduler\\\_core/command\\\_step\\\_helpers.py`

\- `core/tasks/scheduler\\\_core/llm\\\_step\\\_helpers.py`



Main scheduler remained the orchestration shell while queue sync, dispatch flow, repo/runtime sync, trace handling, simple runner flow, path handling, step execution helpers, command execution, and LLM step handling were pulled into dedicated modules.



\### Validation



This consolidation pass was validated repeatedly during each extraction step with:



\- `python tests/test\\\_scheduler\\\_smoke.py`

\- `python tests/run\\\_runtime\\\_smoke.py`



Confirmed passing after the consolidation sequence:



\- Scheduler smoke: PASS

\- Runtime smoke: PASS



\### Why This Matters



This pass reduced responsibility mixing inside `core/tasks/scheduler.py` and made future debugging more local and less fragile.



The value of this pass was not adding new user-facing capability. It was making the scheduler execution chain more inspectable and safer to change without destabilizing the rest of the runtime.



\### Result



Stable checkpoint after scheduler consolidation:



\- scheduler helper extraction completed

\- scheduler smoke: PASS

\- runtime smoke: PASS





\## 2026-04 Document Flow Repair Pass



This pass focused on fixing the real document flow path from planning to LLM prompt injection to file output persistence.



\### Problems Found



The document flow initially had multiple breakpoints:



\- deterministic document planning was overriding user-specified output paths

\- the active planning path was going through `core/system/llm\\\_planner.py`, not only `core/planning/planner.py`

\- `{{file\\\_content}}` was not reliably injected into LLM prompt templates

\- `write\\\_file` with `use\\\_previous\\\_text=true` could complete while still writing empty files

\- `task result` could show finished while the expected shared artifact was empty



\### Fixes Applied



Planning path preservation:



\- `core/system/llm\\\_planner.py`

\- `core/planning/planner.py`



These changes preserved user-specified source and output paths such as:



\- `workspace/shared/input.txt`

\- `workspace/shared/summary\\\_v2.txt`

\- `workspace/shared/action\\\_items\\\_v2.txt`



LLM prompt injection / execution path fixes:



\- `core/runtime/step\\\_executor.py`

\- `core/tasks/scheduler\\\_core/llm\\\_step\\\_helpers.py`

\- `core/tasks/scheduler.py`



These changes repaired the path where document content from `read\\\_file` must actually reach the LLM step.



Write-back / previous-result extraction fixes:



\- `core/runtime/step\\\_handlers.py`



This change repaired `write\\\_file` with `use\\\_previous\\\_text=true` so the previous LLM text is actually written into the target shared file instead of producing an empty artifact.



\### Real Flow Validation



Validated with real task runs, not only smoke tests.



Confirmed working flows:



1\. Summary flow

&#x20;  - input: `workspace/shared/input.txt`

&#x20;  - output: `workspace/shared/summary\\\_v2.txt`



2\. Action items flow

&#x20;  - input: `workspace/shared/input.txt`

&#x20;  - output: `workspace/shared/action\\\_items\\\_v2.txt`



Confirmed behavior:



\- planner preserved the requested output path

\- task reached `finished`

\- `task result` returned the final answer

\- shared output files were actually written

\- generated artifacts matched expected document-flow behavior



\### Example Validated Outputs



Summary flow produced a real plain-text summary in `summary\\\_v2.txt`.



Action-items flow produced a structured plain-text result in `action\\\_items\\\_v2.txt` with:



\- `ACTION ITEMS` heading

\- owner / task / due layout

\- extracted items such as:

&#x20; - Unassigned / Finish API draft / By Friday

&#x20; - Bob / Test upload flow / Next week



\### Why This Matters



This pass moved document flow from “planner can propose the steps” to “the full mainline actually executes and writes user-visible artifacts.”



This is more important than a synthetic smoke pass because it proves the end-to-end path works:



\- planning

\- task submit

\- task tick

\- LLM execution

\- previous-result handoff

\- shared file output

\- final task result reporting



\### Result



Stable document-flow checkpoint:



\- summary flow: working

\- action-items flow: working

\- output path preservation: working

\- LLM file-content injection: working

\- `use\\\_previous\\\_text` write-back: working

\- finished task result + shared artifact output: working



\### Evidence Kept



Keep the latest terminal screenshots showing:



\- scheduler smoke + runtime smoke pass

\- summary flow finished + `summary\_v2.txt` written

\- action-items flow finished + `action\_items\_v2.txt` written



These are useful as devlog proof and future demo / README evidence.


## 2026-04 Document Task Mainline Integration Pass

This pass focused on moving document flow from a direct/demo execution path into the official task lifecycle.

### Completed

Structured document-task support was extended across the mainline path:

- `core/planning/planner.py`
- `app.py`
- `core/tasks/scheduler.py`

What changed:

- planner gained a structured document-task entry path
- app direct-flow handling now builds and forwards document task context
- scheduler task creation / planning path now preserves document-task payload into planner context
- document tasks can now run through the official task lifecycle instead of only a direct one-shot path

Mainline flows now verified through official task path:

- `task create`
- `task submit`
- `task run`
- `task result`
- `task show`

Validated document task modes:

1. Summary task
   - goal: `summarize input.txt into summary.txt`

2. Action-items task
   - goal: `read input.txt and extract action items into action_items.txt`

### Validation

Confirmed working through the official task mainline:

- summary document task: PASS
- action-items document task: PASS
- `task create`: PASS
- `task submit`: PASS
- `task run`: PASS
- `task result`: PASS
- `task show`: PASS

Confirmed behavior:

- task record was written into `workspace/tasks.json`
- task workspace directory was created under `workspace/tasks/<task_id>/`
- task reached `finished`
- step progress reached `3/3`
- final answer was returned through official task result reporting
- task artifacts were written under the task directory:
  - `result.json`
  - `plan.json`
  - `runtime_state.json`
  - `execution_log.json`
  - `trace.json`
  - `task_snapshot.json`

Shared output artifacts also remained valid:

- `workspace/shared/summary.txt`
- `workspace/shared/action_items.txt`

### Why This Matters

This pass moved document flow from “it works as a direct execution shortcut” to “it works through the official task lifecycle.”

That matters because the system is no longer relying only on an isolated demo path. Document processing is now integrated into the same mainline used by the broader task system:

- task creation
- scheduling
- execution
- task-state persistence
- result inspection
- artifact tracking

This is a more meaningful checkpoint than direct-flow success alone, because it proves that document tasks can survive the real task OS path instead of only a narrow shortcut.

### Result

Stable checkpoint after document-task mainline integration:

- summary mainline task flow: working
- action-items mainline task flow: working
- structured document-task context path: working
- official task lifecycle integration: working
- task result / task show reporting: working
- shared output artifact generation: working

### Evidence Kept

Keep the latest terminal evidence showing:

- `task create` -> `task submit` -> `task run` for summary task
- `task result` and `task show` for finished summary task
- `task result` for finished action-items task
- `workspace/tasks.json` containing the created document tasks
- `workspace/tasks/<task_id>/` directories created for the finished tasks
- `workspace/shared/summary.txt`
- `workspace/shared/action_items.txt`

These are strong proof points for future devlog, README, demo, and external presentation material.


## 2026-04 Document Task CLI Entry Pass

This pass focused on making document-task creation more explicit at the CLI layer instead of relying only on free-form natural-language task goals.

### Completed

`app.py` was extended with explicit document-task command entries:

- `task doc-summary <input> <output>`
- `task doc-action-items <input> <output>`

These commands now create official tasks through the normal task system rather than bypassing the mainline.

### Validation

Confirmed working flow through the official task lifecycle:

1. create document task through CLI command
2. submit task
3. run task
4. inspect task result

Validated commands:

- `python app.py task doc-summary input.txt summary_cli.txt`
- `python app.py task doc-action-items input.txt action_items_cli.txt`

Confirmed behavior:

- task creation succeeded
- task reached `finished`
- `task result` returned the expected final answer
- task directory artifacts were created under `workspace/tasks/<task_id>/`
- document-task behavior remained consistent with the mainline integration pass

### Why This Matters

This pass makes document-task entry cleaner and more stable.

Before this, document-task creation depended mainly on natural-language task goals such as:

- `summarize input.txt into summary.txt`
- `read input.txt and extract action items into action_items.txt`

That path still works, but explicit CLI entry is better for:

- repeatable demos
- easier operator usage
- cleaner future UI / API integration
- reducing ambiguity at the command layer

### Result

Stable checkpoint after explicit document-task CLI entry:

- explicit summary task CLI entry: working
- explicit action-items task CLI entry: working
- official task lifecycle path preserved: working
- task result reporting preserved: working

### Evidence Kept

Keep the latest terminal evidence showing:

- `task doc-summary` task creation and completion
- `task doc-action-items` task creation and completion
- `task result` for the finished action-items CLI task

These are useful proof points for future README, demo, and operator-facing documentation.


