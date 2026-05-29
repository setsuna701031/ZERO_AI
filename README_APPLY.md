# ZERO AER Tool Write Verify Runtime Fix v8.2.9

覆蓋/新增：

```text
core/runtime/planner_step_executor_adapter.py
tests/test_aer_tool_write_verify_path_contract.py
```

原因：

```text
StepExecutor 的 planner/tool 範例使用 tool_input 欄位。
ToolCallExecutor 支援 args/input。
前一版 adapter 只補 args/input，導致 StepExecutor tool handler 可能沒有拿到真正寫檔參數。
```

修正：

```text
PlannerStepExecutorAdapter 現在同時輸出：
tool_input
args
input

並且全部指向同一份 tool args。
```

測試：

```bash
python -m pytest tests/test_aer_tool_write_verify_path_contract.py -q
```

完整鏈測試：

```bash
python -m pytest tests/test_long_engineering_runtime_contract.py tests/test_recovery_replay_multicycle_contract.py tests/test_persistent_runtime_orchestrator_contract.py tests/test_agent_loop_persistent_runtime_route_contract.py tests/test_planner_runtime_dispatch_contract.py tests/test_agent_loop_planner_runtime_dispatch_contract.py tests/test_agent_loop_planner_step_executor_bridge_contract.py tests/test_aer_runtime_real_work_smoke_contract.py tests/test_aer_engineering_task_chain_contract.py tests/test_aer_planner_tool_registry_bridge_contract.py tests/test_aer_tool_write_verify_path_contract.py -q
```
