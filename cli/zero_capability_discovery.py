from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from core.runtime.runtime_capability_provider_discovery import DiscoveryError, builtin_provider_descriptors, discover_providers
from core.runtime.runtime_capability_provider_discovery_validation import validate_capability_provider_discovery


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_discovery"); sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("defaults"); sub.add_parser("list-providers")
    discover = sub.add_parser("discover"); discover.add_argument("--domain", action="append"); discover.add_argument("--platform-family"); discover.add_argument("--architecture"); discover.add_argument("--python-version"); discover.add_argument("--output"); discover.add_argument("--pretty", action="store_true")
    validate = sub.add_parser("validate"); validate.add_argument("snapshot_json")
    explain = sub.add_parser("explain"); explain.add_argument("domain"); explain.add_argument("--platform-family"); explain.add_argument("--architecture"); explain.add_argument("--python-version")
    return parser


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        descriptors = builtin_provider_descriptors()
        if args.command in {"defaults", "list-providers"}: return {"providers": descriptors}, 0
        if args.command == "validate":
            result = validate_capability_provider_discovery(json.loads(Path(args.snapshot_json).read_text(encoding="utf-8-sig"))); return {"valid": result.valid, "errors": list(result.errors)}, 0 if result.valid else 1
        context = {key: value for key, value in {"platform_family": args.platform_family, "architecture": args.architecture, "python_version": args.python_version}.items() if value}
        domains = [args.domain] if args.command == "explain" else args.domain
        snapshot = discover_providers(descriptors, domains=domains, context=context)
        if args.command == "explain":
            value = {"domain": args.domain, "selected": [x for x in snapshot["selected_providers"] if x["domain"] == args.domain], "rejected": [x for x in snapshot["rejected_providers"] if x["domain"] == args.domain], "unresolved": args.domain in snapshot["unresolved_domains"]}
        else: value = snapshot
        if getattr(args, "output", None): Path(args.output).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None, allow_nan=False) + "\n", encoding="utf-8")
        return value, 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError, DiscoveryError) as exc: return {"error": "input_error", "error_type": type(exc).__name__}, 2


def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"); return code


if __name__ == "__main__": raise SystemExit(main())
