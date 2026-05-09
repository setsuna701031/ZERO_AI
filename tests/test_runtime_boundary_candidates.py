from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


SCHEDULER_BOUNDARY_CANDIDATES = {
    "trace_runtime": [
        "_trace_",
        "_load_trace",
        "_save_trace",
        "_append_history",
    ],
    "repair_runtime": [
        "repair",
        "rollback",
        "fingerprint",
    ],
    "path_runtime": [
        "_resolve_",
        "_extract_",
        "_artifact_",
        "_scope",
    ],
    "planner_runtime": [
        "_plan_",
        "_planner",
        "_parse_",
    ],
    "repo_sync_runtime": [
        "_sync_",
        "_persist_",
        "_hydrate_",
    ],
}


AGENT_LOOP_BOUNDARY_CANDIDATES = {
    "repo_edit_runtime": [
        "repo_edit",
        "code_edit",
    ],
    "tool_runtime": [
        "_tool_",
        "_execute_tool",
    ],
    "task_runtime": [
        "task_loop",
        "run_task",
        "_enqueue_task",
    ],
    "response_runtime": [
        "_response",
        "_answer",
        "_normalize",
    ],
}


TARGETS = {
    "scheduler": REPO_ROOT / "core/tasks/scheduler.py",
    "agent_loop": REPO_ROOT / "core/agent/agent_loop.py",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _collect_matches(content: str, candidates: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}

    for bucket, patterns in candidates.items():
        matches = []

        for pattern in patterns:
            if pattern in content:
                matches.append(pattern)

        result[bucket] = matches

    return result


def test_scheduler_boundary_candidates_are_visible() -> None:
    content = _read(TARGETS["scheduler"])
    matches = _collect_matches(content, SCHEDULER_BOUNDARY_CANDIDATES)

    for bucket, values in matches.items():
        assert values, bucket


def test_agent_loop_boundary_candidates_are_visible() -> None:
    content = _read(TARGETS["agent_loop"])
    matches = _collect_matches(content, AGENT_LOOP_BOUNDARY_CANDIDATES)

    for bucket, values in matches.items():
        assert values, bucket