from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence

from core.verification.verification_tiers import (
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_TIMEOUT,
    VerificationCommand,
    VerificationResult,
    build_parser,
    run_tier,
)


def _tail(text: str, limit: int = 2000) -> str:
    return text[-limit:] if len(text) > limit else text


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run_command(command: VerificationCommand, repo_root: Path) -> VerificationResult:
    try:
        completed = subprocess.run(
            command.argv(),
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=command.timeout_seconds,
            env=_env(),
        )
    except subprocess.TimeoutExpired as exc:
        return VerificationResult(
            label=command.label,
            tier=command.tier,
            command=command.command_text(),
            status=STATUS_TIMEOUT,
            timeout_seconds=command.timeout_seconds,
            optional=command.optional,
            long_demo=command.long_demo,
            legacy_diagnostic_output=command.legacy_diagnostic_output,
            stdout_tail=_tail(str(exc.stdout or "")),
            stderr_tail=_tail(str(exc.stderr or "")),
        )

    status = STATUS_PASSED if completed.returncode == 0 else STATUS_FAILED
    return VerificationResult(
        label=command.label,
        tier=command.tier,
        command=command.command_text(),
        status=status,
        returncode=completed.returncode,
        timeout_seconds=command.timeout_seconds,
        optional=command.optional,
        long_demo=command.long_demo,
        legacy_diagnostic_output=command.legacy_diagnostic_output,
        stdout_tail=_tail(completed.stdout or ""),
        stderr_tail=_tail(completed.stderr or ""),
    )


def _print_result_summary(payload: dict[str, object]) -> None:
    print(f"[verification] tier={payload['tier']} ok={payload['ok']}")
    print(f"[verification] repo={payload['repo_root']}")
    counts = payload.get("status_counts") if isinstance(payload.get("status_counts"), dict) else {}
    print(
        "[verification] statuses: "
        + ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
    )
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue
        suffix = " legacy_diagnostic_output=true" if item.get("legacy_diagnostic_output") else ""
        print(f"[{item.get('status')}] {item.get('label')}: {item.get('command')}{suffix}")
        if item.get("status") in {STATUS_FAILED, STATUS_TIMEOUT}:
            stdout_tail = str(item.get("stdout_tail") or "").strip()
            stderr_tail = str(item.get("stderr_tail") or "").strip()
            if stdout_tail:
                print("STDOUT_TAIL:")
                print(stdout_tail)
            if stderr_tail:
                print("STDERR_TAIL:")
                print(stderr_tail)


def run_verification_cli(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    payload = run_tier(
        args.tier,
        repo_root=args.repo_root,
        runner=run_command,
        include_skipped=not args.no_skipped,
    )
    _print_result_summary(payload)
    return 0 if payload.get("ok") else 1


__all__ = ["run_command", "run_verification_cli"]
