from __future__ import annotations

from pathlib import Path


REPO_STATE_PATH = Path("core/tasks/scheduler_core/repo_state_helpers.py")
TEST_PATH = Path("tests/test_repo_runtime_state_adapter_contract.py")


HELPER_BLOCK = r'''

# ============================================================
# ZERO Runtime Aggregate Convergence v1.3A
# Repo Runtime State Aggregate Adapter Payload
# ============================================================

def attach_repo_runtime_state_adapter_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    if isinstance(payload.get("adapter_payload"), dict):
        return payload

    ok = _repo_runtime_adapter_ok(payload)
    message = _repo_runtime_adapter_message(payload, ok=ok)
    final_answer = _repo_runtime_adapter_final_answer(payload, message=message)

    adapter_payload = {
        "ok": ok,
        "message": message,
        "final_answer": final_answer,
        "text": final_answer or message,
        "error_text": "" if ok else _repo_runtime_adapter_error_text(payload),
        "error_type": "" if ok else _repo_runtime_adapter_error_type(payload),
        "runtime_mode": _repo_runtime_adapter_runtime_mode(payload),
        "last_result": _repo_runtime_adapter_last_result(payload),
        "execution_trace": _repo_runtime_adapter_execution_trace(payload),
        "raw": copy.deepcopy(payload),
    }

    payload["adapter_payload"] = adapter_payload
    return payload


def build_repo_runtime_state_adapter_payload(
    *,
    merged: Dict[str, Any],
    runner_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged_payload = copy.deepcopy(merged) if isinstance(merged, dict) else {}
    runner_payload = copy.deepcopy(runner_result) if isinstance(runner_result, dict) else {}

    if isinstance(runner_payload.get("adapter_payload"), dict):
        adapter = copy.deepcopy(runner_payload["adapter_payload"])
        merged_payload["adapter_payload"] = adapter
        return merged_payload

    status = str(merged_payload.get("status") or "").strip().lower()
    runner_ok = runner_payload.get("ok") if isinstance(runner_payload, dict) else None

    if runner_ok is not None:
        ok = bool(runner_ok)
    elif status in {"failed", "error", "cancelled"}:
        ok = False
    else:
        ok = True

    message = str(
        merged_payload.get("message")
        or runner_payload.get("message")
        or merged_payload.get("final_answer")
        or runner_payload.get("final_answer")
        or ("runtime state ok" if ok else "runtime state failed")
    )

    final_answer = str(
        merged_payload.get("final_answer")
        or runner_payload.get("final_answer")
        or message
    )

    error_text = str(
        merged_payload.get("last_error")
        or merged_payload.get("failure_message")
        or runner_payload.get("error")
        or ""
    )

    error_type = str(
        merged_payload.get("failure_type")
        or runner_payload.get("error_type")
        or ""
    )

    execution_trace = []
    for source in (runner_payload, merged_payload):
        trace = source.get("execution_trace") if isinstance(source, dict) else None
        if isinstance(trace, list):
            execution_trace = copy.deepcopy(trace)
            break

    last_result = {}
    for source in (runner_payload, merged_payload):
        candidate = source.get("last_result") if isinstance(source, dict) else None
        if isinstance(candidate, dict):
            last_result = copy.deepcopy(candidate)
            break
        candidate = source.get("last_step_result") if isinstance(source, dict) else None
        if isinstance(candidate, dict):
            last_result = copy.deepcopy(candidate)
            break

    merged_payload["adapter_payload"] = {
        "ok": ok,
        "message": message,
        "final_answer": final_answer,
        "text": final_answer or message,
        "error_text": "" if ok else error_text,
        "error_type": "" if ok else (error_type or "runtime_state_failed"),
        "runtime_mode": str(merged_payload.get("runtime_mode") or runner_payload.get("runtime_mode") or "repo_state"),
        "last_result": last_result,
        "execution_trace": execution_trace,
        "raw": copy.deepcopy(merged_payload),
    }
    return merged_payload


def _repo_runtime_adapter_ok(payload: Dict[str, Any]) -> bool:
    if "ok" in payload:
        return bool(payload.get("ok"))

    status = str(payload.get("status") or "").strip().lower()
    if status in {"failed", "error", "cancelled"}:
        return False

    if payload.get("last_error") or payload.get("failure_message"):
        return False

    return True


def _repo_runtime_adapter_message(payload: Dict[str, Any], *, ok: bool) -> str:
    for key in ("message", "summary", "final_answer"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    if not ok:
        return _repo_runtime_adapter_error_text(payload) or "runtime state failed"

    return "runtime state ok"


def _repo_runtime_adapter_final_answer(payload: Dict[str, Any], *, message: str) -> str:
    value = payload.get("final_answer")
    if value is not None and str(value).strip():
        return str(value).strip()
    return message


def _repo_runtime_adapter_error_text(payload: Dict[str, Any]) -> str:
    for key in ("last_error", "failure_message", "error_text", "error"):
        value = payload.get(key)
        if isinstance(value, dict):
            message = value.get("message") or value.get("error") or value.get("text")
            if message is not None and str(message).strip():
                return str(message).strip()
        elif value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _repo_runtime_adapter_error_type(payload: Dict[str, Any]) -> str:
    for key in ("failure_type", "error_type"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    error = payload.get("error")
    if isinstance(error, dict):
        for key in ("type", "error_type", "code"):
            value = error.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    return "runtime_state_failed" if _repo_runtime_adapter_error_text(payload) else ""


def _repo_runtime_adapter_runtime_mode(payload: Dict[str, Any]) -> str:
    for key in ("runtime_mode", "mode", "execution_mode"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "repo_state"


def _repo_runtime_adapter_last_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("last_result", "last_step_result", "runner_result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return copy.deepcopy(value)
    return {}


def _repo_runtime_adapter_execution_trace(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    trace = payload.get("execution_trace")
    if isinstance(trace, list):
        return copy.deepcopy(trace)

    for key in ("last_result", "last_step_result", "runner_result"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested_trace = nested.get("execution_trace")
            if isinstance(nested_trace, list):
                return copy.deepcopy(nested_trace)

    return []
'''


TEST_CONTENT = r'''from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RepoRuntimeStateAdapterContractTest(unittest.TestCase):
    def test_success_repo_runtime_state_gets_adapter_payload(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import attach_repo_runtime_state_adapter_payload

        payload: Dict[str, Any] = {
            "status": "finished",
            "final_answer": "done",
            "runtime_mode": "repo_state",
            "execution_trace": [{"step": 1, "ok": True}],
        }

        adapted = attach_repo_runtime_state_adapter_payload(copy.deepcopy(payload))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("message"), "done")
        self.assertEqual(adapter.get("final_answer"), "done")
        self.assertEqual(adapter.get("runtime_mode"), "repo_state")
        self.assertEqual(adapter.get("execution_trace"), [{"step": 1, "ok": True}])

    def test_failed_repo_runtime_state_gets_error_payload(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import attach_repo_runtime_state_adapter_payload

        payload: Dict[str, Any] = {
            "status": "failed",
            "failure_type": "execution_failed",
            "failure_message": "boom",
            "last_error": "boom",
        }

        adapted = attach_repo_runtime_state_adapter_payload(copy.deepcopy(payload))
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), False)
        self.assertEqual(adapter.get("error_type"), "execution_failed")
        self.assertEqual(adapter.get("error_text"), "boom")
        self.assertEqual(adapter.get("runtime_mode"), "repo_state")

    def test_build_repo_runtime_state_adapter_uses_runner_result(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_repo_runtime_state_adapter_payload

        merged: Dict[str, Any] = {
            "status": "running",
            "final_answer": "",
        }
        runner_result: Dict[str, Any] = {
            "ok": True,
            "message": "runner ok",
            "final_answer": "runner done",
            "runtime_mode": "execute",
            "execution_trace": [{"runner": True}],
            "last_result": {"ok": True},
        }

        adapted = build_repo_runtime_state_adapter_payload(
            merged=copy.deepcopy(merged),
            runner_result=copy.deepcopy(runner_result),
        )
        adapter = adapted.get("adapter_payload")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("message"), "runner ok")
        self.assertEqual(adapter.get("final_answer"), "runner done")
        self.assertEqual(adapter.get("runtime_mode"), "execute")
        self.assertEqual(adapter.get("execution_trace"), [{"runner": True}])
        self.assertEqual(adapter.get("last_result"), {"ok": True})

    def test_existing_adapter_payload_is_preserved_from_runner(self) -> None:
        from core.tasks.scheduler_core.repo_state_helpers import build_repo_runtime_state_adapter_payload

        merged: Dict[str, Any] = {
            "status": "running",
        }
        runner_result: Dict[str, Any] = {
            "ok": True,
            "adapter_payload": {
                "ok": True,
                "message": "already adapted",
            },
        }

        adapted = build_repo_runtime_state_adapter_payload(
            merged=copy.deepcopy(merged),
            runner_result=copy.deepcopy(runner_result),
        )

        self.assertEqual(adapted["adapter_payload"]["message"], "already adapted")


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    if not REPO_STATE_PATH.exists():
        raise FileNotFoundError(REPO_STATE_PATH)

    source = REPO_STATE_PATH.read_text(encoding="utf-8")

    if "def attach_repo_runtime_state_adapter_payload(payload: Any) -> Any:" not in source:
        marker = "\ndef extract_effective_status_and_answer(\n"
        if marker not in source:
            raise RuntimeError("repo_state_helpers insertion marker not found")
        source = source.replace(marker, HELPER_BLOCK + marker, 1)

    source = source.replace(
        '    _save_runtime_state_from_merged(scheduler, merged)\n',
        '    merged = build_repo_runtime_state_adapter_payload(merged=merged, runner_result=runner_result)\n'
        '    _save_runtime_state_from_merged(scheduler, merged)\n',
        1,
    )

    REPO_STATE_PATH.write_text(source, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[repo-runtime-state-adapter-v1] updated core/tasks/scheduler_core/repo_state_helpers.py")
    print("[repo-runtime-state-adapter-v1] created tests/test_repo_runtime_state_adapter_contract.py")


if __name__ == "__main__":
    main()