from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from core.runtime.runtime_capability_strategy_bootstrap_consumer import consume_runtime_strategy_decision
from core.runtime.runtime_capability_strategy_bootstrap_configuration import configure_capability_strategy_bootstrap
from core.runtime.runtime_capability_strategy_bootstrap_decision import decide_capability_strategy_bootstrap


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
    parser = argparse.ArgumentParser(prog="python -m cli.zero_capability_strategy_bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("consume", "configure", "decide"):
        item = sub.add_parser(command); item.add_argument("runtime_decision_json"); item.add_argument("--output")
    return parser


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    args = build_parser().parse_args(argv)
    try:
        source = _read(args.runtime_decision_json)
        builder = {"consume": consume_runtime_strategy_decision, "configure": configure_capability_strategy_bootstrap, "decide": decide_capability_strategy_bootstrap}[args.command]
        value = builder(source); invalid = value["status"] == "rejected"
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
