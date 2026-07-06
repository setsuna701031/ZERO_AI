from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


RUNTIME_OPERATOR_PACKAGE_DISPATCH_BRIDGE_SCHEMA = (
    "zero.runtime.operator_package_dispatch_bridge.v1"
)


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _changes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


class RuntimeOperatorPackageDispatchBridge:
    safe_runtime_operator_package_dispatch_bridge: bool = True

    def prepare(self, package: Mapping[str, Any]) -> dict[str, Any]:
        authority_context = _mapping(package.get("authority_context"))
        requested_changes = _changes(package.get("requested_changes"))
        goal = _text(package.get("goal")) or _text(package.get("package_id"))

        return {
            "schema": RUNTIME_OPERATOR_PACKAGE_DISPATCH_BRIDGE_SCHEMA,
            "package_dispatch_bound": True,
            "dispatch_mode": "runtime_package",
            "goal": goal,
            "package_id": _text(package.get("package_id")),
            "task_id": _text(package.get("task_id")),
            "requested_mode": _text(package.get("requested_mode")),
            "target_root": package.get("target_root"),
            "authority_context": authority_context,
            "requested_changes": requested_changes,
            "non_mainline_issues": [],
        }


def prepare_runtime_operator_package_dispatch(
    package: Mapping[str, Any],
) -> dict[str, Any]:
    return RuntimeOperatorPackageDispatchBridge().prepare(package)


__all__ = [
    "RUNTIME_OPERATOR_PACKAGE_DISPATCH_BRIDGE_SCHEMA",
    "RuntimeOperatorPackageDispatchBridge",
    "prepare_runtime_operator_package_dispatch",
]
