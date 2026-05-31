# ZERO AER Persistent Engineering Session v8.3.1

新增：

```text
core/runtime/persistent_engineering_session.py
tests/test_persistent_engineering_session_contract.py
```

這包不是單純新增 workflow smoke test，而是新增一個實際 runtime state layer：

```text
PlannerRuntimeDispatch result
-> PersistentEngineeringSession
-> runtime session lineage
-> checkpoint index
-> artifact record
-> resume point
-> continuation record
```

邊界：

```text
PersistentEngineeringSession only records session state.
It does not plan.
It does not execute StepExecutor.
It does not call ToolRegistry.
It does not mutate project files outside its own session JSON.
```

單檔測試：

```bash
python -m pytest tests/test_persistent_engineering_session_contract.py -q
```

完整鏈測試：

```bash
python -m pytest tests/test_long_engineering_runtime_contract.py tests/test_recovery_replay_multicycle_contract.py tests/test_persistent_runtime_orchestrator_contract.py tests/test_agent_loop_persistent_runtime_route_contract.py tests/test_planner_runtime_dispatch_contract.py tests/test_agent_loop_planner_runtime_dispatch_contract.py tests/test_agent_loop_planner_step_executor_bridge_contract.py tests/test_aer_runtime_real_work_smoke_contract.py tests/test_aer_engineering_task_chain_contract.py tests/test_aer_planner_tool_registry_bridge_contract.py tests/test_aer_tool_write_verify_path_contract.py tests/test_aer_multifile_engineering_workflow_contract.py tests/test_persistent_engineering_session_contract.py -q
```
