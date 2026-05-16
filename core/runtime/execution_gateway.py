from __future__ import annotations

import subprocess
from dataclasses import dataclass, asdict
from typing import Any, Sequence


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
) -> dict[str, Any]:
    """
    Centralized subprocess execution boundary.

    Phase 1 rule:
    - Preserve subprocess behavior.
    - Do not silently swallow errors.
    - Always return a normalized dict.
    - Keep shell usage explicit and observable.
    """
    try:
        completed = subprocess.run(
            command,
            shell=shell,
            cwd=cwd,
            timeout=timeout,
            input=input_text,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        return ExecutionGatewayResult(
            ok=completed.returncode == 0,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            command=command,
            shell=shell,
            timeout=timeout,
            error=None,
        ).to_dict()

    except subprocess.TimeoutExpired as exc:
        return ExecutionGatewayResult(
            ok=False,
            returncode=None,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            command=command,
            shell=shell,
            timeout=timeout,
            error=f"timeout after {timeout} seconds",
        ).to_dict()

    except Exception as exc:
        return ExecutionGatewayResult(
            ok=False,
            returncode=None,
            stdout="",
            stderr="",
            command=command,
            shell=shell,
            timeout=timeout,
            error=f"{type(exc).__name__}: {exc}",
        ).to_dict()