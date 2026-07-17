from __future__ import annotations

import copy
from typing import Any, Dict, Mapping

from core.runtime.aer_operator_checkpoint import validate_operator_checkpoint
from core.runtime.aer_operator_checkpoint_store import load_checkpoint
from core.runtime.aer_operator_context import build_operator_context, validate_operator_context
from core.runtime.aer_operator_lifecycle import build_operator_lifecycle_record
from core.runtime.aer_operator_state_machine import advance_operator_lifecycle

AER_OPERATOR_RESUME_CONTRACT = "aer.operator_resume.v2"


def resume_from_checkpoint(
    workspace_root: str,
    checkpoint_id: str,
) -> dict:
    loaded = load_checkpoint(workspace_root, checkpoint_id)
    if loaded.get("ok") is not True:
        return build_resume_result(
            ok=False,
            checkpoint_id=str(checkpoint_id or ""),
            errors=list(loaded.get("errors") or ["checkpoint load failed"]),
            metadata={"source": "checkpoint_store", "load_result": loaded},
        )

    return resume_from_payload(loaded.get("checkpoint"))


def resume_from_payload(checkpoint: dict) -> dict:
    checkpoint_validation = validate_operator_checkpoint(checkpoint)
    if checkpoint_validation["ok"] is not True:
        checkpoint_id = checkpoint.get("checkpoint_id") if isinstance(checkpoint, dict) else ""
        return build_resume_result(
            ok=False,
            checkpoint_id=str(checkpoint_id or ""),
            checkpoint=checkpoint if isinstance(checkpoint, dict) else {},
            errors=list(checkpoint_validation["errors"]),
            metadata={"source": "checkpoint_payload"},
        )

    context = build_operator_context(
        operator_session_id=str(checkpoint.get("operator_session_id") or ""),
        package_id=str(checkpoint.get("package_id") or ""),
        current_phase=str(checkpoint.get("phase") or ""),
        checkpoint_id=str(checkpoint.get("checkpoint_id") or ""),
        metadata={
            "resume_token": str(checkpoint.get("resume_token") or ""),
            "checkpoint_metadata": copy.deepcopy(dict(checkpoint.get("metadata") or {})),
        },
    )
    context_validation = validate_operator_context(context)
    if context_validation["ok"] is not True:
        return build_resume_result(
            ok=False,
            checkpoint_id=str(checkpoint.get("checkpoint_id") or ""),
            checkpoint=checkpoint,
            execution_context=context,
            lifecycle_phase=str(checkpoint.get("phase") or ""),
            errors=list(context_validation["errors"]),
            metadata={"source": "execution_context"},
        )

    lifecycle = build_operator_lifecycle_record(
        operator_session_id=str(checkpoint.get("operator_session_id") or ""),
        package_id=str(checkpoint.get("package_id") or ""),
        phase=str(checkpoint.get("phase") or ""),
        transition_reason="resume requested",
    )
    transition_result = advance_operator_lifecycle(
        lifecycle,
        "resumed",
        reason="resume requested",
    )

    if transition_result.get("ok") is True:
        context = build_operator_context(
            operator_session_id=context["operator_session_id"],
            package_id=context["package_id"],
            runtime_session_id=context["runtime_session_id"],
            current_phase=str(transition_result["record"].get("phase") or ""),
            checkpoint_id=context["checkpoint_id"],
            approval_state=context["approval_state"],
            stop_reason=context["stop_reason"],
            issue_report_id=context["issue_report_id"],
            metadata=context["metadata"],
        )

    return build_resume_result(
        ok=transition_result.get("ok") is True,
        checkpoint_id=str(checkpoint.get("checkpoint_id") or ""),
        checkpoint=checkpoint,
        execution_context=context,
        lifecycle_phase=str(transition_result.get("record", {}).get("phase") or checkpoint.get("phase") or ""),
        transition_result=transition_result,
        errors=list(transition_result.get("errors") or []),
        metadata={
            "source": "checkpoint_payload",
            "resume_token": str(checkpoint.get("resume_token") or ""),
        },
    )


def build_resume_result(
    *,
    ok: bool,
    checkpoint_id: str = "",
    checkpoint: Mapping[str, Any] | None = None,
    execution_context: Mapping[str, Any] | None = None,
    lifecycle_phase: str = "",
    transition_result: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    errors: list[str] | None = None,
) -> dict:
    return {
        "ok": bool(ok),
        "contract": AER_OPERATOR_RESUME_CONTRACT,
        "checkpoint_id": str(checkpoint_id or ""),
        "checkpoint": copy.deepcopy(dict(checkpoint or {})),
        "execution_context": copy.deepcopy(dict(execution_context or {})),
        "lifecycle_phase": str(lifecycle_phase or ""),
        "transition_result": copy.deepcopy(dict(transition_result or {})),
        "metadata": copy.deepcopy(dict(metadata or {})),
        "errors": list(errors or []),
    }


def validate_resume_result(payload: Any) -> dict:
    errors = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "contract": AER_OPERATOR_RESUME_CONTRACT,
            "errors": ["payload must be a dict"],
        }

    required_fields = (
        "ok",
        "contract",
        "checkpoint_id",
        "checkpoint",
        "execution_context",
        "lifecycle_phase",
        "transition_result",
        "metadata",
        "errors",
    )
    for field in required_fields:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("contract") != AER_OPERATOR_RESUME_CONTRACT:
        errors.append("invalid contract")

    if not isinstance(payload.get("ok"), bool):
        errors.append("ok must be a bool")

    for field in ("checkpoint", "execution_context", "transition_result", "metadata"):
        if not isinstance(payload.get(field), dict):
            errors.append(f"{field} must be a dict")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")

    if payload.get("ok") is True and payload.get("errors"):
        errors.append("successful resume result must not include errors")

    return {
        "ok": not errors,
        "contract": AER_OPERATOR_RESUME_CONTRACT,
        "errors": errors,
    }
