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


ADAPTER_SOURCE = r''''''
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


_RUNTIME_TERMINAL_OK = {"finished", "success", "completed", "done", "ok"}
_RUNTIME_TERMINAL_FAIL = {"failed", "error", "cancelled", "canceled"}


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, Mapping):
        return dict(value.items())
    return {}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _pick_first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return mapping.get(key)
    return None


def normalize_runtime_native_status(value: Any) -> str:
    text = _clean_text(value).lower()
    if text in _RUNTIME_TERMINAL_OK:
        return "finished"
    if text in _RUNTIME_TERMINAL_FAIL:
        return "failed"
    if text in {"queued", "pending", "created", "new"}:
        return "queued"
    if text in {"running", "in_progress", "executing"}:
        return "running"
    if text in {"blocked", "waiting"}:
        return "blocked"
    if text in {"retry", "retrying"}:
        return "retrying"
    return text or "queued"


@dataclass(frozen=True)
class RuntimeNativeEntryRequest:
    goal: str = ""
    task: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    runtime_session_id: str = ""
    source: str = "runtime_native_entry_adapter"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "goal": self.goal,
            "task": dict(self.task),
            "session_id": self.session_id,
            "runtime_session_id": self.runtime_session_id,
            "source": self.source,
            "metadata": dict(self.metadata),
        }
        if self.session_id and "session_id" not in payload["task"]:
            payload["task"]["session_id"] = self.session_id
        if self.runtime_session_id and "runtime_session_id" not in payload["task"]:
            payload["task"]["runtime_session_id"] = self.runtime_session_id
        if self.goal and "goal" not in payload["task"]:
            payload["task"]["goal"] = self.goal
        return payload


def normalize_runtime_native_entry_request(value: Any) -> Dict[str, Any]:
    raw = _as_dict(value)
    task = _as_dict(_pick_first(raw, "task", "payload", "request"))
    if not task:
        task = dict(raw)

    metadata = _as_dict(_pick_first(raw, "metadata", "meta"))
    task_metadata = _as_dict(task.get("metadata"))
    if task_metadata:
        merged = dict(task_metadata)
        merged.update(metadata)
        metadata = merged

    goal = _clean_text(_pick_first(raw, "goal", "goal_text", "instruction", "prompt"))
    if not goal:
        goal = _clean_text(_pick_first(task, "goal", "goal_text", "instruction", "prompt", "title"))

    session_id = _clean_text(_pick_first(raw, "session_id", "operator_session_id"))
    if not session_id:
        session_id = _clean_text(_pick_first(task, "session_id", "operator_session_id"))

    runtime_session_id = _clean_text(_pick_first(raw, "runtime_session_id", "runtime_id"))
    if not runtime_session_id:
        runtime_session_id = _clean_text(_pick_first(task, "runtime_session_id", "runtime_id"))
    if not runtime_session_id:
        runtime_session_id = session_id

    source = _clean_text(_pick_first(raw, "source", "entry_source")) or "runtime_native_entry_adapter"

    return RuntimeNativeEntryRequest(
        goal=goal,
        task=task,
        session_id=session_id,
        runtime_session_id=runtime_session_id,
        source=source,
        metadata=metadata,
    ).to_dict()


def build_runtime_native_entry_request(
    goal: Any = "",
    task: Optional[Mapping[str, Any]] = None,
    session_id: Any = "",
    runtime_session_id: Any = "",
    metadata: Optional[Mapping[str, Any]] = None,
    source: str = "runtime_native_entry_adapter",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "goal": _clean_text(goal),
        "task": dict(task or {}),
        "session_id": _clean_text(session_id),
        "runtime_session_id": _clean_text(runtime_session_id),
        "metadata": dict(metadata or {}),
        "source": source,
    }
    return normalize_runtime_native_entry_request(payload)


def _call_first_available(target: Any, request: Dict[str, Any]) -> Any:
    for name in ("run_native", "run_entry", "run_request", "run", "execute", "submit", "admit", "dispatch"):
        fn = getattr(target, name, None)
        if callable(fn):
            return fn(request)
    raise AttributeError("Runtime native mainline object has no supported entry method")


def normalize_runtime_native_entry_result(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        result = dict(value)
    else:
        result = {"ok": True, "result": value}

    if "status" in result:
        result["status"] = normalize_runtime_native_status(result.get("status"))
    elif result.get("ok") is True:
        result["status"] = "finished"
    elif result.get("ok") is False:
        result["status"] = "failed"

    return result


class RuntimeNativeEntryAdapter:
    def __init__(self, mainline: Any = None) -> None:
        self.mainline = mainline

    def normalize(self, value: Any) -> Dict[str, Any]:
        return normalize_runtime_native_entry_request(value)

    def run(self, value: Any, mainline: Any = None) -> Dict[str, Any]:
        request = normalize_runtime_native_entry_request(value)
        target = mainline if mainline is not None else self.mainline
        if target is None:
            return {"ok": True, "status": "queued", "request": request, "adapter": "runtime_native_entry_adapter"}
        return normalize_runtime_native_entry_result(_call_first_available(target, request))

    execute = run
    admit = run
    dispatch = run

    def __call__(self, value: Any, mainline: Any = None) -> Dict[str, Any]:
        return self.run(value, mainline=mainline)


def run_runtime_native_entry(mainline: Any, value: Any) -> Dict[str, Any]:
    return RuntimeNativeEntryAdapter(mainline).run(value)


__all__ = [
    "RuntimeNativeEntryAdapter",
    "RuntimeNativeEntryRequest",
    "build_runtime_native_entry_request",
    "normalize_runtime_native_entry_request",
    "normalize_runtime_native_entry_result",
    "normalize_runtime_native_status",
    "run_runtime_native_entry",
]
''''''
ADAPTER_SOURCE = ADAPTER_SOURCE.strip() + "\n"


TEST_SOURCE = r''''''
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_native_entry_adapter_module_exists_and_compiles() -> None:
    path = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"
    assert path.exists()
    ast.parse(path.read_text(encoding="utf-8"))


def test_runtime_native_entry_adapter_exports_compatibility_surface() -> None:
    from core.runtime.runtime_native_entry_adapter import (
        RuntimeNativeEntryAdapter,
        build_runtime_native_entry_request,
        normalize_runtime_native_entry_request,
        run_runtime_native_entry,
    )

    request = build_runtime_native_entry_request(
        goal="seal native entry adapter",
        task={"type": "noop"},
        session_id="s1",
    )
    assert request["goal"] == "seal native entry adapter"
    assert request["session_id"] == "s1"
    assert request["runtime_session_id"] == "s1"
    assert request["task"]["session_id"] == "s1"

    normalized = normalize_runtime_native_entry_request(
        {
            "payload": {"instruction": "legacy goal", "session_id": "legacy-session"},
            "metadata": {"source_test": True},
        }
    )
    assert normalized["goal"] == "legacy goal"
    assert normalized["session_id"] == "legacy-session"
    assert normalized["runtime_session_id"] == "legacy-session"
    assert normalized["metadata"]["source_test"] is True

    adapter = RuntimeNativeEntryAdapter()
    result = adapter.run({"goal": "queued only"})
    assert result["ok"] is True
    assert result["status"] == "queued"

    class FakeMainline:
        def run(self, payload):
            return {"ok": True, "status": "success", "received": payload}

    dispatched = run_runtime_native_entry(FakeMainline(), {"goal": "dispatch me"})
    assert dispatched["ok"] is True
    assert dispatched["status"] == "finished"
    assert dispatched["received"]["goal"] == "dispatch me"


def test_runtime_native_mainline_imports_after_adapter_extraction() -> None:
    import core.runtime.runtime_native_mainline as module

    assert module is not None


def test_adapter_does_not_import_forbidden_mainline_surfaces() -> None:
    path = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"
    source = path.read_text(encoding="utf-8")
    forbidden = [
        "core.tasks.scheduler",
        "TaskRunner",
        "AgentLoop",
        "RuntimeRouteRegistry",
        "work_package_cli",
    ]
    for token in forbidden:
        assert token not in source
''''''
TEST_SOURCE = TEST_SOURCE.strip() + "\n"


BINDING_SOURCE = f'''
{MARKER_BEGIN}
try:
    from core.runtime.runtime_native_entry_adapter import (
        RuntimeNativeEntryAdapter as _ZeroRuntimeNativeEntryAdapter,
        normalize_runtime_native_entry_request as _zero_normalize_runtime_native_entry_request,
        run_runtime_native_entry as _zero_run_runtime_native_entry,
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
'''.strip() + "\n"


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.package16v2_backup_{stamp}")
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

    report = "\n".join(
        [
            "Package16 v2 Runtime Native Adapter Extraction Report",
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
        ]
    )
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")
    print(str(REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
