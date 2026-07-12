from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.runtime.runtime_controlled_apply_admission import (
    RUNTIME_CONTROLLED_APPLY_ADMISSION_SCHEMA, RuntimeControlledApplyAdmission,
)

DEFAULT_RESULT_PATH = Path("workspace/operator_apply_admission/controlled_apply_admission_result.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_controlled_apply_admission")
    sub = parser.add_subparsers(dest="command", required=True)
    admit = sub.add_parser("admit")
    admit.add_argument("proposal_file")
    admit.add_argument("approval_file")
    admit.add_argument("--controlled", action="store_true")
    admit.add_argument("--now")
    admit.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    status = sub.add_parser("status")
    status.add_argument("proposal_file")
    status.add_argument("approval_file", nargs="?")
    status.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    return parser


def _load(path: str | Path) -> tuple[dict[str, Any], str]:
    source = Path(path)
    if not source.is_file(): return {}, "file_not_found"
    try: payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError): return {}, "invalid_json"
    return (dict(payload), "") if isinstance(payload, Mapping) else ({}, "json_object_required")


def _write(path: str | Path, result: Mapping[str, Any]) -> None:
    output = Path(path); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(result), ensure_ascii=False, indent=2,
                                 sort_keys=True, default=str), encoding="utf-8")


def run_controlled_apply_admission_cli(command: str, proposal_file: str | Path,
        approval_file: str | Path | None = None, *, controlled: bool = False,
        now: Any = None, result_path: str | Path = DEFAULT_RESULT_PATH,
        gate: RuntimeControlledApplyAdmission | None = None) -> tuple[dict[str, Any], int]:
    if command == "status":
        result, error = _load(proposal_file)
        if error:
            result = {"ok": False, "admission_status": "input_error", "reason": error}
            code = 2
        elif result.get("schema") != RUNTIME_CONTROLLED_APPLY_ADMISSION_SCHEMA:
            result = {"ok": False, "admission_status": "input_error", "reason": "invalid_admission_schema"}
            code = 2
        else:
            code = 0
    elif command == "admit":
        proposal, error = _load(proposal_file)
        approval, approval_error = _load(approval_file or "")
        if error or approval_error:
            result = {"ok": False, "admission_status": "input_error",
                      "reason": f"proposal_{error}" if error else f"approval_{approval_error}"}
            code = 2
        else:
            result = (gate or RuntimeControlledApplyAdmission()).admit(
                proposal=proposal, approval_record=approval,
                controlled=controlled, now=now)
            code = 0 if result.get("apply_admitted") is True else 1
    else:
        result = {"ok": False, "admission_status": "input_error", "reason": "invalid_command"}
        code = 2
    _write(result_path, result)
    return result, code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result, code = run_controlled_apply_admission_cli(
        args.command, args.proposal_file, getattr(args, "approval_file", None),
        controlled=getattr(args, "controlled", False), now=getattr(args, "now", None),
        result_path=args.result_path)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return code


if __name__ == "__main__": raise SystemExit(main())

__all__ = ["DEFAULT_RESULT_PATH", "build_parser", "main",
           "run_controlled_apply_admission_cli"]
