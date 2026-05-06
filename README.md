# ZERO

ZERO is a local-first AI runtime system for executing real-world tasks.

It is **NOT a chatbot**.\
It is **NOT an API wrapper**.

ZERO turns a request into a structured execution pipeline:

    prompt → plan → decision → tool execution → result → trace

------------------------------------------------------------------------

## 🎬 Demo (Start Here)

Main demo:

    demos/00_zero_task_to_github_draft_no_api_no_push.mp4

Core flow:

    web_search → file_write → github_draft_bundle

ZERO actually:

1.  Searches external information (mock / safe)
2.  Generates structured output
3.  Writes files to workspace
4.  Produces GitHub-ready draft bundle
5.  Records full execution trace
6.  Displays timeline in UI

------------------------------------------------------------------------



## 🎬 Latest Demo

### Autonomous Repair Loop

New demo:

```text
demos/zero-autonomous-code-repair-demo.mp4
```

This demo shows ZERO performing a runtime-aware autonomous repair workflow:

```text
execution failure
-> semantic reasoning
-> repair routing
-> code-chain diff generation
-> patch apply
-> verification
-> successful rerun
```

The repair flow demonstrates:

- semantic-aware error interpretation
- CODE CHAIN diff generation
- runtime trace visibility
- planner-driven repair routing
- patch verification
- controlled local execution
- replayable execution trace

Important:

- local-first execution
- controlled repair workflow
- traceable execution lifecycle
- not a hidden black-box repair flow


## What ZERO Does

ZERO does not just generate answers.

It executes real steps, produces real outputs, and records exactly how
the result was created.

Core capabilities:

-   Task lifecycle management
-   Agent execution loop
-   Decision-aware execution
-   Tool orchestration
-   Persistent execution trace
-   Replayable runtime history

------------------------------------------------------------------------

## GitHub Draft Workflow (Safe)

ZERO uses a controlled output model:

    workspace/github_outbox/

Generated files:

-   commit_message.txt
-   pr_description.md
-   devlog_entry.md
-   publish_plan.md

Important:

-   No API calls
-   No push
-   No PR creation
-   No external side effects

This is **controlled automation**, not autonomous GitHub control.

------------------------------------------------------------------------

## Execution Trace (Core Concept)

ZERO makes AI execution observable.

Each task records:

-   planned steps
-   decisions
-   tool calls
-   arguments
-   execution status (success / denied / error / validation)
-   timestamps
-   outputs

UI Timeline Example:

    Step 1: web_search
    Step 2: file_write
    Step 3: github_draft_bundle
    Result

------------------------------------------------------------------------

## Replay

Replay previous execution:

    runtime-replay

Replay does NOT:

-   execute tools again
-   modify files
-   create new outputs

It answers:

> What did the system actually do?

------------------------------------------------------------------------

## Run Demo

    run hybrid-demo

Check state:

    runtime-status

Replay:

    runtime-replay

Run tests:

    python tests/run_l4_tool_layer_smoke.py
    python tests/run_l4_tool_decision_smoke.py
    python tests/run_l5_tool_decision_core_smoke.py
    python tests/run_l5_external_draft_tools_smoke.py

------------------------------------------------------------------------

## Architecture (Simplified)

**Core Runtime** - Scheduler - Agent Loop - Task Runtime

**Decision Layer** - tool_decision_policy - decision-aware execution

**Tool Layer** - file_read - file_write - web_search (draft) -
github_draft_bundle

**Display Layer** - Persona UI - Execution timeline - Trace replay

------------------------------------------------------------------------

## Project Status

L4 Tool Layer: ✔ Complete\
L5 Decision Core: ✔ Complete\
L5 Controlled Draft Workflow: ✔ Complete

Current phase:\
→ stabilization + reproducibility + demo packaging

Next stage:\
→ controlled automation (L5 expansion)

------------------------------------------------------------------------

## What ZERO Is NOT

-   Not a chatbot
-   Not a prompt wrapper
-   Not a simple script runner
-   Not uncontrolled autonomous AI

------------------------------------------------------------------------

## Why This Matters

Most AI systems hide execution.

ZERO exposes it.

This makes AI:

-   debuggable
-   verifiable
-   reproducible
-   controllable

------------------------------------------------------------------------

## Summary

ZERO is an AI runtime system that turns intent into real execution, with
full visibility and control.
