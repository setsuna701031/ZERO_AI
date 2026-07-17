# Runtime Patch Consolidation Stage 3B - TaskRunner

- before ZERO_PATCH markers: 26
- after ZERO_PATCH markers: 18
- verification passed: False

## Removed markers

- ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V1: 1
- ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V2: 1
- ZERO_PATCH_TASKRUNNER_RUNTIME_GATE_FALLBACK_V3: 1
- ZERO_PATCH_RUNTIME_GATE_FINAL_V4: 1
- ZERO_PATCH_RUNTIME_GATE_FINAL_V5: 1
- ZERO_PATCH_RUNTIME_GATE_FINAL_V6: 1
- ZERO_PATCH_RUNTIME_GATE_FINAL_V7: 1
- ZERO_PATCH_RUNTIME_GATE_FINAL_V8: 1

## Verification

```text
$ C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_evidence_freeze.py
..........                                                               [100%]
10 passed in 0.30s
```

```text
$ C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_execution_ownership_migration_contract.py
.....                                                                    [100%]
5 passed in 4.70s
```

```text
$ C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mainline_freeze_contract.py
....                                                                     [100%]
4 passed in 0.75s
```

```text
$ C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runtime_mode_propagation.py
.F.F                                                                     [100%]
================================== FAILURES ===================================
_ test_task_runner_propagates_runtime_mode_to_step_executor_result_and_trace __

    def test_task_runner_propagates_runtime_mode_to_step_executor_result_and_trace() -> None:
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _dispatcher_owned_task(
            "audit_read",
            "audit",
            {
                "type": "final_answer",
                "content": "audit observation complete",
            },
        )
    
        result = TaskRunner(
            step_executor=StepExecutor(workspace_root=str(TEST_ROOT / "workspace")),
            task_runtime=runtime,
        ).run_task(task, current_tick=1)
    
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))
    
        assert result["ok"] is True
>       assert result["status"] == "finished"
E       AssertionError: assert 'completed' == 'finished'
E         
E         - finished
E         + completed

tests\test_runtime_mode_propagation.py:97: AssertionError
_______ test_task_runner_step_runtime_mode_overrides_task_runtime_mode ________

    def test_task_runner_step_runtime_mode_overrides_task_runtime_mode() -> None:
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _dispatcher_owned_task(
            "step_override",
            "execute",
            {
                "type": "final_answer",
                "runtime_mode": "replay",
                "content": "replay observation complete",
            },
        )
    
        result = TaskRunner(
            step_executor=StepExecutor(workspace_root=str(TEST_ROOT / "workspace")),
            task_runtime=runtime,
        ).run_task(task, current_tick=1)
    
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))
    
        assert result["ok"] is True
>       assert result["status"] == "finished"
E       AssertionError: assert 'completed' == 'finished'
E         
E         - finished
E         + completed

tests\test_runtime_mode_propagation.py:154: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_runtime_mode_propagation.py::test_task_runner_propagates_runtime_mode_to_step_executor_result_and_trace
FAILED tests/test_runtime_mode_propagation.py::test_task_runner_step_runtime_mode_overrides_task_runtime_mode
2 failed, 2 passed in 3.80s
```

```text
$ C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m pytest -q tests/test_runner_scheduler_boundary_survival.py
F..                                                                      [100%]
================================== FAILURES ===================================
_ test_runtime_task_runner_preserves_operator_session_through_runtime_and_executor _

tmp_path = WindowsPath('C:/Users/heero/AppData/Local/Temp/pytest-of-heero/pytest-3021/test_runtime_task_runner_prese0')

    def test_runtime_task_runner_preserves_operator_session_through_runtime_and_executor(tmp_path):
        from core.runtime.task_runner import TaskRunner
    
        operator_runtime, bridge, bootstrap = _operator_stack()
        task = _task(tmp_path, task_id="runner-task", step_type="runner_success")
        task["steps"][1]["type"] = "runner_failure"
        context = {"enable_operator_session": True}
    
        bootstrap_result = bootstrap.ensure_session_for_task(task, context=context)
        session_id = bootstrap_result["operator_session_id"]
        assert session_id
    
        task_runtime = TaskRuntime(workspace_root=str(tmp_path), operator_bridge=bridge)
        step_executor = StepExecutor(workspace_root=str(tmp_path), operator_bridge=bridge)
        step_executor.register_handler("runner_success", _success_handler)
        step_executor.register_handler("runner_failure", _failure_handler)
        runner = TaskRunner(task_runtime=task_runtime, step_executor=step_executor)
    
        first = runner.run_task_tick(_with_dispatch_capability(task), current_tick=1)
        assert first["ok"] is True
>       assert first["runtime_state"]["operator_session_id"] == session_id
               ^^^^^^^^^^^^^^^^^^^^^^
E       KeyError: 'runtime_state'

tests\test_runner_scheduler_boundary_survival.py:127: KeyError
=========================== short test summary info ===========================
FAILED tests/test_runner_scheduler_boundary_survival.py::test_runtime_task_runner_preserves_operator_session_through_runtime_and_executor
1 failed, 2 passed in 2.56s
```

```text
$ C:\Users\heero\AppData\Local\Programs\Python\Python311\python.exe -m compileall core
Listing 'core'...
Listing 'core\\_archive_candidate'...
Listing 'core\\adaptive'...
Listing 'core\\agent'...
Listing 'core\\artifacts'...
Listing 'core\\audit'...
Listing 'core\\capabilities'...
Listing 'core\\control'...
Listing 'core\\display'...
Listing 'core\\engineering'...
Listing 'core\\events'...
Listing 'core\\evidence'...
Listing 'core\\goals'...
Listing 'core\\memory'...
Listing 'core\\operator'...
Listing 'core\\persona'...
Listing 'core\\planning'...
Listing 'core\\policy'...
Listing 'core\\program'...
Listing 'core\\repo_sandbox'...
Listing 'core\\reports'...
Listing 'core\\runtime'...
Listing 'core\\runtime\\snapshot_loader'...
Listing 'core\\session'...
Listing 'core\\system'...
Listing 'core\\tasks'...
Listing 'core\\tasks\\scheduler_core'...
Listing 'core\\tools'...
Listing 'core\\tools\\_archive_candidate'...
Listing 'core\\verification'...
Listing 'core\\watch'...
Listing 'core\\worker'...
Listing 'core\\world'...
```