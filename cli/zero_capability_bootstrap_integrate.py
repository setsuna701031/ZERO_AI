from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from core.runtime.runtime_capability_bootstrap_integration import MODES, default_policy, integrate_capability_bootstrap
from core.runtime.runtime_capability_bootstrap_integration_validation import validate_integration_record

def _read(path: str) -> Any: return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def _render(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_bootstrap_integrate"); sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("modes"); sub.add_parser("defaults")
    for command in ("integrate", "validate", "explain"): item = sub.add_parser(command); item.add_argument("json_file")
    return parser
def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "modes": return {"modes": sorted(MODES)}, 0
        if args.command == "defaults": return {"mode": "validate_only", "policy": default_policy()}, 0
        if args.command == "integrate":
            value = integrate_capability_bootstrap(_read(args.json_file)); return value, 0 if value["integration_status"] in {"validated", "prepared", "accepted", "blocked", "rejected"} else 1
        value = _read(args.json_file); validation = validate_integration_record(value)
        if args.command == "validate": return {"valid": validation.valid, "errors": list(validation.errors)}, 0 if validation.valid else 1
        return {"valid": validation.valid, "integration_status": value.get("integration_status"), "activation_eligibility": value.get("activation_eligibility"), "activation_blockers": value.get("activation_blockers", []), "runtime_started": value.get("runtime_started")}, 0 if validation.valid else 1
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc: return {"error": "input_error", "error_type": type(exc).__name__}, 2
def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(_render(value)); return code
if __name__ == "__main__": raise SystemExit(main())
