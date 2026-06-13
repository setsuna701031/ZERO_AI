from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.runtime.work_package_queue import RuntimePackageQueue
from services.system_boot import ZeroSystem


ROOT = Path(__file__).resolve().parents[1]


class _FakeLLMClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_general(self, prompt: str) -> dict[str, str]:
        self.prompts.append(prompt)
        return {"response": "fake llm response"}


def _payload(package_id: str = "summary-package") -> dict:
    return {
        "package_id": package_id,
        "title": "Summary contract",
        "goal": "Keep CLI output short",
        "description": "Verify the runtime summary projection.",
        "target_files": ["core/runtime/work_package_operator.py"],
        "requirements": ["summary output"],
        "hard_boundary": ["no full progress"],
        "non_mainline_issue_reporting": ["report pollution"],
        "validation_commands": ["pytest"],
        "completion_report_format": ["short json"],
    }


def test_llm_client_propagates_operator_dispatcher_taskrunner_step_executor(tmp_path: Path) -> None:
    client = _FakeLLMClient()
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path, llm_client=client)

    assert operator.llm_client is client
    assert operator.dispatcher.llm_client is client
    assert operator.dispatcher.task_runner.llm_client is client
    assert operator.dispatcher.task_runner.step_executor.llm_client is client


def test_system_boot_passes_same_client_and_operator_to_agent_loop(tmp_path: Path) -> None:
    system = ZeroSystem(workspace=str(tmp_path / "workspace"))
    client = system.llm_client

    class _AgentLoopProbe:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    agent_loop = system._build_agent_loop(_AgentLoopProbe)

    assert agent_loop.kwargs["llm_client"] is client
    assert agent_loop.kwargs["work_package_operator"] is system.work_package_operator
    assert system.work_package_operator.llm_client is client
    assert system.work_package_operator.dispatcher.task_runner.step_executor.llm_client is client


def test_agent_loop_work_package_route_uses_runtime_operator_without_legacy_scheduler() -> None:
    class _Planner:
        def normalize_aer_execution_intent(self, payload, **_kwargs):
            return {"work_package": dict(payload)}

    class _Operator:
        repo_root = Path(".")

        def __init__(self) -> None:
            self.submitted = None
            self.ran = None

        def submit_package(self, payload):
            self.submitted = dict(payload)
            return {"package_id": payload["package_id"], "planning_status": "planned"}

        def run_package(self, package_id):
            self.ran = package_id
            return {
                "package_id": package_id,
                "status": "completed",
                "runtime_lifecycle_state": "completed",
            }

    operator = _Operator()
    result = AgentLoop(planner=_Planner(), work_package_operator=operator)._try_handle_work_package_route(
        json.dumps({"task_type": "work_package", **_payload("agent-runtime-package")})
    )

    assert operator.submitted["package_id"] == "agent-runtime-package"
    assert operator.ran == "agent-runtime-package"
    assert result["ok"] is True
    assert "RuntimeWorkPackageOperator -> RuntimeDispatcher -> TaskRunner -> StepExecutor" in result["route"]["authority_path"]
    assert "WorkPackageScheduler" not in (ROOT / "core/agent/agent_loop.py").read_text(encoding="utf-8")


def test_dispatcher_and_taskrunner_propagate_to_injected_downstream_objects(tmp_path: Path) -> None:
    client = _FakeLLMClient()
    executor = StepExecutor(workspace_root=str(tmp_path))
    runner = TaskRunner(step_executor=executor)
    dispatcher = RuntimeDispatcher(
        queue=RuntimePackageQueue(repo_root=tmp_path),
        task_runner=runner,
        workspace_root=tmp_path / "workspace",
        llm_client=client,
    )

    assert dispatcher.task_runner is runner
    assert runner.llm_client is client
    assert executor.llm_client is client


def test_step_executor_llm_step_uses_injected_fake_client(tmp_path: Path) -> None:
    client = _FakeLLMClient()
    executor = StepExecutor(llm_client=client, workspace_root=str(tmp_path))

    result = executor.execute_step({"id": "llm-1", "type": "llm", "prompt": "hello"})

    assert result["ok"] is True
    assert result["text"] == "fake llm response"
    assert client.prompts == ["hello"]


def test_production_has_one_canonical_llm_provider_and_runtime_does_not_construct_it() -> None:
    provider_definitions: list[str] = []
    for base in (ROOT / "services", ROOT / "core", ROOT / "cli"):
        for path in base.rglob("*.py"):
            if "_archive_candidate" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name in {"LocalLLMClient", "OllamaClient"}:
                    provider_definitions.append(path.relative_to(ROOT).as_posix())

    assert provider_definitions == ["core/system/llm_client.py"]
    for relative in (
        "core/agent/agent_loop.py",
        "core/runtime/work_package_operator.py",
        "core/runtime/runtime_dispatcher.py",
        "core/runtime/task_runner.py",
        "core/runtime/step_executor.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "LocalLLMClient(" not in source
        assert "OllamaClient(" not in source


def test_summary_cli_is_parseable_short_projection_without_large_payloads(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    submitted = operator.submit_package(_payload())
    record = operator.queue.status("summary-package")
    record["memory_context_used"] = [{"file_content": "x" * 50_000}]
    record.setdefault("progress", {})["full_progress_payload"] = {"content": "y" * 50_000}
    operator.queue._write(record)

    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.work_package_cli",
            "--repo-root",
            str(tmp_path),
            "summary",
            "summary-package",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(process.stdout)
    assert process.returncode == 0
    assert payload == {
        "ok": True,
        "package_id": "summary-package",
        "lifecycle_state": "queued",
        "planning_status": "planned",
        "completed_steps": 0,
        "failed_steps": 0,
        "remaining_steps": len(submitted["runtime_queue_item"]["steps"]),
        "percent": 0,
        "root_cause": None,
        "last_transition_reason": "package_submitted",
        "memory_status": "pending",
        "step_types": submitted["task_graph_summary"]["step_types"],
    }
    assert "memory_context_used" not in process.stdout
    assert "file_content" not in process.stdout
    assert "full_progress_payload" not in process.stdout
    assert len(process.stdout) < 1000


def test_report_cli_exposes_full_engineering_report_explicitly(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    operator.submit_package(_payload())

    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.work_package_cli",
            "--repo-root",
            str(tmp_path),
            "report",
            "summary-package",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(process.stdout)
    assert process.returncode == 0
    assert payload["ok"] is True
    assert payload["result"]["engineering_report"]["report_type"] == "work_package"
    assert payload["result"]["engineering_report_markdown"].startswith("# ZERO Engineering Report")
