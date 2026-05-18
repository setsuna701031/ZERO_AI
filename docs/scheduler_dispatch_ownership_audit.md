# Scheduler Dispatch Ownership Audit

## 1. Current sealed boundary

- `dispatch_finalize.py` owns `build_finalize_decision` and `apply_finalize_decision`.
- `dispatch_helpers.py` should remain orchestration glue.
- `dispatch_result_helpers.py` only keeps the compatibility re-export.

## 2. Remaining ownership inside `scheduler.py`

- Repo state transitions around lines 4074-4139.
- Blocked/unblocked sync around lines 3709-3727, 3843-3886, and 4865-4866.
- Requeue/runtime sync around lines 1161-1178, 1699-1755, 3604-3681, and 3895-3922.
- Worker release around lines 538-580, 3709-3727, 3843-3867, and 4707-4727.

## 3. Proposed next boundary

- `dispatch_state_transition.py`

## 4. Do not move yet

- `tick`
- `execute_dispatch_round`
- `handle_dispatch_result`
- `task_runner.py`
- `step_executor.py`

## 5. Acceptance criteria

- Documentation only.
- No runtime code changes.
- `git diff` should only show this markdown file.
