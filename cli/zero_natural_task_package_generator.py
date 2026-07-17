from __future__ import annotations

import argparse
import json
from typing import Sequence

from core.runtime.runtime_natural_task_cli_bridge import (
    build_natural_task_cli_bridge,
    natural_task_cli_bridge_to_summary,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zero_natural_task_package_generator",
        description="Generate a controlled ZERO runtime package from natural task text.",
    )
    parser.add_argument("task", help="Natural language task text.")
    parser.add_argument(
        "--target-root",
        default=".",
        help="Target repository root recorded in the generated package.",
    )
    parser.add_argument(
        "--package-json-path",
        default="<generated-runtime-package.json>",
        help="Planned package JSON path for the operator console command.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print bridge summary instead of full bridge payload.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    bridge = build_natural_task_cli_bridge(
        args.task,
        target_root=args.target_root,
        package_json_path=args.package_json_path,
    )
    payload = natural_task_cli_bridge_to_summary(bridge) if args.summary else bridge
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if bridge.get("ok") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
