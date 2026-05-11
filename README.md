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



## Runtime Repair Transaction / Governance Kernel

Current engineering checkpoint:

```text
runtime-repair-transaction-layer
```

This branch adds ZERO's governed repair transaction path: a deterministic, reviewable, replayable, and policy-gated runtime layer around repair and self-modification workflows.

The latest completed chain is:

```text
transaction
-> preflight
-> sandbox apply
-> diff snapshot
-> human review
-> commit token
-> immutable commit intent
-> execution lease
-> final precheck
-> isolated temp commit
-> commit artifact
-> audit bundle
-> replay
-> reproducibility verification
-> lineage graph
-> knowledge snapshot
-> knowledge index
-> candidate retrieval
-> candidate explanation
-> read-only recommendation draft
-> recommendation review
-> recommendation provenance
-> risk assessment
-> decision trace
-> policy evaluation
-> governance report
```

Important boundaries:

```text
governance != execution
advisory != authority
recommendation != mutation
policy evaluation != scheduler action
replay != scheduler resume
knowledge retrieval != auto-repair
```

The current layer is intentionally controlled:

```text
NO direct formal workspace mutation
NO automatic scheduler execution
NO recommendation auto-apply
NO hidden shell execution
NO unrestricted self-modification
```

Current validation checkpoint:

```text
692 passed
```

This checkpoint moves ZERO beyond a repair-capable runtime into a governed engineering runtime substrate: repair actions can be previewed, reviewed, authorized, replayed, traced, risk-assessed, policy-checked, and summarized before any future controlled mutation path is allowed.

------------------------------------------------------------------------


## Patch Runtime Safety (Latest)

ZERO now includes a governed patch runtime boundary with:

- preflight analysis
- dependency/conflict detection
- transaction metadata
- backup snapshot
- atomic multi-file apply
- verify / commit boundary
- rollback recovery
- regression seal

Current runtime flow:

```text
planned
-> applied
-> verifying
-> committed
```

Failure path:

```text
planned
-> applied
-> verifying
-> rollback
-> failed
```

The runtime preserves:

```text
preflight metadata
transaction metadata
verify metadata
rollback evidence
```

while keeping:

```text
guard = gate
executor = execution
verify = boundary
transaction = state
```

separated to avoid responsibility collapse inside `scheduler.py`.


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
    python tests/test_apply_patch_transaction_layer.py
    python tests/test_step_executor.py

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
L5 Controlled Draft Workflow: ✔ Complete\
Runtime Repair Transaction / Governance Kernel: ✔ Governed cognition/report layer stabilized

Current phase:\
→ runtime transaction safety + verification boundary sealed

Next stage:\
→ patch preview subsystem, governance report export, then controlled persistence/mutation stages

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
