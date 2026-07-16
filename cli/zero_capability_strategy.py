from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from core.runtime.runtime_capability_strategy_selector import select_capability_strategy
from core.runtime.runtime_capability_strategy_validation import validate_capability_strategy


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
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_strategy")
    sub = parser.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select"); select.add_argument("profile_json"); select.add_argument("--output")
    validate = sub.add_parser("validate"); validate.add_argument("strategy_json")
    show = sub.add_parser("show"); show.add_argument("strategy_json")
    return parser


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "select":
            strategy = select_capability_strategy(_read(args.profile_json)).to_dict()
            if args.output: _atomic_write(Path(args.output), _render(strategy))
            return strategy, 0
        value = _read(args.strategy_json)
        if args.command == "show": return value, 0
        result = validate_capability_strategy(value)
        return {"valid": result.valid, "errors": list(result.errors)}, 0 if result.valid else 1
    except (OSError, ValueError, TypeError) as exc:
        return {"error": "input_error", "error_type": type(exc).__name__}, 2


def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(_render(value)); return code


if __name__ == "__main__": raise SystemExit(main())


__all__ = ["build_parser", "main", "run"]
