from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
from core.runtime.runtime_capability_bootstrap_consumer import MODES, SCOPES, ProcessLocalLeaseRegistry, consume_capability_bootstrap, default_policy
from core.runtime.runtime_capability_bootstrap_consumer_validation import validate_consumption_result
def _read(path: str) -> Any: return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_bootstrap_consume"); subs = parser.add_subparsers(dest="command", required=True)
    for name in ("modes", "scopes", "defaults"): subs.add_parser(name)
    for name in ("consume", "validate", "explain"): item = subs.add_parser(name); item.add_argument("json_file")
    return parser
def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "modes": return {"modes": sorted(MODES)}, 0
        if args.command == "scopes": return {"scopes": sorted(SCOPES)}, 0
        if args.command == "defaults": return {"mode": "validate_only", "scope": "combined_runtime_context_read", "policy": default_policy()}, 0
        value = _read(args.json_file)
        if args.command == "consume":
            result = consume_capability_bootstrap(value["request"], integration=value["integration"], runtime_context=value["runtime_context"], lease=value.get("lease"), registry=ProcessLocalLeaseRegistry())
            return result, 0 if result["status"] in {"validated", "leased", "consumed", "blocked", "rejected", "revoked"} else 1
        validation = validate_consumption_result(value)
        if args.command == "validate": return {"valid": validation.valid, "errors": list(validation.errors)}, 0 if validation.valid else 1
        return {"valid": validation.valid, "status": value.get("status"), "eligible": value.get("eligibility", {}).get("eligible"), "blocked_reasons": value.get("blocked_reasons", []), "runtime_started": value.get("runtime_started"), "mutation_performed": value.get("mutation_performed")}, 0 if validation.valid else 1
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc: return {"error": "input_error", "error_type": type(exc).__name__}, 2
def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"); return code
if __name__ == "__main__": raise SystemExit(main())
