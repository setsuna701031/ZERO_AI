from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from cli.zero_natural_task import run_natural_task
from core.runtime.runtime_autonomous_loop import RuntimeAutonomousLoop, project_runtime_mission, project_runtime_session, project_runtime_scheduler, project_runtime_worker
from core.runtime.runtime_mission_model import load_mission
from core.runtime.runtime_operator_session import load_runtime_session
from core.runtime.runtime_session_queue import load_scheduler_state
from core.runtime.runtime_worker_service import load_worker_state
from core.runtime.runtime_workspace_observer import RuntimeWorkspaceObserver
from core.runtime.runtime_repair_advisor import RuntimeRepairAdvisor
from core.runtime.runtime_bounded_repair_retry_loop import (
    RuntimeBoundedRepairRetryLoop,
)
from core.runtime.runtime_change_proposal_engine import (
    RuntimeChangeProposalEngine,
)


ZERO_AUTONOMOUS_LOOP_CLI_SCHEMA = "zero.autonomous_loop_cli.v1"
RUNTIME_AUTONOMOUS_TASK_BATCH_SCHEMA = (
    "zero.runtime.autonomous_task_batch.v1"
)
DEFAULT_RESULT_PATH = Path(
    "workspace/operator_autonomous_loop/autonomous_loop_result.json"
)

def project_runtime_session_file(path: str | Path) -> dict[str, Any]:
    """Read a persisted session and expose loop state without resuming it."""
    return project_runtime_session(load_runtime_session(path))

def project_runtime_scheduler_file(path: str | Path) -> dict[str, Any]:
    return project_runtime_scheduler(load_scheduler_state(path))

def project_runtime_worker_file(path: str | Path, *, now: Any = None) -> dict[str, Any]:
    return project_runtime_worker(load_worker_state(path), now=now)

def project_runtime_mission_file(path: str | Path) -> dict[str, Any]:
    return project_runtime_mission(load_mission(path, check_expiry=False))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli.zero_autonomous_loop",
        description="Run a bounded batch of existing natural-language tasks.",
    )
    parser.add_argument("command_or_task_file")
    parser.add_argument("task_file", nargs="?")
    parser.add_argument("--controlled", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--target-root", default=".")
    parser.add_argument(
        "--workspace-root", default="workspace/operator_intake"
    )
    parser.add_argument("--result-path", default=str(DEFAULT_RESULT_PATH))
    parser.add_argument("--observe-workspace", action="store_true")
    parser.add_argument("--advise-repair", action="store_true")
    parser.add_argument("--bounded-retry", action="store_true")
    parser.add_argument("--repair-max-attempts", type=int, default=2)
    parser.add_argument("--allow-runner-exception-retry", action="store_true")
    parser.add_argument("--propose-changes", action="store_true")
    return parser


def _resolved_task_file(command_or_task_file: str, task_file: str | None) -> str:
    if command_or_task_file == "run":
        return _text(task_file)
    if task_file:
        return ""
    return _text(command_or_task_file)


def load_task_batch(task_file: str | Path) -> dict[str, Any]:
    path = Path(task_file)
    if not path.is_file():
        return {"ok": False, "denial_reason": "task_file_not_found", "tasks": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "denial_reason": "invalid_task_batch_json",
            "error_type": type(exc).__name__,
            "tasks": [],
        }
    if not isinstance(payload, dict):
        return {"ok": False, "denial_reason": "task_batch_object_required", "tasks": []}
    if payload.get("schema") != RUNTIME_AUTONOMOUS_TASK_BATCH_SCHEMA:
        return {"ok": False, "denial_reason": "invalid_task_batch_schema", "tasks": []}
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return {"ok": False, "denial_reason": "tasks_list_required", "tasks": []}
    for index, task in enumerate(tasks):
        if not isinstance(task, (str, Mapping)):
            return {
                "ok": False,
                "denial_reason": f"invalid_task:{index}",
                "tasks": [],
            }
        goal = task if isinstance(task, str) else task.get("goal")
        if not _text(goal):
            return {
                "ok": False,
                "denial_reason": f"task_goal_required:{index}",
                "tasks": [],
            }
    return {"ok": True, "denial_reason": "", "tasks": deepcopy(tasks)}


def _write_result(path: str | Path, result: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            dict(result), ensure_ascii=False, indent=2, sort_keys=True, default=str
        ),
        encoding="utf-8",
    )


def _cli_result(
    *,
    ok: bool,
    controlled: bool,
    task_file: str,
    tasks_received: int,
    max_iterations: int,
    stop_on_error: bool,
    loop_result: Mapping[str, Any] | None,
    result_path: str,
    denial_reason: str = "",
    workspace_observer_enabled: bool = False,
    repair_advisor_enabled: bool = False,
    bounded_retry_enabled: bool = False,
    repair_max_attempts: int = 2,
    change_proposal_engine_enabled: bool = False,
) -> dict[str, Any]:
    loop = dict(loop_result or {})
    iterations = loop.get("iteration_results")
    iterations = iterations if isinstance(iterations, list) else []
    observed_iterations = sum(
        item.get("workspace_observed") is True
        for item in iterations
        if isinstance(item, Mapping)
    )
    observation_issue_count = sum(
        len(_mapping(item.get("workspace_observation")).get("issues") or [])
        for item in iterations
        if isinstance(item, Mapping)
    )
    repair_advised_iterations = sum(
        item.get("repair_advised") is True
        for item in iterations
        if isinstance(item, Mapping)
    )
    manual_review_required_count = sum(
        item.get("repair_advisor_status") == "manual_review_required"
        for item in iterations
        if isinstance(item, Mapping)
    )
    repair_advisor_error_count = sum(
        item.get("repair_advisor_status") == "advisor_error"
        for item in iterations
        if isinstance(item, Mapping)
    )
    bounded_results = [
        _mapping(item.get("bounded_retry_result"))
        for item in iterations
        if isinstance(item, Mapping)
        and isinstance(item.get("bounded_retry_result"), Mapping)
        and item.get("bounded_retry_result")
    ]
    retried_tasks = sum(
        int(item.get("retry_count") or 0) > 0 for item in bounded_results
    )
    retry_attempt_count = sum(
        int(item.get("retry_count") or 0) for item in bounded_results
    )
    retry_exhausted_count = sum(
        item.get("loop_status") == "failed_retry_exhausted"
        for item in bounded_results
    )
    non_retryable_failure_count = sum(
        item.get("loop_status") == "failed_not_retryable"
        for item in bounded_results
    )
    proposed_change_iterations = sum(
        item.get("change_proposed") is True
        for item in iterations if isinstance(item, Mapping)
    )
    manual_approval_required_count = sum(
        _mapping(item.get("change_proposal")).get("approval_status") == "pending"
        for item in iterations if isinstance(item, Mapping)
        and item.get("change_proposal")
    )
    blocked_proposal_count = sum(
        item.get("change_proposal_status") == "proposal_blocked_by_safety"
        for item in iterations if isinstance(item, Mapping)
    )
    proposal_error_count = sum(
        item.get("change_proposal_status") == "proposal_error"
        for item in iterations if isinstance(item, Mapping)
    )
    operator_approval_required_count = sum(
        item.get("approval_required") is True
        for item in iterations if isinstance(item, Mapping)
    )
    pending_approval_count = sum(
        item.get("approval_status") == "pending"
        for item in iterations if isinstance(item, Mapping)
    )
    apply_admission_required_count = sum(
        item.get("apply_admission_required") is True
        for item in iterations if isinstance(item, Mapping)
    )
    apply_admission_not_evaluated_count = sum(
        item.get("apply_admission_status") == "not_evaluated"
        for item in iterations if isinstance(item, Mapping)
    )
    execution_plan_required_count = sum(
        item.get("execution_plan_required") is True
        for item in iterations if isinstance(item, Mapping)
    )
    execution_plan_not_built_count = sum(
        item.get("execution_plan_status") == "not_built"
        for item in iterations if isinstance(item, Mapping)
    )
    review_pending_count = sum(
        item.get("review_status") == "pending"
        for item in iterations if isinstance(item, Mapping)
    )
    review_approved_count = sum(
        item.get("review_status") == "approved"
        for item in iterations if isinstance(item, Mapping)
    )
    review_rejected_count = sum(
        item.get("review_status") == "rejected"
        for item in iterations if isinstance(item, Mapping)
    )
    executor_admission_ready_count = sum(
        item.get("executor_admission_ready") is True
        for item in iterations if isinstance(item, Mapping)
    )
    controlled_execution_operator_request_required_count = sum(
        item.get("controlled_execution_status") == "operator_request_required"
        for item in iterations if isinstance(item, Mapping)
    )
    controlled_execution_ready_for_dry_run_count = sum(
        item.get("controlled_execution_status") == "ready_for_dry_run"
        for item in iterations if isinstance(item, Mapping)
    )
    controlled_execution_completed_count = sum(
        item.get("controlled_execution_status") == "completed"
        for item in iterations if isinstance(item, Mapping)
    )
    controlled_execution_blocked_count = sum(
        item.get("controlled_execution_status") == "blocked"
        for item in iterations if isinstance(item, Mapping)
    )
    executor_token_issued_count = sum(
        item.get("executor_token_status") == "issued"
        for item in iterations if isinstance(item, Mapping)
    )
    executor_token_denied_count = sum(
        item.get("executor_token_status") == "denied"
        for item in iterations if isinstance(item, Mapping)
    )
    active_authorization_operator_required_count = sum(
        item.get("active_authorization_status") == "operator_authorization_required"
        for item in iterations if isinstance(item, Mapping)
    )
    active_authorization_pending_count = sum(
        item.get("active_authorization_status") == "pending"
        for item in iterations if isinstance(item, Mapping)
    )
    active_authorization_authorized_count = sum(
        item.get("active_authorization_status") == "authorized"
        for item in iterations if isinstance(item, Mapping)
    )
    active_authorization_rejected_count = sum(
        item.get("active_authorization_status") == "rejected"
        for item in iterations if isinstance(item, Mapping)
    )
    active_authorization_invalid_count = sum(
        item.get("active_authorization_status") == "invalid"
        for item in iterations if isinstance(item, Mapping)
    )
    transactional_execution_committed_count = sum(item.get("transactional_execution_status") == "committed" for item in iterations if isinstance(item, Mapping))
    transactional_execution_rolled_back_count = sum(item.get("transactional_execution_status") == "rolled_back" for item in iterations if isinstance(item, Mapping))
    transactional_execution_blocked_count = sum(item.get("transactional_execution_status") == "blocked" for item in iterations if isinstance(item, Mapping))
    transactional_execution_critical_failure_count = sum(item.get("transactional_execution_status") == "critical_failure" for item in iterations if isinstance(item, Mapping))
    return {
        "schema": ZERO_AUTONOMOUS_LOOP_CLI_SCHEMA,
        "ok": ok,
        "controlled": controlled,
        "task_file": task_file,
        "tasks_received": tasks_received,
        "max_iterations": max_iterations,
        "stop_on_error": stop_on_error,
        "loop_result": deepcopy(loop),
        "result_path": result_path,
        "denial_reason": denial_reason,
        "autonomous_task_creation": False,
        "goal_mutation_allowed": False,
        "requested_changes_modified": False,
        "runtime_loop_closed": True,
        "workspace_observer_enabled": workspace_observer_enabled,
        "observed_iterations": observed_iterations,
        "observation_issue_count": observation_issue_count,
        "repair_advisor_enabled": repair_advisor_enabled,
        "repair_advised_iterations": repair_advised_iterations,
        "manual_review_required_count": manual_review_required_count,
        "repair_advisor_error_count": repair_advisor_error_count,
        "bounded_retry_enabled": bounded_retry_enabled,
        "repair_max_attempts": repair_max_attempts,
        "retried_tasks": retried_tasks,
        "retry_attempt_count": retry_attempt_count,
        "retry_exhausted_count": retry_exhausted_count,
        "non_retryable_failure_count": non_retryable_failure_count,
        "change_proposal_engine_enabled": change_proposal_engine_enabled,
        "proposed_change_iterations": proposed_change_iterations,
        "manual_approval_required_count": manual_approval_required_count,
        "blocked_proposal_count": blocked_proposal_count,
        "proposal_error_count": proposal_error_count,
        "operator_approval_required_count": operator_approval_required_count,
        "pending_approval_count": pending_approval_count,
        "apply_admission_required_count": apply_admission_required_count,
        "apply_admission_not_evaluated_count": apply_admission_not_evaluated_count,
        "execution_plan_required_count": execution_plan_required_count,
        "execution_plan_not_built_count": execution_plan_not_built_count,
        "review_pending_count": review_pending_count,
        "review_approved_count": review_approved_count,
        "review_rejected_count": review_rejected_count,
        "executor_admission_ready_count": executor_admission_ready_count,
        "controlled_execution_operator_request_required_count": controlled_execution_operator_request_required_count,
        "controlled_execution_ready_for_dry_run_count": controlled_execution_ready_for_dry_run_count,
        "controlled_execution_completed_count": controlled_execution_completed_count,
        "controlled_execution_blocked_count": controlled_execution_blocked_count,
        "executor_token_issued_count": executor_token_issued_count,
        "executor_token_denied_count": executor_token_denied_count,
        "active_authorization_operator_required_count": active_authorization_operator_required_count,
        "active_authorization_pending_count": active_authorization_pending_count,
        "active_authorization_authorized_count": active_authorization_authorized_count,
        "active_authorization_rejected_count": active_authorization_rejected_count,
        "active_authorization_invalid_count": active_authorization_invalid_count,
        "transactional_execution_committed_count": transactional_execution_committed_count,
        "transactional_execution_rolled_back_count": transactional_execution_rolled_back_count,
        "transactional_execution_blocked_count": transactional_execution_blocked_count,
        "transactional_execution_critical_failure_count": transactional_execution_critical_failure_count,
    }


def run_autonomous_loop_cli(
    task_file: str | Path,
    *,
    controlled: bool = False,
    max_iterations: int = 10,
    stop_on_error: bool = False,
    target_root: str = ".",
    workspace_root: str | Path = "workspace/operator_intake",
    result_path: str | Path = DEFAULT_RESULT_PATH,
    natural_task_runner: Callable[..., Mapping[str, Any]] = run_natural_task,
    loop_class: type[RuntimeAutonomousLoop] = RuntimeAutonomousLoop,
    observe_workspace: bool = False,
    observer_factory: Callable[..., Any] = RuntimeWorkspaceObserver,
    advise_repair: bool = False,
    repair_advisor_factory: Callable[..., Any] = RuntimeRepairAdvisor,
    bounded_retry: bool = False,
    repair_max_attempts: int = 2,
    allow_runner_exception_retry: bool = False,
    bounded_retry_loop_class: type[RuntimeBoundedRepairRetryLoop] = (
        RuntimeBoundedRepairRetryLoop
    ),
    propose_changes: bool = False,
    change_proposal_engine_factory: Callable[..., Any] = (
        RuntimeChangeProposalEngine
    ),
) -> tuple[dict[str, Any], int]:
    task_file_text = str(task_file)
    result_path_text = str(result_path)
    loaded = load_task_batch(task_file)
    denial_reason = _text(loaded.get("denial_reason"))
    if max_iterations <= 0:
        denial_reason = "max_iterations_must_be_greater_than_zero"
    if repair_max_attempts < 1:
        denial_reason = "repair_max_attempts_must_be_greater_than_zero"
    if denial_reason:
        result = _cli_result(
            ok=False,
            controlled=controlled,
            task_file=task_file_text,
            tasks_received=0,
            max_iterations=max_iterations,
            stop_on_error=stop_on_error,
            loop_result={},
            result_path=result_path_text,
            denial_reason=denial_reason,
            workspace_observer_enabled=observe_workspace,
            repair_advisor_enabled=advise_repair or bounded_retry or propose_changes,
            bounded_retry_enabled=bounded_retry,
            repair_max_attempts=repair_max_attempts,
            change_proposal_engine_enabled=propose_changes,
        )
        _write_result(result_path, result)
        return result, 2

    tasks = deepcopy(loaded["tasks"])

    def task_runner(goal: str) -> Mapping[str, Any]:
        return natural_task_runner(
            goal,
            controlled=controlled,
            target_root=target_root,
            workspace_root=workspace_root,
        )

    observer = observer_factory(workspace_root=target_root) if observe_workspace else None
    advisor_enabled = advise_repair or bounded_retry or propose_changes
    advisor = repair_advisor_factory() if advisor_enabled else None
    proposal_engine = (
        change_proposal_engine_factory() if propose_changes else None
    )
    loop_kwargs: dict[str, Any] = dict(
        task_runner=task_runner,
        activity_memory=None,
        max_iterations=max_iterations,
        stop_on_error=stop_on_error,
    )
    if bounded_retry:
        loop_kwargs["bounded_repair_retry_loop"] = bounded_retry_loop_class(
            task_runner=task_runner,
            observer=observer,
            repair_advisor=advisor,
            max_attempts=repair_max_attempts,
            allow_bounded_retry=True,
            allow_runner_exception_retry=allow_runner_exception_retry,
        )
    else:
        if observer is not None:
            loop_kwargs["observer"] = observer
        if advisor is not None:
            loop_kwargs["repair_advisor"] = advisor
    if proposal_engine is not None:
        loop_kwargs["change_proposal_engine"] = proposal_engine
    loop = loop_class(**loop_kwargs)
    loop_result = loop.run(tasks)
    loop_status = _text(loop_result.get("loop_status"))
    exit_code = 0 if loop_status in {"completed", "empty_queue"} else 1
    result = _cli_result(
        ok=exit_code == 0,
        controlled=controlled,
        task_file=task_file_text,
        tasks_received=len(tasks),
        max_iterations=max_iterations,
        stop_on_error=stop_on_error,
        loop_result=loop_result,
        result_path=result_path_text,
        workspace_observer_enabled=observe_workspace,
        repair_advisor_enabled=advisor_enabled,
        bounded_retry_enabled=bounded_retry,
        repair_max_attempts=repair_max_attempts,
        change_proposal_engine_enabled=propose_changes,
    )
    _write_result(result_path, result)
    return result, exit_code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    task_file = _resolved_task_file(args.command_or_task_file, args.task_file)
    if not task_file:
        result = _cli_result(
            ok=False,
            controlled=args.controlled,
            task_file="",
            tasks_received=0,
            max_iterations=args.max_iterations,
            stop_on_error=args.stop_on_error,
            loop_result={},
            result_path=args.result_path,
            denial_reason="task_file_required_or_unexpected_positional_argument",
            workspace_observer_enabled=args.observe_workspace,
            repair_advisor_enabled=(
                args.advise_repair or args.bounded_retry or args.propose_changes
            ),
            bounded_retry_enabled=args.bounded_retry,
            repair_max_attempts=args.repair_max_attempts,
            change_proposal_engine_enabled=args.propose_changes,
        )
        _write_result(args.result_path, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    result, exit_code = run_autonomous_loop_cli(
        task_file,
        controlled=args.controlled,
        max_iterations=args.max_iterations,
        stop_on_error=args.stop_on_error,
        target_root=args.target_root,
        workspace_root=args.workspace_root,
        result_path=args.result_path,
        observe_workspace=args.observe_workspace,
        advise_repair=args.advise_repair,
        bounded_retry=args.bounded_retry,
        repair_max_attempts=args.repair_max_attempts,
        allow_runner_exception_retry=args.allow_runner_exception_retry,
        propose_changes=args.propose_changes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_RESULT_PATH",
    "RUNTIME_AUTONOMOUS_TASK_BATCH_SCHEMA",
    "ZERO_AUTONOMOUS_LOOP_CLI_SCHEMA",
    "build_parser",
    "load_task_batch",
    "main",
    "project_runtime_session_file",
    "project_runtime_mission_file",
    "project_runtime_scheduler_file",
    "project_runtime_worker_file",
    "run_autonomous_loop_cli",
]
