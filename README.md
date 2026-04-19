# ZERO

ZERO is a local-first engineering agent prototype built for controllable execution, explicit task flow, and inspectable runtime behavior.

Instead of treating the agent as a black box, ZERO is being developed as an engineering-oriented control surface: task progression can be inspected, runtime state can be checked, CLI behavior is explicit, and file-producing workflows can be validated through the official task lifecycle.

This repository is currently aimed at engineers, builders, and serious operators who care about:

- local-first execution
- controllable task flow
- inspectable runtime state
- explicit CLI control
- task lifecycle visibility
- reproducible engineering checkpoints

---

## Tagline

**A local-first engineering agent with controllable task flow, inspectable runtime state, and explicit CLI-based operation.**

---

## What ZERO Is

ZERO is not being positioned as a polished consumer chatbot.

The current system is better understood as:

- a local-first task-and-agent runtime
- a controllable CLI surface for creating, running, inspecting, and validating tasks
- an execution stack that is being hardened through repeatable engineering checkpoints
- an engineering-first prototype designed to make mainline behavior easier to inspect instead of hiding it

This means the current emphasis is on:

- execution control
- runtime visibility
- task persistence
- result inspection
- artifact tracking
- operator clarity over UI polish

---

## Current Focus

- Local-first execution
- Runtime visibility
- Controllable task flow
- CLI-based task and agent control
- Model/plugin-selectable launch behavior
- Mainline stabilization
- Document-task execution through the official task lifecycle
- Explicit document-task CLI entry

---

## What Is Working Now

### 1. Dual-mode CLI

Interactive mode:

```bash
python app.py
```

One-shot command mode:

```bash
python app.py <command>
```

### 2. Runtime visibility

```bash
python app.py runtime
python app.py health
```

### 3. Task lifecycle commands

```bash
python app.py task list
python app.py task show <task_id>
python app.py task result <task_id>
python app.py task open <task_id>
python app.py task delete <task_id>
python app.py task retry <task_id>
python app.py task rerun <task_id>
python app.py task purge finished
python app.py task purge failed
python app.py task purge all
```

### 4. Model / plugin override from CLI

```bash
python app.py chat "hello" --model llama3.1:latest
python app.py chat "hello" --plugin local_ollama
python app.py ask "Create a demo.txt file with content demo test, then read it back" --model llama3.1:latest
```

### 5. Cleaner one-shot CLI output

Boot banners are suppressed in one-shot command mode so task output and runtime inspection are easier to read.

### 6. Task result visibility

Task results can be inspected from CLI instead of requiring direct manual reading of raw state files.

### 7. Document task mainline integration

Document workflows are no longer limited to a direct/demo path.

Validated document tasks now work through the official task lifecycle:

- `task create`
- `task submit`
- `task run`
- `task result`
- `task show`

Validated task goals include:

```bash
python app.py task create "summarize input.txt into summary.txt"
python app.py task create "read input.txt and extract action items into action_items.txt"
```

### 8. Explicit document-task CLI entry

Document task creation now also has cleaner CLI entrypoints:

```bash
python app.py task doc-summary input.txt summary_cli.txt
python app.py task doc-action-items input.txt action_items_cli.txt
```

These commands create official tasks through the normal task system instead of relying only on free-form natural-language task goals.

---

## Why the Document Task Work Matters

This is one of the most important current checkpoints in the repository.

The system now demonstrates that a file-processing workflow can move through the official task lifecycle instead of only through a narrow direct shortcut.

That means the following chain has been validated for document tasks:

- task creation
- scheduling
- execution
- result reporting
- artifact persistence
- task inspection

This is a stronger engineering checkpoint than “the planner can propose the steps,” because it proves the mainline can actually carry the task to completion.

---

## Current Validation Layers

The project includes layered validation for the main execution path:

- tool layer smoke
- runtime smoke
- executor smoke
- scheduler smoke

Current validation commands:

```bash
python tests/run_tool_layer_smoke.py
python tests/run_runtime_smoke.py
python tests/test_executor_smoke.py
python tests/test_scheduler_smoke.py
```

---

## Quick Start

### Interactive mode

```bash
python app.py
```

### Runtime inspection

```bash
python app.py runtime
python app.py health
```

### Chat from CLI

```bash
python app.py chat "hello"
```

### Ask from CLI

```bash
python app.py ask "Create a demo.txt file with content demo test, then read it back"
```

### Inspect task results

```bash
python app.py task list
python app.py task show <task_id>
python app.py task result <task_id>
```

### Run smoke validation

```bash
python tests/run_tool_layer_smoke.py
python tests/run_runtime_smoke.py
python tests/test_executor_smoke.py
python tests/test_scheduler_smoke.py
```

---

## Example Command Set

### Runtime / model control

```bash
python app.py runtime
python app.py health
python app.py chat "hello" --model llama3.1:latest
python app.py chat "hello" --plugin local_ollama
```

### Task control

```bash
python app.py task list
python app.py task show <task_id>
python app.py task result <task_id>
python app.py task open <task_id>
python app.py task delete <task_id>
python app.py task purge finished
```

### Document task commands

```bash
python app.py task doc-summary input.txt summary_cli.txt
python app.py task doc-action-items input.txt action_items_cli.txt
```

---

## Demo Flow

### Demo flow A — runtime and CLI control

```bash
python app.py runtime
python app.py chat "hello"
python app.py task list
```

### Demo flow B — document summary through task lifecycle

```bash
python app.py task doc-summary input.txt summary_cli.txt
python app.py task list
python app.py task submit <task_id>
python app.py task run 1
python app.py task result <task_id>
python app.py task show <task_id>
```

### Demo flow C — document action items through task lifecycle

```bash
python app.py task doc-action-items input.txt action_items_cli.txt
python app.py task list
python app.py task submit <task_id>
python app.py task run 1
python app.py task result <task_id>
```

---

## Evidence / Checkpoints

Relevant checkpoint images are being kept under:

```text
docs/images/checkpoints/
```

Current checkpoint evidence includes:

- `checkpoint_task_result_action_items_finished.png`
- `checkpoint_task_result_action_items_mainline.png`
- `checkpoint_task_result_and_show_summary_mainline.png`

These are useful for README support, devlog proof, and demo / presentation material because they show:

- CLI invocation
- finished task state
- visible final answer
- task artifact paths
- inspectable task result / show output

---

## Current Stabilization Milestones

### Mainline Stabilization Pass

Completed in this stage:

- tool layer first-pass stabilization
- step executor first-pass outer-envelope stabilization
- step handlers first-pass normalization
- executor first-pass internal responsibility cleanup
- scheduler first-pass internal responsibility cleanup
- smoke entrypoints for tool layer, runtime, executor, and scheduler

### Scheduler Consolidation Pass

Completed in this stage:

- queue sync helper extraction
- dispatch helper extraction
- repo/runtime sync helper extraction
- trace helper extraction
- simple runner helper extraction
- path helper extraction
- command / LLM helper extraction

### Document Flow Repair Pass

Validated in this stage:

- document flow preserved requested output path
- LLM file-content injection worked
- `use_previous_text` write-back worked
- shared output artifacts were written

### Document Task Mainline Integration Pass

Validated in this stage:

- summary task mainline flow: working
- action-items task mainline flow: working
- official task lifecycle integration: working
- `task result` and `task show` reporting: working

### Document Task CLI Entry Pass

Validated in this stage:

- explicit summary task CLI entry: working
- explicit action-items task CLI entry: working
- explicit CLI entry preserves official task lifecycle behavior

---

## Repository Orientation

Key areas in the current system include:

- `app.py` — CLI entry surface
- `core/planning/` — planning / replanning layer
- `core/runtime/` — runtime execution layer
- `core/tasks/` — scheduler, task persistence, task lifecycle
- `docs/devlog.md` — engineering progress records
- `docs/images/checkpoints/` — checkpoint evidence images

---

## Positioning

ZERO is currently best described as:

**A local-first engineering agent prototype with a controllable CLI surface.**

Right now the system is optimized for:

- local execution
- inspectable runtime state
- operator-facing command control
- practical task execution
- result and artifact inspection
- incremental hardening of the execution stack

It is not yet primarily focused on:

- polished end-user UI
- mass-market onboarding
- consumer-first chat experience
- broad workflow packaging
- one-click productized distribution

---

## Current State in One Sentence

This version is already strong enough to demo, explain, validate, and be understood by engineers.

---

## Notes

The current repository should be read as an engineering checkpoint, not as a finished end-user product.

The most important value right now is not surface polish. It is that the mainline is becoming more observable, more controllable, and less fragile while capability is being added.
