# ZERO

Local-first engineering agent prototype with a controllable CLI surface.

ZERO is a local-first agent system focused on controllable task execution, runtime visibility, model-selectable CLI operation, and incremental stabilization of an inspectable runtime stack.

It is being built as an engineering-oriented control surface rather than a consumer chatbot UI. The current emphasis is on local execution, inspectable runtime state, task lifecycle control, practical CLI-based operation, and keeping the core agent path observable while the system is being hardened.

## Current Focus

- Local-first execution
- Runtime visibility
- Controllable task flow
- Model-selectable launch behavior
- CLI-based task and agent control
- Runtime stabilization through layered smoke validation

## What’s Working Now

### Dual-mode CLI

- Interactive mode:
  - `python app.py`
- One-shot command mode:
  - `python app.py <command>`

### Runtime visibility

- `python app.py runtime`
- `python app.py health`

### Task lifecycle commands

- `task list`
- `task show <task_id>`
- `task result <task_id>`
- `task open <task_id>`
- `task delete <task_id>`
- `task purge finished|failed|all`

### Model / plugin override from CLI

- `--model`
- `--plugin`

### Cleaner one-shot CLI output

- Boot banners are suppressed in one-shot command mode

### Improved task result tracking

- Task results can now be inspected from CLI instead of only raw state files

### Layered smoke validation

The project now includes direct smoke coverage for the main execution path instead of relying only on ad hoc manual checks.

Current validation layers include:

- tool layer smoke
- runtime smoke
- executor smoke
- scheduler smoke

## Current Validation Commands

### Tool layer

```powershell
python tests/run_tool_layer_smoke.py
```

### Runtime layer

```powershell
python tests/run_runtime_smoke.py
```

### Executor direct smoke

```powershell
python tests/test_executor_smoke.py
```

### Scheduler direct smoke

```powershell
python tests/test_scheduler_smoke.py
```

## Current Stabilization Milestone

Current milestone:

**Mainline Stabilization v1**

This stage is focused on making the inner execution path less fragile before pushing farther into broader capability expansion.

Completed in this stage:

- tool layer first-pass stabilization
- step executor first-pass outer-envelope stabilization
- step handlers first-pass normalization
- executor first-pass internal responsibility cleanup
- scheduler first-pass internal responsibility cleanup
- smoke entrypoints for tool layer, runtime, executor, and scheduler

This means the current repository is no longer just “it seemed to work once.”  
It now has a repeatable validation path for the main local execution chain.

## Why This Matters

ZERO is no longer just an internal task runtime prototype.

It now has a more usable operator-facing control layer for:

- inspecting runtime configuration
- selecting model/plugin at launch
- executing local tasks
- viewing task results and artifacts
- managing task lifecycle from CLI
- verifying that core execution paths still work after internal changes

The practical value of this stage is not only more features.  
It is that the inner stack is becoming easier to change without blindly breaking the mainline.

## Quick Start

### Interactive mode

```powershell
python app.py
```

### Runtime inspection

```powershell
python app.py runtime
python app.py health
```

### Chat from CLI

```powershell
python app.py chat "hello"
```

### One-shot task execution example

```powershell
python app.py ask "Create a demo.txt file with content demo test, then read it back" --model llama3.1:latest
```

### Inspect task results

```powershell
python app.py task list
python app.py task result <task_id>
```

### Run smoke validation

```powershell
python tests/run_tool_layer_smoke.py
python tests/run_runtime_smoke.py
python tests/test_executor_smoke.py
python tests/test_scheduler_smoke.py
```

## Example Command Set

### Task control

```powershell
python app.py task list
python app.py task show <task_id>
python app.py task result <task_id>
python app.py task open <task_id>
python app.py task delete <task_id>
python app.py task purge finished
```

### Runtime / model control

```powershell
python app.py runtime
python app.py health
python app.py chat "hello" --model llama3.1:latest
python app.py chat "hello" --plugin local_ollama
python app.py ask "Create an i.txt file with content plugin test, then read it back" --model llama3.1:latest
```

## Demo Flow

```powershell
python app.py runtime
python app.py chat "hello"
python app.py ask "Create a demo.txt file with content demo test, then read it back" --model llama3.1:latest
python app.py task list
python app.py task result <task_id>
```

## Testing / Validation Flow

Recommended current validation sequence:

```powershell
python tests/test_executor_smoke.py
python tests/test_scheduler_smoke.py
python tests/run_tool_layer_smoke.py
python tests/run_runtime_smoke.py
```

This sequence is the current shortest path for checking whether recent internal changes broke the main local execution chain.

## Positioning

ZERO is currently best described as:

**A local-first engineering agent prototype with a controllable CLI surface.**

This means the project is currently optimized for:

- local execution
- inspectable runtime state
- operator-facing command control
- practical task execution
- model-selectable launch behavior
- incremental hardening of the execution stack

It is not yet primarily focused on:

- polished end-user UI
- broad enterprise packaging
- full multi-environment deployment
- large-scale public distribution

## Project Direction

The broader direction is to keep ZERO as a reusable agent core with controllable outer layers, rather than hard-coding it into a single narrow workflow.

That means:

- core execution should remain modular
- model choice should remain swappable
- task control should remain visible and inspectable
- future interfaces can be layered on top of the CLI control surface
- validation should remain repeatable as the runtime becomes more capable

## Status

Current status:

**CLI control surface + stabilized inner execution path**

What this repository can currently demonstrate with the best confidence:

- local-first CLI operation
- visible task lifecycle control
- inspectable runtime state
- operator-driven execution
- repeatable smoke validation of the mainline
- continued refactoring of internals without immediately losing the main execution path

## Repository Structure

High-value areas to look at first:

- `app.py`
- `core/tasks/scheduler.py`
- `core/runtime/executor.py`
- `core/runtime/step_executor.py`
- `core/runtime/step_handlers.py`
- `core/tools/tool_registry.py`
- `core/tools/file_tool.py`
- `core/tools/workspace_tool.py`
- `tests/run_tool_layer_smoke.py`
- `tests/run_runtime_smoke.py`
- `tests/test_executor_smoke.py`
- `tests/test_scheduler_smoke.py`

## Demo Asset

Recommended current demo file:

`zero_cli_runtime_task_flow_demo_2026-04-12.mp4`

## Notes

This repository is currently strongest as a technical prototype aimed at:

- local agent control
- engineering workflow experimentation
- task runtime inspection
- operator-driven execution
- stabilization of a reusable local agent core

If you are looking for a polished end-user product, this repository is not there yet.

If you are looking for a local-first agent prototype with visible control surfaces, practical CLI execution, and a mainline that can now be smoke-tested in layers, this is the current direction.
