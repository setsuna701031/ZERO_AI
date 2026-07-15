from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys
from typing import Any, Sequence

from core.agent.runtime_agent_controller import RuntimeAgentController
from core.agent.runtime_persistent_agent_loop import RuntimePersistentAgentLoop


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--state-root")
    parser.add_argument("--now")
    parser.add_argument("--json", action="store_true", dest="json_output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero-agent")
    sub = parser.add_subparsers(dest="command")
    add = sub.add_parser("add"); add.add_argument("mission"); add.add_argument("--target-root"); add.add_argument("--priority", default="normal"); add.add_argument("--tag", action="append"); add.add_argument("--max-attempts", type=int, default=3); add.add_argument("--input-id"); add.add_argument("--not-before"); _common(add)
    listing = sub.add_parser("list", aliases=["missions"]); listing.add_argument("--status"); _common(listing)
    show = sub.add_parser("show"); show.add_argument("entry_id"); _common(show)
    run = sub.add_parser("run"); run.add_argument("--max-missions", type=int, default=1); run.add_argument("--max-iterations", type=int, default=10); run.add_argument("--stop-on-failure", action="store_true"); run.add_argument("--stop-on-blocked", action="store_true"); run.add_argument("--idle-exit", action="store_true", default=True); run.add_argument("--wait-seconds", type=float, default=0.0); _common(run)
    for name in ("status", "pause", "resume", "stop"):
        _common(sub.add_parser(name))
    priority = sub.add_parser("priority"); priority.add_argument("entry_id"); priority.add_argument("priority"); _common(priority)
    cancel = sub.add_parser("cancel"); cancel.add_argument("entry_id"); _common(cancel)
    approve = sub.add_parser("approve"); approve.add_argument("entry_id"); approve.add_argument("--operator-id", required=True); _common(approve)
    deny = sub.add_parser("deny"); deny.add_argument("entry_id"); deny.add_argument("--operator-id", required=True); deny.add_argument("--reason", required=True); _common(deny)
    reflection = sub.add_parser("reflection"); reflection.add_argument("entry_or_action"); reflection.add_argument("entry_id", nargs="?"); _common(reflection)
    memory = sub.add_parser("memory"); memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    memory_list = memory_sub.add_parser("list"); memory_list.add_argument("--outcome"); memory_list.add_argument("--limit", type=int); _common(memory_list)
    memory_search = memory_sub.add_parser("search"); memory_search.add_argument("text"); memory_search.add_argument("--top-k", type=int, default=3); _common(memory_search)
    memory_show = memory_sub.add_parser("show"); memory_show.add_argument("experience_id"); _common(memory_show)
    planning = sub.add_parser("planning"); planning.add_argument("entry_or_action"); planning.add_argument("entry_or_mission", nargs="?"); planning.add_argument("--target-root"); _common(planning)
    return parser


def _controller(args: argparse.Namespace) -> RuntimeAgentController:
    return RuntimeAgentController(workspace_root=args.workspace_root, state_root=args.state_root, create_workspace=args.command == "add", now=args.now)


def _summary(value: Any, command: str) -> str:
    if command == "add": return f"Entry ID: {value['entry_id']}\nPriority: {value['priority']}\nStatus: {value['status']}\nInput: {value['original_input']}"
    if command in {"list", "missions"}:
        if not value: return "No missions."
        return "\n".join(f"{item['entry_id']} | {item['priority']} | {item['status']} | {item.get('mission_id') or '-'} | {item.get('mission_session_id') or '-'} | {item['original_input']} | {item['updated_at']}" for item in value)
    if command == "run": return f"Agent ID: {value['agent_id']}\nStatus: {value['agent_status']}\nSelected: {len(value['selected_entry_ids'])}\nStarted: {value['started']}\nCompleted: {value['completed']}\nWaiting Approval: {value['waiting_approval']}\nBlocked: {value['blocked']}\nFailed: {value['failed']}"
    if command == "status": return f"Agent ID: {value['agent_id']}\nStatus: {value['agent_status']}\nCurrent Entry: {value.get('current_entry_id') or '-'}\nStarted: {value['missions_started']}\nCompleted: {value['missions_completed']}\nBlocked: {value['missions_blocked']}\nFailed: {value['missions_failed']}"
    if command == "reflection":
        reflection = value["reflection"]; experience = value["experience"]
        return f"Entry ID: {reflection['entry_id']}\nMission ID: {reflection.get('mission_id') or '-'}\nOutcome: {reflection['outcome']}\nSummary: {reflection['summary']}\nSucceeded: {', '.join(reflection['what_succeeded']) or '-'}\nFailed: {', '.join(reflection['what_failed']) or '-'}\nBlocked: {', '.join(reflection['what_was_blocked']) or '-'}\nLessons: {', '.join(reflection['lessons']) or '-'}\nReusable Patterns: {', '.join(reflection['reusable_patterns']) or '-'}\nAvoid Patterns: {', '.join(reflection['avoid_patterns']) or '-'}\nEvidence Quality: {reflection['evidence_quality']}\nExperience ID: {experience['experience_id']}"
    if command == "memory" and isinstance(value, dict) and "matches" in value:
        return "No matching experiences." if not value["matches"] else "\n".join(f"{item['experience_id']} | {item['similarity_score']:.6f} | {item['outcome']} | {item.get('summary') or '-'} | {', '.join(item['matched_tokens']) or '-'} | {', '.join(item['lessons']) or '-'}" for item in value["matches"])
    if command == "memory" and isinstance(value, list):
        return "No experiences." if not value else "\n".join(f"{item['experience_id']} | {item['outcome']} | {item.get('summary') or '-'} | {item['created_at']}" for item in value)
    if command == "planning":
        return f"Entry ID: {value.get('entry_id') or '-'}\nFeedback ID: {value.get('feedback_id') or '-'}\nExperiences Used: {', '.join(str(item.get('experience_id')) for item in value.get('experiences_used', [])) or '-'}\nMatched Tokens: {', '.join(value.get('matched_tokens', [])) or '-'}\nApplied Recommendations: {', '.join(str(item.get('recommendation')) for item in value.get('applied_recommendations', [])) or '-'}\nIgnored Recommendations: {', '.join(str(item.get('recommendation')) for item in value.get('ignored_recommendations', [])) or '-'}\nGoal Plan Before: {len(value.get('goal_plan_before', []))}\nGoal Plan After: {len(value.get('goal_plan_after', []))}\nAdded Validations: {', '.join(value.get('added_validations', [])) or '-'}\nRisk Notes: {', '.join(value.get('risk_notes', [])) or '-'}\nScope Preserved: {value.get('scope_preserved')}\nApproval Preserved: {value.get('approval_preserved')}\nConfidence: {value.get('confidence', 0.0)}"
    if isinstance(value, dict) and "entry_id" in value: return f"Entry ID: {value['entry_id']}\nPriority: {value['priority']}\nStatus: {value['status']}\nMission ID: {value.get('mission_id') or '-'}\nSession ID: {value.get('mission_session_id') or '-'}\nInput: {value['original_input']}"
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _emit(value: Any, command: str, json_output: bool) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True) if json_output else _summary(value, command))


def _execute(args: argparse.Namespace) -> tuple[Any, int]:
    controller = _controller(args); command = args.command
    if command == "add": value = controller.add(args.mission, priority=args.priority, target_root=args.target_root, tags=args.tag, max_attempts=args.max_attempts, input_id=args.input_id, not_before=args.not_before, now=args.now)
    elif command in {"list", "missions"}: value = controller.list(status=args.status)
    elif command == "show": value = controller.show(args.entry_id)
    elif command == "run": value = RuntimePersistentAgentLoop(controller).run(max_missions=args.max_missions, max_iterations=args.max_iterations, stop_on_failure=args.stop_on_failure, stop_on_blocked=args.stop_on_blocked, idle_exit=args.idle_exit, wait_seconds=args.wait_seconds, now=args.now)
    elif command == "status": value = controller.load_state()
    elif command == "pause": value = controller.pause(now=args.now)
    elif command == "resume": value = controller.resume(now=args.now)
    elif command == "stop": value = controller.stop(now=args.now)
    elif command == "priority": value = controller.priority(args.entry_id, args.priority, now=args.now)
    elif command == "cancel": value = controller.cancel(args.entry_id, now=args.now)
    elif command == "approve": value = controller.approve(args.entry_id, operator_id=args.operator_id, now=args.now)
    elif command == "deny": value = controller.approve(args.entry_id, operator_id=args.operator_id, deny=True, reason=args.reason, now=args.now)
    elif command == "reflection":
        rebuild = args.entry_or_action == "rebuild"
        entry_id = args.entry_id if rebuild else args.entry_or_action
        if rebuild and not entry_id: raise ValueError("reflection_entry_id_required")
        value = controller.reflect(entry_id, rebuild=rebuild, now=args.now)
    elif command == "memory" and args.memory_command == "list": value = controller.memory_list(outcome=args.outcome, limit=args.limit)
    elif command == "memory" and args.memory_command == "search": value = controller.memory_search(args.text, top_k=args.top_k)
    elif command == "memory" and args.memory_command == "show": value = controller.memory_show(args.experience_id)
    elif command == "planning":
        if args.entry_or_action == "preview":
            if not args.entry_or_mission: raise ValueError("planning_preview_mission_required")
            value = controller.planning_preview(args.entry_or_mission, target_root=args.target_root, now=args.now)
        elif args.entry_or_action == "explain":
            if not args.entry_or_mission: raise ValueError("planning_entry_id_required")
            value = controller.planning(args.entry_or_mission, explain=True)
        else: value = controller.planning(args.entry_or_action)
    else: raise ValueError("agent_command_required")
    status = value.get("status") if isinstance(value, dict) else None
    waiting = isinstance(value, dict) and (int(value.get("waiting_approval") or 0) > 0 or int(value.get("blocked") or 0) > 0)
    code = 3 if status in {"waiting_for_approval", "blocked"} or (command == "run" and waiting) else 5 if command in {"pause", "stop"} else 1 if status == "failed" else 0
    return value, code


def _interactive(workspace_root: str = ".", state_root: str | None = None) -> int:
    print("ZERO Autonomous Agent")
    print("輸入 help 查看指令。")
    while True:
        try: text = input("ZERO> ").strip()
        except EOFError: return 0
        if not text: continue
        if text.casefold() in {"exit", "quit"}: return 0
        if text.casefold() == "help": print("add <mission> | missions | show <id> | run | status | reflection <id> | reflection rebuild <id> | memory list | memory search <text> | memory show <id> | planning <id> | planning explain <id> | planning preview <mission> | pause | resume | stop | approve <id> <operator> | deny <id> <operator> <reason> | priority <id> high|normal|low | cancel <id> | exit"); continue
        try:
            parts = shlex.split(text); command = parts[0].casefold()
            if command == "add" and len(parts) >= 2: parts = ["add", " ".join(parts[1:])]
            elif command == "missions": parts[0] = "list"
            elif command == "approve" and len(parts) == 3: parts = ["approve", parts[1], "--operator-id", parts[2]]
            elif command == "deny" and len(parts) >= 4: parts = ["deny", parts[1], "--operator-id", parts[2], "--reason", " ".join(parts[3:])]
            elif command == "planning" and len(parts) >= 3 and parts[1].casefold() == "preview": parts = ["planning", "preview", " ".join(parts[2:])]
            parts += ["--workspace-root", workspace_root]
            if state_root: parts += ["--state-root", state_root]
            args = build_parser().parse_args(parts); value, _ = _execute(args); _emit(value, args.command, False)
        except (OSError, ValueError, SystemExit) as exc: print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    values = list(argv) if argv is not None else sys.argv[1:]
    if not values: return _interactive()
    try:
        args = build_parser().parse_args(values)
        if args.command is None: return _interactive()
        value, code = _execute(args); _emit(value, args.command, args.json_output); return code
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        json_output = "--json" in values
        message = {"error": str(exc)}
        print(json.dumps(message, ensure_ascii=False) if json_output else f"Error: {exc}", file=sys.stderr)
        return 4 if "fingerprint" in str(exc) or "identity" in str(exc) or "recovery" in str(exc) else 2


if __name__ == "__main__": raise SystemExit(main())


__all__ = ["build_parser", "main"]
