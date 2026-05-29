# ZERO AER v8.2.5 Test Contract Fix

覆蓋：

```text
tests/test_agent_loop_planner_runtime_dispatch_contract.py
```

原因：

```text
v8.2.5 把 AgentLoop planner runtime dispatch 公開 mode 升級為：
planner_step_executor_bridge

舊測試仍固定期待：
planner_runtime_dispatch

功能沒有壞；這是 contract evolution。
```

測試：

```bash
python -m pytest tests/test_long_engineering_runtime_contract.py tests/test_recovery_replay_multicycle_contract.py tests/test_persistent_runtime_orchestrator_contract.py tests/test_agent_loop_persistent_runtime_route_contract.py tests/test_planner_runtime_dispatch_contract.py tests/test_agent_loop_planner_runtime_dispatch_contract.py tests/test_agent_loop_planner_step_executor_bridge_contract.py -q
```
