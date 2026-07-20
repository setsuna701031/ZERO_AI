from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.engineering.engineering_capability_registry import (
    list_capabilities, lookup_capability, lookup_operation, validate_capability_registry,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("validate", "inspect", "lookup", "list", "operations"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--capability-id")
    parser.add_argument("--operation")
    parser.add_argument("--filter", choices=("enabled", "read-only", "mutation-capable"), default="enabled")
    parser.add_argument("--adapter-id")
    parser.add_argument("--execution-boundary")
    return parser


def run(argv=None):
    try: args = build_parser().parse_args(argv)
    except SystemExit as exc: return {"error": "argument_error"}, int(exc.code or 2)
    try: registry = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError): return {"error": "input_error"}, 2
    validation = validate_capability_registry(registry)
    if args.mode == "validate": output = {"valid": validation.valid, "reason_codes": list(validation.errors)}
    elif not validation.valid: output = {"valid": False, "reason_codes": list(validation.errors)}
    elif args.mode == "inspect": output = {"schema": registry["schema"], "registry_id": registry["registry_id"], "fingerprint": registry["fingerprint"], "registration_count": len(registry["registrations"])}
    elif args.mode == "lookup" and args.capability_id: output = lookup_capability(registry, args.capability_id)
    elif args.mode == "operations" and args.operation: output = lookup_operation(registry, args.operation)
    elif args.mode == "list": output = list_capabilities(registry, read_only=True if args.filter == "read-only" else None,
                                                          mutation_capable=True if args.filter == "mutation-capable" else None,
                                                          adapter_id=args.adapter_id, execution_boundary=args.execution_boundary)
    else: output = {"error": "argument_error"}
    status = output.get("lookup_status")
    return output, 0 if validation.valid and status not in {"invalid", "ambiguous", "unavailable"} and "error" not in output else 1


def main(argv=None):
    value, code = run(argv)
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
    return code


if __name__ == "__main__": raise SystemExit(main())
