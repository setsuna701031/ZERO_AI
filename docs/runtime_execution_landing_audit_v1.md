# Runtime Execution Landing Package v1 Audit

## Phase 1 - Execution Ownership Audit

Canonical execution owner:

- `core.runtime.executor.Executor`

The canonical owner now returns `RuntimeExecutionResult`, backed by `RuntimeSideEffectRegistry`.

Execution sources found during repository scan:

- Scheduler execution: `core/tasks/scheduler.py` constructs and invokes `StepExecutor`.
- Scheduler core execution: `core/tasks/scheduler_core/command_step_helpers.py` uses `subprocess.run`.
- Adapter execution: no direct execution in the v0 lifecycle adapter chain; `runtime_scheduler_adapter.py` remains admission-only.
- Bridge execution: `runtime_execution_bridge.py` remains admission-only.
- Connector execution: `runtime_connector.py` remains handoff-only.
- Replay/recovery execution: recovery dry-run and repair flows remain separate governed paths; no migration was performed in this phase.
- Mutation execution: `core/runtime/step_executor.py`, `core/runtime/step_handlers.py`, and repair transaction flows contain file mutation / patch application surfaces.
- Tool command execution: `core/tools/command_tool.py`, readonly tools, and archived tools contain subprocess surfaces.

Illegal execution surfaces to migrate behind the canonical owner:

- `core/runtime/step_executor.py` verification command helper. Status: migrated to canonical executor gateway.
- `core/runtime/step_handlers.py` command and Python helpers. Status: migrated to canonical executor gateway.
- `core/tasks/scheduler_core/command_step_helpers.py`. Status: migrated to canonical executor gateway.
- `core/tasks/simple_step_runner.py`. Status: command execution migrated to canonical executor gateway.
- `core/tools/command_tool.py`. Status: migrated to canonical executor gateway.
- `core/repo_sandbox/controlled_edit.py`.
- Capability and persona smoke/demo command helpers.
- Archived execution helpers under `_archive_candidate`.
- `core/runtime/task_runner.py`.
- `core/runtime/execution_gateway.py`. Status: compatibility wrapper only; no direct subprocess execution.

Migration plan:

1. Keep scheduler, scheduler_core, bridge, adapter, connector, replay, and recovery as request/validation/trace layers.
2. Route new guarded runtime execution through `core.runtime.executor.Executor` only.
3. Convert executor outputs into `RuntimeExecutionResult`.
4. Register side effects through `RuntimeSideEffectRegistry` only.
5. Migrate direct subprocess and mutation helpers one owner at a time, beginning with scheduler command helpers and `StepExecutor` command handlers.
6. Preserve existing replay/recovery result envelopes until compatibility adapters can consume `RuntimeExecutionResult` directly.

Final single execution authority map:

- Owns real execution: `core.runtime.executor.Executor`.
- Owns canonical result currency: `core.runtime.runtime_execution_result.RuntimeExecutionResult`.
- Owns side effect records: `core.runtime.runtime_side_effect_registry.RuntimeSideEffectRegistry`.
- Validates admission and lineage only: public surface, connector, ownership gate, grant issuer, execution bridge, scheduler adapter, queue admission, controlled enqueue, execution pending, execution start, handoff record.
- Requests/enqueues/traces only: scheduler and scheduler_core after migration.
- Replays/recovers using recorded lineage only: replay/recovery layers.

## Illegal Execution Surface Migration v1

Migrated surfaces:

- `core/runtime/execution_gateway.py`
- `core/runtime/step_handlers.py`
- `core/runtime/step_executor.py`
- `core/tasks/scheduler_core/command_step_helpers.py`
- `core/tasks/simple_step_runner.py`
- `core/tools/command_tool.py`

Before:

- These modules could call direct subprocess execution or expose `shell=True`.

After:

- They route command/subprocess execution through `RuntimeExecutionRequest` and `core.runtime.executor.Executor.execute_request()`.
- `RuntimeExecutionResult` is emitted by the canonical executor.
- `RuntimeSideEffectRegistry` records command/subprocess side effects.

Validation commands:

```text
python -m pytest tests/test_runtime_execution_ownership_migration_contract.py tests/test_step_executor.py tests/test_tool_registry.py tests/test_scheduler_command_planner.py tests/test_scheduler_parser_helpers.py -q
```

Expected output:

```text
all selected ownership migration tests pass
```

Additional migrated surfaces:

- `core/_archive_candidate/flask_manager.py`
- `core/capabilities/demo_flows.py`
- `core/capabilities/full_build_flow.py`
- `core/capabilities/document_flow_orchestrator.py`
- `core/persona/persona_agent_orchestrator.py`
- `core/persona/runtime_bridge.py`
- `core/repo_sandbox/controlled_edit.py`
- `core/runtime/task_runner.py`
- `core/tools/github_tool.py`
- `core/tools/readonly_tools.py`
- `core/watch/auto_task_runner.py`
- `core/tools/_archive_candidate/debug_python.py`
- `core/tools/_archive_candidate/run_python_tool.py`
- `core/tools/_archive_candidate/run_shell.py`
- `core/tools/_archive_candidate/terminal_tool.py`

Repository-wide direct execution scan:

- `subprocess.run`: allowed only in `core/runtime/executor.py`
- `subprocess.Popen`: no hits
- `os.system`: no hits
- `shell=True`: no hits outside canonical executor request metadata

Regression risks:

- Command wrappers now depend on the canonical executor result contract.
- Callers that inspected legacy gateway internals may need to read the normalized gateway dict instead.
- Archived Flask detached start now refuses to start a background process outside canonical executor ownership.

## Phase 2 - Runtime Execution Result Contract

Affected files:

- `core/runtime/runtime_execution_result.py`
- `core/runtime/executor.py`
- `tests/test_runtime_execution_result_contract.py`

Architecture summary:

`RuntimeExecutionResult` is the immutable canonical execution currency. `Executor.execute_plan()` now returns it instead of a raw dict while preserving read compatibility for legacy result keys through mapping methods.

Migration reasoning:

The executor is the current canonical owner. Wrapping its legacy execution envelope allows the runtime-core contract to move forward without breaking scheduler/recovery callers that still read legacy keys.

Validation commands:

```text
python -m pytest tests/test_runtime_execution_result_contract.py -q
```

Expected output:

```text
2 passed
```

Regression risks:

- Callers that require `isinstance(result, dict)` must migrate to mapping access or `result.to_dict()`.
- JSON serialization should use `to_dict()` explicitly.

## Phase 3 - Side Effect Registry

Affected files:

- `core/runtime/runtime_side_effect_registry.py`
- `core/runtime/executor.py`
- `tests/test_runtime_side_effect_registry_contract.py`

Architecture summary:

`RuntimeSideEffectRegistry` centralizes side effect records for command execution, subprocess execution, file mutation, patch apply, rollback action, git action, and generated artifacts. The executor registers observed plan side effects into this registry before returning `RuntimeExecutionResult`.

Migration reasoning:

Side effects must be replay/audit/rollback visible. The registry is intentionally small and in-memory for v1 landing, so persistence can be added without changing the execution result shape.

Validation commands:

```text
python -m pytest tests/test_runtime_side_effect_registry_contract.py -q
```

Expected output:

```text
2 passed
```

Regression risks:

- Existing scattered logs still exist and must be migrated gradually.
- Registry persistence is not yet implemented.

## Phase 4 - Guarded Execution Bridge

Affected files:

- `core/runtime/runtime_execution_bridge.py`

Architecture summary:

The bridge remains admission-only in this pass. It does not import scheduler or executor and does not perform direct execution. It is the policy/lineage boundary before adapter and queue admission.

Migration reasoning:

The bridge must not become a second execution owner. Forwarding to the canonical executor should be added only after the public connected path has tests that prove no bypass exists.

Validation commands:

```text
python -m pytest tests/test_runtime_execution_bridge_contract.py -q
```

Expected output:

```text
bridge contract passes
```

Regression risks:

- Adding bridge forwarding too early would blur ownership and violate the v0 freeze boundary.

## Phase 5 - Controlled Public Execution Surface

Affected files:

- `core/runtime/runtime_public_surface.py`
- `core/runtime/runtime_connector.py`

Architecture summary:

The existing public surface remains request-only until the guarded connected path can be wired without bypassing scheduler/replay/recovery semantics.

Migration reasoning:

This package lands canonical result and side-effect contracts first. Public `accepted_connected_guarded` should be enabled only after scheduler enqueue, bridge validation, executor invocation, side-effect registry, audit trace, replay trace, and rollback trace tests are all present.

Validation commands:

```text
python -m pytest tests/test_runtime_public_surface_contract.py tests/test_runtime_connector_contract.py -q
```

Expected output:

```text
public surface and connector contracts pass
```

Regression risks:

- Switching the default public surface to connected execution without full topology validation risks bypass execution.
