from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from core.runtime.runtime_mission_model import (
    build_mission_evidence,
    load_mission,
)
from core.runtime.runtime_mission_orchestrator import (
    advance_mission,
    cancel_mission,
    confirm_mission_plan,
    create_mission,
    submit_mission_input,
)
from core.runtime.runtime_mission_scheduler import (
    create_mission_scheduler_state,
    enqueue_mission,
    load_mission_scheduler_state,
    request_mission_scheduler_action,
    run_mission_scheduler,
    run_mission_scheduler_iteration,
    save_mission_scheduler_state,
)

WAITING = {
    "created",
    "planning",
    "waiting_for_plan_confirmation",
    "ready",
    "running",
    "waiting_for_operator",
    "partially_completed",
    "blocked",
    "cancelled",
}


def _json(path: Any) -> Any:
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8-sig")
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("invalid_input_json") from exc


def _print(value: Any) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )


def _roots(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "target_root": args.target_root,
        "workspace_root": args.workspace_root,
    }


def _exit(mission: dict[str, Any]) -> int:
    status = mission.get("mission_status")
    if status == "expired":
        return 5
    if status == "failed" and any(
        bool((goal.get("failure") or {}).get("critical"))
        for goal in mission.get("goals", {}).values()
    ):
        return 3
    return 1 if status in WAITING else 0


def _summary(mission: dict[str, Any]) -> dict[str, Any]:
    return {
        "mission_id": mission.get("mission_id"),
        "mission_status": mission.get("mission_status"),
        "goal_counts": {
            name: len(mission.get(field, []))
            for name, field in (
                ("ready", "ready_goal_ids"),
                ("running", "running_goal_ids"),
                ("waiting", "waiting_goal_ids"),
                ("completed", "completed_goal_ids"),
                ("failed", "failed_goal_ids"),
                ("blocked", "blocked_goal_ids"),
                ("cancelled", "cancelled_goal_ids"),
            )
        },
        "ready_goals": mission.get("ready_goal_ids", []),
        "next_required_action": (
            "confirm_goal_plan"
            if mission.get("mission_status")
            == "waiting_for_plan_confirmation"
            else (
                "session_operator_input"
                if mission.get("waiting_goal_ids")
                else "advance_mission"
            )
        ),
        "completed_percentage": round(
            100
            * len(mission.get("completed_goal_ids", []))
            / max(1, len(mission.get("goals", {}))),
            2,
        ),
    }


def _scheduler_summary(
    state: dict[str, Any],
) -> dict[str, Any]:
    entries = state.get("entries") or {}
    counts: dict[str, int] = {}
    for entry in entries.values():
        status = str(entry.get("entry_status") or "")
        counts[status] = counts.get(status, 0) + 1

    return {
        "scheduler_id": state.get("scheduler_id"),
        "scheduler_name": state.get("scheduler_name"),
        "scheduler_status": state.get("scheduler_status"),
        "state_path": state.get("state_path"),
        "loop_iteration": state.get("loop_iteration", 0),
        "entry_count": len(entries),
        "entry_status_counts": counts,
        "current_entry_id": state.get("current_entry_id"),
        "current_mission_id": state.get(
            "current_mission_id"
        ),
        "completed_missions": state.get(
            "completed_missions",
            0,
        ),
        "waiting_missions": state.get(
            "waiting_missions",
            0,
        ),
        "blocked_missions": state.get(
            "blocked_missions",
            0,
        ),
        "failed_missions": state.get(
            "failed_missions",
            0,
        ),
        "recovered_leases": state.get(
            "recovered_leases",
            0,
        ),
        "idle_iterations": state.get(
            "idle_iterations",
            0,
        ),
        "stop_requested": state.get(
            "stop_requested"
        )
        is True,
        "pause_requested": state.get(
            "pause_requested"
        )
        is True,
        "last_result": state.get("last_result"),
        "failure": state.get("failure"),
    }


def _add_scheduler_runtime_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_loop_controls: bool,
) -> None:
    parser.add_argument(
        "--worker-state",
        required=True,
    )
    parser.add_argument(
        "--worker-name",
        required=True,
    )
    parser.add_argument(
        "--target-root",
        required=True,
    )
    parser.add_argument(
        "--workspace-root",
        required=True,
    )
    parser.add_argument(
        "--owner",
        default="mission-runtime",
    )
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=120,
    )
    parser.add_argument(
        "--mission-max-iterations",
        type=int,
        default=10,
    )

    if include_loop_controls:
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=1.0,
        )
        parser.add_argument(
            "--max-iterations",
            type=int,
        )
        parser.add_argument(
            "--idle-exit-after",
            type=int,
        )


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        prog="zero-mission-runtime"
    )
    sub = value.add_subparsers(
        dest="command",
        required=True,
    )

    command = sub.add_parser("create")
    command.add_argument("mission_input")
    command.add_argument("--goal-plan", required=True)
    command.add_argument("--target-root", required=True)
    command.add_argument("--workspace-root", required=True)
    command.add_argument("--mission-path", required=True)
    command.add_argument(
        "--scheduler-state",
        required=True,
    )
    command.add_argument("--now")

    command = sub.add_parser("create-natural")
    command.add_argument("mission_text")
    command.add_argument("--operator-id", required=True)
    command.add_argument("--target-root", required=True)
    command.add_argument("--workspace-root", required=True)
    command.add_argument(
        "--requested-scope",
        action="append",
        default=[],
    )
    command.add_argument(
        "--excluded-scope",
        action="append",
        default=[],
    )
    command.add_argument("--mission-path", required=True)
    command.add_argument(
        "--scheduler-state",
        required=True,
    )
    command.add_argument("--now")

    for name in (
        "status",
        "goals",
        "ready",
        "evidence",
        "planning-status",
        "replanning-history",
    ):
        command = sub.add_parser(name)
        command.add_argument("mission")

    for name in ("confirm-plan", "submit-input"):
        command = sub.add_parser(name)
        command.add_argument("mission")
        command.add_argument("operator_input")
        command.add_argument(
            "--scheduler-state",
            required=True,
        )
        command.add_argument("--now")
        command.add_argument("--target-root")
        command.add_argument("--workspace-root")

    command = sub.add_parser("advance")
    command.add_argument("mission")
    command.add_argument(
        "--scheduler-state",
        required=True,
    )
    command.add_argument("--target-root", required=True)
    command.add_argument(
        "--workspace-root",
        required=True,
    )
    command.add_argument("--now")

    command = sub.add_parser("cancel")
    command.add_argument("mission")
    command.add_argument("--operator-id", required=True)
    command.add_argument("--now")

    for name in (
        "submit-clarification",
        "request-replan",
        "confirm-replan",
        "reject-replan",
    ):
        command = sub.add_parser(name)
        command.add_argument("mission")
        command.add_argument("operator_input")
        command.add_argument("--scheduler-state")
        command.add_argument("--now")

    scheduler = sub.add_parser("scheduler")
    scheduler_sub = scheduler.add_subparsers(
        dest="scheduler_command",
        required=True,
    )

    command = scheduler_sub.add_parser("init")
    command.add_argument("scheduler_state")
    command.add_argument(
        "--name",
        default="default",
    )
    command.add_argument("--now")

    command = scheduler_sub.add_parser("enqueue")
    command.add_argument("scheduler_state")
    command.add_argument("mission")
    command.add_argument(
        "--priority",
        type=int,
        default=0,
    )
    command.add_argument("--now")

    command = scheduler_sub.add_parser("status")
    command.add_argument("scheduler_state")

    command = scheduler_sub.add_parser("entries")
    command.add_argument("scheduler_state")

    command = scheduler_sub.add_parser("run-once")
    command.add_argument("scheduler_state")
    _add_scheduler_runtime_arguments(
        command,
        include_loop_controls=False,
    )
    command.add_argument("--now")

    command = scheduler_sub.add_parser("run")
    command.add_argument("scheduler_state")
    _add_scheduler_runtime_arguments(
        command,
        include_loop_controls=True,
    )

    for action in ("pause", "resume", "stop"):
        command = scheduler_sub.add_parser(action)
        command.add_argument("scheduler_state")
        command.add_argument("--now")

    return value


def _scheduler_main(
    args: argparse.Namespace,
) -> int:
    command = args.scheduler_command

    if command == "init":
        state_path = Path(args.scheduler_state)
        if state_path.exists():
            raise ValueError(
                "mission_scheduler_state_already_exists"
            )

        state = create_mission_scheduler_state(
            state_path=state_path,
            scheduler_name=args.name,
            now=args.now,
        )
        state = save_mission_scheduler_state(
            state,
            state_path,
        )
        _print(_scheduler_summary(state))
        return 0

    state = load_mission_scheduler_state(
        args.scheduler_state
    )

    if command == "enqueue":
        state = enqueue_mission(
            state,
            args.mission,
            priority=args.priority,
            now=args.now,
        )
        state = save_mission_scheduler_state(
            state,
            args.scheduler_state,
        )
        _print(_scheduler_summary(state))
        return 0

    if command == "status":
        _print(_scheduler_summary(state))
        return 0

    if command == "entries":
        _print(
            {
                "scheduler_id": state.get(
                    "scheduler_id"
                ),
                "entry_order": state.get(
                    "entry_order",
                    [],
                ),
                "entries": state.get(
                    "entries",
                    {},
                ),
            }
        )
        return 0

    if command == "run-once":
        result = run_mission_scheduler_iteration(
            scheduler_state_path=args.scheduler_state,
            worker_state_path=args.worker_state,
            worker_name=args.worker_name,
            target_root=args.target_root,
            workspace_root=args.workspace_root,
            runtime_config={
                "target_root": args.target_root,
                "workspace_root": args.workspace_root,
            },
            owner=args.owner,
            lease_seconds=args.lease_seconds,
            mission_max_iterations=(
                args.mission_max_iterations
            ),
            now=args.now,
        )
        _print(_scheduler_summary(result))
        return (
            2
            if result.get("scheduler_status")
            in {"blocked", "failed"}
            else 0
        )

    if command == "run":
        result = run_mission_scheduler(
            scheduler_state_path=args.scheduler_state,
            worker_state_path=args.worker_state,
            worker_name=args.worker_name,
            target_root=args.target_root,
            workspace_root=args.workspace_root,
            runtime_config={
                "target_root": args.target_root,
                "workspace_root": args.workspace_root,
            },
            owner=args.owner,
            poll_interval_seconds=args.poll_interval,
            lease_seconds=args.lease_seconds,
            mission_max_iterations=(
                args.mission_max_iterations
            ),
            max_iterations=args.max_iterations,
            idle_exit_after=args.idle_exit_after,
        )
        _print(_scheduler_summary(result))
        return (
            2
            if result.get("scheduler_status")
            in {"blocked", "failed"}
            else 0
        )

    if command in {"pause", "resume", "stop"}:
        state = request_mission_scheduler_action(
            state,
            command,
            now=args.now,
        )
        state = save_mission_scheduler_state(
            state,
            args.scheduler_state,
        )
        _print(_scheduler_summary(state))
        return 0

    raise ValueError(
        "unsupported_mission_scheduler_command"
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    try:
        if args.command == "scheduler":
            return _scheduler_main(args)

        if args.command == "create":
            result = create_mission(
                _json(args.mission_input),
                goal_plan=_json(args.goal_plan),
                target_root=args.target_root,
                workspace_root=args.workspace_root,
                mission_path=args.mission_path,
                scheduler_state_path=args.scheduler_state,
                now=args.now,
            )
        elif args.command == "create-natural":
            from core.runtime.runtime_natural_mission_planner import (
                create_mission_from_planner_output,
                create_natural_mission_input,
                plan_natural_mission,
                save_planner_artifact,
            )

            natural = create_natural_mission_input(
                args.mission_text,
                operator_id=args.operator_id,
                target_root=args.target_root,
                workspace_root=args.workspace_root,
                requested_scope=args.requested_scope,
                excluded_scope=args.excluded_scope,
                now=args.now,
            )
            bundle = plan_natural_mission(
                natural,
                target_root=args.target_root,
                workspace_root=args.workspace_root,
                now=args.now,
            )
            base = Path(args.mission_path)
            artifact = base.with_suffix(".planner.json")
            save_planner_artifact(bundle, artifact)
            result = create_mission_from_planner_output(
                natural,
                bundle["planner_output"],
                planning_request=bundle[
                    "planning_request"
                ],
                target_root=args.target_root,
                workspace_root=args.workspace_root,
                mission_path=args.mission_path,
                scheduler_state_path=args.scheduler_state,
                now=args.now,
                planner_output_path=artifact,
            )
        else:
            result = load_mission(
                args.mission,
                check_expiry=False,
            )

            if args.command == "status":
                _print(_summary(result))
                return 0
            if args.command == "goals":
                _print(result.get("goals", {}))
                return 0
            if args.command == "ready":
                _print(
                    result.get("ready_goal_ids", [])
                )
                return 0
            if args.command == "evidence":
                _print(
                    result.get("mission_evidence")
                    or build_mission_evidence(result)
                )
                return 0
            if args.command == "planning-status":
                _print(
                    {
                        key: result.get(key)
                        for key in (
                            "planning_status",
                            "planning_revision",
                            "clarification_required",
                            "replan_required",
                            "replanning_status",
                            "replanning_revision",
                        )
                    }
                )
                return 0
            if args.command == "replanning-history":
                _print(
                    result.get(
                        "replanning_history",
                        [],
                    )
                )
                return 0

            if args.command == "confirm-plan":
                result = confirm_mission_plan(
                    result,
                    _json(args.operator_input),
                    scheduler_state=args.scheduler_state,
                    now=args.now,
                )
            elif args.command == "advance":
                result = advance_mission(
                    result,
                    scheduler_state=args.scheduler_state,
                    now=args.now,
                    runtime_config=_roots(args),
                )
            elif args.command == "submit-input":
                result = submit_mission_input(
                    result,
                    _json(args.operator_input),
                    scheduler_state=args.scheduler_state,
                    now=args.now,
                    runtime_config=_roots(args),
                )
            elif args.command == "cancel":
                result = cancel_mission(
                    result,
                    operator_id=args.operator_id,
                    now=args.now,
                )
            elif args.command in {
                "submit-clarification",
                "request-replan",
                "confirm-replan",
                "reject-replan",
            }:
                result = submit_mission_input(
                    result,
                    _json(args.operator_input),
                    scheduler_state=args.scheduler_state,
                    now=args.now,
                )

        _print(_summary(result))
        return _exit(result)
    except ValueError as exc:
        print(
            json.dumps(
                {"error": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        text = str(exc)
        if "expired" in text:
            return 5
        if any(
            word in text
            for word in (
                "fingerprint",
                "mismatch",
                "transition",
                "cycle",
                "identity",
            )
        ):
            return 4
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
