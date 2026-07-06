from __future__ import annotations

import py_compile
from pathlib import Path


BRIDGE = '''from __future__ import annotations

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
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, got {count}")
    return text.replace(old, new, 1)


def main() -> None:
    root = Path.cwd()
    bridge_path = root / "core" / "runtime" / "runtime_operator_package_dispatch_bridge.py"
    service_path = root / "core" / "runtime" / "runtime_operator_service.py"
    console_path = root / "cli" / "zero_operator_console.py"

    bridge_path.write_text(BRIDGE, encoding="utf-8")

    service = service_path.read_text(encoding="utf-8")
    import_old = '''from core.runtime.runtime_operator_config import (
    RuntimeOperatorConfig,
    load_runtime_operator_config,
)
'''
    import_new = import_old + '''from core.runtime.runtime_operator_package_dispatch_bridge import (
    prepare_runtime_operator_package_dispatch,
)
'''
    if "prepare_runtime_operator_package_dispatch" not in service:
        service = replace_once(service, import_old, import_new, "service import")

    run_goal_old = '''    def run_goal(
        self,
        goal_text: Any,
        *,
        explicit_manual_mode: bool = False,
    ) -> dict[str, Any]:
        result = launch_goal_session(
            goal_text,
            self.config,
            explicit_manual_mode=explicit_manual_mode,
            emergency_stop_active=self._state.get("emergency_stop_active") is True,
        )
'''
    run_goal_new = '''    def run_goal(
        self,
        goal_text: Any,
        *,
        runtime_package: Mapping[str, Any] | None = None,
        explicit_manual_mode: bool = False,
    ) -> dict[str, Any]:
        result = launch_goal_session(
            goal_text,
            self.config,
            explicit_manual_mode=explicit_manual_mode,
            emergency_stop_active=self._state.get("emergency_stop_active") is True,
        )
        package_dispatch = _mapping(runtime_package)
        if package_dispatch:
            result = dict(result)
            result["package"] = package_dispatch
            result["package_dispatch_bound"] = True
            result["package_dispatch_schema"] = package_dispatch.get("schema", "")
            result["package_id"] = package_dispatch.get("package_id", "")
            result["task_id"] = package_dispatch.get("task_id", "")
'''
    if "runtime_package: Mapping[str, Any] | None = None" not in service:
        service = replace_once(service, run_goal_old, run_goal_new, "service run_goal")

    return_old = '''            "action": "run",
            "goal_id": result.get("goal_id") or "",
'''
    return_new = '''            "action": "run",
            "package_dispatch_bound": result.get("package_dispatch_bound") is True,
            "package_dispatch_schema": result.get("package_dispatch_schema") or "",
            "package_id": result.get("package_id") or "",
            "task_id": result.get("task_id") or "",
            "goal_id": result.get("goal_id") or "",
'''
    if '"package_dispatch_bound": result.get("package_dispatch_bound") is True' not in service:
        service = replace_once(service, return_old, return_new, "service return package fields")

    run_package_method = '''    def run_package(
        self,
        package: Mapping[str, Any],
        *,
        explicit_manual_mode: bool = False,
    ) -> dict[str, Any]:
        dispatch = prepare_runtime_operator_package_dispatch(package)
        return self.run_goal(
            dispatch.get("goal") or package.get("goal") or package.get("package_id"),
            runtime_package=dispatch,
            explicit_manual_mode=explicit_manual_mode,
        )

'''
    if "    def run_package(" not in service:
        service = replace_once(
            service,
            "    def queue_status(self) -> dict[str, Any]:\n",
            run_package_method + "    def queue_status(self) -> dict[str, Any]:\n",
            "service run_package method",
        )
    service_path.write_text(service, encoding="utf-8")

    console = console_path.read_text(encoding="utf-8")
    status_old = '''        "task_id": _text(package.get("task_id")),
        "requested_mode": _text(package.get("requested_mode")),
'''
    status_new = '''        "task_id": _text(package.get("task_id")),
        "package_dispatch_bound": bool(result.get("package_dispatch_bound") is True),
        "package_dispatch_schema": _text(result.get("package_dispatch_schema")),
        "requested_mode": _text(package.get("requested_mode")),
'''
    if '"package_dispatch_bound": bool(result.get("package_dispatch_bound") is True)' not in console:
        console = replace_once(console, status_old, status_new, "console status package fields")

    run_old = '''    service = RuntimeOperatorService(_config(package), **adapters)
    return service.run_goal(_goal(package), explicit_manual_mode=True)
'''
    run_new = '''    service = RuntimeOperatorService(_config(package), **adapters)
    return service.run_package(package, explicit_manual_mode=True)
'''
    if "return service.run_package(package, explicit_manual_mode=True)" not in console:
        console = replace_once(console, run_old, run_new, "console run service")
    console_path.write_text(console, encoding="utf-8")

    for path in (bridge_path, service_path, console_path):
        py_compile.compile(str(path), doraise=True)

    print("runtime operator package dispatch bridge applied")


if __name__ == "__main__":
    main()
