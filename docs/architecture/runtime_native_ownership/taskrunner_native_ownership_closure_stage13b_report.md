# TaskRunner Dependency Closure Inventory — Stage13B

Inventory and dependency ordering only. No blocker was repaired and no production runtime behavior was modified.

## Summary

- TaskRunner total: 19
- Confirmed blockers: 19
- Scheduler direct unlock count: 1
- StepExecutor dependency count: 12
- Unresolved ambiguities: 0
- Production runtime touched: false

## Ownership counts

- `taskrunner_state_ownership`: 2
- `taskrunner_execution_ownership`: 14
- `taskrunner_continuation_ownership`: 1
- `taskrunner_runtime_session_ownership`: 2

## Dependency counts

- `scheduler_dependencies`: 13
- `step_executor_dependencies`: 12
- `repair_chain_dependencies`: 3

## Closure and unlock graph

1. `taskrunner_state_ownership` — blocked by: none; unlocks: `taskrunner_runtime_session_ownership`
2. `taskrunner_runtime_session_ownership` — blocked by: `taskrunner_state_ownership`; unlocks: `taskrunner_scheduler_dependency`
3. `taskrunner_scheduler_dependency` — blocked by: `scheduler_contract`, `taskrunner_runtime_session_ownership`; unlocks: `taskrunner_step_executor_dependency`
4. `taskrunner_step_executor_dependency` — blocked by: `step_executor_contract`, `taskrunner_scheduler_dependency`; unlocks: `taskrunner_repair_chain_dependency`, `taskrunner_execution_ownership`
5. `taskrunner_repair_chain_dependency` — blocked by: `repair_chain`, `taskrunner_step_executor_dependency`; unlocks: `taskrunner_execution_ownership`
6. `taskrunner_execution_ownership` — blocked by: `taskrunner_scheduler_dependency`, `taskrunner_step_executor_dependency`, `taskrunner_repair_chain_dependency`; unlocks: `taskrunner_continuation_ownership`
7. `taskrunner_continuation_ownership` — blocked by: `taskrunner_execution_ownership`, `goal_lineage_contract`; unlocks: `scheduler_contract`

## Scheduler blockers directly unlocked

- `S13A-SCHED-023` `Scheduler._sync_runner_result_and_requeue_if_ready` — TaskRunner is the only cross-domain dependency.

## Scheduler blockers partially unlocked

- `S13A-SCHED-001` `Scheduler._handle_dispatch_result` — still blocked by `step_executor_contract`
- `S13A-SCHED-004` `Scheduler._finalize_dispatched_task` — still blocked by `step_executor_contract`
- `S13A-SCHED-008` `Scheduler._execute_simple_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-009` `Scheduler._execute_simple_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-019` `Scheduler._run_simple_task_tick` — still blocked by `step_executor_contract`
- `S13A-SCHED-022` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-027` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-028` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-029` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-030` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-031` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-032` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-035` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-036` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-037` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-038` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-039` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-040` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-041` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-042` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-043` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-044` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-045` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-046` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-047` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-048` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-049` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-050` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-051` `Scheduler.run_one_step` — still blocked by `step_executor_contract`
- `S13A-SCHED-052` `Scheduler.run_one_step` — still blocked by `step_executor_contract`

## TaskRunner ownership inventory

### taskrunner_state_ownership (2)

- `S13B-TR-004` — `core/runtime/task_runner.py:4686` — `TaskRunner.READ_ONLY_STEP_TYPES`
  - Ownership: `taskrunner_state_ownership`; dependencies: none
  - Markers: none
  - Replacement target: `core.runtime.task_runner.TaskRunner.READ_ONLY_STEP_TYPES`
  - Why blocker: class-level routing allowlist changes scheduler/task_runner/step_executor execution selection
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: Native TaskRunner declares canonical step-type routing sets and all consumers use those declarations.
  - Recommended action: Promote routing state into the native class only after duplicate set extensions are reconciled.
- `S13B-TR-005` — `core/runtime/task_runner.py:4696` — `TaskRunner.CODE_CHAIN_WORKFLOW_STEP_TYPES`
  - Ownership: `taskrunner_state_ownership`; dependencies: none
  - Markers: none
  - Replacement target: `core.runtime.task_runner.TaskRunner.CODE_CHAIN_WORKFLOW_STEP_TYPES`
  - Why blocker: class-level routing allowlist changes scheduler/task_runner/step_executor execution selection
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: Native TaskRunner declares canonical step-type routing sets and all consumers use those declarations.
  - Recommended action: Promote routing state into the native class only after duplicate set extensions are reconciled.

### taskrunner_execution_ownership (14)

- `S13B-TR-001` — `core/runtime/task_runner.py:4589` — `TaskRunner._run_one_step`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner._run_one_step`
  - Why blocker: class-level executable replacement changes runtime execution, state transition, authority, or recovery behavior
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-002` — `core/runtime/task_runner.py:4624` — `TaskRunner._determine_failure_type`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `repair_chain_dependencies`
  - Markers: none
  - Replacement target: `core.runtime.task_runner.TaskRunner._determine_failure_type`
  - Why blocker: class-level executable replacement changes runtime execution, state transition, authority, or recovery behavior
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-003` — `core/runtime/task_runner.py:4669` — `TaskRunner._determine_failure_type`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `repair_chain_dependencies`
  - Markers: none
  - Replacement target: `core.runtime.task_runner.TaskRunner._determine_failure_type`
  - Why blocker: class-level executable replacement changes runtime execution, state transition, authority, or recovery behavior
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-006` — `core/runtime/task_runner.py:4722` — `TaskRunner._determine_failure_type`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `repair_chain_dependencies`
  - Markers: none
  - Replacement target: `core.runtime.task_runner.TaskRunner._determine_failure_type`
  - Why blocker: class-level executable replacement changes runtime execution, state transition, authority, or recovery behavior
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-010` — `core/runtime/task_runner.py:5630` — `TaskRunner.run_task_tick`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: direct StepExecutor overlay, goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task_tick`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-011` — `core/runtime/task_runner.py:5643` — `TaskRunner.run_task`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: direct StepExecutor overlay, goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-012` — `core/runtime/task_runner.py:5683` — `TaskRunner.run_task_tick`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task_tick`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-013` — `core/runtime/task_runner.py:5692` — `TaskRunner.run_task`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-014` — `core/runtime/task_runner.py:5875` — `TaskRunner.run_task_tick`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task_tick`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-015` — `core/runtime/task_runner.py:5889` — `TaskRunner.run_task`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-016` — `core/runtime/task_runner.py:5982` — `TaskRunner.run_task_tick`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task_tick`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-017` — `core/runtime/task_runner.py:5991` — `TaskRunner.run_task`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-018` — `core/runtime/task_runner.py:6036` — `TaskRunner.run_task_tick`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task_tick`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.
- `S13B-TR-019` — `core/runtime/task_runner.py:6045` — `TaskRunner.run_task`
  - Ownership: `taskrunner_execution_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency, runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task`
  - Why blocker: replacement directly intercepts a named runtime execution or authority chain
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.
  - Recommended action: Order overlays chronologically, identify the terminal contract, and plan one native execution chain.

### taskrunner_continuation_ownership (1)

- `S13B-TR-009` — `core/runtime/task_runner.py:5476` — `TaskRunner.run_task_adaptive`
  - Ownership: `taskrunner_continuation_ownership`; dependencies: `scheduler_dependencies`, `step_executor_dependencies`
  - Markers: goal-lineage dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.run_task_adaptive`
  - Why blocker: class-level executable replacement changes runtime execution, state transition, authority, or recovery behavior
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: Native adaptive execution preserves complete goal lineage and continuation identity through scheduler handoff.
  - Recommended action: Close continuation and goal-lineage contracts before retiring the adaptive execution overlay.

### taskrunner_runtime_session_ownership (2)

- `S13B-TR-007` — `core/runtime/task_runner.py:5179` — `TaskRunner.__init__`
  - Ownership: `taskrunner_runtime_session_ownership`; dependencies: none
  - Markers: runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner.__init__`
  - Why blocker: class-level constructor replacement changes runtime dependency ownership
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: Native construction and persistence use one runtime-session owner and preserve step results across resume.
  - Recommended action: Consolidate constructor/session wiring and persistence under the native TaskRunner owner.
- `S13B-TR-008` — `core/runtime/task_runner.py:5180` — `TaskRunner._persist_step_result_to_runtime_state`
  - Ownership: `taskrunner_runtime_session_ownership`; dependencies: `scheduler_dependencies`
  - Markers: runtime-session dependency
  - Replacement target: `core.runtime.task_runner.TaskRunner._persist_step_result_to_runtime_state`
  - Why blocker: class-level executable replacement changes runtime execution, state transition, authority, or recovery behavior
  - Safe removal precondition: Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries. Stage13B TaskRunner condition: Native construction and persistence use one runtime-session owner and preserve step results across resume.
  - Recommended action: Consolidate constructor/session wiring and persistence under the native TaskRunner owner.

## Non-Mainline Issue Report

No TaskRunner-domain non-mainline issue exists in Stage12, and no outside-domain issue was discovered during Stage13B analysis.

## Outputs

- `docs/architecture/runtime_native_ownership/taskrunner_native_ownership_closure_stage13b.json`
- `docs/architecture/runtime_native_ownership/taskrunner_native_ownership_closure_stage13b_summary.json`
- `docs/architecture/runtime_native_ownership/taskrunner_native_ownership_closure_stage13b_report.md`
