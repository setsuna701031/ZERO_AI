from __future__ import annotations

import argparse
import json
from typing import Sequence

from core.runtime.runtime_natural_task_operator_pipeline import (
    run_natural_task_operator_pipeline,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zero_natural_task",
        description="Run a natural task through the controlled ZERO runtime pipeline.",
    )
    parser.add_argument("task", nargs="+", help="Natural task text.")
    parser.add_argument(
        "--target-root",
        default=".",
        help="Target root recorded in the generated package.",
    )
    parser.add_argument(
        "--controlled",
        action="store_true",
        help="Use controlled/manual-safe mode.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_natural_task_operator_pipeline(
        " ".join(args.task),
        target_root=args.target_root,
        explicit_manual_mode=args.controlled,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
