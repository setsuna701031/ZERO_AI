from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TASK_RUNNER_PATH = ROOT / "core" / "runtime" / "task_runner.py"
TEST_PATH = ROOT / "tests" / "test_taskrunner_registry_admission_consolidation.py"
REPORT_PATH = ROOT / "taskrunner_registry_admission_consolidation_report.txt"

MARKER_BEGIN = "# ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_BEGIN"
MARKER_END = "# ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_END"

TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\n\nROOT = Path(__file__).resolve().parents[1]\nTASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"\n\n\ndef test_taskrunner_registry_admission_consolidation_import_safe() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n    ast.parse(source)\n\n    import core.runtime.task_runner as module\n\n    assert module is not None\n\n\ndef test_taskrunner_registry_admission_consolidation_single_helper_marker() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n\n    assert source.count("ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_BEGIN") == 1\n    assert source.count("ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_END") == 1\n    assert source.count("def _zero_taskrunner_registry_admit_aer_closure_v24") == 1\n\n\ndef test_taskrunner_registry_admission_consolidation_helper_calls_run_observer() -> None:\n    import core.runtime.task_runner as module\n\n    calls = []\n\n    class FakeRegistry:\n        def run_observer(self, **kwargs):\n            calls.append(kwargs)\n            return {"ok": True, "status": "admitted"}\n\n    host = SimpleNamespace(runtime_route_registry=FakeRegistry())\n\n    result = module._zero_taskrunner_registry_admit_aer_closure_v24(\n        host,\n        "execute_owned_step",\n        {"step_id": "s1"},\n    )\n\n    assert result["ok"] is True\n    assert calls\n    assert calls[0]["event"] == "execute_owned_step"\n    assert calls[0]["payload"]["step_id"] == "s1"\n\n\ndef test_taskrunner_registry_admission_consolidation_helper_supports_admit() -> None:\n    import core.runtime.task_runner as module\n\n    calls = []\n\n    class FakeRegistry:\n        def admit(self, event, payload):\n            calls.append((event, payload))\n            return {"ok": True, "admitted": True}\n\n    host = SimpleNamespace(registry=FakeRegistry())\n\n    result = module._zero_taskrunner_registry_admit_aer_closure_v24(\n        host,\n        "tick",\n        {"tick": 1},\n    )\n\n    assert result["ok"] is True\n    assert calls == [("tick", {"tick": 1})]\n\n\ndef test_taskrunner_registry_admission_consolidation_class_binding_if_taskrunner_exists() -> None:\n    import core.runtime.task_runner as module\n\n    cls = getattr(module, "TaskRunner", None)\n    if isinstance(cls, type):\n        assert hasattr(cls, "_aer_registry_admit")\n        assert hasattr(cls, "_registry_admit_owned_step")\n        assert hasattr(cls, "_registry_admit_tick")\n'
BLOCK_SOURCE = '# ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_BEGIN\ndef _zero_taskrunner_registry_admit_aer_closure_v24(self, event, payload=None):\n    payload = dict(payload or {})\n    event = str(event or "").strip() or "taskrunner_event"\n\n    registry = (\n        getattr(self, "runtime_route_registry", None)\n        or getattr(self, "route_registry", None)\n        or getattr(self, "registry", None)\n        or getattr(self, "_runtime_route_registry", None)\n        or getattr(self, "_route_registry", None)\n        or getattr(self, "_registry", None)\n    )\n\n    if registry is None:\n        return {"ok": True, "status": "skipped", "reason": "registry_unavailable", "event": event, "payload": payload}\n\n    for method_name in ("run_observer", "admit", "observe", "record", "register", "dispatch"):\n        method = getattr(registry, method_name, None)\n        if not callable(method):\n            continue\n\n        attempts = (\n            lambda: method(event=event, payload=payload),\n            lambda: method(event, payload),\n            lambda: method(payload),\n            lambda: method(event),\n        )\n        last_error = None\n        for attempt in attempts:\n            try:\n                result = attempt()\n                if isinstance(result, dict):\n                    normalized = dict(result)\n                    normalized.setdefault("ok", True)\n                    normalized.setdefault("event", event)\n                    normalized.setdefault("payload", payload)\n                    return normalized\n                return {"ok": True, "status": "admitted", "event": event, "payload": payload, "result": result}\n            except TypeError as exc:\n                last_error = exc\n                continue\n        if last_error is not None:\n            continue\n\n    return {"ok": True, "status": "skipped", "reason": "registry_method_unavailable", "event": event, "payload": payload}\n\n\ndef _zero_taskrunner_registry_admit_owned_step_v24(self, payload=None):\n    return _zero_taskrunner_registry_admit_aer_closure_v24(self, "execute_owned_step", payload)\n\n\ndef _zero_taskrunner_registry_admit_tick_v24(self, payload=None):\n    return _zero_taskrunner_registry_admit_aer_closure_v24(self, "tick", payload)\n\n\ntry:\n    _zero_taskrunner_cls_v24 = globals().get("TaskRunner")\n    if isinstance(_zero_taskrunner_cls_v24, type):\n        if not hasattr(_zero_taskrunner_cls_v24, "_aer_registry_admit"):\n            setattr(_zero_taskrunner_cls_v24, "_aer_registry_admit", _zero_taskrunner_registry_admit_aer_closure_v24)\n        if not hasattr(_zero_taskrunner_cls_v24, "_registry_admit_owned_step"):\n            setattr(_zero_taskrunner_cls_v24, "_registry_admit_owned_step", _zero_taskrunner_registry_admit_owned_step_v24)\n        if not hasattr(_zero_taskrunner_cls_v24, "_registry_admit_tick"):\n            setattr(_zero_taskrunner_cls_v24, "_registry_admit_tick", _zero_taskrunner_registry_admit_tick_v24)\nexcept Exception:\n    pass\n# ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_END\n'


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package24_backup_{stamp}"))


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
        "_zero_taskrunner_registry_admit_aer_closure_v24",
        "_zero_taskrunner_registry_admit_owned_step_v24",
        "_zero_taskrunner_registry_admit_tick_v24",
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
    updated = _install_block(source)
    ast.parse(updated)
    TASK_RUNNER_PATH.write_text(updated, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    report = "\n".join([
        "Package24 TaskRunner Registry Admission Consolidation Report",
        "",
        f"root: {ROOT}",
        f"task_runner: {TASK_RUNNER_PATH.relative_to(ROOT)}",
        f"test: {TEST_PATH.relative_to(ROOT)}",
        "",
        "Completed:",
        "- installed one TaskRunner registry admission helper",
        "- installed owned-step and tick helper wrappers",
        "- bound helper methods to TaskRunner when TaskRunner class exists",
        "- added consolidation seal tests",
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
        "python -m pytest tests/test_taskrunner_registry_admission_consolidation.py tests/test_taskrunner_aer_closure_inventory.py tests/test_aer_mainline_closure_seal.py -q",
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
