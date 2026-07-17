# Persistent Runtime Contract Inventory

Status: drafted after the `4059 passed` runtime seal checkpoint  
Branch context: `debug/persistent-runtime-contract`  
Purpose: map the current persistent/runtime/resume contract surface before the next engineering package.

## Current Verified Checkpoint

The focused persistent-runtime validation set passed:

```text
38 passed, 8 subtests passed
```

The full repository validation also passed at the previous seal point:

```text
4059 passed
```

This means the immediate runtime-persistence / authority-propagation failure burst has been sealed. The next risk is not missing tests; it is unclear ownership of the many existing runtime contracts.

## Mainline Persistent Runtime Chain

These tests are currently treated as the mainline chain for persistent runtime continuity:

```text
test_agent_loop_persistent_runtime_route_contract.py
test_runtime_loop_continuation_integration_v1.py
test_scheduler_runtime_payload_contract.py
test_scheduler_runtime_tail_regression.py
test_agentloop_scheduler_lifecycle_continuity.py
```

Current focused result:

```text
38 passed, 8 subtests passed
```

## Persistent Runtime Files

Existing persistent-related tests discovered:

```text
persistent_engineering_session.py
test_agent_loop_persistent_runtime_route_contract.py
test_persistent_engineering_session_contract.py
test_persistent_operator_integration_bridge.py
test_persistent_operator_runtime_contract.py
test_persistent_runtime_orchestrator_contract.py
```

Interpretation:

- Persistent runtime coverage exists.
- Operator persistence coverage exists.
- Engineering session persistence exists.
- The next task is to verify whether these are connected to the mainline runtime ownership path or remain isolated contracts.

## Resume Files

Existing resume-related tests discovered:

```text
test_runtime_blocker_loop_resume.py
test_runtime_replay_resume_loop_v1.py
test_runtime_session_resume_seal_v1.py
test_runtime_session_resume_v1.py
```

Interpretation:

- Resume is present as a defined contract surface.
- Replay resume and session resume are already separated.
- Next check: confirm whether resume preserves authority, owner, session id, task id, runtime state, and evidence links across reload.

## Runtime Contract Surface

The runtime contract surface is now broad. The discovered runtime-contract list includes these major areas:

```text
Admission
Authority
Boundary
Burn-in
Capability
Closure
Consistency
Connector
Controlled execution
Event bus / event channel / event replay
Evidence bundle / registry / persistence / replay / snapshot
Execution bridge / grant / handoff / lease / ownership / session / transaction
Forensic stack
Gate integration
Governed rollback
Grant eligibility / grant issuer
Hydration
Incident
Integration adapter
Intent classifier / intent gate
Kernel boundary
Lifecycle coordinator / pipeline / propagation
Mainline evidence seal / freeze
Memory index
Monitor
Mutation governance / guard
Observability
Operation registry
Orchestrator
Ownership / ownership gate
Payload adapter
Plan executor
Policy engine
Prediction constitution / memory
Public surface
Queue admission
Recovery approval / audit / commit gate / coordinator / execution / plan / policy / reasoning / terminal
Repair apply / persistence / replay legality
Replay determinism / engine / readiness
Scheduler adapter
Session replay
Side effect registry
Snapshot
State / state registry
Transaction boundary / context / coordinator / lifecycle / orchestrator / propagation
Transition
Trust policy
Workflow session
Task runtime evidence
Trace runtime
```

Interpretation:

- The project already has enough contract files to describe a runtime kernel surface.
- The next risk is overlap and unclear layering, not lack of assertions.
- Future work should avoid adding more contracts until ownership and coverage are mapped.

## Proposed Next Engineering Package

Recommended package:

```text
AER Phase: Runtime Ownership Enforcement Seal
```

Reason:

The recent root-cause package fixed these ownership-adjacent failures:

```text
RuntimePersistenceService → RuntimeFileService → governed mutation path
TaskRunner authority defaults
StepExecutor authority endpoint
Operator session continuity
Scheduler repair failure propagation
ZeroSystem bootstrap wiring
Runtime JSON hygiene
```

Those fixes all point toward the same next boundary:

```text
Who owns execution authority?
Who may mutate runtime state?
How is authority preserved through task → scheduler → runtime → step executor?
How is ownership preserved through persist → reload → resume?
```

## Ownership / Authority / Grant Inventory Commands

Run these before editing code:

```powershell
Get-ChildItem tests -Filter "*ownership*.py" | Select-Object Name
Get-ChildItem tests -Filter "*authority*.py" | Select-Object Name
Get-ChildItem tests -Filter "*grant*.py" | Select-Object Name
```

Then classify the results into:

```text
1. Ownership creation
2. Ownership propagation
3. Ownership persistence
4. Ownership resume/reload
5. Authority grant
6. Authority denial
7. Mutation endpoint enforcement
8. Scheduler / TaskRunner propagation
9. StepExecutor endpoint validation
10. Recovery / repair authority preservation
```

## Do Not Do Yet

Do not start capability-layer expansion yet:

```text
No new tool packs
No new memory layer
No new scraping/browser layer
No new UI/remote control layer
No new model-routing layer
```

These should wait until ownership enforcement is sealed.

## Acceptance Criteria for Runtime Ownership Enforcement Seal

The next package should be considered sealed only when all of these are true:

```text
1. Ownership/authority/grant tests pass as a focused set.
2. Full pytest passes.
3. No direct runtime protected-zone write bypass is reintroduced.
4. No new allowlist/skip/mock is added to hide failures.
5. TaskRunner returns explicit authority context, not missing/None defaults.
6. StepExecutor accepts valid authority and rejects invalid authority.
7. Runtime persistence preserves operator/session metadata.
8. Resume/reload preserves task identity and authority metadata.
9. Scheduler repair failures remain failures and are not converted to success.
10. Evidence screenshot is saved under docs/images after full pass.
```

## Recommended Next Focused Test Set

After ownership/authority/grant files are listed, build a focused set similar to:

```powershell
pytest -q tests/test_runtime_ownership_contract.py tests/test_runtime_ownership_gate_contract.py tests/test_runtime_execution_ownership_migration_contract.py tests/test_runtime_authority_governance_contract.py tests/test_runtime_execution_grant_contract.py
```

Adjust the exact list based on the discovered files.

## Current Decision

The persistent runtime chain is healthy enough to move forward.

Next stage should be:

```text
Runtime Ownership Enforcement Seal
```

not:

```text
More persistence rewrites
More runtime contract files
Capability expansion
UI expansion
Memory expansion
```
