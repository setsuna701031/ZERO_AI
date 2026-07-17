from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from core.runtime.runtime_capability_bootstrap_plan import SCOPES, default_policy, plan_capability_bootstrap
from core.runtime.runtime_capability_bootstrap_plan_validation import validate_capability_bootstrap_plan


def _read(path: str) -> Any: return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def _render(value: Any, pretty: bool = False) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2 if pretty else None, separators=None if pretty else (",", ":"), allow_nan=False) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_bootstrap_plan"); sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("defaults"); sub.add_parser("scopes")
    plan = sub.add_parser("plan")
    for name in ("discovery", "detection", "profile", "strategy", "provenance"): plan.add_argument(f"--{name}", required=True)
    plan.add_argument("--registry"); plan.add_argument("--scope", default="capability_runtime_initialization"); plan.add_argument("--policy"); plan.add_argument("--output"); plan.add_argument("--pretty", action="store_true")
    validate = sub.add_parser("validate"); validate.add_argument("plan_json")
    explain = sub.add_parser("explain"); explain.add_argument("plan_json")
    return parser


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "defaults": return {"policy": default_policy()}, 0
        if args.command == "scopes": return {"scopes": sorted(SCOPES)}, 0
        if args.command == "validate":
            result = validate_capability_bootstrap_plan(_read(args.plan_json)); return {"valid": result.valid, "errors": list(result.errors)}, 0 if result.valid else 1
        if args.command == "explain":
            value = _read(args.plan_json); result = validate_capability_bootstrap_plan(value)
            return {"valid": result.valid, "readiness": value.get("readiness"), "blocked_reasons": value.get("blocked_reasons", []), "warnings": value.get("warnings", []), "steps": [{"step_id": x.get("step_id"), "step_type": x.get("step_type"), "status": x.get("status"), "blocked_reason": x.get("blocked_reason")} for x in value.get("ordered_steps", []) if isinstance(x, dict)]}, 0 if result.valid else 1
        value = plan_capability_bootstrap(discovery=_read(args.discovery), detection=_read(args.detection), profile=_read(args.profile), strategy=_read(args.strategy), provenance=_read(args.provenance), registry=_read(args.registry) if args.registry else None, scope=args.scope, policy=_read(args.policy) if args.policy else None)
        if args.output: Path(args.output).write_text(_render(value, args.pretty), encoding="utf-8")
        return value, 0 if value["readiness"] not in {"invalid", "unsupported"} else 1
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc: return {"error": "input_error", "error_type": type(exc).__name__}, 2


def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(_render(value)); return code


if __name__ == "__main__": raise SystemExit(main())
