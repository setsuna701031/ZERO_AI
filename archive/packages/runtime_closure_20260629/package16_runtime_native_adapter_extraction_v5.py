from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "core" / "runtime"
TESTS_DIR = ROOT / "tests"
ADAPTER_PATH = RUNTIME_DIR / "runtime_native_entry_adapter.py"
MAINLINE_PATH = RUNTIME_DIR / "runtime_native_mainline.py"
TEST_PATH = TESTS_DIR / "test_runtime_native_compatibility_adapter_extraction.py"
REPORT_PATH = ROOT / "runtime_native_compatibility_adapter_extraction_report.txt"

MARKER_BEGIN = "# ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN"
MARKER_END = "# ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END"

ADAPTER_SOURCE = 'from __future__ import annotations\n\nfrom dataclasses import dataclass, field\nfrom typing import Any, Dict, Mapping, Optional\n\n\n_RUNTIME_TERMINAL_OK = {"finished", "success", "completed", "done", "ok"}\n_RUNTIME_TERMINAL_FAIL = {"failed", "error", "cancelled", "canceled"}\n\n\ndef _as_dict(value: Any) -> Dict[str, Any]:\n    if isinstance(value, dict):\n        return dict(value)\n    if isinstance(value, Mapping):\n        return dict(value.items())\n    return {}\n\n\ndef _clean_text(value: Any) -> str:\n    return str(value or "").strip()\n\n\ndef _pick_first(mapping: Mapping[str, Any], *keys: str) -> Any:\n    for key in keys:\n        if key in mapping and mapping.get(key) not in (None, ""):\n            return mapping.get(key)\n    return None\n\n\ndef normalize_runtime_native_status(value: Any) -> str:\n    text = _clean_text(value).lower()\n    if text in _RUNTIME_TERMINAL_OK:\n        return "finished"\n    if text in _RUNTIME_TERMINAL_FAIL:\n        return "failed"\n    if text in {"queued", "pending", "created", "new"}:\n        return "queued"\n    if text in {"running", "in_progress", "executing"}:\n        return "running"\n    if text in {"blocked", "waiting"}:\n        return "blocked"\n    if text in {"retry", "retrying"}:\n        return "retrying"\n    return text or "queued"\n\n\n@dataclass(frozen=True)\nclass RuntimeNativeEntryRequest:\n    goal: str = ""\n    task: Dict[str, Any] = field(default_factory=dict)\n    session_id: str = ""\n    runtime_session_id: str = ""\n    source: str = "runtime_native_entry_adapter"\n    metadata: Dict[str, Any] = field(default_factory=dict)\n\n    def to_dict(self) -> Dict[str, Any]:\n        payload = {\n            "goal": self.goal,\n            "task": dict(self.task),\n            "session_id": self.session_id,\n            "runtime_session_id": self.runtime_session_id,\n            "source": self.source,\n            "metadata": dict(self.metadata),\n        }\n        if self.session_id and "session_id" not in payload["task"]:\n            payload["task"]["session_id"] = self.session_id\n        if self.runtime_session_id and "runtime_session_id" not in payload["task"]:\n            payload["task"]["runtime_session_id"] = self.runtime_session_id\n        if self.goal and "goal" not in payload["task"]:\n            payload["task"]["goal"] = self.goal\n        return payload\n\n\ndef normalize_runtime_native_entry_request(value: Any) -> Dict[str, Any]:\n    raw = _as_dict(value)\n    task = _as_dict(_pick_first(raw, "task", "payload", "request"))\n    if not task:\n        task = dict(raw)\n\n    metadata = _as_dict(_pick_first(raw, "metadata", "meta"))\n    task_metadata = _as_dict(task.get("metadata"))\n    if task_metadata:\n        merged = dict(task_metadata)\n        merged.update(metadata)\n        metadata = merged\n\n    goal = _clean_text(_pick_first(raw, "goal", "goal_text", "instruction", "prompt"))\n    if not goal:\n        goal = _clean_text(_pick_first(task, "goal", "goal_text", "instruction", "prompt", "title"))\n\n    session_id = _clean_text(_pick_first(raw, "session_id", "operator_session_id"))\n    if not session_id:\n        session_id = _clean_text(_pick_first(task, "session_id", "operator_session_id"))\n\n    runtime_session_id = _clean_text(_pick_first(raw, "runtime_session_id", "runtime_id"))\n    if not runtime_session_id:\n        runtime_session_id = _clean_text(_pick_first(task, "runtime_session_id", "runtime_id"))\n    if not runtime_session_id:\n        runtime_session_id = session_id\n\n    source = _clean_text(_pick_first(raw, "source", "entry_source")) or "runtime_native_entry_adapter"\n\n    return RuntimeNativeEntryRequest(\n        goal=goal,\n        task=task,\n        session_id=session_id,\n        runtime_session_id=runtime_session_id,\n        source=source,\n        metadata=metadata,\n    ).to_dict()\n\n\ndef build_runtime_native_entry_request(\n    goal: Any = "",\n    task: Optional[Mapping[str, Any]] = None,\n    session_id: Any = "",\n    runtime_session_id: Any = "",\n    metadata: Optional[Mapping[str, Any]] = None,\n    source: str = "runtime_native_entry_adapter",\n) -> Dict[str, Any]:\n    payload: Dict[str, Any] = {\n        "goal": _clean_text(goal),\n        "task": dict(task or {}),\n        "session_id": _clean_text(session_id),\n        "runtime_session_id": _clean_text(runtime_session_id),\n        "metadata": dict(metadata or {}),\n        "source": source,\n    }\n    return normalize_runtime_native_entry_request(payload)\n\n\ndef _call_first_available(target: Any, request: Dict[str, Any]) -> Any:\n    for name in ("run_native", "run_entry", "run_request", "run", "execute", "submit", "admit", "dispatch"):\n        fn = getattr(target, name, None)\n        if callable(fn):\n            return fn(request)\n    raise AttributeError("Runtime native mainline object has no supported entry method")\n\n\ndef normalize_runtime_native_entry_result(value: Any) -> Dict[str, Any]:\n    if isinstance(value, dict):\n        result = dict(value)\n    else:\n        result = {"ok": True, "result": value}\n\n    if "status" in result:\n        result["status"] = normalize_runtime_native_status(result.get("status"))\n    elif result.get("ok") is True:\n        result["status"] = "finished"\n    elif result.get("ok") is False:\n        result["status"] = "failed"\n\n    return result\n\n\nclass RuntimeNativeEntryAdapter:\n    def __init__(self, mainline: Any = None) -> None:\n        self.mainline = mainline\n\n    def normalize(self, value: Any) -> Dict[str, Any]:\n        return normalize_runtime_native_entry_request(value)\n\n    def run(self, value: Any, mainline: Any = None) -> Dict[str, Any]:\n        request = normalize_runtime_native_entry_request(value)\n        target = mainline if mainline is not None else self.mainline\n        if target is None:\n            return {"ok": True, "status": "queued", "request": request, "adapter": "runtime_native_entry_adapter"}\n        return normalize_runtime_native_entry_result(_call_first_available(target, request))\n\n    execute = run\n    admit = run\n    dispatch = run\n\n    def __call__(self, value: Any, mainline: Any = None) -> Dict[str, Any]:\n        return self.run(value, mainline=mainline)\n\n\ndef run_runtime_native_entry(mainline: Any, value: Any) -> Dict[str, Any]:\n    return RuntimeNativeEntryAdapter(mainline).run(value)\n\n\ndef run_via_runtime_native_mainline(**kwargs: Any) -> Any:\n    runner = kwargs.get("runner")\n    if callable(runner):\n        return runner()\n\n    mainline = kwargs.get("mainline")\n    payload = kwargs.get("payload")\n    if payload is None:\n        payload = kwargs.get("request")\n    if payload is None:\n        payload = kwargs.get("task")\n    if payload is None:\n        payload = kwargs\n\n    if mainline is not None:\n        return run_runtime_native_entry(mainline, payload)\n\n    return RuntimeNativeEntryAdapter().run(payload)\n\n\n__all__ = [\n    "RuntimeNativeEntryAdapter",\n    "RuntimeNativeEntryRequest",\n    "build_runtime_native_entry_request",\n    "normalize_runtime_native_entry_request",\n    "normalize_runtime_native_entry_result",\n    "normalize_runtime_native_status",\n    "run_runtime_native_entry",\n    "run_via_runtime_native_mainline",\n]\n'
TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_runtime_native_entry_adapter_module_exists_and_compiles() -> None:\n    path = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"\n    assert path.exists()\n    ast.parse(path.read_text(encoding="utf-8"))\n\n\ndef test_runtime_native_entry_adapter_exports_compatibility_surface() -> None:\n    from core.runtime.runtime_native_entry_adapter import (\n        RuntimeNativeEntryAdapter,\n        build_runtime_native_entry_request,\n        normalize_runtime_native_entry_request,\n        run_runtime_native_entry,\n        run_via_runtime_native_mainline,\n    )\n\n    request = build_runtime_native_entry_request(\n        goal="seal native entry adapter",\n        task={"type": "noop"},\n        session_id="s1",\n    )\n    assert request["goal"] == "seal native entry adapter"\n    assert request["session_id"] == "s1"\n    assert request["runtime_session_id"] == "s1"\n    assert request["task"]["session_id"] == "s1"\n\n    normalized = normalize_runtime_native_entry_request(\n        {\n            "payload": {"instruction": "legacy goal", "session_id": "legacy-session"},\n            "metadata": {"source_test": True},\n        }\n    )\n    assert normalized["goal"] == "legacy goal"\n    assert normalized["session_id"] == "legacy-session"\n    assert normalized["runtime_session_id"] == "legacy-session"\n    assert normalized["metadata"]["source_test"] is True\n\n    adapter = RuntimeNativeEntryAdapter()\n    result = adapter.run({"goal": "queued only"})\n    assert result["ok"] is True\n    assert result["status"] == "queued"\n\n    class FakeMainline:\n        def run(self, payload):\n            return {"ok": True, "status": "success", "received": payload}\n\n    dispatched = run_runtime_native_entry(FakeMainline(), {"goal": "dispatch me"})\n    assert dispatched["ok"] is True\n    assert dispatched["status"] == "finished"\n    assert dispatched["received"]["goal"] == "dispatch me"\n\n    via_runner = run_via_runtime_native_mainline(runner=lambda: {"ok": True})\n    assert via_runner == {"ok": True}\n\n\ndef test_runtime_native_mainline_imports_after_adapter_extraction() -> None:\n    import core.runtime.runtime_native_mainline as module\n\n    assert module is not None\n\n\ndef test_adapter_does_not_import_forbidden_mainline_surfaces() -> None:\n    path = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"\n    source = path.read_text(encoding="utf-8")\n    forbidden = [\n        "core.tasks.scheduler",\n        "TaskRunner",\n        "AgentLoop",\n        "RuntimeRouteRegistry",\n        "work_package_cli",\n    ]\n    for token in forbidden:\n        assert token not in source\n'

BINDING_SOURCE = f"""{MARKER_BEGIN}
try:
    from core.runtime.runtime_native_entry_adapter import (
        RuntimeNativeEntryAdapter as _ZeroRuntimeNativeEntryAdapter,
        normalize_runtime_native_entry_request as _zero_normalize_runtime_native_entry_request,
        run_runtime_native_entry as _zero_run_runtime_native_entry,
        run_via_runtime_native_mainline as _zero_run_via_runtime_native_mainline,
    )

    def _zero_runtime_native_mainline_admit_legacy_request(self, payload):
        return _zero_run_runtime_native_entry(self, payload)

    def _zero_runtime_native_mainline_normalize_legacy_request(self, payload):
        return _zero_normalize_runtime_native_entry_request(payload)

    for _zero_cls_name in ("RuntimeNativeMainLine", "RuntimeNativeMainline", "RuntimeNativeMainlineV1"):
        _zero_cls = globals().get(_zero_cls_name)
        if isinstance(_zero_cls, type):
            if not hasattr(_zero_cls, "admit_legacy_request"):
                setattr(_zero_cls, "admit_legacy_request", _zero_runtime_native_mainline_admit_legacy_request)
            if not hasattr(_zero_cls, "normalize_legacy_request"):
                setattr(_zero_cls, "normalize_legacy_request", _zero_runtime_native_mainline_normalize_legacy_request)
except Exception:
    pass
{MARKER_END}
"""


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.package16v5_backup_{stamp}")
    shutil.copy2(path, backup)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(text)
    path.write_text(text, encoding="utf-8", newline="\n")


def _replace_or_append_binding(source: str) -> str:
    if MARKER_BEGIN in source and MARKER_END in source:
        before = source.split(MARKER_BEGIN, 1)[0].rstrip()
        after = source.split(MARKER_END, 1)[1].lstrip()
        return before + "\n\n" + BINDING_SOURCE + "\n" + after
    return source.rstrip() + "\n\n" + BINDING_SOURCE


def main() -> int:
    if not MAINLINE_PATH.exists():
        raise FileNotFoundError(f"Missing runtime mainline: {MAINLINE_PATH}")

    _backup(ADAPTER_PATH)
    _backup(TEST_PATH)
    _backup(MAINLINE_PATH)

    _write(ADAPTER_PATH, ADAPTER_SOURCE)
    _write(TEST_PATH, TEST_SOURCE)

    mainline_source = MAINLINE_PATH.read_text(encoding="utf-8")
    updated_mainline = _replace_or_append_binding(mainline_source)
    ast.parse(updated_mainline)
    MAINLINE_PATH.write_text(updated_mainline, encoding="utf-8", newline="\n")

    report = "\n".join([
        "Package16 v5 Runtime Native Adapter Extraction Report",
        "",
        f"root: {ROOT}",
        f"adapter: {ADAPTER_PATH.relative_to(ROOT)}",
        f"mainline: {MAINLINE_PATH.relative_to(ROOT)}",
        f"test: {TEST_PATH.relative_to(ROOT)}",
        "",
        "Touched:",
        "- core/runtime/runtime_native_entry_adapter.py",
        "- core/runtime/runtime_native_mainline.py",
        "- tests/test_runtime_native_compatibility_adapter_extraction.py",
        "- runtime_native_compatibility_adapter_extraction_report.txt",
        "",
        "Compatibility restored:",
        "- core.runtime.runtime_native_entry_adapter.run_via_runtime_native_mainline",
        "",
        "Not touched:",
        "- Scheduler",
        "- TaskRunner",
        "- AgentLoop",
        "- CLI",
        "- RuntimeRouteRegistry",
        "",
        "Validation:",
        "python -m compileall core/runtime tests",
        "python -m pytest tests/test_runtime_native_compatibility_adapter_extraction.py tests/test_runtime_native_compatibility_entry_semantics.py tests/test_runtime_route_registry_admission.py tests/test_aer_mainline_closure_seal.py -q",
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
