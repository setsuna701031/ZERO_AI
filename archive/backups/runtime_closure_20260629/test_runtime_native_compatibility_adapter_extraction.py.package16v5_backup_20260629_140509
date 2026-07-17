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
        run_via_runtime_native_mainline,
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

    via_runner = run_via_runtime_native_mainline(runner=lambda: {"ok": True})
    assert via_runner == {"ok": True}


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
