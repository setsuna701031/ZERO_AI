\# ZERO Devlog



\## 2026-04 Mainline Stabilization Pass



This pass focused on stabilizing the inner execution path before pushing farther into broader capability expansion.



\### Completed



\* Tool layer first-pass stabilization



&#x20; \* `core/tools/tool\\\\\\\\\\\\\\\_registry.py`

&#x20; \* `core/tools/command\\\\\\\\\\\\\\\_tool.py`

&#x20; \* `core/tools/file\\\\\\\\\\\\\\\_tool.py`

&#x20; \* `core/tools/workspace\\\\\\\\\\\\\\\_tool.py`

&#x20; \* `core/tasks/task\\\\\\\\\\\\\\\_paths.py`

\* Step executor first-pass outer-envelope stabilization



&#x20; \* `core/runtime/step\\\\\\\\\\\\\\\_executor.py`

\* Step handlers first-pass normalization



&#x20; \* `core/runtime/step\\\\\\\\\\\\\\\_handlers.py`

\* Executor first-pass internal responsibility cleanup



&#x20; \* `core/runtime/executor.py`

\* Scheduler first-pass internal responsibility cleanup



&#x20; \* `core/tasks/scheduler.py`



\### Validation Added



Tool layer validation:



\* `tests/test\\\\\\\\\\\\\\\_file\\\\\\\\\\\\\\\_tool.py`

\* `tests/test\\\\\\\\\\\\\\\_workspace\\\\\\\\\\\\\\\_tool.py`

\* `tests/test\\\\\\\\\\\\\\\_tool\\\\\\\\\\\\\\\_registry.py`

\* `tests/run\\\\\\\\\\\\\\\_tool\\\\\\\\\\\\\\\_layer\\\\\\\\\\\\\\\_smoke.py`



Runtime / execution validation:



\* `tests/test\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\_executor.py`

\* `tests/test\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\_repair\\\\\\\\\\\\\\\_rules.py`

\* `tests/test\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\_safe\\\\\\\\\\\\\\\_path\\\\\\\\\\\\\\\_repair.py`

\* `tests/test\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop.py`

\* `tests/test\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\_smoke.py`

\* `tests/run\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\_smoke.py`



\### Current Validation Status



Confirmed passing during this stabilization pass:



\* `python tests/run\\\\\\\\\\\\\\\_tool\\\\\\\\\\\\\\\_layer\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/test\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/test\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\_smoke.py`



\### Why This Matters



This stage moved the project from “it worked in a few manual runs” toward a repeatable validation path for the main local execution chain.



The main value of this pass is not only capability. It is reduced fragility while changing internals.



\### Current Mainline Status



Current stable checkpoint:



\* Tool layer smoke: PASS

\* Runtime smoke: PASS

\* Executor smoke: PASS

\* Scheduler smoke: PASS



\### Notes



This pass prioritized:



\* local-first execution

\* inspectable runtime state

\* stable task lifecycle behavior

\* safer internal refactoring boundaries

\* repeatable smoke validation



It did \*\*not\*\* prioritize polished UI or broad public packaging yet.



\## 2026-04 Scheduler Consolidation Pass



This pass focused on reducing scheduler responsibility mixing before pushing farther into new capability work.



\### Completed



Scheduler internal responsibility split completed across helper layers:



\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/queue\\\\\\\\\\\\\\\_sync\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/dispatch\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/repo\\\\\\\\\\\\\\\_state\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/trace\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/simple\\\\\\\\\\\\\\\_runner\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/step\\\\\\\\\\\\\\\_path\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/simple\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/command\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/llm\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\_helpers.py`



Main scheduler remained the orchestration shell while queue sync, dispatch flow, repo/runtime sync, trace handling, simple runner flow, path handling, step execution helpers, command execution, and LLM step handling were pulled into dedicated modules.



\### Validation



This consolidation pass was validated repeatedly during each extraction step with:



\* `python tests/test\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\_smoke.py`



Confirmed passing after the consolidation sequence:



\* Scheduler smoke: PASS

\* Runtime smoke: PASS



\### Why This Matters



This pass reduced responsibility mixing inside `core/tasks/scheduler.py` and made future debugging more local and less fragile.



The value of this pass was not adding new user-facing capability. It was making the scheduler execution chain more inspectable and safer to change without destabilizing the rest of the runtime.



\### Result



Stable checkpoint after scheduler consolidation:



\* scheduler helper extraction completed

\* scheduler smoke: PASS

\* runtime smoke: PASS



\## 2026-04 Document Flow Repair Pass



This pass focused on fixing the real document flow path from planning to LLM prompt injection to file output persistence.



\### Problems Found



The document flow initially had multiple breakpoints:



\* deterministic document planning was overriding user-specified output paths

\* the active planning path was going through `core/system/llm\\\\\\\\\\\\\\\_planner.py`, not only `core/planning/planner.py`

\* `{{file\\\\\\\\\\\\\\\_content}}` was not reliably injected into LLM prompt templates

\* `write\\\\\\\\\\\\\\\_file` with `use\\\\\\\\\\\\\\\_previous\\\\\\\\\\\\\\\_text=true` could complete while still writing empty files

\* `task result` could show finished while the expected shared artifact was empty



\### Fixes Applied



Planning path preservation:



\* `core/system/llm\\\\\\\\\\\\\\\_planner.py`

\* `core/planning/planner.py`



These changes preserved user-specified source and output paths such as:



\* `workspace/shared/input.txt`

\* `workspace/shared/summary\\\\\\\\\\\\\\\_v2.txt`

\* `workspace/shared/action\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\_v2.txt`



LLM prompt injection / execution path fixes:



\* `core/runtime/step\\\\\\\\\\\\\\\_executor.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\_core/llm\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler.py`



These changes repaired the path where document content from `read\\\\\\\\\\\\\\\_file` must actually reach the LLM step.



Write-back / previous-result extraction fixes:



\* `core/runtime/step\\\\\\\\\\\\\\\_handlers.py`



This change repaired `write\\\\\\\\\\\\\\\_file` with `use\\\\\\\\\\\\\\\_previous\\\\\\\\\\\\\\\_text=true` so the previous LLM text is actually written into the target shared file instead of producing an empty artifact.



\### Real Flow Validation



Validated with real task runs, not only smoke tests.



Confirmed working flows:



1\. Summary flow



&#x20;  \* input: `workspace/shared/input.txt`

&#x20;  \* output: `workspace/shared/summary\\\\\\\\\\\\\\\_v2.txt`

2\. Action items flow



&#x20;  \* input: `workspace/shared/input.txt`

&#x20;  \* output: `workspace/shared/action\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\_v2.txt`



Confirmed behavior:



\* planner preserved the requested output path

\* task reached `finished`

\* `task result` returned the final answer

\* shared output files were actually written

\* generated artifacts matched expected document-flow behavior



\### Example Validated Outputs



Summary flow produced a real plain-text summary in `summary\\\\\\\\\\\\\\\_v2.txt`.



Action-items flow produced a structured plain-text result in `action\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\_v2.txt` with:



\* `ACTION ITEMS` heading

\* owner / task / due layout

\* extracted items such as:



&#x20; \* Unassigned / Finish API draft / By Friday

&#x20; \* Bob / Test upload flow / Next week



\### Why This Matters



This pass moved document flow from “planner can propose the steps” to “the full mainline actually executes and writes user-visible artifacts.”



This is more important than a synthetic smoke pass because it proves the end-to-end path works:



\* planning

\* task submit

\* task tick

\* LLM execution

\* previous-result handoff

\* shared file output

\* final task result reporting



\### Result



Stable document-flow checkpoint:



\* summary flow: working

\* action-items flow: working

\* output path preservation: working

\* LLM file-content injection: working

\* `use\\\\\\\\\\\\\\\_previous\\\\\\\\\\\\\\\_text` write-back: working

\* finished task result + shared artifact output: working



\### Evidence Kept



Keep the latest terminal screenshots showing:



\* scheduler smoke + runtime smoke pass

\* summary flow finished + `summary\\\\\\\\\\\\\\\_v2.txt` written

\* action-items flow finished + `action\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\_v2.txt` written



These are useful as devlog proof and future demo / README evidence.



\## 2026-04 Document Task Mainline Integration Pass



This pass focused on moving document flow from a direct/demo execution path into the official task lifecycle.



\### Completed



Structured document-task support was extended across the mainline path:



\* `core/planning/planner.py`

\* `app.py`

\* `core/tasks/scheduler.py`



What changed:



\* planner gained a structured document-task entry path

\* app direct-flow handling now builds and forwards document task context

\* scheduler task creation / planning path now preserves document-task payload into planner context

\* document tasks can now run through the official task lifecycle instead of only a direct one-shot path



Mainline flows now verified through official task path:



\* `task create`

\* `task submit`

\* `task run`

\* `task result`

\* `task show`



Validated document task modes:



1\. Summary task



&#x20;  \* goal: `summarize input.txt into summary.txt`

2\. Action-items task



&#x20;  \* goal: `read input.txt and extract action items into action\\\\\\\\\\\\\\\_items.txt`



\### Validation



Confirmed working through the official task mainline:



\* summary document task: PASS

\* action-items document task: PASS

\* `task create`: PASS

\* `task submit`: PASS

\* `task run`: PASS

\* `task result`: PASS

\* `task show`: PASS



Confirmed behavior:



\* task record was written into `workspace/tasks.json`

\* task workspace directory was created under `workspace/tasks/<task\\\\\\\\\\\\\\\_id>/`

\* task reached `finished`

\* step progress reached `3/3`

\* final answer was returned through official task result reporting

\* task artifacts were written under the task directory:



&#x20; \* `result.json`

&#x20; \* `plan.json`

&#x20; \* `runtime\\\\\\\\\\\\\\\_state.json`

&#x20; \* `execution\\\\\\\\\\\\\\\_log.json`

&#x20; \* `trace.json`

&#x20; \* `task\\\\\\\\\\\\\\\_snapshot.json`



Shared output artifacts also remained valid:



\* `workspace/shared/summary.txt`

\* `workspace/shared/action\\\\\\\\\\\\\\\_items.txt`



\### Why This Matters



This pass moved document flow from “it works as a direct execution shortcut” to “it works through the official task lifecycle.”



That matters because the system is no longer relying only on an isolated demo path. Document processing is now integrated into the same mainline used by the broader task system:



\* task creation

\* scheduling

\* execution

\* task-state persistence

\* result inspection

\* artifact tracking



This is a more meaningful checkpoint than direct-flow success alone, because it proves that document tasks can survive the real task OS path instead of only a narrow shortcut.



\### Result



Stable checkpoint after document-task mainline integration:



\* summary mainline task flow: working

\* action-items mainline task flow: working

\* structured document-task context path: working

\* official task lifecycle integration: working

\* task result / task show reporting: working

\* shared output artifact generation: working



\### Evidence Kept



Keep the latest terminal evidence showing:



\* `task create` -> `task submit` -> `task run` for summary task

\* `task result` and `task show` for finished summary task

\* `task result` for finished action-items task

\* `workspace/tasks.json` containing the created document tasks

\* `workspace/tasks/<task\\\\\\\\\\\\\\\_id>/` directories created for the finished tasks

\* `workspace/shared/summary.txt`

\* `workspace/shared/action\\\\\\\\\\\\\\\_items.txt`



These are strong proof points for future devlog, README, demo, and external presentation material.



\## 2026-04 Document Task CLI Entry Pass



This pass focused on making document-task creation more explicit at the CLI layer instead of relying only on free-form natural-language task goals.



\### Completed



`app.py` was extended with explicit document-task command entries:



\* `task doc-summary <input> <output>`

\* `task doc-action-items <input> <output>`



These commands now create official tasks through the normal task system rather than bypassing the mainline.



\### Validation



Confirmed working flow through the official task lifecycle:



1\. create document task through CLI command

2\. submit task

3\. run task

4\. inspect task result



Validated commands:



\* `python app.py task doc-summary input.txt summary\\\\\\\\\\\\\\\_cli.txt`

\* `python app.py task doc-action-items input.txt action\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\_cli.txt`



Confirmed behavior:



\* task creation succeeded

\* task reached `finished`

\* `task result` returned the expected final answer

\* task directory artifacts were created under `workspace/tasks/<task\\\\\\\\\\\\\\\_id>/`

\* document-task behavior remained consistent with the mainline integration pass



\### Why This Matters



This pass makes document-task entry cleaner and more stable.



Before this, document-task creation depended mainly on natural-language task goals such as:



\* `summarize input.txt into summary.txt`

\* `read input.txt and extract action items into action\\\\\\\\\\\\\\\_items.txt`



That path still works, but explicit CLI entry is better for:



\* repeatable demos

\* easier operator usage

\* cleaner future UI / API integration

\* reducing ambiguity at the command layer



\### Result



Stable checkpoint after explicit document-task CLI entry:



\* explicit summary task CLI entry: working

\* explicit action-items task CLI entry: working

\* official task lifecycle path preserved: working

\* task result reporting preserved: working



\### Evidence Kept



Keep the latest terminal evidence showing:



\* `task doc-summary` task creation and completion

\* `task doc-action-items` task creation and completion

\* `task result` for the finished action-items CLI task



These are useful proof points for future README, demo, and operator-facing documentation.



\## 2026-04 Shared Artifact Visibility Pass



This pass focused on improving task result visibility for completed document tasks.



\### Completed



`app.py` was updated so that:



\* `task result <task\\\\\\\\\\\\\\\_id>`

\* `task show <task\\\\\\\\\\\\\\\_id>`



now display shared-scope artifacts in addition to task-local runtime files.



This means completed document tasks now expose shared outputs more directly instead of requiring the operator to remember that final artifacts are usually written under `workspace/shared/`.



\### Validation



Confirmed working on finished document tasks:



\* `task result` shows `shared\\\\\\\\\\\\\\\_artifacts`

\* `task show` shows `shared\\\\\\\\\\\\\\\_artifacts`



Confirmed shared-scope paths were visible in task output, including examples such as:



\* `workspace/shared/input.txt`

\* `workspace/shared/action\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\_cli.txt`



\### Why This Matters



Before this pass, task output mainly exposed task-local runtime files such as:



\* `result.json`

\* `plan.json`

\* `runtime\\\\\\\\\\\\\\\_state.json`

\* `execution\\\\\\\\\\\\\\\_log.json`

\* `trace.json`



Those are useful for engineering inspection, but operators usually care most about the actual shared output artifact.



This pass improves operator clarity, demo usability, and result discoverability without changing planner or scheduler core behavior.



\### Result



Stable checkpoint after shared artifact visibility update:



\* task-local runtime paths: still visible

\* shared output artifacts: now visible

\* `task result` usability: improved

\* `task show` usability: improved



\## 2026-04 Document Task Smoke and Mainline Validation Pass



This pass focused on locking the document-task checkpoint with repeatable validation.



\### Completed



Added:



\* `tests/run\\\\\\\\\\\\\\\_document\\\\\\\\\\\\\\\_task\\\\\\\\\\\\\\\_smoke.py`

\* `tests/run\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke.py`



`run\\\\\\\\\\\\\\\_document\\\\\\\\\\\\\\\_task\\\\\\\\\\\\\\\_smoke.py` validates both document-task flows end-to-end:



1\. summary flow

2\. action-items flow



The smoke covers:



\* task creation

\* task submission

\* task execution

\* task completion

\* shared output generation

\* `task result` output

\* `task show` output



`run\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke.py` was added as a higher-level validation entry for stable mainline checks.



\### Validation



Confirmed passing:



\* summary document-task smoke: PASS

\* action-items document-task smoke: PASS

\* document-task smoke overall: PASS

\* stable mainline smoke: PASS



Example outputs confirmed:



\* `summary\\\\\\\\\\\\\\\_smoke.txt` created under `workspace/shared/`

\* `action\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\_smoke.txt` created under `workspace/shared/`

\* smoke runner reported `ALL PASS`



\### Why This Matters



Before this pass, document-task validation depended mostly on manual CLI testing.



After this pass, the repository now has a repeatable smoke path that helps protect the document-task mainline against future regressions when `app.py`, scheduler, planner, or related task plumbing changes.



This is a stronger engineering checkpoint because the feature is no longer only “working now” — it is also guarded by repeatable validation.



\### Result



Stable checkpoint after document-task smoke integration:



\* document summary smoke: working

\* document action-items smoke: working

\* shared artifact validation: working

\* mainline smoke entry: working

\* repeatable regression protection: improved



\## 2026-04 AgentLoop Run Compatibility and Runtime Smoke Recovery Pass



This pass focused on restoring runtime validation compatibility after `tests/test\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop.py` exposed an interface mismatch.



\### Problem



`runtime\\\\\\\\\\\\\\\_smoke` was failing because:



\* `tests/test\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop.py` called `loop.run(user\\\\\\\\\\\\\\\_input)`

\* `core/agent/agent\\\\\\\\\\\\\\\_loop.py` no longer exposed a compatible `run(...)` entry



This caused runtime validation to fail with:



\* `AttributeError: 'AgentLoop' object has no attribute 'run'`



\### Completed



`core/agent/agent\\\\\\\\\\\\\\\_loop.py` was updated with a minimal compatibility `run(user\\\\\\\\\\\\\\\_input: str)` entry.



The fix was intentionally kept small:



\* restore compatibility with test expectations

\* preserve current direct / llm / task / single-shot routing structure

\* preserve forced planner-based document-task routing

\* avoid broad restructuring of the main AgentLoop body



\### Validation



Confirmed passing after the compatibility restoration:



\* `tests/test\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop.py`: PASS

\* `tests/run\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\_smoke.py`: PASS

\* `tests/run\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke.py`: PASS



\### Why This Matters



This pass does not just fix a broken test.



It restores a critical part of the runtime validation chain, which means the project once again has:



\* direct feature validation

\* task validation

\* runtime validation

\* stable mainline validation



That makes the current checkpoint more trustworthy, because document-task stabilization is no longer isolated from runtime-level validation.



\### Result



Stable checkpoint after AgentLoop compatibility recovery:



\* AgentLoop `run(...)` compatibility: restored

\* runtime smoke: restored

\* mainline smoke after runtime recovery: passing

\* validation chain completeness: improved



\## 2026-04-19 - Mainline smoke folded with requirement/execution demos



Today I finished folding the new demo smoke coverage into the stable mainline smoke path.



\### What was completed



\* Added `tests/run\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\_smoke.py`

\* Added `tests/run\\\\\\\\\\\\\\\_execution\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\_smoke.py`

\* Folded both into `tests/run\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke.py`

\* Verified `python tests/run\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke.py` passes end-to-end



\### Current result



\* Requirement demo smoke is now part of mainline validation

\* Execution demo smoke is now part of mainline validation

\* Mainline smoke now covers tool layer, scheduler, document task, requirement demo, and execution demo

\* Stable mainline smoke passed successfully



\### Still excluded for now



\* `runtime\\\\\\\\\\\\\\\_smoke`

\* Reason: currently blocked by `tests/test\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop.py`

\* Known blocker: `AttributeError: 'AgentLoop' object has no attribute 'run'`



\### Impact



\* Demo-oriented smoke checks are no longer isolated scripts only

\* They are now folded into the stable validation path

\* This improves confidence that the showcased flows are tied to the real mainline



\### Next step



\* Investigate and repair the runtime / `agent\\\\\\\\\\\\\\\_loop` path

\* Unblock runtime smoke so it can eventually be folded into the mainline validation suite



\## 2026-04 Smoke Script Rename and Runner Sync Pass



This pass focused on removing naming ambiguity inside `tests/` after several manual smoke scripts were still using misleading `test\\\\\\\\\\\\\\\_\\\\\\\\\\\\\\\*.py` names.



\### Problem



Some files under `tests/` looked like pytest tests by name, but were actually direct-execution smoke scripts with `main()` entrypoints.



This created two kinds of confusion:



\* operators could incorrectly try to run them with pytest

\* smoke runners could drift behind after renames and start referencing missing files



The most visible cases were:



\* `tests/test\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop.py`

\* `tests/test\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\_smoke.py`



\### Completed



Renamed manual smoke / diagnostic scripts to `run\\\\\\\\\\\\\\\_\\\\\\\\\\\\\\\*.py` naming:



\* `tests/test\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop.py` -> `tests/run\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\_smoke.py` -> `tests/run\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\_smoke.py` -> `tests/run\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\_reflection.py` -> `tests/run\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\_reflection.py`



Updated smoke runners to follow the renamed paths:



\* `tests/run\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\_smoke.py`

\* `tests/run\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke.py`



\### Validation



Confirmed passing after rename and runner sync:



\* `python tests/run\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke.py`



Confirmed result:



\* runtime smoke: PASS

\* mainline smoke: PASS

\* renamed scheduler smoke path: PASS

\* renamed agent loop smoke path: PASS



\### Why This Matters



This pass did not add new capability.



Its value was reducing test/smoke-role ambiguity inside the repository and keeping validation entrypoints aligned with what the files actually are.



That matters because the repository now separates these categories more clearly:



\* `test\\\\\\\\\\\\\\\_\\\\\\\\\\\\\\\*.py` for real test-style checks

\* `run\\\\\\\\\\\\\\\_\\\\\\\\\\\\\\\*.py` for direct-execution smoke and diagnostic scripts



This reduces future operator confusion and lowers the chance of smoke runner breakage during maintenance.



\### Result



Stable checkpoint after smoke-script rename and runner sync:



\* smoke script naming: cleaner

\* runtime smoke after rename: passing

\* mainline smoke after rename: passing

\* repository validation structure: clearer



\### Evidence Kept



Keep the latest terminal screenshots showing:



\* runtime smoke pass after script rename

\* mainline smoke all pass after script rename

\* clean git state after push



These are useful proof points for future devlog, README, and internal checkpoint tracking.



\## 2026-04 AgentLoop Structure Cleanup Pass



This pass focused on reducing responsibility mixing inside `core/agent/agent\\\\\\\\\\\\\\\_loop.py` without breaking the current mainline validation chain.



\### Problem



`agent\\\\\\\\\\\\\\\_loop.py` had started accumulating too many different kinds of responsibilities in one file:



\* route / mode policy decisions

\* component invocation compatibility glue

\* document-flow trace writing

\* main control flow for direct / llm / task / single-shot paths



This increased the risk that future changes would keep adding more special-case logic into the main loop body.



\### Completed



Three focused extractions were completed.



\#### 1. Route policy extraction



Added:



\* `core/agent/agent\\\\\\\\\\\\\\\_route\\\\\\\\\\\\\\\_policy.py`



Moved route / mode decision rules out of the main loop, including:



\* document-flow forced planner detection

\* summary/action-items document-flow matching

\* explicit task-request detection

\* task-mode entry decision



\#### 2. Component invocation adapter extraction



Added:



\* `core/agent/agent\\\\\\\\\\\\\\\_component\\\\\\\\\\\\\\\_invoker.py`



Moved callable compatibility / adapter glue out of the main loop, including:



\* router invocation

\* planner invocation

\* llm planner invocation

\* step executor invocation

\* verifier / safety guard wrapper calls



\#### 3. Document flow trace writer extraction



Added:



\* `core/agent/document\\\\\\\\\\\\\\\_flow\\\\\\\\\\\\\\\_trace\\\\\\\\\\\\\\\_writer.py`



Moved document-flow trace generation / payload extraction / runtime-info collection out of the main loop.



\### Validation



Confirmed passing after each extraction step:



\* `python tests/run\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\_smoke.py`



Confirmed result after the cleanup sequence:



\* runtime smoke: PASS

\* mainline smoke: PASS

\* agent loop smoke: PASS



\### Why This Matters



This pass did not primarily add new user-facing capability.



Its value was structural:



\* `agent\\\\\\\\\\\\\\\_loop.py` is now closer to a true orchestration shell

\* policy logic is more explicit

\* invocation compatibility glue is separated

\* document-flow tracing no longer lives inside the main loop body



This makes future changes safer, because new route rules, adapter logic, or trace behavior no longer need to pile directly into the core loop file.



\### Result



Stable checkpoint after AgentLoop structure cleanup:



\* route policy: extracted

\* component invoker: extracted

\* document flow trace writer: extracted

\* runtime smoke: passing

\* mainline smoke: passing

\* agent loop smoke: passing



\## 2026-04-20 - Mainline stabilization + requirement demo showcase checkpoint



This checkpoint focused on bringing the current mainline, demo path, and public-facing documentation into alignment.



\### Core stabilization completed



The main execution path was tightened across the planner, loop, executor, and guard layers.



Completed:



\* `core/planning/planner.py`

\* `core/planning/planner\\\\\\\\\\\\\\\_rule\\\\\\\\\\\\\\\_parser.py`

\* `core/agent/agent\\\\\\\\\\\\\\\_loop.py`

\* `core/runtime/step\\\\\\\\\\\\\\\_executor.py`

\* `core/tasks/execution\\\\\\\\\\\\\\\_guard.py`



What changed:



\* planner result contract was stabilized

\* agent loop response / execution contract was stabilized

\* step executor envelope and batch contract were stabilized

\* guard command policy was repaired to allow trusted python mainline/demo execution while still blocking non-whitelisted command execution

\* requirement demo mainline command path was repaired after guard blocking surfaced during smoke validation



\### Validation confirmed



Confirmed passing after the stabilization sequence:



\* `python tests/run\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/test\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\_executor.py`

\* `python tests/run\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\_smoke.py`



Confirmed result:



\* runtime smoke: PASS

\* mainline smoke: PASS

\* step executor tests: PASS

\* agent loop smoke: PASS

\* scheduler smoke: PASS



\### Showcase chain established



A fixed requirement demo showcase path was set up and validated.



Fixed demo input:



\* `workspace/shared/requirement.txt`



Validated requirement demo command:



\* `python main.py requirement-demo`



Validated generated outputs:



\* `workspace/shared/project\\\\\\\\\\\\\\\_summary.txt`

\* `workspace/shared/implementation\\\\\\\\\\\\\\\_plan.txt`

\* `workspace/shared/acceptance\\\\\\\\\\\\\\\_checklist.txt`



Requirement demo assets were organized under:



\* `demos/07\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\_demo/requirement\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\_execution\\\\\\\\\\\\\\\_pass\\\\\\\\\\\\\\\_2026-04-20.mp4`

\* `demos/07\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\_demo/requirement\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\_outputs\\\\\\\\\\\\\\\_2026-04-20.mp4`



This means the requirement scenario now has:



\* fixed input

\* repeatable command

\* stable outputs

\* execution proof

\* output proof



\### Documentation aligned



Public-facing demo documents were updated to match the new requirement showcase path.



Updated:



\* `README.md`

\* `docs/demo.md`



Checkpoint images were also cleaned up and aligned under:



\* `docs/images/checkpoints/`



Primary current checkpoint set:



\* `checkpoint\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\_smoke\\\\\\\\\\\\\\\_all\\\\\\\\\\\\\\\_pass.png`

\* `checkpoint\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\_smoke\\\\\\\\\\\\\\\_pass.png`

\* `checkpoint\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\_pass.png`

\* `checkpoint\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\_outputs.png`

\* `checkpoint\\\\\\\\\\\\\\\_execution\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\_pass.png`

\* `checkpoint\\\\\\\\\\\\\\\_task\\\\\\\\\\\\\\\_os\\\\\\\\\\\\\\\_integration\\\\\\\\\\\\\\\_tests\\\\\\\\\\\\\\\_passed.png`



\### Why This Matters



This checkpoint is important because it is not only an internal engineering repair.



It aligns three layers at once:



\* mainline execution stability

\* repeatable representative demo flow

\* public-facing explanation and proof assets



That makes the project easier to validate internally and easier to explain externally.



\### Result



Stable checkpoint after this pass:



\* planner / loop / execution / guard path: stabilized

\* runtime smoke: passing

\* mainline smoke: passing

\* requirement demo showcase: established

\* README / demo docs: aligned

\* checkpoint image naming: aligned

\* demo video assets: organized



\## 2026-04-20 - Mini-build demo showcase checkpoint



This checkpoint focused on adding a stronger execution-oriented showcase on top of the stabilized mainline.



\### What was established



A new representative scenario was added through:



\* `python main.py mini-build-demo`



This scenario was designed to demonstrate a compact engineering workflow:



\* requirement input

\* planning output

\* generated Python artifact

\* script execution

\* result verification



\### Fixed inputs



The mini-build demo now uses fixed workspace inputs:



\* `workspace/shared/requirement.txt`

\* `workspace/shared/numbers\\\\\\\\\\\\\\\_input.txt`



The requirement defines a small engineering build task around a statistics utility.

The numbers input provides the fixed data used for execution verification.



\### Generated outputs



Validated mini-build outputs now include:



\* `workspace/shared/project\\\\\\\\\\\\\\\_summary.txt`

\* `workspace/shared/implementation\\\\\\\\\\\\\\\_plan.txt`

\* `workspace/shared/acceptance\\\\\\\\\\\\\\\_checklist.txt`

\* `workspace/shared/number\\\\\\\\\\\\\\\_stats.py`

\* `workspace/shared/stats\\\\\\\\\\\\\\\_result.txt`



\### What the flow proves



This scenario now proves that ZERO can move beyond planning-only delivery and complete a compact requirement-to-build chain:



\* read requirement

\* generate planning bundle

\* generate executable script

\* run that script locally

\* write result file

\* verify output values



Validated result fields include:



\* `sum`

\* `average`

\* `max`

\* `min`



\### Validation result



Confirmed successful run:



\* `python main.py mini-build-demo`: PASS



Confirmed visible proof in terminal:



\* generated `number\\\\\\\\\\\\\\\_stats.py`

\* generated `stats\\\\\\\\\\\\\\\_result.txt`

\* verified statistics output

\* `\\\\\\\\\\\\\\\[mini-build-demo] PASS`



\### Showcase assets organized



Mini-build demo assets were organized under:



\* `demos/08\\\\\\\\\\\\\\\_mini\\\\\\\\\\\\\\\_build\\\\\\\\\\\\\\\_demo/mini\\\\\\\\\\\\\\\_build\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\_execution\\\\\\\\\\\\\\\_pass\\\\\\\\\\\\\\\_2026-04-20.mp4`



A dedicated checkpoint image should be kept as:



\* `docs/images/checkpoints/checkpoint\\\\\\\\\\\\\\\_mini\\\\\\\\\\\\\\\_build\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\_pass.png`



\### Documentation alignment



Public-facing documentation was extended to include this new showcase.



Updated / to update together:



\* `README.md`

\* `docs/demo.md`

\* `docs/proof\\\\\\\\\\\\\\\_map.md`

\* `docs/devlog.md`



\### Why This Matters



This checkpoint is important because it upgrades the outward story of the system.



Before this, the strongest public-facing examples were mainly:



\* planning-oriented requirement delivery

\* minimal execution proof



Now the project also has a compact execution showcase that demonstrates:



\* requirement-driven flow

\* planning artifacts

\* generated implementation artifact

\* real execution

\* result verification



That is a stronger proof that ZERO is not only producing documentation or chat-like outputs.

It can now show a small but complete engineering loop.



\### Result



Stable checkpoint after this pass:



\* mini-build demo entry: established

\* requirement -> planning -> implementation -> execution -> verification chain: demonstrated

\* generated script output: validated

\* result file output: validated

\* mini-build demo video asset: organized

\* public-facing showcase coverage: expanded



\## 2026-04-21 - Runtime trace and command execution contract checkpoint



This checkpoint focused on tightening the mainline runtime contract rather than adding new outward-facing capability.



\### v31 validation



Validated against a new manual-tick summary task run through the official task path.



Confirmed:



\* `execution\\\\\\\\\\\\\\\_trace` remained at the outer step result layer

\* nested inner `execution\\\\\\\\\\\\\\\_trace` was removed

\* summary flow completed successfully under manual ticks

\* runtime state stayed inspectable after the trace cleanup pass



\### v32 step 1



Command execution cwd policy was repaired.



Confirmed:



\* command execution no longer defaulted into `workspace/tasks/<task\\\\\\\\\\\\\\\_id>/`

\* command execution now runs from project root when no explicit command cwd is provided

\* `python app.py ...` style command tasks no longer fail due to missing `app.py`



\### v32 step 2



Command result contract was cleaned and made more explicit.



Confirmed:



\* original step payload is preserved without misleading execution-only cwd fields

\* actual command execution cwd is explicitly recorded as `effective\\\\\\\\\\\\\\\_cwd`

\* nested command result also records the real cwd used for execution

\* command task finished successfully with `returncode = 0`



\### Why This Matters



This checkpoint improves trust in the runtime execution record.



The value is not only that command tasks now work more reliably.

It is that runtime inspection is cleaner and less misleading:



\* trace ownership is clearer

\* nested payload noise is reduced

\* command execution location is explicit

\* debugging future command / DAG behavior becomes safer



\### Result



Stable checkpoint after this pass:



\* mini-build demo entry: established

\* requirement -> planning -> implementation -> execution -> result pipeline: validated

\* generated script output: validated

\* result file output: validated

\* mini-build demo video asset: organized

\* public-facing showcase coverage: expanded



v31 validation: passed



\* execution\_trace outer kept

\* nested inner execution\_trace removed

\* summary flow finished under manual ticks



v32 step 1: passed



\* command cwd policy fixed

\* command now runs from project root



v32 step 2: passed



\* command result contract cleaned

\* original step preserved

\* effective\_cwd recorded explicitly



v32 step 3: passed

\- command stdout retained

\- parsed\_output added

\- output\_text added



v32 step 4: passed

\- command message/final\_answer summarized

\- large JSON stdout no longer pollutes top-level message fields



v33 step 1: passed

\- app display layer now consumes normalized command result

\- task result uses summarized final\_answer

\- task show uses summarized final\_answer

\- large raw stdout no longer pollutes main CLI display



v33 step 2: passed

* task result now shows parsed\_output summary block
* task show now shows parsed\_output summary block
* normalized command result is now visible in main CLI display
* no need to inspect runtime\_state.json for basic command output understanding

v33 step 2 smoke: passed

* parsed\_output summary block verified on a newly created command task
* task result displays summarized parsed\_output correctly
* task show displays summarized parsed\_output correctly
* CLI display path is repeatable, not single-task only

v34 step 1: passed

* command-like goals are now blocked from task semantic path
* task create accepts real goal sentences only
* CLI/command input is no longer treated as task intent
* semantic task path and command path begin to separate

v34 step 2b: passed

* planner routing precedence fixed
* summary now uses semantic\_summary\_pipeline
* action\_items now uses semantic\_action\_items\_pipeline
* report now uses semantic\_report\_pipeline
* semantic type now determines planner execution route

v34 step 3: passed

* semantic summary pipeline produces summary.txt
* semantic action\_items pipeline produces action\_items.txt
* semantic report pipeline produces report.txt
* semantic routes are not only planned, but also land real shared artifacts

v34 step 4: passed

* task run <task\_id> now executes the requested task
* targeted semantic report task reaches finished 3/3
* previous\_result substitution now lands real report content
* report.txt is no longer written as literal {{previous\_result}}

v34 semantic task smoke: passed

* added tests/run\_semantic\_task\_smoke.py
* command-like task goals are blocked by smoke validation
* summary semantic pipeline validated
* action\_items semantic pipeline validated
* report semantic pipeline validated
* targeted task run validated through smoke
* shared semantic artifacts validated:

  * summary\_smoke.txt
  * action\_items\_smoke.txt
  * report\_smoke.txt
* previous\_result placeholder leak is no longer present in report\_smoke.txt
* semantic-task smoke now provides repeatable regression coverage for the new semantic task path

v35 requirement-pack semantic pipeline: passed

* planner now routes requirement-pack into a fixed semantic artifact pipeline
* requirement-demo now writes real shared artifacts:

  * project\_summary.txt
  * implementation\_plan.txt
  * acceptance\_checklist.txt
* requirement\_demo\_smoke now passes against real file outputs
* mainline\_smoke returns ALL PASS after integrating requirement-pack fix
* requirement-pack path is no longer a description-only completion; it now lands real artifacts

## 2026-04-22 - Document pipeline identity stabilization checkpoint

This checkpoint focused on finishing the document-task identity layer instead of adding a new outward-facing capability.

### What was completed

The document flow family now has three distinct pipelines with stable task-level identity:

* summary pipeline
* action-items pipeline
* requirement pipeline

Confirmed pipeline identities:

* `scenario`
* `task\_type`
* `mode`
* `pipeline\_name`
* `execution\_name`

Confirmed document pipeline set:

* `doc\_summary` -> `summary\_pipeline`
* `doc\_action\_items` -> `action\_items\_pipeline`
* `doc\_requirement` -> `requirement\_pipeline`

### What was repaired

This pass fixed two important document-task consistency problems:

1. Metadata persistence consistency
* document pipeline identity is now persisted across:

  * `task\_snapshot.json`
  * `runtime\_state.json`
  * `result.json`
2. Split submit/run path consistency
* requirement pipeline identity now survives the normal task lifecycle even when the operator runs:

  * `task create`
  * `task submit`
  * `task run`

This repaired the earlier mismatch where identity could appear during creation but disappear or drift after finished execution.

### Validation confirmed

Confirmed through real task runs and CLI inspection:

* `task show` displays:

  * `scenario`
  * `task\_type`
  * `mode`
  * `pipeline\_name`
  * `execution\_name`
* `task result` displays:

  * `scenario`
  * `task\_type`
  * `mode`
  * `pipeline\_name`
  * `execution\_name`

Confirmed stable identity after finished execution for:

* summary pipeline
* action-items pipeline
* requirement pipeline

Confirmed requirement pipeline now remains:

* `scenario: doc\_requirement`
* `task\_type: document`
* `mode: requirement`
* `pipeline\_name: requirement\_pipeline`
* `execution\_name: requirement\_execution`

even after a separated:

* `task submit <task\_id>`
* `task run <task\_id>`

flow.

### Architectural conclusion

This checkpoint matters because the project now has three stable document-pipeline samples, which is the minimum useful point for structure observation.

Current conclusion:

* the system now clearly has a `document pipeline family`
* summary and action-items are single-output siblings
* requirement is a multi-output sibling
* future abstraction should not collapse them into one oversimplified template

At this stage, the correct architectural reading is:

* shared family exists
* direct factory extraction should still be cautious
* requirement proves there are at least two document-pipeline shapes:

  * single-output
  * multi-output

### Result

Stable checkpoint after this pass:

* summary pipeline identity: stable
* action-items pipeline identity: stable
* requirement pipeline identity: stable
* metadata persistence: stable
* CLI-visible separation: stable
* split submit/run path consistency: stable

### Evidence kept

Keep the latest terminal screenshots showing:

* finished summary pipeline with visible identity fields
* finished action-items pipeline with visible identity fields
* finished requirement pipeline with visible identity fields
* requirement pipeline surviving separated `submit` + `run`
* `task show` and `task result` both exposing the same pipeline identity

## 2026-04-22 - Document pipeline family first-pass cleanup checkpoint

This checkpoint focused on performing a low-risk cleanup pass on the document pipeline family after the identity layer and regression protection had already been stabilized.

### What was completed

`app.py` document pipeline logic was consolidated into a clearer family-oriented helper layer without changing the outward command surface.

Document family coverage remained:

* summary pipeline
* action-items pipeline
* requirement pipeline

The cleanup preserved the existing command/task entry points, including:

* `task doc-summary <input> <output>`
* `task doc-action-items <input> <output>`
* `task doc-requirement <input>`
* `task requirement-pack <input>`

### Cleanup intent

This was intentionally **not** a full factory extraction.

The goal was narrower:

* reduce repeated document-pipeline logic inside `app.py`
* keep outward behavior stable
* keep requirement as a multi-output member
* avoid premature over-abstraction

The cleanup pass primarily grouped and normalized:

* document pipeline metadata construction
* document pipeline task creation helpers
* document pipeline run/finalization helpers
* post-finish metadata persistence handling
* summary/action-items/requirement naming alignment

### Validation

Confirmed before acceptance:

* `python -m py\_compile app.py`
* `python tests/run\_mainline\_smoke.py`

Confirmed passing after cleanup:

* tool layer smoke: PASS
* scheduler smoke: PASS
* runtime smoke: PASS
* document task smoke: PASS
* document pipeline identity smoke: PASS
* requirement demo smoke: PASS
* execution demo smoke: PASS
* semantic task smoke: PASS
* mainline smoke: ALL PASS

### Why This Matters

This checkpoint is important because it moves the document pipeline family from “working but spread across the CLI layer” toward “working and structurally easier to maintain,” while staying inside the current protected mainline.

The value of this pass was not adding a new user-facing capability.

Its value was:

* cleaner document-family responsibility grouping in `app.py`
* lower local maintenance cost
* safer future document-family changes
* preserved stability under full mainline regression coverage

### Architectural conclusion

At this stage, the project now has:

* three stable document pipeline samples
* identity persistence protection
* dedicated document pipeline identity smoke coverage
* mainline smoke protection
* a first-pass family cleanup in `app.py`

The correct next-step constraint remains:

* do not rush into a broad factory abstraction
* keep future extraction incremental
* continue respecting the distinction between:

  * single-output document pipelines
  * multi-output document pipelines

### Result

Stable checkpoint after this pass:

* document family first-pass cleanup: completed
* outward CLI/task behavior: preserved
* summary pipeline: stable
* action-items pipeline: stable
* requirement pipeline: stable
* mainline regression after cleanup: passing

### Evidence kept

Keep the latest terminal screenshots showing:

* `python -m py\_compile app.py` passing after cleanup
* `python tests/run\_mainline\_smoke.py` returning ALL PASS after cleanup
* the folded mainline run including document pipeline identity smoke

## \[Checkpoint] Document Pipeline First Cut

### Summary

Completed first-stage consolidation of document-related pipelines under stable execution flow.

### Completed

* summary pipeline (input → summary.txt)
* action\_items pipeline
* requirement pipeline
* document pipeline identity persistence
* CLI visible separation
* document pipeline smoke test
* fold-in mainline smoke
* app.py document family first integration

### Notes

* This is a structural consolidation under stable functionality (no feature expansion)
* Pipelines are now consistent enough for demo-grade flow integration

### Next

* Define a single demo-grade mainline scenario
* Add end-to-end smoke for that scenario

## 2026-04-23 - Full-build demo mainline checkpoint

This checkpoint focused on turning the existing requirement/planning/execution pieces into a more complete representative workflow and then protecting it with smoke coverage.

### What was completed

`main.py` gained a new:

* `full-build-demo`

This flow now executes a fixed representative chain:

1. prepare requirement input
2. prepare numbers input
3. run `requirement-pack`
4. verify planning artifacts
5. generate implementation artifact
6. execute generated script
7. verify result file contents

Validated generated artifacts:

* `workspace/shared/project\_summary.txt`
* `workspace/shared/implementation\_plan.txt`
* `workspace/shared/acceptance\_checklist.txt`
* `workspace/shared/number\_stats.py`
* `workspace/shared/stats\_result.txt`

### Validation added

Added:

* `tests/run\_full\_build\_demo\_smoke.py`

This smoke validates:

* `python main.py full-build-demo`
* planning artifacts exist and are non-empty
* generated script exists
* `stats\_result.txt` exists and is non-empty
* verified numeric outputs:

  * `sum: 100`
  * `average: 25`
  * `max: 40`
  * `min: 10`

### Smoke integration

`run\_full\_build\_demo\_smoke.py` was folded into:

* `tests/run\_mainline\_smoke.py`

This means the representative requirement -> build -> execute -> verify chain is now part of protected mainline validation instead of being only a manual demo path.

### Requirement smoke hardening

During fold-in, the older requirement smoke was exposed as too brittle because it depended on exact wording such as `Deliverable` in `acceptance\_checklist.txt`.

`tests/run\_requirement\_demo\_smoke.py` was updated to validate more stable workflow signals instead:

* command success
* non-empty artifact generation
* stable section checks such as:

  * `Acceptance`
  * `Verification`

instead of overfitting to one exact phrasing.

### Validation confirmed

Confirmed passing after integration:

* `python tests/run\_requirement\_demo\_smoke.py`
* `python tests/run\_full\_build\_demo\_smoke.py`
* `python tests/run\_mainline\_smoke.py`

Confirmed result:

* requirement demo smoke: PASS
* full-build demo smoke: PASS
* mainline smoke: ALL PASS

### Why This Matters

This checkpoint is important because the project now has a more representative engineering workflow protected by the stable mainline validation path.

The value is not just that a demo command works.

The value is that the system can now repeatedly prove a compact chain of:

* requirement intake
* planning artifact generation
* implementation artifact generation
* execution
* result verification

under smoke protection.

### Result

Stable checkpoint after this pass:

* `full-build-demo` entry: established
* representative requirement -> build -> execute -> verify flow: established
* dedicated full-build smoke: added
* requirement smoke: hardened
* mainline smoke after fold-in: passing

### Evidence kept

Keep the latest terminal screenshots showing:

* `python main.py full-build-demo` PASS
* `python tests/run\_full\_build\_demo\_smoke.py` ALL PASS
* `python tests/run\_requirement\_demo\_smoke.py` ALL PASS
* `python tests/run\_mainline\_smoke.py` ALL PASS after fold-in

## 2026-04-23 - Full-build demo upgraded to system-task path

This checkpoint upgraded the full-build representative workflow from a helper-written implementation artifact into a system-task-generated implementation artifact, and then verified that the workflow still passed under smoke protection and mainline validation.

### What changed

The previous `full-build-demo` flow still depended on a direct helper write for `number\_stats.py`.

This pass replaced that behavior with a formal task path:

* `task implementation-proof`

That task now generates:

* `workspace/shared/number\_stats.py`

through the normal task system instead of writing the implementation artifact directly inside `main.py`.

### Key engineering fix

The main issue was not the planner response itself.

At create time, the structured implementation plan was already visible, but submit/run still fell back to the old generic planning path.

This was fixed by making the structured plan persist into the actual task state consumed by runtime execution, including:

* `planner\_result`
* `steps`
* `steps\_total`
* `current\_step\_index`
* reset execution/result fields for the created task
* synchronized task persistence into repo-backed task state and task artifacts such as `plan.json` / `task\_snapshot.json`

After this fix, `implementation-proof` executed as the intended 2-step structured plan:

1. `write\_file shared/number\_stats.py`
2. `verify shared/number\_stats.py contains "stats\_result.txt"`

instead of falling back into the broken 4-step generic path.

### Escaping / script-content fix

The generated `number\_stats.py` content was also corrected so the written script preserves:

* `"\\n".join(...)`
* `+ "\\n"`

as real Python string literals in the generated file.

This removed the earlier broken script output / invalid string literal issue.

### Full-build-demo upgrade

`main.py` was updated so that:

* `full-build-demo`
* `mini-build-demo`

no longer directly write the implementation script.

Instead, they now:

1. create `implementation-proof`
2. submit and run that task
3. verify the generated implementation artifact
4. execute the generated Python utility
5. verify the final stats output

This upgraded the representative flow into:

* requirement intake
* planning artifact generation
* implementation task generation
* execution
* result verification

### Validation

Confirmed passing:

* `python main.py full-build-demo`
* `python tests/run\_full\_build\_demo\_smoke.py`
* `python tests/run\_mainline\_smoke.py`

Observed results:

* `\[full-build-demo] PASS`
* `\[full-build-demo-smoke] ALL PASS`
* `\[mainline-smoke] ALL PASS`

### Why this checkpoint matters

This is a stronger checkpoint than the previous helper-based version.

The value is that the representative workflow is no longer:

* planning -> helper-written script -> execution

It is now:

* planning -> system-task-generated implementation artifact -> execution

That makes the workflow more representative of the intended engineering-agent path and more defensible as a real system capability instead of a stitched demo path.

### Evidence kept

Keep these screenshots:

* `checkpoint\_full\_build\_demo\_pass.png`
* `checkpoint\_mainline\_smoke\_all\_pass\_after\_full\_build.png`

### Stable checkpoint after this pass

* `implementation-proof` task path: established
* structured plan persistence into runtime-executed task state: fixed
* generated implementation artifact path: working
* `full-build-demo` upgraded to system-task path: complete
* full-build smoke: passing
* mainline smoke after integration: passing

## 2026-04-23 - Implementation-proof smoke folded into mainline

This checkpoint focused on closing the protection gap around the new system-task-based implementation path.

### What was completed

Added:

* `tests/run\_implementation\_proof\_smoke.py`

This smoke validates the new formal implementation path:

* `python app.py task implementation-proof`
* task creation succeeds
* structured implementation plan is visible at create time
* task submit succeeds
* task run succeeds
* `task show` reaches:

  * `status: finished`
  * `step: 2/2`
* generated artifact exists:

  * `workspace/shared/number\_stats.py`

It also validates stable script content markers such as:

* `from pathlib import Path`
* `numbers\_input.txt`
* `stats\_result.txt`
* `"\\n".join(...)`

### Mainline integration

`tests/run\_implementation\_proof\_smoke.py` was folded into:

* `tests/run\_mainline\_smoke.py`

This means the new implementation-task path is no longer protected only indirectly through `full-build-demo`.

It now has its own direct regression coverage and is also part of the stable mainline smoke chain.

### Full-build-demo validation rule sync

While folding this in, `main.py` still had an older brittle checklist assertion inside `full-build-demo` that required the exact word:

* `Deliverable`

The current requirement output no longer guarantees that wording.

`main.py` was updated so that `full-build-demo` now validates more stable checklist markers instead:

* `Acceptance Criteria`
* `Verification`

This aligned the full-build-demo validation logic with the earlier smoke-hardening direction and removed the last stale brittle assertion in that path.

### Validation confirmed

Confirmed passing after integration:

* `python main.py full-build-demo`
* `python tests/run\_implementation\_proof\_smoke.py`
* `python tests/run\_full\_build\_demo\_smoke.py`
* `python tests/run\_mainline\_smoke.py`

Confirmed result:

* implementation-proof smoke: PASS
* full-build-demo smoke: PASS
* mainline smoke: ALL PASS

Current mainline summary after fold-in:

* pass: 12
* fail: 0
* missing\_required: 0
* skip\_optional: 0

### Why this matters

This checkpoint matters because the new implementation-task path is now protected both directly and indirectly:

* directly by `implementation-proof smoke`
* indirectly by `full-build-demo smoke`
* globally by `mainline smoke`

That makes the representative engineering chain more trustworthy:

* requirement intake
* planning artifact generation
* implementation task generation
* execution
* verification

The project is now less dependent on a single showcase path to expose regressions in implementation-task behavior.

### Evidence kept

Keep these screenshots:

* `checkpoint\_full\_build\_demo\_pass.png`
* `checkpoint\_mainline\_smoke\_all\_pass\_after\_full\_build.png`

### Stable checkpoint after this pass

* `implementation-proof` task path: established
* `implementation-proof` smoke: added
* `implementation-proof` folded into mainline smoke: complete
* `full-build-demo` brittle acceptance check: fixed
* `full-build-demo`: passing
* `mainline smoke`: ALL PASS

## 2026-04-24 - Persona Runtime showcase checkpoint

This checkpoint focused on adding a local visual runtime shell for ZERO and connecting it to real runtime status and execution-demo output.

### What was completed

Added a new Persona Runtime window:

* `ui/persona\_runtime\_window.py`

Added persona visual support and assets:

* `assets/persona/zero\_v1/profile.json`
* `assets/persona/zero\_v1/circuit\_bg.png`
* `assets/persona/zero\_v1/idle\_open.png`
* `assets/persona/zero\_v1/idle\_half.png`
* `assets/persona/zero\_v1/idle\_closed.png`
* `core/persona/visual\_profile.py`

Added validation coverage:

* `tests/run\_persona\_visual\_profile\_smoke.py`

Updated public-facing showcase documentation:

* `README.md`
* `docs/demo\_assets/persona\_runtime/persona\_runtime\_v1\_visual\_ready.png`
* `docs/demo\_assets/persona\_runtime/persona\_runtime\_v2\_execution\_demo\_success.png`

### Issues fixed during integration

The first UI runs appeared unchanged because the active Python environment did not have Pillow installed.

After installing Pillow, the UI correctly enabled image composition, including:

* circuit background rendering
* transparent persona image composition
* persona scaling inside the visual panel
* runtime state badge display

Blink animation was temporarily disabled because the open / half / closed eye frames do not yet share identical transparent canvas alignment. Keeping blink disabled prevents visual jumping until the image assets are normalized.

### Validation confirmed

Confirmed manually through the Persona Runtime window:

* visual persona panel loads correctly
* `Status` outputs a runtime snapshot
* `Show Panel` opens the persona panel
* `Run Execution Demo` runs successfully
* runtime state updates to `SUCCESS`
* output hint points to `workspace/shared/hello.py`
* execution-demo artifacts and trace paths are displayed in the chat panel

Confirmed repository update:

* pushed to GitHub main at commit `351842e`

### Why this matters

This checkpoint adds a visible runtime shell to ZERO.

The value is not only that the UI looks better. The window now shows that the local runtime can expose:

* persona identity
* live runtime state
* command interaction
* status snapshot output
* execution-demo success
* task artifact paths

This makes ZERO easier to demonstrate externally because it provides a visual proof layer on top of the existing CLI/task system.

### Stable checkpoint after this pass

* Persona Runtime UI: added
* persona visual profile: added
* visual assets: added
* Pillow image composition: working
* Status snapshot: working
* execution-demo through UI: working
* README showcase section: added
* persona runtime demo screenshots: added
* GitHub main push: complete

### Evidence kept

Keep these screenshots:

* `docs/demo\_assets/persona\_runtime/persona\_runtime\_v1\_visual\_ready.png`
* `docs/demo\_assets/persona\_runtime/persona\_runtime\_v2\_execution\_demo\_success.png`


## 2026-04-24 - Persona Runtime multi-step demo checkpoint

This checkpoint focused on extending the Persona Runtime window from a single execution-demo showcase into a visible multi-step document-flow showcase.

### What was completed

Added a new Persona Runtime UI action:

* `Run Multi-Step Demo`

Added a matching persona command path:

* `run multi-step-demo`

The new multi-step demo is routed through the existing document demo flow so the Persona Runtime window can now display a document-oriented multi-step capability instead of only the smaller execution-demo path.

Updated files:

* `ui/persona_runtime_window.py`
* `core/persona/chat_shell.py`

Added new showcase evidence:

* `docs/demo_assets/persona_runtime/persona_runtime_v3_multistep_demo_success.png`

### Validation confirmed

Confirmed manually through the Persona Runtime window:

* `Run Multi-Step Demo` button is visible
* `run multi-step-demo` command is accepted from the chat input
* runtime state updates to `SUCCESS`
* last capability updates to `multi-step-demo`
* last result updates to `success`
* output hints show:
  * `workspace/shared/summary_demo.txt`
  * `workspace/shared/action_items_demo.txt`
* chat output shows the underlying document-demo flow reaching `PASS`

Confirmed repository update:

* pushed to GitHub main at commit `8e0cf3e`

### Why this matters

This is a stronger Persona Runtime showcase than the first execution-demo-only version.

The previous UI proof showed that Persona Runtime could trigger a simple capability and display runtime state.

This checkpoint shows that the same UI shell can also represent a multi-step document-oriented flow with multiple output artifacts. That moves the Persona Runtime window closer to a real operator-facing surface rather than only a visual wrapper around a single hello-world style execution path.

The important distinction is:

* execution-demo proves command execution and artifact landing
* multi-step-demo proves a document-flow capability with multiple outputs can be surfaced through the Persona Runtime UI

### Stable checkpoint after this pass

* Persona Runtime multi-step button: added
* `run multi-step-demo` command: added
* doc-demo flow routed through Persona Runtime: working
* summary demo output hint: visible
* action-items demo output hint: visible
* runtime state update to `SUCCESS`: working
* v3 screenshot evidence: added
* GitHub main push: complete

### Evidence kept

Keep this screenshot:

* `docs/demo_assets/persona_runtime/persona_runtime_v3_multistep_demo_success.png`
