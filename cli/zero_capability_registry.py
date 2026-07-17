from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from core.runtime.runtime_capability_registry import RuntimeCapabilityRegistry, build_default_capability_registry
from core.runtime.runtime_capability_registry_validation import validate_capability_registry


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
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_registry")
    sub = parser.add_subparsers(dest="command", required=True)
    defaults = sub.add_parser("defaults"); defaults.add_argument("--output")
    validate = sub.add_parser("validate"); validate.add_argument("registry_json")
    listing = sub.add_parser("list"); listing.add_argument("registry_json"); listing.add_argument("--kind"); listing.add_argument("--domain"); listing.add_argument("--enabled-only", action="store_true")
    resolve = sub.add_parser("resolve"); resolve.add_argument("registry_json"); resolve.add_argument("--kind", required=True); resolve.add_argument("--domain", required=True)
    return parser


def _load_registry(value: Any) -> RuntimeCapabilityRegistry:
    result = validate_capability_registry(value)
    if not result.valid: raise ValueError("invalid_registry")
    registry = RuntimeCapabilityRegistry()
    for entry in value["entries"]: registry.register(entry)
    return registry


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "defaults":
            value = build_default_capability_registry().snapshot()
            if args.output: _atomic_write(Path(args.output), _render(value))
            return value, 0
        value = _read(args.registry_json)
        if args.command == "validate":
            result = validate_capability_registry(value)
            return {"valid": result.valid, "errors": list(result.errors)}, 0 if result.valid else 1
        registry = _load_registry(value)
        if args.command == "list": return {"entries": registry.list_entries(args.kind, args.domain, args.enabled_only)}, 0
        resolution = registry.resolve(args.kind, args.domain)
        return ({"found": False, "entry": None}, 1) if resolution is None else ({"found": True, "entry": resolution.entry}, 0)
    except (OSError, ValueError, TypeError) as exc:
        return {"error": "input_error", "error_type": type(exc).__name__}, 2


def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(_render(value)); return code


if __name__ == "__main__": raise SystemExit(main())


__all__ = ["build_parser", "main", "run"]
