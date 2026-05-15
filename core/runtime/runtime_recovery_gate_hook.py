from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from core.runtime.runtime_recovery_approval import approve_runtime_recovery_plan
from core.runtime.runtime_recovery_commit_gate import gate_runtime_recovery_commit
from core.runtime.runtime_recovery_dry_run_executor import dry_run_runtime_recovery
from core.runtime.runtime_recovery_execution_contract import (
    build_runtime_recovery_execution_contract,
)


def runtime_recovery_gate_hook(
    context: dict[str, Any],
    *,
    manual_confirmation_provided: bool = False,
) -> dict[str, Any]:
    """
    Governed repair gate hook adapter.

    This adapter is intentionally thin:
    - it receives the governed repair gate context
    - builds recovery execution contract evidence
    - runs approval / dry-run / commit gate checks
    - returns a normalized allow/block result

    It does not apply files, execute mutations, or import command dispatch.
    """

    source = _source_from_context(context)

    contract_report = build_runtime_recovery_execution_contract(source)
    approval_report = approve_runtime_recovery_plan(source)
    dry_run_report = dry_run_runtime_recovery(source)
    commit_report = gate_runtime_recovery_commit(
        source,
        manual_confirmation_provided=manual_confirmation_provided,
    )

    reports = {
        "contract": _to_plain(contract_report),
        "approval": _to_plain(approval_report),
        "dry_run": _to_plain(dry_run_report),
        "commit": _to_plain(commit_report),
    }

    blockers = _collect_blockers(reports)

    if blockers:
        return {
            "ok": False,
            "blocked": True,
            "error": "runtime_recovery_gate_blocked",
            "blockers": blockers,
            "reports": reports,
        }

    return {
        "ok": True,
        "blocked": False,
        "reports": reports,
    }


def _source_from_context(context: dict[str, Any]) -> Any:
    if not isinstance(context, dict):
        return context

    for key in ("recovery", "recovery_plan", "plan", "transaction"):
        value = context.get(key)
        if value is not None:
            return value

    return context


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _collect_blockers(reports: dict[str, Any]) -> list[str]:
    blockers: list[str] = []

    for name, report in reports.items():
        if not isinstance(report, dict):
            continue

        if report.get("ok") is False:
            blockers.append(f"{name}: ok=false")

        if report.get("blocked") is True:
            blockers.append(f"{name}: blocked=true")

        if report.get("approved") is False:
            blockers.append(f"{name}: approved=false")

        if report.get("authorized") is False:
            blockers.append(f"{name}: authorized=false")

        if report.get("ready") is False:
            blockers.append(f"{name}: ready=false")

        status = str(report.get("status") or "").lower()
        if status in {"blocked", "rejected", "failed", "unsafe"}:
            blockers.append(f"{name}: status={status}")

        for key in ("blockers", "errors", "issues", "reasons"):
            values = report.get(key)
            if isinstance(values, list):
                blockers.extend(f"{name}: {item}" for item in values if item)
            elif values:
                blockers.append(f"{name}: {values}")

    return blockers
