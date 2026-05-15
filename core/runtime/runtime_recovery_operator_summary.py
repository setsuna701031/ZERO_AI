from __future__ import annotations

from typing import Any


def build_runtime_recovery_operator_summary(gate_result: Any) -> dict[str, Any]:
    if not isinstance(gate_result, dict):
        return {
            "ok": False,
            "status": "invalid_gate_result",
            "summary": "Recovery gate returned a non-dict result.",
            "blockers": ["invalid gate result"],
            "readiness": "blocked",
        }

    ok = bool(gate_result.get("ok", False))
    blocked = bool(gate_result.get("blocked", not ok))
    blockers = _normalize_list(gate_result.get("blockers"))

    reports = gate_result.get("reports")
    reports = reports if isinstance(reports, dict) else {}

    contract = _report_status(reports.get("contract"))
    approval = _report_status(reports.get("approval"))
    dry_run = _report_status(reports.get("dry_run"))
    commit = _report_status(reports.get("commit"))

    readiness = "ready" if ok and not blocked and not blockers else "blocked"

    return {
        "ok": ok and not blocked and not blockers,
        "status": "ready" if readiness == "ready" else "blocked",
        "summary": _summary_text(readiness, blockers),
        "readiness": readiness,
        "blockers": blockers,
        "reports": {
            "contract": contract,
            "approval": approval,
            "dry_run": dry_run,
            "commit": commit,
        },
    }


def _report_status(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "present": False,
            "ok": None,
            "status": "missing",
            "summary": "",
        }

    ok = report.get("ok")
    status = str(
        report.get("status")
        or report.get("decision")
        or report.get("state")
        or ""
    ).strip()

    if not status:
        if report.get("blocked") is True:
            status = "blocked"
        elif report.get("approved") is False:
            status = "rejected"
        elif report.get("authorized") is False:
            status = "unauthorized"
        elif ok is True:
            status = "ok"
        elif ok is False:
            status = "failed"
        else:
            status = "present"

    return {
        "present": True,
        "ok": ok,
        "status": status,
        "summary": str(
            report.get("summary")
            or report.get("reason")
            or report.get("message")
            or ""
        ),
    }


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _summary_text(readiness: str, blockers: list[str]) -> str:
    if readiness == "ready":
        return "Recovery gate passed. Runtime repair execution is ready to continue."
    if blockers:
        return "Recovery gate blocked runtime repair execution: " + "; ".join(blockers)
    return "Recovery gate blocked runtime repair execution."
