# Scheduler Core Module Boundary

`repo_state_helpers.py` is a compatibility facade only. It preserves historic import names for external callers and tests, but scheduler_core implementation modules import the concrete modules directly.

Allowed direction:

```text
scheduler.py
  -> repo_task_state.py
  -> repo_runtime_sync.py
  -> repo_blocked_state.py

repo_state_helpers.py
  -> repo_task_state.py
  -> repo_runtime_sync.py
  -> repo_blocked_state.py
  -> repo_runtime_adapter.py
  -> repo_observability.py

repo_runtime_sync.py
  -> repo_task_state.py
  -> repo_blocked_state.py
  -> repo_runtime_adapter.py

repo_task_state.py
  -> repo_observability.py
```

Not allowed:

```text
repo_observability.py -> repo_state_helpers.py
repo_runtime_adapter.py -> repo_state_helpers.py
repo_task_state.py -> repo_state_helpers.py
repo_runtime_sync.py -> repo_state_helpers.py
repo_blocked_state.py -> repo_state_helpers.py
```

Current extracted modules:

- `repo_observability.py`
- `repo_runtime_adapter.py`
- `repo_task_state.py`
- `repo_runtime_sync.py`
- `repo_blocked_state.py`

Compatibility rule:

Do not remove names from `repo_state_helpers.py` unless tests and compileall pass and existing compatibility imports have explicit coverage.
