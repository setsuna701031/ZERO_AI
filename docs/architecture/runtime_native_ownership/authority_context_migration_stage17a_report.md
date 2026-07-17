# Stage17A — Wave1 Authority Context Migration

## Decision

- Wave1 status: **blocked**
- Wave2 ready: **false**
- Active TaskRunner authority overlays: 0
- New blockers: runtime_session, repair_chain

## Authority propagation before

1. `Scheduler._build_scheduler_authority_context`
2. `Scheduler._run_step_via_task_runner`
3. `RuntimeDispatcher.run_scheduler_boundary`
4. `TaskRunner._build_taskrunner_authority_context (module-level overlay replacement)`
5. `delegate_taskrunner_execution_capability`
6. `StepExecutor.execute_step`

## Authority propagation after

1. `Scheduler._build_scheduler_authority_context`
2. `Scheduler canonical root-lineage normalization`
3. `Scheduler._run_step_via_task_runner`
4. `RuntimeDispatcher.run_scheduler_boundary`
5. `TaskRunner._build_taskrunner_authority_context (class entrypoint)`
6. `taskrunner_authority_contract.build_taskrunner_authority_context`
7. `delegate_taskrunner_execution_capability`
8. `StepExecutor.execute_step`

## Domain preservation

- `authority_context`: incoming scheduler context + immutable capability provenance
- `runtime_session`: ['session_id', 'runtime_session_id', 'operator_session_id', 'persistent_operator_session_id']
- `goal_lineage`: canonical goal_lineage plus runtime_identity and runtime_identity_graph
- `continuation_chain`: ['continuation_id', 'parent_continuation_id', 'continuation_chain', 'continuation_lineage']
- `repair_chain`: ['repair_chain_id', 'repair_context']

## Validation

- `compileall`: pass (0 passed, 0 failed, 0 errors)
- `ownership`: pass (69 passed, 0 failed, 0 errors)
- `authority`: pass (79 passed, 0 failed, 0 errors)
- `lineage`: pass (33 passed, 0 failed, 0 errors)
- `runtime_session`: fail (44 passed, 4 failed, 0 errors)
- `repair_chain`: timeout (0 passed, 0 failed, 0 errors)

## Compatibility and non-mainline reporting

- Compatibility bridges visible: 15 / 15
- Non-mainline issues: 6 / 6 preserved
- Scheduler boundary compatibility overlay remains visible for its assigned later retirement wave; it does not own TaskRunner authority propagation.
