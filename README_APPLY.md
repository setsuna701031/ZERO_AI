# ZERO AER AgentLoop Planner Runtime Dispatch v8.2.4

覆蓋：

```text
core/agent/agent_loop.py
```

新增：

```text
tests/test_agent_loop_planner_runtime_dispatch_contract.py
```

這包正式接：

```text
User
  -> AgentLoop
      -> Planner
          -> PlannerRuntimeDispatch
              -> PersistentRuntimeOrchestrator
                  -> MultiCycleEngineeringLoop
                      -> RecoveryReplayClosure
                          -> LongEngineeringRuntime
```

不改：

```text
core/planning/planner.py
core/runtime/step_executor.py
core/runtime/execution_gateway.py
```

測試：

```bash
python -m pytest tests/test_long_engineering_runtime_contract.py tests/test_recovery_replay_multicycle_contract.py tests/test_persistent_runtime_orchestrator_contract.py tests/test_agent_loop_persistent_runtime_route_contract.py tests/test_planner_runtime_dispatch_contract.py tests/test_agent_loop_planner_runtime_dispatch_contract.py -q
```
