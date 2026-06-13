from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from core.runtime.work_package_operator import RuntimeWorkPackageOperator


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.work_package_cli")
    parser.add_argument("--repo-root", default=os.environ.get("ZERO_REPO_ROOT", "."))
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("package_file")
    status = sub.add_parser("status")
    status.add_argument("package_id")
    plan = sub.add_parser("plan")
    plan.add_argument("package_id")
    run = sub.add_parser("run")
    run.add_argument("package_id")
    progress = sub.add_parser("progress")
    progress.add_argument("package_id")
    summary = sub.add_parser("summary")
    summary.add_argument("package_id")
    report = sub.add_parser("report")
    report.add_argument("package_id")
    memory = sub.add_parser("memory")
    memory.add_argument("package_id")
    sub.add_parser("memory-status")
    pause = sub.add_parser("pause")
    pause.add_argument("package_id")
    resume = sub.add_parser("resume")
    resume.add_argument("package_id")
    cancel = sub.add_parser("cancel")
    cancel.add_argument("package_id")
    listing = sub.add_parser("list")
    listing.add_argument("--status")
    listing.add_argument("--active", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    operator = RuntimeWorkPackageOperator(repo_root=args.repo_root)
    try:
        if args.command == "submit":
            payload = json.loads(Path(args.package_file).read_text(encoding="utf-8"))
            result = operator.submit_package(payload)
        elif args.command == "status":
            result = operator.package_status(args.package_id)
        elif args.command == "plan":
            result = operator.plan_package(args.package_id)
        elif args.command == "run":
            result = operator.run_package(args.package_id)
        elif args.command == "progress":
            result = operator.package_progress(args.package_id)
        elif args.command == "summary":
            _print_json(operator.package_summary(args.package_id))
            return 0
        elif args.command == "report":
            result = operator.package_report(args.package_id)
        elif args.command == "memory":
            result = operator.package_memory(args.package_id)
        elif args.command == "memory-status":
            result = operator.memory_status()
        elif args.command == "pause":
            result = operator.pause_package(args.package_id)
        elif args.command == "resume":
            result = operator.resume_package(args.package_id)
        elif args.command == "cancel":
            result = operator.cancel_package(args.package_id)
        else:
            result = operator.list_packages(status=args.status, active_only=args.active)
        _print_json({"ok": True, "result": result})
        return 0
    except Exception as exc:
        _print_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
