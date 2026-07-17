from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from core.runtime.runtime_capability_detection import CapabilityDetectionOrchestrator
from core.runtime.runtime_capability_detection_validation import validate_capability_detection


def _render(value: Any, pretty: bool = True) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2 if pretty else None, separators=None if pretty else (",", ":"), allow_nan=False) + "\n"
def _read(path: str) -> Any: return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream: stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        try: os.unlink(temporary)
        except OSError: pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_detect")
    sub = parser.add_subparsers(dest="command", required=True)
    detect = sub.add_parser("detect"); detect.add_argument("--domain", action="append"); detect.add_argument("--workspace-root"); detect.add_argument("--output"); detect.add_argument("--pretty", action="store_true")
    validate = sub.add_parser("validate"); validate.add_argument("snapshot_json")
    sub.add_parser("defaults"); sub.add_parser("list-detectors")
    return parser


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv); orchestrator = CapabilityDetectionOrchestrator()
    try:
        if args.command in {"defaults", "list-detectors"}: return {"detectors": orchestrator.list_detectors()}, 0
        if args.command == "validate":
            result = validate_capability_detection(_read(args.snapshot_json)); return {"valid": result.valid, "errors": list(result.errors)}, 0 if result.valid else 1
        value = orchestrator.detect(args.domain, workspace_root=args.workspace_root)
        if args.output: _write(Path(args.output), _render(value, args.pretty))
        return value, 0
    except (OSError, ValueError, TypeError) as exc: return {"error": "input_error", "error_type": type(exc).__name__}, 2


def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(_render(value)); return code


if __name__ == "__main__": raise SystemExit(main())


__all__ = ["build_parser", "main", "run"]
