# core/system/command_dispatch.py
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from core.audit.review_audit import ReviewAuditLog
from core.audit.review_execution_link import ReviewExecutionLinkLog
from core.control.control_api import ZeroControlAPI


class CommandDispatch:
    """
    ZERO command semantic routing layer.

    This layer routes operator commands into platform-facing APIs
    and records governance evidence for review actions.
    """

    name = "command_dispatch"

    def __init__(
        self,
        control_api: Optional[ZeroControlAPI] = None,
        review_audit: Optional[ReviewAuditLog] = None,
        execution_link_log: Optional[ReviewExecutionLinkLog] = None,
        operator_id: str = "local_operator",
    ) -> None:
        self.control_api = control_api or ZeroControlAPI()
        self.review_audit = review_audit or ReviewAuditLog()
        self.execution_link_log = execution_link_log or ReviewExecutionLinkLog()
        self.operator_id = str(operator_id or "local_operator")

    def dispatch(self, command: Any) -> Dict[str, Any]:
        text = self._normalize_command(command)
        if not text:
            return self._result(
                ok=False,
                action="invalid",
                command="",
                error={
                    "type": "invalid_command",
                    "message": "command is empty",
                    "retryable": False,
                },
            )

        review_action = self._parse_review_command(text)
        if review_action:
            return self._dispatch_review_action(review_action, command=text)

        return self._result(
            ok=False,
            action="unsupported",
            command=text,
            error={
                "type": "unsupported_command",
                "message": f"unsupported command: {text}",
                "retryable": False,
            },
        )

    def run(self, command: Any) -> Dict[str, Any]:
        return self.dispatch(command)

    def execute(self, command: Any) -> Dict[str, Any]:
        return self.dispatch(command)

    def invoke(self, command: Any) -> Dict[str, Any]:
        return self.dispatch(command)

    def _dispatch_review_action(self, parsed: Dict[str, Any], *, command: str) -> Dict[str, Any]:
        action = parsed.get("action")
        item_id = parsed.get("item_id")

        try:
            if action == "get_review_queue":
                result = self.control_api.get_review_queue()
                ok = self._extract_ok(result)

                audit_event = self.review_audit.record_queue_read(
                    ok=ok,
                    operator_id=self.operator_id,
                    command=command,
                    result=result,
                    error=None if ok else self._extract_error(result),
                    metadata={
                        "source": self.name,
                    },
                )

                return self._result(
                    ok=ok,
                    action=action,
                    command=command,
                    result=result,
                    audit_event_id=audit_event.get("event_id"),
                )

            if action == "approve_review_item":
                result = self.control_api.approve_review_item(item_id)
                ok = self._extract_ok(result)
                error = None if ok else self._extract_error(result)

                audit_event = self.review_audit.record_approval(
                    item_id=str(item_id or ""),
                    ok=ok,
                    operator_id=self.operator_id,
                    command=command,
                    result=result,
                    error=error,
                    metadata={
                        "source": self.name,
                    },
                )

                link_event = self.execution_link_log.record_link(
                    review_item_id=str(item_id or ""),
                    decision="approved",
                    ok=ok,
                    operator_id=self.operator_id,
                    command=command,
                    result=result,
                    error=error,
                    execution_id=self._extract_first(result, "execution_id", "exec_id"),
                    mutation_id=self._extract_first(result, "mutation_id", "patch_id"),
                    rollback_id=self._extract_first(result, "rollback_id", "rollback_ref"),
                    trace_id=self._extract_first(result, "trace_id", "runtime_trace_id"),
                    applied_files=self._extract_applied_files(result),
                    metadata={
                        "source": self.name,
                        "audit_event_id": audit_event.get("event_id"),
                    },
                )

                return self._result(
                    ok=ok,
                    action=action,
                    command=command,
                    item_id=item_id,
                    result=result,
                    audit_event_id=audit_event.get("event_id"),
                    execution_link_id=link_event.get("link_id"),
                    error=error,
                )

            if action == "reject_review_item":
                result = self.control_api.reject_review_item(item_id)
                ok = self._extract_ok(result)
                error = None if ok else self._extract_error(result)

                audit_event = self.review_audit.record_rejection(
                    item_id=str(item_id or ""),
                    ok=ok,
                    operator_id=self.operator_id,
                    command=command,
                    result=result,
                    error=error,
                    metadata={
                        "source": self.name,
                    },
                )

                link_event = self.execution_link_log.record_link(
                    review_item_id=str(item_id or ""),
                    decision="rejected",
                    ok=ok,
                    operator_id=self.operator_id,
                    command=command,
                    result=result,
                    error=error,
                    execution_id=self._extract_first(result, "execution_id", "exec_id"),
                    mutation_id=self._extract_first(result, "mutation_id", "patch_id"),
                    rollback_id=self._extract_first(result, "rollback_id", "rollback_ref"),
                    trace_id=self._extract_first(result, "trace_id", "runtime_trace_id"),
                    applied_files=self._extract_applied_files(result),
                    metadata={
                        "source": self.name,
                        "audit_event_id": audit_event.get("event_id"),
                    },
                )

                return self._result(
                    ok=ok,
                    action=action,
                    command=command,
                    item_id=item_id,
                    result=result,
                    audit_event_id=audit_event.get("event_id"),
                    execution_link_id=link_event.get("link_id"),
                    error=error,
                )

            return self._result(
                ok=False,
                action="invalid_review_action",
                command=command,
                item_id=item_id,
                error={
                    "type": "invalid_review_action",
                    "message": f"unknown review action: {action}",
                    "retryable": False,
                },
            )

        except Exception as exc:
            return self._result(
                ok=False,
                action=str(action or "review_action"),
                command=command,
                item_id=item_id,
                error={
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                    "retryable": False,
                },
            )

    def _parse_review_command(self, text: str) -> Optional[Dict[str, Any]]:
        normalized = self._compact_spaces(text).lower()

        if normalized in {
            "review",
            "reviews",
            "list review",
            "list reviews",
            "review list",
            "review queue",
            "reviews queue",
            "get review queue",
            "show review queue",
            "show reviews",
            "get reviews",
        }:
            return {
                "action": "get_review_queue",
                "item_id": None,
            }

        approve_match = re.match(
            r"^(?:approve|approved|accept|accepted)\s+(?:review\s+)?(?P<item_id>[A-Za-z0-9_.:\-]+)$",
            normalized,
        )
        if approve_match:
            return {
                "action": "approve_review_item",
                "item_id": approve_match.group("item_id"),
            }

        reject_match = re.match(
            r"^(?:reject|rejected|deny|denied|decline|declined)\s+(?:review\s+)?(?P<item_id>[A-Za-z0-9_.:\-]+)$",
            normalized,
        )
        if reject_match:
            return {
                "action": "reject_review_item",
                "item_id": reject_match.group("item_id"),
            }

        approve_review_match = re.match(
            r"^review\s+(?:approve|accept)\s+(?P<item_id>[A-Za-z0-9_.:\-]+)$",
            normalized,
        )
        if approve_review_match:
            return {
                "action": "approve_review_item",
                "item_id": approve_review_match.group("item_id"),
            }

        reject_review_match = re.match(
            r"^review\s+(?:reject|deny|decline)\s+(?P<item_id>[A-Za-z0-9_.:\-]+)$",
            normalized,
        )
        if reject_review_match:
            return {
                "action": "reject_review_item",
                "item_id": reject_review_match.group("item_id"),
            }

        return None

    def _normalize_command(self, command: Any) -> str:
        if isinstance(command, dict):
            for key in ("command", "command_text", "text", "input", "query"):
                value = command.get(key)
                if value is not None:
                    return self._compact_spaces(str(value))
            return ""

        return self._compact_spaces(str(command or ""))

    def _compact_spaces(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _extract_ok(self, result: Any) -> bool:
        if isinstance(result, dict):
            if "ok" in result:
                return bool(result.get("ok"))
            if "success" in result:
                return bool(result.get("success"))
            if result.get("error"):
                return False
        return True

    def _extract_error(self, result: Any) -> Any:
        if isinstance(result, dict):
            return result.get("error")
        return None

    def _extract_first(self, value: Any, *keys: str) -> Optional[str]:
        found = self._find_first_recursive(value, set(keys))
        if found is None:
            return None
        return str(found)

    def _find_first_recursive(self, value: Any, keys: set[str]) -> Any:
        if isinstance(value, dict):
            for key in keys:
                if key in value and value[key] is not None:
                    return value[key]
            for child in value.values():
                found = self._find_first_recursive(child, keys)
                if found is not None:
                    return found

        if isinstance(value, list):
            for child in value:
                found = self._find_first_recursive(child, keys)
                if found is not None:
                    return found

        return None

    def _extract_applied_files(self, result: Any) -> list[str]:
        value = self._find_first_recursive(
            result,
            {
                "applied_files",
                "changed_files",
                "files",
                "touched_files",
            },
        )

        if value is None:
            return []

        if isinstance(value, list):
            return [str(item) for item in value]

        if isinstance(value, tuple):
            return [str(item) for item in value]

        if isinstance(value, str):
            return [value]

        return [repr(value)]

    def _result(
        self,
        *,
        ok: bool,
        action: str,
        command: Optional[str] = None,
        item_id: Optional[str] = None,
        result: Any = None,
        audit_event_id: Optional[str] = None,
        execution_link_id: Optional[str] = None,
        error: Optional[Any] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": bool(ok),
            "tool": self.name,
            "action": action,
        }

        if command is not None:
            payload["command"] = command

        if item_id is not None:
            payload["item_id"] = item_id

        if result is not None:
            payload["result"] = result

        if audit_event_id is not None:
            payload["audit_event_id"] = audit_event_id

        if execution_link_id is not None:
            payload["execution_link_id"] = execution_link_id

        payload["error"] = error

        return payload


def dispatch_command(command: Any, control_api: Optional[ZeroControlAPI] = None) -> Dict[str, Any]:
    return CommandDispatch(control_api=control_api).dispatch(command)