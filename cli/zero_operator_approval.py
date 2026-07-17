from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.runtime.runtime_operator_approval_gate import (
    RUNTIME_OPERATOR_APPROVAL_GATE_SCHEMA,
    RuntimeOperatorApprovalGate,
    evaluate_expiration,
)


DEFAULT_RESULT_PATH = Path(
    "workspace/operator_approvals/operator_approval_result.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli.zero_operator_approval",
        description="Review a change proposal without granting execution authority.",
    )
    parser.add_argument("command", choices=("approve", "reject", "revoke", "status"))
    parser.add_argument("proposal_or_approval_file")
    parser.add_argument("--operator-id", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--expires-at")
    parser.add_argument("--scope-file")
    parser.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    return parser


def _load_json(path: str | Path) -> tuple[dict[str, Any], str]:
    source = Path(path)
    if not source.is_file():
        return {}, "file_not_found"
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}, "invalid_json"
    return (dict(payload), "") if isinstance(payload, Mapping) else ({}, "json_object_required")


def _write(path: str | Path, result: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(dict(result), ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def run_operator_approval_cli(
    command: str,
    proposal_or_approval_file: str | Path,
    *,
    operator_id: str = "",
    reason: str = "",
    expires_at: str | None = None,
    scope_file: str | Path | None = None,
    result_path: str | Path = DEFAULT_RESULT_PATH,
    gate: RuntimeOperatorApprovalGate | None = None,
) -> tuple[dict[str, Any], int]:
    payload, error = _load_json(proposal_or_approval_file)
    if error:
        result = {"ok": False, "approval_status": "input_error", "reason": error}
        _write(result_path, result)
        return result, 2
    normalized = str(command or "").strip().lower()
    if normalized not in {"approve", "reject", "revoke", "status"}:
        result = {"ok": False, "approval_status": "input_error", "reason": "invalid_command"}
        _write(result_path, result)
        return result, 2
    if normalized != "status" and not str(operator_id or "").strip():
        result = {"ok": False, "approval_status": "input_error", "reason": "operator_id_required"}
        _write(result_path, result)
        return result, 2
    if normalized in {"reject", "revoke"} and not str(reason or "").strip():
        result = {"ok": False, "approval_status": "input_error", "reason": "reason_required"}
        _write(result_path, result)
        return result, 2

    approved_scope = None
    if scope_file:
        approved_scope, scope_error = _load_json(scope_file)
        if scope_error:
            result = {"ok": False, "approval_status": "input_error", "reason": f"scope_{scope_error}"}
            _write(result_path, result)
            return result, 2
        if isinstance(approved_scope.get("approved_scope"), Mapping):
            approved_scope = dict(approved_scope["approved_scope"])

    approval_gate = gate or RuntimeOperatorApprovalGate()
    if normalized in {"approve", "reject"}:
        result = approval_gate.review(
            proposal=payload,
            decision=normalized,
            operator_id=operator_id,
            reason=reason,
            expires_at=expires_at,
            approved_scope=approved_scope,
        )
        exit_code = 0 if result.get("approval_status") in {"approved", "rejected"} else 1
    elif normalized == "revoke":
        result = approval_gate.revoke(payload, operator_id, reason)
        exit_code = 0 if result.get("approval_status") == "revoked" else 1
    else:
        if payload.get("schema") != RUNTIME_OPERATOR_APPROVAL_GATE_SCHEMA:
            result = {
                "ok": False,
                "approval_status": "invalid_proposal",
                "reason": "invalid_approval_schema",
                "execution_authority_granted": False,
                "mutation_allowed": False,
                "patch_application_allowed": False,
                "autonomous_apply_allowed": False,
                "requires_controlled_apply": True,
            }
            exit_code = 1
        else:
            result = evaluate_expiration(payload, approval_gate.clock())
            exit_code = 0
    _write(result_path, result)
    return result, exit_code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result, exit_code = run_operator_approval_cli(
        args.command,
        args.proposal_or_approval_file,
        operator_id=args.operator_id,
        reason=args.reason,
        expires_at=args.expires_at,
        scope_file=args.scope_file,
        result_path=args.result_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_RESULT_PATH",
    "build_parser",
    "main",
    "run_operator_approval_cli",
]
