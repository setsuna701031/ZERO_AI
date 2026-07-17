from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from core.runtime.runtime_natural_language_mission_bootstrap import NaturalLanguageMissionBootstrap


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero-mission")
    parser.add_argument("mission", nargs="?")
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--target-root")
    parser.add_argument("--operator-id", default="zero-mission-cli")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume")
    parser.add_argument("--show-plan")
    parser.add_argument("--status")
    parser.add_argument("--approve")
    parser.add_argument("--deny")
    parser.add_argument("--scope", action="append")
    parser.add_argument("--reason", default="")
    parser.add_argument("--force-new", action="store_true")
    parser.add_argument("--max-iterations", type=int)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--now")
    return parser


def _summary(value: dict) -> str:
    mission = value.get("mission_reference") or {}
    session = value.get("session_reference") or {}
    graph = value.get("graph_reference") or {}
    lines = [
        f"Mission ID: {mission.get('mission_id', '-')}",
        f"Session ID: {value.get('session_id') or session.get('session_id', '-')}",
        f"Status: {value.get('session_status') or value.get('bootstrap_status') or value.get('session_status', '-')}",
        f"Goals: {len(graph.get('goal_order') or [])}",
        f"Completed: {1 if (value.get('session_status') or value.get('bootstrap_status')) == 'completed' else 0}",
        f"Blocked: {1 if (value.get('session_status') or value.get('bootstrap_status')) == 'blocked' else 0}",
        f"Artifact: {value.get('artifact_path', '-')}",
    ]
    return "\n".join(lines)


def _emit(value: dict, json_output: bool) -> None:
    if json_output:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    else:
        print(_summary(value))


def _exit(value: dict, *, resume: bool = False) -> int:
    status = value.get("bootstrap_status") or value.get("mission_status") or value.get("session_status")
    if value.get("approval_status") == "denied": return 3
    if status in {"blocked", "waiting_for_plan_confirmation", "denied"}: return 3
    if status == "failed": return 1
    if resume and status in {"paused", "stopped"}: return 4
    return 0


def _execute(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace_root).resolve(strict=True)
    bootstrap = NaturalLanguageMissionBootstrap()
    control = args.show_plan or args.status or args.approve or args.deny
    if control:
        from core.runtime.runtime_mission_execution_approval_flow import ensure_pending_execution_plan, execute_approved_mission, mission_execution_status, review_mission_execution_plan
        root = workspace
        candidates = list(root.rglob("bootstrap.json"))
        sibling = root.parent / ".zero_ai_runtime"
        if sibling.exists(): candidates += list(sibling.rglob("bootstrap.json"))
        artifact_path = None
        for item in candidates:
            try: value = json.loads(item.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError): continue
            if control in {value.get("bootstrap_id"), (value.get("session_reference") or {}).get("session_id")} or str(item.resolve()) == str(control): artifact_path = item; break
        if artifact_path is None: raise ValueError("mission_session_not_found")
        if args.show_plan:
            result = ensure_pending_execution_plan(artifact_path, now=args.now)
        elif args.status:
            result = mission_execution_status(artifact_path, now=args.now)
        elif args.deny:
            result = review_mission_execution_plan(artifact_path, decision="deny", operator_id=args.operator_id, reason=args.reason, now=args.now)
        else:
            review_mission_execution_plan(artifact_path, decision="approve", operator_id=args.operator_id, approved_scope=args.scope, reason=args.reason, now=args.now)
            result = execute_approved_mission(artifact_path, operator_id=args.operator_id, max_iterations=args.max_iterations if args.max_iterations is not None else 20, now=args.now)
        _emit(result, args.json_output); return _exit(result)
    if args.resume:
        result = bootstrap.resume(args.resume, workspace_root=workspace, max_iterations=args.max_iterations if args.max_iterations is not None else 1, now=args.now)
        _emit(result, args.json_output); return _exit(result, resume=True)
    if not args.mission: raise ValueError("natural_language_mission_required")
    result = bootstrap.run(args.mission, workspace_root=workspace, target_root=args.target_root, operator_id=args.operator_id, prepare_only=args.prepare_only, force_new=args.force_new, max_iterations=args.max_iterations if args.max_iterations is not None else 1, now=args.now)
    _emit(result, args.json_output); return _exit(result)


def _interactive(args: argparse.Namespace) -> int:
    print("ZERO Mission Console")
    print("輸入自然語言任務；輸入 exit 離開。")
    result = 0
    while True:
        try: text = input("ZERO> ").strip()
        except EOFError: break
        if text.casefold() in {"exit", "quit"}: break
        if not text: continue
        current = argparse.Namespace(**vars(args)); current.mission = text
        try: result = _execute(current)
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr); result = 2
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.mission is None and not any((args.resume, args.show_plan, args.status, args.approve, args.deny)): return _interactive(args)
        return _execute(args)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 4 if args.resume else 2


if __name__ == "__main__": raise SystemExit(main())


__all__ = ["build_parser", "main"]
