from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from core.runtime.executor import Executor
from core.runtime.runtime_execution_request import RuntimeExecutionRequest


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


def _build_runtime_identity() -> dict[str, Any]:
    return {
        "identity_id": "system:runtime_execution_gateway",
        "identity_type": "SYSTEM",
        "source": RUNTIME_AUTHORITY_SOURCE,
        "canonical_owner": RUNTIME_AUTHORITY_OWNER,
    }


def _build_authority_metadata(
    *,
    shell: bool,
    input_text: str | None,
    capture_output: bool,
    text: bool,
    encoding: str,
    errors: str,
    extra_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": "runtime_execution_gateway",
        "gateway": "canonical_execution_gateway",
        "runtime_authority_entrypoint": RUNTIME_AUTHORITY_ENTRYPOINT,
        "runtime_authority_source": RUNTIME_AUTHORITY_SOURCE,
        "canonical_owner": RUNTIME_AUTHORITY_OWNER,
        "execution_authority_unified": True,
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
        "provenance": {
            "requested_by": "core.runtime.execution_gateway.safe_subprocess_run",
            "gateway": "canonical_execution_gateway",
            "canonical_owner": RUNTIME_AUTHORITY_OWNER,
            "bypass_prevention": "subprocess execution is delegated to Executor.execute_request",
        },
    }

    if extra_metadata:
        metadata.update(dict(extra_metadata))

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
) -> RuntimeExecutionRequest:
    normalized_command = _normalize_command(command)

    request_metadata = _build_authority_metadata(
        shell=shell,
        input_text=input_text,
        capture_output=capture_output,
        text=text,
        encoding=encoding,
        errors=errors,
        extra_metadata=metadata,
    )

    request_lineage: dict[str, Any] = {
        "execution_start_id": "execution_start:runtime_execution_gateway",
        "authority_entrypoint": RUNTIME_AUTHORITY_ENTRYPOINT,
        "authority_source": RUNTIME_AUTHORITY_SOURCE,
        "canonical_owner": RUNTIME_AUTHORITY_OWNER,
    }

    if lineage:
        request_lineage.update(dict(lineage))

    return RuntimeExecutionRequest(
        execution_type="command" if shell else "subprocess",
        command=normalized_command,
        working_directory=cwd,
        environment=env,
        timeout=timeout,
        metadata=request_metadata,
        lineage=request_lineage,
    )


def execute_runtime_request(
    request: RuntimeExecutionRequest,
    *,
    workspace_root: str = "workspace",
    executor: Executor | None = None,
) -> ExecutionGatewayResult:
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
    )

    return execute_runtime_request(request).to_dict()