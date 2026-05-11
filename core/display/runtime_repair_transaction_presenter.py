from __future__ import annotations

from typing import Any, Dict, List, Mapping


SUMMARY_LIMIT = 240


def format_runtime_repair_transaction(transaction: Any) -> str:
    """Render a deterministic runtime repair transaction preview.

    This presenter is display-only.
    It does not mutate runtime state, execute tools, write files,
    schedule tasks, or apply patches.
    """
    safe = transaction if isinstance(transaction, Mapping) else {}

    lines: List[str] = [
        "Runtime Repair Transaction:",
    ]

    _append(lines, "transaction_id", safe.get("transaction_id"))
    _append(lines, "task_id", safe.get("task_id"))
    _append(lines, "proposal_id", safe.get("proposal_id"))
    _append(lines, "state", safe.get("state"))
    _append(lines, "goal", safe.get("goal"))
    _append(lines, "summary", safe.get("summary"))

    scope_gate = safe.get("scope_gate")
    if isinstance(scope_gate, Mapping):
        lines.append("  - scope_gate:")
        _append(lines, "scope_status", scope_gate.get("scope_status"), indent="      ")
        _append(lines, "scope_allowed", scope_gate.get("scope_allowed"), indent="      ")
        _append(lines, "allowed_next_action", scope_gate.get("allowed_next_action"), indent="      ")

        blocked_reasons = _safe_list(scope_gate.get("blocked_reasons"))
        if blocked_reasons:
            lines.append("      - blocked_reasons:")
            for item in blocked_reasons:
                lines.append(f"          - {item}")

    risk_level = classify_runtime_repair_transaction_risk(safe)
    lines.append(f"  - risk_level: {risk_level}")

    lines.append(f"  - commit_ready: {_bool_text(is_runtime_repair_transaction_commit_ready(safe))}")
    lines.append(f"  - rollback_ready: {_bool_text(is_runtime_repair_transaction_rollback_ready(safe))}")

    staged_mutations = _safe_list_of_dicts(safe.get("staged_mutations"))
    committed_mutations = _safe_list_of_dicts(safe.get("committed_mutations"))
    rolled_back_mutations = _safe_list_of_dicts(safe.get("rolled_back_mutations"))

    _append_mutation_group(
        lines,
        "staged_mutations",
        staged_mutations,
    )

    _append_mutation_group(
        lines,
        "committed_mutations",
        committed_mutations,
    )

    _append_mutation_group(
        lines,
        "rolled_back_mutations",
        rolled_back_mutations,
    )

    audit_events = _safe_list_of_dicts(safe.get("audit_events"))
    if audit_events:
        lines.append("  - audit_events:")
        for event in audit_events[-5:]:
            event_type = _safe_text(event.get("event_type"))
            status = _safe_text(event.get("status"))
            summary = _compact_text(event.get("summary"))

            lines.append(
                f"      - {event_type} [{status}] {summary}"
            )

    snapshot_artifacts = _safe_list_of_dicts(safe.get("snapshot_artifacts"))
    if snapshot_artifacts:
        lines.append("  - snapshot_artifacts:")
        for artifact in snapshot_artifacts:
            artifact_id = _safe_text(artifact.get("artifact_id"))
            artifact_type = _safe_text(artifact.get("artifact_type"))
            lines.append(
                f"      - {artifact_type}: {artifact_id}"
            )

    return "\n".join(lines)


def classify_runtime_repair_transaction_risk(transaction: Any) -> str:
    safe = transaction if isinstance(transaction, Mapping) else {}

    scope_gate = safe.get("scope_gate")
    if isinstance(scope_gate, Mapping):
        if not bool(scope_gate.get("scope_allowed", True)):
            return "critical"

    staged = _safe_list_of_dicts(safe.get("staged_mutations"))

    if not staged:
        return "low"

    risky_actions = {
        "delete_file",
        "run_shell_command",
        "modify_scheduler",
        "modify_planner",
    }

    medium_actions = {
        "write_file",
        "apply_patch",
    }

    has_medium = False

    for mutation in staged:
        action = _safe_text(mutation.get("action")).lower()

        if action in risky_actions:
            return "high"

        if action in medium_actions:
            has_medium = True

        target = _safe_text(mutation.get("target_path")).lower()

        if any(
            keyword in target
            for keyword in (
                "scheduler.py",
                "agent_loop.py",
                "system_boot.py",
            )
        ):
            return "high"

    if has_medium:
        return "medium"

    return "low"


def is_runtime_repair_transaction_commit_ready(transaction: Any) -> bool:
    safe = transaction if isinstance(transaction, Mapping) else {}

    state = _safe_text(safe.get("state")).lower()
    if state not in {
        "created",
        "staged",
    }:
        return False

    staged = _safe_list_of_dicts(safe.get("staged_mutations"))
    if not staged:
        return False

    scope_gate = safe.get("scope_gate")
    if isinstance(scope_gate, Mapping):
        if not bool(scope_gate.get("scope_allowed", True)):
            return False

    return True


def is_runtime_repair_transaction_rollback_ready(transaction: Any) -> bool:
    safe = transaction if isinstance(transaction, Mapping) else {}

    state = _safe_text(safe.get("state")).lower()

    return state in {
        "staged",
        "committed",
        "failed",
        "blocked",
    }


def _append_mutation_group(
    lines: List[str],
    label: str,
    mutations: List[Dict[str, Any]],
) -> None:
    if not mutations:
        return

    lines.append(f"  - {label}:")

    for mutation in mutations:
        mutation_id = _safe_text(mutation.get("mutation_id"))
        action = _safe_text(mutation.get("action"))
        target_path = _safe_text(mutation.get("target_path"))
        content_hash = _safe_text(mutation.get("content_hash"))

        lines.append(
            f"      - [{action}] {target_path}"
        )

        if mutation_id:
            lines.append(f"          mutation_id: {mutation_id}")

        if content_hash:
            lines.append(f"          content_hash: {content_hash[:12]}")


def _append(
    lines: List[str],
    key: str,
    value: Any,
    *,
    indent: str = "  ",
) -> None:
    text = _compact_text(value)

    if text:
        lines.append(f"{indent}- {key}: {text}")


def _bool_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"

    text = _safe_text(value)
    return text if text else "false"


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _compact_text(value: Any, max_len: int = SUMMARY_LIMIT) -> str:
    text = _safe_text(value)

    if not text:
        return ""

    text = " ".join(text.split())

    if len(text) <= max_len:
        return text

    return text[: max_len - 3].rstrip() + "..."


def _safe_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []

    result: List[str] = []

    for item in value:
        text = _safe_text(item)

        if text:
            result.append(text)

    return result


def _safe_list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    result: List[Dict[str, Any]] = []

    for item in value:
        if isinstance(item, Mapping):
            result.append(dict(item))

    return result