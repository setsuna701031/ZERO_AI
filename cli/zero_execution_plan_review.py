from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.runtime.runtime_execution_plan_review_gate import (
    RUNTIME_EXECUTION_PLAN_REVIEW_GATE_CONTRACT, review_execution_plan,
)

DEFAULT_RESULT_PATH = Path("workspace/operator_plan_reviews/execution_plan_review_result.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_execution_plan_review")
    subs = parser.add_subparsers(dest="command", required=True)
    build = subs.add_parser("build")
    build.add_argument("execution_plan_file"); build.add_argument("operator_review_file")
    build.add_argument("--now"); build.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    status = subs.add_parser("status")
    status.add_argument("execution_plan_file"); status.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    return parser


def _load(path: str | Path) -> tuple[dict[str, Any], str]:
    source = Path(path)
    if not source.is_file(): return {}, "file_not_found"
    try: value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError): return {}, "invalid_json"
    return (dict(value), "") if isinstance(value, Mapping) else ({}, "json_object_required")


def _write(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2,
                                 sort_keys=True, default=str), encoding="utf-8")


def run_execution_plan_review_cli(command: str, execution_plan_file: str | Path,
        operator_review_file: str | Path | None = None, *, now: Any = None,
        result_path: str | Path = DEFAULT_RESULT_PATH) -> tuple[dict[str, Any], int]:
    if command == "status":
        result, error = _load(execution_plan_file)
        if error or result.get("contract") != RUNTIME_EXECUTION_PLAN_REVIEW_GATE_CONTRACT:
            result = {"contract": RUNTIME_EXECUTION_PLAN_REVIEW_GATE_CONTRACT,
                      "review_status": "input_error", "review_valid": False,
                      "executor_admission_ready": False, "execution_allowed": False,
                      "reasons": [error or "invalid_review_result_contract"]}; code = 2
        else: code = 0
    elif command == "build":
        plan, plan_error = _load(execution_plan_file)
        review, review_error = _load(operator_review_file or "")
        if plan_error or review_error:
            result = {"contract": RUNTIME_EXECUTION_PLAN_REVIEW_GATE_CONTRACT,
                      "review_status": "input_error", "review_valid": False,
                      "executor_admission_ready": False, "execution_allowed": False,
                      "reasons": [f"plan_{plan_error}" if plan_error else f"review_{review_error}"]}; code = 2
        else:
            result = review_execution_plan(plan, review, now=now)
            code = 0 if result["review_status"] == "approved" else 1
    else:
        result = {"contract": RUNTIME_EXECUTION_PLAN_REVIEW_GATE_CONTRACT,
                  "review_status": "input_error", "execution_allowed": False,
                  "reasons": ["invalid_command"]}; code = 2
    _write(result_path, result)
    return result, code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result, code = run_execution_plan_review_cli(
        args.command, args.execution_plan_file, getattr(args, "operator_review_file", None),
        now=getattr(args, "now", None), result_path=args.result_path)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return code


if __name__ == "__main__": raise SystemExit(main())

__all__ = ["DEFAULT_RESULT_PATH", "build_parser", "main", "run_execution_plan_review_cli"]
