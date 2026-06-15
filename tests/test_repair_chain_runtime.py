from __future__ import annotations

import json
import copy
import shutil
from pathlib import Path

from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime
from core.runtime.step_executor import StepExecutor
from core.tasks.scheduler import Scheduler
from core.tasks.execution_guard import ExecutionGuard


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / ".test_tmp" / "repair_chain_runtime"


class RepairChainExecutor:
    def __init__(self, *, fail_step_type: str = "") -> None:
        self.calls: list[str] = []
        self.fail_step_type = fail_step_type

    def execute_step(self, **kwargs: object) -> dict:
        step = kwargs["step"]
        step_index = int(kwargs["step_index"])
        previous_result = kwargs.get("previous_result")
        assert isinstance(step, dict)
        step_type = str(step.get("type") or "")
        self.calls.append(step_type)

        if step_type == self.fail_step_type:
            return {
                "ok": False,
                "step_index": step_index,
                "step_type": step_type,
                "error": f"{step_type} failed",
                "execution_trace": [
                    {"step_index": step_index, "step_type": step_type, "ok": False, "error": f"{step_type} failed"}
                ],
            }

        result: dict = {
            "ok": True,
            "step_index": step_index,
            "step_type": step_type,
            "message": f"{step_type} ok",
            "result": {"ok": True, "step_type": step_type, "message": f"{step_type} ok"},
            "execution_trace": [
                {"step_index": step_index, "step_type": step_type, "ok": True, "message": f"{step_type} ok"}
            ],
        }
        if step_index == 0:
            result["result"].update({"verification_passed": False, "failed_reason": "expected add to use plus"})
        if step_type == "code_chain_repair":
            result["result"].update({"patch_path": "workspace/shared/fix.patch", "repair_uses_previous": bool(previous_result)})
        if step_type == "apply_unified_diff":
            result["result"].update({"applied": True, "target_path": step.get("target_path")})
        if step_index == 3:
            result["result"].update({"verification_passed": True})
        return result


class InvalidRepairThenRealApplyExecutor:
    def __init__(self) -> None:
        self.real = StepExecutor()

    def execute_step(self, **kwargs: object) -> dict:
        step = kwargs["step"]
        assert isinstance(step, dict)
        if step.get("type") == "code_chain_repair":
            return {
                "ok": True,
                "message": "invalid repair payload",
                "result": {"patch": "--- half made patch ---"},
            }
        return self.real.execute_step(**kwargs)


class FinalVerifyFailExecutor:
    def __init__(self, *, delete_backup_before_verify: bool = False) -> None:
        self.real = StepExecutor()
        self.delete_backup_before_verify = delete_backup_before_verify
        self.calls: list[tuple[str, int]] = []

    def execute_step(self, **kwargs: object) -> dict:
        step = kwargs["step"]
        step_index = int(kwargs["step_index"])
        assert isinstance(step, dict)
        self.calls.append((str(step.get("type") or ""), step_index))
        if step.get("type") == "code_chain_verify" and step_index == 3:
            if self.delete_backup_before_verify:
                backup_path = REPO_ROOT / "workspace" / "shared" / "code_chain_probe.py.bak_edit_payload"
                if backup_path.exists():
                    backup_path.unlink()
            return {
                "ok": False,
                "step_index": step_index,
                "step_type": "code_chain_verify",
                "message": "verification_failed",
                "error": "verification_failed",
                "result": {
                    "requested_functions": ["add", "multiply"],
                    "failed_functions": ["multiply"],
                    "verification": {
                        "ok": False,
                        "requested_functions": ["add", "multiply"],
                        "failed_functions": ["multiply"],
                    },
                },
                "execution_trace": [
                    {"step_index": step_index, "step_type": "code_chain_verify", "ok": False, "error": "verification_failed"}
                ],
            }
        return self.real.execute_step(**kwargs)


class RegressionFailThenRealRepairExecutor:
    def __init__(self) -> None:
        self.real = StepExecutor()

    def execute_step(self, **kwargs: object) -> dict:
        step = kwargs["step"]
        task = kwargs.get("task")
        assert isinstance(step, dict)
        if step.get("type") == "code_chain_repair":
            strategy = "minimal_patch"
            if isinstance(task, dict):
                strategy = task.get("repair_context", {}).get("strategy", {}).get("current_strategy", "minimal_patch")
            if strategy == "minimal_patch":
                return {
                    "ok": True,
                    "message": "minimal strategy intentionally emits regression failure",
                    "strategy": "minimal_patch",
                    "edit_payload": {
                        "old_text": "VALUE = 1\n",
                        "new_text": "def broken(:\n",
                        "schema": "replacement_pair_v1",
                        "strategy": "minimal_patch",
                    },
                    "result": {
                        "strategy": "minimal_patch",
                        "edit_payload": {
                            "old_text": "VALUE = 1\n",
                            "new_text": "def broken(:\n",
                            "schema": "replacement_pair_v1",
                            "strategy": "minimal_patch",
                        },
                    },
                }
            return {
                "ok": True,
                "message": "function_rewrite strategy emits valid payload",
                "strategy": strategy,
                "edit_payload": {
                    "old_text": "VALUE = 1\n",
                    "new_text": "VALUE = 2\n",
                    "schema": "replacement_pair_v1",
                    "strategy": strategy,
                },
                "result": {
                    "strategy": strategy,
                    "edit_payload": {
                        "old_text": "VALUE = 1\n",
                        "new_text": "VALUE = 2\n",
                        "schema": "replacement_pair_v1",
                        "strategy": strategy,
                    },
                },
            }
        if step.get("type") == "code_chain_verify":
            return {"ok": True, "message": "verify ok", "result": {"verification": {"ok": True}}}
        return self.real.execute_step(**kwargs)


def setup_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def teardown_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def _repair_task() -> dict:
    task_dir = TEST_ROOT / "tasks" / "repair_chain"
    failed_step = {"type": "verify", "target_path": "workspace/shared/math_ops.py"}
    return {
        "task_id": "repair_chain",
        "task_name": "repair_chain",
        "goal": "repair workspace/shared/math_ops.py",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "failed_step": failed_step,
        "failed_file": "workspace/shared/math_ops.py",
        "failed_reason": "initial verify found broken add",
        "repair_intent": "fix add implementation",
        "repair_context": {
            "original_failed_step": failed_step,
            "failed_file": "workspace/shared/math_ops.py",
            "failed_reason": "initial verify found broken add",
        },
        "steps": [
            {"id": "verify_before", "type": "code_chain_verify", "target_path": "workspace/shared/math_ops.py"},
            {"id": "repair", "type": "code_chain_repair", "target_path": "workspace/shared/math_ops.py"},
            {
                "id": "apply",
                "type": "apply_unified_diff",
                "patch_path": "workspace/shared/fix.patch",
                "target_path": "workspace/shared/math_ops.py",
            },
            {"id": "verify_after", "type": "code_chain_verify", "target_path": "workspace/shared/math_ops.py"},
        ],
        "current_step_index": 0,
        "max_replans": 1,
    }


def _read_runtime_json() -> dict:
    return json.loads(Path(_repair_task()["runtime_state_file"]).read_text(encoding="utf-8"))


def test_repair_chain_without_dispatcher_lineage_cannot_persist_finished_state() -> None:
    executor = RepairChainExecutor()
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runner = TaskRunner(step_executor=executor, task_runtime=runtime)

    first = runner.run_task(_repair_task(), current_tick=1)
    assert first["ok"] is False
    assert first["status"] == "retrying"
    assert first["error"]["type"] == "execution_authority_denied"

    reloaded = runtime.load_runtime_state(_repair_task())
    assert reloaded["current_step_index"] == 0

    second = runner.run_task(_repair_task(), current_tick=2)
    third = runner.run_task(_repair_task(), current_tick=3)
    fourth = runner.run_task(_repair_task(), current_tick=4)
    final_json = _read_runtime_json()

    assert second["status"] == third["status"] == "retrying"
    assert fourth["ok"] is False
    assert fourth["status"] == "retrying"
    assert fourth["error"]["type"] == "execution_authority_denied"
    assert final_json["current_step_index"] == 0
    assert final_json["status"] in {"retrying", "blocked"}
    assert "runtime dispatcher live capability required" in final_json["last_error"]
    assert executor.calls == []
    assert final_json["execution_log"]
    assert all(item["step_index"] == 0 for item in final_json["execution_log"])
    assert all(item["result"]["executed"] is False for item in final_json["execution_log"])

    repair_context = final_json["repair_context"]
    assert not repair_context.get("repair_result")
    assert not repair_context.get("apply_result")
    assert repair_context["verify_result"]["step_index"] == 0
    assert repair_context["verify_result"]["result"]["executed"] is False
    assert not repair_context.get("repo_impact")
    assert not repair_context.get("rollback_result")
    assert not repair_context.get("regression_verify")
    assert final_json.get("completion_authority") is None
    assert final_json.get("terminal_execution_evidence") is None


def test_reload_resume_without_dispatcher_lineage_does_not_execute_repair_steps() -> None:
    executor = RepairChainExecutor()
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))

    TaskRunner(step_executor=executor, task_runtime=runtime).run_task(_repair_task(), current_tick=1)
    assert runtime.load_runtime_state(_repair_task())["current_step_index"] == 0

    resumed_runner = TaskRunner(step_executor=executor, task_runtime=runtime)
    resumed_runner.run_task(_repair_task(), current_tick=2)
    resumed_runner.run_task(_repair_task(), current_tick=3)
    resumed_runner.run_task(_repair_task(), current_tick=4)

    state = _read_runtime_json()
    assert executor.calls == []
    assert state["current_step_index"] == 0
    assert state["status"] in {"retrying", "blocked"}
    assert "runtime dispatcher live capability required" in state["last_error"]


def test_custom_repair_executor_cannot_run_without_dispatcher_lineage() -> None:
    executor = RepairChainExecutor(fail_step_type="code_chain_repair")
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runner = TaskRunner(step_executor=executor, task_runtime=runtime)

    runner.run_task(_repair_task(), current_tick=1)
    result = runner.run_task(_repair_task(), current_tick=2)
    failed_json = _read_runtime_json()

    assert result["ok"] is False
    assert result["status"] == "retrying"
    assert result["error"]["type"] == "execution_authority_denied"
    assert failed_json["status"] in {"retrying", "blocked"}
    assert failed_json["current_step_index"] == 0
    assert "runtime dispatcher live capability required" in failed_json["last_error"]
    assert executor.calls == []


def test_duplicate_repair_enqueue_is_suppressed() -> None:
    workspace = TEST_ROOT / "scheduler_workspace"
    shared = workspace / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "math_ops.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    scheduler = Scheduler(workspace_dir=str(workspace), debug=False)
    goal = "repair broken math functions in workspace/shared/math_ops.py"

    first_gate = scheduler._pre_enqueue_repair_fingerprint_gate(goal=goal)
    second_gate = scheduler._pre_enqueue_repair_fingerprint_gate(goal=goal)

    assert first_gate["ok"] is True
    assert first_gate["suppress"] is False
    assert second_gate["ok"] is True
    assert second_gate["suppress"] is True
    assert second_gate["duplicate_suppressed"] is True
    assert "duplicate autonomous repair task suppressed" in second_gate["message"]


def _syntax_repair_task(max_strategy_attempts: int = 3) -> dict:
    task_dir = TEST_ROOT / "tasks" / "syntax_repair_chain"
    return {
        "task_id": "syntax_repair_chain",
        "task_name": "syntax_repair_chain",
        "goal": "Analyze workspace/shared/code_chain_probe.py and repair broken math functions",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "failed_file": "workspace/shared/code_chain_probe.py",
        "failed_reason": "python syntax error",
        "repair_intent": "fix syntax error",
        "repair_context": {
            "strategy": {
                "current_strategy": "minimal_patch",
                "max_strategy_attempts": max_strategy_attempts,
            }
        },
        "steps": [
            {
                "id": "verify_before",
                "type": "code_chain_verify",
                "target_path": "workspace/shared/code_chain_probe.py",
                "task_text": "Analyze workspace/shared/code_chain_probe.py and repair broken math functions",
                "continue_on_failure": True,
            },
            {
                "id": "repair",
                "type": "code_chain_repair",
                "target_path": "workspace/shared/code_chain_probe.py",
                "task_text": "Analyze workspace/shared/code_chain_probe.py and repair broken math functions",
            },
            {
                "id": "apply",
                "type": "apply_patch",
                "target_path": "workspace/shared/code_chain_probe.py",
            },
            {
                "id": "verify_after",
                "type": "code_chain_verify",
                "target_path": "workspace/shared/code_chain_probe.py",
                "task_text": "Analyze workspace/shared/code_chain_probe.py and repair broken math functions",
            },
        ],
        "current_step_index": 0,
    }


def test_real_syntax_repair_without_dispatcher_lineage_is_rolled_back() -> None:
    probe_path = REPO_ROOT / "workspace" / "shared" / "code_chain_probe.py"
    backup_path = Path(str(probe_path) + ".bak_edit_payload")
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe_path.exists()
    original_text = probe_path.read_text(encoding="utf-8") if original_exists else None

    try:
        probe_path.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        if backup_path.exists():
            backup_path.unlink()

        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime)

        results = _run_until_terminal(runner, _syntax_repair_task)
        state = json.loads(Path(_syntax_repair_task()["runtime_state_file"]).read_text(encoding="utf-8"))
        repaired = probe_path.read_text(encoding="utf-8")

        assert [item["action"] for item in results].count("strategy_retry") == 0
        assert results[-1]["ok"] is False
        assert results[-1]["action"] == "retry"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert repaired == "def add(a,b)\n    return a+b\n"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert state["current_step_index"] < state["steps_total"]
    finally:
        if original_exists:
            probe_path.write_text(original_text or "", encoding="utf-8")
        elif probe_path.exists():
            probe_path.unlink()
        if backup_path.exists():
            backup_path.unlink()


def test_invalid_repair_executor_cannot_reach_apply_without_dispatcher_lineage() -> None:
    probe_path = REPO_ROOT / "workspace" / "shared" / "code_chain_probe.py"
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe_path.exists()
    original_text = probe_path.read_text(encoding="utf-8") if original_exists else None

    try:
        probe_path.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=InvalidRepairThenRealApplyExecutor(), task_runtime=runtime)

        runner.run_task(_syntax_repair_task(), current_tick=1)
        runner.run_task(_syntax_repair_task(), current_tick=2)
        result = runner.run_task(_syntax_repair_task(), current_tick=3)
        state = json.loads(Path(_syntax_repair_task()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["ok"] is False
        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert state["status"] in {"retrying", "blocked"}
        assert state["current_step_index"] == 0
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert probe_path.read_text(encoding="utf-8") == "def add(a,b)\n    return a+b\n"
    finally:
        if original_exists:
            probe_path.write_text(original_text or "", encoding="utf-8")
        elif probe_path.exists():
            probe_path.unlink()


def test_final_verify_executor_cannot_run_without_dispatcher_lineage() -> None:
    probe_path = REPO_ROOT / "workspace" / "shared" / "code_chain_probe.py"
    backup_path = Path(str(probe_path) + ".bak_edit_payload")
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe_path.exists()
    original_text = probe_path.read_text(encoding="utf-8") if original_exists else None

    try:
        broken_text = "def add(a,b)\n    return a+b\n"
        probe_path.write_text(broken_text, encoding="utf-8")
        if backup_path.exists():
            backup_path.unlink()

        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        executor = FinalVerifyFailExecutor()
        runner = TaskRunner(step_executor=executor, task_runtime=runtime)
        results = [runner.run_task(_syntax_repair_task(max_strategy_attempts=1), current_tick=tick) for tick in range(1, 5)]
        state = json.loads(Path(_syntax_repair_task(max_strategy_attempts=1)["runtime_state_file"]).read_text(encoding="utf-8"))

        assert results[-1]["ok"] is False
        assert results[-1]["status"] == "retrying"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert probe_path.read_text(encoding="utf-8") == broken_text
        assert state["status"] in {"retrying", "blocked"}
        assert state["current_step_index"] == 0
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert executor.calls == []
        assert not state["repair_context"].get("rollback_result")
    finally:
        if original_exists:
            probe_path.write_text(original_text or "", encoding="utf-8")
        elif probe_path.exists():
            probe_path.unlink()
        if backup_path.exists():
            backup_path.unlink()


def test_rollback_is_not_attempted_without_dispatcher_lineage() -> None:
    probe_path = REPO_ROOT / "workspace" / "shared" / "code_chain_probe.py"
    backup_path = Path(str(probe_path) + ".bak_edit_payload")
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe_path.exists()
    original_text = probe_path.read_text(encoding="utf-8") if original_exists else None

    try:
        probe_path.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        if backup_path.exists():
            backup_path.unlink()

        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        executor = FinalVerifyFailExecutor(delete_backup_before_verify=True)
        runner = TaskRunner(step_executor=executor, task_runtime=runtime)
        runner.run_task(_syntax_repair_task(max_strategy_attempts=1), current_tick=1)
        runner.run_task(_syntax_repair_task(max_strategy_attempts=1), current_tick=2)
        runner.run_task(_syntax_repair_task(max_strategy_attempts=1), current_tick=3)
        result = runner.run_task(_syntax_repair_task(max_strategy_attempts=1), current_tick=4)
        state = json.loads(Path(_syntax_repair_task(max_strategy_attempts=1)["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["ok"] is False
        assert result["error"]["type"] == "execution_authority_denied"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert state["repair_context"]["rollback_result"] is None
        assert executor.calls == []
    finally:
        if original_exists:
            probe_path.write_text(original_text or "", encoding="utf-8")
        elif probe_path.exists():
            probe_path.unlink()
        if backup_path.exists():
            backup_path.unlink()


def test_successful_rollback_is_idempotent_on_later_tick() -> None:
    probe_path = REPO_ROOT / "workspace" / "shared" / "code_chain_probe.py"
    backup_path = Path(str(probe_path) + ".bak_edit_payload")
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe_path.exists()
    original_text = probe_path.read_text(encoding="utf-8") if original_exists else None

    try:
        broken_text = "def add(a,b)\n    return a+b\n"
        probe_path.write_text(broken_text, encoding="utf-8")
        if backup_path.exists():
            backup_path.unlink()

        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        executor = FinalVerifyFailExecutor()
        runner = TaskRunner(step_executor=executor, task_runtime=runtime)
        for tick in range(1, 5):
            runner.run_task(_syntax_repair_task(max_strategy_attempts=1), current_tick=tick)
        state_after_rollback = json.loads(Path(_syntax_repair_task(max_strategy_attempts=1)["runtime_state_file"]).read_text(encoding="utf-8"))
        file_after_rollback = probe_path.read_text(encoding="utf-8")

        result = runner.run_task(_syntax_repair_task(max_strategy_attempts=1), current_tick=5)
        state_after_rerun = json.loads(Path(_syntax_repair_task(max_strategy_attempts=1)["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["action"] == "retry"
        assert result["status"] == "retrying"
        assert file_after_rollback == broken_text
        assert probe_path.read_text(encoding="utf-8") == file_after_rollback
        assert state_after_rerun["repair_context"]["rollback_result"] == state_after_rollback["repair_context"]["rollback_result"]
    finally:
        if original_exists:
            probe_path.write_text(original_text or "", encoding="utf-8")
        elif probe_path.exists():
            probe_path.unlink()
        if backup_path.exists():
            backup_path.unlink()


def _apply_task(task_id: str, step: dict) -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": task_id,
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [step],
        "current_step_index": 0,
    }


def _strategy_task(task_id: str, target_path: str, max_strategy_attempts: int = 3) -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": f"repair {target_path}",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "repair_context": {
            "strategy": {
                "current_strategy": "minimal_patch",
                "max_strategy_attempts": max_strategy_attempts,
            }
        },
        "steps": [
            {"type": "code_chain_verify", "target_path": target_path, "task_text": f"repair {target_path}", "continue_on_failure": True},
            {"type": "code_chain_repair", "target_path": target_path, "task_text": f"repair {target_path}"},
            {"type": "apply_patch", "target_path": target_path},
            {"type": "code_chain_verify", "target_path": target_path, "task_text": f"repair {target_path}"},
        ],
        "current_step_index": 0,
    }


def _run_until_terminal(runner: TaskRunner, task_factory, *, max_ticks: int = 12) -> list[dict]:
    results = []
    for tick in range(1, max_ticks + 1):
        result = runner.run_task(task_factory(), current_tick=tick)
        results.append(result)
        status = str(result.get("status") or "").lower()
        if status in {"finished", "failed", "done", "completed"}:
            break
    return results


def test_shared_single_file_apply_without_dispatcher_lineage_is_blocked() -> None:
    target = REPO_ROOT / "workspace" / "shared" / "impact_single.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    original_exists = target.exists()
    original_text = target.read_text(encoding="utf-8") if original_exists else None
    try:
        target.write_text("VALUE = 1\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "workspace/shared/impact_single.py",
            "edit_payload": {
                "old_text": "VALUE = 1\n",
                "new_text": "VALUE = 2\n",
                "schema": "replacement_pair_v1",
            },
        }
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(_apply_task("shared_low_risk", step), current_tick=1)
        state = json.loads(Path(_apply_task("shared_low_risk", step)["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["ok"] is False
        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    finally:
        if original_exists:
            target.write_text(original_text or "", encoding="utf-8")
        elif target.exists():
            target.unlink()
        backup = Path(str(target) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_core_runtime_apply_stops_at_dispatcher_lineage_denial() -> None:
    step = {
        "type": "apply_patch",
        "target_path": "core/runtime/task_runtime.py",
        "edit_payload": {
            "old_text": "# old\n",
            "new_text": "# new\n",
            "schema": "replacement_pair_v1",
        },
    }
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _apply_task("core_blocked", step)
    result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"
    assert state["status"] in {"retrying", "blocked"}
    assert "runtime dispatcher live capability required" in state["last_error"]
    assert not state["repair_context"].get("repo_impact")


def test_multi_file_repo_repair_plan_stops_at_dispatcher_lineage_denial() -> None:
    step = {
        "type": "apply_patch",
        "target_path": "core/runtime/task_runtime.py",
        "edit_payload": {
            "old_text": "# old\n",
            "new_text": "# new\n",
            "schema": "replacement_pair_v1",
            "changed_files": ["core/runtime/task_runtime.py", "core/runtime/task_runner.py"],
        },
    }
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _apply_task("multi_file_blocked", step)
    result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"
    assert state["status"] in {"retrying", "blocked"}
    assert "runtime dispatcher live capability required" in state["last_error"]
    assert not state["repair_context"].get("repo_impact")


def test_import_impact_detection_does_not_run_without_dispatcher_lineage() -> None:
    shared = REPO_ROOT / "workspace" / "shared"
    a_path = shared / "impact_a.py"
    b_path = shared / "impact_b.py"
    shared.mkdir(parents=True, exist_ok=True)
    originals = {
        a_path: a_path.read_text(encoding="utf-8") if a_path.exists() else None,
        b_path: b_path.read_text(encoding="utf-8") if b_path.exists() else None,
    }
    try:
        a_path.write_text("VALUE = 1\n", encoding="utf-8")
        b_path.write_text("import impact_a\nprint(impact_a.VALUE)\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "workspace/shared/impact_a.py",
            "edit_payload": {
                "old_text": "VALUE = 1\n",
                "new_text": "VALUE = 2\n",
                "schema": "replacement_pair_v1",
            },
        }
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _apply_task("import_impact", step)
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["ok"] is False
        assert result["error"]["type"] == "execution_authority_denied"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert not state["repair_context"].get("repo_impact")
        assert a_path.read_text(encoding="utf-8") == "VALUE = 1\n"
    finally:
        for path, text in originals.items():
            if text is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(text, encoding="utf-8")
        backup = Path(str(a_path) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_single_file_dependency_impact_does_not_run_without_dispatcher_lineage() -> None:
    target = REPO_ROOT / "workspace" / "shared" / "impact_no_importers.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    original_exists = target.exists()
    original_text = target.read_text(encoding="utf-8") if original_exists else None
    try:
        target.write_text("VALUE = 1\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "workspace/shared/impact_no_importers.py",
            "edit_payload": {
                "old_text": "VALUE = 1\n",
                "new_text": "VALUE = 2\n",
                "schema": "replacement_pair_v1",
            },
        }
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _apply_task("impact_no_importers", step)
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert not state["repair_context"].get("repo_impact")
        assert not state["repair_context"].get("rollback_result")
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    finally:
        if original_exists:
            target.write_text(original_text or "", encoding="utf-8")
        elif target.exists():
            target.unlink()
        backup = Path(str(target) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_impacted_file_regression_does_not_run_without_dispatcher_lineage() -> None:
    shared = REPO_ROOT / "workspace" / "shared"
    a_path = shared / "impact_plan_a.py"
    b_path = shared / "impact_plan_b.py"
    shared.mkdir(parents=True, exist_ok=True)
    originals = {
        a_path: a_path.read_text(encoding="utf-8") if a_path.exists() else None,
        b_path: b_path.read_text(encoding="utf-8") if b_path.exists() else None,
    }
    try:
        a_path.write_text("VALUE = 1\n", encoding="utf-8")
        b_path.write_text("import impact_plan_a\ndef broken(:\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "workspace/shared/impact_plan_a.py",
            "edit_payload": {
                "old_text": "VALUE = 1\n",
                "new_text": "VALUE = 2\n",
                "schema": "replacement_pair_v1",
            },
        }
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _apply_task("impact_plan_fail", step)
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert not state["repair_context"].get("multi_file_plan")
        assert not state["repair_context"].get("regression_verify")
        assert a_path.read_text(encoding="utf-8") == "VALUE = 1\n"
    finally:
        for path, text in originals.items():
            if text is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(text, encoding="utf-8")
        backup = Path(str(a_path) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_repo_source_importer_stops_before_confirmation_without_dispatcher_lineage() -> None:
    core_path = REPO_ROOT / "core" / "foo_dependency_probe.py"
    test_path = REPO_ROOT / "tests" / "test_foo_dependency_probe.py"
    originals = {
        core_path: core_path.read_text(encoding="utf-8") if core_path.exists() else None,
        test_path: test_path.read_text(encoding="utf-8") if test_path.exists() else None,
    }
    try:
        core_path.write_text("VALUE = 1\n", encoding="utf-8")
        test_path.write_text("from core import foo_dependency_probe\n\nVALUE = foo_dependency_probe.VALUE\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "core/foo_dependency_probe.py",
            "edit_payload": {
                "old_text": "VALUE = 1\n",
                "new_text": "VALUE = 2\n",
                "schema": "replacement_pair_v1",
            },
        }
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _apply_task("repo_source_importer", step)
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["ok"] is False
        assert result["error"]["type"] == "execution_authority_denied"
        assert core_path.read_text(encoding="utf-8") == "VALUE = 1\n"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert not state["repair_context"].get("repo_impact")
    finally:
        for path, text in originals.items():
            if text is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(text, encoding="utf-8")


def test_multi_file_shared_apply_does_not_start_without_dispatcher_lineage() -> None:
    shared = REPO_ROOT / "workspace" / "shared"
    a_path = shared / "multi_apply_a.py"
    b_path = shared / "multi_apply_b.py"
    shared.mkdir(parents=True, exist_ok=True)
    originals = {
        a_path: a_path.read_text(encoding="utf-8") if a_path.exists() else None,
        b_path: b_path.read_text(encoding="utf-8") if b_path.exists() else None,
    }
    try:
        a_path.write_text("VALUE = 1\n", encoding="utf-8")
        b_path.write_text("VALUE = 10\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "workspace/shared/multi_apply_a.py",
            "edit_payload": {
                "schema": "replacement_pair_v1",
                "file_edits": [
                    {
                        "target_path": "workspace/shared/multi_apply_a.py",
                        "old_text": "VALUE = 1\n",
                        "new_text": "VALUE = 2\n",
                    },
                    {
                        "target_path": "workspace/shared/multi_apply_b.py",
                        "old_text": "VALUE = 99\n",
                        "new_text": "VALUE = 20\n",
                    },
                ],
            },
        }
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _apply_task("multi_apply_rollback", step)
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert state["status"] in {"retrying", "blocked"}
        assert a_path.read_text(encoding="utf-8") == "VALUE = 1\n"
        assert b_path.read_text(encoding="utf-8") == "VALUE = 10\n"
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert state["repair_context"]["rollback_result"] is None
    finally:
        for path, text in originals.items():
            if text is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(text, encoding="utf-8")
        for path in (a_path, b_path):
            backup = Path(str(path) + ".bak_edit_payload")
            if backup.exists():
                backup.unlink()


def test_strategy_minimal_patch_without_dispatcher_lineage_does_not_apply() -> None:
    target = REPO_ROOT / "workspace" / "shared" / "strategy_minimal.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    original_exists = target.exists()
    original_text = target.read_text(encoding="utf-8") if original_exists else None
    try:
        target.write_text("def add(a,b)\n    return a+b\n\ndef multiply(a, b):\n    return a * b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime)
        task_factory = lambda: _strategy_task("strategy_minimal", "workspace/shared/strategy_minimal.py")
        results = _run_until_terminal(runner, task_factory)
        state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert results[-1]["status"] == "retrying"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert target.read_text(encoding="utf-8") == "def add(a,b)\n    return a+b\n\ndef multiply(a, b):\n    return a * b\n"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert state["repair_context"]["strategy"]["current_strategy"] == "minimal_patch"
        assert not [item for item in state["repair_context"]["strategy"]["strategy_history"] if item["outcome"] == "failed"]
    finally:
        if original_exists:
            target.write_text(original_text or "", encoding="utf-8")
        elif target.exists():
            target.unlink()
        backup = Path(str(target) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_strategy_without_dispatcher_lineage_does_not_switch_or_finish() -> None:
    target = REPO_ROOT / "workspace" / "shared" / "strategy_math.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    original_exists = target.exists()
    original_text = target.read_text(encoding="utf-8") if original_exists else None
    try:
        target.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime)
        task_factory = lambda: _syntax_repair_task()
        # _syntax_repair_task targets code_chain_probe.py, so set that file too.
        probe = REPO_ROOT / "workspace" / "shared" / "code_chain_probe.py"
        probe_original_exists = probe.exists()
        probe_original_text = probe.read_text(encoding="utf-8") if probe_original_exists else None
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        try:
            results = _run_until_terminal(runner, task_factory)
            state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))
            assert results[-1]["status"] == "retrying"
            assert results[-1]["error"]["type"] == "execution_authority_denied"
            assert state["status"] in {"retrying", "blocked"}
            assert "runtime dispatcher live capability required" in state["last_error"]
            assert state["repair_context"]["strategy"]["current_strategy"] == "minimal_patch"
            assert not [item for item in state["repair_context"]["strategy"]["strategy_history"] if item["outcome"] == "failed"]
            assert probe.read_text(encoding="utf-8") == "def add(a,b)\n    return a+b\n"
        finally:
            if probe_original_exists:
                probe.write_text(probe_original_text or "", encoding="utf-8")
            elif probe.exists():
                probe.unlink()
            backup = Path(str(probe) + ".bak_edit_payload")
            if backup.exists():
                backup.unlink()
    finally:
        if original_exists:
            target.write_text(original_text or "", encoding="utf-8")
        elif target.exists():
            target.unlink()


def test_strategy_recording_executor_without_dispatcher_lineage_is_rejected() -> None:
    target = REPO_ROOT / "workspace" / "shared" / "strategy_regression.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    original_exists = target.exists()
    original_text = target.read_text(encoding="utf-8") if original_exists else None
    try:
        target.write_text("VALUE = 1\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=RegressionFailThenRealRepairExecutor(), task_runtime=runtime)
        task_factory = lambda: _strategy_task("strategy_regression", "workspace/shared/strategy_regression.py")
        results = _run_until_terminal(runner, task_factory)
        state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert not any(result.get("action") == "strategy_retry" for result in results)
        assert results[-1]["status"] == "retrying"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert state["repair_context"]["strategy"]["current_strategy"] == "minimal_patch"
    finally:
        if original_exists:
            target.write_text(original_text or "", encoding="utf-8")
        elif target.exists():
            target.unlink()
        backup = Path(str(target) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_strategy_exhaustion_cannot_run_without_dispatcher_lineage() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "code_chain_probe.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None
    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        executor = FinalVerifyFailExecutor()
        runner = TaskRunner(step_executor=executor, task_runtime=runtime)
        task_factory = lambda: _syntax_repair_task(max_strategy_attempts=3)
        results = _run_until_terminal(runner, task_factory, max_ticks=16)
        state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert results[-1]["status"] == "retrying"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert state["status"] in {"retrying", "blocked"}
        assert state["repair_context"]["strategy"]["exhausted"] is False
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert executor.calls == []
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()
        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_strategy_retry_without_dispatcher_lineage_is_rejected_before_repo_impact() -> None:
    step = {
        "type": "apply_patch",
        "target_path": "core/runtime/task_runtime.py",
        "edit_payload": {
            "old_text": "# old\n",
            "new_text": "# new\n",
            "schema": "replacement_pair_v1",
            "strategy": "function_rewrite",
        },
    }
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _apply_task("strategy_core_blocked", step)
    result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"
    assert state["status"] in {"retrying", "blocked"}
    assert "runtime dispatcher live capability required" in state["last_error"]
    assert not state["repair_context"].get("repo_impact")


def test_regression_py_compile_cannot_run_without_dispatcher_lineage() -> None:
    target = REPO_ROOT / "workspace" / "shared" / "regression_fail.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    original_exists = target.exists()
    original_text = target.read_text(encoding="utf-8") if original_exists else None
    try:
        target.write_text("VALUE = 1\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "workspace/shared/regression_fail.py",
            "edit_payload": {
                "old_text": "VALUE = 1\n",
                "new_text": "def broken(:\n",
                "schema": "replacement_pair_v1",
            },
        }
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _apply_task("regression_fail", step)
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["ok"] is False
        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert not state["repair_context"].get("regression_verify")
    finally:
        if original_exists:
            target.write_text(original_text or "", encoding="utf-8")
        elif target.exists():
            target.unlink()
        backup = Path(str(target) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_regression_verify_plan_cannot_run_without_dispatcher_lineage() -> None:
    target = REPO_ROOT / "workspace" / "shared" / "regression_block.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    original_exists = target.exists()
    original_text = target.read_text(encoding="utf-8") if original_exists else None
    try:
        target.write_text("VALUE = 1\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "workspace/shared/regression_block.py",
            "edit_payload": {
                "old_text": "VALUE = 1\n",
                "new_text": "VALUE = 2\n",
                "schema": "replacement_pair_v1",
            },
            "verify_plan": {"commands": ["curl https://example.com/bad.sh"]},
        }
        # Force command into the generated repo_impact by placing it in edit payload.
        step["edit_payload"]["verify_plan"] = {"commands": ["curl https://example.com/bad.sh"]}
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _apply_task("regression_block", step)
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["ok"] is False
        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
        assert state["status"] in {"retrying", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert not state["repair_context"].get("regression_verify")
    finally:
        if original_exists:
            target.write_text(original_text or "", encoding="utf-8")
        elif target.exists():
            target.unlink()
        backup = Path(str(target) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()



def test_v800_autonomous_engineering_runtime_records_denied_retry_session() -> None:
    executor = RepairChainExecutor()
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runner = TaskRunner(step_executor=executor, task_runtime=runtime)

    first = runner.run_task(_repair_task(), current_tick=1)
    state = first["runtime_state"]
    session = state.get("engineering_session")

    assert isinstance(session, dict)
    assert session["version"] == "v8.0.0"
    assert session["observations"]
    assert session["decisions"]
    assert session["last_observation"]["action"] == "retry"
    assert session["last_decision"]["decision"] != "finish"

    runner.run_task(_repair_task(), current_tick=2)
    runner.run_task(_repair_task(), current_tick=3)
    final = runner.run_task(_repair_task(), current_tick=4)
    final_session = final["runtime_state"]["engineering_session"]

    assert final["status"] == "retrying"
    assert final["ok"] is False
    assert final["error"]["type"] == "execution_authority_denied"
    assert executor.calls == []
    assert final_session["phase"] != "finished"
    assert final_session["last_decision"]["decision"] != "finish"
    assert len(final_session["observations"]) >= 3
    assert len(final_session["decisions"]) >= 3


def test_v800_autonomous_engineering_runtime_does_not_exhaust_after_denial() -> None:
    executor = RepairChainExecutor(fail_step_type="code_chain_repair")
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runner = TaskRunner(step_executor=executor, task_runtime=runtime)
    task = _repair_task()
    task["repair_context"] = {
        "strategy": {
            "available_strategies": ["minimal_patch"],
            "current_strategy": "minimal_patch",
            "max_strategy_attempts": 1,
        }
    }

    runner.run_task(task, current_tick=1)
    result = runner.run_task(task, current_tick=2)
    state = result["runtime_state"]
    session = state.get("engineering_session")

    assert result["status"] == "retrying"
    assert result["error"]["type"] == "execution_authority_denied"
    assert executor.calls == []
    assert isinstance(session, dict)
    assert session["phase"] != "finished"
    assert session["last_decision"]["decision"] != "finish"
    assert state["repair_context"]["strategy"]["exhausted"] is False


def test_repair_session_graph_without_dispatcher_lineage_is_not_finished() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "session_success.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None
    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime)
        task_factory = lambda: _strategy_task("session_success", "workspace/shared/session_success.py")
        results = _run_until_terminal(runner, task_factory)
        state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert results[-1]["status"] == "retrying"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert probe.read_text(encoding="utf-8") == "def add(a,b)\n    return a+b\n"
        session = state["repair_context"]["repair_session"]
        node_types = [node["type"] for node in session["nodes"]]
        assert node_types
        assert session["status"] != "finished"
        assert session["summary"].get("final_status") != "finished"
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()
        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_repair_session_graph_cannot_switch_strategy_without_dispatcher_lineage() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "session_strategy.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None
    try:
        probe.write_text("VALUE = 1\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=RegressionFailThenRealRepairExecutor(), task_runtime=runtime)
        task_factory = lambda: _strategy_task("session_strategy", "workspace/shared/session_strategy.py")
        results = _run_until_terminal(runner, task_factory)
        state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert results[-1]["status"] == "retrying"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert probe.read_text(encoding="utf-8") == "VALUE = 1\n"
        session = state["repair_context"]["repair_session"]
        node_types = [node["type"] for node in session["nodes"]]
        assert "rollback" not in node_types
        assert "strategy_switch" not in node_types
        assert session["edges"]
        assert all(edge["from"] and edge["to"] for edge in session["edges"])
        assert len(session["summary"].get("strategies_used", [])) <= 1
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()
        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_repair_session_graph_cannot_plan_impacted_apply_without_dispatcher_lineage() -> None:
    shared = REPO_ROOT / "workspace" / "shared"
    a_path = shared / "session_plan_a.py"
    b_path = shared / "session_plan_b.py"
    shared.mkdir(parents=True, exist_ok=True)
    originals = {
        a_path: a_path.read_text(encoding="utf-8") if a_path.exists() else None,
        b_path: b_path.read_text(encoding="utf-8") if b_path.exists() else None,
    }
    try:
        a_path.write_text("VALUE = 1\n", encoding="utf-8")
        b_path.write_text("import session_plan_a\ndef broken(:\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "workspace/shared/session_plan_a.py",
            "edit_payload": {
                "old_text": "VALUE = 1\n",
                "new_text": "VALUE = 2\n",
                "schema": "replacement_pair_v1",
            },
        }
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _apply_task("session_plan_fail", step)
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert a_path.read_text(encoding="utf-8") == "VALUE = 1\n"
        session = state["repair_context"]["repair_session"]
        assert "multi_file_plan" not in [node["type"] for node in session["nodes"]]
        assert session["status"] != "finished"
        assert "workspace/shared/session_plan_b.py" not in session["summary"].get("impacted_files", [])
    finally:
        for path, text in originals.items():
            if text is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(text, encoding="utf-8")
        backup = Path(str(a_path) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_repair_session_graph_persists_across_reload_without_duplicate_nodes() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "session_reload.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None
    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task_factory = lambda: _strategy_task("session_reload", "workspace/shared/session_reload.py")
        first_runner = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime)
        first_runner.run_task(task_factory(), current_tick=1)
        first_runner.run_task(task_factory(), current_tick=2)
        mid_state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))
        mid_node_ids = [node["node_id"] for node in mid_state["repair_context"]["repair_session"]["nodes"]]

        reloaded_runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        second_runner = TaskRunner(step_executor=StepExecutor(), task_runtime=reloaded_runtime)
        results = _run_until_terminal(second_runner, task_factory, max_ticks=8)
        final_state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))
        final_node_ids = [node["node_id"] for node in final_state["repair_context"]["repair_session"]["nodes"]]

        assert results[-1]["status"] == "retrying"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert probe.read_text(encoding="utf-8") == "def add(a,b)\n    return a+b\n"
        assert all(node_id in final_node_ids for node_id in mid_node_ids)
        assert len(final_node_ids) == len(set(final_node_ids))
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()
        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_repair_session_graph_compacts_node_payloads() -> None:
    context = {}
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runtime._append_repair_session_node(
        context=context,
        node_type="repair",
        status="success",
        tick=1,
        step_index=0,
        step_id="huge",
        input_summary="x" * 1000,
        output_summary={"full_result": "y" * 2000, "runtime_state": {"too": "large"}},
        error="",
        related_files=["workspace/shared/huge.py"],
        strategy="minimal_patch",
    )
    node = context["repair_session"]["nodes"][0]

    assert len(node["input_summary"]) <= 520
    assert len(node["output_summary"]) <= 540
    assert "y" * 1000 not in node["output_summary"]
    assert "result" not in node


def test_engineering_goal_state_legacy_single_repair_requires_dispatcher_lineage() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "goal_legacy.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None
    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime)
        task_factory = lambda: _strategy_task("goal_legacy", "workspace/shared/goal_legacy.py")
        results = _run_until_terminal(runner, task_factory)
        state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert results[-1]["status"] == "retrying"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert probe.read_text(encoding="utf-8") == "def add(a,b)\n    return a+b\n"
        goal_state = state["repair_context"]["engineering_goal_state"]
        assert goal_state["subgoals"][0]["subgoal_id"] == "default"
        assert goal_state["status"] != "finished"
        assert goal_state["summary"].get("goal_status") != "finished"
        assert state["repair_context"]["repair_session"]["summary"].get("goal_status") != "finished"
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()
        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_engineering_goal_state_two_subgoals_remain_incomplete_after_denial() -> None:
    task_dir = TEST_ROOT / "tasks" / "goal_two"
    task = {
        "task_id": "goal_two",
        "task_name": "goal_two",
        "goal": "two sequential subgoals",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [
            {"id": "one", "type": "noop"},
            {"id": "two", "type": "noop"},
        ],
        "subgoals": [
            {"subgoal_id": "sg1", "title": "one", "steps": [0]},
            {"subgoal_id": "sg2", "title": "two", "steps": [1], "depends_on": ["sg1"]},
        ],
        "current_step_index": 0,
    }
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    first_executor = RepairChainExecutor()
    first_runner = TaskRunner(step_executor=first_executor, task_runtime=runtime)
    first_runner.run_task(copy.deepcopy(task), current_tick=1)
    mid_state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))
    assert mid_state["repair_context"]["engineering_goal_state"]["completed_subgoals"] == []
    assert first_executor.calls == []

    second_executor = RepairChainExecutor()
    second_runner = TaskRunner(step_executor=second_executor, task_runtime=TaskRuntime(workspace_root=str(TEST_ROOT)))
    result = second_runner.run_task(copy.deepcopy(task), current_tick=2)
    final_state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["status"] == "retrying"
    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"
    assert result.get("finished", False) is False
    assert result.get("completed", False) is False
    assert second_executor.calls == []
    assert all(record["step"]["id"] == "one" for record in final_state["execution_log"])
    assert all(record["result"]["executed"] is False for record in final_state["execution_log"])
    goal_state = final_state["repair_context"]["engineering_goal_state"]
    assert goal_state["completed_subgoals"] == []
    assert goal_state["status"] != "finished"
    assert final_state["status"] != "finished"
    assert final_state.get("completion_authority") is None
    assert final_state.get("terminal_execution_evidence") is None
    assert final_state.get("goal_completion_attestation") is None


def test_engineering_goal_state_dependency_blocked_without_completed_dependency() -> None:
    task_dir = TEST_ROOT / "tasks" / "goal_blocked"
    task = {
        "task_id": "goal_blocked",
        "task_name": "goal_blocked",
        "goal": "blocked dependency",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [
            {"id": "one", "type": "noop"},
            {"id": "two", "type": "noop"},
        ],
        "subgoals": [
            {"subgoal_id": "sg1", "title": "one", "steps": [0]},
            {"subgoal_id": "sg2", "title": "two", "steps": [1], "depends_on": ["sg1"]},
        ],
        "current_step_index": 1,
    }
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    result = TaskRunner(step_executor=RepairChainExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["status"] == "blocked"
    goal_state = state["repair_context"]["engineering_goal_state"]
    assert "sg2" in goal_state["blocked_subgoals"]
    assert "dependency unmet" in goal_state["subgoals"][1]["blocked_reason"]


def test_engineering_goal_state_subgoal_failure_creates_replan_request() -> None:
    task_dir = TEST_ROOT / "tasks" / "goal_fail"
    task = {
        "task_id": "goal_fail",
        "task_name": "goal_fail",
        "goal": "subgoal failure",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [{"id": "bad", "type": "code_chain_repair", "target_path": "workspace/shared/missing_goal_fail.py"}],
        "subgoals": [{"subgoal_id": "sg_fail", "title": "fail", "steps": [0]}],
        "current_step_index": 0,
    }
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["status"] in {"failed", "retrying"}
    goal_state = state["repair_context"]["engineering_goal_state"]
    if result["status"] == "retrying":
        # The first failure is retry-classified, but the failed subgoal state is already durable.
        assert "sg_fail" in goal_state["failed_subgoals"]
    else:
        assert goal_state["status"] in {"failed", "blocked"}
    assert goal_state["replan_request"]["failed_subgoal_id"] == "sg_fail"
    assert goal_state["replan_request"]["reason"]


def test_failed_subgoal_creates_replan_proposal_without_modifying_steps() -> None:
    task_dir = TEST_ROOT / "tasks" / "goal_fail_proposal"
    task = {
        "task_id": "goal_fail_proposal",
        "task_name": "goal_fail_proposal",
        "goal": "subgoal failure proposal",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [{"id": "bad", "type": "code_chain_repair", "target_path": "workspace/shared/missing_goal_fail.py"}],
        "subgoals": [{"subgoal_id": "sg_fail", "title": "fail", "steps": [0]}],
        "current_step_index": 0,
    }
    original_steps = copy.deepcopy(task["steps"])
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    goal_state = state["repair_context"]["engineering_goal_state"]
    proposal = goal_state["replan_proposal"]
    assert proposal["status"] == "proposed"
    assert proposal["proposed_action"]
    assert state["steps"] == original_steps
    assert state["current_step_index"] == 0
    session = state["repair_context"]["repair_session"]
    assert "replan_proposal" in [node["type"] for node in session["nodes"]]
    assert any(edge["to"] for edge in session["edges"])


def test_repo_source_apply_without_dispatcher_lineage_stops_before_confirmation_proposal() -> None:
    step = {
        "type": "apply_patch",
        "target_path": "core/runtime/task_runtime.py",
        "edit_payload": {
            "old_text": "# old\n",
            "new_text": "# new\n",
            "schema": "replacement_pair_v1",
            "strategy": "function_rewrite",
        },
    }
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _apply_task("proposal_repo_source_blocked", step)
    result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    proposal = state["repair_context"]["engineering_goal_state"]["replan_proposal"]
    assert result["ok"] is False
    assert result["status"] == "retrying"
    assert result["error"]["type"] == "execution_authority_denied"
    assert "runtime dispatcher live capability required" in state["last_error"]
    assert not state["repair_context"].get("repo_impact")
    assert proposal["requires_confirmation"] is False
    assert proposal["proposed_action"] != "require_confirmation"
    assert "auto apply" not in json.dumps(proposal["proposed_steps"]).lower()


def test_multi_file_plan_without_dispatcher_lineage_replans_without_apply() -> None:
    shared = REPO_ROOT / "workspace" / "shared"
    a_path = shared / "proposal_plan_a.py"
    b_path = shared / "proposal_plan_b.py"
    shared.mkdir(parents=True, exist_ok=True)
    originals = {
        a_path: a_path.read_text(encoding="utf-8") if a_path.exists() else None,
        b_path: b_path.read_text(encoding="utf-8") if b_path.exists() else None,
    }
    try:
        a_path.write_text("VALUE = 1\n", encoding="utf-8")
        b_path.write_text("import proposal_plan_a\ndef broken(:\n", encoding="utf-8")
        step = {
            "type": "apply_patch",
            "target_path": "workspace/shared/proposal_plan_a.py",
            "edit_payload": {
                "old_text": "VALUE = 1\n",
                "new_text": "VALUE = 2\n",
                "schema": "replacement_pair_v1",
            },
        }
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task = _apply_task("proposal_multi_file_plan", step)
        result = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime).run_task(task, current_tick=1)
        state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

        proposal = state["repair_context"]["engineering_goal_state"]["replan_proposal"]
        assert result["ok"] is False
        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert a_path.read_text(encoding="utf-8") == "VALUE = 1\n"
        assert b_path.read_text(encoding="utf-8") == "import proposal_plan_a\ndef broken(:\n"
        assert proposal["proposed_action"] == "switch_strategy"
    finally:
        for path, text in originals.items():
            if text is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(text, encoding="utf-8")
        backup = Path(str(a_path) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_strategy_cannot_exhaust_without_dispatcher_lineage() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "proposal_strategy_abort.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None
    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=FinalVerifyFailExecutor(), task_runtime=runtime)
        task_factory = lambda: _strategy_task("proposal_strategy_abort", "workspace/shared/proposal_strategy_abort.py", max_strategy_attempts=1)
        results = _run_until_terminal(runner, task_factory, max_ticks=8)
        state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        proposal = state["repair_context"]["engineering_goal_state"]["replan_proposal"]
        assert results[-1]["status"] == "retrying"
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert probe.read_text(encoding="utf-8") == "def add(a,b)\n    return a+b\n"
        assert state["repair_context"]["strategy"]["exhausted"] is False
        assert proposal["proposed_action"] != "abort_goal"
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()
        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_replan_proposal_records_new_denied_retry_without_finishing() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "proposal_idempotent.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None
    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        task_factory = lambda: _strategy_task("proposal_idempotent", "workspace/shared/proposal_idempotent.py", max_strategy_attempts=1)
        runner = TaskRunner(step_executor=FinalVerifyFailExecutor(), task_runtime=runtime)
        _run_until_terminal(runner, task_factory, max_ticks=8)
        first_state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))
        first_proposal = first_state["repair_context"]["engineering_goal_state"]["replan_proposal"]
        first_nodes = [
            node["node_id"]
            for node in first_state["repair_context"]["repair_session"]["nodes"]
            if node["type"] == "replan_proposal"
        ]

        result = TaskRunner(
            step_executor=FinalVerifyFailExecutor(),
            task_runtime=TaskRuntime(workspace_root=str(TEST_ROOT)),
        ).run_task(task_factory(), current_tick=99)
        second_state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))
        second_nodes = [
            node["node_id"]
            for node in second_state["repair_context"]["repair_session"]["nodes"]
            if node["type"] == "replan_proposal"
        ]

        assert result["ok"] is False
        assert result["status"] == "retrying"
        assert result["error"]["type"] == "execution_authority_denied"
        assert probe.read_text(encoding="utf-8") == "def add(a,b)\n    return a+b\n"
        assert second_state["repair_context"]["engineering_goal_state"]["replan_proposal"]["proposal_id"] != first_proposal["proposal_id"]
        assert all(node_id in second_nodes for node_id in first_nodes)
        assert len(second_nodes) == len(set(second_nodes))
        assert second_state["status"] != "finished"
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()
        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_repair_session_step_nodes_include_subgoal_id() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "goal_graph.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None
    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime)
        task_factory = lambda: _strategy_task("goal_graph", "workspace/shared/goal_graph.py")
        _run_until_terminal(runner, task_factory)
        state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))
        step_nodes = [
            node for node in state["repair_context"]["repair_session"]["nodes"]
            if node["type"] in {"verify", "repair", "apply", "regression_verify", "final_verify"}
        ]

        assert step_nodes
        assert all(node["subgoal_id"] == "default" for node in step_nodes)
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()
        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


# ============================================================
# AER v9.1 - Engineering Execution Coordinator Runtime tests
# ============================================================

def _coordination_task(task_id: str = "coordination_runtime") -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "coordinate subgoal execution",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "subgoals": [
            {
                "subgoal_id": "blocked_first",
                "title": "Blocked first subgoal",
                "status": "pending",
                "depends_on": ["missing_dependency"],
                "steps": [0],
            },
            {
                "subgoal_id": "ready_second",
                "title": "Ready second subgoal",
                "status": "pending",
                "depends_on": [],
                "steps": [1],
            },
        ],
        "steps": [
            {"id": "blocked_step", "type": "noop"},
            {"id": "ready_step", "type": "noop"},
        ],
        "current_step_index": 0,
    }


def test_engineering_execution_is_initialized_from_goal_state() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _coordination_task("coordination_init")
    state = runtime.ensure_runtime_state(task)
    execution = state["repair_context"]["engineering_execution"]

    assert execution["status"] in {"running", "blocked"}
    assert execution["active_subgoal_queue"] == ["ready_second"]
    assert execution["waiting_dependencies"] == {"blocked_first": ["missing_dependency"]}
    assert execution["subgoal_retry_budget"]["blocked_first"] == 1
    assert execution["subgoal_attempts"]["ready_second"] == 0


def test_engineering_execution_selects_ready_subgoal_when_current_is_dependency_blocked() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _coordination_task("coordination_select_ready")
    result = runtime.prepare_current_subgoal(task, current_tick=1)
    state = result["runtime_state"]
    goal_state = state["repair_context"]["engineering_goal_state"]
    execution = state["repair_context"]["engineering_execution"]

    assert result["ok"] is True
    assert state["current_step_index"] == 1
    assert goal_state["current_subgoal_id"] == "ready_second"
    assert "blocked_first" in goal_state["blocked_subgoals"]
    assert execution["current_subgoal_id"] == "ready_second"
    assert execution["last_selected_subgoal_id"] == "ready_second"
    assert execution["subgoal_attempts"]["ready_second"] >= 1


def test_engineering_execution_updates_after_subgoal_step_completion() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _coordination_task("coordination_after_step")
    runtime.prepare_current_subgoal(task, current_tick=1)
    state = runtime.load_runtime_state(task)
    state["current_step_index"] = 1
    runtime.save_runtime_state(task, state)

    result = runtime.advance_step(task, step_result={"ok": True, "message": "ready done"}, current_tick=2)
    state = result["runtime_state"]
    execution = state["repair_context"]["engineering_execution"]

    assert "ready_second" in execution["completed_subgoals"]
    assert "ready_second" in execution["execution_order"]
    assert execution["summary"]["completed_subgoals"] >= 1


def test_engineering_execution_persists_across_reload() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _coordination_task("coordination_reload")
    runtime.prepare_current_subgoal(task, current_tick=1)

    reloaded = TaskRuntime(workspace_root=str(TEST_ROOT)).load_runtime_state(task)
    execution = reloaded["repair_context"]["engineering_execution"]

    assert execution["current_subgoal_id"] == "ready_second"
    assert execution["last_selected_subgoal_id"] == "ready_second"
    assert execution["waiting_dependencies"] == {"blocked_first": ["missing_dependency"]}



def test_engineering_execution_action_landing_records_denial_without_completion() -> None:
    executor = RepairChainExecutor()
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runner = TaskRunner(step_executor=executor, task_runtime=runtime)

    for tick in range(1, 5):
        runner.run_task(_repair_task(), current_tick=tick)

    state = _read_runtime_json()
    execution = state["repair_context"]["engineering_execution"]

    assert execution["action_landing_version"] == "aer_v9_1_2"
    assert execution["current_action"] == {}
    assert execution["pending_actions"]
    assert execution["completed_actions"] == []
    assert execution["action_status"]["completed"] == 0
    assert executor.calls == []
    assert state["status"] in {"retrying", "blocked"}
# ---------------------------------------------------------------------------
# Repair Boundary Tests v1
# ---------------------------------------------------------------------------
# These tests are intentionally appended as a boundary-only layer.
# They do not add new runtime features; they verify that the current repair
# runtime does not enter recursive / infinite / unsafe states under failure.


def test_boundary_verify_forever_failure_without_dispatcher_lineage_stays_bounded() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "boundary_verify_forever.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None

    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")

        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        executor = FinalVerifyFailExecutor()
        runner = TaskRunner(step_executor=executor, task_runtime=runtime)
        task_factory = lambda: _strategy_task(
            "boundary_verify_forever",
            "workspace/shared/boundary_verify_forever.py",
            max_strategy_attempts=2,
        )

        results = _run_until_terminal(runner, task_factory, max_ticks=12)
        state = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert len(results) <= 12
        assert results[-1]["status"] in {"retrying", "replan", "replanning", "denied", "blocked"}
        assert results[-1]["error"]["type"] == "execution_authority_denied"
        assert state["status"] in {"retrying", "replan", "replanning", "denied", "blocked"}
        assert "runtime dispatcher live capability required" in state["last_error"]
        assert executor.calls == []
        assert state["repair_context"]["strategy"]["exhausted"] is False
        assert not [
            item
            for item in state["repair_context"]["strategy"]["strategy_history"]
            if item.get("outcome") == "failed"
        ]
        assert state["repair_context"]["engineering_goal_state"]["replan_proposal"]
        assert state["repair_context"]["repair_session"]["nodes"]
        assert probe.read_text(encoding="utf-8") == "def add(a,b)\n    return a+b\n"
        assert not state["repair_context"].get("repo_impact")
        assert not state["repair_context"].get("rollback_result")
        assert not state["repair_context"].get("regression_verify")
        assert results[-1].get("finished", False) is False
        assert results[-1].get("completed", False) is False
        assert state.get("completion_authority") is None
        assert state.get("terminal_execution_evidence") is None
        assert state.get("goal_completion_attestation") is None
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()

        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


def test_boundary_recursive_repair_goal_is_fingerprint_suppressed(monkeypatch) -> None:
    monkeypatch.setattr("core.tasks.scheduler.time.time", lambda: 1_700_000_000.0)
    workspace = TEST_ROOT / "boundary_recursive_scheduler"
    shared = workspace / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "recursive_repair.py").write_text("def broken(:\n", encoding="utf-8")

    scheduler = Scheduler(workspace_dir=str(workspace), debug=False)
    goal = (
        "repair recursive repair task that tries to repair its own repair "
        "for workspace/shared/recursive_repair.py"
    )

    first_gate = scheduler._pre_enqueue_repair_fingerprint_gate(goal=goal)
    second_gate = scheduler._pre_enqueue_repair_fingerprint_gate(goal=goal)
    third_gate = scheduler._pre_enqueue_repair_fingerprint_gate(goal=goal)

    assert first_gate["ok"] is True
    assert first_gate["suppress"] is False

    assert second_gate["ok"] is True
    assert second_gate["suppress"] is True
    assert second_gate["duplicate_suppressed"] is True

    assert third_gate["ok"] is True
    assert third_gate["suppress"] is True
    assert third_gate["duplicate_suppressed"] is True


def test_boundary_corrupted_rollback_is_not_reached_without_dispatcher_lineage() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "boundary_corrupt_rollback.py"
    backup_path = Path(str(probe) + ".bak_edit_payload")
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None

    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")
        if backup_path.exists():
            backup_path.unlink()

        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        executor = FinalVerifyFailExecutor(delete_backup_before_verify=True)
        runner = TaskRunner(step_executor=executor, task_runtime=runtime)
        task_factory = lambda: _strategy_task(
            "boundary_corrupt_rollback",
            "workspace/shared/boundary_corrupt_rollback.py",
            max_strategy_attempts=1,
        )

        for tick in range(1, 5):
            runner.run_task(task_factory(), current_tick=tick)

        state_after_failure = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))
        result_after_terminal = runner.run_task(task_factory(), current_tick=5)
        state_after_rerun = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert state_after_failure["status"] in {"retrying", "blocked"}
        assert not state_after_failure["repair_context"].get("rollback_result")
        assert "runtime dispatcher live capability required" in state_after_failure["last_error"]
        assert executor.calls == []

        assert result_after_terminal["status"] == "retrying"
        assert result_after_terminal["error"]["type"] == "execution_authority_denied"
        assert state_after_rerun["status"] in {"retrying", "blocked"}
        assert not state_after_rerun["repair_context"].get("rollback_result")
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()

        if backup_path.exists():
            backup_path.unlink()


def test_boundary_terminal_repair_task_does_not_duplicate_execution_log_after_rerun() -> None:
    probe = REPO_ROOT / "workspace" / "shared" / "boundary_terminal_rerun.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    original_exists = probe.exists()
    original_text = probe.read_text(encoding="utf-8") if original_exists else None

    try:
        probe.write_text("def add(a,b)\n    return a+b\n", encoding="utf-8")

        runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
        runner = TaskRunner(step_executor=StepExecutor(), task_runtime=runtime)
        task_factory = lambda: _strategy_task(
            "boundary_terminal_rerun",
            "workspace/shared/boundary_terminal_rerun.py",
        )

        results = _run_until_terminal(runner, task_factory, max_ticks=12)
        state_after_finished = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))
        log_len_after_finished = len(state_after_finished.get("execution_log", []))

        rerun_result = runner.run_task(task_factory(), current_tick=99)
        state_after_rerun = json.loads(Path(task_factory()["runtime_state_file"]).read_text(encoding="utf-8"))

        assert results[-1]["status"] == "finished"
        assert rerun_result["status"] == "finished"
        assert len(state_after_rerun.get("execution_log", [])) == log_len_after_finished
        assert state_after_rerun["status"] == "finished"
    finally:
        if original_exists:
            probe.write_text(original_text or "", encoding="utf-8")
        elif probe.exists():
            probe.unlink()

        backup = Path(str(probe) + ".bak_edit_payload")
        if backup.exists():
            backup.unlink()


# ---------------------------------------------------------------------------
# Repair Observability Layer v1
# ---------------------------------------------------------------------------
# These tests verify that autonomous repair decisions can be reconstructed from
# durable policy metadata, not only from raw step logs.


def test_repair_observability_policy_decision_contains_reconstruction_fields() -> None:
    from core.runtime.failure_policy import FailurePolicy

    decision = FailurePolicy.decide_repair(
        task={"auto_repair": True, "max_repair_depth": 2},
        state={"repair_context": {"injections": []}},
        step={"type": "run_python", "path": "workspace/shared/observability.py"},
        step_result={"ok": False, "error": "python failed"},
        source_path="workspace/shared/observability.py",
    ).to_dict()

    assert decision["allow"] is True
    assert decision["action"] == "allow"
    assert decision["risk_level"] == "low"
    assert decision["max_repair_depth"] == 2
    assert decision["current_repair_depth"] == 0


def test_repair_observability_policy_decision_records_review_required_reason() -> None:
    from core.runtime.failure_policy import FailurePolicy

    decision = FailurePolicy.decide_repair(
        task={"auto_repair": True, "max_repair_depth": 2},
        state={"repair_context": {}},
        step={"type": "run_python", "path": "core/runtime/task_runner.py"},
        step_result={"ok": False, "error": "python failed"},
        source_path="core/runtime/task_runner.py",
    ).to_dict()

    assert decision["allow"] is False
    assert decision["action"] == "review_required"
    assert decision["requires_review"] is True
    assert decision["risk_level"] == "high"
    assert "critical repo path" in decision["reason"]


def test_repair_observability_policy_decision_records_quarantine_reason() -> None:
    from core.runtime.failure_policy import FailurePolicy

    decision = FailurePolicy.decide_repair(
        task={"auto_repair": True},
        state={"repair_context": {"rollback_result": {"ok": False, "reason": "restore failed"}}},
        step={"type": "run_python", "path": "workspace/shared/quarantine.py"},
        step_result={"ok": False, "error": "python failed"},
        source_path="workspace/shared/quarantine.py",
    ).to_dict()

    assert decision["allow"] is False
    assert decision["action"] == "fail"
    assert decision["quarantine"] is True
    assert decision["risk_level"] == "high"
    assert "rollback failure quarantine" in decision["reason"]


def test_repair_observability_policy_decision_records_depth_block() -> None:
    from core.runtime.failure_policy import FailurePolicy

    decision = FailurePolicy.decide_repair(
        task={"auto_repair": True, "max_repair_depth": 1},
        state={"repair_context": {"injections": [{"injected_step_count": 2}]}},
        step={"type": "run_python", "path": "workspace/shared/depth.py"},
        step_result={"ok": False, "error": "python failed"},
        source_path="workspace/shared/depth.py",
    ).to_dict()

    assert decision["allow"] is False
    assert decision["action"] == "fail"
    assert decision["risk_level"] == "medium"
    assert decision["current_repair_depth"] == 1
    assert decision["max_repair_depth"] == 1
    assert "max repair depth" in decision["reason"]


def test_repair_observability_helper_builds_stable_chain_metadata() -> None:
    from core.runtime.repair_observability import build_repair_chain_id, build_repair_observability

    task = {"task_id": "obs_helper"}
    step = {"id": "compile", "type": "run_python"}
    decision = {
        "allow": False,
        "action": "review_required",
        "reason": "critical repo path requires review",
        "risk_level": "high",
        "requires_review": True,
        "quarantine": False,
        "current_repair_depth": 1,
        "max_repair_depth": 2,
    }
    chain_id = build_repair_chain_id(
        task=task,
        source_path="core/runtime/task_runner.py",
        step_index=3,
        current_tick=7,
    )
    event = build_repair_observability(
        task=task,
        step=step,
        source_path="core/runtime/task_runner.py",
        step_index=3,
        current_tick=7,
        policy_decision=decision,
        repair_chain_id=chain_id,
    )

    assert chain_id == "repair_obs_helper_core_runtime_task_runner.py_step_3_tick_7"
    assert event["repair_chain_id"] == chain_id
    assert event["repair_origin_step"]["step_id"] == "compile"
    assert event["repair_origin_step"]["step_type"] == "run_python"
    assert event["repair_risk_level"] == "high"
    assert event["repair_block_reason"] == "critical repo path requires review"
    assert event["repair_depth"] == 1
    assert event["max_repair_depth"] == 2
# ---------------------------------------------------------------------------
# Repair Rollback Extraction v1
# ---------------------------------------------------------------------------


def test_repair_rollback_helper_decides_failed_verify_restore_available() -> None:
    from core.runtime.repair_rollback import should_rollback_after_failed_verify

    assert should_rollback_after_failed_verify(
        step={"type": "code_chain_verify"},
        step_result={"ok": False, "error": "verification_failed"},
        state={"repair_context": {"rollback": {"restore_available": True}}},
    ) is True

    assert should_rollback_after_failed_verify(
        step={"type": "code_chain_verify"},
        step_result={"ok": True},
        state={"repair_context": {"rollback": {"restore_available": True}}},
    ) is False

    assert should_rollback_after_failed_verify(
        step={"type": "run_python"},
        step_result={"ok": False},
        state={"repair_context": {"rollback": {"restore_available": True}}},
    ) is False


def test_repair_rollback_helper_normalizes_invalid_runtime_result() -> None:
    from core.runtime.repair_rollback import restore_repair_backup

    class BadRuntime:
        def rollback_last_apply(self, **kwargs):
            return "not a dict"

    result = restore_repair_backup(
        runtime=BadRuntime(),
        task={"task_id": "bad_runtime"},
        current_tick=1,
        verify_error="verification_failed",
    )

    assert result["ok"] is False
    assert result["rollback_result"]["ok"] is False
    assert "invalid result" in result["rollback_result"]["reason"]
# ---------------------------------------------------------------------------
# Repair Context Budget Guard v1
# ---------------------------------------------------------------------------


def _budget_task(task_id: str = "budget_guard") -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "budget guard",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [{"id": "noop", "type": "noop"}],
        "current_step_index": 0,
    }


def test_budget_caps_execution_trace_growth() -> None:
    from core.runtime.task_runtime import MAX_STORED_TRACE_ITEMS

    task = _budget_task("budget_trace_cap")
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    state = runtime.ensure_runtime_state(task)

    state["execution_trace"] = [
        {"event": "trace_item", "index": index}
        for index in range(MAX_STORED_TRACE_ITEMS + 25)
    ]

    saved = runtime.save_runtime_state(task, state)
    stored = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    expected_len = min(MAX_STORED_TRACE_ITEMS, MAX_STORED_TRACE_ITEMS + 25)
    assert len(saved["execution_trace"]) <= MAX_STORED_TRACE_ITEMS
    assert len(stored["execution_trace"]) <= MAX_STORED_TRACE_ITEMS
    assert len(stored["execution_trace"]) == len(saved["execution_trace"])
    assert stored["execution_trace"][-1]["index"] == MAX_STORED_TRACE_ITEMS + 24


def test_budget_truncates_large_stdout() -> None:
    from core.runtime.task_runtime import MAX_STORED_TEXT_CHARS

    task = _budget_task("budget_large_stdout")
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    state = runtime.ensure_runtime_state(task)

    large_stdout = "x" * (MAX_STORED_TEXT_CHARS + 500)
    state["last_step_result"] = {
        "step_index": 0,
        "step": {"id": "huge", "type": "run_python"},
        "result": {
            "ok": False,
            "stdout": large_stdout,
            "stderr": large_stdout,
        },
    }
    state["last_output"] = large_stdout

    saved = runtime.save_runtime_state(task, state)
    stored = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))
    stored_text = json.dumps(stored)

    assert "<truncated:" in stored_text
    assert len(stored["last_output"]) < len(large_stdout)
    result_payload = stored["last_step_result"]["result"]["result"]
    assert len(result_payload["stdout"]) < len(large_stdout)
    assert len(saved["last_step_result"]["result"]["result"]["stdout"]) < len(large_stdout)


def test_budget_drops_recursive_runtime_state_keys() -> None:
    task = _budget_task("budget_recursive_keys")
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    state = runtime.ensure_runtime_state(task)

    state["runtime_state"] = {"should_not_persist": True}
    state["raw_result"] = {"should_not_persist": True}
    state["repair_context"] = {
        "ok": True,
        "runtime_state": {"nested_should_not_persist": True},
        "task": {"nested_should_not_persist": True},
        "nested": {
            "runner_result": {"nested_should_not_persist": True},
            "safe_value": "kept",
        },
    }

    saved = runtime.save_runtime_state(task, state)
    stored = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))
    stored_text = json.dumps(stored)

    assert "should_not_persist" not in stored_text
    assert "nested_should_not_persist" not in stored_text
    assert "runtime_state" not in stored
    assert "raw_result" not in stored.get("repair_context", {})
    assert stored["repair_context"]["ok"] is True
    assert stored["repair_context"]["nested"]["safe_value"] == "kept"
    assert saved["repair_context"]["nested"]["safe_value"] == "kept"


def test_budget_limits_repair_history_growth() -> None:
    from core.runtime.task_runtime import MAX_STORED_LIST_ITEMS

    task = _budget_task("budget_repair_history")
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    state = runtime.ensure_runtime_state(task)

    state["repair_context"] = {
        "strategy": {
            "strategy_history": [
                {"index": index, "strategy": "minimal_patch", "outcome": "failed"}
                for index in range(MAX_STORED_LIST_ITEMS + 30)
            ],
        },
        "injections": [
            {"index": index, "step_ids": [f"repair_{index}"]}
            for index in range(MAX_STORED_LIST_ITEMS + 30)
        ],
    }
    state["execution_log"] = [
        {"step_index": index, "step": {"type": "noop"}, "result": {"ok": True}}
        for index in range(MAX_STORED_LIST_ITEMS + 30)
    ]

    saved = runtime.save_runtime_state(task, state)
    stored = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert len(stored["execution_log"]) <= MAX_STORED_LIST_ITEMS
    assert stored["execution_log"][-1]["step_index"] == MAX_STORED_LIST_ITEMS + 29
    assert len(stored["repair_context"]["strategy"]["strategy_history"]) <= MAX_STORED_LIST_ITEMS
    assert stored["repair_context"]["strategy"]["strategy_history"][-1]["index"] == MAX_STORED_LIST_ITEMS + 29
    assert len(stored["repair_context"]["injections"]) <= MAX_STORED_LIST_ITEMS
    assert stored["repair_context"]["injections"][-1]["index"] == MAX_STORED_LIST_ITEMS + 29
    assert saved["repair_context"]["injections"][-1]["index"] == MAX_STORED_LIST_ITEMS + 29

def test_replay_runtime_blocks_apply_patch_execution() -> None:
    workspace = TEST_ROOT / "replay_guard_workspace"
    shared = workspace / "shared"
    task_dir = workspace / "tasks" / "replay_block"
    shared.mkdir(parents=True, exist_ok=True)
    task_dir.mkdir(parents=True, exist_ok=True)

    target = shared / "test.py"
    target.write_text("A\n", encoding="utf-8")

    guard = ExecutionGuard(
        workspace_root=str(workspace),
        shared_dir=str(shared),
        allow_commands=False,
    )

    result = guard.check_step(
        {
            "type": "apply_patch",
            "runtime_mode": "replay",
            "target_path": "workspace/shared/test.py",
            "edit_payload": {
                "old_text": "A\n",
                "new_text": "B\n",
                "schema": "replacement_pair_v1",
            },
        },
        task_dir=str(task_dir),
    )

    assert result["ok"] is False
    assert result["guard_mode"] == "readonly_runtime_blocked"
    assert "readonly" in result["policy_reason"]
    assert target.read_text(encoding="utf-8") == "A\n"

