from __future__ import annotations

import argparse
import json
import shlex
import sys
from typing import Any, Sequence

from core.agent.runtime_goal_controller import RuntimeGoalController


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-root", default="."); parser.add_argument("--state-root"); parser.add_argument("--now"); parser.add_argument("--json", action="store_true", dest="json_output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zero-goal"); sub = parser.add_subparsers(dest="command")
    create = sub.add_parser("create"); create.add_argument("goal"); create.add_argument("--target-root"); create.add_argument("--priority", default="normal"); create.add_argument("--max-replans", type=int, default=3); _common(create)
    listing = sub.add_parser("list", aliases=["goals"]); listing.add_argument("--status"); _common(listing)
    for name in ("show", "milestones", "status", "pause", "resume", "stop", "cancel"):
        item = sub.add_parser(name); item.add_argument("goal_id"); _common(item)
    preview = sub.add_parser("preview"); preview.add_argument("goal"); preview.add_argument("--target-root"); preview.add_argument("--priority", default="normal"); preview.add_argument("--max-replans", type=int, default=3); _common(preview)
    run = sub.add_parser("run"); run.add_argument("goal_id"); run.add_argument("--max-milestones", type=int, default=1); run.add_argument("--max-missions", type=int, default=10); run.add_argument("--max-iterations", type=int, default=20); run.add_argument("--stop-on-blocked", action="store_true"); run.add_argument("--stop-on-failed", action="store_true"); run.add_argument("--idle-exit", action="store_true", default=True); run.add_argument("--wait-seconds", type=float, default=0.0); _common(run)
    replan = sub.add_parser("replan"); replan.add_argument("goal_id"); replan.add_argument("--reason", required=True); _common(replan)
    for name in ("approve", "deny"):
        item = sub.add_parser(name); item.add_argument("goal_id"); item.add_argument("milestone_id"); item.add_argument("--operator-id", required=True)
        if name == "deny": item.add_argument("--reason", required=True)
        _common(item)
    daemon = sub.add_parser("daemon"); daemon.add_argument("--once", action="store_true"); daemon.add_argument("--max-cycles", type=int, default=1); daemon.add_argument("--poll-interval", type=float, default=1.0); daemon.add_argument("--max-goals-per-cycle", type=int, default=2); daemon.add_argument("--max-missions-per-cycle", type=int, default=4); daemon.add_argument("--max-projections-per-cycle", type=int, default=10); daemon.add_argument("--max-replans-per-cycle", type=int, default=1); _common(daemon)
    _common(sub.add_parser("daemon-status"))
    for name in ("overview", "health", "pending-approvals"):
        item = sub.add_parser(name); item.add_argument("--runtime-budget", type=int, default=4); _common(item)
    for name in ("inspect", "timeline"):
        item = sub.add_parser(name); item.add_argument("goal_id"); item.add_argument("--runtime-budget", type=int, default=4); _common(item)
    return parser


def _controller(args: argparse.Namespace) -> RuntimeGoalController:
    return RuntimeGoalController(workspace_root=args.workspace_root, state_root=args.state_root, create_workspace=args.command == "create", now=args.now)


def _goal_summary(goal: dict[str, Any]) -> str:
    progress = goal.get("progress") or {}
    return f"Goal ID: {goal['goal_id']}\nTitle: {goal['goal_title']}\nStatus: {goal['goal_status']}\nWorkspace: {goal['workspace_root']}\nProgress: {progress.get('completion_percentage', 0)}%\nCurrent Milestone: {goal.get('current_milestone_id') or '-'}\nCompleted Milestones: {len(progress.get('completed_milestones', []))}\nWaiting Approval: {len(progress.get('waiting_approval_milestones', []))}\nBlocked: {len(progress.get('blocked_milestones', []))}\nFailed: {len(progress.get('failed_milestones', []))}\nNext Ready: {', '.join(progress.get('next_ready_milestone_ids', [])) or '-'}\nCreated: {goal['created_at']}\nUpdated: {goal['updated_at']}"


def _summary(value: Any, command: str) -> str:
    if command in {"create", "show", "status", "pause", "resume", "stop", "cancel", "replan", "approve", "deny"}: return _goal_summary(value)
    if command in {"list", "goals"}: return "No goals." if not value else "\n\n".join(_goal_summary(goal) for goal in value)
    if command == "milestones":
        return "No milestones." if not value else "\n\n".join(f"Milestone ID: {item['milestone_id']}\nStatus: {item['milestone_status']}\nDependencies: {', '.join(item['dependencies']) or '-'}\nMission Entries: {', '.join(item['mission_entry_ids']) or '-'}\nSuccess Criteria: {', '.join(item['success_criteria']) or '-'}\nApproval Expected: {item['approval_expected']}\nFailure: {json.dumps(item.get('failure'), ensure_ascii=False) if item.get('failure') else '-'}\nEvidence: {', '.join(item['evidence_requirements']) or '-'}" for item in value)
    if command == "preview": return f"Goal ID: {value['goal']['goal_id']}\nStatus: {value['goal']['goal_status']}\nMilestones: {len(value['plan']['milestone_order'])}\nSupported: {value['plan']['supported']}\nPrepare Only: {value['prepare_only']}"
    if command == "run": return f"Goal ID: {value['goal_id']}\nStatus: {value['goal_status']}\nStopped: {value['stopped_reason']}\nProcessed Missions: {len(value['processed_entry_ids'])}\nProgress: {value['progress']['completion_percentage']}%\nCurrent Milestone: {value.get('current_milestone_id') or '-'}"
    if command in {"daemon", "daemon-status"}: return f"Daemon Contract: {value['contract']}\nVersion: {value['version']}\nStatus: {value['daemon_status']}\nLast Cycle: {value.get('last_cycle_identity') or '-'}\nLast Cycle Timestamp: {value.get('last_cycle_timestamp') or '-'}\nCycle Count: {value['cycle_count']}\nActive Goals: {value['active_goal_count']}\nWaiting Approval: {value['waiting_approval_count']}\nReady Goals: {value['ready_goal_count']}\nBlocked Goals: {value['blocked_goal_count']}\nLast Error: {json.dumps(value.get('last_error'), ensure_ascii=False) if value.get('last_error') else '-'}\nConfiguration Fingerprint: {value['configuration_fingerprint']}"
    if command == "overview": return f"Goals: {value['total_goal_count']}\nActive: {value['active_goal_count']}\nCompleted: {value['completed_goal_count']}\nWaiting Approval: {value['waiting_approval_goal_count']}\nStalled: {value['stalled_goal_count']}\nActive Missions: {value['active_mission_count']}/{value['runtime_mission_budget']}\nDaemon: {value['daemon_status']}"
    if command == "inspect": return f"Goal: {value['goal_identity']}\nStatus: {value['goal_status']}\nProgress: {value['goal_progress'].get('completion_percentage', 0)}%\nMilestones: {len(value['milestones'])}\nReference Integrity: {value['reference_integrity_result']['integrity']}"
    if command == "timeline": return f"Goal: {value['goal_id']}\nEvents: {value['event_count']}\n" + "\n".join(f"{event['persisted_timestamp']} {event['event_category']} {event.get('milestone_id') or '-'}" for event in value['events'])
    if command == "health": return f"Healthy: {value['healthy']}\nReady: {value['ready']}\nDegraded: {value['degraded']}\nCritical: {value['critical']}\nIssues: {len(value['issues'])}\nStalled Goals: {len(value['stalled_goals'])}"
    if command == "pending-approvals": return "No pending approvals." if not value["pending_approvals"] else "\n\n".join(f"Goal: {item['goal_id']}\nMilestone: {item['milestone_id']}\nEntry: {item['entry_id']}\nProposal: {item['approval_or_proposal_id'] or '-'}\nScope: {', '.join(item['requested_scope']) or '-'}" for item in value["pending_approvals"])
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _execute(args: argparse.Namespace) -> tuple[Any, int]:
    command = args.command
    if command in {"overview", "inspect", "timeline", "health", "pending-approvals"}:
        from core.agent.runtime_goal_operations import GoalOperationsConfig, GoalOperationsService
        service = GoalOperationsService(GoalOperationsConfig(workspace_root=args.workspace_root, state_root=args.state_root, runtime_budget_limit=args.runtime_budget, reference_time=args.now))
        projection = service.overview() if command == "overview" else service.inspect(args.goal_id) if command == "inspect" else service.timeline(args.goal_id) if command == "timeline" else service.health() if command == "health" else service.pending_approvals()
        value = projection.to_dict(); return value, (4 if command == "health" and value["critical"] else 3 if command == "health" and value["degraded"] else 0)
    controller = _controller(args)
    if command == "create": value = controller.create(args.goal, target_root=args.target_root, priority=args.priority, max_replans=args.max_replans, now=args.now)
    elif command in {"list", "goals"}: value = controller.list(status=args.status)
    elif command in {"show", "status"}: value = controller.show(args.goal_id)
    elif command == "milestones": value = controller.milestones(args.goal_id)
    elif command == "preview": value = controller.preview(args.goal, target_root=args.target_root, priority=args.priority, max_replans=args.max_replans, now=args.now)
    elif command == "run": value = controller.run(args.goal_id, max_milestones=args.max_milestones, max_missions=args.max_missions, max_iterations=args.max_iterations, stop_on_blocked=args.stop_on_blocked, stop_on_failed=args.stop_on_failed, idle_exit=args.idle_exit, wait_seconds=args.wait_seconds, now=args.now)
    elif command == "pause": value = controller.pause(args.goal_id, now=args.now)
    elif command == "resume": value = controller.resume(args.goal_id, now=args.now)
    elif command == "stop": value = controller.stop(args.goal_id, now=args.now)
    elif command == "cancel": value = controller.cancel(args.goal_id, now=args.now)
    elif command == "replan": value = controller.replan(args.goal_id, reason=args.reason, now=args.now)
    elif command == "approve": value = controller.approve(args.goal_id, args.milestone_id, operator_id=args.operator_id, now=args.now)
    elif command == "deny": value = controller.approve(args.goal_id, args.milestone_id, operator_id=args.operator_id, deny=True, reason=args.reason, now=args.now)
    elif command in {"daemon", "daemon-status"}:
        from core.agent.runtime_goal_daemon import GoalDaemon, GoalDaemonConfig
        config = GoalDaemonConfig(poll_interval_seconds=args.poll_interval, max_goals_per_cycle=args.max_goals_per_cycle, max_missions_started_per_cycle=args.max_missions_per_cycle, max_projection_updates_per_cycle=args.max_projections_per_cycle, max_replans_per_cycle=args.max_replans_per_cycle) if command == "daemon" else None
        daemon = GoalDaemon(controller, config=config, now=args.now)
        if command == "daemon": value = daemon.run(max_cycles=1 if args.once else args.max_cycles, now_provider=lambda: args.now, sleep_provider=lambda seconds: __import__("time").sleep(seconds)).to_dict()
        else: value = daemon.status().to_dict()
    else: raise ValueError("goal_command_required")
    status = value.get("goal_status") if isinstance(value, dict) else None
    daemon_status = value.get("daemon_status") if isinstance(value, dict) else None
    code = 3 if status in {"waiting_for_approval", "blocked"} else 5 if status in {"paused", "stopped"} else 1 if status == "failed" or daemon_status == "failed" else 0
    return value, code


def _interactive(workspace_root: str = ".", state_root: str | None = None) -> int:
    print("ZERO Long-Horizon Goal Manager")
    while True:
        try: text = input("ZERO-GOAL> ").strip()
        except EOFError: return 0
        if not text: continue
        if text.casefold() in {"exit", "quit"}: return 0
        if text.casefold() == "help": print("create <goal> | goals | show <id> | milestones <id> | preview <goal> | run <id> | daemon | daemon-status | overview | inspect <id> | timeline <id> | health | pending-approvals | status <id> | pause <id> | resume <id> | stop <id> | cancel <id> | replan <id> <reason> | approve <goal> <milestone> <operator> | deny <goal> <milestone> <operator> <reason> | exit"); continue
        try:
            parts = shlex.split(text); command = parts[0].casefold()
            if command in {"create", "preview"} and len(parts) >= 2: parts = [command, " ".join(parts[1:])]
            elif command == "goals": parts[0] = "list"
            elif command == "replan" and len(parts) >= 3: parts = ["replan", parts[1], "--reason", " ".join(parts[2:])]
            elif command == "approve" and len(parts) == 4: parts = ["approve", parts[1], parts[2], "--operator-id", parts[3]]
            elif command == "deny" and len(parts) >= 5: parts = ["deny", parts[1], parts[2], "--operator-id", parts[3], "--reason", " ".join(parts[4:])]
            parts += ["--workspace-root", workspace_root]
            if state_root: parts += ["--state-root", state_root]
            args = build_parser().parse_args(parts); value, _ = _execute(args); print(_summary(value, args.command))
        except (OSError, ValueError, SystemExit, json.JSONDecodeError) as exc: print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    values = list(argv) if argv is not None else sys.argv[1:]
    if not values: return _interactive()
    try:
        args = build_parser().parse_args(values)
        if args.command is None: return _interactive()
        value, code = _execute(args)
        if args.json_output and args.command in {"overview", "inspect", "timeline", "health", "pending-approvals"}:
            from core.agent.runtime_goal_operations_snapshot import serialize_projection
            print(serialize_projection(value))
        else: print(json.dumps(value, ensure_ascii=False, sort_keys=True) if args.json_output else _summary(value, args.command))
        return code
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False) if "--json" in values else f"Error: {exc}", file=sys.stderr); return 4 if "fingerprint" in str(exc) or "identity" in str(exc) or "recovery" in str(exc) else 2


if __name__ == "__main__": raise SystemExit(main())

__all__ = ["build_parser", "main"]
