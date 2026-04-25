from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.capabilities.capability_registry import get_operation, has_capability, has_operation


OPERATION_TO_REGISTRY_OPERATION: Dict[str, str] = {
    "summary": "run_summary",
    "action_items": "run_action_items",
    "summary_and_action_items": "run_summary_and_action_items",
}


@dataclass(frozen=True)
class CapabilityResolution:
    ok: bool
    capability: str
    operation: str
    registry_operation: str
    reason: str
    callable_ref: Optional[Callable] = None

    @property
    def callable_available(self) -> bool:
        return callable(self.callable_ref)

    def to_dict(self, include_callable: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": self.ok,
            "capability": self.capability,
            "operation": self.operation,
            "registry_operation": self.registry_operation,
            "reason": self.reason,
            "callable_available": self.callable_available,
        }

        if include_callable:
            payload["callable_ref"] = self.callable_ref

        return payload


def normalize_capability_route(route: Any) -> Dict[str, Any]:
    if not isinstance(route, dict):
        return {}

    capability = str(route.get("capability") or "").strip()
    operation = str(route.get("operation") or "").strip()
    registry_operation = ""

    registry_hint = route.get("capability_registry_hint")
    if isinstance(registry_hint, dict):
        capability = str(registry_hint.get("capability") or capability).strip()
        operation = str(registry_hint.get("operation") or operation).strip()
        registry_operation = str(registry_hint.get("registry_operation") or "").strip()

    capability_hint = route.get("capability_hint")
    if isinstance(capability_hint, dict):
        capability = str(capability_hint.get("capability") or capability).strip()
        operation = str(capability_hint.get("operation") or operation).strip()

    if not registry_operation:
        registry_operation = OPERATION_TO_REGISTRY_OPERATION.get(operation, "")

    return {
        "capability": capability,
        "operation": operation,
        "registry_operation": registry_operation,
    }


def resolve_capability_from_route(route: Any) -> CapabilityResolution:
    normalized = normalize_capability_route(route)

    capability = str(normalized.get("capability") or "").strip()
    operation = str(normalized.get("operation") or "").strip()
    registry_operation = str(normalized.get("registry_operation") or "").strip()

    if not capability:
        return CapabilityResolution(
            ok=False,
            capability="",
            operation=operation,
            registry_operation=registry_operation,
            reason="missing_capability",
            callable_ref=None,
        )

    if not has_capability(capability):
        return CapabilityResolution(
            ok=False,
            capability=capability,
            operation=operation,
            registry_operation=registry_operation,
            reason="capability_not_registered",
            callable_ref=None,
        )

    if not operation:
        return CapabilityResolution(
            ok=False,
            capability=capability,
            operation="",
            registry_operation=registry_operation,
            reason="missing_operation",
            callable_ref=None,
        )

    if not registry_operation:
        return CapabilityResolution(
            ok=False,
            capability=capability,
            operation=operation,
            registry_operation="",
            reason="operation_not_mapped",
            callable_ref=None,
        )

    if not has_operation(capability, registry_operation):
        return CapabilityResolution(
            ok=False,
            capability=capability,
            operation=operation,
            registry_operation=registry_operation,
            reason="operation_not_registered",
            callable_ref=None,
        )

    callable_ref = get_operation(capability, registry_operation)
    if not callable(callable_ref):
        return CapabilityResolution(
            ok=False,
            capability=capability,
            operation=operation,
            registry_operation=registry_operation,
            reason="callable_missing",
            callable_ref=None,
        )

    return CapabilityResolution(
        ok=True,
        capability=capability,
        operation=operation,
        registry_operation=registry_operation,
        reason="resolved",
        callable_ref=callable_ref,
    )


def can_resolve_capability(route: Any) -> bool:
    return resolve_capability_from_route(route).ok


def describe_capability_resolution(route: Any) -> Dict[str, Any]:
    return resolve_capability_from_route(route).to_dict(include_callable=False)


def main() -> int:
    sample_route = {
        "capability": "document_flow",
        "operation": "summary_and_action_items",
        "capability_registry_hint": {
            "capability": "document_flow",
            "operation": "summary_and_action_items",
            "registry_operation": "run_summary_and_action_items",
            "capability_registered": True,
            "operation_registered": True,
        },
    }

    resolution = resolve_capability_from_route(sample_route)
    print("[capability-invoker] sample resolution")
    for key, value in resolution.to_dict(include_callable=False).items():
        print(f"{key}: {value}")

    if not resolution.ok:
        print("[capability-invoker] FAIL")
        return 1

    if resolution.capability != "document_flow":
        print("[capability-invoker] FAIL: wrong capability")
        return 1

    if resolution.registry_operation != "run_summary_and_action_items":
        print("[capability-invoker] FAIL: wrong registry operation")
        return 1

    if not resolution.callable_available:
        print("[capability-invoker] FAIL: callable unavailable")
        return 1

    print("[capability-invoker] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())