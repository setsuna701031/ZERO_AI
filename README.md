# ZERO

**Local-first engineering agent prototype with a controllable CLI surface.**

ZERO is a local-first agent system focused on controllable task execution, runtime visibility, and model-selectable CLI operation.

It is being built as an engineering-oriented control surface rather than a consumer chatbot UI. The current emphasis is on local execution, inspectable runtime state, task lifecycle control, and practical CLI-based operation.

## Current Focus

- Local-first execution
- Runtime visibility
- Controllable task flow
- Model-selectable launch behavior
- CLI-based task and agent control

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

## Why This Matters

ZERO is no longer just an internal task runtime prototype.

It now has a more usable operator-facing control layer for:
- inspecting runtime configuration
- selecting model/plugin at launch
- executing local tasks
- viewing task results and artifacts
- managing task lifecycle from CLI

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

### One-shot task execution example
```bash
python app.py ask "Create a demo.txt file with content demo test, then read it back" --model llama3.1:latest
```

### Inspect task results
```bash
python app.py task list
python app.py task result <task_id>
```

## Example Command Set

### Task control
```bash
python app.py task list
python app.py task show <task_id>
python app.py task result <task_id>
python app.py task open <task_id>
python app.py task delete <task_id>
python app.py task purge finished
```

### Runtime / model control
```bash
python app.py runtime
python app.py health
python app.py chat "hello" --model llama3.1:latest
python app.py chat "hello" --plugin local_ollama
python app.py ask "Create an i.txt file with content plugin test, then read it back" --model llama3.1:latest
```

## Demo Flow

```bash
python app.py runtime
python app.py chat "hello"
python app.py ask "Create a demo.txt file with content demo test, then read it back" --model llama3.1:latest
python app.py task list
python app.py task result <task_id>
```

## Positioning

ZERO is currently best described as:

**A local-first engineering agent prototype with a controllable CLI surface.**

This means the project is currently optimized for:
- local execution
- inspectable runtime state
- operator-facing command control
- practical task execution
- model-selectable launch behavior

It is **not yet** primarily focused on:
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

## Status

Current milestone:

**CLI Control Surface v1**

Completed in this stage:
- dual-mode CLI
- runtime / health inspection
- task lifecycle control commands
- model/plugin override from CLI
- local ask/task execution flow
- task result inspection
- working CLI demo flow

## Demo Asset

Recommended current demo file:

`zero_cli_runtime_task_flow_demo_2026-04-12.mp4`

## Notes

This repository is currently strongest as a technical prototype aimed at:
- local agent control
- engineering workflow experimentation
- task runtime inspection
- operator-driven execution

If you are looking for a polished end-user product, this repository is not there yet.
If you are looking for a local-first agent prototype with visible control surfaces and practical CLI execution, this is the current direction.
