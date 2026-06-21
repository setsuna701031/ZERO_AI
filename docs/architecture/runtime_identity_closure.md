# Runtime Identity Closure

## Canonical identity graph

Runtime identity is one graph, not a collection of convenient IDs:

`goal/root/source/lineage/branch -> session/runtime-session -> execution -> capability -> evidence -> persistence/resume`

The canonical goal source is `core.goals.goal_lineage_contract`. `create_root_goal_lineage` is the sole root minting boundary; `create_goal_branch_lineage` is the sole continuation/replan branch boundary. `canonical_runtime_identity_graph`, `bind_runtime_identity_graph`, and `attach_runtime_identity_graph` reject drift while execution, capability, and evidence IDs are bound.

## Enforced invariants

- Root creation produces one stable `goal_lineage_id`, `session_id`, and `runtime_session_id`.
- Continuation and replan preserve `root_goal_id`, `source_goal_id`, `goal_lineage_id`, `session_id`, and `runtime_session_id`; only explicit `goal_id`, `branch_type`, and `branch_id` change.
- RuntimeDispatcher deterministically binds one `execution_id` to the canonical lineage/task and binds the authority-derived `capability_id` to that execution.
- TaskRunner rejects capability provenance whose execution/capability identity differs from the task identity graph.
- TaskRuntime persists the identity graph with runtime state.
- RuntimeEvidenceAuthority binds `evidence_id` to the same execution and capability and rejects identity replacement.
- RuntimeEvidenceRegistry indexes the same identity graph.
- RuntimePersistenceService verifies evidence/persistence graph consistency and returns the persisted graph.
- RuntimeSessionResume validates the original graph and capability provenance. It does not mint session, runtime-session, execution, or capability identity during resume.
- Missing canonical identity is blocked rather than filled from task/package/default labels.

## Branch semantics

Continuation uses `branch_type=continuation` and an explicit continuation `branch_id`. Replan uses `branch_type=replan` and an explicit request-derived `branch_id`. Neither branch replaces the original `source_goal_id`. Serialized pre-closure branches with parent-as-source remain legacy records; they are not canonicalized silently.

## Audited paths

- `core/goals/goal_lineage_contract.py`: canonical source and graph validation.
- `core/adaptive/continuation_runtime.py`, `continuation_coordinator.py`: explicit continuation branch identity.
- `core/adaptive/replan_runtime.py`, `replan_coordinator.py`: explicit replan branch identity.
- `core/runtime/runtime_session_resume.py`: recovery and validation without identity minting.
- `core/runtime/runtime_dispatcher.py`: execution identity owner and capability binding.
- `core/runtime/task_runner.py`, `task_runtime.py`: runtime validation and persistence propagation.
- `core/runtime/runtime_execution_authority.py`, `runtime_capability_tokens.py`: capability/execution binding.
- `core/runtime/runtime_evidence_authority.py`, `runtime_evidence_registry.py`: evidence identity binding/indexing.
- `core/runtime/runtime_persistence_service.py`: graph consistency at serialization.
- `core/tasks/engineering_goal_loop.py`, `engineering_goal_runner.py`: root lineage delegated to the canonical source.
- `core/session/*`: session lifecycle consumes identity; it is not a canonical identity minting source.

## Non-mainline findings

These findings remain mandatory even when closure tests pass:

| Required finding | Observation | Disposition |
| --- | --- | --- |
| parallel identity systems | Operator sessions, persistent operator sessions, `source_session_id`, queue package/task IDs, live execution seals, and runtime identity graphs coexist. | Domain IDs remain, but none may replace canonical graph fields. A later migration should remove operator-session aliases from strict runtime identity extraction. |
| legacy lineage systems | `extract_goal_lineage` retains compatibility inference for old records that lack explicit root/source/branch/lineage fields. | Strict boundaries use `require_complete=True`; legacy inference is reported and must not be used to create new mainline work. |
| hidden lineage source | Some task/goal adapters still derive `goal_id` from task/package IDs and TaskRuntime retains `unknown_task` filesystem compatibility paths. | New goal-loop/runner roots use `create_root_goal_lineage`; remaining adapters are non-mainline migration targets. |
| resume identity drift | Historical resume records may lack `runtime_identity_graph` or capability provenance. | New capture blocks missing identity instead of minting it. Existing legacy records require explicit migration. |
| continuation lineage drift | Historical continuation records used the immediate parent as `source_goal_id`. | New continuation branches preserve the original source; old serialized records are not rewritten silently. |
| replan lineage drift | Historical replan records replaced `source_goal_id` with the replanned goal. | New replan branches preserve original source and require an explicit branch ID. |
| ownership/identity mixing | Runtime owner/source labels are still stored beside identity fields in task, evidence, and persistence metadata. | Labels remain descriptive; graph validation never accepts them as identity values. |
| evidence/identity drift | Older evidence bundles may have `evidence_id` and capability graph data without a full identity graph. | New evidence binds all fields; legacy evidence remains descriptive and requires migration before resume. |
| capability/identity drift | Legacy zone tokens and pre-closure capability provenance may omit `execution_id`. | Decision-rooted issuance now requires execution identity; legacy tokens remain explicitly non-mainline. |
| persistence/identity drift | Older runtime-state and report files may serialize partial lineage or capability IDs without evidence identity. | New state/evidence persistence checks one graph; existing artifacts are not backfilled from guesses. |

Report these findings; do not suppress, infer around, or “repair” them with fallback identities.
