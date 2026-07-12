from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.runtime.runtime_apply_execution_plan_builder import (
    RUNTIME_APPLY_EXECUTION_PLAN_SCHEMA, RuntimeApplyExecutionPlanBuilder,
)

DEFAULT_RESULT_PATH = Path("workspace/operator_apply_plans/apply_execution_plan_result.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_apply_execution_plan")
    subs = parser.add_subparsers(dest="command", required=True)
    build = subs.add_parser("build")
    for name in ("proposal_file", "approval_file", "admission_file"):
        build.add_argument(name)
    build.add_argument("--now")
    build.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    status = subs.add_parser("status")
    status.add_argument("proposal_file")
    status.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    return parser


def _load(path: str | Path) -> tuple[dict[str, Any], str]:
    source = Path(path)
    if not source.is_file(): return {}, "file_not_found"
    try: value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError): return {}, "invalid_json"
    return (dict(value), "") if isinstance(value, Mapping) else ({}, "json_object_required")


def _write(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2,
                                 sort_keys=True, default=str), encoding="utf-8")


def run_apply_execution_plan_cli(command: str, proposal_file: str | Path,
        approval_file: str | Path | None = None, admission_file: str | Path | None = None,
        *, now: Any = None, result_path: str | Path = DEFAULT_RESULT_PATH,
        builder: RuntimeApplyExecutionPlanBuilder | None = None) -> tuple[dict[str, Any], int]:
    if command == "status":
        result, error = _load(proposal_file)
        if error or result.get("schema") != RUNTIME_APPLY_EXECUTION_PLAN_SCHEMA:
            result = {"ok": False, "plan_status": "input_error",
                      "reason": error or "invalid_plan_schema"}; code = 2
        else: code = 0
    elif command == "build":
        values = [_load(path or "") for path in (proposal_file, approval_file, admission_file)]
        error_index = next((i for i, (_, error) in enumerate(values) if error), None)
        if error_index is not None:
            names = ("proposal", "approval", "admission")
            result = {"ok": False, "plan_status": "input_error",
                      "reason": f"{names[error_index]}_{values[error_index][1]}"}; code = 2
        else:
            result = (builder or RuntimeApplyExecutionPlanBuilder()).build(
                proposal=values[0][0], approval_record=values[1][0],
                admission_record=values[2][0], now=now)
            code = 0 if result.get("plan_ready") is True else 1
    else:
        result = {"ok": False, "plan_status": "input_error", "reason": "invalid_command"}; code = 2
    _write(result_path, result)
    return result, code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result, code = run_apply_execution_plan_cli(
        args.command, args.proposal_file, getattr(args, "approval_file", None),
        getattr(args, "admission_file", None), now=getattr(args, "now", None),
        result_path=args.result_path)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return code


if __name__ == "__main__": raise SystemExit(main())

__all__ = ["DEFAULT_RESULT_PATH", "build_parser", "main", "run_apply_execution_plan_cli"]
