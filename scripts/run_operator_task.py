from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _repo_root_for_imports() -> Path:
    return Path(__file__).resolve().parents[1]


sys.path.insert(0, str(_repo_root_for_imports()))

from core.operator.operator_runner import result_to_json, run_operator_task


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local ZERO Codex-style operator task.")
    parser.add_argument("task", nargs="?", help="Task text for the operator.")
    parser.add_argument("--repo-root", default=str(_repo_root_for_imports()), help="Repository root to scan and operate on.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and plan only; do not apply edits or verify.")
    parser.add_argument("--allow-path", action="append", default=[], help="Restrict selected files to this path prefix. Can be repeated.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not str(args.task or "").strip():
        parser.error("task text is required")
    result = run_operator_task(
        args.task,
        repo_root=args.repo_root,
        dry_run=bool(args.dry_run),
        allow_paths=args.allow_path,
    )
    print(result_to_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
