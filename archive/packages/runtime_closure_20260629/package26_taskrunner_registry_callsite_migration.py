from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TASK_RUNNER_PATH = ROOT / "core" / "runtime" / "task_runner.py"
TEST_PATH = ROOT / "tests" / "test_taskrunner_registry_callsite_migration.py"
REPORT_PATH = ROOT / "taskrunner_registry_callsite_migration_report.txt"

MARKER_BEGIN = "# ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_BEGIN"
MARKER_END = "# ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_END"

TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nTASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"\n\n\ndef test_taskrunner_registry_callsite_migration_import_safe() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n    ast.parse(source)\n\n    import core.runtime.task_runner as module\n\n    assert module is not None\n\n\ndef test_taskrunner_registry_callsite_migration_marker_once() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n\n    assert source.count("ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_BEGIN") == 1\n    assert source.count("ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_END") == 1\n\n\ndef test_taskrunner_registry_callsite_migration_helpers_exist() -> None:\n    import core.runtime.task_runner as module\n\n    assert hasattr(module, "_zero_taskrunner_registry_callsite_payload_v26")\n    assert hasattr(module, "_zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26")\n    assert hasattr(module, "_zero_taskrunner_registry_callsite_wrap_tick_v26")\n\n\ndef test_taskrunner_registry_callsite_migration_payload_extracts_step_id() -> None:\n    import core.runtime.task_runner as module\n\n    payload = module._zero_taskrunner_registry_callsite_payload_v26(\n        "execute_owned_step",\n        ({"step_id": "s26", "type": "noop"},),\n        {"current_tick": 9},\n    )\n\n    assert payload["event"] == "execute_owned_step"\n    assert payload["step_id"] == "s26"\n    assert payload["current_tick"] == 9\n\n\ndef test_taskrunner_registry_callsite_migration_class_binding_if_taskrunner_exists() -> None:\n    import core.runtime.task_runner as module\n\n    cls = getattr(module, "TaskRunner", None)\n    if isinstance(cls, type):\n        assert getattr(cls, "_zero_package26_registry_callsite_migration_installed", False) is True\n\n\ndef test_taskrunner_registry_callsite_migration_wrapper_calls_unified_helper() -> None:\n    import core.runtime.task_runner as module\n\n    calls = []\n\n    class Host:\n        def _aer_registry_admit(self, event, payload=None):\n            calls.append((event, payload))\n            return {"ok": True, "status": "admitted"}\n\n    def base(self, step, **kwargs):\n        return {"ok": True, "step": step, "kwargs": kwargs}\n\n    wrapped = module._zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26(base)\n    result = wrapped(Host(), {"step_id": "owned-26"}, current_tick=26)\n\n    assert result["ok"] is True\n    assert calls\n    assert calls[0][0] == "execute_owned_step"\n    assert calls[0][1]["step_id"] == "owned-26"\n\n\ndef test_taskrunner_registry_callsite_migration_tick_wrapper_calls_unified_helper() -> None:\n    import core.runtime.task_runner as module\n\n    calls = []\n\n    class Host:\n        def _aer_registry_admit(self, event, payload=None):\n            calls.append((event, payload))\n            return {"ok": True, "status": "admitted"}\n\n    def base(self, **kwargs):\n        return {"ok": True, "kwargs": kwargs}\n\n    wrapped = module._zero_taskrunner_registry_callsite_wrap_tick_v26(base)\n    result = wrapped(Host(), current_tick=27)\n\n    assert result["ok"] is True\n    assert calls\n    assert calls[0][0] == "tick"\n    assert calls[0][1]["current_tick"] == 27\n'
BLOCK_SOURCE = '# ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_BEGIN\ndef _zero_taskrunner_registry_callsite_payload_v26(event, args=None, kwargs=None):\n    args = tuple(args or ())\n    kwargs = dict(kwargs or {})\n    payload = {"event": str(event or "").strip() or "taskrunner_event"}\n\n    if args:\n        first = args[0]\n        if isinstance(first, dict):\n            payload.update(first)\n        else:\n            payload["target"] = first\n\n    for key in (\n        "step",\n        "step_id",\n        "task",\n        "task_id",\n        "current_tick",\n        "tick",\n        "runtime_session_id",\n        "session_id",\n        "operator_session_id",\n    ):\n        if key in kwargs and kwargs.get(key) is not None:\n            value = kwargs.get(key)\n            if key == "step" and isinstance(value, dict):\n                payload.update(value)\n            else:\n                payload[key] = value\n\n    if "step_id" not in payload:\n        step = payload.get("step")\n        if isinstance(step, dict) and step.get("step_id"):\n            payload["step_id"] = step.get("step_id")\n        elif isinstance(step, dict) and step.get("id"):\n            payload["step_id"] = step.get("id")\n\n    return payload\n\n\ndef _zero_taskrunner_registry_callsite_admit_v26(self, event, args=None, kwargs=None):\n    payload = _zero_taskrunner_registry_callsite_payload_v26(event, args, kwargs)\n    helper = getattr(self, "_aer_registry_admit", None)\n    if callable(helper):\n        return helper(event, payload)\n\n    fallback = globals().get("_zero_taskrunner_registry_admit_aer_closure_v24")\n    if callable(fallback):\n        return fallback(self, event, payload)\n\n    return {"ok": True, "status": "skipped", "reason": "aer_registry_admit_unavailable", "event": event, "payload": payload}\n\n\ndef _zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26(base):\n    def _zero_execute_owned_step_with_registry_admission(self, *args, **kwargs):\n        _zero_taskrunner_registry_callsite_admit_v26(self, "execute_owned_step", args, kwargs)\n        return base(self, *args, **kwargs)\n\n    _zero_execute_owned_step_with_registry_admission.__name__ = getattr(base, "__name__", "execute_owned_step")\n    _zero_execute_owned_step_with_registry_admission.__doc__ = getattr(base, "__doc__", None)\n    _zero_execute_owned_step_with_registry_admission._zero_package26_registry_wrapped = True\n    return _zero_execute_owned_step_with_registry_admission\n\n\ndef _zero_taskrunner_registry_callsite_wrap_tick_v26(base):\n    def _zero_tick_with_registry_admission(self, *args, **kwargs):\n        _zero_taskrunner_registry_callsite_admit_v26(self, "tick", args, kwargs)\n        return base(self, *args, **kwargs)\n\n    _zero_tick_with_registry_admission.__name__ = getattr(base, "__name__", "tick")\n    _zero_tick_with_registry_admission.__doc__ = getattr(base, "__doc__", None)\n    _zero_tick_with_registry_admission._zero_package26_registry_wrapped = True\n    return _zero_tick_with_registry_admission\n\n\ndef _zero_taskrunner_registry_callsite_install_v26():\n    cls = globals().get("TaskRunner")\n    if not isinstance(cls, type):\n        return False\n\n    for name, wrapper in (\n        ("execute_owned_step", _zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26),\n        ("tick", _zero_taskrunner_registry_callsite_wrap_tick_v26),\n    ):\n        base = getattr(cls, name, None)\n        if callable(base) and not getattr(base, "_zero_package26_registry_wrapped", False):\n            setattr(cls, name, wrapper(base))\n\n    setattr(cls, "_zero_package26_registry_callsite_migration_installed", True)\n    return True\n\n\ntry:\n    _zero_taskrunner_registry_callsite_install_v26()\nexcept Exception:\n    pass\n# ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_END\n'


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package26_backup_{stamp}"))


def _strip_marked_blocks(source: str) -> str:
    current = source
    while MARKER_BEGIN in current and MARKER_END in current:
        before = current.split(MARKER_BEGIN, 1)[0].rstrip()
        tail = current.split(MARKER_BEGIN, 1)[1]
        after = tail.split(MARKER_END, 1)[1].lstrip()
        current = before + "\n\n" + after
    return current


def _remove_top_level_duplicate_helpers(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    helper_names = {
        "_zero_taskrunner_registry_callsite_payload_v26",
        "_zero_taskrunner_registry_callsite_admit_v26",
        "_zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26",
        "_zero_taskrunner_registry_callsite_wrap_tick_v26",
        "_zero_taskrunner_registry_callsite_install_v26",
    }
    remove_lines: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in helper_names:
            start = node.lineno
            end = getattr(node, "end_lineno", node.lineno)
            remove_lines.update(range(start, end + 1))
    if not remove_lines:
        return source
    kept = [line for idx, line in enumerate(lines, start=1) if idx not in remove_lines]
    return "\n".join(kept).rstrip() + "\n"


def _install_block(source: str) -> str:
    cleaned = _strip_marked_blocks(source)
    cleaned = _remove_top_level_duplicate_helpers(cleaned)
    return cleaned.rstrip() + "\n\n" + BLOCK_SOURCE.rstrip() + "\n"


def main() -> int:
    if not TASK_RUNNER_PATH.exists():
        raise FileNotFoundError(f"Missing TaskRunner target: {TASK_RUNNER_PATH}")

    _backup(TASK_RUNNER_PATH)
    _backup(TEST_PATH)

    source = TASK_RUNNER_PATH.read_text(encoding="utf-8")
    if "_zero_taskrunner_registry_admit_aer_closure_v24" not in source:
        raise RuntimeError("Package24 helper is missing; run package24 first")

    updated = _install_block(source)
    ast.parse(updated)
    TASK_RUNNER_PATH.write_text(updated, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    report = "\n".join([
        "Package26 TaskRunner Registry Callsite Migration Report",
        "",
        f"root: {ROOT}",
        f"task_runner: {TASK_RUNNER_PATH.relative_to(ROOT)}",
        f"test: {TEST_PATH.relative_to(ROOT)}",
        "",
        "Completed:",
        "- installed execute_owned_step wrapper that admits through the Package24 unified helper before delegating",
        "- installed tick wrapper that admits through the Package24 unified helper before delegating",
        "- kept repair/rollback/evidence paths unchanged",
        "- added focused callsite migration tests",
        "",
        "Not touched:",
        "- Scheduler",
        "- AgentLoop",
        "- CLI",
        "- RuntimeRouteRegistry",
        "- Runtime Native marker chain",
        "",
        "Validation:",
        "python -m compileall core/runtime tests",
        "python -m pytest tests/test_taskrunner_registry_callsite_migration.py tests/test_taskrunner_registry_direct_admission_inventory.py tests/test_taskrunner_registry_admission_consolidation.py tests/test_taskrunner_aer_closure_inventory.py tests/test_aer_mainline_closure_seal.py -q",
        "",
        "Non-mainline issue reporting:",
        "Any unrelated issue discovered during validation must be reported explicitly and not silently skipped.",
        "",
    ])
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")
    print(str(REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
