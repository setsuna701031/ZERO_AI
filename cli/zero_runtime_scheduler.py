from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.runtime.runtime_session_queue import (create_scheduler_state, enqueue_session, load_scheduler_state,
    ordered_entries, save_scheduler_state)
from core.runtime.runtime_session_scheduler import (cancel_scheduled_session, compute_scheduler_stats, dispatch_session,
    lease_next_session, recover_scheduler_state, resume_ready_sessions, submit_operator_input)

def _read(path: Any) -> dict[str, Any]:
    try: value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_json_file") from exc
    if not isinstance(value, Mapping): raise ValueError("json_object_required")
    return dict(value)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero-runtime-scheduler"); commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init"); init.add_argument("--state-path", required=True); init.add_argument("--now")
    enqueue = commands.add_parser("enqueue"); enqueue.add_argument("state_path"); enqueue.add_argument("session_path"); enqueue.add_argument("--priority", default="normal"); enqueue.add_argument("--target-root"); enqueue.add_argument("--workspace-root"); enqueue.add_argument("--now")
    for name in ("status", "list", "waiting", "stats"):
        item = commands.add_parser(name); item.add_argument("state_path")
    lease = commands.add_parser("lease-next"); lease.add_argument("state_path"); lease.add_argument("--owner", required=True); lease.add_argument("--now")
    dispatch = commands.add_parser("dispatch"); dispatch.add_argument("state_path"); dispatch.add_argument("--owner", required=True); dispatch.add_argument("--target-root", required=True); dispatch.add_argument("--workspace-root", required=True); dispatch.add_argument("--now")
    submit = commands.add_parser("submit-input"); submit.add_argument("state_path"); submit.add_argument("operator_input"); submit.add_argument("--target-root", required=True); submit.add_argument("--workspace-root", required=True); submit.add_argument("--now")
    ready = commands.add_parser("resume-ready"); ready.add_argument("state_path"); ready.add_argument("--owner", required=True); ready.add_argument("--max-sessions", type=int, required=True); ready.add_argument("--target-root", required=True); ready.add_argument("--workspace-root", required=True); ready.add_argument("--now")
    cancel = commands.add_parser("cancel"); cancel.add_argument("state_path"); cancel.add_argument("session_id"); cancel.add_argument("--operator-id", required=True); cancel.add_argument("--now")
    return parser

def _summary(state: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract": state.get("contract"), "scheduler_id": state.get("scheduler_id"), "scheduler_status": state.get("scheduler_status"),
        "queue_version": state.get("queue_version"), "stats": compute_scheduler_stats(state), "updated_at": state.get("updated_at")}

def run(argv: Sequence[str] | None = None) -> tuple[dict[str, Any], int]:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init": state = save_scheduler_state(create_scheduler_state(state_path=args.state_path, now=args.now), args.state_path); return _summary(state), 0
        state = load_scheduler_state(args.state_path)
        if args.command == "enqueue": state = enqueue_session(state, args.session_path, priority=args.priority, target_root=args.target_root, workspace_root=args.workspace_root, now=args.now); output = {"enqueued": True, "entries": ordered_entries(state)}
        elif args.command == "status": return _summary(recover_scheduler_state(state)), 0
        elif args.command == "list": return {"entries": ordered_entries(state)}, 0
        elif args.command == "waiting": return {"waiting_operator_sessions": state.get("waiting_operator_sessions", [])}, 0
        elif args.command == "stats": return compute_scheduler_stats(state), 0
        elif args.command == "lease-next": state, lease = lease_next_session(state, owner=args.owner, now=args.now); output = {"lease": lease}; code = 0 if lease else 1; save_scheduler_state(state, args.state_path); return output, code
        elif args.command == "dispatch": state, output = dispatch_session(state, owner=args.owner, target_root=args.target_root, workspace_root=args.workspace_root, now=args.now)
        elif args.command == "submit-input": state, session = submit_operator_input(state, _read(args.operator_input), target_root=args.target_root, workspace_root=args.workspace_root, now=args.now); output = {"session_id": session.get("session_id"), "session_status": session.get("session_status"), "required_action": session.get("required_action")}
        elif args.command == "resume-ready": state, results = resume_ready_sessions(state, owner=args.owner, max_sessions=args.max_sessions, target_root=args.target_root, workspace_root=args.workspace_root, now=args.now); output = {"results": results, "count": len(results)}
        else: state, session = cancel_scheduled_session(state, args.session_id, operator_id=args.operator_id, now=args.now); output = {"session_id": session.get("session_id"), "session_status": session.get("session_status")}
        state = save_scheduler_state(state, args.state_path); status = output.get("session_status")
        return output, 3 if status == "failed" else 1 if status in {"blocked", "expired"} or output.get("reason") == "no_dispatchable_session" else 0
    except ValueError as exc:
        message = str(exc); code = 4 if any(word in message for word in ("fingerprint", "lease", "mismatch", "duplicate", "tamper")) else 2
        return {"ok": False, "error": message}, code

def main(argv: Sequence[str] | None = None) -> int:
    result, code = run(argv); print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return code

if __name__ == "__main__": raise SystemExit(main())
__all__ = ["build_parser", "main", "run"]
