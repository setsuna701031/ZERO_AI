from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.runtime.runtime_controlled_execution_activation import (
    RUNTIME_CONTROLLED_EXECUTION_ACTIVATION_CONTRACT, activate_controlled_execution,
)

DEFAULT_RESULT_PATH = Path("workspace/operator_controlled_execution/controlled_execution_result.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_controlled_execution")
    subs = parser.add_subparsers(dest="command", required=True)
    run = subs.add_parser("run")
    run.add_argument("execution_plan_file"); run.add_argument("review_result_file"); run.add_argument("operator_request_file")
    run.add_argument("--target-root", required=True); run.add_argument("--now")
    run.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    status = subs.add_parser("status"); status.add_argument("execution_plan_file")
    status.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    return parser


def _load(path: str | Path) -> tuple[dict[str, Any], str]:
    source = Path(path)
    if not source.is_file(): return {}, "file_not_found"
    try: value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError): return {}, "invalid_json"
    return (dict(value), "") if isinstance(value, Mapping) else ({}, "json_object_required")


def _write(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_controlled_execution_cli(command: str, execution_plan_file: str | Path,
        review_result_file: str | Path | None = None, operator_request_file: str | Path | None = None,
        *, target_root: str | Path | None = None, now: Any = None,
        result_path: str | Path = DEFAULT_RESULT_PATH) -> tuple[dict[str, Any], int]:
    if command == "status":
        result, error = _load(execution_plan_file)
        if error or result.get("contract") != RUNTIME_CONTROLLED_EXECUTION_ACTIVATION_CONTRACT:
            result = {"contract": RUNTIME_CONTROLLED_EXECUTION_ACTIVATION_CONTRACT,
                      "activation_status": "input_error", "execution_allowed": False,
                      "file_mutation_performed": False, "reasons": [error or "invalid_activation_contract"]}; code = 2
        else: code = 0
    elif command == "run":
        values = [_load(path or "") for path in (execution_plan_file, review_result_file, operator_request_file)]
        bad = next((i for i, (_, error) in enumerate(values) if error), None)
        if bad is not None or not target_root:
            names = ("plan", "review", "request")
            reason = "target_root_required" if bad is None else f"{names[bad]}_{values[bad][1]}"
            result = {"contract": RUNTIME_CONTROLLED_EXECUTION_ACTIVATION_CONTRACT,
                      "activation_status": "input_error", "execution_allowed": False,
                      "file_mutation_performed": False, "reasons": [reason]}; code = 2
        else:
            result = activate_controlled_execution(values[0][0], values[1][0], values[2][0],
                                                   target_root=target_root, now=now)
            code = 0 if result["activation_status"] == "completed" else 1
    else:
        result = {"contract": RUNTIME_CONTROLLED_EXECUTION_ACTIVATION_CONTRACT,
                  "activation_status": "input_error", "execution_allowed": False,
                  "file_mutation_performed": False, "reasons": ["invalid_command"]}; code = 2
    _write(result_path, result)
    return result, code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result, code = run_controlled_execution_cli(args.command, args.execution_plan_file,
        getattr(args, "review_result_file", None), getattr(args, "operator_request_file", None),
        target_root=getattr(args, "target_root", None), now=getattr(args, "now", None),
        result_path=args.result_path)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str)); return code


if __name__ == "__main__": raise SystemExit(main())

__all__ = ["DEFAULT_RESULT_PATH", "build_parser", "main", "run_controlled_execution_cli"]
