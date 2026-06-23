from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.tasks.work_package_runtime_intake import package_payload_from_text
from core.tasks.work_package_scheduler import WorkPackageScheduler


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _is_scheduler_work_package(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return all(key in payload for key in ("package_id", "kind", "mode", "scope_paths", "report_path"))


def _scheduler_payload_to_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    package_id = str(payload.get("package_id") or "").strip()
    title = str(payload.get("title") or payload.get("instructions") or package_id).strip()
    scope_paths = list(payload.get("scope_paths") or [])
    return {
        **payload,
        "goal_id": str(payload.get("goal_id") or package_id),
        "title": title,
        "goal": str(payload.get("goal") or payload.get("instructions") or title),
        "description": str(payload.get("description") or payload.get("instructions") or title),
        "target_files": list(payload.get("target_files") or scope_paths),
        "requirements": list(payload.get("requirements") or ["sealed_runtime_dispatch"]),
        "hard_boundary": payload.get("hard_boundary") or ["RuntimeDispatcher required"],
        "non_mainline_issue_reporting": payload.get("non_mainline_issue_reporting") or ["report all"],
        "validation_commands": list(payload.get("validation_commands") or []),
        "completion_report_format": payload.get("completion_report_format") or ["runtime progress"],
        "metadata": {
            **(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
            "scheduler_compatibility_payload": True,
            "original_scheduler_payload": payload,
        },
    }


def _read_memory(repo_root: str, package_id: str) -> dict[str, Any]:
    root = Path(repo_root)
    record_path = root / "workspace" / "runtime_work_packages" / f"{package_id}.json"
    if not record_path.is_file():
        return {}

    record = json.loads(record_path.read_text(encoding="utf-8"))
    progress = record.get("progress_snapshot") if isinstance(record.get("progress_snapshot"), dict) else {}
    memory_id = progress.get("memory_record_id") or record.get("memory_record_id")

    if memory_id:
        memory_path = root / "workspace" / "work_package_memory" / "records" / f"{memory_id}.json"
        if memory_path.is_file():
            return json.loads(memory_path.read_text(encoding="utf-8"))

    return record


def _print_readable_report(repo_root: str, package_id: str, fallback: dict[str, Any] | None = None) -> None:
    data = _read_memory(repo_root, package_id) or fallback or {}
    progress = data.get("progress_snapshot") if isinstance(data.get("progress_snapshot"), dict) else {}
    evidence = data.get("execution_evidence_summary") if isinstance(data.get("execution_evidence_summary"), dict) else {}
    tests = data.get("test_result_summary") if isinstance(data.get("test_result_summary"), dict) else {}
    objective = data.get("original_objective") if isinstance(data.get("original_objective"), dict) else {}

    status = data.get("final_status") or data.get("lifecycle_state") or progress.get("lifecycle_state") or "unknown"
    title = objective.get("title") or data.get("title") or ""
    package_objective = data.get("objective") or objective.get("goal") or data.get("goal") or ""
    validation_results = data.get("validation_results") or data.get("validation_summary", {}).get("results") if isinstance(data.get("validation_summary"), dict) else data.get("validation_results") or []
    completion_status = data.get("completion_criteria_status") or {}

    print("# ZERO Work Package Report")
    print()
    print(f"Package: {package_id}")
    print(f"Title: {title}")
    print(f"Objective: {package_objective}")
    print(f"Status: {status}")
    print(f"Memory: {data.get('memory_status') or 'committed' if status == 'completed' else data.get('memory_status') or ''}")
    print()
    print("## Progress")
    print(f"- Completed steps: {tests.get('completed_steps', progress.get('completed_steps', 0))}")
    print(f"- Failed steps: {tests.get('failed_steps', progress.get('failed_steps', 0))}")
    print(f"- Remaining steps: {progress.get('remaining_steps', 0)}")
    print(f"- Evidence count: {evidence.get('evidence_count', 0)}")
    print()
    print("## Validation Commands")
    for cmd in tests.get("validation_commands") or data.get("validation_commands") or []:
        print(f"- {cmd}")
    if not (tests.get("validation_commands") or data.get("validation_commands")):
        print("- None")
    print()
    print("## Validation Results")
    for item in validation_results if isinstance(validation_results, list) else []:
        print(f"- `{item.get('command')}` exit={item.get('exit_code')} ok={item.get('ok')}")
    if not validation_results:
        print("- None")
    print()
    print("## Modified Files")
    files = [str(x) for x in data.get("modified_files_summary") or [] if str(x).strip()]
    for item in files:
        print(f"- {item}")
    if not files:
        print("- None")
    print()
    print("## Non-mainline Findings")
    findings = data.get("non_mainline_findings") or []
    for item in findings:
        print(f"- {item}")
    if not findings:
        print("- None")
    print()
    print("## Root Cause")
    print(data.get("root_cause") or progress.get("root_cause") or "None")
    print()
    print("## Remaining Failures")
    remaining = data.get("remaining_failures") or progress.get("remaining_failures") or []
    for item in remaining:
        print(f"- {item}")
    if not remaining:
        print("- None")
    print()
    print("## Completion Criteria")
    if isinstance(completion_status, dict):
        print(f"- Met: {completion_status.get('met')}")
        for item in completion_status.get("criteria") or []:
            print(f"- {item}")
    else:
        print("- None")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.work_package_cli")
    parser.add_argument("--repo-root", default=os.environ.get("ZERO_REPO_ROOT", "."))
    sub = parser.add_subparsers(dest="command", required=True)

    submit = sub.add_parser("submit")
    submit.add_argument("package_file")

    intake = sub.add_parser("intake")
    intake_source = intake.add_mutually_exclusive_group(required=True)
    intake_source.add_argument("--file")
    intake_source.add_argument("--text")

    run_validation = sub.add_parser("run-validation")
    run_validation.add_argument("package_id")

    for name in ("status", "plan", "run", "progress", "summary", "report", "memory", "pause", "resume", "cancel"):
        cmd = sub.add_parser(name)
        cmd.add_argument("package_id")
        if name in {"summary", "report", "memory"}:
            cmd.add_argument("--json", action="store_true")
        if name in {"summary", "report"}:
            cmd.add_argument("--format", choices=("json", "markdown", "report"))

    sub.add_parser("memory-status")

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
            if _is_scheduler_work_package(payload):
                result = WorkPackageScheduler(repo_root=args.repo_root).submit(payload)
            else:
                result = operator.submit_package(payload)

        elif args.command == "intake":
            source_text = (
                Path(args.file).read_text(encoding="utf-8")
                if args.file
                else str(args.text or "")
            )
            payload = package_payload_from_text(source_text)
            result = operator.intake_package(payload)

        elif args.command == "run-validation":
            result = operator.run_validation_only(args.package_id)

        elif args.command == "status":
            result = operator.package_status(args.package_id)

        elif args.command == "plan":
            result = operator.plan_package(args.package_id)

        elif args.command == "run":
            result = operator.run_package(args.package_id)

        elif args.command == "progress":
            result = operator.package_progress(args.package_id)

        elif args.command == "summary":
            result = operator.package_summary(args.package_id)
            output_format = "json" if args.json else (args.format or "json")
            if output_format in {"markdown", "report"}:
                _print_readable_report(args.repo_root, args.package_id, result)
                return 0
            _print_json({"ok": True, **result})
            return 0

        elif args.command == "report":
            result = operator.package_report(args.package_id)
            output_format = "json" if args.json else (args.format or "json")
            if output_format in {"markdown", "report"}:
                _print_readable_report(args.repo_root, args.package_id, result)
                return 0
            _print_json({"ok": True, "result": result})
            return 0

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
