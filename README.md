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




## Governed Repair Runtime / Operator Review Loop (Latest)

Current engineering checkpoint:

```text
runtime-aggregate-convergence-v1
```

ZERO now includes a human-supervised governed repair runtime loop:

```text
governed_repair_mutation
-> MutationBoundary risk classification
-> approval / verification policy
-> governed repair transaction
-> awaiting_review
-> scheduler review_queue
-> operator approve / reject
-> authorized / blocked lifecycle
-> runtime resume semantics
-> control API surface
```

What changed:

- repair-generated mutations now route through boundary risk policy
- approval-required transactions stop at `awaiting_review`
- approved reviews transition toward `authorized`
- rejected reviews transition to `blocked`
- scheduler exposes a native `review_queue`
- scheduler exposes `get_review_queue()`, `approve_review_item(...)`, and `reject_review_item(...)`
- `ZeroControlAPI` exposes review inbox actions without exposing scheduler internals

Important boundaries:

```text
review queue != UI
approval != hidden execution
operator action != unrestricted mutation
control API != scheduler rewrite
```

Current validation checkpoint:

```text
1973 passed, 162 subtests passed
```

This moves ZERO from a governed repair transaction substrate toward a human-supervised autonomous engineering runtime: repair actions can now be risk-classified, queued for review, surfaced to an operator, approved or rejected, persisted, and resumed through controlled lifecycle semantics.

------------------------------------------------------------------------



## Recovery Policy Topology Landing (Latest)

Current engineering checkpoint:

```text
recovery-policy-topology-landing-v1
```

ZERO now supports an opt-in runtime recovery gate topology inside the governed repair execution path.

Completed runtime chain:

```text
governed_repair_mutation step
-> governed repair API
-> repair transaction execution bridge
-> governed repair execution
-> runtime_recovery_gate_hook
-> recovery execution contract
-> recovery approval
-> recovery dry-run
-> recovery commit gate
-> allow / block mutation execution
```

What changed:

- added `core/runtime/runtime_recovery_gate_hook.py`
- added optional `gate_hook` support to governed repair execution
- added `use_runtime_recovery_gate=True` as an opt-in execution flag
- passed the recovery gate option through the governed repair API and execution bridge
- connected the `governed_repair_mutation` step handler to the runtime recovery gate option
- locked the recovery command lifecycle with a command-dispatch regression test

Important boundaries:

```text
recovery gate != mutation executor
approval / dry-run / commit gate != step handler logic
command dispatch != governed repair execution
scheduler / planner / agent remain uncoupled
```

Current validation checkpoint:

```text
493 passed
503 passed
```

This moves ZERO from having recovery governance modules beside the runtime to having a recovery policy topology that can actually guard governed repair execution before mutation is allowed.

------------------------------------------------------------------------

## Governed Runtime Resume / Rollback Recovery Chain (Latest)

Current engineering checkpoint:

```text
operator-review-runtime-resume-rollback-v1
```

ZERO now includes a governed operator review path that can resume runtime execution and recover from verification failure through rollback backup evidence.

Completed runtime chain:

```text
operator command
-> command dispatch
-> control API review action
-> scheduler review state transition
-> audit event
-> execution link evidence
-> runtime resume
-> mutation execution
-> verification failure detection
-> rollback decision
-> backup snapshot fallback
-> restore execution
-> rollback result evidence
```

What changed:

- added `core/system/command_dispatch.py` for semantic operator review commands
- added review audit persistence through `core/audit/review_audit.py`
- added review-to-execution evidence linking through `core/audit/review_execution_link.py`
- connected approve / reject command dispatch to `ZeroControlAPI` review actions
- confirmed approve transitions review tasks into resumable runtime state
- confirmed `resume_task(...)` moves approved work back to queued execution
- confirmed `run_one(...)` can execute a resumed mutation step and land a workspace artifact
- fixed scheduler review lookup fallback when `_load_task` is unavailable
- fixed rollback restore fallback from `backup_snapshot` into `repair_context.rollback.per_file`
- confirmed rollback can restore a mutated file from backup snapshot evidence

Validated chain:

```text
approve review
-> resume_task
-> queued
-> run_one
-> write_file
-> artifact landing
-> verify failure rollback trigger
-> restore from backup snapshot
-> restored_files evidence
```

Important boundaries:

```text
operator command != shell execution
review approval != unrestricted mutation
runtime resume != hidden approval
verification failure != silent failure
rollback snapshot != new mutation authority
rollback restore != scheduler rewrite
```

Current validation checkpoint:

```text
1973 passed, 162 subtests passed
```

This moves ZERO from reviewable repair transactions toward a controlled autonomous engineering runtime where operator approval, runtime continuation, mutation landing, verification failure, rollback recovery, and evidence persistence are all part of one inspectable execution chain.

------------------------------------------------------------------------

## Runtime Aggregate Convergence / Evidence Kernel

Current engineering checkpoint:

```text
runtime-aggregate-convergence-v1
```

This branch adds ZERO's deterministic runtime aggregate and evidence substrate.
It does not connect new runtime contracts directly into `scheduler.py`, `agent_loop.py`, or `step_executor.py`.

The completed runtime primitive chain is:

```text
RuntimeExecutionGraph
-> RuntimeOperation
-> RuntimeTransaction
-> ExecutionPlan
-> ExecutionPlanSnapshot
-> ExecutionReplayRecord
-> ExecutionAuditRecord / ExecutionAuditTrail
-> RollbackVerificationRecord
-> RuntimeEvidenceBundle
-> RuntimeEvidenceSerializer
-> RuntimeEvidenceStore / InMemoryRuntimeEvidenceStore
```

The layer provides:

- deterministic dependency topology
- operation and transaction contracts
- execution plan identity
- immutable plan snapshots
- replay verification records
- audit trail evidence
- rollback-order verification
- portable evidence bundles
- canonical JSON serialization
- persistence boundary abstraction with an in-memory store

Important boundaries:

```text
contract != scheduler action
replay verification != tool rerun
audit evidence != execution authority
rollback verification != rollback execution
persistence boundary != sqlite/file backend
serialization != networking
```

Current validation checkpoint:

```text
tests/run_regression_contracts.py: ALL PASS, 49 test files
```

This checkpoint moves ZERO closer to a deterministic runtime kernel substrate: execution plans can be represented, snapshotted, verified, audited, rollback-checked, bundled, serialized, and stored behind a boundary before any future runtime integration is allowed.

------------------------------------------------------------------------


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
    python tests/run_regression_contracts.py

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
Runtime Repair Transaction / Governance Kernel: ✔ Governed cognition/report layer stabilized\
Runtime Aggregate Convergence / Evidence Kernel: ✔ Contract layer sealed\
Governed Repair Runtime / Operator Review Loop: ✔ Human-supervised review loop wired
Operator Review Runtime Resume / Rollback Recovery Chain: ✔ Governed resume, mutation landing, and rollback restore validated

Current phase:\
→ recovery policy topology has landed into governed repair execution; operator review, runtime resume, mutation landing, verification failure rollback, and backup-snapshot restore remain wired

Next stage:\
→ recovery gate evidence hardening and operator-visible gate summaries, without bypassing control API, review gates, or execution boundaries

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
