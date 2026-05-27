from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from core.runtime.executor import Executor
from core.runtime.execution_authority import ensure_authority_metadata, validate_authority_metadata
from core.runtime.runtime_surface_registry import classify_runtime_surface
from core.runtime.runtime_execution_request import RuntimeExecutionRequest
from core.runtime.runtime_transaction_context import build_transaction_boundary_metadata
from core.runtime.runtime_consistency import build_runtime_state_consistency
from core.runtime.runtime_closure import build_runtime_closure_fields


RUNTIME_AUTHORITY_SOURCE = "core.runtime.execution_gateway"
RUNTIME_AUTHORITY_OWNER = "core.runtime.executor"
RUNTIME_AUTHORITY_ENTRYPOINT = "safe_subprocess_run"
RUNTIME_AUTHORITY_SCOPE_ID = "authority:system:execution_gateway"
RUNTIME_CAPABILITY_SCOPE_ID = "capability:system:subprocess"


@dataclass(frozen=True)
class ExecutionGatewayResult:
    ok: bool
    returncode: int | None
    stdout: str
    stderr: str
    command: Any
    shell: bool
    timeout: float | None
    error: str | None = None
    replay_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    risk_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_command(command: str | Sequence[str]) -> str | tuple[str, ...]:
    if isinstance(command, str):
        return command
    return tuple(str(item) for item in command)


def _stable_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(repr(value).encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _build_runtime_identity() -> dict[str, Any]:
    return {
        "identity_id": "system:runtime_execution_gateway",
        "identity_type": "SYSTEM",
        "source": RUNTIME_AUTHORITY_SOURCE,
        "canonical_owner": RUNTIME_AUTHORITY_OWNER,
    }


def _build_authority_metadata(
    *,
    command: Any,
    shell: bool,
    input_text: str | None,
    capture_output: bool,
    text: bool,
    encoding: str,
    errors: str,
    extra_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    transaction_boundary = build_transaction_boundary_metadata(
        {
            "transaction_source": "runtime_execution_gateway",
            "transaction_status": "opened",
            "transaction_scope": "execution_gateway",
        }
    )
    metadata: dict[str, Any] = {
        "task_id": "runtime_execution_gateway",
        "step_id": _stable_id("gateway_step", command),
        "runtime_session": _stable_id("runtime_session", time.time_ns()),
        "approval_state": "approved",
        "policy_result": {"allowed": True, "source": RUNTIME_AUTHORITY_SOURCE},
        "trace_id": _stable_id("trace", command),
        "source": "runtime_execution_gateway",
        "execution_source": "runtime_execution_gateway",
        "gateway": "canonical_execution_gateway",
        "runtime_authority_entrypoint": RUNTIME_AUTHORITY_ENTRYPOINT,
        "runtime_authority_source": RUNTIME_AUTHORITY_SOURCE,
        "authority_source": RUNTIME_AUTHORITY_SOURCE,
        "authority_scope": RUNTIME_AUTHORITY_SCOPE_ID,
        "authority_status": "allowed",
        "authority_reason": "runtime_execution_gateway_authorized",
        "ownership_source": RUNTIME_AUTHORITY_OWNER,
        "ownership_scope": RUNTIME_CAPABILITY_SCOPE_ID,
        "canonical_owner": RUNTIME_AUTHORITY_OWNER,
        "execution_authority_unified": True,
        "execution_legality": "legal",
        "direct_subprocess_bypass": False,
        "shell": shell,
        "input_text_ignored": input_text is not None,
        "capture_output": capture_output,
        "text": text,
        "encoding": encoding,
        "errors": errors,
        "runtime_identity": _build_runtime_identity(),
        "authority_scope_id": RUNTIME_AUTHORITY_SCOPE_ID,
        "capability_scope_id": RUNTIME_CAPABILITY_SCOPE_ID,
        "transaction_boundary": transaction_boundary,
        "provenance": {
            "requested_by": "core.runtime.execution_gateway.safe_subprocess_run",
            "gateway": "canonical_execution_gateway",
            "canonical_owner": RUNTIME_AUTHORITY_OWNER,
            "bypass_prevention": "subprocess execution is delegated to Executor.execute_request",
        },
    }

    if extra_metadata:
        metadata.update(dict(extra_metadata))

    closure = build_runtime_closure_fields(
        {
            **metadata,
            "execution_status": metadata.get("execution_status", "opened"),
            "source": "runtime_execution_gateway",
        },
        artifact_type="execution_gateway",
        artifact_id=RUNTIME_AUTHORITY_ENTRYPOINT,
        finalized_by="runtime_execution_gateway",
    )
    metadata.update(closure)
    metadata["consistency_seal"] = build_runtime_state_consistency(metadata)
    metadata["authority_validation"] = {
        "ok": True,
        "reason": "authority_metadata_valid",
        "missing_fields": [],
    }
    return metadata


def build_runtime_execution_request(
    command: str | Sequence[str],
    *,
    shell: bool = False,
    cwd: str | None = None,
    timeout: float | None = 60.0,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = True,
    text: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
    metadata: Mapping[str, Any] | None = None,
    lineage: Mapping[str, Any] | None = None,
    operator_session_id: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> RuntimeExecutionRequest:
    normalized_command = _normalize_command(command)
    surface = classify_runtime_surface("command" if shell else "subprocess")
    forwarded_metadata: dict[str, Any] = dict(metadata or {})
    forwarded_lineage: dict[str, Any] = dict(lineage or {})
    context_session_id = ""
    if isinstance(context, Mapping):
        context_session_id = str(context.get("operator_session_id") or context.get("persistent_operator_session_id") or "").strip()
    resolved_operator_session_id = str(operator_session_id or context_session_id or "").strip()
    if resolved_operator_session_id:
        forwarded_metadata.setdefault("operator_session_id", resolved_operator_session_id)
        forwarded_lineage.setdefault("operator_session_id", resolved_operator_session_id)

    request_metadata = _build_authority_metadata(
        command=normalized_command,
        shell=shell,
        input_text=input_text,
        capture_output=capture_output,
        text=text,
        encoding=encoding,
        errors=errors,
        extra_metadata=forwarded_metadata,
    )

    request_lineage: dict[str, Any] = {
        "execution_start_id": "execution_start:runtime_execution_gateway",
        "authority_entrypoint": RUNTIME_AUTHORITY_ENTRYPOINT,
        "authority_source": RUNTIME_AUTHORITY_SOURCE,
        "canonical_owner": RUNTIME_AUTHORITY_OWNER,
    }

    if forwarded_lineage:
        request_lineage.update(forwarded_lineage)

    return RuntimeExecutionRequest(
        execution_type="command" if shell else "subprocess",
        command=normalized_command,
        working_directory=cwd,
        environment=env,
        timeout=timeout,
        metadata={**request_metadata, "runtime_surface": surface.name},
        lineage=request_lineage,
    )


def execute_runtime_request(
    request: RuntimeExecutionRequest,
    *,
    workspace_root: str = "workspace",
    executor: Executor | None = None,
) -> ExecutionGatewayResult:
    normalized_metadata, authority_validation = ensure_authority_metadata(
        request.metadata,
        lineage=request.lineage,
        authority_source=str(request.metadata.get("authority_source") or "execution_gateway"),
        action_type="execute",
        surface=request.execution_type,
    )
    if normalized_metadata != request.metadata:
        request = RuntimeExecutionRequest(
            execution_type=request.execution_type,
            command=request.command,
            working_directory=request.working_directory,
            environment=request.environment,
            timeout=request.timeout,
            metadata=normalized_metadata,
            lineage=dict(request.lineage),
            replay_id=request.replay_id,
            repair_session_id=request.repair_session_id,
            dry_run=request.dry_run,
        )
    if not authority_validation.get("ok"):
        reason = str(authority_validation.get("reason") or "authority_metadata_invalid")
        metadata = {
            **dict(request.metadata),
            "authority_validation": authority_validation,
            "blocked": True,
            "blocked_reason": reason,
            "audit_event": {
                "event_type": "execution_blocked",
                "reason": reason,
                "source": RUNTIME_AUTHORITY_SOURCE,
            },
            "evidence": {
                "blocked": True,
                "reason": reason,
                "authority_validation": authority_validation,
            },
            "replay_event": {
                "event_type": "execution_decision",
                "decision": "blocked",
                "reason": reason,
            },
        }
        return ExecutionGatewayResult(
            ok=False,
            returncode=1,
            stdout="",
            stderr=reason,
            command=request.command,
            shell=request.execution_type == "command",
            timeout=request.timeout,
            error=reason,
            replay_id=request.replay_id,
            metadata=metadata,
            risk_metadata={"authority_validation": authority_validation},
        )

    runtime_executor = executor if executor is not None else Executor(workspace_root=workspace_root)
    result = runtime_executor.execute_request(request)

    stderr_text = str(result.stderr or "")
    timed_out = result.return_code == 124 and "timeout" in stderr_text.lower()

    return ExecutionGatewayResult(
        ok=result.return_code == 0,
        returncode=None if timed_out else result.return_code,
        stdout=result.stdout,
        stderr=result.stderr,
        command=request.command,
        shell=request.execution_type == "command",
        timeout=request.timeout,
        error=(f"timeout after {request.timeout} seconds" if timed_out else None),
        replay_id=result.replay_id,
        metadata=dict(result.metadata),
        risk_metadata=dict(result.risk_metadata),
    )


def safe_subprocess_run(
    command: str | Sequence[str],
    *,
    shell: bool = False,
    cwd: str | None = None,
    timeout: float | None = 60.0,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = True,
    text: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
    metadata: Mapping[str, Any] | None = None,
    operator_session_id: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Canonical runtime execution gateway.

    This function intentionally does not call subprocess directly.
    All command/subprocess execution is delegated to Executor.execute_request()
    so policy, boundary, replay, evidence, lineage, and risk metadata stay
    under one runtime authority path.
    """
    request = build_runtime_execution_request(
        command=command,
        shell=shell,
        cwd=cwd,
        timeout=timeout,
        input_text=input_text,
        env=env,
        capture_output=capture_output,
        text=text,
        encoding=encoding,
        errors=errors,
        metadata=metadata,
        operator_session_id=operator_session_id,
        context=context,
    )

    return execute_runtime_request(request).to_dict()
