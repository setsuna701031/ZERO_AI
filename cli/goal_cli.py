from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.tasks.engineering_goal_dependency_graph import EngineeringGoalDependencyGraph
from core.tasks.engineering_goal_portfolio import EngineeringGoalPortfolio
from core.tasks.engineering_goal_scheduler import EngineeringGoalScheduler


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
    return _workspace_root(repo_root) / "engineering_goals.json"


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _read_store(repo_root: Path) -> dict[str, Any]:
    path = _store_path(repo_root)
    if not path.is_file():
        return {"schema": GOAL_CLI_SCHEMA, "goals": [], "dependencies": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    goals = data.get("goals")
    dependencies = data.get("dependencies")
    return {
        "schema": _clean_text(data.get("schema"), GOAL_CLI_SCHEMA),
        "goals": [copy.deepcopy(item) for item in goals if isinstance(item, dict)] if isinstance(goals, list) else [],
        "dependencies": (
            [copy.deepcopy(item) for item in dependencies if isinstance(item, dict)]
            if isinstance(dependencies, list)
            else []
        ),
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


def _new_goal_id(summary: str, existing_goals: Sequence[Mapping[str, Any]]) -> str:
    base = "goal_" + hashlib.sha1(summary.encode("utf-8")).hexdigest()[:12]
    existing = {_goal_id(goal) for goal in existing_goals}
    if base not in existing:
        return base
    suffix = 2
    while f"{base}_{suffix}" in existing:
        suffix += 1
    return f"{base}_{suffix}"


def _goal_record(summary: str, existing_goals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    now = time.time()
    goal_id = _new_goal_id(summary, existing_goals)
    return {
        "goal_id": goal_id,
        "priority": 0.0,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "last_result_summary": "",
        "blocked_reason": "",
        "planning_refs": {"source": "goal_cli"},
        "lifecycle_refs": {},
        "payload": {
            "goal": summary,
            "goal_id": goal_id,
            "package_id": goal_id,
            "task_id": goal_id,
            "task_type": "engineering_task",
        },
        "summary": summary,
    }


def _goal_statuses(goals: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {_goal_id(goal): _status(goal) for goal in goals if _goal_id(goal)}


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


def _handle_add(argv: list[str], repo_root: Path) -> bool:
    if len(argv) < 3 or argv[1] != "add":
        return False
    summary = " ".join(argv[2:]).strip()
    if not summary:
        _print_json({"schema": GOAL_CLI_SCHEMA, "ok": False, "error": "goal_summary_required"})
        return True
    store = _read_store(repo_root)
    goals = _ordered_goals(store["goals"])
    goal = _goal_record(summary, goals)
    goals.append(goal)
    store["goals"] = goals
    _write_store(repo_root, store)
    EngineeringGoalPortfolio().decide_next_goal(goals)
    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": True, "created": True, "goal": goal})
    return True


def _handle_list(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "list":
        return False
    store = _read_store(repo_root)
    EngineeringGoalPortfolio().decide_next_goal(store["goals"])
    _print_goal_list(store["goals"])
    return True


def _handle_status(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "status":
        return False
    store = _read_store(repo_root)
    goal = _find_goal(store["goals"], argv[2])
    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": goal is not None, "goal": goal or {}, "goal_id": argv[2]})
    return True


def _handle_run_next(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "run-next":
        return False
    store = _read_store(repo_root)
    result = EngineeringGoalScheduler().schedule_next_goal(store["goals"])
    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": bool(result.get("ok")), "scheduler_result": result})
    return True


def _handle_scheduler_status(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] not in {"pause", "resume", "cancel", "defer"}:
        return False
    store = _read_store(repo_root)
    scheduler = EngineeringGoalScheduler()
    command = argv[1]
    goal_id = argv[2]
    if command == "pause":
        result = scheduler.pause_goal(store["goals"], goal_id)
    elif command == "resume":
        result = scheduler.resume_goal(store["goals"], goal_id)
    elif command == "cancel":
        result = scheduler.cancel_goal(store["goals"], goal_id)
    else:
        result = scheduler.defer_goal(store["goals"], goal_id)
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
        _handle_run_next,
        _handle_scheduler_status,
        _handle_deps,
    ):
        if handler(normalized, repo_root):
            return True

    _print_json({"schema": GOAL_CLI_SCHEMA, "ok": False, "error": "unknown_goal_command"})
    return True


__all__ = ["GOAL_CLI_SCHEMA", "try_handle_goal_command"]
