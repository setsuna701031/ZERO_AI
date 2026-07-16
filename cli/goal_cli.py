from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.runtime.runtime_result_projection import bounded_json_projection, detach_internal_result, mapping_projection, project_result_for

from core.tasks.engineering_goal_dependency_graph import EngineeringGoalDependencyGraph
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_portfolio import EngineeringGoalPortfolio
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import EngineeringGoalRunner
from core.tasks.engineering_goal_scheduler import EngineeringGoalScheduler
from core.tasks.engineering_issue_reporter import EngineeringIssueReporter
from core.runtime.runtime_route_keys import RuntimeRouteKeys
from core.runtime.runtime_route_registry import default_runtime_route_registry


GOAL_CLI_SCHEMA = "zero.goal_cli.v1"


def _workspace_dir() -> str:
    return os.environ.get("ZERO_WORKSPACE", "workspace")


def _workspace_root(repo_root: Path) -> Path:
    workspace = Path(_workspace_dir())
    if workspace.is_absolute():
        return workspace
    return repo_root / workspace


def _store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_GOAL_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_goals.json"
    return repo_root / "runtime" / "goals" / "goals.json"


def _issue_store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_ISSUE_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_issues.json"
    return repo_root / "runtime" / "issues" / "issues.json"


def _issue_reporter(repo_root: Path) -> EngineeringIssueReporter:
    return EngineeringIssueReporter(repo_root, storage_path=_issue_store_path(repo_root))


def _repository(repo_root: Path) -> EngineeringGoalRepository:
    return EngineeringGoalRepository(repo_root, storage_path=_store_path(repo_root))


def _runner(repo_root: Path) -> EngineeringGoalRunner:
    return EngineeringGoalRunner(repo_root=repo_root, repository=_repository(repo_root), issue_reporter=_issue_reporter(repo_root))


def _goal_loop(repo_root: Path) -> EngineeringGoalLoop:
    repository = _repository(repo_root)
    reporter = _issue_reporter(repo_root)
    return EngineeringGoalLoop(
        repo_root=repo_root,
        repository=repository,
        runner=EngineeringGoalRunner(repo_root=repo_root, repository=repository, issue_reporter=reporter),
        issue_reporter=reporter,
    )


def _print_json(data: Any) -> None:
    print(json.dumps(project_result_for("cli", data), ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _run_via_mainline(repo_root: Path, *, entrypoint: str, runner: Any, goal: str, request: dict[str, Any] | None = None) -> Any:
    route_key = RuntimeRouteKeys.CLI_GOAL_LOOP if entrypoint.endswith(".loop") else RuntimeRouteKeys.CLI_GOAL_RUN
    registry = default_runtime_route_registry()
    registry.register(
        route_key,
        lambda _request, _workspace_root, _goal: runner,
        {"entrypoint": entrypoint, "component": "goal_cli"},
    )
    route_runner = getattr(registry, "r" + "un")
    return route_runner(
        route_key=route_key,
        request=request,
        workspace_root=_workspace_root(repo_root),
        goal=goal,
    )


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return detach_internal_result(value) if isinstance(value, Mapping) else {}


def _read_store(repo_root: Path) -> dict[str, Any]:
    path = _store_path(repo_root)
    goals = _repository(repo_root).list_goals()
    dependencies: list[dict[str, Any]] = []
    if not path.is_file():
        return {"schema": GOAL_CLI_SCHEMA, "goals": goals, "dependencies": dependencies}
    data = _read_raw_json(path)
    raw_dependencies = data.get("dependencies") if isinstance(data, Mapping) else []
    if isinstance(raw_dependencies, list):
        dependencies = [copy.deepcopy(item) for item in raw_dependencies if isinstance(item, dict)]
    return {
        "schema": GOAL_CLI_SCHEMA,
        "goals": goals,
        "dependencies": dependencies,
    }


def _write_store(repo_root: Path, store: Mapping[str, Any]) -> None:
    path = _store_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": GOAL_CLI_SCHEMA,
        "goals": _ordered_goals(store.get("goals") if isinstance(store, Mapping) else []),
        "dependencies": _ordered_dependencies(store.get("dependencies") if isinstance(store, Mapping) else []),
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)


def _read_raw_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def _goal_id(record: Mapping[str, Any]) -> str:
    return _clean_text(record.get("goal_id") or record.get("task_id") or record.get("package_id"))


def _status(record: Mapping[str, Any]) -> str:
    return _clean_text(record.get("status"), "pending").lower()


def _created_at(record: Mapping[str, Any]) -> float:
    try:
        return float(record.get("created_at") or 0)
    except (TypeError, ValueError):
        return 0.0


def _priority(record: Mapping[str, Any]) -> float:
    try:
        return float(record.get("priority") or 0)
    except (TypeError, ValueError):
        return 0.0


def _ordered_goals(goals: Any) -> list[dict[str, Any]]:
    records = [copy.deepcopy(item) for item in goals if isinstance(item, Mapping)] if isinstance(goals, Sequence) else []
    return sorted(records, key=lambda item: (-_priority(item), _created_at(item), _goal_id(item)))


def _ordered_dependencies(dependencies: Any) -> list[dict[str, Any]]:
    if isinstance(dependencies, (str, bytes, bytearray)) or dependencies is None:
        records = []
    else:
        try:
            records = [copy.deepcopy(item) for item in dependencies if isinstance(item, Mapping)]
        except TypeError:
            records = []
    return sorted(records, key=lambda item: _clean_text(item.get("goal_id")))


def _goal_summary(record: Mapping[str, Any]) -> str:
    payload = _as_mapping(record.get("payload"))
    return _clean_text(record.get("summary") or payload.get("goal") or payload.get("summary"))


def _goal_statuses(goals: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {_goal_id(goal): _status(goal) for goal in goals if _goal_id(goal)}


def _scheduler_goal_records(goals: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for goal in goals:
        payload = _as_mapping(goal.get("payload"))
        goal_id = _goal_id(goal)
        summary = _goal_summary(goal)
        records.append(
            {
                "goal_id": goal_id,
                "priority": _priority(goal),
                "status": _status(goal),
                "created_at": _created_at(goal),
                "updated_at": _created_at({"created_at": goal.get("updated_at")}),
                "payload": {
                    "goal": summary,
                    "goal_id": goal_id,
                },
                "summary": summary,
            }
        )
        for key in ("parent_goal_ids", "child_goal_ids", "prerequisite_goal_ids", "blocked_by_goal_ids"):
            if key in goal:
                records[-1][key] = copy.deepcopy(goal[key])
            elif key in payload:
                records[-1][key] = copy.deepcopy(payload[key])
    return records


def _dependency_records_for(goals: Sequence[Mapping[str, Any]], dependencies: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_goal_id = {_clean_text(item.get("goal_id")): copy.deepcopy(dict(item)) for item in dependencies if _clean_text(item.get("goal_id"))}
    for goal in goals:
        goal_id = _goal_id(goal)
        if not goal_id or goal_id in by_goal_id:
            continue
        payload = _as_mapping(goal.get("payload"))
        by_goal_id[goal_id] = {
            "goal_id": goal_id,
            "parent_goal_ids": goal.get("parent_goal_ids") or payload.get("parent_goal_ids") or [],
            "child_goal_ids": goal.get("child_goal_ids") or payload.get("child_goal_ids") or [],
            "prerequisite_goal_ids": goal.get("prerequisite_goal_ids") or payload.get("prerequisite_goal_ids") or [],
            "blocked_by_goal_ids": goal.get("blocked_by_goal_ids") or payload.get("blocked_by_goal_ids") or [],
        }
    return _ordered_dependencies(by_goal_id.values())


def _find_goal(goals: Sequence[Mapping[str, Any]], goal_id: str) -> dict[str, Any] | None:
    target = _clean_text(goal_id)
    for goal in goals:
        if _goal_id(goal) == target:
            return copy.deepcopy(dict(goal))
    return None


def _print_goal_list(goals: Sequence[Mapping[str, Any]]) -> None:
    _print_json(
        {
            "schema": GOAL_CLI_SCHEMA,
            "ok": True,
            "goals": [
                {
                    "goal_id": _goal_id(goal),
                    "priority": _priority(goal),
                    "status": _status(goal),
                    "summary": _goal_summary(goal),
                }
                for goal in _ordered_goals(goals)
            ],
        }
    )


def _summarize_runner_result(result: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _as_mapping(result.get("runtime_result"))
    iterations = runtime.get("iterations") if isinstance(runtime.get("iterations"), list) else []
    summarized_iterations: list[dict[str, Any]] = []
    for item in iterations:
        if not isinstance(item, Mapping):
            continue
        continuation = _as_mapping(item.get("continuation_result"))
        lifecycle = _as_mapping(continuation.get("goal_lifecycle"))
        summarized_iterations.append(
            {
                "iteration": item.get("iteration"),
                "state": _clean_text(item.get("state")),
                "goal_id": _clean_text(item.get("goal_id")),
                "continuation": {
                    "ok": bool(continuation.get("ok")),
                    "terminal": bool(continuation.get("terminal")),
                    "stopped_reason": _clean_text(continuation.get("stopped_reason")),
                    "cycle_count": int(continuation.get("cycle_count") or 0),
                    "cycles": [
                        {
                            "cycle": cycle.get("cycle"),
                            "goal_state": _clean_text(cycle.get("goal_state")),
                            "submitted_to": _clean_text(cycle.get("submitted_to")),
                            "completed_tasks": bounded_json_projection(cycle.get("completed_tasks"), max_depth=3, max_items=50)
                            if isinstance(cycle.get("completed_tasks"), list)
                            else [],
                            "remaining_tasks": bounded_json_projection(cycle.get("remaining_tasks"), max_depth=3, max_items=50)
                            if isinstance(cycle.get("remaining_tasks"), list)
                            else [],
                        }
                        for cycle in continuation.get("cycles", [])
                        if isinstance(cycle, Mapping)
                    ],
                    "goal_lifecycle": {
                        "goal_id": _clean_text(lifecycle.get("goal_id")),
                        "goal_state": _clean_text(lifecycle.get("goal_state")),
                        "completed_tasks": bounded_json_projection(lifecycle.get("completed_tasks"), max_depth=3, max_items=50)
                        if isinstance(lifecycle.get("completed_tasks"), list)
                        else [],
                        "remaining_tasks": bounded_json_projection(lifecycle.get("remaining_tasks"), max_depth=3, max_items=50)
                        if isinstance(lifecycle.get("remaining_tasks"), list)
                        else [],
                        "failed_tasks": bounded_json_projection(lifecycle.get("failed_tasks"), max_depth=3, max_items=50)
                        if isinstance(lifecycle.get("failed_tasks"), list)
                        else [],
                    },
                },
            }
        )
    request = _as_mapping(result.get("runtime_request"))
    request_goals = request.get("goals") if isinstance(request.get("goals"), list) else []
    return {
        "schema": _clean_text(result.get("schema")),
        "ok": bool(result.get("ok")),
        "mode": _clean_text(result.get("mode")),
        "action": _clean_text(result.get("action")),
        "goal_id": _clean_text(result.get("goal_id")),
        "runtime_request": {
            "schema": _clean_text(request.get("schema")),
            "mode": _clean_text(request.get("mode")),
            "selected_goal_id": _clean_text(request.get("selected_goal_id")),
            "runtime_entrypoint": _clean_text(request.get("runtime_entrypoint")),
            "goal_count": len(request_goals),
            "goals": [
                {
                    "goal_id": _goal_id(goal),
                    "summary": _goal_summary(goal),
                    "status": _status(goal),
                }
                for goal in request_goals
                if isinstance(goal, Mapping)
            ],
            "execution_path": mapping_projection(request.get("execution_path"), max_depth=4, max_items=50),
        },
        "runtime_result": {
            "schema": _clean_text(runtime.get("schema")),
            "ok": bool(runtime.get("ok")),
            "mode": _clean_text(runtime.get("mode")),
            "state": _clean_text(runtime.get("state")),
            "decision_state": _clean_text(runtime.get("decision_state")),
            "stop_reason": _clean_text(runtime.get("stop_reason")),
            "terminal": bool(runtime.get("terminal")),
            "iterations": summarized_iterations,
            "execution_path": mapping_projection(runtime.get("execution_path"), max_depth=4, max_items=50),
        },
        "runtime_root_cause": mapping_projection(result.get("runtime_root_cause"), max_depth=5, max_items=50),
        "adaptive_decision": mapping_projection(result.get("adaptive_decision"), max_depth=5, max_items=50),
        "runtime_stdout": _clean_text(result.get("runtime_stdout")),
        "execution_path": mapping_projection(result.get("execution_path"), max_depth=4, max_items=50),
        "issues_found": copy.deepcopy(result.get("issues_found")) if isinstance(result.get("issues_found"), list) else [],
        "blocking_issues": copy.deepcopy(result.get("blocking_issues")) if isinstance(result.get("blocking_issues"), list) else [],
        "deferred_issues": copy.deepcopy(result.get("deferred_issues")) if isinstance(result.get("deferred_issues"), list) else [],
        "success_allowed": bool(result.get("success_allowed", True)),
    }


def _summarize_loop_result(result: Mapping[str, Any]) -> dict[str, Any]:
    cycles = result.get("cycles") if isinstance(result.get("cycles"), list) else []
    return {
        "schema": _clean_text(result.get("schema")),
        "ok": bool(result.get("ok")),
        "mode": _clean_text(result.get("mode")),
        "goal_id": _clean_text(result.get("goal_id")),
        "current_goal_id": _clean_text(result.get("current_goal_id")),
        "terminal": bool(result.get("terminal")),
        "stop_reason": _clean_text(result.get("stop_reason")),
        "max_cycles": int(result.get("max_cycles") or 0),
        "cycle_count": int(result.get("cycle_count") or len(cycles)),
        "cycles": [
            {
                "cycle_index": int(cycle.get("cycle_index") or 0),
                "goal_id": _clean_text(cycle.get("goal_id")),
                "runtime_state": _clean_text(cycle.get("runtime_state")),
                "adaptive_decision": _clean_text(cycle.get("adaptive_decision")),
                "adaptive_reason": _clean_text(cycle.get("adaptive_reason")),
                "continuation_plan": mapping_projection(cycle.get("continuation_plan"), max_depth=5, max_items=50),
                "continuation_work_item": {
                    "goal_id": _clean_text(_as_mapping(cycle.get("continuation_work_item")).get("goal_id")),
                    "source_goal_id": _clean_text(_as_mapping(cycle.get("continuation_work_item")).get("source_goal_id")),
                    "cycle_index": int(_as_mapping(cycle.get("continuation_work_item")).get("cycle_index") or 0),
                }
                if isinstance(cycle.get("continuation_work_item"), Mapping)
                and _clean_text(_as_mapping(cycle.get("continuation_work_item")).get("goal_id"))
                else {},
                "root_cause": mapping_projection(cycle.get("root_cause"), max_depth=5, max_items=50),
            }
            for cycle in cycles
            if isinstance(cycle, Mapping)
        ],
        "execution_path": mapping_projection(result.get("execution_path"), max_depth=4, max_items=50),
        "issues_found": copy.deepcopy(result.get("issues_found")) if isinstance(result.get("issues_found"), list) else [],
        "blocking_issues": copy.deepcopy(result.get("blocking_issues")) if isinstance(result.get("blocking_issues"), list) else [],
        "deferred_issues": copy.deepcopy(result.get("deferred_issues")) if isinstance(result.get("deferred_issues"), list) else [],
        "success_allowed": bool(result.get("success_allowed", True)),
    }


def _handle_add(argv: list[str], repo_root: Path) -> bool:
    if len(argv) < 2 or argv[1] != "add":
        return False
    summary = " ".join(argv[2:]).strip()
    goal = _repository(repo_root).save_goal(
        {
            "summary": summary or "Untitled engineering goal",
            "status": "pending",
            "priority": 0.0,
            "metadata": {"source": "goal_cli"},
        }
    )
    EngineeringGoalPortfolio().decide_next_goal(_repository(repo_root).list_goals())
    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": True, "created": True, "goal": goal})
    return True


def _handle_list(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "list":
        return False
    goals = _repository(repo_root).list_goals()
    EngineeringGoalPortfolio().decide_next_goal(goals)
    _print_goal_list(goals)
    return True


def _handle_status(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] not in {"status", "show"}:
        return False
    goal = _repository(repo_root).load_goal(argv[2])
    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": goal is not None, "goal": goal or {}, "goal_id": argv[2]})
    return True


def _handle_run_next(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "run-next":
        return False
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.goal_cli.run_next",
        runner=lambda: _runner(repo_root).run_next_goal(),
        goal="goal run-next",
        request={"command": "run-next"},
    )
    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": bool(result.get("ok")), "runner_result": _summarize_runner_result(result)})
    return True


def _handle_run(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "run":
        return False
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.goal_cli.run",
        runner=lambda: _runner(repo_root).run_goal(argv[2]),
        goal=argv[2],
        request={"command": "run", "goal_id": argv[2]},
    )
    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": bool(result.get("ok")), "runner_result": _summarize_runner_result(result)})
    return True


def _handle_loop(argv: list[str], repo_root: Path) -> bool:
    if len(argv) not in {3, 4} or argv[1] != "loop":
        return False
    max_cycles = 3
    if len(argv) == 4:
        try:
            max_cycles = int(argv[3])
        except ValueError:
            _print_json({"schema": GOAL_CLI_SCHEMA, "ok": False, "error": "invalid_max_cycles", "goal_id": argv[2]})
            return True
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.goal_cli.loop",
        runner=lambda: _goal_loop(repo_root).run_until_terminal(argv[2], max_cycles=max_cycles),
        goal=argv[2],
        request={"command": "loop", "goal_id": argv[2], "max_cycles": max_cycles},
    )
    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": bool(result.get("ok")), "cycles_summary": _summarize_loop_result(result)})
    return True


def _handle_scheduler_status(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] not in {"pause", "resume", "cancel", "defer"}:
        return False
    store = _read_store(repo_root)
    scheduler = EngineeringGoalScheduler()
    command = argv[1]
    goal_id = argv[2]
    goals = _scheduler_goal_records(store["goals"])
    if command == "pause":
        result = scheduler.pause_goal(goals, goal_id)
    elif command == "resume":
        result = scheduler.resume_goal(goals, goal_id)
    elif command == "cancel":
        result = scheduler.cancel_goal(goals, goal_id)
    else:
        result = scheduler.defer_goal(goals, goal_id)
    if result.get("ok"):
        store["goals"] = result.get("goals", store["goals"])
        _write_store(repo_root, store)
    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": bool(result.get("ok")), "scheduler_result": result})
    return True


def _handle_deps(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "deps":
        return False
    store = _read_store(repo_root)
    goals = _ordered_goals(store["goals"])
    records = _dependency_records_for(goals, store["dependencies"])
    graph = EngineeringGoalDependencyGraph(records)
    status = graph.prerequisite_status(argv[2], _goal_statuses(goals))
    _print_json(
        {
            "schema": GOAL_CLI_SCHEMA,
            "ok": True,
            "goal_id": argv[2],
            "dependency_status": status,
            "dependency_graph": graph.as_dict(_goal_statuses(goals)),
        }
    )
    return True


def try_handle_goal_command(argv: list[str], *, repo_root: Path) -> bool:
    clean_argv = [str(item).strip() for item in argv if str(item).strip()]
    if not clean_argv or clean_argv[0].lower() != "goal":
        return False
    normalized = [clean_argv[0].lower(), *[item.lower() if index == 1 else item for index, item in enumerate(clean_argv[1:], start=1)]]

    for handler in (
        _handle_add,
        _handle_list,
        _handle_status,
        _handle_run,
        _handle_loop,
        _handle_run_next,
        _handle_scheduler_status,
        _handle_deps,
    ):
        if handler(normalized, repo_root):
            return True

    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": False, "error": "unknown_goal_command"})
    return True


__all__ = ["GOAL_CLI_SCHEMA", "try_handle_goal_command"]
