from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.runtime.runtime_operator_config import load_runtime_operator_config
from core.runtime.runtime_operator_service import RuntimeOperatorService


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero")
    parser.add_argument("--config", default="")
    parser.add_argument("--checkpoint-path", default="")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "status", "stop", "resume", "health"):
        commands.add_parser(name)
    run = commands.add_parser("run")
    run.add_argument("goal")
    return parser


def _service(args: argparse.Namespace) -> RuntimeOperatorService:
    config_source: Any = args.config if args.config else None
    config = load_runtime_operator_config(config_source)
    if args.checkpoint_path:
        config = load_runtime_operator_config(
            {
                **config.to_dict(),
                "checkpoint_path": str(Path(args.checkpoint_path)),
            }
        )
    return RuntimeOperatorService(config)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = _service(args)

    if args.command == "start":
        result = service.start()
    elif args.command == "status":
        result = service.status()
    elif args.command == "stop":
        result = service.stop()
    elif args.command == "resume":
        result = service.resume()
    elif args.command == "run":
        result = service.run_goal(args.goal, explicit_manual_mode=True)
    else:
        result = service.health()

    _print_json(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
