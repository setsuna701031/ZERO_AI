# ZERO Runtime State Schema

Version: v0.1  
Scope: repair-chain runtime, engineering execution, strategy fallback, observation/session state, dependency/subgoal coordination.

## Purpose

`runtime_state.json` is the persisted contract for ZERO task execution. It must remain stable across:

- process restart
- task reload
- repair retry
- regression verification
- rollback
- scheduler handoff
- future agent-loop / Codex-like execution

This file defines ownership rules so `task_runner.py`, `task_runtime.py`, `scheduler.py`, repair executors, and future agent layers do not overwrite each other’s fields.

## Core Rule

`TaskRuntime` owns persistence and normalization.  
`TaskRunner` owns step execution flow.  
Schedulers must not directly mutate deep runtime fields except through runtime APIs.

No component should write arbitrary nested fields unless it owns that schema section.

---

## Top-Level Runtime Fields

| Field | Type | Owner | Mutation Rule |
|---|---:|---|---|
| `task_id` | string | TaskRuntime | Set from task metadata; stable after creation |
| `task_name` | string | TaskRuntime | Set from task metadata; stable after creation |
| `goal` | string | TaskRuntime | Set from task metadata |
| `task_dir` | string path | TaskRuntime | Normalized from task |
| `status` | string | TaskRuntime | Only via runtime transition methods |
| `steps` | list | TaskRuntime / TaskRunner | Runtime copy is source of truth after creation |
| `steps_total` | int | TaskRuntime | Derived from `steps` |
| `current_step_index` | int | TaskRuntime | Advanced by runtime transition only |
| `results` | list | TaskRuntime | Append-only compacted step records |
| `step_results` | list | TaskRuntime | Append-only compacted step records |
| `execution_log` | list | TaskRuntime | Append-only compacted execution records |
| `execution_trace` | list | TaskRunner | TaskRuntime persists and compacts |
| `last_step_result` | dict | TaskRuntime | Updated from latest step record |
| `last_error` | string/null | TaskRuntime | Updated on failure or cleared on success |
| `last_output` | string | TaskRuntime | Extracted from step result |
| `final_answer` | string | TaskRuntime | Set on finish |
| `final_result` | dict | TaskRuntime | Set on finish |
| `created_at` | timestamp | TaskRuntime | Set once |
| `updated_at` | timestamp | TaskRuntime | Updated on save |
| `next_action` | string | TaskRuntime / TaskRunner | Used for tick continuation and waiting states |
| `terminal_reason` | string | TaskRuntime | Set on terminal state |

---

## Status Values

### Terminal

- `finished`
- `failed`
- `cancelled`
- `timeout`

### Non-Terminal

- `queued`
- `planning`
- `ready`
- `running`
- `waiting`
- `blocked`
- `waiting_review`
- `waiting_blocker`
- `retrying`
- `replanning`
- `paused`

Status changes should go through `TaskRuntime` transition methods:

- `mark_running`
- `advance_step`
- `record_step_failure`
- `mark_finished`
- `mark_failed`
- `mark_waiting_blocker`
- `mark_waiting_review`
- `remove_blocker`
- `prepare_current_subgoal`

---

## Persistence Rules

### Runtime state file path

Owner: `TaskRuntime._get_runtime_state_file`

Rules:

- Always normalize `runtime_state_file`
- Collapse double-escaped Windows backslashes before writing
- Use `os.path.normpath`
- Do not trust persisted path strings blindly

Reason: Windows paths may reload as double-escaped strings such as:

```text
E:\zero_ai\.test_tmp\repair_chain_runtime\tasks\regression_fail\runtime_state.json
```

These must become valid OS paths before file writes.

---

## Steps and Plan Ownership

### `steps`

Owner: `TaskRuntime`

Rules:

- Initial value comes from task metadata.
- Once `runtime_state.json` exists, runtime `steps` are source of truth.
- Task-level `steps` must not overwrite runtime `steps`.
- Repair injection may append or replace runtime `steps`.
- Scheduler should not directly rewrite runtime `steps`.

### `current_step_index`

Owner: `TaskRuntime`

Rules:

- `advance_step` increments this field.
- Failed observations with `continue_on_failure` may advance.
- Terminal states clamp it to `steps_total`.
- Public results must include `current_step_index` and `steps_total`.

---

## `repair_context`

Owner: shared nested contract, but writes are section-specific.

Top-level structure:

```json
{
  "flow": [],
  "phase_results": {},
  "original_failed_step": null,
  "failed_step": null,
  "failed_file": "",
  "failed_reason": "",
  "repair_result": null,
  "apply_result": null,
  "verify_result": null,
  "original_file_content": "",
  "proposed_fix": "",
  "final_edit_payload": "",
  "requested_functions": "",
  "failed_functions": "",
  "verification_result": "",
  "rollback": "",
  "rollback_result": null,
  "per_file_rollback_metadata": "",
  "dependency_graph": "",
  "repo_impact": "",
  "regression_verify": "",
  "multi_file_plan": "",
  "repair_session": {},
  "engineering_goal_state": {},
  "strategy": {},
  "last_phase": "",
  "last_error": ""
}
```

Rules:

- `TaskRuntime` normalizes shape.
- TaskRunner and repair executors may update owned subsections only.
- Avoid replacing the entire `repair_context` unless merging existing content.

---

## `repair_context.strategy`

Owner: repair strategy layer / TaskRunner repair path.

Purpose: records fallback strategy progression.

Expected fields:

| Field | Type | Meaning |
|---|---:|---|
| `current_strategy` | string | Active strategy, e.g. `minimal_patch`, `function_rewrite` |
| `max_strategy_attempts` | int | Strategy attempt cap |
| `strategy_history` | list | Prior strategy outcomes |
| `exhausted` | bool | Whether all strategies failed |
| `last_strategy_transition_reason` | string | Why strategy changed |
| `updated_at` | timestamp | Last strategy update |

Rules:

- Do not globally switch every successful verification to `function_rewrite`.
- `minimal_patch` success must remain `minimal_patch`.
- Switch to `function_rewrite` only when repair flow actually required function-level rewrite behavior.
- Strategy history should be append-only except for compaction.

---

## `repair_context.regression_verify`

Owner: TaskRunner regression verification phase.

Purpose: records post-apply regression checks.

Expected fields:

| Field | Type |
|---|---:|
| `passed` | bool |
| `commands` | list |
| `error` | string/null |
| `stdout` | string |
| `stderr` | string |
| `returncode` | int/null |
| `rollback` | bool |
| `changed_files` | list |

Rules:

- Regression verification must not corrupt runtime path fields.
- Failed regression may trigger rollback.
- Rollback metadata must be persisted before strategy retry.

---

## `repair_context.engineering_goal_state`

Owner: TaskRuntime goal/subgoal coordination.

Purpose: coordinates multi-subgoal engineering execution.

Expected fields:

| Field | Type | Meaning |
|---|---:|---|
| `goal_id` | string | Goal identifier |
| `goal_text` | string | Goal summary |
| `status` | string | `running`, `finished`, `failed`, `blocked` |
| `subgoals` | list | Normalized subgoal records |
| `current_subgoal_id` | string | Current active subgoal |
| `completed_subgoals` | list | Finished/skipped subgoals |
| `failed_subgoals` | list | Failed subgoals |
| `blocked_subgoals` | list | Blocked subgoals |
| `replan_count` | int | Replan count |
| `summary` | dict | Optional rollup |
| `replan_request` | dict | Optional replan request |
| `replan_proposal` | dict | Optional replan proposal |

Subgoal record:

| Field | Type |
|---|---:|
| `subgoal_id` | string |
| `title` | string |
| `description` | string |
| `status` | string |
| `depends_on` | list |
| `related_files` | list |
| `risk_level` | string |
| `requires_confirmation` | bool |
| `steps` | list |
| `result_summary` | string |
| `failure_reason` | string |
| `blocked_reason` | string |

Rules:

- `prepare_current_subgoal` may reroute from blocked dependency subgoal to a ready subgoal.
- Direct TaskRunner execution may return `blocked` when explicitly positioned on a subgoal whose dependencies are missing.
- Do not globally remove ready-subgoal rerouting.
- Completed subgoals must not rerun after reload.

---

## `repair_context.repair_session`

Owner: observation/session layer.

Purpose: records repair-chain graph/session state.

Expected fields:

| Field | Type |
|---|---:|
| `session_id` | string |
| `version` | string |
| `status` | string |
| `nodes` | list |
| `edges` | list |
| `observations` | list |
| `decisions` | list |
| `last_observation` | dict |
| `last_decision` | dict |

Rules:

- Observation labels must match runtime contract.
- Use `step_failed_observed` only when a failed step is advanced via `continue_on_failure` or equivalent original failed-step observation flow.
- Normal successful step completion remains `step_completed`.
- Session graph updates should be append-only and compacted.

---

## Blockers and Review

Owner: TaskRuntime blocker APIs.

Fields:

| Field | Type |
|---|---:|
| `blockers` | list |
| `active_blocker_count` | int |
| `requires_review` | bool |
| `review_status` | string |
| `review_id` | string |
| `review_payload` | dict |
| `waiting_reason` | string |

Rules:

- Use `mark_waiting_blocker`, `mark_waiting_review`, `add_blocker`, `remove_blocker`.
- Do not mutate blocker arrays directly from scheduler.
- `active_blocker_count` is derived from normalized blockers.

---

## Write Ownership Matrix

| Area | Owner | Other Components |
|---|---|---|
| File persistence | `TaskRuntime` | read only |
| Path normalization | `TaskRuntime` | no direct writes |
| Step execution result | `TaskRunner` | executor returns payload only |
| Step result storage | `TaskRuntime` | append via transition |
| Repair strategy | repair path / TaskRunner | scheduler read only |
| Regression verify | TaskRunner | TaskRuntime persists |
| Rollback metadata | repair rollback layer | TaskRuntime persists |
| Engineering goal state | TaskRuntime | TaskRunner may request prepare/block |
| Repair session | observation layer / TaskRunner | TaskRuntime normalizes |
| Scheduler task queue | scheduler | runtime read/write only through API |
| Public result payload | TaskRunner | must mirror runtime fields |

---

## Anti-Patterns

Do not:

- Write `runtime_state.json` outside `TaskRuntime`
- Replace entire `repair_context` without merging
- Trust raw `runtime_state_file` strings
- Let `task.steps` overwrite runtime-injected `steps`
- Let scheduler own deep runtime fields
- Switch all successful repairs to `function_rewrite`
- Mark normal completed steps as failed observations
- Remove ready-subgoal rerouting globally
- Add scheduler-specific exceptions into `TaskRuntime`

---

## Acceptance Tests

Current required baseline:

```powershell
python -m py_compile core/runtime/task_runner.py
python -m py_compile core/runtime/task_runtime.py
python -m pytest tests/test_repair_chain_runtime.py -q
```

Expected:

```text
61 passed
```

Before future scheduler or agent-loop refactors, this test must remain green.

---

## Next Schema Work

After this schema is stable:

1. Add `docs/runtime_write_ownership.md`
2. Add runtime schema validation helper
3. Add lightweight state invariant tests
4. Add public devlog entry for repair-chain stabilization
5. Start scheduler slimming only after runtime contract remains green
