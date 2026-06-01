from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


SUMMARY_LIMIT = 240


def code_chain_repair_evidence_path(*, repo_root: Path, task_id: str) -> Path:
    """Return the exported repair-result evidence path for a task.

    This mirrors the exporter path convention without importing execution code.
    """
    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "code_chain_task"
    return (
        root
        / "workspace"
        / "evidence"
        / "code_chain_repair"
        / f"{safe_task_id}_repair_result_report.json"
    )


def load_code_chain_repair_evidence(*, repo_root: Path, task_id: str) -> dict[str, Any]:
    """Read an exported Code Chain repair evidence JSON document.

    Presentation is intentionally read-only: this function only opens the
    existing report path and returns a decoded mapping, or an empty mapping when
    the report is unavailable or malformed.
    """
    evidence_path = code_chain_repair_evidence_path(repo_root=repo_root, task_id=task_id)
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(data) if isinstance(data, Mapping) else {}


def format_code_chain_repair_evidence(report: Any, *, evidence_path: Any = "") -> str:
    """Render exported Code Chain repair evidence for CLI/status display."""
    safe = report if isinstance(report, Mapping) else {}
    resolved_evidence_path = _first_text(
        evidence_path,
        safe.get("evidence_path"),
        safe.get("artifact_path"),
    )

    lines = [
        "Code Chain Repair Evidence:",
        f"- final_status: {_display(safe.get('final_status'))}",
        f"- original_failure: {_display(_original_failure_summary(safe.get('original_failure')))}",
        f"- attempt_count: {_display(safe.get('attempt_count'))}",
        f"- attempt_1_failed_reason: {_display(_first_attempt_failed_reason(safe))}",
        f"- repair_attempted: {_bool_text(safe.get('repair_attempted'))}",
        f"- repair_succeeded: {_bool_text(safe.get('repair_succeeded'))}",
        f"- verification_result: {_display(_verification_result(safe))}",
        f"- evidence_path: {_display(resolved_evidence_path, max_len=500)}",
    ]
    return "\n".join(lines)


def format_code_chain_repair_evidence_for_task(*, repo_root: Path, task_id: str) -> str:
    """Read and render the exported repair evidence for a task id."""
    evidence_path = code_chain_repair_evidence_path(repo_root=repo_root, task_id=task_id)
    report = load_code_chain_repair_evidence(repo_root=repo_root, task_id=task_id)
    return format_code_chain_repair_evidence(report, evidence_path=str(evidence_path))


def _original_failure_summary(value: Any) -> str:
    if not isinstance(value, Mapping):
        return _compact_text(value)

    text = _first_text(
        value.get("message"),
        value.get("final_answer"),
        value.get("error"),
        value.get("failure_reason"),
        value.get("reason"),
    )
    if text:
        return _compact_text(text)

    parts = []
    for key in ("ok", "status", "type", "exit_code"):
        field = _safe_text(value.get(key))
        if field:
            parts.append(f"{key}={field}")
    return _compact_text("; ".join(parts))


def _first_attempt_failed_reason(report: Mapping[str, Any]) -> str:
    attempts = report.get("attempt_history")
    if not isinstance(attempts, list) or not attempts:
        return _original_failure_summary(report.get("original_failure"))

    first = attempts[0]
    if not isinstance(first, Mapping):
        return _original_failure_summary(report.get("original_failure"))

    failed = first.get("ok") is False
    reason = _first_text(
        first.get("failure_reason"),
        first.get("message"),
        _original_failure_summary(report.get("original_failure")),
    )
    if failed:
        return reason
    return ""


def _verification_result(report: Mapping[str, Any]) -> str:
    history = report.get("verification_history")
    if not isinstance(history, list) or not history:
        return "not recorded"

    latest = next((item for item in reversed(history) if isinstance(item, Mapping)), None)
    if latest is None:
        return "not recorded"

    status = "passed" if latest.get("ok") is True else "failed"
    details = []
    attempt_index = _safe_text(latest.get("attempt_index"))
    attempt_kind = _safe_text(latest.get("attempt_kind"))
    command = _safe_text(latest.get("verification_command"))
    failure_reason = _safe_text(latest.get("failure_reason"))

    if attempt_index:
        details.append(f"attempt #{attempt_index}")
    if attempt_kind:
        details.append(attempt_kind)
    if command:
        details.append(command)
    if failure_reason:
        details.append(failure_reason)

    if not details:
        return status
    return _compact_text(f"{status} ({'; '.join(details)})")


def _bool_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return _display(value)


def _display(value: Any, max_len: int = SUMMARY_LIMIT) -> str:
    text = _compact_text(value, max_len=max_len)
    return text if text else "<none>"


def _compact_text(value: Any, *, max_len: int = SUMMARY_LIMIT) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _first_text(*values: Any) -> str:
    for value in values:
        text = _safe_text(value)
        if text:
            return text
    return ""


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._-")[:120]
