# ZERO AI

ZERO is a local-first autonomous engineering system.

It does not just respond.  
It observes, decides, executes, writes files, and preserves evidence.

**Requirement → Planning → Execution → Verification → Autonomous Loop**

ZERO is not a chatbot wrapper.  
It is a controllable local agent platform for engineering workflows.

\---

## Current Stable Baseline: L4 Replan Suggestion Gate

ZERO's L4 mainline is now closed with a controlled recovery gate.

Validated end-to-end flow:

```text
fail → suggestion → preview → dry-run → manual approve → queued
```

### What this proves

* failed tasks can produce structured repair suggestions
* suggestions are represented as an actions schema, not only free text
* preview can inspect the proposed action before execution
* dry-run can simulate the proposed action
* manual approval is required before the action is queued
* suggestion does not automatically replan or execute by itself
* existing L3/L4 preview/control smoke paths remain intact

### Safety boundary

The current L4 recovery gate is intentionally protective:

```text
suggestion = propose only
preview = inspect only
dry-run = simulate only
approve = explicit manual gate
queued = only after approval
```

Automatic replanning is not enabled at this baseline.

### Validation proof

Confirmed smoke coverage:

```text
run\_replan\_suggestion\_smoke.py -> ALL PASS
run\_auto\_replan\_suggestion\_smoke.py -> L4 smoke PASS
run\_replan\_suggestion\_actions\_e2e\_smoke.py -> E2E PASS
run\_replan\_control\_preview\_smoke.py -> ALL PASS
```

### Git checkpoint

```text
3994c4f  Stabilize L4 replan suggestion gate
2f05da0  Ignore test workspace runtime files
```

This is the stable L4 baseline before opening true L5 automatic replanning.

\---

## Current Highlight: L5 Autonomous Execution

ZERO now includes a minimal autonomous world loop:

```text
external event → world\_state → background observe loop → action → real file output
```

This means ZERO can react to external state without manual CLI input.

### Evidence Pack

The current L5 evidence pack is stored under:

```text
docs/demo\_assets/
```

Recommended assets:

```text
l5\_control\_api\_world\_trigger\_result.png
l5\_auto\_output\_file\_updated.png
l5\_control\_api\_task\_execution\_trace.png
l5\_auto\_output\_sample.txt
```

### What this proves

* external events can be injected through the platform control API
* ZERO detects world\_state changes in a background loop
* ZERO performs an action automatically
* a real output file is written to disk
* the trigger is cleared after execution
* execution can be inspected through task/runtime artifacts

### Main Screenshot

!\[L5 Control API world trigger result](docs/demo\_assets/l5\_control\_api\_world\_trigger\_result.png)

### Output File Proof

!\[L5 auto output file updated](docs/demo\_assets/l5\_auto\_output\_file\_updated.png)

Sample output:

```text
L5 auto triggered
timestamp=2026-04-28T03:52:03Z
```

\---

## Platform Control API

ZERO now exposes a small platform-facing API:

```python
from core.control.control\_api import Zero

z = Zero()

z.get\_status()
z.inject\_world("demo\_trigger", {"test": True})
z.submit("Create a task that writes hello to workspace/shared/api.txt")
```

This API is the first step toward making ZERO usable as a platform instead of only a CLI tool.

### Current API capabilities

* boot the ZERO system
* inspect runtime/task status
* inject world\_state events
* submit semantic tasks
* access task state
* bridge external scripts/tools into ZERO

\---

## Core Showcase: Mini Build Agent

```bash
python main.py mini-build-demo
```

This demo shows a complete engineering loop:

* read a requirement document
* generate planning outputs
* generate Python code
* execute the generated script
* write result artifacts
* verify the final output

### Output Artifacts

```text
workspace/shared/project\_summary.txt
workspace/shared/implementation\_plan.txt
workspace/shared/acceptance\_checklist.txt
workspace/shared/number\_stats.py
workspace/shared/stats\_result.txt
```

### What this proves

* not just text generation
* real file outputs
* code generation and execution
* result verification

Demo assets:

```text
demos/08\_mini\_build\_demo/
```

\---

## Requirement Demo

```bash
python main.py requirement-demo
```

Demonstrates:

* requirement input
* planning output
* multi-artifact generation
* result inspection

### Output Artifacts

```text
workspace/shared/project\_summary.txt
workspace/shared/implementation\_plan.txt
workspace/shared/acceptance\_checklist.txt
```

Demo assets:

```text
demos/07\_requirement\_demo/
```

\---

## Persona Runtime Window

ZERO includes a local Persona Runtime window for showing runtime state through a visual UI.

This window is not only a character display. It shows:

* current runtime state
* command/chat interaction
* execution-demo result
* task artifact paths
* runtime summary and output hints

### Visual Ready

!\[Persona Runtime visual ready](docs/demo\_assets/persona\_runtime/persona\_runtime\_v1\_visual\_ready.png)

### Execution Demo Success

!\[Persona Runtime execution demo success](docs/demo\_assets/persona\_runtime/persona\_runtime\_v2\_execution\_demo\_success.png)

### What this proves

* the UI is connected to runtime state
* execution-demo can update the persona status to SUCCESS
* output artifacts such as `workspace/shared/hello.py` are surfaced in the UI
* task IDs and execution traces are visible for inspection

\---

## Capabilities

* local-first runtime
* requirement understanding
* planning system
* code generation
* tool execution
* output verification
* task lifecycle control
* background world\_state observe loop
* platform control API
* controlled AgentLoop observe-decide-act path
* controlled L4 replan suggestion gate
* artifact visibility
* runtime trace inspection

\---

## What Makes ZERO Different

ZERO is not an LLM wrapper.

ZERO:

* executes tasks, not just responds
* produces real artifacts
* exposes runtime state
* verifies outputs through execution
* can react to external world\_state events
* is structured as a local platform core, not a single-purpose demo

It demonstrates a complete engineering agent loop with a path toward autonomous platform behavior.

\---

## Quick Start

### Show help

```bash
python main.py help
```

### Check runtime

```bash
python main.py runtime
```

### Run validation

```bash
python main.py smoke
```

### Run demos

```bash
python main.py doc-demo
python main.py requirement-demo
python main.py execution-demo
python main.py mini-build-demo
```

\---

## Core CLI

```bash
python app.py runtime
python app.py health
python app.py task list
python app.py task show <task\_id>
python app.py task result <task\_id>
python app.py task loop <task\_id> \[max\_cycles]
```

### Document tasks

```bash
python app.py task doc-summary input.txt summary.txt
python app.py task doc-action-items input.txt action\_items.txt
```

\---

## Controlled AgentLoop Loop

ZERO includes a controlled minimal AgentLoop path:

```bash
python app.py task loop <task\_id> \[max\_cycles]
```

This path is intentionally explicit. It does not replace the default scheduler or `task run` behavior.

It supports a safe observe-decide-act cycle:

* observe current task/runtime result
* decide whether to finish, continue, replan, fail, or stop on guard/block conditions
* run the next tick only when the decision is `continue`
* stop safely on `finish`, `replan`, `fail`, `blocked`, or `max\_cycles\_reached`

### What this proves

* AgentLoop records observe/decide metadata
* task loop execution can run until terminal state under a max-cycle guard
* CLI access is controlled through an explicit command
* default task execution remains unchanged

\---

## Multi-task Demo

ZERO includes a repeatable multi-task demo scenario:

```bash
python tests/run\_multi\_task\_demo\_smoke.py
```

This demo creates three tasks:

* one normal task that writes and verifies `MULTI\_DEMO\_A`
* one normal task that writes and verifies `MULTI\_DEMO\_B`
* one intentionally failing verification task

The expected result is that the two normal tasks finish successfully while the intentional failure moves into a safe repair state without blocking the queue.

!\[Multi-task demo smoke all pass](docs/images/checkpoints/checkpoint\_multi\_task\_demo\_smoke\_all\_pass.png)

### What this proves

* multiple tasks can be queued and advanced together
* normal tasks can finish even when another task fails or replans
* each task has observable trace evidence
* the demo is repeatable through smoke validation

Engineering proof for the queue policy is also kept here:

!\[Queue policy failure does not block](docs/images/checkpoints/checkpoint\_queue\_policy\_failure\_does\_not\_block.png)

\---

## System Structure

```text
main.py                 unified entrypoint
app.py                  core CLI + background world loop
core/control/           platform control API
core/world/             world\_state layer
core/planning/          planner
core/runtime/           execution layer
core/tasks/             scheduler + lifecycle
tests/                  validation
demos/                  showcase assets
docs/                   devlog + checkpoints
docs/demo\_assets/       demo evidence assets
```

\---

## Current Engineering Checkpoint

ZERO's current mainline has a runtime-safe multi-task execution baseline.

Validated mainline capabilities include:

* controlled L4 recovery gate: `fail → suggestion → preview → dry-run → manual approve → queued`
* structured replan suggestion actions schema
* preview / dry-run / approve path for suggested repair actions
* manual approval boundary before queued execution
* auto replan remains disabled at the L4 baseline
* normalized handler results
* observable local traces with `step\_start`, `step\_result`, and `task\_finished`
* task-local trace ticks for cleaner inspection
* queue readiness rules that prevent `created` tasks from running before submit
* multi-task queue progression without failed/replanning tasks blocking normal tasks
* runtime artifact safety guards to prevent oversized `runtime\_state.json` / `result.json` growth
* command safety guard against self-invoking task commands such as `python app.py task run ...`
* L5 background world\_state loop through `app.py`
* platform-facing `control\_api.py`

Latest regression proof:

```bash
python app.py task create "write MAIN\_SAFE\_OK to main\_safe\_ok.txt, then verify main\_safe\_ok.txt contains MAIN\_SAFE\_OK"
python app.py task submit <task\_id>
python app.py task run 1
python app.py task run 1
python app.py task run 1
python app.py task show <task\_id>
```

Confirmed result:

* task reached `finished`
* step progress reached `3/3`
* final answer: `MAIN\_SAFE\_OK`

\---

## Current Position

ZERO is:

* local-first
* execution-oriented
* artifact-producing
* inspectable
* reproducible
* platform-oriented
* ready for controlled external event integration

Not optimized yet for:

* polished UI
* one-click install
* mass users

\---

## Recommended Next Step

The next engineering step is to open true L5 automatic replanning only after the L4 safety baseline remains stable.

Recommended boundary:

```text
manual L4 recovery gate remains the safety baseline
→ introduce auto replan behind explicit policy control
→ keep preview / dry-run / approval available as guardrails
→ validate with repeatable smoke before enabling broader automation
```

A later platform-facing step is a file watcher event source:

```text
drop file into watched folder
→ emit world\_state event
→ ZERO detects event
→ task runs automatically
→ result file is written
```

\---

## One-line Summary

ZERO is a local-first autonomous engineering platform that can turn requirements and external events into executable, verifiable results.



### Git Pipeline Replay (Core)

https://github.com/setsuna701031/ZERO\_AI/blob/main/demos/00\_git\_pipeline\_replay\_demo.mp4

ZERO analyzes real git changes, generates PR artifacts into a controlled outbox, and provides a read-only replay of the execution trace.

* No repository mutation
* Full traceability
* Replayable execution



