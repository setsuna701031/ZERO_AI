from pathlib import Path

ROOT = Path.cwd()
MAINLINE = ROOT / "core" / "runtime" / "runtime_native_mainline.py"
ADAPTER = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"
TEST = ROOT / "tests" / "test_runtime_native_compatibility_adapter_extraction.py"
REPORT = ROOT / "runtime_native_compatibility_adapter_extraction_report.txt"


ADAPTER_CONTENT = """from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable


CompatibilityRunner = Callable[[], Any]


@dataclass(frozen=True)
class RuntimeNativeCompatibilityEntryResult:
    raw_result: Any
    result_payload: dict[str, Any]
    status: str
    event_type: str
    exception: BaseException | None = None


class RuntimeNativeCompatibilityEntryAdapter:
    """Compatibility semantics for RuntimeNativeMainline legacy admissions.

    This adapter owns behavior-shaping only:
    - dict results receive additive metadata.
    - non-dict results are returned unchanged to the caller.
    - exceptions are captured for audit and must be re-raised by the caller
      after persistence/event recording.
    """

    def run(
        self,
        *,
        entrypoint: str,
        runner: CompatibilityRunner,
        request: dict[str, Any] | None = None,
        goal: str = "",
        metadata: dict[str, Any] | None = None,
        status_completed: str = "completed",
        status_failed: str = "failed",
    ) -> RuntimeNativeCompatibilityEntryResult:
        if not callable(runner):
            raise TypeError("runtime_native_compatibility_runner_must_be_callable")

        normalized_entrypoint = str(entrypoint or "").strip()
        payload = copy.deepcopy(request) if isinstance(request, dict) else {}
        _ = payload
        _ = str(goal or "").strip()
        _ = copy.deepcopy(metadata or {})

        try:
            raw_result = runner()
        except Exception as exc:
            result_payload = {
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
                "runtime_native_mainline_entrypoint": normalized_entrypoint,
                "runtime_native_mainline_compatibility_wrapper": True,
                "runtime_native_mainline_canonical_entry": True,
            }
            result_payload["execution_path"] = {
                "runtime_native_mainline_entrypoint": normalized_entrypoint,
                "runtime_native_mainline_canonical_entry": True,
                "legacy_behavior_preserved": True,
                "exception_reraised_after_audit": True,
            }
            return RuntimeNativeCompatibilityEntryResult(
                raw_result=None,
                result_payload=result_payload,
                status=status_failed,
                event_type="runtime_native_mainline_compatibility_entry_failed",
                exception=exc,
            )

        if isinstance(raw_result, dict):
            result_payload = copy.deepcopy(raw_result)
            self._attach_dict_metadata(result_payload, normalized_entrypoint)
            ok = bool(result_payload.get("ok", True))
            return RuntimeNativeCompatibilityEntryResult(
                raw_result=result_payload,
                result_payload=result_payload,
                status=status_completed if ok else status_failed,
                event_type="runtime_native_mainline_compatibility_entry_completed",
                exception=None,
            )

        result_payload = {
            "ok": bool(raw_result),
            "result": copy.deepcopy(raw_result),
            "runtime_native_mainline_entrypoint": normalized_entrypoint,
            "runtime_native_mainline_compatibility_wrapper": True,
            "runtime_native_mainline_canonical_entry": True,
            "execution_path": {
                "runtime_native_mainline_entrypoint": normalized_entrypoint,
                "runtime_native_mainline_canonical_entry": True,
                "legacy_behavior_preserved": True,
                "non_dict_passthrough": True,
            },
        }
        return RuntimeNativeCompatibilityEntryResult(
            raw_result=raw_result,
            result_payload=result_payload,
            status=status_completed if bool(raw_result) else status_failed,
            event_type="runtime_native_mainline_compatibility_entry_completed",
            exception=None,
        )

    def _attach_dict_metadata(self, result_payload: dict[str, Any], entrypoint: str) -> None:
        result_payload.setdefault("runtime_native_mainline_entrypoint", entrypoint)
        result_payload.setdefault("runtime_native_mainline_compatibility_wrapper", True)
        result_payload.setdefault("runtime_native_mainline_canonical_entry", True)

        path = result_payload.get("execution_path")
        if not isinstance(path, dict):
            path = {}
        path.setdefault("runtime_native_mainline_entrypoint", entrypoint)
        path.setdefault("runtime_native_mainline_canonical_entry", True)
        path.setdefault("legacy_behavior_preserved", True)
        result_payload["execution_path"] = path
"""


TEST_CONTENT = """from __future__ import annotations

import pytest

from core.runtime.runtime_native_entry_adapter import RuntimeNativeCompatibilityEntryAdapter


def test_adapter_adds_metadata_to_dict_result_without_replacing_payload() -> None:
    adapter = RuntimeNativeCompatibilityEntryAdapter()

    result = adapter.run(
        entrypoint="tests.adapter.dict",
        runner=lambda: {"ok": True, "value": 42},
        request={"goal": "dict"},
        goal="dict",
    )

    assert result.raw_result["ok"] is True
    assert result.raw_result["value"] == 42
    assert result.raw_result["runtime_native_mainline_canonical_entry"] is True
    assert result.result_payload["execution_path"]["legacy_behavior_preserved"] is True
    assert result.exception is None


def test_adapter_preserves_non_dict_truthy_result() -> None:
    adapter = RuntimeNativeCompatibilityEntryAdapter()

    result = adapter.run(
        entrypoint="tests.adapter.raw",
        runner=lambda: "raw-value",
        request={},
        goal="raw",
    )

    assert result.raw_result == "raw-value"
    assert result.result_payload["result"] == "raw-value"
    assert result.result_payload["execution_path"]["non_dict_passthrough"] is True


def test_adapter_preserves_non_dict_falsy_result() -> None:
    adapter = RuntimeNativeCompatibilityEntryAdapter()

    result = adapter.run(
        entrypoint="tests.adapter.none",
        runner=lambda: None,
        request={},
        goal="none",
    )

    assert result.raw_result is None
    assert result.result_payload["ok"] is False
    assert result.status == "failed"


def test_adapter_captures_exception_for_caller_reraise_after_audit() -> None:
    adapter = RuntimeNativeCompatibilityEntryAdapter()

    def boom():
        raise RuntimeError("adapter boom")

    result = adapter.run(
        entrypoint="tests.adapter.exception",
        runner=boom,
        request={},
        goal="boom",
    )

    assert isinstance(result.exception, RuntimeError)
    assert result.result_payload["ok"] is False
    assert result.event_type == "runtime_native_mainline_compatibility_entry_failed"
    with pytest.raises(RuntimeError, match="adapter boom"):
        raise result.exception
"""


def replace_run_compatibility_entry(text: str) -> str:
    marker = "    def run_compatibility_entry(\n"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError("run_compatibility_entry method not found")

    next_marker = "\n    def health("
    end = text.find(next_marker, start)
    if end < 0:
        raise RuntimeError("health method marker not found after run_compatibility_entry")

    replacement = """    def run_compatibility_entry(
        self,
        *,
        entrypoint: str,
        runner: CompatibilityRunnerFn,
        request: dict[str, Any] | None = None,
        goal: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Canonical admission wrapper for legacy entrypoints.

        RuntimeNativeMainline now delegates compatibility result semantics to
        RuntimeNativeCompatibilityEntryAdapter while retaining persistence,
        event recording, and the public compatibility API.
        """
        if not self._booted:
            self.boot()

        from core.runtime.runtime_native_entry_adapter import RuntimeNativeCompatibilityEntryAdapter

        entrypoint = self._validate_text("entrypoint", entrypoint)
        payload = _copy_dict(request)
        compatibility_metadata = {
            "runtime_native_mainline_compatibility_wrapper": True,
            "compatibility_entrypoint": entrypoint,
            **copy.deepcopy(metadata or {}),
        }
        run_goal = str(
            goal
            or payload.get("goal")
            or payload.get("prompt")
            or payload.get("task")
            or payload.get("task_id")
            or entrypoint
        ).strip()
        run_id = "runtime-native-mainline-compat-" + stable_mainline_fingerprint(
            {
                "entrypoint": entrypoint,
                "goal": run_goal,
                "sequence": len(self._runs) + 1,
            }
        )[:16]

        adapter_result = RuntimeNativeCompatibilityEntryAdapter().run(
            entrypoint=entrypoint,
            runner=runner,
            request=payload,
            goal=run_goal,
            metadata=compatibility_metadata,
            status_completed=MAINLINE_STATUS_COMPLETED,
            status_failed=MAINLINE_STATUS_FAILED,
        )

        result = RuntimeNativeMainlineRunResult(
            run_id=run_id,
            status=adapter_result.status,
            goal=run_goal,
            runtime_id=self.config.runtime_id,
            source_session_id=self.config.source_session_id,
            final_result=adapter_result.result_payload,
            metadata=compatibility_metadata,
        )
        self._store_result(result)
        self._append_event(
            adapter_result.event_type,
            run_id=run_id,
            payload={"entrypoint": entrypoint, "result": result.to_dict()},
        )
        self.save()

        if adapter_result.exception is not None:
            raise adapter_result.exception

        return adapter_result.raw_result
"""
    return text[:start] + replacement + text[end:]


def main() -> None:
    if not MAINLINE.is_file():
        raise SystemExit(f"missing {MAINLINE}")

    ADAPTER.parent.mkdir(parents=True, exist_ok=True)
    ADAPTER.write_text(ADAPTER_CONTENT, encoding="utf-8")

    mainline_text = MAINLINE.read_text(encoding="utf-8")
    MAINLINE.write_text(replace_run_compatibility_entry(mainline_text), encoding="utf-8")

    TEST.parent.mkdir(parents=True, exist_ok=True)
    TEST.write_text(TEST_CONTENT, encoding="utf-8")

    REPORT.write_text(
        """RuntimeNative Compatibility Adapter Extraction Report
================================================

Status: Package 16
Code changes:
- core/runtime/runtime_native_entry_adapter.py now owns compatibility result semantics.
- core/runtime/runtime_native_mainline.py delegates run_compatibility_entry semantics to the adapter.
- tests/test_runtime_native_compatibility_adapter_extraction.py added.

Semantics preserved:
- dict result: additive metadata only.
- non-dict truthy result: raw value returned to caller.
- non-dict falsy / None result: raw value returned to caller.
- exception: failed compatibility result/event is recorded by RuntimeNativeMainline, then original exception is re-raised.
- RuntimeNativeMainline still owns persistence/event recording.
- RuntimeRouteRegistry routing behavior is unchanged.

Files intentionally not touched:
- Scheduler
- TaskRunner
- AgentLoop
- CLI
- RuntimeRouteRegistry

Recommended short validation:
python -m compileall core/runtime tests
python -m pytest tests/test_runtime_native_compatibility_adapter_extraction.py tests/test_runtime_native_compatibility_entry_semantics.py tests/test_runtime_route_registry_admission.py tests/test_aer_mainline_closure_seal.py -q
""",
        encoding="utf-8",
    )

    print("patched RuntimeNative compatibility adapter extraction")
    print(f"wrote {ADAPTER}")
    print(f"patched {MAINLINE}")
    print(f"wrote {TEST}")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
