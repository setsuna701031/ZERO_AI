---
## 2026-05-18 - Runtime Admission Governance v0 frozen baseline

This checkpoint records `Runtime Admission Governance v0` as a frozen baseline.

### What was established

```text
Public Surface -> Connector -> Ownership Gate -> Admission Policy -> Admission Trace -> Execution Lease
```

The baseline preserves:

* default-deny admission behavior
* `request_id` / `trace_id` / `lease_id` lineage
* no scheduler, executor, mutation, recovery, or replay coupling
* no execution capability
* unchanged public behavior

### Validation confirmed

Confirmed governance / boundary pack:

```text
python -m pytest tests/test_runtime_admission_policy_contract.py tests/test_runtime_admission_trace_contract.py tests/test_runtime_execution_lease_contract.py tests/test_runtime_ownership_gate_contract.py tests/test_runtime_connector_contract.py tests/test_runtime_public_surface_contract.py tests/test_runtime_boundary_imports.py tests/test_runtime_mutation_authority_boundaries.py -q
-> 36 passed
```

Confirmed regression pack:

```text
python -m pytest tests/test_repair_chain_runtime.py tests/test_scheduler_parser_helpers.py -q
-> 80 passed
```

Total validation:

```text
116 passed
existing warning only: datetime.utcnow() deprecation warnings in core/runtime/mutation_boundary.py
```

### Baseline boundary

This checkpoint does not add:

```text
NO scheduler coupling
NO enqueue
NO execution grant
NO mutation behavior
NO recovery behavior
NO replay behavior
NO queue connection
```

## 2026-05-18 - Runtime Execution Bridge Plan v0

Added `docs/runtime_execution_bridge_plan_v0.md` as the design-only next step after Runtime Admission Governance v0.

The planned bridge structure is:

```text
Public Surface
-> Connector
-> Ownership Gate
-> Policy
-> Trace
-> Lease
-> Execution Bridge
-> Scheduler Adapter
```

This plan keeps the current default-deny baseline intact:

* no direct `submit_runtime_task()` scheduler call
* no execution logic in connector
* no scheduler logic in ownership gate
* no bypass around policy / trace / lease
* no mutation, recovery, or replay behavior
* no enqueue before a real execution grant exists

Bridge contracts to design before behavior:

* `RuntimeExecutionBridge`
* `RuntimeSchedulerAdapter`
* `RuntimeExecutionGrant`
* `RuntimeExecutionHandoffRecord`

## 2026-05-18 - Runtime Execution Grant Model v0

Added `docs/runtime_execution_grant_model_v0.md` as a docs-only contract boundary for future granted execution leases.

The model records the current default-deny state:

* Runtime Admission Governance v0 is frozen
* Execution Bridge Plan v0 is established
* execution leases remain `granted=False`
* `submit_runtime_task()` still returns `accepted_not_connected`

The grant boundary preserves these rules:

* request accepted does not mean execution granted
* policy allowed does not mean enqueued
* granted lease only permits possible handoff, not execution
* scheduler handoff must go through Execution Bridge plus Scheduler Adapter
* grants must be traceable, auditable, and revocable

The draft `RuntimeExecutionGrant` contract includes:

```text
grant_id
request_id
trace_id
lease_id
granted: bool
status
reason
authority_scope
risk_level
granted_by
expires_at
metadata
```

Version 0 remains docs-only and default-deny:

* no real `granted=True`
* no enqueue
* no execution
* no scheduler connection
* no mutation, recovery, or replay connection

Forbidden paths remain explicit:

* public surface directly calling scheduler
* connector directly enqueueing
* gate directly executing
* policy directly mutating
* bridge bypassing lease
* adapter bypassing grant
* `submit_runtime_task()` executing just because a request was accepted

## 2026-05-18 - Runtime Conditional Grant v0 design

Added `docs/runtime_conditional_grant_v0.md` as a docs-only design checkpoint for the first future conditions that could allow `granted=True`.

Current checkpoint:

* Runtime Admission Governance v0
* RuntimeExecutionGrant v0
* RuntimeGrantIssuer v0

Minimum conditional grant principles:

* only `RuntimeGrantIssuer` can produce `granted=True`
* `policy.allowed=True` is necessary but not sufficient
* `lease.granted=True` is required
* `authority_scope` cannot be `none`
* `risk_level` must be explicitly allowed
* trace / lease / grant lineage must be complete
* `granted=True` still does not mean enqueued or executed

First candidate scopes:

* `dry_run`
* `read_only`

Temporarily forbidden scopes:

* `write`
* `mutation`
* `recovery`
* `replay`
* `scheduler_enqueue`

Explicit prohibitions remain:

* `submit_runtime_task()` must not execute because a request was accepted
* connector must not enqueue directly
* ownership gate must not directly produce grants
* grant issuer must not call scheduler directly
* `granted=True` must not directly mean scheduler handoff
* Execution Bridge / Scheduler Adapter must not be bypassed

Next expected code contract:

* `RuntimeGrantEligibility`
* `RuntimeGrantIssuer.evaluate_eligibility()`
* `RuntimeGrantIssuer.issue_grant()` checks eligibility before any grant
* v0 code remains default-deny unless an explicit test mode permits an isolated `dry_run` grant

## 2026-05-18 - Runtime Scheduler Adapter + Handoff Record v0

Added contract-only adapter admission and handoff record layers behind the execution bridge.

New code contracts:

* `RuntimeSchedulerAdapter`
* `RuntimeSchedulerAdapterDecision`
* `RuntimeExecutionHandoffRecord`

The adapter only accepts a bridge decision when:

* bridge decision is accepted
* bridge status is `bridge_accepted`
* authority scope is `dry_run` or `read_only`

Accepted adapter decisions return:

```text
accepted=True
status="adapter_ready"
```

This remains non-executing:

* no scheduler import
* no enqueue
* no execute
* no mutation, recovery, or replay
* public surface / connector behavior unchanged

Handoff records preserve lineage and explicitly keep:

```text
executed=False
enqueued=False
scheduler_touched=False
```

## 2026-05-18 - Adapter to Queue Admission Bundle v0

Added contract-only queue admission behind adapter readiness.

New code contracts:

* `RuntimeQueueAdmissionDecision`
* `RuntimeQueueAdmissionController`

The queue admission controller accepts only:

* adapter decision accepted
* authority scope `dry_run` or `read_only`

Accepted queue admission returns:

```text
accepted=True
status="queue_admission_accepted"
reason="adapter_ready_for_non_executing_scope"
enqueued=False
executed=False
scheduler_touched=False
```

Rejected adapter decisions return:

```text
accepted=False
status="queue_admission_rejected"
reason="adapter_not_ready"
```

The scheduler adapter may expose queue admission through the controller, but it still does not enqueue, execute, import scheduler, or touch mutation / recovery / replay behavior.

`RuntimeExecutionHandoffRecord` now can include:

* `queue_admission_id`
* `queue_admission_status`

## 2026-05-18 - Runtime Controlled Enqueue Boundary v0

Added `docs/runtime_controlled_enqueue_boundary_v0.md` as a docs-only plan for the first future conditions that may allow `scheduler_touched=True` and `enqueued=True`.

Current stable chain:

```text
Public Surface
-> Connector
-> Ownership Gate
-> Admission Policy
-> Admission Trace
-> Execution Lease
-> Grant Eligibility
-> Grant Issuer
-> Execution Grant
-> Execution Bridge
-> Scheduler Adapter
-> Queue Admission
-> Handoff Record
```

Core boundaries remain:

* `queue_admission_accepted` does not mean enqueued
* `adapter_ready` does not mean scheduler touched
* `bridge_accepted` does not mean execution
* `grant_issued` does not mean execution
* `submit_runtime_task` accepted does not mean execution

Minimum future enqueue conditions:

* `queue_admission.accepted=True`
* `execution_grant.granted=True`
* explicit allowed `authority_scope`
* acceptable `risk_level`
* complete handoff record
* scheduler adapter is the only scheduler contact point
* an enqueue record exists
* enqueue lineage traces `request_id`, `trace_id`, `lease_id`, `grant_id`, and `queue_admission_id`

Forbidden in v0:

* mutation
* recovery
* replay
* `write` scope
* direct `scheduler_enqueue` scope pass-through
* public surface direct enqueue
* connector / gate / bridge scheduler access
* enqueue causing automatic execution

Next expected code contract:

* `RuntimeControlledEnqueueRequest`
* `RuntimeControlledEnqueueDecision`
* `RuntimeControlledEnqueueController`
* first `enqueued=True` remains non-executing and limited to `dry_run` / `read_only` queue placeholders

## 2026-05-15 - Runtime Boundary Freeze Baseline checkpoint

This checkpoint records the runtime boundary freeze baseline on `main`.

The goal was not to declare the whole Runtime fully sealed. The goal was to create a clean freeze candidate checkpoint after recovery, replay, mutation governance, evidence, audit, session reconstruction, and boundary contract validation were confirmed green together.

### What was completed

Added the runtime boundary freeze manifest:

* `docs/runtime_boundary_freeze.md`
  * records the current freeze candidate status
  * records verified regression groups
  * defines the no-new-capability rule for large runtime files
  * lists high-risk files that should not absorb more responsibilities
  * defines the next allowed work as extraction only after a green baseline

Added mutation recovery observability smoke coverage:

* `tests/test_mutation_recovery_observability_smoke.py`
  * verifies mutation recovery observability readiness
  * verifies operator-visible blocker summary behavior
  * verifies blocked readiness state propagation
  * keeps dry-run-only recovery behavior visible before mutation execution

### Runtime validation confirmed

Confirmed targeted validation:

```text
python -m pytest tests/test_mutation_recovery_observability_smoke.py -q
-> 2 passed
```

Confirmed mutation recovery / governed execution validation:

```text
python -m pytest (Get-ChildItem tests/test_mutation_*.py | ForEach-Object { $_.FullName }) tests/test_runtime_repair_transaction_to_governed_execution.py -q
-> 67 passed
```

Confirmed runtime recovery / replay validation:

```text
python -m pytest (Get-ChildItem tests/test_runtime_recovery*.py,tests/test_runtime_replay*.py -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }) -q
-> 183 passed
```

Confirmed combined recovery / replay / mutation / governed execution validation:

```text
python -m pytest (Get-ChildItem tests/test_runtime_recovery*.py,tests/test_runtime_replay*.py,tests/test_mutation_*.py -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }) tests/test_runtime_repair_transaction_to_governed_execution.py -q
-> 250 passed
```

Confirmed evidence / seal / audit validation:

```text
python -m pytest (Get-ChildItem tests/*evidence*.py,tests/*seal*.py,tests/*audit*.py -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }) -q
-> 254 passed
```

Confirmed session / reconstruction validation:

```text
python -m pytest (Get-ChildItem tests/*session*.py,tests/*lineage*.py,tests/*reconstruct*.py,tests/*provenance*.py -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }) -q
-> 40 passed
```

Confirmed runtime mainline combined validation:

```text
python -m pytest (Get-ChildItem tests/*evidence*.py,tests/*seal*.py,tests/*audit*.py,tests/*session*.py,tests/*lineage*.py,tests/*reconstruct*.py,tests/*provenance*.py,tests/test_runtime_recovery*.py,tests/test_runtime_replay*.py,tests/test_mutation_*.py -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }) tests/test_runtime_repair_transaction_to_governed_execution.py -q
-> 490 passed
```

Confirmed boundary / contract / ownership validation:

```text
python -m pytest (Get-ChildItem tests/*boundary*.py,tests/*contract*.py,tests/*ownership*.py -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }) -q
-> 1249 passed, 154 subtests passed
```

Confirmed full-suite validation after the freeze baseline commit:

```text
python -m pytest -q
-> 2009 passed, 162 subtests passed
```

### Git checkpoint

Committed and pushed on `main`:

```text
25202d6 - freeze(runtime): establish runtime boundary freeze baseline
```

### Freeze rules established

The freeze manifest establishes these rules:

```text
NO new capability should be added directly into scheduler.py, agent_loop.py, task_runtime.py, step_executor.py, or task_runner.py.
New behavior must enter through adapter, boundary, policy, evidence, or contract modules.
Runtime core changes require regression across boundary, evidence, recovery, replay, mutation, and governed execution tests.
```

### High-risk files identified

The current high-risk responsibility hotspots are:

```text
core/tasks/scheduler.py
core/agent/agent_loop.py
core/runtime/task_runtime.py
core/runtime/step_executor.py
core/runtime/task_runner.py
core/tasks/runtime_repair_apply_transaction.py
```

Observed large-file scan also showed:

```text
core/tasks/scheduler.py: 8425 lines
core/agent/agent_loop.py: 5426 lines
core/runtime/task_runtime.py: 5267 lines
core/runtime/step_executor.py: 5106 lines
core/runtime/task_runner.py: 4284 lines
core/tasks/runtime_repair_apply_transaction.py: 3818 lines
```

### Boundaries preserved

This checkpoint intentionally preserves these boundaries:

```text
freeze baseline != final runtime seal
boundary freeze != behavior rewrite
cleanup candidate != immediate extraction
adapter / policy / evidence / contract != scheduler responsibility
recovery evidence != hidden mutation authority
audit seal != execution permission
```

The checkpoint does not add:

```text
NO new capability
NO scheduler rewrite
NO agent_loop rewrite
NO direct large-file extraction
NO hidden approval
NO automatic GitHub action
NO new external side effect
```

### Why this matters

This checkpoint gives ZERO a clean runtime freeze candidate baseline.

The important result is not that the whole runtime is permanently sealed. The important result is that recovery, replay, mutation governance, evidence, audit, session reconstruction, and boundary contracts are now green together, committed, pushed, and documented as the baseline before any slimming or extraction work begins.

This reduces the risk that future cleanup accidentally changes runtime behavior or lets large files absorb more responsibilities.

### Stable checkpoint after this pass

* mutation recovery observability smoke: working
* recovery / replay regression: passing
* mutation / governed execution regression: passing
* evidence / seal / audit regression: passing
* session reconstruction regression: passing
* boundary / contract / ownership regression: passing
* full suite: passing
* runtime boundary freeze manifest: added
* freeze baseline commit: pushed to `main`
* worktree after push and full test: clean
* runtime is a freeze candidate, not yet declared fully sealed

### Evidence kept

Keep screenshots showing:

* `2 passed` for mutation recovery observability smoke
* `67 passed` for mutation / governed execution validation
* `183 passed` for recovery / replay validation
* `250 passed` for combined recovery / replay / mutation / governed execution
* `254 passed` for evidence / seal / audit
* `40 passed` for session / reconstruction
* `490 passed` for runtime mainline combined validation
* `1249 passed, 154 subtests passed` for boundary / contract / ownership
* commit `25202d6`
* `2009 passed, 162 subtests passed`
* clean `git status --short`

### Next step

Recommended next checkpoint:

```text
Runtime Freeze Report / Release Note Sync
```

Expected boundary:

```text
devlog / README status sync
-> no runtime code change
-> no scheduler extraction yet
-> full-suite result remains the authority
```

Still avoid:

```text
NO behavioral rewrite during freeze
NO large-file extraction before a dedicated plan
NO new runtime capability
NO scheduler / agent_loop responsibility growth


## 2026-05-15 - Recovery Policy Topology Landing checkpoint

This checkpoint records the landing of the runtime recovery gate topology into the governed repair execution mainline.

The goal was not to hard-code recovery policy into the repair executor. The goal was to add a clean gate adapter path so recovery approval, dry-run, execution-contract, and commit-gate checks can participate in governed repair execution without collapsing policy, execution, command dispatch, and scheduler responsibilities into one layer.

### What was completed

Added a runtime recovery gate hook adapter:

* `core/runtime/runtime_recovery_gate_hook.py`
  * builds runtime recovery execution contract evidence
  * runs recovery approval evaluation
  * runs recovery dry-run simulation
  * runs recovery commit gate evaluation
  * normalizes the result into a gate response:
    * `ok`
    * `blocked`
    * `blockers`
    * `reports`

Extended governed repair execution with an optional gate hook:

* `core/runtime/governed_repair_execution.py`
  * added `gate_hook`
  * added `use_runtime_recovery_gate`
  * resolves either a caller-provided hook or the runtime recovery gate hook
  * blocks governed repair execution before mutation if the gate returns a blocking result
  * keeps actual file writes owned by the governed mutation execution layer

Extended the API and bridge pass-through path:

* `core/runtime/governed_repair_api.py`
  * accepts `gate_hook`
  * accepts `use_runtime_recovery_gate`
  * passes both through without importing scheduler, command dispatch, or recovery internals

* `core/runtime/repair_transaction_execution_bridge.py`
  * accepts `gate_hook`
  * accepts `use_runtime_recovery_gate`
  * passes both into governed repair execution after building the executable transaction

Connected the runtime step path:

* `core/runtime/step_handlers.py`
  * `governed_repair_mutation` step can now opt into:
    * `use_runtime_recovery_gate=True`
  * keeps the step handler as a caller/adapter only
  * does not move approval, dry-run, contract, or commit-gate logic into the handler

Added regression coverage:

* `tests/test_runtime_recovery_gate_hook.py`
  * verifies the recovery gate adapter returns normalized gate output
  * confirms reports for:
    * contract
    * approval
    * dry-run
    * commit

* `tests/test_governed_repair_execution.py`
  * verifies custom gate hook pass-through
  * verifies gate hook blocking before write
  * verifies API-level gate hook pass-through
  * verifies `use_runtime_recovery_gate=True` can route through the default runtime recovery gate

* `tests/test_command_dispatch_recovery_lifecycle.py`
  * locks the command-dispatch recovery lifecycle:
    * `recovery list`
    * `recovery status`
    * `run recovery`
    * `verify recovery`

### Runtime chain established

The completed runtime gate topology is now:

```text
governed_repair_mutation step
-> GovernedRepairMutationStepHandler
-> execute_governed_repair_mutation(...)
-> execute_committed_runtime_repair_transaction(...)
-> execute_governed_repair_transaction(...)
-> runtime_recovery_gate_hook(...)
-> build_runtime_recovery_execution_contract(...)
-> approve_runtime_recovery_plan(...)
-> dry_run_runtime_recovery(...)
-> gate_runtime_recovery_commit(...)
-> allow / block governed mutation execution
```

The command recovery lifecycle path is also locked:

```text
operator command
-> CommandDispatch
-> RuntimeRecoveryCoordinator
-> recovery plan
-> replay
-> verify
```

### Boundaries preserved

This checkpoint intentionally preserves these boundaries:

```text
gate hook != mutation executor
recovery gate != command dispatch
recovery policy != scheduler rewrite
approval / dry-run / commit gate != step handler logic
execution contract != real file write
governed repair API != direct scheduler access
step handler != recovery-policy implementation
```

The new topology still does not add:

```text
NO hidden autonomous approval
NO direct recovery gate hard-coded into every repair path
NO command dispatch dependency in governed repair execution
NO scheduler / planner / agent coupling
NO mutation_boundary pollution
NO automatic GitHub push / merge
NO unrestricted workspace mutation
```

### Boundary audit

The ownership audit after this pass showed the new topology stayed small:

```text
core/runtime/governed_repair_api.py                 96 lines / 1 function
core/runtime/governed_repair_execution.py           155 lines / 4 functions
core/runtime/repair_transaction_execution_bridge.py 141 lines / 4 functions
core/runtime/runtime_recovery_gate_hook.py          121 lines / 4 functions
```

Domain scan confirmed no drift into:

```text
scheduler
planner
agent
LLM
command dispatch
tool registry
mutation boundary
```

The recovery gate hook remains focused on:

```text
approval
dry-run
execution contract
commit gate
```

### Validation confirmed

Confirmed focused validation:

```text
python -m pytest tests/test_runtime_recovery_gate_hook.py -q
python -m pytest tests/test_governed_repair_execution.py -q
python -m pytest tests/test_repair_transaction_execution_bridge.py tests/test_governed_repair_execution.py tests/test_governed_repair_mutation_policy_smoke.py -q
python -m pytest tests/test_step_executor_governed_repair_mutation.py tests/test_governed_repair_execution.py tests/test_runtime_recovery_gate_hook.py tests/test_governed_repair_mutation_policy_smoke.py -q
```

Confirmed integrated validation:

```text
16 passed
493 passed
503 passed
```

The important validation result is that the recovery gate topology now participates in the governed repair runtime path without breaking the runtime repair / recovery / replay stack.

### Why this matters

This checkpoint moves ZERO from having recovery governance modules beside the runtime into having a recovery policy topology that can actually guard runtime execution.

The important result is not that another gate module exists. The important result is that governed repair execution can now opt into recovery approval, recovery dry-run, recovery execution-contract, and recovery commit-gate checks through a clean adapter boundary before mutation execution is allowed.

This is a stronger AER property because policy, gate evaluation, execution, command dispatch, and scheduler ownership remain separated while still forming one executable runtime chain.

### Stable checkpoint after this pass

* runtime recovery gate hook: working
* governed repair execution gate hook: working
* API pass-through: working
* bridge pass-through: working
* step handler opt-in: working
* command recovery lifecycle test: working
* recovery policy topology: landed
* policy / execution boundary: preserved
* command dispatch boundary: preserved
* scheduler / planner / agent coupling: avoided
* runtime repair / recovery / replay regression: passing

### Evidence kept

Keep screenshots showing:

* `tests/test_runtime_recovery_gate_hook.py` passing
* `tests/test_governed_repair_execution.py` passing
* `16 passed`
* `493 passed`
* `503 passed`
* boundary audit showing:
  * governed repair API remains 96 lines / 1 function
  * governed repair execution remains 155 lines / 4 functions
  * repair transaction bridge remains 141 lines / 4 functions
  * runtime recovery gate hook remains 121 lines / 4 functions
* domain scan showing no scheduler / planner / agent / command dispatch drift

### Next step

Recommended next checkpoint:

```text
Recovery Gate Evidence Hardening
```

Expected boundary:

```text
gate result
-> normalized blocker summary
-> recovery reports bundle
-> operator-visible gate explanation
-> audit/evidence link
```

Still avoid:

```text
NO hidden approval
NO broad scheduler rewrite
NO agent_loop rewrite
NO command dispatch dependency inside execution
NO mutation executor ownership inside recovery gate
NO automatic external side effects
```

## 2026-05-15 - Operator Review Runtime Resume and Rollback Recovery checkpoint

This checkpoint records the completion of the operator review command path, governed runtime resume path, mutation landing proof, and rollback recovery fallback on `main`.

The goal was not to add another isolated mutation module. The goal was to connect the existing review, control API, scheduler, audit, runtime resume, mutation execution, verification failure, and rollback restore pieces into one inspectable governed execution chain.

### What was completed

Added the operator command dispatch layer:

* `core/system/command_dispatch.py`
  * routes semantic review commands such as `review queue`, `approve review <id>`, and `reject review <id>`
  * calls `ZeroControlAPI.get_review_queue()`
  * calls `ZeroControlAPI.approve_review_item(...)`
  * calls `ZeroControlAPI.reject_review_item(...)`
  * keeps shell command execution separate from operator governance commands

Added governance evidence persistence:

* `core/audit/review_audit.py`
  * records review queue reads
  * records approvals
  * records rejections
  * persists JSONL audit evidence under `workspace/audit/`

* `core/audit/review_execution_link.py`
  * links review item IDs to execution / mutation / rollback / trace identifiers when available
  * records applied files and command metadata
  * creates replay-friendly JSONL evidence

Fixed scheduler review item lookup:

* `core/tasks/scheduler.py`
  * review action lookup no longer hard-depends on `_load_task(...)`
  * falls back to in-memory task collections and `review_queue` entries
  * allows injected or public review items to transition through approve / reject paths without crashing when `_load_task` is unavailable

Fixed rollback restore metadata fallback:

* `core/runtime/task_runtime.py`
  * `rollback_last_apply(...)` can now derive `repair_context.rollback.per_file` from available backup snapshot metadata
  * supports fallback from:
    * `repair_context.rollback.backup_snapshot`
    * `repair_context.backup_snapshot`
    * `repair_context.apply_result.transaction.backup_snapshot`
  * maps backup snapshot entries into rollback restore records containing:
    * `target_path`
    * `full_target_path`
    * `backup_path`
    * `old_text`

### Runtime chain established

The completed chain is now:

```text
operator command
-> command dispatch
-> control API review action
-> scheduler review state mutation
-> audit event
-> execution link evidence
-> approve / reject lifecycle
-> runtime resume
-> queued execution
-> mutation step execution
-> artifact landing
-> verification failure rollback trigger
-> rollback restore from backup snapshot
-> rollback result evidence
```

### Validation confirmed

Confirmed semantic command parsing:

```text
review queue -> get_review_queue
approve review abc123 -> approve_review_item
reject review abc123 -> reject_review_item
```

Confirmed command dispatch evidence path with fake control API:

```text
ok=True
audit_event_id present
execution_link_id present
```

Confirmed real reject path:

```text
reject review review-test-1
-> review_state = rejected
-> status = blocked
-> requires_review = False
-> next_action = archive_or_revise_transaction
-> audit_event_id present
-> execution_link_id present
```

Confirmed real approve path:

```text
approve review review-approve-1
-> review_state = approved
-> requires_review = False
-> next_action = run_next_tick
-> agent_action = resume_execution
-> audit_event_id present
-> execution_link_id present
```

Confirmed runtime resume path:

```text
approve review resume-test-1
-> resume_task(resume-test-1)
-> status = queued
```

Confirmed runtime continuation and mutation landing:

```text
approve review mutation-test-2
-> resume_task
-> run_one
-> write_file
-> workspace/shared/runtime_resume_test.txt exists
-> content = governed runtime execution
```

Confirmed rollback trigger condition:

```text
verify step failed
repair_context.rollback.restore_available = True
-> should_rollback_after_failed_verify(...) = True
```

Confirmed rollback restore from backup snapshot fallback:

```text
workspace/shared/rollback_snapshot_test.txt: mutated
backup snapshot points to original backup
restore_repair_backup(...)
-> ok = True
-> restored_files includes workspace/shared/rollback_snapshot_test.txt
-> file content restored to original
```

Observed full-suite validation after both commits:

```text
1973 passed, 162 subtests passed
```

### Git checkpoints

Committed and pushed on `main`:

```text
352b5f5 - feat: connect operator review governance to runtime resume
b1fada4 - fix: restore rollback from backup snapshot fallback
```

### Boundaries preserved

This checkpoint intentionally preserves these boundaries:

```text
operator command != shell execution
command dispatch != scheduler internals
control API != direct mutation bypass
approval != hidden unrestricted execution
runtime resume != review bypass
rollback restore != new mutation authority
verification failure != silent continuation
backup snapshot != scheduler rewrite
```

The new path still does not add:

```text
NO hidden autonomous approval
NO direct UI-to-mutation shortcut
NO unrestricted shell execution
NO automatic GitHub push / merge
NO scheduler rewrite
NO agent_loop rewrite
NO rollback without restore metadata
```

### Why this matters

This checkpoint moves ZERO from a reviewable repair runtime into a governed autonomous engineering execution path.

The important result is not that ZERO can write a file. The important result is that ZERO can now take an operator-approved review item, resume it through the scheduler, execute a mutation step, detect verification rollback conditions, restore from backup snapshot evidence, and preserve review / execution evidence along the way.

This is a stronger runtime property than a normal agent loop because mutation, verification, rollback, audit, and operator authority remain inspectable and separated.

### Stable checkpoint after this pass

* operator review command dispatch: working
* command-to-control-API review routing: working
* review audit JSONL persistence: working
* review execution link persistence: working
* scheduler review lookup fallback: working
* reject path to blocked state: working
* approve path to resume state: working
* `resume_task(...)` to queued state: working
* `run_one(...)` runtime continuation: working
* governed `write_file` artifact landing: working
* verification-failure rollback trigger: working
* backup snapshot fallback for rollback restore: working
* rollback restore evidence: working
* full suite passing: working

### Evidence kept

Keep screenshots showing:

* command dispatch parse results for `review queue`, `approve review`, and `reject review`
* fake-control command dispatch test returning audit and execution link IDs
* real reject path setting `review_state=rejected` and `status=blocked`
* real approve path setting `next_action=run_next_tick` and `agent_action=resume_execution`
* `resume_task(...)` returning `status=queued`
* `run_one(...)` finishing resumed execution
* `workspace/shared/runtime_resume_test.txt` exists with `governed runtime execution`
* rollback trigger returning `True`
* rollback snapshot restore returning `ok=True` and restoring `original`
* `1973 passed, 162 subtests passed`
* commits `352b5f5` and `b1fada4` pushed to `main`

### Next step

Recommended next checkpoint:

```text
Rollback / Verification Evidence Hardening
```

Expected boundary:

```text
mutation result
-> verification result
-> rollback decision
-> rollback result
-> evidence bundle / audit link
-> operator-visible recovery summary
```

Still avoid:

```text
NO UI shortcut around control API
NO hidden rollback without evidence
NO broad scheduler rewrite
NO agent_loop rewrite
NO automatic GitHub write action
```

---

## 2026-05-14 - Governed Repair Runtime / Operator Review Loop checkpoint

This checkpoint records the governed repair runtime convergence work on branch:

```text
runtime-aggregate-convergence-v1
```

The goal was not to add another autonomous mutation path. The goal was to connect the existing governed mutation, review, transaction, scheduler, persistence, and control surfaces into one visible human-supervised runtime loop.

### What was completed

Completed the governed repair execution and review-loop wiring across the runtime path:

* routed `governed_repair_mutation` through `MutationBoundary` risk classification
* fixed verification precedence so explicit `skip_verification=True` overrides risk-default verification when intentionally requested
* gated approval-required repair transactions behind `awaiting_review` instead of allowing direct commit
* wired transaction review approval into lifecycle transitions:
  * `awaiting_review -> approved -> authorized`
* wired transaction review rejection into:
  * `awaiting_review -> blocked`
* exposed governed repair review lifecycle fields in public task records
* persisted review lifecycle fields through scheduler repo state sync
* surfaced `review_queue` in scheduler queue snapshots
* added scheduler operator review bridge:
  * `approve_review_item(...)`
  * `reject_review_item(...)`
* added scheduler-native review inbox API:
  * `get_review_queue()`
* exposed review inbox actions through `ZeroControlAPI`:
  * `get_review_queue()`
  * `approve_review_item(...)`
  * `reject_review_item(...)`

### Runtime chain established

The completed chain is now:

```text
governed_repair_mutation
-> MutationBoundary risk classification
-> approval / verification policy
-> governed repair transaction
-> awaiting_review state
-> persisted review lifecycle fields
-> scheduler public task projection
-> scheduler review_queue
-> operator inbox query
-> approve / reject action
-> lifecycle transition
-> authorized resume semantics
-> audit / replay continuity
```

### Major layers completed

#### Risk-aware governed mutation routing

* repair-generated mutation now routes through mutation boundary policy
* explicit scope is required by default
* approval mode is derived from risk classification
* verification mode is derived from risk classification with explicit operator override precedence
* smoke coverage locks the conservative default behavior

#### Runtime repair transaction lifecycle

* approval-required transactions stop at `awaiting_review`
* approved transactions transition toward `authorized`
* rejected transactions transition to `blocked`
* commit remains allowed only for authorized / approved transactions or no-approval-required transactions
* audit events are appended for review lifecycle transitions
* rollback path remains untouched

#### Scheduler visibility and persistence

* public task records now expose review lifecycle state
* repo state sync persists:
  * `transaction_state`
  * `allowed_next_action`
  * `approval_required`
* scheduler queue snapshot now includes:
  * `review_queue`
  * `review_queue_size`
* review queue is derived from existing task/public-record state rather than a separate inbox database

#### Operator bridge and control surface

* scheduler has operator-facing review actions:
  * approve review item
  * reject review item
* scheduler exposes review inbox listing via `get_review_queue()`
* control API exposes the same review actions without forcing callers into scheduler internals
* no UI implementation was added in this checkpoint; the layer is API/control-surface only

### Boundaries preserved

This checkpoint intentionally preserves these boundaries:

```text
review queue != UI
operator action != unrestricted mutation
approval != immediate hidden execution
scheduler visibility != scheduler authority expansion
control API != direct scheduler internals exposure
```

The new path still does not add:

```text
NO new UI
NO unrestricted workspace mutation
NO hidden autonomous approve/reject
NO scheduler rewrite
NO agent_loop rewrite
NO new review framework
NO automatic merge / push / external side effects
```

### Validation confirmed

Confirmed passing during this checkpoint:

```text
python -m pytest tests/test_runtime_repair_transaction.py tests/test_runtime_repair_transaction_review.py tests/test_step_executor_governed_repair_mutation.py -q
python -m pytest -q
```

Observed full-suite validation:

```text
1973 passed, 162 subtests passed
```

### Git checkpoints

Committed and pushed on branch:

```text
runtime-aggregate-convergence-v1
```

Relevant commits from this pass:

```text
e03acfa - route governed repair mutation through boundary risk policy
18b9cc8 - add risk-aware governed repair mutation policy enforcement
1ae7dc3 - gate runtime repair commit behind approval review state
7791bbe - wire approval review lifecycle into governed repair transactions
379bcd6 - expose governed repair review lifecycle in public task records
cff5bb7 - persist governed repair review lifecycle fields
ba788cd - surface review queue in scheduler snapshot
1ed2f43 - add scheduler operator review action bridge
ecec22f - add scheduler review inbox api
6ba1ca4 - expose review inbox actions through control api
```

### Why this matters

This checkpoint moves ZERO from a governed repair transaction substrate into a human-supervised autonomous engineering runtime path.

The important result is not that ZERO can write more files. The important result is that a repair mutation can now become a governed transaction, enter a review queue, be surfaced to an operator, transition through approval or rejection, persist its lifecycle, and remain visible through scheduler and control API surfaces before any resume path is allowed.

This reduces the risk that mutation, review, approval, resume, audit, replay, and UI concerns collapse into one untestable path inside `scheduler.py` or `agent_loop.py`.

### Stable checkpoint after this pass

* governed repair mutation boundary routing: working
* risk-aware approval/verification policy: working
* explicit scope gate: working
* approval-required transaction stop at `awaiting_review`: working
* approve lifecycle transition to `authorized`: working
* reject lifecycle transition to `blocked`: working
* review lifecycle persistence: working
* public task projection: working
* scheduler review queue: working
* scheduler operator action bridge: working
* scheduler review inbox API: working
* control API review action surface: working
* full test suite: passing
* UI not yet added
* hidden autonomous approval not enabled

### Evidence kept

Keep screenshots showing:

* `1973 passed, 162 subtests passed`
* `review_queue` added to scheduler snapshot
* commits pushed to `runtime-aggregate-convergence-v1`
* `scheduler.get_review_queue()` API completion
* control API review action completion
* runtime artifact cleanup before commits

### Next step

Recommended next checkpoint:

```text
Operator Review Console / UI Adapter v1
```

Expected boundary:

```text
review_queue -> display / console adapter -> approve/reject command -> control API -> scheduler bridge
```

Still avoid:

```text
NO direct UI-to-mutation shortcut
NO hidden approval
NO automatic execution without review state
NO scheduler rewrite
NO agent_loop rewrite
```

## 2026-05-13 - Runtime Aggregate Convergence v1 deterministic evidence checkpoint

This checkpoint records the runtime aggregate convergence work on branch:

```text
runtime-aggregate-convergence-v1
```

The goal was not to wire the new runtime evidence stack directly into scheduler, agent loop, or step executor. The goal was to seal deterministic runtime contracts first so future execution, replay, audit, rollback, serialization, and persistence work has a stable substrate instead of becoming another tangled path inside `scheduler.py` or `agent_loop.py`.

### What was completed

Added and stabilized the deterministic runtime primitive / evidence chain under `core/runtime/`:

* `core/runtime/runtime_execution_graph.py`
* `core/runtime/runtime_operation.py`
* `core/runtime/runtime_transaction.py`
* `core/runtime/execution_plan.py`
* `core/runtime/execution_plan_snapshot.py`
* `core/runtime/execution_replay.py`
* `core/runtime/execution_audit.py`
* `core/runtime/rollback_verification.py`
* `core/runtime/runtime_evidence_bundle.py`
* `core/runtime/runtime_evidence_serialization.py`
* `core/runtime/runtime_evidence_persistence.py`

Added matching regression contracts, including:

* `tests/test_runtime_execution_graph_contract.py`
* `tests/test_runtime_operation_contract.py`
* `tests/test_runtime_transaction_contract.py`
* `tests/test_execution_plan_contract.py`
* `tests/test_execution_plan_snapshot_contract.py`
* `tests/test_execution_replay_contract.py`
* `tests/test_execution_audit_contract.py`
* `tests/test_rollback_verification_contract.py`
* `tests/test_runtime_evidence_bundle_contract.py`
* `tests/test_runtime_evidence_serialization_contract.py`
* `tests/test_runtime_evidence_persistence_contract.py`
* `tests/test_runtime_transaction_orchestrator_contract.py`

Updated:

* `tests/run_regression_contracts.py`

### Runtime chain established

The completed deterministic runtime chain is:

```text
RuntimeExecutionGraph
-> RuntimeOperation
-> RuntimeTransaction
-> ExecutionPlan
-> ExecutionPlanSnapshot
-> ExecutionReplayVerifier
-> ExecutionAuditTrail
-> RollbackVerificationVerifier
-> RuntimeEvidenceBundle
-> RuntimeEvidenceSerializer
-> RuntimeEvidenceStore / InMemoryRuntimeEvidenceStore
```

### Major layers completed

#### Execution topology and operation contracts

* deterministic dependency graph
* dependency validation
* cycle / duplicate / self-edge rejection
* deterministic topological execution order
* runtime operation status transition contract
* terminal-state transition freeze
* operation result / failure attach-once behavior
* operation fingerprint using canonical JSON

#### Transaction and execution plan contracts

* deterministic operation group contract
* duplicate operation rejection
* transaction aggregate status derived from operation state
* execution plan graph/transaction identity validation
* graph node IDs aligned with transaction operation IDs
* deterministic plan execution order
* plan fingerprint tied to graph structure and transaction fingerprint

#### Snapshot, replay, and audit evidence

* immutable execution plan snapshot
* snapshot isolation from later plan / graph / transaction mutation
* replay verification against snapshot
* mismatch diagnostics for plan fingerprint, execution order, operation fingerprints, missing operations, extra operations, and aggregate status
* immutable audit record from replay evidence
* audit trail with deterministic append order and trail fingerprint

#### Rollback verification and evidence packaging

* reverse dependency-safe rollback order verification
* rollback mismatch diagnostics
* runtime evidence bundle combining snapshot, replay, audit, and rollback verification evidence
* identity consistency checks across bundle components
* deterministic bundle fingerprint

#### Serialization and persistence boundary

* canonical JSON serialization for evidence bundles
* deterministic serialize -> deserialize -> serialize roundtrip
* fingerprint mismatch rejection
* missing-field rejection
* payload mutation isolation
* abstract runtime evidence store boundary
* in-memory evidence store implementation for contract validation
* deterministic store fingerprint from ordered bundle fingerprints

### Boundaries preserved

This checkpoint intentionally preserves these boundaries:

```text
contract != scheduler action
replay verification != tool rerun
audit evidence != execution authority
rollback verification != rollback execution
persistence boundary != sqlite/file backend
serialization != networking
orchestrator contract != main runtime integration
```

The new stack still does not allow:

```text
NO scheduler coupling
NO agent_loop coupling
NO step_executor coupling
NO real tool replay
NO real rollback execution
NO filesystem persistence backend
NO sqlite backend
NO networking export
NO UI integration
NO formal workspace mutation
```

### Validation confirmed

Confirmed passing during this checkpoint:

```text
tests/test_runtime_execution_graph_contract.py: PASS, 30 tests
tests/test_runtime_operation_contract.py: PASS, 18 tests
tests/test_runtime_transaction_contract.py: PASS, 21 tests
tests/test_execution_plan_contract.py: PASS, 14 tests
tests/test_execution_plan_snapshot_contract.py: 11 tests OK
tests/test_execution_replay_contract.py: 13 tests OK
tests/test_execution_audit_contract.py: 12 tests OK
tests/test_rollback_verification_contract.py: 11 tests OK
tests/test_runtime_evidence_bundle_contract.py: 9 tests OK
tests/test_runtime_evidence_serialization_contract.py: 10 tests OK
tests/test_runtime_evidence_persistence_contract.py: 12 tests OK
tests/run_regression_contracts.py: ALL PASS, 49 test files
```

### Git checkpoint

Pushed branch:

```text
runtime-aggregate-convergence-v1
```

Observed push range:

```text
92284b1..1ea2da1  runtime-aggregate-convergence-v1 -> runtime-aggregate-convergence-v1
```

### Why this matters

This checkpoint moves ZERO from a repair-capable and governance-aware runtime toward a deterministic runtime evidence kernel.

The important result is not that ZERO executes more tools. The important result is that ZERO can now represent execution structure, operation state, transaction grouping, execution plans, snapshots, replay verification, audit evidence, rollback verification, evidence bundles, serialization payloads, and persistence boundaries as deterministic contracts before those pieces are allowed into the live runtime path.

This reduces the risk that future execution replay, rollback, audit, persistence, repair evidence, and scheduler integration collapse into one untestable runtime path.

### Stable checkpoint after this pass

* runtime execution graph: working
* runtime operation contract: working
* runtime transaction contract: working
* execution plan contract: working
* execution plan snapshot: working
* replay verification: working
* audit record / audit trail: working
* rollback verification: working
* runtime evidence bundle: working
* evidence serialization: working
* persistence boundary abstraction: working
* regression contract runner: 49 files passing
* scheduler, agent loop, and step executor remain uncoupled
* real rollback, real replay, filesystem persistence, and runtime integration remain disabled

### Evidence kept

Keep screenshots showing:

* `tests/run_regression_contracts.py: ALL PASS: 49 test files`
* Runtime Evidence Persistence Contract v1 completion summary
* Runtime Evidence Serialization Contract v1 completion summary
* Runtime Evidence Bundle Contract v1 completion summary
* Rollback Verification Contract v1 completion summary
* Execution Audit / Replay / Snapshot completion summaries
* push to `runtime-aggregate-convergence-v1`
* commit range `92284b1..1ea2da1`

### Next step

Do not connect this stack directly into the live scheduler path yet.

Recommended next checkpoint:

```text
FilesystemEvidenceStore v1
```

Expected boundary:

```text
contract -> safe file adapter -> load validation -> fingerprint verification -> no scheduler execution
```

Still avoid:

```text
NO automatic scheduler resume
NO executor replay
NO rollback execution
NO hidden workspace mutation
NO agent_loop integration until evidence store semantics are stable
```

## 2026-05-11 - Runtime Repair Transaction v1-v25 governed cognition checkpoint

This checkpoint records the completion of the governed repair transaction cognition stack on branch:

```text
runtime-repair-transaction-layer
```

The goal was not to open unrestricted self-modifying execution. The goal was to build a deterministic transaction, review, authorization, replay, knowledge, recommendation, risk, policy, and governance-report path before allowing any future formal workspace mutation.

### What was completed

Added and stabilized the runtime repair transaction stack in:

* `core/tasks/runtime_repair_apply_transaction.py`
* `tests/test_runtime_repair_apply_transaction.py`

The completed chain now covers:

```text
transaction
-> preflight
-> sandbox apply
-> rollback safety
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

### Major layers completed

#### Transaction and apply safety

* staged transaction record
* preflight validation
* abort lifecycle
* dry-run apply plan
* sandbox-only apply
* rollback and cleanup behavior
* temp-workspace controlled commit

#### Review and authority separation

* human review gate
* explicit approval / rejection
* commit authorization token
* token expiry / revoke / consume lifecycle
* immutable commit intent
* short-lived execution lease
* final consistency precheck

#### Evidence, replay, and reproducibility

* immutable commit artifact
* deterministic audit bundle
* artifact replay
* reproducibility verification
* replay workspace isolation
* original artifact non-mutation

#### Lineage and repair knowledge

* artifact lineage node
* lineage graph
* cycle / orphan / tamper validation
* repair knowledge snapshot
* knowledge index
* deterministic query layer

#### Advisory and cognition layer

* similarity query
* candidate retrieval
* candidate explanation
* read-only recommendation draft
* recommendation review gate
* recommendation provenance
* risk assessment
* decision trace
* policy evaluation
* governance report

### Boundaries preserved

The checkpoint intentionally preserves these boundaries:

```text
governance != execution
advisory != authority
recommendation != mutation
policy evaluation != scheduler action
knowledge retrieval != auto-repair
replay != scheduler resume
commit preview != formal workspace mutation
```

The layer still does not allow:

```text
NO direct formal workspace mutation
NO automatic scheduler execution
NO recommendation auto-apply
NO hidden shell execution
NO unrestricted self-modification
```

### Validation confirmed

Confirmed passing:

```text
python -m pytest tests/test_runtime_repair_apply_transaction.py -q
python -m pytest tests -q
```

Observed validation result:

```text
tests/test_runtime_repair_apply_transaction.py: 193 passed
tests: 692 passed
```

### Git checkpoint

Committed and pushed on branch:

```text
runtime-repair-transaction-layer
```

Commit:

```text
7dda138 - Add governed repair transaction cognition layers
```

### Why this matters

This checkpoint moves ZERO from a repair-capable runtime toward a governed engineering cognition runtime.

The important result is not just that ZERO can prepare repairs. The important result is that repair activity can now be represented as a deterministic, reviewable, replayable, risk-assessed, policy-checked, and provenance-preserving chain.

This reduces the risk that future mutation execution, rollback, replay, recommendation, audit, and policy logic become one tangled path inside `scheduler.py` or `agent_loop.py`.

### Stable checkpoint after this pass

* transaction lifecycle: working
* preflight / abort: working
* dry-run plan: working
* sandbox apply / rollback: working
* commit preview / diff snapshot: working
* human review gate: working
* commit token: working
* immutable intent: working
* execution lease: working
* final precheck: working
* temp-workspace commit: working
* commit artifact / audit bundle: working
* replay / reproducibility: working
* lineage graph: working
* knowledge snapshot / index: working
* candidate retrieval / explanation: working
* read-only recommendation draft: working
* recommendation review / provenance: working
* risk assessment: working
* decision trace: working
* policy evaluation: working
* governance report: working
* recommendation remains read-only
* scheduler and agent loop not coupled into this stack
* formal workspace mutation still disabled

### Evidence kept

Keep screenshots showing:

* `692 passed`
* `tests/test_runtime_repair_apply_transaction.py: 193 passed`
* commit `7dda138`
* push to `runtime-repair-transaction-layer`
* the v25 governance report completion summary

### Next step

Do not jump directly into autonomous mutation.

Recommended next checkpoint:

```text
Runtime Repair Patch Preview Subsystem
```

Current untracked files:

```text
core/tasks/runtime_repair_patch_preview.py
tests/test_runtime_repair_patch_preview.py
```

Treat this as a separate subsystem checkpoint instead of mixing it into the governed transaction cognition stack.



---

## 2026-05-10 - Runtime Governance / Recovery Kernel skeleton checkpoint

This checkpoint records the runtime repair governance and recovery infrastructure work on branch:

```text
runtime-repair-transaction-layer
```

The goal was not to open unrestricted self-modifying execution. The goal was to build deterministic governance, review, replay, recovery, and persistence contracts before allowing any real mutation executor.

### What was completed

Added the runtime repair safety and governance stack:

* `core/tasks/runtime_repair_transaction.py`
* `core/display/runtime_repair_transaction_presenter.py`
* `core/tasks/runtime_repair_transaction_preview.py`
* `core/tasks/runtime_repair_transaction_review.py`
* `core/tasks/runtime_repair_review_artifact.py`
* `core/tasks/runtime_repair_transaction_state_machine.py`
* `core/tasks/runtime_repair_controlled_apply.py`
* `core/tasks/runtime_repair_apply_executor_contract.py`
* `core/tasks/runtime_repair_transaction_snapshot.py`
* `core/tasks/runtime_repair_replay_queue.py`
* `core/tasks/runtime_repair_governance_boundary.py`
* `core/tasks/runtime_repair_persistence_contract.py`

Added matching validation:

* `tests/test_runtime_repair_transaction.py`
* `tests/test_runtime_repair_transaction_presenter.py`
* `tests/test_runtime_repair_transaction_preview.py`
* `tests/test_runtime_repair_transaction_review.py`
* `tests/test_runtime_repair_review_artifact.py`
* `tests/test_runtime_repair_transaction_state_machine.py`
* `tests/test_runtime_repair_controlled_apply.py`
* `tests/test_runtime_repair_apply_executor_contract.py`
* `tests/test_runtime_repair_transaction_snapshot.py`
* `tests/test_runtime_repair_replay_queue.py`
* `tests/test_runtime_repair_governance_boundary.py`
* `tests/test_runtime_repair_persistence_contract.py`

### Runtime chain established

The completed chain is:

```text
proposal
-> confirmation
-> authorization
-> scope gate
-> transaction
-> preview payload
-> presenter
-> review contract
-> review artifact
-> state machine
-> controlled apply planning
-> executor contract
-> execution receipt
-> rollback receipt
-> execution audit payload
-> transaction snapshot
-> recovery payload
-> hydration contract
-> replay queue item
-> replay chain
-> continuation metadata
-> governance boundary
-> persistence contract
```

### Boundaries preserved

The checkpoint intentionally keeps these boundaries sealed:

```text
governance != execution
recovery != persistence
snapshot != storage backend
replay != scheduler resume
apply plan != mutation execution
boundary != runtime mutation
```

The new infrastructure remains contract-only:

```text
NO real file write
NO real patch execution
NO shell execution
NO SQLite backend
NO automatic restore
NO scheduler resume
NO filesystem resume
```

### Why this matters

This checkpoint moves ZERO from a repair-capable runtime toward an autonomous engineering runtime substrate.

The important step is not that ZERO can mutate files. The important step is that ZERO now has a governed path for deciding whether a repair transaction can be reviewed, authorized, planned, snapshotted, replayed, and prepared for future persistence without directly coupling those responsibilities into `scheduler.py` or `agent_loop.py`.

This reduces the risk that future mutation execution, rollback, replay, audit, and crash recovery become one tangled runtime path.

### Validation confirmed

Confirmed passing:

```text
python -m pytest tests/test_runtime_repair_governance_boundary.py -q
python -m pytest tests/test_runtime_repair_replay_queue.py -q
python -m pytest tests/test_runtime_repair_transaction_snapshot.py -q
python -m pytest tests/test_runtime_repair_apply_executor_contract.py -q
python -m pytest tests/test_runtime_repair_controlled_apply.py -q
python -m pytest tests/test_runtime_repair_persistence_contract.py -q
python -m pytest tests -q
```

Observed full-suite result:

```text
492 passed
```

### Stable checkpoint after this pass

* runtime repair transaction foundation: working
* transaction preview payload: working
* transaction review contract: working
* review artifact: working
* transaction state machine: working
* controlled apply planning: working
* executor contract: working
* dry-run execution receipt: working
* rollback receipt: working
* transaction snapshot: working
* recovery payload: working
* hydration contract: working
* replay queue: working
* governance boundary: working
* persistence contract: working
* scheduler and agent loop untouched by this branch
* real mutation execution still disabled

### Next step

Do not jump directly into broad autonomous mutation.

Recommended next stage:

```text
Persistent Runtime Backend
```

Expected scope:

```text
contract -> safe storage adapter -> reload validation -> replay inspection
```

Still avoid real mutation execution until persistence, replay, and recovery semantics are stable.




---

## 2026-05-06 - Autonomous Code Repair Loop checkpoint

This checkpoint records the first stabilized autonomous code-repair workflow integrated into the ZERO runtime path.

The goal was not to create unrestricted self-modifying AI. The goal was to prove a controlled local repair loop capable of:

```text
observe
-> identify semantic failure
-> generate structured repair action
-> apply controlled patch
-> verify result
-> rerun safely
```

### What was demonstrated

Added runtime-aware repair flow behavior:

* semantic error interpretation
* repair intent routing
* CODE CHAIN diff generation
* controlled patch apply
* verification pass
* execution replay visibility

The repair path now distinguishes:

```text
syntax issue
vs
semantic mismatch
```

Example demonstrated:

```python
def multiply(a, b):
    return a + b
```

The runtime recognized the issue was not a syntax failure, but a semantic mismatch between the function name and actual behavior.

### Repair chain behavior

Observed flow:

```text
task failure
-> execution trace
-> semantic routing
-> repair action generation
-> patch diff
-> patch apply
-> verification
-> successful rerun
```

The repair loop preserved:

* execution trace visibility
* patch visibility
* verification state
* replayable runtime history

### Important boundaries preserved

The repair workflow still remains controlled:

* no unrestricted filesystem mutation
* no unrestricted shell execution
* no hidden autonomous background edits
* repair actions remain traceable
* verification required before success state

### Why this matters

This checkpoint moves ZERO from:

```text
task execution runtime
```

toward:

```text
runtime-aware autonomous engineering workflow
```

The important transition is that ZERO is no longer only generating code output.

It is beginning to:

* observe execution state
* interpret failures semantically
* generate structured repair actions
* apply controlled patches
* verify execution recovery

### Demo artifact

Recorded demo:

```text
demos/zero-autonomous-code-repair-demo.mp4
```

### Stable checkpoint after this pass

* semantic repair routing: working
* CODE CHAIN diff generation: working
* controlled patch apply: working
* verification rerun: working
* execution trace visibility: working
* replayable repair flow: working


# ZERO Devlog

## 2026-05-02 - L5 Persona Runtime and Presentation checkpoint

This checkpoint records the L5 digital-human/persona runtime work completed after the L4 tool layer was sealed.

The goal was not to add avatar, voice, or UI effects first. The goal was to seal a stable runtime path that a future digital-human interface can call without contaminating scheduler, worker, policy, or tool execution internals.

### What was completed

Added the thin L5 CLI transport path:

* `app.py`
  * added `l5-run`
  * accepts task text
  * supports JSON and passive TTS output modes
  * calls the persona runtime bridge instead of becoming a controller
* `main.py`
  * forwards `l5-run` into `app.py`
  * remains a launcher/transport layer

Added display-state contract support:

* `core/persona/display_state_contract.py`
  * `DISPLAY_STATE_SCHEMA_VERSION`
  * `DISPLAY_STATE_REQUIRED_KEYS`
  * `TTS_PIPELINE_REQUIRED_KEYS`
  * `PRESENTATION_LOG_REQUIRED_KEYS`
  * `PERSONA_RUNTIME_CONTRACT_REQUIRED_KEYS`
  * `ensure_display_state_contract(...)`

Updated persona runtime bridge:

* `core/persona/runtime_bridge.py`
  * validates display-state contract
  * keeps TTS passive
  * keeps `persona_final_reply` as the source for human-facing output
  * prevents UI/CLI from inventing missing runtime behavior

Added policy layer and decision trace:

* `core/persona/policy_layer.py`
  * `evaluate_persona_runtime_policy(...)`
  * `policy_decision_trace(...)`
  * low risk -> allowed
  * medium risk -> allowed with confirmation-required marker
  * high risk -> blocked before runtime execution

Added persona runtime session state:

* `core/persona/runtime_state.py`
  * `PersonaRuntimeState`
  * `create_persona_runtime_state(...)`
  * `update_policy_decision(...)`
  * `update_display_state(...)`
  * `snapshot(...)`

Added presentation bridge:

* `core/persona/presentation_bridge.py`
  * `render_cli_view(display_state, include_tts=False)`
  * `render_json_view(display_state)`
  * `extract_tts_input(display_state)`

### Contract boundaries

The L5 persona path now follows:

```text
CLI transport
-> PersonaRuntimeBridge
-> policy layer
-> runtime state
-> display_state contract
-> presentation bridge
-> CLI / JSON / TTS output
```

Important boundaries preserved:

```text
runtime_state = internal state
display_state = public API
presentation_bridge = public API renderer
```

The presentation bridge only reads `display_state`.

It does not read or mutate:

* `runtime_state`
* policy internals
* scheduler state
* worker state
* tool result / raw output

### Validation confirmed

Confirmed passing:

```text
python tests/run_l5_run_cli_smoke.py
python tests/run_persona_runtime_bridge_smoke.py
python tests/run_persona_policy_layer_smoke.py
python tests/run_persona_runtime_state_smoke.py
python tests/run_presentation_bridge_smoke.py
python tests/run_persona_presentation_bridge_smoke.py
python tests/run_hybrid_demo_smoke.py
```

### Why this matters

This checkpoint turns the digital-human path from a UI idea into a stable runtime interface.

The important result is that a future UI, TTS layer, or avatar layer can consume `display_state` and `persona_final_reply` without reaching backward into scheduler, policy, worker, or tool internals.

Stable checkpoint after this pass:

* L5 CLI transport: working
* persona runtime bridge: working
* display-state contract: working
* policy decision trace: working
* runtime session state: working
* presentation bridge: working
* TTS remains passive
* core runtime boundaries preserved

---

## 2026-05-02 - L5.5 Worker Runtime and Task Execution System checkpoint

This checkpoint records the engineering-mainline work that moved ZERO from a single persona runtime path into a composable task execution system.

The goal was not to create multi-agent chat or autonomous workers. The goal was to build a deterministic worker/task foundation that can decompose, schedule, execute, collect, aggregate, trace, and replay work without giving workers planner authority.

### Worker contract foundation

Added:

* `core/worker/worker_contracts.py`
  * worker task contract
  * worker result contract
  * worker state snapshot
  * parent task contract
  * aggregation contract
  * final result contract
  * scheduler queue item contract
  * scheduler state contract

Worker task intentionally only accepts:

```text
task_id
parent_task_id
role
objective
input_context
```

Worker task explicitly rejects strategy and policy fields such as:

```text
constraints
expected_output
retry_policy
policy
strategy
planner_decision
```

This preserves the rule:

```text
persona / planner = decision layer
worker = constrained execution unit
worker_runtime = orchestration layer
```

### Worker runtime foundation

Added:

* `core/worker/worker_runtime.py`
  * `create_task(...)`
  * `run_task(...)`
  * `collect_result(...)`
  * `merge_result(...)`
  * `snapshot_state(...)`

The worker runtime only delegates to the injected ZERO runtime runner.

It does not:

* execute tools directly
* make policy decisions
* retry by itself
* become a planner

### Manual task decomposition

Added:

* `core/worker/task_decomposition.py`

The manual decomposition path supports:

```text
parent_task
-> manual worker_specs
-> worker_task
-> worker_runtime
-> merge
-> snapshot
```

This pass intentionally did not add:

* auto planner
* AI task decomposition
* worker-to-worker chat
* parallel execution

### Result aggregation

Added:

* `core/worker/result_aggregation.py`
  * `AggregationRuntime.aggregate(...)`
  * `AggregationRuntime.to_display_state(...)`

Supported deterministic aggregation strategies:

```text
concat
select
synthesize
```

`synthesize` is deterministic and does not call AI.

Aggregation converts multiple `worker_result` records into a single `final_result` and can project that final result into display state.

### Scheduler foundation

Added:

* `core/worker/worker_scheduler.py`
  * `enqueue(...)`
  * `run_next(...)`
  * `run_until_idle(...)`
  * `snapshot_state(...)`

The scheduler supports:

```text
pending
running
done
failed
```

Behavior is deterministic:

* one queued worker task runs at a time
* execution order follows enqueue order
* retry uses a fixed max-retry rule
* failed retry exhaustion lands in `failed`
* successful execution lands in `done`
* worker runtime state is updated after execution

The scheduler intentionally does not perform:

* AI planning
* automatic task decomposition
* parallel execution
* multi-agent behavior

### Execution trace and replay

Added:

* `core/worker/execution_trace.py`
  * `TraceEvent`
  * `TraceRecorder`
  * `TraceReplayRuntime`
  * `create_trace_event(...)`
  * `ensure_trace_event_contract(...)`
  * `trace_digest(...)`

Trace event schema covers:

```text
worker
scheduler
aggregation
```

Every event includes:

```text
schema_version
event_id
sequence
ts
component
event_type
payload
```

Replay can rebuild:

```text
scheduler_state
worker_results
final_result
trace_digest
```

The trace layer is deterministic and does not use AI.

### Validation confirmed

Confirmed passing:

```text
python tests/run_worker_runtime_contract_smoke.py
python tests/run_task_decomposition_manual_smoke.py
python tests/run_result_aggregation_strategy_smoke.py
python tests/run_worker_scheduler_foundation_smoke.py
python tests/run_execution_trace_replay_smoke.py
python tests/run_persona_runtime_state_smoke.py
python tests/run_persona_presentation_bridge_smoke.py
python tests/run_l5_tool_controller_core_smoke.py
python tests/run_l5_tool_decision_core_smoke.py
```

### Git checkpoint

Committed and pushed:

```text
597f82f - Add L5 worker runtime and digital human shell
```

This commit included the worker runtime foundation, deterministic task execution system pieces, trace/replay layer, and digital-human UI shell files.

### Why this matters

This checkpoint moves ZERO from:

```text
single persona runtime
```

to:

```text
decomposable, schedulable, observable, replayable task execution system
```

The completed chain is:

```text
input
-> parent_task
-> manual decomposition
-> worker_tasks
-> scheduler queue
-> worker_runtime
-> worker_results
-> aggregation
-> final_result
-> display_state / presentation
-> execution_trace
-> replay
```

Stable checkpoint after this pass:

* worker contracts: working
* worker runtime: working
* manual decomposition: working
* result aggregation: working
* deterministic scheduler: working
* trace/replay: working
* existing L5 persona path preserved
* no AI planner added
* no parallel execution added
* no worker strategy authority added

---

## 2026-05-02 - L6 Digital Human UI Shell and Interaction checkpoint

This checkpoint records the product-layer work that wrapped the existing ZERO runtime output in a digital-human interface shell.

The goal was not to make the runtime smarter. The goal was to make the completed runtime understandable, operable, and presentable through a digital-human-style UI while preserving the core boundary.

### What was completed

Added the digital-human UI shell:

* `ui/digital_human.html`
  * left avatar/persona status area
  * right task input/result/status/trace/display-state area
  * browser-accessible product shell

Added display-state projection:

* `ui/digital_human_shell.py`
  * reads display_state
  * projects display_state into UI shell state
  * does not mutate display_state
  * does not read runtime_state, policy, scheduler, worker, or raw tool output

Added server entry:

* `ui/digital_human_server.py`
  * standalone server path
  * does not require Flask
  * exposes `/digital-human`
  * exposes digital-human API routes for the shell

Updated:

* `ui/server.py`
  * added digital-human route compatibility

### Interaction shell additions

Enhanced the shell with product-interaction behavior:

* input area presented as a conversation flow
* frontend keeps local history
* every run becomes a run block
* persona UI status states:
  * `idle`
  * `thinking`
  * `running`
  * `blocked`
* trace output is summarized rather than dumped in full
* persona is locked as the same ZERO identity
* TTS placeholder:
  * displays `speaking...`
  * `voice_enabled: false`
  * does not connect to any speech service

### Boundaries preserved

This pass intentionally did not:

* modify core runtime
* add a new planner
* add a new worker
* change display_state schema
* connect real voice service
* add Live2D / avatar engine
* add multi-character or multi-role behavior

The product layer remains:

```text
ZERO Runtime
-> display_state
-> presentation bridge
-> digital_human_shell projection
-> digital_human UI
```

### Validation confirmed

Confirmed passing:

```text
python tests/run_digital_human_ui_shell_smoke.py
python tests/run_persona_presentation_bridge_smoke.py
python tests/run_persona_runtime_state_smoke.py
python tests/run_l5_tool_controller_core_smoke.py
python tests/run_l5_tool_decision_core_smoke.py
```

The smoke validation confirmed:

* shell projects display_state without changing schema
* shell command returns persona reply and status surface
* HTML exposes avatar, task input, result, status, and trace summary
* server exposes digital-human shell routes
* standalone server can serve shell without Flask
* presentation bridge remains stable

### Current launch path

Current startup path:

```powershell
python ui\digital_human_server.py
```

Then open:

```text
http://127.0.0.1:7861/digital-human
```

If using the virtual environment directly, the equivalent launch command is:

```powershell
.\.venv\Scripts\python.exe ui\digital_human_server.py
```

### Current limitation

The current digital-human UI shell is an interface and projection layer.

It can display and structure persona output, but the next product step is to make the UI submit tasks directly into the ZERO runtime through a controlled API route.

Recommended next pack:

```text
Digital Human Runtime Integration Pack
```

Expected boundary:

```text
UI task input
-> POST /api/digital-human/run
-> PersonaRuntimeBridge / l5-run path
-> display_state
-> UI projection
```

Still do not modify scheduler, worker, policy, or display_state schema for that step.

### Why this matters

This checkpoint turns the engineering runtime into something that can be shown and operated as a product surface.

It moves ZERO from:

```text
runtime works in terminal
```

toward:

```text
runtime can be presented as a controllable digital-human interface
```

Stable checkpoint after this pass:

* digital-human shell: working
* display-state projection: working
* interaction blocks: working
* status animation classes: working
* trace summary: working
* TTS placeholder: working
* standalone server route: working
* core runtime untouched

---

## 2026-05-02 - L4 Tool Calling Layer sealed checkpoint

This checkpoint closed the missing L4 Tool Calling Layer gap before moving into broader L5 tool expansion.

The goal was not to add more tools. The goal was to install the safe contract layer between Agent Loop / planner decisions and real tools, so future tools can be added without polluting the scheduler or hard-coding tool logic into the main task runtime.

### What was completed

Added the L4 tool schema foundation:

* `core/tools/tool_schema.py`
  * `ToolSpec`
  * `ToolParameter`
  * `ToolObservation`

Added the first controlled filesystem tool set:

* `core/tools/filesystem_tools.py`
  * `read_file`
  * `write_file`
  * `list_dir`

Added the tool execution layer:

* `core/tools/tool_executor.py`
  * schema validation
  * policy / scope guard enforcement
  * standardized observation output
  * trace output

Added the tool policy layer:

* `core/tools/tool_policy.py`
  * scope validation
  * blocked path / unsafe operation handling
  * write protection boundary

Updated the registry layer:

* `core/tools/tool_registry.py`
  * manages tool instances
  * exposes tool schemas
  * keeps tool definitions centralized

Updated tool-call compatibility:

* `core/tools/tool_call.py`
  * uses the L4 executor when a tool has a schema-backed implementation

Added repeatable validation:

* `tests/run_l4_tool_layer_smoke.py`

### Validation confirmed

Confirmed passing:

```text
[l4-tool-layer-smoke] ALL PASS
[tool-schema-smoke] PASS
[tool-policy-smoke] ALL PASS
[hybrid-demo-smoke] ALL PASS
[web-search-tool-call-smoke] ALL PASS
[persona-runtime-bridge-smoke] ALL PASS
[github-commit-tool-call-smoke] ALL PASS
```

Confirmed changed files:

```text
core/tools/filesystem_tools.py
core/tools/tool_call.py
core/tools/tool_executor.py
core/tools/tool_policy.py
core/tools/tool_registry.py
core/tools/tool_schema.py
tests/run_l4_tool_layer_smoke.py
```

### Architecture boundary preserved

The important boundary was preserved:

```text
scheduler = task scheduling / orchestration
tool layer = tool schema / policy / execution / observation
```

`scheduler.py` was not made aware of individual filesystem tools, and it did not import the L4 executor, schema, or filesystem tool implementations.

This prevents the scheduler from becoming a tool-specific dumping ground.

### L4 tool contract

The L4 Tool Calling Layer now answers these questions:

1. Which tools are available?
2. What parameters does each tool accept?
3. Is this tool call allowed under current policy / scope?
4. What was the execution result?
5. Can the result be returned as a standardized observation for the Agent Loop?

The expected contract is:

```json
{
  "ok": true,
  "tool": "read_file",
  "status": "success",
  "observation": {
    "type": "file_content",
    "summary": "read 120 chars from workspace/demo.txt",
    "content": "..."
  },
  "trace": {
    "tool_call_id": "...",
    "args": {
      "path": "workspace/demo.txt"
    },
    "duration_ms": 12
  }
}
```

Agent Loop should receive standardized observation, not raw tool output.

### What was intentionally not done

This checkpoint intentionally did not add:

* GitHub API write actions
* Web Search expansion
* browser automation
* video generation
* digital human / persona generation tools
* unrestricted shell command tools
* delete tools
* broad overwrite tools
* UI execution control

Those belong to L5+ expansion after the L4 tool contract is stable.

### Why this matters

Before this pass, ZERO had tools and task execution paths, but tool behavior could still be interpreted as system-specific logic rather than a sealed Agent-to-tool contract.

After this pass, ZERO has a dedicated tool layer that can be extended by plugin-style tools later while preserving core separation.

This moves ZERO from:

```text
system uses some tools
```

toward:

```text
Agent/runtime can call controlled tools through a standard contract
```

### Stable checkpoint after this pass

* L4 tool schema: working
* L4 tool registry: working
* L4 tool executor: working
* L4 tool policy / scope guard: working
* first filesystem tool set: working
* standardized observation: working
* trace output: working
* scheduler/tool boundary: preserved
* smoke validation: passing
* tool layer ready for next decision bridge

### Evidence kept

Keep screenshots showing:

* `run_l4_tool_layer_smoke.py` passing
* schema smoke passing
* policy smoke passing
* changed file list with the seven tool-layer files
* confirmation that scheduler stayed orchestration-only
* observation/trace result shape

### Next step

The next L5-entry step is the thin LLM Tool Decision bridge.

Do not add new tools yet.

The next step should only connect structured LLM / planner tool-call output into the existing ToolExecutor and return the standardized observation back into the loop.

---

## 2026-05-02 - L4 mainline closure and L5 entry boundary

This checkpoint records the corrected L4 status after the Tool Calling Layer was sealed.

Earlier wording treated the L4 showcase baseline as fully sealed before the tool layer was actually complete. That was too broad. The corrected status is:

```text
L4 showcase baseline was stable earlier.
L4 Tool Calling Layer was the remaining gap.
After the L4 Tool Calling Layer pass, ZERO's L4 mainline can be treated as sealed.
```

### Current L4 sealed areas

The following areas are now considered L4-sealed baseline areas:

* task lifecycle
* scheduler orchestration boundary
* execution guard / policy baseline
* runtime trace / observation baseline
* document task flows
* requirement / build demo flows
* multi-task safe execution baseline
* replan suggestion gate
* Web UI display bridge baseline
* Tool Calling Layer contract

### L4 / L5 boundary

The following items are **not** L4 debt anymore. They are L5+ expansion:

* LLM autonomous tool selection
* richer multi-tool planning
* real Web Search adapter
* GitHub inbox/outbox workflow
* controlled GitHub API actions
* browser automation
* video generation
* digital human / persona generation
* remote-control UI
* plugin marketplace / ecosystem behavior
* self-improvement loops
* multi-worker collaboration

### Practical interpretation

The L4 layer is now the safe core baseline.

The next work should not be framed as “more L4 cleanup” unless a regression is found.

From this checkpoint forward, new work should be classified as one of:

```text
L4 regression fix
L5 tool / decision expansion
L5 application demo
L6+ autonomy / multi-worker work
```

This prevents the project from constantly reopening L4 and causing the feeling that nothing is ever finished.

### Why this matters

The project had a mismatch where some core pieces were already touching L5 while the tool contract still lagged behind.

That mismatch is now corrected:

```text
core runtime: L4 sealed / L5-ready
tool layer: L4 sealed
next work: L5-entry decision bridge
```

### Stable checkpoint after this pass

* L4 mainline status: sealed
* remaining non-L4 items: reclassified as L5+
* next work direction: LLM Tool Decision bridge
* instruction for future work: do not reopen L4 unless a real regression appears

---

## 2026-05-02 - L5-entry Tool Decision bridge plan

This is the next planned step after the L4 Tool Calling Layer seal.

This checkpoint is a planning note, not a completed implementation record.

### Goal

Add the thinnest possible bridge from structured LLM / planner tool-call output to the existing L4 ToolExecutor.

The goal is:

```text
LLM/planner output -> tool decision parser -> ToolExecutor -> standardized observation -> Agent Loop / trace
```

The goal is not to add more tools.

### Scope

Allowed additions:

* `core/tools/tool_decision.py`
* `tests/run_l4_tool_decision_smoke.py`

Optional small compatibility updates only if necessary:

* `core/tools/tool_call.py`
* a thin adapter hook in `core/agent/agent_loop.py`
* a thin adapter hook in `core/tasks/scheduler.py`

### Strict limits

Do not:

* add new tools
* add Web Search
* add GitHub API
* add browser automation
* add video / digital human tools
* add shell command tools
* put tool schema or tool-specific logic into `scheduler.py`
* make scheduler know about `read_file`, `write_file`, or `list_dir`
* rewrite the existing L4 tool layer
* rewrite `agent_loop.py`
* bypass tool policy / scope guard

### Initial tool decision format

Support one small structured format first:

```json
{
  "type": "tool_call",
  "tool": "read_file",
  "args": {
    "path": "workspace/demo.txt"
  }
}
```

Optional wrapper support is acceptable if kept narrow:

```json
{
  "action": {
    "type": "tool_call",
    "tool": "write_file",
    "args": {
      "path": "workspace/out.txt",
      "content": "hello"
    }
  }
}
```

Do not turn the parser into a catch-all natural-language command interpreter.

### Acceptance criteria

The decision bridge is accepted only if:

1. legal tool-call JSON can be parsed
2. non-tool-call content is not executed
3. unknown tools return blocked/error observation
4. invalid arguments return validation error observation
5. `write_file` still follows scope / policy guard
6. executor returns standardized observation, not raw output
7. trace includes tool name, argument summary, status, and duration
8. existing L4 tool layer smoke still passes
9. scheduler remains orchestration-only and does not gain tool-specific branches

### Expected completion definition

The completion definition is:

```text
LLM does not directly operate on files.
LLM emits structured tool_call.
Tool Decision parses it.
ToolExecutor executes it under policy.
Agent Loop receives standardized observation.
```

### Why this matters

This is the first L5-entry bridge from controlled tools into actual agent behavior.

Once this is done, future tools such as web search, GitHub draft workflows, browser helpers, or media generation can be added as plugins instead of contaminating the scheduler or agent loop.

---

## 2026-05-02 - External AI/video/news intake triage note

This note records how to classify outside AI/video/news information encountered during ZERO work.

### Classification rule

When outside AI tools or market news appear, classify them into one of three buckets:

1. affects current mainline now
2. useful later / waiting list
3. market noise

### Current classification

Seedance / Higgsfield / AI video tools:

```text
bucket: useful later / waiting list
reason: useful for demo or digital-human presentation later, but not part of L4 core
```

InfiniteTalk / local talking-head video tools:

```text
bucket: useful later / waiting list
reason: possible local-first media tool later, but not stable enough for current core work
```

Big-tech AI infrastructure / military-oriented news clips:

```text
bucket: market context
reason: confirms direction toward AI as system infrastructure, but should not change today's engineering scope
```

### Current rule

Do not let external news or tool demos reopen L4 scope.

Current engineering priority remains:

```text
L4 sealed -> L5-entry Tool Decision bridge -> then controlled tool expansion
```

---

## 2026-04-29 - L4 replan suggestion gate stable baseline

This checkpoint closed the L4 recovery gate before opening true L5 automatic replanning.

The goal was not to enable automatic replan yet. The goal was to make sure failed-task recovery can be proposed, inspected, simulated, and manually approved without letting the system repair, queue, or execute actions by itself.

### What was completed

Updated the replan suggestion path:

* `core/planning/replan_suggestion.py`

Updated smoke validation:

* `tests/run_replan_suggestion_smoke.py`
* `tests/run_auto_replan_suggestion_smoke.py`
* `tests/run_replan_suggestion_actions_e2e_smoke.py`

Confirmed existing preview/control validation remains intact:

* `tests/run_replan_control_preview_smoke.py`

### Validated L4 recovery flow

The completed controlled flow is:

```text
fail -> suggestion -> preview -> dry-run -> manual approve -> queued
```

This is the stable L4 safety baseline.

### Important safety boundary

At this checkpoint, suggestion output is protective only.

```text
suggestion = propose only
preview = inspect only
dry-run = simulate only
manual approve = required gate
queued = only after approval
```

Automatic replanning remains disabled.

The smoke validation confirmed the suggestion path does not silently cross into automatic execution:

```text
would_replan: true
replanned: false
submitted: false
queued: false
ran: false
```

### Validation confirmed

Confirmed passing:

```text
run_replan_suggestion_smoke.py -> ALL PASS
run_auto_replan_suggestion_smoke.py -> L4 smoke PASS
run_replan_suggestion_actions_e2e_smoke.py -> E2E PASS
run_replan_control_preview_smoke.py -> ALL PASS
```

Confirmed end-to-end chain:

```text
fail -> suggestion -> preview -> dry-run -> manual approve -> queued
```

Confirmed the previous L4 preview/control path was not broken.

### Git checkpoints

Committed and pushed:

* `3994c4f` - Stabilize L4 replan suggestion gate
* `2f05da0` - Ignore test workspace runtime files

### Runtime workspace cleanup

During validation, `tests/workspace/` was created as local runtime/test output.

It contains generated test runtime data such as:

* cache
* logs
* memory
* runtime
* shared
* tasks
* `tasks.json`

This folder is not source code and should not be committed.

It was added to `.gitignore` so repeated smoke runs do not pollute Git status.

### Why this matters

This checkpoint marks ZERO's L4 as a stable, controlled baseline.

The system can now show a failed-task recovery path that is structured and inspectable, but still gated by human approval before queuing work.

That matters because it prevents the common failure mode where an agent jumps directly from failure into uncontrolled self-repair.

This checkpoint proves:

* failed tasks can produce structured repair suggestions
* repair suggestions can be represented as actions schema
* preview and dry-run can inspect the proposed repair
* manual approval is required before queueing
* suggestions do not automatically replan or execute
* L3/L4 control smoke paths remain stable

### Stable checkpoint after this pass

* L4 mainline: stable
* L4 replan suggestion gate: stable
* actions schema: working
* preview / dry-run / approve path: working
* end-to-end smoke: passing
* auto replan: still disabled
* runtime test workspace ignored
* GitHub main updated
* working tree expected clean after smoke artifacts are ignored

### Evidence kept

Keep screenshots showing:

* `run_replan_suggestion_smoke.py` passing
* `run_auto_replan_suggestion_smoke.py` passing
* `run_replan_suggestion_actions_e2e_smoke.py` passing
* `run_replan_control_preview_smoke.py` passing
* the end-to-end chain text:
  `fail -> suggestion -> preview -> dry-run -> manual approve -> queued`
* Git commits:
  `3994c4f` and `2f05da0`

### Next step

Do not add more L4 concepts.

The next stage is to open true L5 automatic replanning behind explicit policy control, while preserving the current L4 recovery gate as the safe baseline.

---

## 2026-04-28 - Web UI Persona Bridge display checkpoint

This checkpoint focused on connecting ZERO's local Web UI to the real workspace display state without turning the UI into an unrestricted remote-control layer.

### What was completed

Added a local Web UI backend:

* `ui/server.py`

Added a display-layer bridge:

* `core/display/ui_bridge.py`

Updated the Web UI:

* `ui/index.html`

Updated startup flow:

* `start_zero.bat`

Updated demo documentation:

* `docs/demo.md`

Added Web UI proof asset:

* `docs/demo_assets/persona_runtime/web_ui_persona_bridge_status_success_20260428.png`

### UI bridge behavior

The Web UI now uses this path:

```text
ui/index.html
  -> /api/chat
  -> ui/server.py
  -> core/display/ui_bridge.py
  -> workspace/shared + workspace/tasks
```

The UI can display:

* `status`
* `summary`
* `tasks`
* `files`

Confirmed working through browser tests:

* `status` shows current system status and recent task records
* `summary` shows the latest `*_summary.txt` content
* `tasks` shows recent task runtime state
* `files` lists recent `workspace/shared` files

### Persona Visual integration

The Web UI now includes a right-side Persona Visual panel using the existing assets under:

* `assets/persona/zero_v1/`

Current active image:

* `idle_open.png`

Background image:

* `circuit_bg.png`

Blink is currently disabled.

Reason:

* `idle_open.png`
* `idle_half.png`
* `idle_closed.png`

are not yet aligned to identical transparent canvas boundaries, crop position, character scale, and anchor position. Directly switching them in the browser causes the character to visually jump forward/backward. For the current demo, the stable open-eye frame is used.

### Layout stabilization

The Web UI layout was stabilized so that result content no longer pushes the main content panel downward.

Completed layout fixes:

* summary panel uses fixed height
* main content panel uses fixed height
* summary and main content scroll internally
* Persona Visual remains visible beside the main status panel
* UI remains stable across `status`, `summary`, `tasks`, and `files` commands

### Validation confirmed

Confirmed locally through browser UI:

* `status`: PASS
* `summary`: PASS
* `tasks`: PASS
* `files`: PASS

Confirmed Git state after completion:

* `main` up to date with `origin/main`
* working tree clean

### Git checkpoints

Committed and pushed:

* `baad703` - Add web UI persona bridge status view
* `00fb86d` - Document web UI persona bridge demo

### Why this matters

This checkpoint moves ZERO from a terminal-only demonstration path toward a presentable local UI display layer.

The important boundary is that this is currently a display/status bridge, not a full remote-control agent interface. That keeps the architecture safer while still making ZERO easier to demonstrate externally.

Current scope:

```text
Web UI -> status / workspace display bridge
```

Not yet enabled:

```text
Web UI -> unrestricted agent execution controller
```

This preserves the architectural separation between UI display, backend bridge, and core task execution.

### Stable checkpoint after this pass

* Web UI server: working
* `/api/chat` route: working
* display-layer `ui_bridge.py`: working
* `status` command: working
* `summary` command: working
* `tasks` command: working
* `files` command: working
* Persona Visual panel: working
* blink disabled for visual stability
* `docs/demo.md` updated
* proof screenshot preserved
* GitHub main updated
* working tree clean

### Evidence kept

Keep the latest Web UI screenshots showing:

* `status` success with task records visible
* `summary` success with latest summary content
* `tasks` success with task runtime records
* `files` success with shared file list
* Persona Visual displayed beside the runtime status panel

Recommended primary asset:

* `docs/demo_assets/persona_runtime/web_ui_persona_bridge_status_success_20260428.png`

### Next step

The next reasonable stage is a safe task-submission entry for the Web UI.

Recommended boundary:

* first submit into `workspace/inbox` or a controlled task-submit flow
* keep status display separate from execution control
* avoid directly wiring arbitrary Web UI input into unrestricted agent execution

---

## 2026-04-27 - Runtime-safe multi-task demo checkpoint

This checkpoint focused on turning the stabilized task execution pipeline into a repeatable multi-task demonstration.

### What was completed

Added a new demo script:

* `demos/demo_multi_task_scenario.py`

Added a repeatable smoke test:

* `tests/run_multi_task_demo_smoke.py`

Added proof screenshots:

* `docs/images/checkpoints/checkpoint_multi_task_demo_smoke_all_pass.png`
* `docs/images/checkpoints/checkpoint_queue_policy_failure_does_not_block.png`

### Demo behavior

The demo creates three tasks:

1. `A-normal`
   * writes `MULTI_DEMO_A`
   * verifies `MULTI_DEMO_A`
   * reaches `finished`

2. `B-normal`
   * writes `MULTI_DEMO_B`
   * verifies `MULTI_DEMO_B`
   * reaches `finished`

3. `C-intentional-failure`
   * verifies a missing file
   * safely moves into `replanning`
   * does not block the two normal tasks

The demo also writes:

* `workspace/shared/demo_multi_task_summary.txt`

### Validation confirmed

Confirmed on main:

* `python -m py_compile demos/demo_multi_task_scenario.py tests/run_multi_task_demo_smoke.py`
* `python tests/run_multi_task_demo_smoke.py`

Observed result:

* `[multi-task-demo] PASS`
* `[multi-task-demo-smoke] ALL PASS`

Confirmed task outcomes:

* `A-normal`: `finished`, final answer `MULTI_DEMO_A`
* `B-normal`: `finished`, final answer `MULTI_DEMO_B`
* `C-intentional-failure`: `replanning`, failure handled safely

### Why this matters

This checkpoint proves that ZERO can run a small multi-task queue scenario where a failing task does not drag down unrelated normal tasks.

This is stronger than a single-task proof because it demonstrates:

* queue coordination
* safe failure isolation
* trace-backed execution
* repeatable smoke validation
* demo-grade evidence suitable for README / public proof assets

### Result

Stable checkpoint after this pass:

* multi-task demo script: added
* multi-task smoke: added
* queue failure isolation: demonstrated
* trace evidence: available
* proof screenshots: committed
* main branch: clean and synced

\# ZERO Devlog

## 2026-04-27 - Runtime-safe multi-task execution baseline checkpoint

This checkpoint focused on stabilizing ZERO's task execution baseline after Handler / Local Observer work, multi-task queue checks, and runtime artifact safety issues surfaced during real CLI runs.

### What was completed

Stabilized the Handler / Local Observer execution path:

* normalized step handler result envelopes
* made tool / command results easier to inspect
* preserved structured stderr / error information
* added reliable trace landing for `step_start`, `step_result`, and `task_finished`
* normalized task-local trace ticks so each task records a clean `1 -> 2 -> 3` sequence while preserving `scheduler_tick` separately

Stabilized queue readiness policy:

* `created` tasks no longer run automatically
* tasks must be submitted / queued before execution
* terminal tasks are excluded from queue rebuild
* blocked / waiting tasks depend on dependency readiness
* planning / replanning / paused tasks no longer interfere with normal queued tasks
* failed or replanning tasks do not block normal queued tasks from finishing

Added runtime artifact safety guards:

* blocked self-invoking ZERO task commands such as `python app.py task run ...`
* compacted runtime persistence paths to avoid recursive task/runtime_state growth
* capped command stdout / stderr stored in result payloads
* reduced risk of `runtime_state.json`, `result.json`, and `execution_log.json` growing uncontrollably

### Problems found and resolved

During validation, an old runtime artifact was found to have grown to nearly 1 GB:

* `workspace/tasks/task_1776761962199/runtime_state.json`

This caused `task list` and `task run` to slow down or stall while scanning and deep-copying old task runtime data.

The oversized runtime artifact was moved out of the active task scan path into `workspace/artifact_backups/`, and later safety guards were added so new tasks do not repeat this pattern.

A toxic old task was also found:

* it attempted to execute `python app.py task run ...` from inside a task command step
* this could cause recursive task execution and runaway trace output

The toxic task was removed, and command/task guards now reject this class of self-invoking task command.

### Validation confirmed

Validated on `main` after merge:

* `python -m py_compile core/runtime/task_runtime.py core/runtime/task_runner.py core/tasks/execution_guard.py core/tasks/scheduler_core/command_step_helpers.py core/tasks/scheduler_core/queue_sync_helpers.py`
* `python app.py task list`
* created and ran `MAIN_SAFE_OK` task through the official task lifecycle

Confirmed final mainline task result:

* task reached `finished`
* step progress reached `3/3`
* final answer: `MAIN_SAFE_OK`

Also confirmed runtime artifact safety with a normal task:

* `ARTIFACT_SAFE_OK` task reached `finished`
* new task `runtime_state.json`, `result.json`, `execution_log.json`, and `trace.json` remained small

### Git checkpoints

Merged into `main` through these branches:

* `handler-local-observer`
* `multi-task-queue-policy`
* `runtime-artifact-safety`

Important commits:

* `09132ae` - Stabilize handler results and local observer trace
* `516939a` - Normalize task-local trace ticks
* `face037` - Tighten multi-task queue readiness policy
* `62f7b96` - Add runtime artifact safety guards

### Why this matters

This checkpoint is important because ZERO's task execution baseline is now safer and more observable.

Before this pass, the system could execute tasks, but several risks remained:

* handler outputs were less normalized
* trace tick ordering could be confusing under multi-task runs
* created tasks could be accidentally picked up by queue rebuild behavior
* old retrying / replanning tasks could interfere with queue tests
* large runtime artifacts could slow or stall the system
* command tasks could accidentally self-invoke ZERO task execution

After this pass, ZERO has a more stable foundation for multi-task demos and future AgentLoop expansion.

### Stable checkpoint after this pass

* Handler result normalization: working
* Local Observer trace landing: working
* task-local trace ticks: working
* real doc-summary demo: working
* two-task queue progression: working
* failure task does not block normal task: working
* created task does not auto-run: working
* submitted task runs normally: working
* self-invoking task command guard: working
* runtime artifact compacting: working
* main regression task: passing

### Evidence kept

Keep terminal screenshots showing:

* handler/local observer trace task finishing
* doc-summary real task demo finishing
* multi-task `MULTI_A` / `MULTI_B` finishing independently
* queue failure test not blocking `QUEUE_OK`
* trace ticks normalized to `1 -> 2 -> 3`
* oversized runtime artifact discovery and cleanup
* toxic `python app.py task run ...` task being identified
* self-invoking task command rejected
* `ARTIFACT_SAFE_OK` task finished with small runtime files
* main regression `MAIN_SAFE_OK` finished


\## 2026-04-27 - AgentLoop minimal observe-decide-act loop checkpoint

This checkpoint focused on crossing the first controlled L4 loop boundary for ZERO without changing the default scheduler behavior.

\### What was completed

Added the first minimal observe-decide-act loop path for AgentLoop:

\* observe task/runtime result
\* decide next action
\* act by running the next tick only when appropriate
\* stop safely on terminal or protected states

Added:

\* `core/agent/loop_decision.py`
\* `AgentLoop.run_task_until_terminal(...)`
\* controlled CLI entry: `python app.py task loop <task_id> [max_cycles]`

The new CLI path is explicit and does not replace:

\* `task run`
\* scheduler default behavior
\* existing task lifecycle commands

\### Decision behavior covered

The loop decision layer now records and handles:

\* `finish` -> stop
\* `continue` -> run next tick
\* `replan` -> stop at replan boundary; automatic replan is not enabled yet
\* `fail` -> stop
\* `blocked` -> stop
\* `max_cycles_reached` -> stop safely as blocked

Loop metadata is recorded into task state, including:

\* `last_decision`
\* `next_action`
\* `last_observation`
\* `loop_cycle_count`
\* `loop_history`
\* `terminal_reason`

\### Validation added

Added smoke coverage:

\* `tests/run_agent_loop_observe_decide_smoke.py`
\* `tests/run_agent_loop_until_terminal_smoke.py`
\* `tests/run_app_task_loop_cli_smoke.py`

Validation confirmed:

\* `python -m py_compile app.py`
\* `python -m py_compile core/agent/agent_loop.py`
\* `python -m py_compile core/agent/loop_decision.py`
\* `python tests/run_agent_loop_observe_decide_smoke.py`
\* `python tests/run_agent_loop_until_terminal_smoke.py`
\* `python tests/run_app_task_loop_cli_smoke.py`
\* `python tests/run_mainline_smoke.py`

Confirmed mainline result:

\* pass: 13
\* fail: 0
\* `[mainline-smoke] ALL PASS`

\### Real CLI loop proof

Confirmed the controlled CLI entry can run a real created task through the loop path:

\* created a small write-file task
\* ran it with `python app.py task loop <task_id> 5`
\* task reached `finished`
\* loop decision reached `finish`
\* task result and runtime state persisted
\* shared artifact was written under `workspace/shared/`

A separate malformed write+verify goal also safely stopped at the replan boundary, proving the loop path does not continue blindly after a failed observation.

\### Git / release checkpoint

This work was merged through PR #5:

\* branch: `agent-loop-observe-decide-act`
\* merge target: `main`
\* merge method: squash merge
\* main synced after merge
\* local and remote feature branch cleaned up

Old merged local branches also cleaned:

\* `capability-execution-poc`
\* `loop-fix-review`

Remaining active branch kept for later:

\* `display-i18n-status`

\### Why this matters

This checkpoint is important because ZERO now has a minimal controlled loop beyond one-shot execution.

Before this pass, the system could run tasks and report results, but the AgentLoop did not yet have a protected outer loop path that explicitly observed, decided, acted, and repeated under a max-cycle guard.

After this pass, ZERO has the first safe form of:

\* observe
\* decide
\* act
\* loop
\* stop safely

This is not full autonomous L4 yet. Automatic replanning is intentionally still disabled. However, the minimum loop skeleton is now present, tested, and available through an explicit CLI command.

\### Stable checkpoint after this pass

\* observe/decide metadata: working
\* minimal until-terminal loop wrapper: working
\* controlled CLI task loop entry: working
\* missing-task CLI safety: working
\* real task loop execution: working
\* replan boundary stop: working
\* mainline smoke: ALL PASS
\* PR merged into main: complete

\### Evidence kept

Keep the latest terminal screenshots showing:

\* observe/decide smoke ALL PASS
\* until-terminal smoke ALL PASS
\* task loop CLI smoke ALL PASS
\* real task loop reaching finished
\* malformed task stopping at replan
\* mainline smoke ALL PASS
\* PR #5 merged into main




\## 2026-04 Mainline Stabilization Pass



This pass focused on stabilizing the inner execution path before pushing farther into broader capability expansion.



\### Completed



\* Tool layer first-pass stabilization



&#x20; \* `core/tools/tool\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_registry.py`

&#x20; \* `core/tools/command\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_tool.py`

&#x20; \* `core/tools/file\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_tool.py`

&#x20; \* `core/tools/workspace\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_tool.py`

&#x20; \* `core/tasks/task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_paths.py`

\* Step executor first-pass outer-envelope stabilization



&#x20; \* `core/runtime/step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor.py`

\* Step handlers first-pass normalization



&#x20; \* `core/runtime/step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_handlers.py`

\* Executor first-pass internal responsibility cleanup



&#x20; \* `core/runtime/executor.py`

\* Scheduler first-pass internal responsibility cleanup



&#x20; \* `core/tasks/scheduler.py`



\### Validation Added



Tool layer validation:



\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_file\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_tool.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_workspace\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_tool.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_tool\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_registry.py`

\* `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_tool\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_layer\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



Runtime / execution validation:



\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_repair\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_rules.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_safe\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_path\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_repair.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



\### Current Validation Status



Confirmed passing during this stabilization pass:



\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_tool\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_layer\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



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



\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/queue\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_sync\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/dispatch\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/repo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_state\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/trace\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/simple\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runner\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_path\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/simple\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/command\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/llm\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`



Main scheduler remained the orchestration shell while queue sync, dispatch flow, repo/runtime sync, trace handling, simple runner flow, path handling, step execution helpers, command execution, and LLM step handling were pulled into dedicated modules.



\### Validation



This consolidation pass was validated repeatedly during each extraction step with:



\* `python tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



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

\* the active planning path was going through `core/system/llm\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_planner.py`, not only `core/planning/planner.py`

\* `{{file\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_content}}` was not reliably injected into LLM prompt templates

\* `write\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_file` with `use\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_previous\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text=true` could complete while still writing empty files

\* `task result` could show finished while the expected shared artifact was empty



\### Fixes Applied



Planning path preservation:



\* `core/system/llm\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_planner.py`

\* `core/planning/planner.py`



These changes preserved user-specified source and output paths such as:



\* `workspace/shared/input.txt`

\* `workspace/shared/summary\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v2.txt`

\* `workspace/shared/action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v2.txt`



LLM prompt injection / execution path fixes:



\* `core/runtime/step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor.py`

\* `core/tasks/scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_core/llm\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_helpers.py`

\* `core/tasks/scheduler.py`



These changes repaired the path where document content from `read\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_file` must actually reach the LLM step.



Write-back / previous-result extraction fixes:



\* `core/runtime/step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_handlers.py`



This change repaired `write\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_file` with `use\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_previous\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text=true` so the previous LLM text is actually written into the target shared file instead of producing an empty artifact.



\### Real Flow Validation



Validated with real task runs, not only smoke tests.



Confirmed working flows:



1\. Summary flow



&#x20;  \* input: `workspace/shared/input.txt`

&#x20;  \* output: `workspace/shared/summary\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v2.txt`

2\. Action items flow



&#x20;  \* input: `workspace/shared/input.txt`

&#x20;  \* output: `workspace/shared/action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v2.txt`



Confirmed behavior:



\* planner preserved the requested output path

\* task reached `finished`

\* `task result` returned the final answer

\* shared output files were actually written

\* generated artifacts matched expected document-flow behavior



\### Example Validated Outputs



Summary flow produced a real plain-text summary in `summary\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v2.txt`.



Action-items flow produced a structured plain-text result in `action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v2.txt` with:



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

\* `use\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_previous\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_text` write-back: working

\* finished task result + shared artifact output: working



\### Evidence Kept



Keep the latest terminal screenshots showing:



\* scheduler smoke + runtime smoke pass

\* summary flow finished + `summary\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v2.txt` written

\* action-items flow finished + `action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_v2.txt` written



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



&#x20;  \* goal: `read input.txt and extract action items into action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items.txt`



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

\* task workspace directory was created under `workspace/tasks/<task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id>/`

\* task reached `finished`

\* step progress reached `3/3`

\* final answer was returned through official task result reporting

\* task artifacts were written under the task directory:



&#x20; \* `result.json`

&#x20; \* `plan.json`

&#x20; \* `runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_state.json`

&#x20; \* `execution\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_log.json`

&#x20; \* `trace.json`

&#x20; \* `task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_snapshot.json`



Shared output artifacts also remained valid:



\* `workspace/shared/summary.txt`

\* `workspace/shared/action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items.txt`



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

\* `workspace/tasks/<task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id>/` directories created for the finished tasks

\* `workspace/shared/summary.txt`

\* `workspace/shared/action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items.txt`



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



\* `python app.py task doc-summary input.txt summary\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_cli.txt`

\* `python app.py task doc-action-items input.txt action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_cli.txt`



Confirmed behavior:



\* task creation succeeded

\* task reached `finished`

\* `task result` returned the expected final answer

\* task directory artifacts were created under `workspace/tasks/<task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id>/`

\* document-task behavior remained consistent with the mainline integration pass



\### Why This Matters



This pass makes document-task entry cleaner and more stable.



Before this, document-task creation depended mainly on natural-language task goals such as:



\* `summarize input.txt into summary.txt`

\* `read input.txt and extract action items into action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items.txt`



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



\* `task result <task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id>`

\* `task show <task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id>`



now display shared-scope artifacts in addition to task-local runtime files.



This means completed document tasks now expose shared outputs more directly instead of requiring the operator to remember that final artifacts are usually written under `workspace/shared/`.



\### Validation



Confirmed working on finished document tasks:



\* `task result` shows `shared\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_artifacts`

\* `task show` shows `shared\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_artifacts`



Confirmed shared-scope paths were visible in task output, including examples such as:



\* `workspace/shared/input.txt`

\* `workspace/shared/action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_cli.txt`



\### Why This Matters



Before this pass, task output mainly exposed task-local runtime files such as:



\* `result.json`

\* `plan.json`

\* `runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_state.json`

\* `execution\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_log.json`

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



\* `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_document\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



`run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_document\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py` validates both document-task flows end-to-end:



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



`run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py` was added as a higher-level validation entry for stable mainline checks.



\### Validation



Confirmed passing:



\* summary document-task smoke: PASS

\* action-items document-task smoke: PASS

\* document-task smoke overall: PASS

\* stable mainline smoke: PASS



Example outputs confirmed:



\* `summary\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.txt` created under `workspace/shared/`

\* `action\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_items\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.txt` created under `workspace/shared/`

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



This pass focused on restoring runtime validation compatibility after `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py` exposed an interface mismatch.



\### Problem



`runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke` was failing because:



\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py` called `loop.run(user\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_input)`

\* `core/agent/agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py` no longer exposed a compatible `run(...)` entry



This caused runtime validation to fail with:



\* `AttributeError: 'AgentLoop' object has no attribute 'run'`



\### Completed



`core/agent/agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py` was updated with a minimal compatibility `run(user\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_input: str)` entry.



The fix was intentionally kept small:



\* restore compatibility with test expectations

\* preserve current direct / llm / task / single-shot routing structure

\* preserve forced planner-based document-task routing

\* avoid broad restructuring of the main AgentLoop body



\### Validation



Confirmed passing after the compatibility restoration:



\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py`: PASS

\* `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`: PASS

\* `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`: PASS



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



\* Added `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* Added `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_execution\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* Folded both into `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* Verified `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py` passes end-to-end



\### Current result



\* Requirement demo smoke is now part of mainline validation

\* Execution demo smoke is now part of mainline validation

\* Mainline smoke now covers tool layer, scheduler, document task, requirement demo, and execution demo

\* Stable mainline smoke passed successfully



\### Still excluded for now



\* `runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke`

\* Reason: currently blocked by `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py`

\* Known blocker: `AttributeError: 'AgentLoop' object has no attribute 'run'`



\### Impact



\* Demo-oriented smoke checks are no longer isolated scripts only

\* They are now folded into the stable validation path

\* This improves confidence that the showcased flows are tied to the real mainline



\### Next step



\* Investigate and repair the runtime / `agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop` path

\* Unblock runtime smoke so it can eventually be folded into the mainline validation suite



\## 2026-04 Smoke Script Rename and Runner Sync Pass



This pass focused on removing naming ambiguity inside `tests/` after several manual smoke scripts were still using misleading `test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\*.py` names.



\### Problem



Some files under `tests/` looked like pytest tests by name, but were actually direct-execution smoke scripts with `main()` entrypoints.



This created two kinds of confusion:



\* operators could incorrectly try to run them with pytest

\* smoke runners could drift behind after renames and start referencing missing files



The most visible cases were:



\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



\### Completed



Renamed manual smoke / diagnostic scripts to `run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\*.py` naming:



\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py` -> `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py` -> `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py` -> `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_reflection.py` -> `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_reflection.py`



Updated smoke runners to follow the renamed paths:



\* `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



\### Validation



Confirmed passing after rename and runner sync:



\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



Confirmed result:



\* runtime smoke: PASS

\* mainline smoke: PASS

\* renamed scheduler smoke path: PASS

\* renamed agent loop smoke path: PASS



\### Why This Matters



This pass did not add new capability.



Its value was reducing test/smoke-role ambiguity inside the repository and keeping validation entrypoints aligned with what the files actually are.



That matters because the repository now separates these categories more clearly:



\* `test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\*.py` for real test-style checks

\* `run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\*.py` for direct-execution smoke and diagnostic scripts



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



This pass focused on reducing responsibility mixing inside `core/agent/agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py` without breaking the current mainline validation chain.



\### Problem



`agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py` had started accumulating too many different kinds of responsibilities in one file:



\* route / mode policy decisions

\* component invocation compatibility glue

\* document-flow trace writing

\* main control flow for direct / llm / task / single-shot paths



This increased the risk that future changes would keep adding more special-case logic into the main loop body.



\### Completed



Three focused extractions were completed.



\#### 1. Route policy extraction



Added:



\* `core/agent/agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_route\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_policy.py`



Moved route / mode decision rules out of the main loop, including:



\* document-flow forced planner detection

\* summary/action-items document-flow matching

\* explicit task-request detection

\* task-mode entry decision



\#### 2. Component invocation adapter extraction



Added:



\* `core/agent/agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_component\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_invoker.py`



Moved callable compatibility / adapter glue out of the main loop, including:



\* router invocation

\* planner invocation

\* llm planner invocation

\* step executor invocation

\* verifier / safety guard wrapper calls



\#### 3. Document flow trace writer extraction



Added:



\* `core/agent/document\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_flow\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_trace\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_writer.py`



Moved document-flow trace generation / payload extraction / runtime-info collection out of the main loop.



\### Validation



Confirmed passing after each extraction step:



\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



Confirmed result after the cleanup sequence:



\* runtime smoke: PASS

\* mainline smoke: PASS

\* agent loop smoke: PASS



\### Why This Matters



This pass did not primarily add new user-facing capability.



Its value was structural:



\* `agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py` is now closer to a true orchestration shell

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

\* `core/planning/planner\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_rule\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_parser.py`

\* `core/agent/agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop.py`

\* `core/runtime/step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor.py`

\* `core/tasks/execution\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_guard.py`



What changed:



\* planner result contract was stabilized

\* agent loop response / execution contract was stabilized

\* step executor envelope and batch contract were stabilized

\* guard command policy was repaired to allow trusted python mainline/demo execution while still blocking non-whitelisted command execution

\* requirement demo mainline command path was repaired after guard blocking surfaced during smoke validation



\### Validation confirmed



Confirmed passing after the stabilization sequence:



\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/test\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_step\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_executor.py`

\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_agent\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_loop\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`

\* `python tests/run\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_scheduler\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke.py`



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



\* `workspace/shared/project\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_summary.txt`

\* `workspace/shared/implementation\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_plan.txt`

\* `workspace/shared/acceptance\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_checklist.txt`



Requirement demo assets were organized under:



\* `demos/07\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo/requirement\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_execution\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_pass\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_2026-04-20.mp4`

\* `demos/07\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo/requirement\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_outputs\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_2026-04-20.mp4`



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



\* `checkpoint\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mainline\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_all\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_pass.png`

\* `checkpoint\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_runtime\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_smoke\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_pass.png`

\* `checkpoint\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_pass.png`

\* `checkpoint\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_requirement\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_outputs.png`

\* `checkpoint\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_execution\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_pass.png`

\* `checkpoint\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_os\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_integration\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_tests\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_passed.png`



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

\* `workspace/shared/numbers\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_input.txt`



The requirement defines a small engineering build task around a statistics utility.

The numbers input provides the fixed data used for execution verification.



\### Generated outputs



Validated mini-build outputs now include:



\* `workspace/shared/project\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_summary.txt`

\* `workspace/shared/implementation\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_plan.txt`

\* `workspace/shared/acceptance\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_checklist.txt`

\* `workspace/shared/number\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_stats.py`

\* `workspace/shared/stats\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_result.txt`



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



\* generated `number\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_stats.py`

\* generated `stats\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_result.txt`

\* verified statistics output

\* `\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\[mini-build-demo] PASS`



\### Showcase assets organized



Mini-build demo assets were organized under:



\* `demos/08\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mini\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_build\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo/mini\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_build\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_execution\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_pass\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_2026-04-20.mp4`



A dedicated checkpoint image should be kept as:



\* `docs/images/checkpoints/checkpoint\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_mini\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_build\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_demo\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_pass.png`



\### Documentation alignment



Public-facing documentation was extended to include this new showcase.



Updated / to update together:



\* `README.md`

\* `docs/demo.md`

\* `docs/proof\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_map.md`

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



\* `execution\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_trace` remained at the outer step result layer

\* nested inner `execution\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_trace` was removed

\* summary flow completed successfully under manual ticks

\* runtime state stayed inspectable after the trace cleanup pass



\### v32 step 1



Command execution cwd policy was repaired.



Confirmed:



\* command execution no longer defaulted into `workspace/tasks/<task\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_id>/`

\* command execution now runs from project root when no explicit command cwd is provided

\* `python app.py ...` style command tasks no longer fail due to missing `app.py`



\### v32 step 2



Command result contract was cleaned and made more explicit.



Confirmed:



\* original step payload is preserved without misleading execution-only cwd fields

\* actual command execution cwd is explicitly recorded as `effective\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\_cwd`

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
* `task\\\_type`
* `mode`
* `pipeline\\\_name`
* `execution\\\_name`

Confirmed document pipeline set:

* `doc\\\_summary` -> `summary\\\_pipeline`
* `doc\\\_action\\\_items` -> `action\\\_items\\\_pipeline`
* `doc\\\_requirement` -> `requirement\\\_pipeline`

### What was repaired

This pass fixed two important document-task consistency problems:

1. Metadata persistence consistency
* document pipeline identity is now persisted across:

  * `task\\\_snapshot.json`
  * `runtime\\\_state.json`
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
  * `task\\\_type`
  * `mode`
  * `pipeline\\\_name`
  * `execution\\\_name`
* `task result` displays:

  * `scenario`
  * `task\\\_type`
  * `mode`
  * `pipeline\\\_name`
  * `execution\\\_name`

Confirmed stable identity after finished execution for:

* summary pipeline
* action-items pipeline
* requirement pipeline

Confirmed requirement pipeline now remains:

* `scenario: doc\\\_requirement`
* `task\\\_type: document`
* `mode: requirement`
* `pipeline\\\_name: requirement\\\_pipeline`
* `execution\\\_name: requirement\\\_execution`

even after a separated:

* `task submit <task\\\_id>`
* `task run <task\\\_id>`

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

* `python -m py\\\_compile app.py`
* `python tests/run\\\_mainline\\\_smoke.py`

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

* `python -m py\\\_compile app.py` passing after cleanup
* `python tests/run\\\_mainline\\\_smoke.py` returning ALL PASS after cleanup
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

* `workspace/shared/project\\\_summary.txt`
* `workspace/shared/implementation\\\_plan.txt`
* `workspace/shared/acceptance\\\_checklist.txt`
* `workspace/shared/number\\\_stats.py`
* `workspace/shared/stats\\\_result.txt`

### Validation added

Added:

* `tests/run\\\_full\\\_build\\\_demo\\\_smoke.py`

This smoke validates:

* `python main.py full-build-demo`
* planning artifacts exist and are non-empty
* generated script exists
* `stats\\\_result.txt` exists and is non-empty
* verified numeric outputs:

  * `sum: 100`
  * `average: 25`
  * `max: 40`
  * `min: 10`

### Smoke integration

`run\\\_full\\\_build\\\_demo\\\_smoke.py` was folded into:

* `tests/run\\\_mainline\\\_smoke.py`

This means the representative requirement -> build -> execute -> verify chain is now part of protected mainline validation instead of being only a manual demo path.

### Requirement smoke hardening

During fold-in, the older requirement smoke was exposed as too brittle because it depended on exact wording such as `Deliverable` in `acceptance\\\_checklist.txt`.

`tests/run\\\_requirement\\\_demo\\\_smoke.py` was updated to validate more stable workflow signals instead:

* command success
* non-empty artifact generation
* stable section checks such as:

  * `Acceptance`
  * `Verification`

instead of overfitting to one exact phrasing.

### Validation confirmed

Confirmed passing after integration:

* `python tests/run\\\_requirement\\\_demo\\\_smoke.py`
* `python tests/run\\\_full\\\_build\\\_demo\\\_smoke.py`
* `python tests/run\\\_mainline\\\_smoke.py`

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
* `python tests/run\\\_full\\\_build\\\_demo\\\_smoke.py` ALL PASS
* `python tests/run\\\_requirement\\\_demo\\\_smoke.py` ALL PASS
* `python tests/run\\\_mainline\\\_smoke.py` ALL PASS after fold-in

## 2026-04-23 - Full-build demo upgraded to system-task path

This checkpoint upgraded the full-build representative workflow from a helper-written implementation artifact into a system-task-generated implementation artifact, and then verified that the workflow still passed under smoke protection and mainline validation.

### What changed

The previous `full-build-demo` flow still depended on a direct helper write for `number\\\_stats.py`.

This pass replaced that behavior with a formal task path:

* `task implementation-proof`

That task now generates:

* `workspace/shared/number\\\_stats.py`

through the normal task system instead of writing the implementation artifact directly inside `main.py`.

### Key engineering fix

The main issue was not the planner response itself.

At create time, the structured implementation plan was already visible, but submit/run still fell back to the old generic planning path.

This was fixed by making the structured plan persist into the actual task state consumed by runtime execution, including:

* `planner\\\_result`
* `steps`
* `steps\\\_total`
* `current\\\_step\\\_index`
* reset execution/result fields for the created task
* synchronized task persistence into repo-backed task state and task artifacts such as `plan.json` / `task\\\_snapshot.json`

After this fix, `implementation-proof` executed as the intended 2-step structured plan:

1. `write\\\_file shared/number\\\_stats.py`
2. `verify shared/number\\\_stats.py contains "stats\\\_result.txt"`

instead of falling back into the broken 4-step generic path.

### Escaping / script-content fix

The generated `number\\\_stats.py` content was also corrected so the written script preserves:

* `"\\\\n".join(...)`
* `+ "\\\\n"`

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
* `python tests/run\\\_full\\\_build\\\_demo\\\_smoke.py`
* `python tests/run\\\_mainline\\\_smoke.py`

Observed results:

* `\\\[full-build-demo] PASS`
* `\\\[full-build-demo-smoke] ALL PASS`
* `\\\[mainline-smoke] ALL PASS`

### Why this checkpoint matters

This is a stronger checkpoint than the previous helper-based version.

The value is that the representative workflow is no longer:

* planning -> helper-written script -> execution

It is now:

* planning -> system-task-generated implementation artifact -> execution

That makes the workflow more representative of the intended engineering-agent path and more defensible as a real system capability instead of a stitched demo path.

### Evidence kept

Keep these screenshots:

* `checkpoint\\\_full\\\_build\\\_demo\\\_pass.png`
* `checkpoint\\\_mainline\\\_smoke\\\_all\\\_pass\\\_after\\\_full\\\_build.png`

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

* `tests/run\\\_implementation\\\_proof\\\_smoke.py`

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

  * `workspace/shared/number\\\_stats.py`

It also validates stable script content markers such as:

* `from pathlib import Path`
* `numbers\\\_input.txt`
* `stats\\\_result.txt`
* `"\\\\n".join(...)`

### Mainline integration

`tests/run\\\_implementation\\\_proof\\\_smoke.py` was folded into:

* `tests/run\\\_mainline\\\_smoke.py`

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
* `python tests/run\\\_implementation\\\_proof\\\_smoke.py`
* `python tests/run\\\_full\\\_build\\\_demo\\\_smoke.py`
* `python tests/run\\\_mainline\\\_smoke.py`

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

* `checkpoint\\\_full\\\_build\\\_demo\\\_pass.png`
* `checkpoint\\\_mainline\\\_smoke\\\_all\\\_pass\\\_after\\\_full\\\_build.png`

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

* `ui/persona\\\_runtime\\\_window.py`

Added persona visual support and assets:

* `assets/persona/zero\\\_v1/profile.json`
* `assets/persona/zero\\\_v1/circuit\\\_bg.png`
* `assets/persona/zero\\\_v1/idle\\\_open.png`
* `assets/persona/zero\\\_v1/idle\\\_half.png`
* `assets/persona/zero\\\_v1/idle\\\_closed.png`
* `core/persona/visual\\\_profile.py`

Added validation coverage:

* `tests/run\\\_persona\\\_visual\\\_profile\\\_smoke.py`

Updated public-facing showcase documentation:

* `README.md`
* `docs/demo\\\_assets/persona\\\_runtime/persona\\\_runtime\\\_v1\\\_visual\\\_ready.png`
* `docs/demo\\\_assets/persona\\\_runtime/persona\\\_runtime\\\_v2\\\_execution\\\_demo\\\_success.png`

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

* `docs/demo\\\_assets/persona\\\_runtime/persona\\\_runtime\\\_v1\\\_visual\\\_ready.png`
* `docs/demo\\\_assets/persona\\\_runtime/persona\\\_runtime\\\_v2\\\_execution\\\_demo\\\_success.png`



## 2026-04-24 - Persona Runtime multi-step demo checkpoint

This checkpoint focused on extending the Persona Runtime window from a single execution-demo showcase into a visible multi-step document-flow showcase.

### What was completed

Added a new Persona Runtime UI action:

* `Run Multi-Step Demo`

Added a matching persona command path:

* `run multi-step-demo`

The new multi-step demo is routed through the existing document demo flow so the Persona Runtime window can now display a document-oriented multi-step capability instead of only the smaller execution-demo path.

Updated files:

* `ui/persona\_runtime\_window.py`
* `core/persona/chat\_shell.py`

Added new showcase evidence:

* `docs/demo\_assets/persona\_runtime/persona\_runtime\_v3\_multistep\_demo\_success.png`

### Validation confirmed

Confirmed manually through the Persona Runtime window:

* `Run Multi-Step Demo` button is visible
* `run multi-step-demo` command is accepted from the chat input
* runtime state updates to `SUCCESS`
* last capability updates to `multi-step-demo`
* last result updates to `success`
* output hints show:

  * `workspace/shared/summary\_demo.txt`
  * `workspace/shared/action\_items\_demo.txt`
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

* `docs/demo\_assets/persona\_runtime/persona\_runtime\_v3\_multistep\_demo\_success.png`



## 2026-04-24 - Persona Agent Orchestrator POC checkpoint

This checkpoint focused on moving Persona Runtime beyond fixed script-level demo flows toward a first deterministic agent-level orchestration proof.

### What was completed

Added a new deterministic persona agent orchestrator:

* `core/persona/persona_agent_orchestrator.py`

Added a Persona shell command path:

* `run agent-demo`

Updated Persona Runtime / shell integration through:

* `core/persona/chat_shell.py`

Added regression protection:

* `tests/run_persona_agent_demo_smoke.py`

Added showcase evidence:

* `docs/demo_assets/persona_runtime/persona_runtime_v5_agent_demo_success.png`

### What the agent-demo now performs

The new `agent-demo` flow performs a small but important orchestration chain:

1. receive a goal
2. classify the goal deterministically
3. select the document summary + action-items task path
4. create an official `doc-summary` task
5. run the summary task through the task lifecycle
6. create an official `doc-action-items` task
7. run the action-items task through the task lifecycle
8. verify shared output artifacts
9. return a combined PASS result with task IDs and artifact paths

Confirmed generated artifacts:

* `workspace/shared/persona_agent_summary.txt`
* `workspace/shared/persona_agent_action_items.txt`

### Validation confirmed

Confirmed through direct orchestrator execution:

* `python core/persona/persona_agent_orchestrator.py`

Confirmed through Persona Runtime:

* `run agent-demo` can be triggered from the Persona Runtime command input
* runtime state updates to `SUCCESS`
* last capability updates to `agent-demo`
* output hints show the persona agent shared artifacts
* chat output shows verified artifacts, task lifecycle, task IDs, and `[agent-demo] PASS`

Confirmed through smoke validation:

* `python tests/run_persona_agent_demo_smoke.py`

Smoke confirmed:

* `selected_plan: document_summary_and_action_items`
* `[agent-demo] task lifecycle`
* `[agent-demo] PASS`
* `persona_agent_summary.txt` exists and is non-empty
* `persona_agent_action_items.txt` exists and is non-empty

Confirmed repository updates:

* orchestrator POC pushed to GitHub main at commit `899eb9d`
* Persona Runtime `run agent-demo` command connected at commit `5de6358`
* persona agent demo smoke pushed at commit `5f90cbf`

### Why this matters

This checkpoint is different from the earlier Persona Runtime multi-step demo.

The earlier multi-step demo was still a fixed script-level flow:

* known button
* known document demo path
* known outputs
* PASS

The new agent-demo adds a first deterministic orchestration layer:

* goal
* classify
* choose task path
* create official tasks
* run official tasks
* verify artifacts
* return combined result

This is not full autonomous tool selection yet, but it is a cleaner bridge between scripted demos and future agent-level tool orchestration.

### Stable checkpoint after this pass

* deterministic persona agent orchestrator: added
* `run agent-demo` command: connected
* Persona Runtime can trigger agent-demo: working
* official doc-summary task lifecycle: working
* official doc-action-items task lifecycle: working
* artifact verification: working
* persona agent demo smoke: passing
* v5 screenshot evidence: added
* GitHub main push: complete

### Evidence kept

Keep these proof points:

* `docs/demo_assets/persona_runtime/persona_runtime_v5_agent_demo_success.png`
* latest terminal screenshot showing `python tests/run_persona_agent_demo_smoke.py` returning `ALL PASS`

## 2026-04-24 - Document Flow Showcase mainline checkpoint

This checkpoint focused on turning the existing document-flow capability into a fixed mainline showcase path and then folding that showcase into protected mainline validation.

### What was completed

Added a new formal main entry:

* `python main.py document-flow-demo`

Added a fixed document-flow showcase inside:

* `core/capabilities/demo_flows.py`

Updated the unified entry layer:

* `main.py`

Added dedicated regression protection:

* `tests/run_document_flow_showcase_smoke.py`

Folded the new smoke into the stable mainline validation path:

* `tests/run_mainline_smoke.py`

### What the document-flow-demo performs

The new document-flow showcase performs a fixed, repeatable document-processing chain:

1. prepare a fixed input file
2. create an official `doc-summary` task
3. submit and run the summary task through the task lifecycle
4. create an official `doc-action-items` task
5. submit and run the action-items task through the task lifecycle
6. verify both shared output artifacts
7. print task lifecycle IDs and report `PASS`

Confirmed generated artifacts:

* `workspace/shared/document_flow_input.txt`
* `workspace/shared/document_flow_summary.txt`
* `workspace/shared/document_flow_action_items.txt`

### Validation confirmed

Confirmed direct showcase execution:

* `python main.py document-flow-demo`

Confirmed result:

* `[document-flow-demo] PASS`
* summary task lifecycle ID printed
* action-items task lifecycle ID printed
* `document_flow_summary.txt` generated
* `document_flow_action_items.txt` generated

Confirmed dedicated smoke execution:

* `python tests/run_document_flow_showcase_smoke.py`

Smoke confirmed:

* `[document-flow-demo] task lifecycle`
* `[document-flow-demo] PASS`
* `summary_task_id: task_...`
* `action_items_task_id: task_...`
* document-flow input artifact exists and is non-empty
* document-flow summary artifact exists and is non-empty
* document-flow action-items artifact exists and is non-empty

Confirmed mainline smoke integration:

* `python tests/run_mainline_smoke.py`
* `python main.py smoke`

Mainline smoke confirmed:

* `document flow showcase smoke`: PASS
* `pass: 13`
* `fail: 0`
* `missing_required: 0`
* `skip_optional: 0`
* `[mainline-smoke] ALL PASS`

Confirmed repository update:

* document-flow showcase demo pushed to GitHub main at commit `0a044f3`
* document-flow showcase smoke folded into mainline at commit `1f9e35c`

### Why this matters

This checkpoint separates the document-flow showcase from the Persona Runtime / UI line.

The Persona work proved that a visual runtime can surface execution and agent-demo state. This checkpoint returns the focus to the core document-processing capability and gives it a stable, repeatable, non-UI mainline entry.

The important distinction is:

* `doc-demo` remains a simple existing document demo path
* `document-flow-demo` is now the fixed mainline showcase path
* `run_document_flow_showcase_smoke.py` protects that showcase directly
* `run_mainline_smoke.py` now protects it as part of the broader stable validation chain

This makes document flow easier to demonstrate, easier to validate, and harder to regress accidentally.

### Stable checkpoint after this pass

* `document-flow-demo` entry: added
* fixed document-flow input: added
* summary task lifecycle through official task path: working
* action-items task lifecycle through official task path: working
* shared document-flow artifacts: verified
* dedicated document-flow showcase smoke: passing
* document-flow showcase smoke folded into mainline: complete
* mainline smoke after fold-in: ALL PASS

### Evidence kept

Keep the latest terminal screenshots showing:

* `python main.py document-flow-demo` returning `PASS`
* `python tests/run_document_flow_showcase_smoke.py` returning `ALL PASS`
* `python tests/run_mainline_smoke.py` / `python main.py smoke` showing `document flow showcase smoke` and `ALL PASS`



---

## 2026-05-11 - Patch Runtime Transaction / Verification Boundary Seal checkpoint

This checkpoint sealed ZERO's controlled patch runtime execution boundary on branch:

```text
runtime-repair-transaction-layer
```

The goal was not unrestricted self-modification.

The goal was to establish a deterministic patch transaction runtime with:

```text
preflight
-> transaction
-> backup snapshot
-> atomic apply
-> verify boundary
-> rollback recovery
-> regression seal
```

### Completed layers

Added and stabilized:

* patch dependency / preflight analysis
* repo source confirmation gate
* transaction metadata lifecycle
* backup snapshot handling
* atomic multi-file apply
* verify / commit boundary
* rollback recovery
* regression seal coverage
* mutation boundary scaffold

### Runtime flow

Successful path:

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

### Metadata layers preserved

The runtime now preserves independent:

```text
preflight metadata
transaction metadata
verify metadata
rollback metadata
```

Important architectural boundary:

```text
guard = gate
executor = execution
verify = boundary
transaction = state
```

This prevents scheduler responsibility collapse and reduces the risk that rollback, verification, execution, and policy become one tangled runtime path.

### Validation confirmed

Confirmed passing through compile + manual harness validation:

```text
tests/test_apply_patch_transaction_layer.py
tests/test_step_executor.py
```

Validated behaviors:

* apply_patch handler remains registered
* no unsupported step type regression
* committed only appears after verify pass
* rollback restores original file contents
* multi-file rollback leaves no half-applied state
* repo_source unconfirmed remains blocked
* repo_source confirmed still requires verify before commit

### Git checkpoint

Merged into:

```text
main
```

through PR:

```text
#7
```

Merge title:

```text
Seal patch runtime transaction and verification boundary
```

### Why this matters

This checkpoint moves ZERO from:

```text
AI patch application
```

toward:

```text
transactional engineering runtime
```

The important result is not only patch execution.

The important result is that execution, verification, rollback, replay, and future governance layers now have a deterministic runtime boundary instead of being mixed directly into scheduler logic.

---

## 2026-05-11 - Scheduler Pure Helper Extraction checkpoint

This checkpoint records the first safe scheduler extraction passes after the runtime transaction / verification boundary seal.

The goal was not to broadly split `core/tasks/scheduler.py`.

The goal was to prove that a small, low-risk extraction path can move pure helper logic into `scheduler_core/` without changing runtime behavior, task lifecycle semantics, execution dispatch, queue behavior, or the recently sealed transaction / verify / rollback chain.

### What was completed

Added:

* `core/tasks/scheduler_core/pure_helpers.py`

Extracted pure helper logic from `core/tasks/scheduler.py`:

* `_safe_int_for_runtime_gate`
* `_extract_task_id`
* `_strip_quotes`
* `_extract_file_path`
* `_canonicalize_steps_for_compare`

Completed commits:

```text
08b2d22 - refactor: extract scheduler pure helpers
de839f5 - refactor: extract scheduler canonicalize helper
```

### Boundary preserved

This extraction intentionally did not touch:

```text
NO execution dispatch extraction
NO queue lifecycle extraction
NO task state transition rewrite
NO planner fallback rewrite
NO repair / replan chain extraction
NO transaction / verify / rollback changes
NO StepExecutor changes
NO ExecutionGuard changes
NO runtime mutation behavior changes
```

Scheduler still remains the orchestration surface.

The new helper module is limited to pure utility behavior and must remain free of:

```text
Scheduler state
StepExecutor
ExecutionGuard
transaction logic
verify logic
rollback logic
queue mutation
persistence side effects
```

### Validation confirmed

Confirmed passing:

```text
python -m py_compile core/tasks/scheduler.py core/tasks/scheduler_core/pure_helpers.py
python tests/test_step_executor.py
```

Observed result:

```text
PASS: test_step_executor.py
working tree clean
```

### Why this matters

This is the first real scheduler extraction after the runtime seal.

It matters because it proves that scheduler reduction can proceed through small, reversible, behavior-preserving steps instead of large risky rewrites.

The first attempted broader extraction correctly stopped when helper candidates were found to still reference scheduler state. The final accepted extraction only moved helpers with no `self` dependency and no repair / replan / transaction coupling.

### Stable checkpoint after this pass

* `pure_helpers.py`: added
* small pure helper extraction: working
* scheduler import / wrapper forwarding: working
* StepExecutor contract: preserved
* unsupported step type contract: preserved
* transaction / verify / rollback chain: untouched
* main branch: clean and pushed

### Next step

Do not continue random helper extraction.

The next extraction target must be selected only after confirming:

```text
no self state dependency
no repair / replan coupling
no transaction / verify / rollback coupling
no queue lifecycle mutation
no persistence write path
```

Recommended next move:

```text
pause extraction or perform another target scan before any third extraction
```


---

## 2026-05-11 - Scheduler Path Parser Helper Extraction checkpoint

This checkpoint records the safe extraction of path/text parser helper logic from:

```text
core/tasks/scheduler.py
```

into:

```text
core/tasks/scheduler_core/path_parser_helpers.py
```

### What was extracted

The following helper functions were moved out of the main scheduler orchestration shell:

* `_extract_python_file_paths`
* `_is_shared_like_path`
* `_strip_markdown_code_fences`
* `_extract_all_document_file_paths`
* `_extract_document_arrow_paths`

The extraction preserved the scheduler boundary:

```text
scheduler = orchestration shell
path_parser_helpers = pure parsing / normalization helpers
```

### Boundary preserved

This extraction intentionally did not modify:

```text
queue lifecycle
execution dispatch
repair / replan flow
transaction logic
verify / rollback logic
StepExecutor behavior
ExecutionGuard behavior
```

The extracted helper module remains free of:

```text
Scheduler state mutation
queue mutation
execution dispatch
transaction side effects
verify / rollback side effects
persistence side effects
```

### Validation confirmed

Confirmed passing:

```text
python -m py_compile core/tasks/scheduler.py core/tasks/scheduler_core/path_parser_helpers.py core/tasks/scheduler_core/pure_helpers.py
python tests/test_step_executor.py
```

Observed result:

```text
PASS: test_step_executor.py
working tree clean
```

### Git checkpoint

Committed and pushed on `main`:

```text
6f5800b - refactor: extract scheduler path parser helpers
```

### Why this matters

This pass continues the scheduler responsibility-reduction work without destabilizing runtime behavior.

The important result is not user-facing capability. The important result is that parser / normalization logic is no longer accumulating inside the main scheduler orchestration file.

This reduces future refactor risk and keeps extraction boundaries explicit:

```text
scheduler = orchestration
helpers = deterministic utility behavior
```

### Stable checkpoint after this pass

* path parser helper extraction: working
* scheduler compile validation: working
* StepExecutor regression: PASS
* runtime behavior unchanged
* working tree clean after validation

### Next step

Before additional extraction passes:

```text
pause
-> regression validation
-> inspect next extraction target carefully
-> avoid moving stateful scheduler behavior into helper modules
```


---

## 2026-05-11 - Planning Parser Extraction Attempt rejected checkpoint

This checkpoint records a rejected scheduler extraction attempt during the parsing-helper phase.

The attempted target was:

```text
core/tasks/scheduler_core/planning_parser_helpers.py
```

Candidate helpers inspected:

```text
_normalize_verify_step
_extract_function_name_for_fix
_try_plan_read_file
```

### Result

The extraction was reverted.

No source code changes were committed.

The repository returned to:

```text
working tree clean
```

### Why it was rejected

The attempted extraction used an automated AST/unparse script.

That approach proved unsafe for this candidate group because the target helper bodies contain Chinese patterns / Chinese keyword strings and planner-facing regex logic.

The generated helper file showed encoding damage / broken string content in planner parsing logic.

This was unacceptable because the affected helpers sit near:

```text
verify-step normalization
function-repair targeting
read-file planning intent
planner / step-schema semantics
```

### Boundary preserved

The revert preserved:

```text
No scheduler.py behavior change
No planner behavior change
No verify-step parser change
No command/read/write planning change
No StepExecutor change
No ExecutionGuard change
No transaction / verify / rollback change
```

### Rule added

Do not use automated AST/unparse extraction for scheduler helpers that contain:

```text
Chinese strings
localized command keywords
planner intent patterns
regex-heavy semantic parsing
step-schema construction
repair targeting rules
```

Those helpers require manual full-file extraction, exact string preservation, and dedicated regression tests.

### Next step

Do not retry this extraction immediately.

Before touching this area again:

```text
1. Print the exact source bodies.
2. Manually preserve all string literals.
3. Add or identify planner/parser regression coverage.
4. Extract only one narrow helper group.
5. Compile and run StepExecutor smoke.
6. Prefer full-file overwrite over patch fragments.
```

Current conclusion:

```text
pure_helpers extraction: accepted
path_parser_helpers extraction: accepted
planning_parser_helpers extraction: rejected / reverted
```


---

## 2026-05-11 - Regression Coverage Phase v1 checkpoint

This checkpoint records the first formal regression gate added after the scheduler helper extraction and runtime execution boundary work.

The goal was not to add scattered tests.

The goal was to create a small repeatable regression contract pack that protects the current scheduler/helper/runtime boundaries before any further extraction or refactor work.

### What was added

Added scheduler/parser regression coverage:

```text
tests/test_scheduler_parser_helpers.py
```

Added runtime execution contract coverage:

```text
tests/test_runtime_execution_contracts.py
```

Added one entrypoint for the current regression pack:

```text
tests/run_regression_contracts.py
```

### Coverage included

Scheduler/parser regression coverage currently protects:

```text
path parser helpers
pure helpers
planning parser behavior that remains inside Scheduler
scheduler parser semantics
```

Runtime execution contract coverage currently protects:

```text
unsupported step type contract
execute_steps failure contract
execute_steps empty contract
apply_patch handler registration
```

### Validation confirmed

Confirmed passing:

```text
python tests/test_scheduler_parser_helpers.py
python tests/test_runtime_execution_contracts.py
python tests/run_regression_contracts.py
```

Observed result:

```text
tests/test_scheduler_parser_helpers.py: 13 tests OK
tests/test_runtime_execution_contracts.py: 4 tests OK
tests/run_regression_contracts.py: ALL PASS, 2 test files
```

### Git checkpoint

Committed and pushed on `main`:

```text
8633fe6 - test: add scheduler and runtime regression contracts
```

### Why this matters

This checkpoint turns the recent scheduler extraction work from manual confidence into a repeatable safety gate.

The important result is that future scheduler/helper/runtime changes now have a small contract layer to catch regressions before more extraction work continues.

This protects:

```text
scheduler orchestration boundary
pure helper behavior
path parser helper behavior
planning parser behavior still inside Scheduler
StepExecutor unsupported-step behavior
StepExecutor empty execution behavior
apply_patch handler availability
```

### Stable checkpoint after this pass

* scheduler/parser regression tests: working
* runtime execution contract tests: working
* regression runner: working
* current regression gate: ALL PASS
* working tree clean after commit/push

### Next step

Do not continue broad scheduler extraction immediately.

Recommended next phase:

```text
Regression Coverage Phase v2
```

Scope should remain narrow:

```text
add tests only when they protect an actual extraction/refactor boundary
avoid speculative contract assertions not matching current runtime behavior
do not force runtime code to satisfy imagined contracts
```

The previous failed expansion attempt showed that runtime contract tests must describe the existing stable contract first, not an idealized future contract.

---

## 2026-05-11 - Regression Coverage Phase v2 checkpoint

This checkpoint records the stabilization of the scheduler/runtime regression safety layer after the earlier parser-helper extraction work.

The goal of this phase was not to expand capability. The goal was to establish repeatable regression contracts before continuing deeper scheduler decomposition.

### What was completed

Added and stabilized regression coverage for:

* scheduler parser helpers
* runtime execution result normalization
* scheduler extraction boundary protection

Added:

* `tests/test_scheduler_parser_helpers.py`
* `tests/test_runtime_execution_contracts.py`
* `tests/test_scheduler_extraction_boundary.py`
* `tests/run_regression_contracts.py`

### Regression contracts established

The regression runner now validates:

```text
tests/test_scheduler_parser_helpers.py
tests/test_runtime_execution_contracts.py
tests/test_scheduler_extraction_boundary.py
```

The consolidated regression gate is:

```text
python tests/run_regression_contracts.py
```

### Parser helper coverage

Validated extraction/runtime helper behavior for:

```text
_extract_python_file_paths
_is_shared_like_path
_strip_markdown_code_fences
_extract_all_document_file_paths
_extract_document_arrow_paths
_normalize_verify_step
_extract_function_name_for_fix
_try_plan_read_file
```

Confirmed helper extraction preserves existing scheduler behavior.

### Runtime execution contracts

Validated execution result normalization for:

```text
unsupported step type
failure indexing
success normalization
empty execute_steps flow
```

The runtime contract layer now guarantees deterministic result envelopes for regression validation.

### Scheduler extraction boundary coverage

Validated scheduler extraction boundaries to ensure:

```text
helper modules remain stateless
no queue mutation leaks
no runtime side effects
no scheduler execution coupling
```

The extraction boundary suite protects against accidental responsibility drift while future helper extraction continues.

### Validation confirmed

Confirmed passing:

```text
python tests/test_scheduler_parser_helpers.py
python tests/test_runtime_execution_contracts.py
python tests/test_scheduler_extraction_boundary.py
python tests/run_regression_contracts.py
```

Observed result:

```text
[regression] ALL PASS: 3 test files
```

### Why this matters

This checkpoint is important because the project is entering a dangerous stage:

```text
large scheduler decomposition
+
runtime extraction
+
behavior preservation
```

Without regression contracts, future helper extraction risks silently breaking:

* parser behavior
* execution normalization
* runtime envelopes
* scheduler orchestration assumptions

This phase creates a repeatable safety gate before larger decomposition continues.

### Stable checkpoint after this pass

* parser helper regression coverage: working
* runtime execution contract coverage: working
* extraction boundary coverage: working
* consolidated regression runner: working
* regression replay path: stable
* scheduler decomposition safety baseline: improved

### Git checkpoints

Committed and pushed:

```text
8633fe6 - test: add scheduler and runtime regression contracts
4063c09 - test: add scheduler extraction boundary regression coverage
8d4ca42 - docs: record regression coverage phase v1
```

### Evidence kept

Keep screenshots showing:

* `ALL PASS: 3 test files`
* parser helper suite passing
* runtime execution contract suite passing
* extraction boundary suite passing
* clean git status after regression run

### Next step

Do not aggressively extract more scheduler logic yet.

Recommended next phase:

```text
Scheduler Runtime Contract Stabilization
```

Priority:

```text
protect runtime envelopes
protect task lifecycle contracts
protect scheduler orchestration boundaries
expand deterministic regression coverage first
```

---

## 2026-05-11 - Runtime Contract Hardening v1 checkpoint

This checkpoint records the first hardening pass that converts `tests/test_step_executor.py` from a smoke/output inspection script into a runtime contract assertion layer.

The goal was not to change runtime behavior.

The goal was to lock the currently proven StepExecutor result envelopes so future runtime refactors do not silently break the execution contract.

### What was completed

Updated:

```text
tests/test_step_executor.py
```

The test now keeps its existing readable smoke output while adding explicit assertions for stable StepExecutor envelopes.

### Contracts hardened

The first locked contracts are:

```text
unsupported_step_type
execute_steps failure envelope
execute_steps empty envelope
handler registration baseline
```

This intentionally avoids asserting unproven or imagined future contracts.

### Validation confirmed

Confirmed passing:

```text
python tests/test_step_executor.py
python tests/run_regression_contracts.py
```

Observed results:

```text
PASS: test_step_executor.py
[regression] ALL PASS: 3 test files
```

### Git checkpoint

Committed and pushed on `main`:

```text
c9807d9 - test: harden step executor runtime contracts
```

### Why this matters

This checkpoint starts hardening the AER runtime envelope.

Before this pass, `test_step_executor.py` printed useful diagnostic output, but important result-envelope behavior was not fully locked by assertions.

After this pass, future StepExecutor changes must preserve the proven runtime contract for:

```text
unsupported step type behavior
batch failure envelope
empty batch success envelope
basic handler availability
```

This protects the scheduler/runtime boundary because scheduler-side orchestration relies on stable execution result shapes.

### Stable checkpoint after this pass

* StepExecutor smoke: working
* unsupported step type contract: asserted
* execute_steps failure envelope: asserted
* execute_steps empty envelope: asserted
* regression gate: still passing
* working tree clean after commit/push

### Next step

Continue contract hardening carefully.

Do not assert idealized future behavior.

Only harden runtime contracts after they are observed stable through:

```text
direct smoke output
regression runner
existing runtime behavior
```

Recommended next phase:

```text
Runtime Contract Hardening v2
```

Candidate scope:

```text
successful write/read/verify result envelope
task lifecycle result envelope
scheduler tick result envelope
```

Do not touch queue mutation or scheduler extraction in the same pass.

---

## 2026-05-11 - Runtime Contract Hardening v2 checkpoint

This checkpoint records the second StepExecutor runtime contract hardening pass.

The goal was not to add new runtime capability.

The goal was to lock the currently proven successful execution envelope for the stable write/read/verify path.

### What was completed

Updated:

```text
tests/test_step_executor.py
```

The test now asserts the successful batch execution contract for:

```text
write_file -> read_file -> verify
```

This complements the earlier v1 hardening pass that locked:

```text
unsupported_step_type
execute_steps failure envelope
execute_steps empty envelope
handler registration baseline
```

### Successful path contract locked

The successful runtime path now asserts:

```text
ok == True
summary == all steps executed
message == CONTRACT_OK
final_answer == CONTRACT_OK
step_count == 3
completed_steps == 3
failed_step == None
error == None
results length == 3
last_result step_type == verify
execution_trace length == 3
```

Each successful step result now asserts the stable shape for:

```text
runtime_mode
step_type
step_index
step_count
message
final_answer
error
task_id
step payload
inner result payload
execution_trace entry
```

### Step-specific contracts

The write step asserts stable fields for:

```text
type == write_file
path == workspace/shared/contract_ok.txt
content == CONTRACT_OK
scope == sandbox
bytes == len(CONTRACT_OK)
```

The read step asserts stable fields for:

```text
type == read_file
path == workspace/shared/contract_ok.txt
content == CONTRACT_OK
candidates exists
full_path exists
```

The verify step asserts stable fields for:

```text
type == verify
path == workspace/shared/contract_ok.txt
content == CONTRACT_OK
actual == True
expected == CONTRACT_OK
mode == contains
candidates exists
full_path exists
```

### What was intentionally not locked

The test does not assert unstable environment-specific values such as:

```text
exact temp directory path
exact Windows full_path prefix
candidate ordering beyond list existence
absolute filesystem path identity
```

This keeps the contract deterministic without overfitting to one local machine.

### Validation confirmed

Confirmed passing:

```text
python tests/test_step_executor.py
python tests/run_regression_contracts.py
```

Observed result:

```text
PASS: test_step_executor.py
[regression] ALL PASS: 3 test files
```

### Git checkpoint

Committed and pushed on `main`:

```text
f57134d - test: harden successful runtime execution contracts
```

### Why this matters

This checkpoint turns the successful StepExecutor path from a smoke-tested behavior into an asserted runtime contract.

ZERO now has hard regression protection for both failure and success envelopes in the StepExecutor layer.

This is important because scheduler-side orchestration depends on stable runtime result shapes. If a future runtime refactor changes these envelopes accidentally, the contract test should fail immediately instead of letting the breakage surface later inside scheduler or agent-loop behavior.

### Stable checkpoint after this pass

* unsupported runtime envelope: asserted
* failure batch runtime envelope: asserted
* empty batch runtime envelope: asserted
* successful write/read/verify runtime envelope: asserted
* execution_trace success shape: asserted
* regression gate: still passing
* working tree clean after commit/push

### Next step

Do not expand this into scheduler extraction yet.

Recommended next phase:

```text
Scheduler Runtime Contract Mapping
```

Goal:

```text
identify which scheduler paths depend on StepExecutor result envelope fields
document scheduler -> runtime assumptions
only harden those assumptions after observing current behavior
```

Avoid mixing runtime contract mapping with broad scheduler refactoring in the same pass.


## Command Dispatch Boundary Check
- command_dispatch.py checked after recovery command wiring.
- Current size: 458 lines, 19 functions.
- Domain scan: recovery/review/audit only; no scheduler/planner/repair/github responsibility mixed in.
- Decision: keep command_dispatch.py as command surface for now; split only if a third command domain is added or orchestration logic grows.
- Regression: 494 runtime recovery/repair/replay related tests passed.

## Mutation Boundary Hotspot Check
- mutation_boundary.py checked after recovery command lifecycle stabilization.
- Current size: 872 lines, 34 functions.
- Hotspot: run_governed_mutation_lifecycle is 108 lines.
- Current decision: acceptable as lifecycle runner because it does not directly apply file changes; execution layer still owns real writes.
- Boundary rule: do not add real apply/diff/patch/policy/commit/scheduler retry logic into mutation_boundary.py. Split if governed lifecycle grows beyond orchestration stitching.

## Windows Smoke Baseline Reproducibility
- Status: pending full pass.
- Updated only smoke runner / launcher output handling for Windows reproducibility.
- `tests/run_mainline_smoke.py` now uses safe console output and UTF-8 child process environment defaults.
- `main.py` child process launcher now sets UTF-8 Python output defaults when not already configured.
- Current machine-generated baseline completed without UnicodeEncodeError interruption.
- Observed baseline: pass=5, fail=8, missing_required=0, skip_optional=0.
- Passing smoke labels: tool layer, scheduler, runtime, agent loop, executor.
- Failing smoke labels: document task, document flow showcase, document pipeline identity, requirement demo, execution demo, semantic task, implementation-proof, full-build-demo.
- Dominant failing runtime issue: `app.py` CLI JSON output hits `ValueError: Circular reference detected`.
- This entry is not a full-pass declaration.
