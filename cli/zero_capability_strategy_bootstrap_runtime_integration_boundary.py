from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import SCHEMA, integrate_bootstrap_consumption
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary_validation import validate_bootstrap_runtime_integration_boundary


def _read(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _render(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_strategy_bootstrap_runtime_integration_boundary")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("integrate", "validate", "inspect"):
        sub.add_parser(command).add_argument("json_file")
    return parser


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        value = _read(args.json_file)
        if args.command == "integrate":
            result = integrate_bootstrap_consumption(value)
            return result, 0 if result["status"] in {"integrated", "default_compatible"} else 1
        if not isinstance(value, dict) or value.get("schema") != SCHEMA:
            return {"valid": False, "errors": ["unsupported_schema"]}, 1
        validation = validate_bootstrap_runtime_integration_boundary(value)
        if args.command == "validate":
            return {"valid": validation.valid, "errors": list(validation.errors)}, 0 if validation.valid else 1
        return {
            "valid": validation.valid, "schema": value.get("schema"), "status": value.get("status"),
            "boundary_id": value.get("boundary_id"), "source_consumption_id": value.get("source_consumption_id"),
            "integration_payload_available": value.get("integration_payload") is not None,
        }, 0 if validation.valid else 1
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"error": "input_error", "error_type": type(exc).__name__}, 2


def main(argv: list[str] | None = None) -> int:
    try:
        value, code = run(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    sys.stdout.write(_render(value))
    return code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main", "run"]
