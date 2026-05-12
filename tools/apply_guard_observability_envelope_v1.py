from __future__ import annotations

from pathlib import Path


GUARD_PATH = Path("core/tasks/execution_guard.py")
TEST_PATH = Path("tests/test_guard_observability_envelope_contract.py")


OLD_ALLOW_DENY = '''    def _allow(self, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ok": True}
        payload.update(extra)
        return payload

    def _deny(self, error: str, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "error": str(error or "blocked by execution guard"),
        }
        payload.update(extra)
        return payload
'''


NEW_ALLOW_DENY = '''    def _allow(self, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ok": True}
        payload.update(extra)
        return self._attach_guard_observability_event(payload)

    def _deny(self, error: str, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "error": str(error or "blocked by execution guard"),
        }
        payload.update(extra)
        return self._attach_guard_observability_event(payload)

    def _attach_guard_observability_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload

        if isinstance(payload.get("observability_event"), dict):
            return payload

        ok = bool(payload.get("ok", False))
        guard_mode = str(payload.get("guard_mode") or ("allowed" if ok else "blocked"))
        policy_action = str(payload.get("policy_action") or ("allow" if ok else "deny"))
        policy_reason = str(payload.get("policy_reason") or payload.get("error") or "")

        event = {
            "event_type": "execution_guard",
            "ok": ok,
            "guard_mode": guard_mode,
            "policy_action": policy_action,
            "policy_reason": policy_reason,
            "error_text": "" if ok else str(payload.get("error") or ""),
            "runtime_mode": str(payload.get("runtime_mode") or "guard"),
        }

        payload["observability_event"] = event

        if "adapter_payload" not in payload:
            payload["adapter_payload"] = {
                "ok": ok,
                "message": policy_reason or ("guard allowed" if ok else "guard blocked"),
                "final_answer": policy_reason or ("guard allowed" if ok else "guard blocked"),
                "text": policy_reason or ("guard allowed" if ok else "guard blocked"),
                "error_text": "" if ok else str(payload.get("error") or policy_reason or ""),
                "error_type": "" if ok else guard_mode,
                "runtime_mode": "guard",
                "last_result": {},
                "execution_trace": [event],
                "raw": dict(payload),
            }

        return payload
'''


TEST_CONTENT = r'''from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GuardObservabilityEnvelopeContractTest(unittest.TestCase):
    def test_allow_result_gets_observability_event(self) -> None:
        from core.tasks.execution_guard import ExecutionGuard

        with tempfile.TemporaryDirectory() as tmp:
            guard = ExecutionGuard(project_root=tmp)
            result = guard._allow(
                guard_mode="workspace_read",
                policy_action="allow",
                policy_reason="path allowed",
            )

        event = result.get("observability_event")
        adapter = result.get("adapter_payload")

        self.assertIsInstance(event, dict)
        self.assertIs(event.get("ok"), True)
        self.assertEqual(event.get("event_type"), "execution_guard")
        self.assertEqual(event.get("guard_mode"), "workspace_read")
        self.assertEqual(event.get("policy_action"), "allow")
        self.assertEqual(event.get("policy_reason"), "path allowed")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("runtime_mode"), "guard")
        self.assertIsInstance(adapter.get("execution_trace"), list)

    def test_deny_result_gets_observability_event_and_error_payload(self) -> None:
        from core.tasks.execution_guard import ExecutionGuard

        with tempfile.TemporaryDirectory() as tmp:
            guard = ExecutionGuard(project_root=tmp)
            result = guard._deny(
                "blocked path",
                guard_mode="path_outside_workspace",
                policy_action="deny",
                policy_reason="path outside workspace",
            )

        event = result.get("observability_event")
        adapter = result.get("adapter_payload")

        self.assertIsInstance(event, dict)
        self.assertIs(event.get("ok"), False)
        self.assertEqual(event.get("event_type"), "execution_guard")
        self.assertEqual(event.get("guard_mode"), "path_outside_workspace")
        self.assertEqual(event.get("policy_action"), "deny")
        self.assertEqual(event.get("policy_reason"), "path outside workspace")
        self.assertEqual(event.get("error_text"), "blocked path")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), False)
        self.assertEqual(adapter.get("error_type"), "path_outside_workspace")
        self.assertEqual(adapter.get("error_text"), "blocked path")
        self.assertEqual(adapter.get("runtime_mode"), "guard")

    def test_existing_observability_event_is_preserved(self) -> None:
        from core.tasks.execution_guard import ExecutionGuard

        with tempfile.TemporaryDirectory() as tmp:
            guard = ExecutionGuard(project_root=tmp)
            payload = {
                "ok": True,
                "observability_event": {
                    "event_type": "custom",
                    "ok": True,
                },
            }
            result = guard._attach_guard_observability_event(payload)

        self.assertIs(result, payload)
        self.assertEqual(result["observability_event"]["event_type"], "custom")


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    if not GUARD_PATH.exists():
        raise FileNotFoundError(GUARD_PATH)

    source = GUARD_PATH.read_text(encoding="utf-8")

    if "_attach_guard_observability_event" not in source:
        if OLD_ALLOW_DENY not in source:
            raise RuntimeError("ExecutionGuard _allow/_deny block not found")
        source = source.replace(OLD_ALLOW_DENY, NEW_ALLOW_DENY, 1)

    GUARD_PATH.write_text(source, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[guard-observability-envelope-v1] updated core/tasks/execution_guard.py")
    print("[guard-observability-envelope-v1] created tests/test_guard_observability_envelope_contract.py")


if __name__ == "__main__":
    main()