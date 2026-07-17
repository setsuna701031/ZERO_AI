from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_executor import MODES, execute_capability_bootstrap
from core.runtime.runtime_capability_bootstrap_execution_validation import validate_execution_result

def _read(path: str) -> Any: return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def _render(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_bootstrap_execute"); sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("modes"); sub.add_parser("defaults")
    execute = sub.add_parser("execute"); execute.add_argument("request_json")
    validate = sub.add_parser("validate-result"); validate.add_argument("result_json")
    explain = sub.add_parser("explain"); explain.add_argument("result_json")
    return parser

def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "modes": return {"modes": sorted(MODES)}, 0
        if args.command == "defaults": return {"mode": "validation_only", "dry_run": True, "mutation_allowed": False}, 0
        if args.command == "execute":
            result = execute_capability_bootstrap(_read(args.request_json)); return result, 0 if result["overall_status"] in {"completed", "partial", "blocked"} else 1
        result = _read(args.result_json); validation = validate_execution_result(result)
        if args.command == "validate-result": return {"valid": validation.valid, "errors": list(validation.errors)}, 0 if validation.valid else 1
        return {"valid": validation.valid, "overall_status": result.get("overall_status"), "blocked_reasons": result.get("blocked_reasons", []), "warnings": result.get("warnings", []), "steps": [{"step_id": x.get("step_id"), "step_type": x.get("step_type"), "status": x.get("status")} for x in result.get("ordered_step_results", []) if isinstance(x, Mapping)]}, 0 if validation.valid else 1
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc: return {"error": "input_error", "error_type": type(exc).__name__}, 2

def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(_render(value)); return code

if __name__ == "__main__": raise SystemExit(main())
