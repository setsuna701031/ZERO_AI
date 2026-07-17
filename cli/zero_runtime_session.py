from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.runtime.runtime_end_to_end_orchestrator import (cancel_runtime_session, create_runtime_session,
    load_runtime_session, resume_runtime_session, save_runtime_session)

def _read(path: Any) -> dict[str, Any]:
    try: value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_json_file") from exc
    if not isinstance(value, Mapping): raise ValueError("json_object_required")
    return dict(value)

def projection(session: Mapping[str, Any]) -> dict[str, Any]:
    return {key: session.get(key) for key in ("contract", "session_id", "session_status", "task_id", "current_phase", "required_action", "required_input_contract", "completed", "failure")}

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero-runtime-session"); commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create"); create.add_argument("natural_task"); create.add_argument("--target-root", required=True); create.add_argument("--workspace-root", required=True); create.add_argument("--session-path", required=True); create.add_argument("--now")
    status = commands.add_parser("status"); status.add_argument("session_path")
    resume = commands.add_parser("resume"); resume.add_argument("session_path"); resume.add_argument("--operator-input", required=True); resume.add_argument("--target-root", required=True); resume.add_argument("--workspace-root", required=True); resume.add_argument("--now")
    cancel = commands.add_parser("cancel"); cancel.add_argument("session_path"); cancel.add_argument("--operator-id", required=True); cancel.add_argument("--now")
    history = commands.add_parser("history"); history.add_argument("session_path")
    artifacts = commands.add_parser("artifacts"); artifacts.add_argument("session_path")
    return parser

def run(argv: Sequence[str] | None = None) -> tuple[dict[str, Any], int]:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create": result = create_runtime_session(args.natural_task, target_root=args.target_root, workspace_root=args.workspace_root, session_path=args.session_path, now=args.now)
        elif args.command == "status": result = load_runtime_session(args.session_path)
        elif args.command == "resume":
            result = load_runtime_session(args.session_path, target_root=args.target_root, workspace_root=args.workspace_root, now=args.now)
            result = resume_runtime_session(result, operator_input=_read(args.operator_input), target_root=args.target_root, workspace_root=args.workspace_root, now=args.now)
            result = save_runtime_session(result, args.session_path)
        elif args.command == "cancel":
            result = cancel_runtime_session(load_runtime_session(args.session_path), operator_id=args.operator_id, now=args.now); result = save_runtime_session(result, args.session_path)
        elif args.command == "history": return {"phase_history": load_runtime_session(args.session_path).get("phase_history", []), "checkpoints": load_runtime_session(args.session_path).get("checkpoints", [])}, 0
        else: return {"artifacts": load_runtime_session(args.session_path).get("artifacts", {}), "artifact_fingerprints": load_runtime_session(args.session_path).get("artifact_fingerprints", {})}, 0
        output = projection(result); status = result.get("session_status")
        return output, 3 if status == "failed" else 1 if status in {"blocked", "expired", "cancelled"} else 0
    except ValueError as exc:
        message = str(exc); code = 4 if any(word in message for word in ("fingerprint", "mismatch", "transition", "unsafe_session")) else 2
        return {"ok": False, "error": message}, code

def main(argv: Sequence[str] | None = None) -> int:
    result, code = run(argv); print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return code

if __name__ == "__main__": raise SystemExit(main())

__all__ = ["build_parser", "main", "projection", "run"]
