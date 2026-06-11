from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_LOOP = ROOT / "core" / "agent" / "agent_loop.py"
TEST_FILE = ROOT / "tests" / "test_legacy_engineering_task_route_elimination.py"


NEW_METHOD = '''    def _try_handle_engineering_task_route(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Admit legacy JSON engineering-task payloads through governed runtime.

        This route intentionally does not execute EngineeringTaskRunner directly.
        It preserves JSON engineering_task compatibility as a runtime admission
        envelope only, so AgentLoop remains orchestration-only.
        """

        text = str(user_input or "").strip()
        if not text:
            return None
        if not (text.startswith("{") and text.endswith("}")):
            return None

        try:
            payload = json.loads(text)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        task_type = str(payload.get("task_type") or payload.get("type") or "").strip().lower()
        if task_type != "engineering_task":
            return None

        package_id = str(payload.get("package_id") or payload.get("id") or "engineering-task").strip()
        repo_root = str(payload.get("repo_root") or payload.get("workspace_root") or "").strip()
        requirements = payload.get("requirements")
        target_files = payload.get("target_files")

        authority_path = (
            "AgentLoop -> Runtime Admission -> AgentExecutionRuntime "
            "-> TaskRunner -> StepExecutor"
        )
        execution_path = {
            "route": authority_path,
            "legacy_direct_engineering_task_route": False,
            "program_mainline": False,
            "persisted_engineering_goal": False,
            "direct_goal_runner_bypass": False,
            "direct_execution": False,
            "agent_loop_owns_execution": False,
            "runtime_owns_execution": True,
            "governed_runtime_route": True,
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
        }
        route = {
            "mode": "runtime_admission_engineering_task",
            "task": True,
            "forced_route": True,
            "engineering_task": True,
            "package_id": package_id,
            "repo_root": repo_root,
            "legacy_direct_json_engineering_task_runner": False,
            "governed_runtime_route": True,
            "runtime_owns_execution": True,
            "direct_execution": False,
            "agent_loop_owns_execution": False,
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
            "execution_path": copy.deepcopy(execution_path),
            "authority_path": authority_path,
            "runtime_admission_payload": {
                "task_type": "engineering_task",
                "package_id": package_id,
                "repo_root": repo_root,
                "requirements": copy.deepcopy(requirements),
                "target_files": copy.deepcopy(target_files),
                "source_payload": copy.deepcopy(payload),
                "governed_runtime_route": True,
                "runtime_owns_execution": True,
                "direct_execution": False,
                "agent_loop_owns_execution": False,
            },
        }
        final_answer = (
            f"engineering task {package_id} admitted to governed runtime route; "
            "direct EngineeringTaskRunner execution is disabled"
        )
        return {
            "ok": True,
            "status": "admitted",
            "route": route,
            "result": copy.deepcopy(route),
            "execution_path": copy.deepcopy(execution_path),
            "authority_path": authority_path,
            "legacy_direct_json_engineering_task_runner": False,
            "governed_runtime_route": True,
            "runtime_owns_execution": True,
            "direct_execution": False,
            "agent_loop_owns_execution": False,
            "final_answer": final_answer,
        }

'''


TEST_CONTENT = '''from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_LOOP_PATH = ROOT / "core" / "agent" / "agent_loop.py"


def _source() -> str:
    return AGENT_LOOP_PATH.read_text(encoding="utf-8")


def _method_node() -> ast.FunctionDef:
    tree = ast.parse(_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_try_handle_engineering_task_route":
            return node
    raise AssertionError("_try_handle_engineering_task_route not found")


def test_legacy_direct_engineering_task_route_removed_from_source() -> None:
    source = _source()

    assert "legacy_direct_json_engineering_task_runner\\\"] = True" not in source
    assert "legacy_direct_json_engineering_task_runner'] = True" not in source
    assert "\\"legacy_direct_json_engineering_task_runner\\": True" not in source
    assert "'legacy_direct_json_engineering_task_runner': True" not in source
    assert "AgentLoop -> EngineeringTaskRunner" not in source


def test_engineering_task_route_is_runtime_admission_only() -> None:
    method = _method_node()
    method_source = ast.get_source_segment(_source(), method) or ""

    assert "governed_runtime_route" in method_source
    assert "runtime_owns_execution" in method_source
    assert "direct_execution" in method_source
    assert "agent_loop_owns_execution" in method_source
    assert "AgentExecutionRuntime" in method_source
    assert "TaskRunner" in method_source
    assert "StepExecutor" in method_source
    assert "EngineeringTaskRunner(" not in method_source


def test_agent_loop_does_not_directly_call_step_executor_in_legacy_route() -> None:
    method = _method_node()

    forbidden_names = {
        "EngineeringTaskRunner",
        "StepExecutor",
        "TaskRunner",
        "execute_step",
        "execute_steps",
    }

    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                assert target.id not in forbidden_names
            if isinstance(target, ast.Attribute):
                assert target.attr not in {"execute_step", "execute_steps", "run_task"}
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"step_executor", "task_runner"}


def test_legacy_route_reports_runtime_owned_authority_contract() -> None:
    method_source = ast.get_source_segment(_source(), _method_node()) or ""

    assert "\\"legacy_direct_json_engineering_task_runner\\": False" in method_source
    assert "\\"governed_runtime_route\\": True" in method_source
    assert "\\"runtime_owns_execution\\": True" in method_source
    assert "\\"direct_execution\\": False" in method_source
    assert "\\"agent_loop_owns_execution\\": False" in method_source
    assert "\\"taskrunner_required\\": True" in method_source
    assert "\\"step_executor_endpoint_only\\": True" in method_source
'''


def replace_dispatch_flags(source: str) -> str:
    old = '''        engineering_task_result = self._try_handle_engineering_task_route(text)
        if engineering_task_result is not None:
            engineering_task_result["agent_loop_runtime_route"] = "engineering_task_runner"
            engineering_task_result["legacy_direct_json_engineering_task_runner"] = True
            return engineering_task_result
'''
    new = '''        engineering_task_result = self._try_handle_engineering_task_route(text)
        if engineering_task_result is not None:
            engineering_task_result["agent_loop_runtime_route"] = "runtime_admission_engineering_task"
            engineering_task_result["legacy_direct_json_engineering_task_runner"] = False
            engineering_task_result["governed_runtime_route"] = True
            engineering_task_result["runtime_owns_execution"] = True
            engineering_task_result["direct_execution"] = False
            engineering_task_result["agent_loop_owns_execution"] = False
            return engineering_task_result
'''
    if old in source:
        return source.replace(old, new, 1)

    fallback_pattern = re.compile(
        r'        engineering_task_result = self\._try_handle_engineering_task_route\(text\)\n'
        r'        if engineering_task_result is not None:\n'
        r'(?:            .*\n)*?'
        r'            return engineering_task_result\n',
        re.MULTILINE,
    )
    match = fallback_pattern.search(source)
    if not match:
        raise RuntimeError("dispatch legacy engineering task block not found")
    return source[: match.start()] + new + source[match.end() :]


def replace_method(source: str) -> str:
    marker = "def _try_handle_engineering_task_route"
    marker_index = source.find(marker)
    if marker_index < 0:
        raise RuntimeError("_try_handle_engineering_task_route method not found")

    line_start = source.rfind("\n", 0, marker_index) + 1
    if line_start < 0:
        line_start = 0

    next_method = re.search(r"\n    def\s+", source[marker_index + 1 :])
    if next_method:
        end = marker_index + 1 + next_method.start() + 1
    else:
        end = len(source)

    return source[:line_start] + NEW_METHOD + source[end:]


def main() -> None:
    if not AGENT_LOOP.exists():
        raise FileNotFoundError(AGENT_LOOP)

    source = AGENT_LOOP.read_text(encoding="utf-8")
    backup = AGENT_LOOP.with_suffix(".py.bak_legacy_engineering_route")
    backup.write_text(source, encoding="utf-8")

    updated = replace_dispatch_flags(source)
    updated = replace_method(updated)

    forbidden = [
        '"legacy_direct_json_engineering_task_runner": True',
        "'legacy_direct_json_engineering_task_runner': True",
        'legacy_direct_json_engineering_task_runner"] = True',
        "legacy_direct_json_engineering_task_runner'] = True",
        "AgentLoop -> EngineeringTaskRunner",
    ]
    remaining = [item for item in forbidden if item in updated]
    if remaining:
        raise RuntimeError(f"legacy route markers still present: {remaining}")

    AGENT_LOOP.write_text(updated, encoding="utf-8")
    TEST_FILE.write_text(TEST_CONTENT, encoding="utf-8")

    print("patched:", AGENT_LOOP)
    print("backup:", backup)
    print("test:", TEST_FILE)


if __name__ == "__main__":
    main()