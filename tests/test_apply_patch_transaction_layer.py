from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime.step_executor import StepExecutor
from core.tasks.execution_guard import ExecutionGuard


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _executor(tmp_path: Path) -> tuple[StepExecutor, Path]:
    workspace = tmp_path / "workspace"
    shared = workspace / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    return StepExecutor(workspace_root=str(workspace)), shared


def _result(payload: dict) -> dict:
    return payload.get("result", {}) if isinstance(payload.get("result"), dict) else {}


def _transaction(payload: dict) -> dict:
    return _result(payload).get("transaction", {}) if isinstance(_result(payload).get("transaction"), dict) else {}


def test_apply_patch_handler_registered_regression(tmp_path: Path) -> None:
    executor, _shared = _executor(tmp_path)

    result = executor.execute_step({"type": "apply_patch"})

    assert executor.has_handler("apply_patch") is True
    assert "apply_patch" in executor.list_handlers()
    assert result["ok"] is False
    assert result["error"]["type"] != "unsupported_step_type"


def test_single_file_patch_transaction_applied(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "single.txt", "before\n")
    _write(shared / "single.patch", "--- a/single.txt\n+++ b/single.txt\n@@ -1 +1 @@\n-before\n+after\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patch_path": "workspace/shared/single.patch",
            "target_path": "workspace/shared/single.txt",
            "verify_contains": "after",
        },
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is True
    assert _result(result)["preflight"]["preflight_ok"] is True
    assert tx["status"] == "committed"
    assert tx["verify_result"] == "passed"
    assert [item["status"] for item in tx["status_history"]][-3:] == ["applied", "verifying", "committed"]
    assert tx["transaction_id"].startswith("patch_tx:")
    assert tx["backup_files"]
    assert (shared / "single.txt").read_text(encoding="utf-8") == "after\n"


def test_preflight_transaction_and_verify_metadata_remain_separate(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "layers.txt", "before\n")
    _write(shared / "layers.patch", "--- a/layers.txt\n+++ b/layers.txt\n@@ -1 +1 @@\n-before\n+after\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patch_path": "workspace/shared/layers.patch",
            "target_path": "workspace/shared/layers.txt",
            "verify_contains": "after",
        },
        task={"confirmed": True},
    )

    payload = _result(result)
    preflight = payload["preflight"]
    tx = payload["transaction"]
    verification = payload["verification"]
    assert result["ok"] is True
    assert preflight["preflight_ok"] is True
    assert preflight["changed_files"] == ["workspace/shared/layers.txt"]
    assert "verify_result" not in preflight
    assert "status" not in preflight
    assert tx["status"] == "committed"
    assert tx["verify_result"] == "passed"
    assert verification["verification_ok"] is True


def test_multi_file_patch_transaction_applied(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "a.txt", "a-before\n")
    _write(shared / "b.txt", "b-before\n")
    _write(shared / "a.patch", "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-a-before\n+a-after\n")
    _write(shared / "b.patch", "--- a/b.txt\n+++ b/b.txt\n@@ -1 +1 @@\n-b-before\n+b-after\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patches": [
                {"patch_path": "workspace/shared/a.patch", "target_path": "workspace/shared/a.txt", "verify_contains": "a-after"},
                {"patch_path": "workspace/shared/b.patch", "target_path": "workspace/shared/b.txt", "verify_contains": "b-after"},
            ],
        },
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is True
    assert _result(result)["atomic"] is True
    assert tx["status"] == "committed"
    assert sorted(tx["transaction_files"]) == ["workspace/shared/a.txt", "workspace/shared/b.txt"]
    assert len(tx["backup_files"]) == 2


def test_duplicate_patch_transaction_blocked(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "dup.txt", "before\n")
    _write(shared / "dup.patch", "--- a/dup.txt\n+++ b/dup.txt\n@@ -1 +1 @@\n-before\n+after\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patches": [
                {"patch_path": "workspace/shared/dup.patch", "target_path": "workspace/shared/dup.txt"},
                {"patch_path": "workspace/shared/dup.patch", "target_path": "workspace/shared/dup.txt"},
            ],
        },
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is False
    assert tx["status"] == "blocked"
    assert "duplicate target path" in tx["error_reason"]
    assert (shared / "dup.txt").read_text(encoding="utf-8") == "before\n"


def test_missing_patch_transaction_blocked(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "target.txt", "before\n")

    result = executor.execute_step(
        {"type": "apply_patch", "patch_path": "workspace/shared/missing.patch", "target_path": "workspace/shared/target.txt"},
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is False
    assert tx["status"] == "blocked"
    assert "patch file missing" in tx["error_reason"]
    assert (shared / "target.txt").read_text(encoding="utf-8") == "before\n"


def test_repo_source_unconfirmed_transaction_blocked() -> None:
    guard = ExecutionGuard(workspace_root="workspace", shared_dir="workspace/shared")
    result = guard.check_step(
        step={"type": "apply_patch", "patch_path": "workspace/shared/source.patch", "target_path": "core/runtime/step_executor.py"},
        task_dir="workspace",
    )

    tx = result["transaction"]
    assert result["ok"] is False
    assert tx["status"] == "blocked"
    assert tx["repo_source"] is True
    assert tx["requires_confirmation"] is True
    assert "verify_result" not in tx
    assert "verify_checks" not in tx


def test_repo_source_unconfirmed_step_executor_blocks_without_writing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo_file = tmp_path / "core" / "runtime" / "blocked_demo.py"
    _write(repo_file, "value = 1\n")
    executor, shared = _executor(tmp_path)
    _write(shared / "blocked_source.patch", "--- a/blocked_demo.py\n+++ b/blocked_demo.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patch_path": "workspace/shared/blocked_source.patch",
            "target_path": "core/runtime/blocked_demo.py",
            "verify_contains": "value = 2",
        },
        task={},
    )

    tx = _transaction(result)
    preflight = _result(result)["preflight"]
    assert result["ok"] is False
    assert preflight["requires_confirmation"] is True
    assert tx["status"] == "blocked"
    assert repo_file.read_text(encoding="utf-8") == "value = 1\n"


def test_repo_source_confirmed_transaction_commits_only_after_verify_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo_file = tmp_path / "core" / "runtime" / "demo.py"
    _write(repo_file, "value = 1\n")
    executor, shared = _executor(tmp_path)
    _write(shared / "source.patch", "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "confirmed": True,
            "patch_path": "workspace/shared/source.patch",
            "target_path": "core/runtime/demo.py",
            "verify_contains": "value = 2",
        },
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is True
    assert tx["status"] == "committed"
    assert tx["repo_source"] is True
    assert tx["verify_result"] == "passed"
    assert [item["status"] for item in tx["status_history"]][-3:] == ["applied", "verifying", "committed"]
    assert repo_file.read_text(encoding="utf-8") == "value = 2\n"


def test_repo_source_confirmed_verify_failure_rolls_back_without_commit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    repo_file = tmp_path / "core" / "runtime" / "verify_fail_demo.py"
    _write(repo_file, "value = 1\n")
    executor, shared = _executor(tmp_path)
    _write(shared / "verify_fail_source.patch", "--- a/verify_fail_demo.py\n+++ b/verify_fail_demo.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "confirmed": True,
            "patch_path": "workspace/shared/verify_fail_source.patch",
            "target_path": "core/runtime/verify_fail_demo.py",
            "verify_contains": "value = 3",
        },
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is False
    assert tx["status"] == "failed"
    assert tx["repo_source"] is True
    assert tx["verify_result"] == "failed"
    assert tx["rollback_result"]["rollback_applied"] is True
    assert "committed" not in [item["status"] for item in tx["status_history"]]
    assert repo_file.read_text(encoding="utf-8") == "value = 1\n"


def test_apply_failure_triggers_rollback(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "a.txt", "a-before\n")
    _write(shared / "b.txt", "b-before\n")
    _write(shared / "a.patch", "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-a-before\n+a-after\n")
    _write(shared / "b.patch", "--- a/b.txt\n+++ b/b.txt\n@@ -1 +1 @@\n-not-present\n+b-after\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patches": [
                {"patch_path": "workspace/shared/a.patch", "target_path": "workspace/shared/a.txt"},
                {"patch_path": "workspace/shared/b.patch", "target_path": "workspace/shared/b.txt"},
            ],
        },
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is False
    assert tx["status"] == "failed"
    assert tx["rollback_result"]["rollback_applied"] is True
    assert sorted(tx["rollback_result"]["rolled_back_files"]) == ["workspace/shared/a.txt"]
    assert _result(result)["rollback_applied"] is True
    assert (shared / "a.txt").read_text(encoding="utf-8") == "a-before\n"
    assert (shared / "b.txt").read_text(encoding="utf-8") == "b-before\n"


def test_compile_verify_fail_rolls_back(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "bad.py", "def value():\n    return 1\n")
    _write(shared / "bad.patch", "--- a/bad.py\n+++ b/bad.py\n@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return (\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patch_path": "workspace/shared/bad.patch",
            "target_path": "workspace/shared/bad.py",
            "verify_compile": True,
        },
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is False
    assert tx["status"] == "failed"
    assert tx["verify_result"] == "failed"
    assert tx["rollback_result"]["rollback_applied"] is True
    assert (shared / "bad.py").read_text(encoding="utf-8") == "def value():\n    return 1\n"


def test_custom_verify_fail_rolls_back(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "cmd.txt", "before\n")
    _write(shared / "cmd.patch", "--- a/cmd.txt\n+++ b/cmd.txt\n@@ -1 +1 @@\n-before\n+after\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patch_path": "workspace/shared/cmd.patch",
            "target_path": "workspace/shared/cmd.txt",
            "verify_command": "exit 7",
        },
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is False
    assert tx["status"] == "failed"
    assert any("verify_command" in check for check in tx["verify_checks"])
    assert (shared / "cmd.txt").read_text(encoding="utf-8") == "before\n"


def test_multi_file_boundary_verify_fail_rolls_back(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "ma.txt", "a-before\n")
    _write(shared / "mb.txt", "b-before\n")
    _write(shared / "ma.patch", "--- a/ma.txt\n+++ b/ma.txt\n@@ -1 +1 @@\n-a-before\n+a-after\n")
    _write(shared / "mb.patch", "--- a/mb.txt\n+++ b/mb.txt\n@@ -1 +1 @@\n-b-before\n+b-after\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patches": [
                {"patch_path": "workspace/shared/ma.patch", "target_path": "workspace/shared/ma.txt"},
                {"patch_path": "workspace/shared/mb.patch", "target_path": "workspace/shared/mb.txt"},
            ],
            "verify_command": "exit 9",
        },
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is False
    assert tx["status"] == "failed"
    assert tx["rollback_result"]["rollback_applied"] is True
    assert sorted(tx["transaction_files"]) == ["workspace/shared/ma.txt", "workspace/shared/mb.txt"]
    assert "workspace/shared/ma.txt" in tx["rollback_result"]["rolled_back_files"]
    assert (shared / "ma.txt").read_text(encoding="utf-8") == "a-before\n"
    assert (shared / "mb.txt").read_text(encoding="utf-8") == "b-before\n"


def test_committed_transaction_metadata_is_queryable(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "query.txt", "before\n")
    _write(shared / "query.patch", "--- a/query.txt\n+++ b/query.txt\n@@ -1 +1 @@\n-before\n+after\n")

    result = executor.execute_step(
        {"type": "apply_patch", "patch_path": "workspace/shared/query.patch", "target_path": "workspace/shared/query.txt"},
        task={"confirmed": True},
    )

    tx = _transaction(result)
    assert result["ok"] is True
    assert tx["status"] == "committed"
    assert tx["transaction_id"]
    assert tx["backup_snapshot"]
