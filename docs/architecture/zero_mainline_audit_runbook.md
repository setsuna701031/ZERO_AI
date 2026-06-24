# ZERO Mainline Audit Package

## 放置位置

把 `tools/zero_mainline_audit.py` 放到：

```text
E:\zero_ai\tools\zero_mainline_audit.py
```

## 執行

在 repo root：

```powershell
cd E:\zero_ai

python tools/zero_mainline_audit.py
```

會產生：

```text
docs/architecture/mainline_audit/zero_mainline_audit_report.json
docs/architecture/mainline_audit/zero_mainline_audit_report.md
```

## 建議接著跑

```powershell
python -m compileall core cli tests tools

python -m pytest `
tests/test_engineering_task_runner_phase5.py `
tests/test_runtime_mainline_evidence_seal_contract.py `
tests/test_runtime_session_resume_identity_boundary.py `
tests/test_engineering_long_horizon_goal_flow.py `
tests/test_runtime_status_canonicalization_seal.py `
tests/test_runtime_status_write_authority_seal.py `
tests/test_runtime_status_ownership_inventory.py `
tests/test_aer_runtime_dispatcher_migration_closure.py `
tests/test_aer_terminal_authority_lineage_seal.py `
tests/test_aer_live_execution_lineage_subject_binding.py `
-q
```

## 這包在做什麼

這不是修功能，而是封板前審計。

它會盤：

```text
Runtime Status Alias
Legacy Scheduler Route
AgentLoop Legacy Branch
Runtime Dispatcher Bypass
Authority Bypass
Monkey Patch / Deprecated / Fallback
Dead Code Marker
Large File Inventory
Non-Mainline Issue Report
```

## 注意

這是保守型 static audit。

有 finding 不等於 bug。

但 critical/high 且出現在 `core/` 的項目，要優先檢查。
