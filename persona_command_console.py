#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZERO Persona Command Console - Z5 takeover version

Place this file at:
    E:\zero_ai\persona_command_console.py

execute always runs:
    python persona_workcopy_executor.py run
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, List


SELF_EDIT_ROOT = Path("workspace") / "self_edit"
WORKCOPY_DIR = SELF_EDIT_ROOT / "zero_ai_workcopy"
PERSONA_INBOX = SELF_EDIT_ROOT / "persona_inbox"
PERSONA_OUTBOX = SELF_EDIT_ROOT / "persona_outbox"
PERSONA_EXECUTION = SELF_EDIT_ROOT / "persona_execution"
REVIEW_DIR = SELF_EDIT_ROOT / "review"

LATEST_COMMAND_TXT = PERSONA_INBOX / "latest_command.txt"
COMMANDS_JSON = PERSONA_INBOX / "commands.json"
PERSONA_REPLY_TXT = PERSONA_OUTBOX / "persona_reply.txt"

PERSONA_STATUS_TXT = SELF_EDIT_ROOT / "persona_status.txt"
EXECUTION_STATUS_TXT = PERSONA_EXECUTION / "execution_status.txt"
EXECUTION_PLAN_TXT = PERSONA_EXECUTION / "execution_plan.txt"
RETRY_LOG_JSON = PERSONA_EXECUTION / "retry_log.json"

CHANGED_FILES_TXT = REVIEW_DIR / "changed_files.txt"
MANIFEST_JSON = REVIEW_DIR / "manifest.json"


HIGH_RISK_TERMS = {
    "apply back", "apply-back", "套回", "覆蓋本體", "刪除本體",
    "delete live", "remove live", "force push", "merge", "deploy",
    "token", "secret", "password", "format", "rmdir", "rm ",
}


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    PERSONA_INBOX.mkdir(parents=True, exist_ok=True)
    PERSONA_OUTBOX.mkdir(parents=True, exist_ok=True)
    PERSONA_EXECUTION.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def read_text(path: Path, fallback: str = "") -> str:
    if not path.exists():
        return fallback
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return f"[read failed] {path}: {type(exc).__name__}: {exc}"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def classify_risk(command: str) -> str:
    lower = command.lower()
    for term in HIGH_RISK_TERMS:
        if term.lower() in lower:
            return "high"
    return "normal"


def workcopy_ready() -> bool:
    return WORKCOPY_DIR.exists() and WORKCOPY_DIR.is_dir()


def run_command(args: List[str]) -> int:
    proc = subprocess.run(args, text=True, encoding="utf-8", errors="ignore", capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n")
    return proc.returncode


def command_ask(command_text: str) -> int:
    ensure_dirs()
    risk = classify_risk(command_text)
    payload = {
        "time": now(),
        "target": str(WORKCOPY_DIR),
        "risk": risk,
        "command": command_text,
        "boundary": {"live_repo_write_allowed": False, "workcopy_write_allowed": True, "apply_back_auto_run": False},
    }

    commands = read_json(COMMANDS_JSON, [])
    if not isinstance(commands, list):
        commands = []
    commands.append(payload)

    write_text(LATEST_COMMAND_TXT, command_text + "\n")
    write_json(COMMANDS_JSON, commands)
    write_text(PERSONA_REPLY_TXT, "[ZERO PERSONA REPLY]\nResult : accepted\nNext:\npython persona_command_console.py execute\n")

    print("[ZERO PERSONA COMMAND]")
    print("Time   : " + payload["time"])
    print("Target : " + str(WORKCOPY_DIR))
    print("Risk   : " + risk)
    print("")
    print("[USER REQUEST]")
    print(command_text)
    print("")
    print("[BOUNDARY]")
    print("Live repo write allowed : False")
    print("Workcopy write allowed  : True")
    print("Apply back auto-run     : False")
    print("")
    print("[RESULT]")
    print("Command accepted into Persona inbox.")
    print("Next execution target is the self-edit workcopy.")
    print("Run:")
    print("python persona_command_console.py execute")
    print("")
    print("[FILES WRITTEN]")
    print("- " + str(LATEST_COMMAND_TXT))
    print("- " + str(COMMANDS_JSON))
    print("- " + str(PERSONA_REPLY_TXT))
    print("")
    print("[NEXT]")
    print("python persona_command_console.py execute")
    return 0


def command_execute() -> int:
    ensure_dirs()
    if not workcopy_ready():
        print("[ZERO PERSONA EXECUTE]")
        print("Workcopy is missing.")
        print("Run:")
        print("python self_edit_zero.py prepare")
        return 2
    if not Path("persona_workcopy_executor.py").exists():
        print("[ZERO PERSONA EXECUTE]")
        print("Missing persona_workcopy_executor.py in repo root.")
        return 2
    rc = run_command([sys.executable, "persona_workcopy_executor.py", "run"])
    if rc != 0:
        print("")
        print("[ZERO PERSONA EXECUTE ERROR]")
        print("Executor returned non-zero exit code: " + str(rc))
    return rc


def command_review() -> int:
    ensure_dirs()
    if not Path("self_edit_zero.py").exists():
        print("[ZERO PERSONA REVIEW]")
        print("Missing self_edit_zero.py.")
        return 2
    rc = run_command([sys.executable, "self_edit_zero.py", "package-review"])
    if rc != 0:
        print("")
        print("[ZERO PERSONA REVIEW ERROR]")
        print("self_edit_zero.py package-review returned: " + str(rc))
        return rc

    print("")
    print("[ZERO REVIEW SUMMARY]")
    changed = read_text(CHANGED_FILES_TXT).splitlines()
    print("")
    print("[CHANGED FILES]")
    if changed:
        for item in changed:
            print(item)
    else:
        print("(none)")

    manifest = read_json(MANIFEST_JSON, {})
    print("")
    print("[MANIFEST]")
    if isinstance(manifest, dict):
        summary = manifest.get("summary") or {}
        if isinstance(summary, dict):
            print("changed_file_count: " + str(summary.get("changed_file_count", len(changed))))
        files = manifest.get("files") or []
        if files:
            for item in files:
                if isinstance(item, dict):
                    print("- " + str(item.get("status")) + ": " + str(item.get("path")))
    else:
        print("(manifest unreadable)")

    print("")
    print("[GATE]")
    print("Apply back is still blocked until you explicitly run:")
    print("python self_edit_apply_back.py --confirm-reviewed")
    return 0


def command_status() -> int:
    ensure_dirs()
    print("[ZERO PERSONA STATUS BRIDGE]")
    print("Workcopy ready : " + str(workcopy_ready()))
    print("Workcopy path  : " + str(WORKCOPY_DIR))
    print("Executor status: " + str(EXECUTION_STATUS_TXT))
    print("Execution plan : " + str(EXECUTION_PLAN_TXT))
    print("Retry log      : " + str(RETRY_LOG_JSON))
    print("")
    if EXECUTION_STATUS_TXT.exists():
        print(read_text(EXECUTION_STATUS_TXT), end="")
    elif PERSONA_STATUS_TXT.exists():
        print(read_text(PERSONA_STATUS_TXT), end="")
    else:
        print("No status generated yet.")
    return 0


def command_plan() -> int:
    ensure_dirs()
    print(read_text(EXECUTION_PLAN_TXT, "[ZERO PERSONA PLAN]\nNo execution plan yet.\n"), end="")
    return 0


def command_inspect() -> int:
    ensure_dirs()
    print(read_text(EXECUTION_STATUS_TXT, "[ZERO PERSONA INSPECT]\nNo execution status yet.\n"), end="")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ZERO Persona Command Console - Z5 takeover")
    sub = parser.add_subparsers(dest="command")
    ask_parser = sub.add_parser("ask")
    ask_parser.add_argument("text", nargs="+")
    sub.add_parser("execute")
    sub.add_parser("review")
    sub.add_parser("status")
    sub.add_parser("plan")
    sub.add_parser("inspect")
    args = parser.parse_args()

    if args.command == "ask":
        return command_ask(" ".join(args.text))
    if args.command == "execute":
        return command_execute()
    if args.command == "review":
        return command_review()
    if args.command == "status":
        return command_status()
    if args.command == "plan":
        return command_plan()
    if args.command == "inspect":
        return command_inspect()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
