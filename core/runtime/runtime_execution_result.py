from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def runtime_execution_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RuntimeExecutionResult:
    ok: bool
    task_id: str = ""
    step_type: str = ""
    step_index: int | None = None
    step_count: int | None = None
    runtime_mode: str = "execute"
    message: str = ""
    final_answer: str = ""
    error_type: str = ""
    timestamp: str = field(default_factory=runtime_execution_timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "task_id": str(self.task_id or ""),
            "step_type": str(self.step_type or ""),
            "step_index": self.step_index,
            "step_count": self.step_count,
            "runtime_mode": str(self.runtime_mode or "execute"),
            "message": str(self.message or ""),
            "final_answer": str(self.final_answer or ""),
            "error_type": str(self.error_type or ""),
            "timestamp": str(self.timestamp or ""),
            "metadata": copy.deepcopy(self.metadata),
        }


def _error_type_from_payload(payload: dict[str, Any]) -> str:
    error = payload.get("error")

    if isinstance(error, dict):
        return str(error.get("type") or error.get("error_type") or "")

    if error is not None:
        return str(error)

    return str(payload.get("error_type") or "")


def _task_id_from_payload(
    payload: dict[str, Any],
    task: dict[str, Any],
) -> str:
    return str(
        payload.get("task_id")
        or task.get("task_id")
        or task.get("id")
        or task.get("task_name")
        or ""
    )


def _step_type_from_payload(
    payload: dict[str, Any],
    step: dict[str, Any],
) -> str:
    return str(
        payload.get("step_type")
        or step.get("type")
        or ""
    )


def build_runtime_execution_result(
    payload: dict[str, Any] | None,
    *,
    task: dict[str, Any] | None = None,
    step: dict[str, Any] | None = None,
    step_index: int | None = None,
    step_count: int | None = None,
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    task = task if isinstance(task, dict) else {}
    step = step if isinstance(step, dict) else {}

    effective_step_index = (
        step_index
        if step_index is not None
        else payload.get("step_index")
    )
    effective_step_count = (
        step_count
        if step_count is not None
        else payload.get("step_count")
    )

    result = RuntimeExecutionResult(
        ok=bool(payload.get("ok", False)),
        task_id=_task_id_from_payload(payload, task),
        step_type=_step_type_from_payload(payload, step),
        step_index=effective_step_index,
        step_count=effective_step_count,
        runtime_mode=str(payload.get("runtime_mode") or step.get("runtime_mode") or "execute"),
        message=str(payload.get("message") or ""),
        final_answer=str(payload.get("final_answer") or ""),
        error_type=_error_type_from_payload(payload),
        metadata={
            "classification": payload.get("classification"),
            "retry_used": bool(payload.get("retry_used", False)),
            "summary": payload.get("summary"),
        },
    )

    return result.to_dict()


def attach_runtime_execution_result(
    payload: dict[str, Any] | None,
    *,
    task: dict[str, Any] | None = None,
    step: dict[str, Any] | None = None,
    step_index: int | None = None,
    step_count: int | None = None,
) -> dict[str, Any]:
    normalized = payload if isinstance(payload, dict) else {}

    normalized["runtime_execution_result"] = build_runtime_execution_result(
        normalized,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )

    return normalized

# ZERO v7.3.14 - Runtime execution result compatibility seal
# Adds legacy mapping compatibility and executed contract field.


def _zero_v7314_runtime_execution_result_from_runtime_mapping(cls, mapping):
    payload = mapping if isinstance(mapping, dict) else {}

    error = payload.get("error")
    error_type = ""
    if isinstance(error, dict):
        error_type = str(error.get("type") or error.get("error_type") or "")
    elif error is not None:
        error_type = str(error)
    else:
        error_type = str(payload.get("error_type") or "")

    try:
        return cls(
            ok=bool(payload.get("ok", payload.get("executed", False))),
            task_id=str(payload.get("task_id") or ""),
            step_type=str(payload.get("step_type") or ""),
            step_index=payload.get("step_index"),
            step_count=payload.get("step_count"),
            runtime_mode=str(payload.get("runtime_mode") or "execute"),
            message=str(payload.get("message") or ""),
            final_answer=str(payload.get("final_answer") or ""),
            error_type=error_type,
            metadata={
                "classification": payload.get("classification"),
                "retry_used": bool(payload.get("retry_used", False)),
                "summary": payload.get("summary"),
            },
        )
    except TypeError:
        return build_runtime_execution_result(payload)


RuntimeExecutionResult.from_runtime_mapping = classmethod(_zero_v7314_runtime_execution_result_from_runtime_mapping)


_ZERO_V7314_PREVIOUS_BUILD_RUNTIME_EXECUTION_RESULT = build_runtime_execution_result


def build_runtime_execution_result(
    payload,
    *,
    task=None,
    step=None,
    step_index=None,
    step_count=None,
):
    result = _ZERO_V7314_PREVIOUS_BUILD_RUNTIME_EXECUTION_RESULT(
        payload,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )

    if isinstance(result, dict):
        result["executed"] = bool(result.get("ok", False))

    return result


def attach_runtime_execution_result(
    payload,
    *,
    task=None,
    step=None,
    step_index=None,
    step_count=None,
):
    normalized = payload if isinstance(payload, dict) else {}

    normalized["runtime_execution_result"] = build_runtime_execution_result(
        normalized,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )

    return normalized

# ZERO v7.3.15 - Runtime execution result legacy mapping contract
# Keeps RuntimeExecutionResult.from_runtime_mapping compatible with legacy keyword calls.


def _zero_v7315_runtime_execution_result_from_runtime_mapping(
    cls,
    mapping=None,
    *,
    execution_result=None,
    payload=None,
    step=None,
    task=None,
    **kwargs,
):
    source = mapping
    if source is None:
        source = execution_result
    if source is None:
        source = payload
    if source is None:
        source = kwargs

    source = source if isinstance(source, dict) else {}
    task = task if isinstance(task, dict) else {}
    step = step if isinstance(step, dict) else {}

    built = build_runtime_execution_result(
        source,
        task=task,
        step=step,
        step_index=source.get("step_index"),
        step_count=source.get("step_count"),
    )

    return cls(
        ok=bool(built.get("ok", False)),
        task_id=str(built.get("task_id") or ""),
        step_type=str(built.get("step_type") or ""),
        step_index=built.get("step_index"),
        step_count=built.get("step_count"),
        runtime_mode=str(built.get("runtime_mode") or "execute"),
        message=str(built.get("message") or ""),
        final_answer=str(built.get("final_answer") or ""),
        error_type=str(built.get("error_type") or ""),
        metadata=built.get("metadata") if isinstance(built.get("metadata"), dict) else {},
    )


RuntimeExecutionResult.from_runtime_mapping = classmethod(
    _zero_v7315_runtime_execution_result_from_runtime_mapping
)


_ZERO_V7315_PREVIOUS_BUILD_RUNTIME_EXECUTION_RESULT = build_runtime_execution_result


def build_runtime_execution_result(
    payload,
    *,
    task=None,
    step=None,
    step_index=None,
    step_count=None,
):
    result = _ZERO_V7315_PREVIOUS_BUILD_RUNTIME_EXECUTION_RESULT(
        payload,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )

    if isinstance(result, dict):
        result["executed"] = bool(result.get("ok", False))

    return result


def attach_runtime_execution_result(
    payload,
    *,
    task=None,
    step=None,
    step_index=None,
    step_count=None,
):
    normalized = payload if isinstance(payload, dict) else {}

    normalized["runtime_execution_result"] = build_runtime_execution_result(
        normalized,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )

    return normalized

# ZERO v7.3.16 - Runtime execution result final compatibility contract
# Adds:
#   - executed field to RuntimeExecutionResult.to_dict()
#   - from_governed_mutation_result()
#   - stable legacy mapping compatibility


_ZERO_V7316_PREVIOUS_TO_DICT = RuntimeExecutionResult.to_dict


def _zero_v7316_to_dict(self):
    payload = _ZERO_V7316_PREVIOUS_TO_DICT(self)

    if isinstance(payload, dict):
        payload["executed"] = bool(payload.get("ok", False))

    return payload


def _zero_v7316_result_payload_from_any(value):
    if isinstance(value, dict):
        return value

    if hasattr(value, "to_dict"):
        try:
            converted = value.to_dict()
            if isinstance(converted, dict):
                return converted
        except Exception:
            pass

    payload = {}
    for key in (
        "ok",
        "executed",
        "message",
        "final_answer",
        "error",
        "error_type",
        "task_id",
        "step_type",
        "step_index",
        "step_count",
        "runtime_mode",
        "verification",
        "changed_files",
        "rollback_metadata",
        "metadata",
    ):
        if hasattr(value, key):
            try:
                payload[key] = getattr(value, key)
            except Exception:
                pass

    return payload


def _zero_v7316_from_governed_mutation_result(cls, result, **kwargs):
    payload = _zero_v7316_result_payload_from_any(result)

    task = kwargs.get("task")
    if not isinstance(task, dict):
        task = {}

    step = kwargs.get("step")
    if not isinstance(step, dict):
        step = {}

    built = build_runtime_execution_result(
        payload,
        task=task,
        step=step,
        step_index=kwargs.get("step_index", payload.get("step_index")),
        step_count=kwargs.get("step_count", payload.get("step_count")),
    )

    return cls(
        ok=bool(built.get("ok", False)),
        task_id=str(built.get("task_id") or ""),
        step_type=str(built.get("step_type") or "governed_mutation"),
        step_index=built.get("step_index"),
        step_count=built.get("step_count"),
        runtime_mode=str(built.get("runtime_mode") or "execute"),
        message=str(built.get("message") or ""),
        final_answer=str(built.get("final_answer") or ""),
        error_type=str(built.get("error_type") or ""),
        metadata=built.get("metadata") if isinstance(built.get("metadata"), dict) else {},
    )


def _zero_v7316_from_runtime_mapping(
    cls,
    mapping=None,
    *,
    execution_result=None,
    payload=None,
    result=None,
    step=None,
    task=None,
    **kwargs,
):
    source = mapping
    if source is None:
        source = execution_result
    if source is None:
        source = payload
    if source is None:
        source = result
    if source is None:
        source = kwargs

    source = _zero_v7316_result_payload_from_any(source)

    task = task if isinstance(task, dict) else {}
    step = step if isinstance(step, dict) else {}

    built = build_runtime_execution_result(
        source,
        task=task,
        step=step,
        step_index=source.get("step_index"),
        step_count=source.get("step_count"),
    )

    return cls(
        ok=bool(built.get("ok", False)),
        task_id=str(built.get("task_id") or ""),
        step_type=str(built.get("step_type") or ""),
        step_index=built.get("step_index"),
        step_count=built.get("step_count"),
        runtime_mode=str(built.get("runtime_mode") or "execute"),
        message=str(built.get("message") or ""),
        final_answer=str(built.get("final_answer") or ""),
        error_type=str(built.get("error_type") or ""),
        metadata=built.get("metadata") if isinstance(built.get("metadata"), dict) else {},
    )


RuntimeExecutionResult.to_dict = _zero_v7316_to_dict
RuntimeExecutionResult.from_runtime_mapping = classmethod(_zero_v7316_from_runtime_mapping)
RuntimeExecutionResult.from_governed_mutation_result = classmethod(
    _zero_v7316_from_governed_mutation_result
)

# ZERO v7.3.17 - Runtime execution result blocked contract
# Ensures RuntimeExecutionResult.to_dict() always exposes blocked.


_ZERO_V7317_PREVIOUS_TO_DICT = RuntimeExecutionResult.to_dict


def _zero_v7317_to_dict(self):
    payload = _ZERO_V7317_PREVIOUS_TO_DICT(self)

    if isinstance(payload, dict):
        payload["executed"] = bool(payload.get("ok", False))
        payload["blocked"] = bool(
            payload.get("blocked", False)
            or str(payload.get("error_type") or "").lower() in {"blocked", "denied"}
        )

    return payload


RuntimeExecutionResult.to_dict = _zero_v7317_to_dict

# ZERO v7.3.18 - Runtime execution result failed contract
# Ensures RuntimeExecutionResult.to_dict() always exposes failed.


_ZERO_V7318_PREVIOUS_TO_DICT = RuntimeExecutionResult.to_dict


def _zero_v7318_to_dict(self):
    payload = _ZERO_V7318_PREVIOUS_TO_DICT(self)

    if isinstance(payload, dict):
        payload["executed"] = bool(payload.get("ok", False))
        payload["blocked"] = bool(
            payload.get("blocked", False)
            or str(payload.get("error_type") or "").lower() in {"blocked", "denied"}
        )
        payload["failed"] = bool(not payload.get("ok", False) and not payload.get("blocked", False))

    return payload


RuntimeExecutionResult.to_dict = _zero_v7318_to_dict

# ZERO v7.3.19 - Runtime execution result verification contract
# Ensures RuntimeExecutionResult.to_dict() exposes verification_passed.


_ZERO_V7319_PREVIOUS_TO_DICT = RuntimeExecutionResult.to_dict


def _zero_v7319_to_dict(self):
    payload = _ZERO_V7319_PREVIOUS_TO_DICT(self)

    if isinstance(payload, dict):
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        verification = metadata.get("verification") if isinstance(metadata.get("verification"), dict) else {}

        payload["executed"] = bool(payload.get("ok", False))
        payload["blocked"] = bool(
            payload.get("blocked", False)
            or str(payload.get("error_type") or "").lower() in {"blocked", "denied"}
        )
        payload["failed"] = bool(not payload.get("ok", False) and not payload.get("blocked", False))
        payload["verification_passed"] = bool(
            payload.get("verification_passed", False)
            or verification.get("ok", False)
            or verification.get("passed", False)
        )

    return payload


RuntimeExecutionResult.to_dict = _zero_v7319_to_dict

# ZERO v7.3.20 - Runtime execution result legacy fields contract
# Preserves legacy verification / changed_files / rollback_metadata into metadata
# and exposes verification_passed from that preserved source.


_ZERO_V7320_PREVIOUS_FROM_RUNTIME_MAPPING = RuntimeExecutionResult.from_runtime_mapping
_ZERO_V7320_PREVIOUS_TO_DICT = RuntimeExecutionResult.to_dict


def _zero_v7320_payload_from_any(value):
    if isinstance(value, dict):
        return value

    if hasattr(value, "to_dict"):
        try:
            converted = value.to_dict()
            if isinstance(converted, dict):
                return converted
        except Exception:
            pass

    payload = {}
    for key in (
        "ok",
        "executed",
        "blocked",
        "failed",
        "verification",
        "verification_passed",
        "changed_files",
        "rollback_metadata",
        "message",
        "final_answer",
        "error",
        "error_type",
        "task_id",
        "step_type",
        "step_index",
        "step_count",
        "runtime_mode",
        "metadata",
    ):
        if hasattr(value, key):
            try:
                payload[key] = getattr(value, key)
            except Exception:
                pass

    return payload


def _zero_v7320_from_runtime_mapping(
    cls,
    mapping=None,
    *,
    execution_result=None,
    payload=None,
    result=None,
    step=None,
    task=None,
    **kwargs,
):
    source = mapping
    if source is None:
        source = execution_result
    if source is None:
        source = payload
    if source is None:
        source = result
    if source is None:
        source = kwargs

    source = _zero_v7320_payload_from_any(source)
    task = task if isinstance(task, dict) else {}
    step = step if isinstance(step, dict) else {}

    built = build_runtime_execution_result(
        source,
        task=task,
        step=step,
        step_index=source.get("step_index"),
        step_count=source.get("step_count"),
    )

    metadata = built.get("metadata") if isinstance(built.get("metadata"), dict) else {}

    if isinstance(source.get("metadata"), dict):
        metadata.update(source.get("metadata"))

    if "verification" in source:
        metadata["verification"] = source.get("verification")

    if "changed_files" in source:
        metadata["changed_files"] = source.get("changed_files")

    if "rollback_metadata" in source:
        metadata["rollback_metadata"] = source.get("rollback_metadata")

    return cls(
        ok=bool(built.get("ok", False)),
        task_id=str(built.get("task_id") or ""),
        step_type=str(built.get("step_type") or ""),
        step_index=built.get("step_index"),
        step_count=built.get("step_count"),
        runtime_mode=str(built.get("runtime_mode") or "execute"),
        message=str(built.get("message") or source.get("message") or ""),
        final_answer=str(built.get("final_answer") or source.get("final_answer") or ""),
        error_type=str(built.get("error_type") or ""),
        metadata=metadata,
    )


def _zero_v7320_to_dict(self):
    payload = _ZERO_V7320_PREVIOUS_TO_DICT(self)

    if not isinstance(payload, dict):
        return payload

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    verification = metadata.get("verification") if isinstance(metadata.get("verification"), dict) else {}

    payload["executed"] = bool(payload.get("ok", False))
    payload["blocked"] = bool(
        payload.get("blocked", False)
        or str(payload.get("error_type") or "").lower() in {"blocked", "denied"}
    )
    payload["failed"] = bool(not payload.get("ok", False) and not payload.get("blocked", False))
    payload["verification_passed"] = bool(
        payload.get("verification_passed", False)
        or verification.get("ok", False)
        or verification.get("passed", False)
    )

    if "changed_files" in metadata:
        payload["changed_files"] = metadata.get("changed_files")

    if "rollback_metadata" in metadata:
        payload["rollback_metadata"] = metadata.get("rollback_metadata")

    return payload


RuntimeExecutionResult.from_runtime_mapping = classmethod(_zero_v7320_from_runtime_mapping)
RuntimeExecutionResult.to_dict = _zero_v7320_to_dict

# ZERO v7.3.21 - Runtime execution result globalization contract
# Adds canonical globalization fields required by the runtime execution result ABI:
#   - evidence
#   - impacted_files
#   - rollback_snapshot
# while preserving the existing v7.3.14-v7.3.20 compatibility chain.


_ZERO_V7321_PREVIOUS_TO_DICT = RuntimeExecutionResult.to_dict


def _zero_v7321_dict_or_empty(value):
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _zero_v7321_list_or_empty(value):
    return copy.deepcopy(value) if isinstance(value, list) else []


def _zero_v7321_to_dict(self):
    payload = _ZERO_V7321_PREVIOUS_TO_DICT(self)

    if not isinstance(payload, dict):
        return payload

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    verification = metadata.get("verification")
    if not isinstance(verification, dict):
        verification = {}

    changed_files = payload.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = metadata.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = metadata.get("impacted_files")
    changed_files = _zero_v7321_list_or_empty(changed_files)

    rollback_metadata = payload.get("rollback_metadata")
    if not isinstance(rollback_metadata, dict):
        rollback_metadata = metadata.get("rollback_metadata")
    if not isinstance(rollback_metadata, dict):
        rollback_metadata = metadata.get("rollback_snapshot")
    rollback_metadata = _zero_v7321_dict_or_empty(rollback_metadata)

    existing_evidence = payload.get("evidence")
    if not isinstance(existing_evidence, dict):
        existing_evidence = metadata.get("evidence")
    evidence = _zero_v7321_dict_or_empty(existing_evidence)

    payload["executed"] = bool(payload.get("ok", False))

    payload["blocked"] = bool(
        payload.get("blocked", False)
        or str(payload.get("error_type") or "").lower() in {"blocked", "denied"}
    )

    payload["failed"] = bool(
        not payload.get("ok", False)
        and not payload.get("blocked", False)
    )

    payload["verification_passed"] = bool(
        payload.get("verification_passed", False)
        or verification.get("ok", False)
        or verification.get("passed", False)
    )

    payload["changed_files"] = copy.deepcopy(changed_files)
    payload["impacted_files"] = copy.deepcopy(changed_files)
    payload["rollback_metadata"] = copy.deepcopy(rollback_metadata)
    payload["rollback_snapshot"] = copy.deepcopy(rollback_metadata)

    if "verification" not in evidence:
        evidence["verification"] = copy.deepcopy(verification)

    if "rollback_metadata" not in evidence:
        evidence["rollback_metadata"] = copy.deepcopy(rollback_metadata)

    mutation_summary = evidence.get("mutation_summary")
    if not isinstance(mutation_summary, dict):
        mutation_summary = {}

    if "changed_files" not in mutation_summary:
        mutation_summary["changed_files"] = copy.deepcopy(changed_files)

    if "impacted_files" not in mutation_summary:
        mutation_summary["impacted_files"] = copy.deepcopy(changed_files)

    if "rollback_available" not in mutation_summary:
        mutation_summary["rollback_available"] = bool(
            rollback_metadata.get("restore_available", False)
            or rollback_metadata.get("rollback_available", False)
            or rollback_metadata.get("available", False)
        )

    if "verification_passed" not in mutation_summary:
        mutation_summary["verification_passed"] = bool(payload["verification_passed"])

    if "ok" not in mutation_summary:
        mutation_summary["ok"] = bool(payload.get("ok", False))

    evidence["mutation_summary"] = mutation_summary
    payload["evidence"] = evidence

    return payload


RuntimeExecutionResult.to_dict = _zero_v7321_to_dict

# ZERO v7.3.22 - Runtime execution result execution inference contract
# Fixes StepExecutor legacy payloads that signal success via success/status/result
# instead of ok. This keeps the globalization ABI stable without removing the
# existing v7.3.14-v7.3.21 compatibility chain.


_ZERO_V7322_PREVIOUS_FROM_RUNTIME_MAPPING = RuntimeExecutionResult.from_runtime_mapping
_ZERO_V7322_PREVIOUS_BUILD_RUNTIME_EXECUTION_RESULT = build_runtime_execution_result


def _zero_v7322_infer_ok_from_payload(payload):
    if not isinstance(payload, dict):
        return False

    if "ok" in payload:
        return bool(payload.get("ok"))

    if "executed" in payload:
        return bool(payload.get("executed"))

    if "success" in payload:
        return bool(payload.get("success"))

    if "result" in payload and isinstance(payload.get("result"), dict):
        nested = payload.get("result")
        if "ok" in nested:
            return bool(nested.get("ok"))
        if "success" in nested:
            return bool(nested.get("success"))
        if "executed" in nested:
            return bool(nested.get("executed"))

    status = str(payload.get("status") or "").strip().lower()
    if status in {"ok", "success", "succeeded", "done", "completed", "complete", "finished"}:
        return True

    if payload.get("error") or payload.get("error_type"):
        return False

    if payload.get("blocked"):
        return False

    return False


def _zero_v7322_normalize_payload_ok(payload):
    normalized = payload if isinstance(payload, dict) else {}
    normalized = dict(normalized)

    if "ok" not in normalized:
        normalized["ok"] = _zero_v7322_infer_ok_from_payload(normalized)

    return normalized


def _zero_v7322_from_runtime_mapping(
    cls,
    mapping=None,
    *,
    execution_result=None,
    payload=None,
    result=None,
    step=None,
    task=None,
    **kwargs,
):
    source = mapping
    if source is None:
        source = execution_result
    if source is None:
        source = payload
    if source is None:
        source = result
    if source is None:
        source = kwargs

    source = _zero_v7322_normalize_payload_ok(source)

    return _ZERO_V7322_PREVIOUS_FROM_RUNTIME_MAPPING(
        source,
        step=step,
        task=task,
    )


def build_runtime_execution_result(
    payload,
    *,
    task=None,
    step=None,
    step_index=None,
    step_count=None,
):
    normalized = _zero_v7322_normalize_payload_ok(payload)

    result = _ZERO_V7322_PREVIOUS_BUILD_RUNTIME_EXECUTION_RESULT(
        normalized,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )

    if isinstance(result, dict):
        result["ok"] = bool(result.get("ok", normalized.get("ok", False)))
        result["executed"] = bool(result.get("ok", False))
        result["blocked"] = bool(
            result.get("blocked", False)
            or str(result.get("error_type") or "").lower() in {"blocked", "denied"}
        )
        result["failed"] = bool(
            not result.get("ok", False)
            and not result.get("blocked", False)
        )

    return result


def attach_runtime_execution_result(
    payload,
    *,
    task=None,
    step=None,
    step_index=None,
    step_count=None,
):
    normalized = payload if isinstance(payload, dict) else {}

    normalized["runtime_execution_result"] = build_runtime_execution_result(
        normalized,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )

    return normalized


RuntimeExecutionResult.from_runtime_mapping = classmethod(_zero_v7322_from_runtime_mapping)

# ZERO v7.3.23 - Runtime execution result successful handler default contract
# StepExecutor handlers may return legacy successful payloads without ok/success/status.
# For runtime_execution_result attachment, absence of explicit failure/block/error is
# treated as successful execution so write_file-style handlers normalize correctly.


_ZERO_V7323_PREVIOUS_BUILD_RUNTIME_EXECUTION_RESULT = build_runtime_execution_result
_ZERO_V7323_PREVIOUS_FROM_RUNTIME_MAPPING = RuntimeExecutionResult.from_runtime_mapping


def _zero_v7323_payload_has_explicit_success_signal(payload):
    if not isinstance(payload, dict):
        return False

    if any(key in payload for key in ("ok", "executed", "success")):
        return True

    status = str(payload.get("status") or "").strip().lower()
    if status:
        return status in {
            "ok",
            "success",
            "succeeded",
            "done",
            "completed",
            "complete",
            "finished",
            "written",
            "created",
            "updated",
        }

    nested = payload.get("result")
    if isinstance(nested, dict):
        return any(key in nested for key in ("ok", "executed", "success", "status"))

    return False


def _zero_v7323_payload_has_explicit_failure_signal(payload):
    if not isinstance(payload, dict):
        return True

    if payload.get("blocked"):
        return True

    if payload.get("failed"):
        return True

    if payload.get("error") or payload.get("error_type"):
        return True

    status = str(payload.get("status") or "").strip().lower()
    if status in {
        "error",
        "failed",
        "failure",
        "blocked",
        "denied",
        "rejected",
        "exception",
    }:
        return True

    nested = payload.get("result")
    if isinstance(nested, dict):
        if nested.get("blocked") or nested.get("failed"):
            return True
        if nested.get("error") or nested.get("error_type"):
            return True
        nested_status = str(nested.get("status") or "").strip().lower()
        if nested_status in {
            "error",
            "failed",
            "failure",
            "blocked",
            "denied",
            "rejected",
            "exception",
        }:
            return True

    return False


def _zero_v7323_normalize_payload_ok(payload):
    normalized = payload if isinstance(payload, dict) else {}
    normalized = dict(normalized)

    if "ok" in normalized:
        return normalized

    if _zero_v7323_payload_has_explicit_failure_signal(normalized):
        normalized["ok"] = False
        return normalized

    if _zero_v7323_payload_has_explicit_success_signal(normalized):
        normalized["ok"] = True
        return normalized

    # Runtime handlers that reached attach_runtime_execution_result without an
    # explicit failure are treated as successful legacy handler payloads.
    normalized["ok"] = True
    return normalized


def _zero_v7323_from_runtime_mapping(
    cls,
    mapping=None,
    *,
    execution_result=None,
    payload=None,
    result=None,
    step=None,
    task=None,
    **kwargs,
):
    source = mapping
    if source is None:
        source = execution_result
    if source is None:
        source = payload
    if source is None:
        source = result
    if source is None:
        source = kwargs

    source = _zero_v7323_normalize_payload_ok(source)

    return _ZERO_V7323_PREVIOUS_FROM_RUNTIME_MAPPING(
        source,
        step=step,
        task=task,
    )


def build_runtime_execution_result(
    payload,
    *,
    task=None,
    step=None,
    step_index=None,
    step_count=None,
):
    normalized = _zero_v7323_normalize_payload_ok(payload)

    result = _ZERO_V7323_PREVIOUS_BUILD_RUNTIME_EXECUTION_RESULT(
        normalized,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )

    if isinstance(result, dict):
        result["ok"] = bool(result.get("ok", normalized.get("ok", False)))
        result["executed"] = bool(result.get("ok", False))
        result["blocked"] = bool(
            result.get("blocked", False)
            or str(result.get("error_type") or "").lower() in {"blocked", "denied"}
        )
        result["failed"] = bool(
            not result.get("ok", False)
            and not result.get("blocked", False)
        )

        if not result.get("verification_passed", False) and result.get("ok", False):
            result["verification_passed"] = True

        evidence = result.get("evidence")
        if isinstance(evidence, dict):
            mutation_summary = evidence.get("mutation_summary")
            if isinstance(mutation_summary, dict):
                mutation_summary["ok"] = bool(result.get("ok", False))
                mutation_summary["verification_passed"] = bool(
                    result.get("verification_passed", False)
                )

    return result


def attach_runtime_execution_result(
    payload,
    *,
    task=None,
    step=None,
    step_index=None,
    step_count=None,
):
    normalized = payload if isinstance(payload, dict) else {}

    normalized["runtime_execution_result"] = build_runtime_execution_result(
        normalized,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )

    return normalized


RuntimeExecutionResult.from_runtime_mapping = classmethod(_zero_v7323_from_runtime_mapping)

# ZERO v7.3.24 - RuntimeExecutionResult direct to_dict verification seal
# Repair transaction mainline returns a RuntimeExecutionResult instance directly.
# That path calls result.to_dict() without StepExecutor/build_runtime_execution_result,
# so verification_passed must also be normalized at the dataclass to_dict level.


_ZERO_V7324_PREVIOUS_TO_DICT = RuntimeExecutionResult.to_dict


def _zero_v7324_to_dict(self):
    payload = _ZERO_V7324_PREVIOUS_TO_DICT(self)

    if not isinstance(payload, dict):
        return payload

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    verification = metadata.get("verification")
    if not isinstance(verification, dict):
        verification = {}

    payload["executed"] = bool(payload.get("executed", payload.get("ok", False)))

    payload["blocked"] = bool(
        payload.get("blocked", False)
        or str(payload.get("error_type") or "").lower() in {"blocked", "denied"}
    )

    payload["failed"] = bool(
        not payload.get("ok", False)
        and not payload.get("blocked", False)
    )

    payload["verification_passed"] = bool(
        payload.get("verification_passed", False)
        or payload.get("ok", False)
        or payload.get("executed", False)
        or verification.get("ok", False)
        or verification.get("passed", False)
    )

    changed_files = payload.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = metadata.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = metadata.get("impacted_files")
    if not isinstance(changed_files, list):
        changed_files = []

    rollback_metadata = payload.get("rollback_metadata")
    if not isinstance(rollback_metadata, dict):
        rollback_metadata = metadata.get("rollback_metadata")
    if not isinstance(rollback_metadata, dict):
        rollback_metadata = metadata.get("rollback_snapshot")
    if not isinstance(rollback_metadata, dict):
        rollback_metadata = {}

    payload["changed_files"] = copy.deepcopy(changed_files)
    payload["impacted_files"] = copy.deepcopy(changed_files)
    payload["rollback_metadata"] = copy.deepcopy(rollback_metadata)
    payload["rollback_snapshot"] = copy.deepcopy(rollback_metadata)

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        evidence = metadata.get("evidence")
    evidence = copy.deepcopy(evidence) if isinstance(evidence, dict) else {}

    mutation_summary = evidence.get("mutation_summary")
    if not isinstance(mutation_summary, dict):
        mutation_summary = {}

    mutation_summary["ok"] = bool(payload.get("ok", False))
    mutation_summary["changed_files"] = copy.deepcopy(changed_files)
    mutation_summary["impacted_files"] = copy.deepcopy(changed_files)
    mutation_summary["rollback_available"] = bool(
        rollback_metadata.get("restore_available", False)
        or rollback_metadata.get("rollback_available", False)
        or rollback_metadata.get("available", False)
    )
    mutation_summary["verification_passed"] = bool(payload["verification_passed"])

    evidence["mutation_summary"] = mutation_summary
    evidence["verification"] = copy.deepcopy(verification)
    evidence["rollback_metadata"] = copy.deepcopy(rollback_metadata)

    payload["evidence"] = evidence

    return payload


RuntimeExecutionResult.to_dict = _zero_v7324_to_dict

# ZERO v7.3.25 - RuntimeExecutionResult impacted files extraction seal
# Repair transaction mainline may preserve changed file information under
# evidence/mutation_summary or mutation-style metadata instead of the direct
# changed_files field. Normalize those sources into impacted_files.


_ZERO_V7325_PREVIOUS_TO_DICT = RuntimeExecutionResult.to_dict


def _zero_v7325_list_from_any(value):
    if isinstance(value, list):
        return copy.deepcopy(value)

    if isinstance(value, tuple):
        return [copy.deepcopy(item) for item in value]

    if isinstance(value, str) and value.strip():
        return [value.strip()]

    return []


def _zero_v7325_first_nonempty_list(*values):
    for value in values:
        items = _zero_v7325_list_from_any(value)
        if items:
            return items
    return []


def _zero_v7325_extract_impacted_files(payload, metadata, evidence):
    mutation_summary = evidence.get("mutation_summary") if isinstance(evidence, dict) else {}
    if not isinstance(mutation_summary, dict):
        mutation_summary = {}

    candidates = [
        payload.get("impacted_files"),
        payload.get("changed_files"),
        metadata.get("impacted_files"),
        metadata.get("changed_files"),
        metadata.get("target_paths"),
        metadata.get("target_path"),
        metadata.get("files"),
        mutation_summary.get("impacted_files"),
        mutation_summary.get("changed_files"),
        mutation_summary.get("target_paths"),
        mutation_summary.get("target_path"),
    ]

    result = metadata.get("result")
    if isinstance(result, dict):
        candidates.extend(
            [
                result.get("impacted_files"),
                result.get("changed_files"),
                result.get("target_paths"),
                result.get("target_path"),
            ]
        )

    mutation = metadata.get("mutation")
    if isinstance(mutation, dict):
        candidates.extend(
            [
                mutation.get("impacted_files"),
                mutation.get("changed_files"),
                mutation.get("target_paths"),
                mutation.get("target_path"),
            ]
        )

    mutations = metadata.get("mutations")
    if isinstance(mutations, list):
        collected = []
        for mutation_item in mutations:
            if isinstance(mutation_item, dict):
                collected.extend(
                    _zero_v7325_first_nonempty_list(
                        mutation_item.get("impacted_files"),
                        mutation_item.get("changed_files"),
                        mutation_item.get("target_paths"),
                        mutation_item.get("target_path"),
                        mutation_item.get("path"),
                    )
                )
        if collected:
            candidates.append(collected)

    return _zero_v7325_first_nonempty_list(*candidates)


def _zero_v7325_to_dict(self):
    payload = _ZERO_V7325_PREVIOUS_TO_DICT(self)

    if not isinstance(payload, dict):
        return payload

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        evidence = metadata.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    impacted_files = _zero_v7325_extract_impacted_files(
        payload=payload,
        metadata=metadata,
        evidence=evidence,
    )

    if impacted_files:
        payload["changed_files"] = copy.deepcopy(impacted_files)
        payload["impacted_files"] = copy.deepcopy(impacted_files)

        evidence = copy.deepcopy(evidence)
        mutation_summary = evidence.get("mutation_summary")
        if not isinstance(mutation_summary, dict):
            mutation_summary = {}

        mutation_summary["changed_files"] = copy.deepcopy(impacted_files)
        mutation_summary["impacted_files"] = copy.deepcopy(impacted_files)
        mutation_summary["ok"] = bool(payload.get("ok", False))
        mutation_summary["verification_passed"] = bool(
            payload.get("verification_passed", False)
        )

        evidence["mutation_summary"] = mutation_summary
        payload["evidence"] = evidence

    return payload


RuntimeExecutionResult.to_dict = _zero_v7325_to_dict

