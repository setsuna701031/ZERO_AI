from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Sequence

from core.runtime.executor import Executor
from core.runtime.runtime_execution_request import RuntimeExecutionRequest


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    Compatibility wrapper that forwards command execution to the canonical
    runtime executor. This function does not perform subprocess execution.
    """
    request = RuntimeExecutionRequest(
        execution_type="command" if shell else "subprocess",
        command=command if isinstance(command, str) else tuple(str(item) for item in command),
        working_directory=cwd,
        environment=env,
        timeout=timeout,
        metadata={
            "source": "runtime_execution_gateway",
            "shell": shell,
            "input_text_ignored": input_text is not None,
            "capture_output": capture_output,
            "text": text,
            "encoding": encoding,
            "errors": errors,
            "runtime_identity": {
                "identity_id": "system:runtime_execution_gateway",
                "identity_type": "SYSTEM",
                "source": "core.runtime.execution_gateway",
            },
            "authority_scope_id": "authority:system:execution_gateway",
            "capability_scope_id": "capability:system:subprocess",
            "provenance": {
                "requested_by": "core.runtime.execution_gateway.safe_subprocess_run",
                "gateway": "canonical_execution_gateway",
            },
        },
        lineage={
            "execution_start_id": "execution_start:runtime_execution_gateway",
        },
    )
    result = Executor(workspace_root="workspace").execute_request(request)
    timed_out = result.return_code == 124 and "timeout" in result.stderr.lower()
    return ExecutionGatewayResult(
        ok=result.return_code == 0,
        returncode=None if timed_out else result.return_code,
        stdout=result.stdout,
        stderr=result.stderr,
        command=command,
        shell=shell,
        timeout=timeout,
        error=(f"timeout after {timeout} seconds" if timed_out else None),
    ).to_dict()
