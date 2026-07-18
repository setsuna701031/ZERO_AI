from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from core.runtime.runtime_capability_strategy_runtime_consumer import consume_capability_strategy
from core.runtime.runtime_capability_strategy_runtime_integration import integrate_capability_strategy_runtime
from core.runtime.runtime_capability_strategy_runtime_decision import decide_capability_strategy_runtime


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
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_strategy_runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("consume", "integrate", "decide"):
        item = sub.add_parser(command); item.add_argument("strategy_json"); item.add_argument("--output")
    return parser


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        strategy = _read(args.strategy_json)
        builder = {"consume": consume_capability_strategy, "integrate": integrate_capability_strategy_runtime, "decide": decide_capability_strategy_runtime}[args.command]
        value = builder(strategy)
        invalid = value["status"] in {"invalid", "rejected"}
        if args.output and not invalid: _atomic_write(Path(args.output), _render(value))
        return value, 1 if invalid else 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"error": "input_error", "error_type": type(exc).__name__}, 2


def main(argv: list[str] | None = None) -> int:
    try: value, code = run(argv)
    except SystemExit as exc: return int(exc.code or 0)
    sys.stdout.write(_render(value)); return code


if __name__ == "__main__": raise SystemExit(main())
__all__ = ["build_parser", "main", "run"]
