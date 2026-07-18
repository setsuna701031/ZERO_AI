from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from core.runtime.runtime_capability_strategy_bootstrap_configuration import SCHEMA as CONFIGURATION_SCHEMA
from core.runtime.runtime_capability_strategy_bootstrap_wiring import REQUEST_SCHEMA, RESULT_SCHEMA, build_bootstrap_wiring_request, wire_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_wiring_validation import validate_wiring_request, validate_wiring_result


def _read(path: str) -> Any: return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def _render(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream: stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        try: os.unlink(temporary)
        except OSError: pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_strategy_bootstrap_wiring")
    sub = parser.add_subparsers(dest="command", required=True)
    wire = sub.add_parser("wire"); wire.add_argument("json_file"); wire.add_argument("--target", choices=("plan", "integration", "consumer"), default="plan"); wire.add_argument("--disabled", action="store_true"); wire.add_argument("--output")
    for command in ("validate", "inspect"):
        item = sub.add_parser(command); item.add_argument("json_file")
    return parser


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        value = _read(args.json_file)
        if args.command == "wire":
            if not isinstance(value, dict): return {"error": "input_error", "error_type": "invalid_type"}, 2
            request = value if value.get("schema") == REQUEST_SCHEMA else build_bootstrap_wiring_request(bootstrap_configuration=value, target_bootstrap_stage=args.target, enabled=not args.disabled)
            result = wire_capability_strategy_bootstrap(request)
            if args.output and result["status"] not in {"invalid", "rejected"}: _atomic_write(Path(args.output), _render(result))
            return result, 1 if result["status"] in {"invalid", "rejected"} else 0
        validation = validate_wiring_request(value) if value.get("schema") == REQUEST_SCHEMA else validate_wiring_result(value) if value.get("schema") == RESULT_SCHEMA else None
        if validation is None: return {"valid": False, "errors": ["unsupported_schema"]}, 1
        if args.command == "validate": return {"valid": validation.valid, "errors": list(validation.errors)}, 0 if validation.valid else 1
        return {"valid": validation.valid, "schema": value.get("schema"), "status": value.get("status"), "target_bootstrap_stage": value.get("target_bootstrap_stage"), "configuration_applied": value.get("configuration_applied"), "compatibility_mode": value.get("compatibility_mode")}, 0 if validation.valid else 1
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"error": "input_error", "error_type": type(exc).__name__}, 2


def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(_render(value)); return code


if __name__ == "__main__": raise SystemExit(main())
__all__ = ["build_parser", "main", "run"]
