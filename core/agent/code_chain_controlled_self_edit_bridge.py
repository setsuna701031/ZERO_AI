from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable

from core.agent.code_chain_repair_evidence import export_code_chain_repair_evidence
from core.agent.code_chain_repair_report import normalize_code_chain_repair_report
from core.runtime.agent_execution_runtime import agent_execution_path


CODE_CHAIN_ROUTE_VALUES = {
    "code_chain_controlled_self_edit",
    "code_chain_controlled_self_edit_bridge",
    "controlled_self_edit",
    "controlled_code_edit",
}

CODE_CHAIN_TASK_KINDS = {
    "code_fix",
    "repair",
    "refactor",
    "controlled_edit",
    "engineering_mutation",
}


def run_planner_owned_code_chain_bridge(
    *,
    agent: Any,
    user_input: str,
    call_planner_like: Callable[..., dict[str, Any]] | None,
    fallback_candidate: Callable[[str], bool] | None = None,
    fallback_enabled: bool = True,
) -> dict[str, Any] | None:
    text = str(user_input or "").strip()
    if not text or not callable(call_planner_like):
        return None

    repo_root = _repo_root_from_agent(agent)
    task_id = f"code_chain_controlled_self_edit_{str(abs(hash(text)))[-8:]}"
    context = {
        "source": "agent_loop",
        "route": "code_chain_controlled_self_edit_bridge",
        "code_chain_controlled_self_edit_bridge": True,
        "planner_owned_intent_routing": True,
        "planner_runtime_dispatch": True,
        "workspace_root": str(repo_root / "workspace"),
        "repo_root": str(repo_root),
        "user_input": text,
    }
    route = {
        "mode": "code_chain_controlled_self_edit_bridge",
        "task": True,
        "forced_route": True,
        "planner_runtime_dispatch": True,
        "runtime_execution_required": True,
        "authority_path": agent_execution_path()["authority_path"],
        "planner_owned_intent_routing": True,
    }

    planner_result = call_planner_like(
        agent,
        context=context,
        user_input=text,
        route=route,
    )
    route_decision = planner_code_chain_route_decision(planner_result)
    fallback_used = False
    if not route_decision["should_route"]:
        if not fallback_enabled or not callable(fallback_candidate) or not bool(fallback_candidate(text)):
            return None
        fallback_used = True
        route_decision = {
            "should_route": True,
            "source": "agent_loop_keyword_fallback",
            "reason": "v1 fallback candidate matched",
            "route": "",
            "task_kind": "",
            "requires_controlled_mutation": False,
        }

    raw_steps = extract_plan_steps(planner_result)
    controlled_steps = [step for step in raw_steps if is_controlled_edit_step(step)]
    if not controlled_steps:
        failure_reason = "planner did not produce a controlled mutation step"
        execution = _execution_failure(failure_reason)
        review = reviewable_result(
            ok=False,
            task_id=task_id,
            goal=text,
            steps=[],
            execution_result=execution,
            failure_reason=failure_reason,
        )
        return _make_response(
            agent=agent,
            ok=False,
            context=context,
            route=route,
            planner_result=planner_result,
            plan={
                "ok": False,
                "planner_result": copy.deepcopy(planner_result),
                "steps": raw_steps,
                "route_decision": copy.deepcopy(route_decision),
                "planner_owned_intent_routing": not fallback_used,
                "fallback_used": fallback_used,
            },
            execution=execution,
            final_answer=failure_reason,
            error=failure_reason,
            review=review,
            extra={
                "planner_owned_intent_routing": not fallback_used,
                "code_chain_v1_fallback_used": fallback_used,
            },
        )

    execution_runtime = runtime_owner_from_agent(agent)
    if execution_runtime is None:
        failure_reason = "Runtime unavailable for controlled mutation execution"
        execution = _execution_failure(failure_reason)
        review = reviewable_result(
            ok=False,
            task_id=task_id,
            goal=text,
            steps=controlled_steps,
            execution_result=execution,
            failure_reason=failure_reason,
        )
        return _make_response(
            agent=agent,
            ok=False,
            context=context,
            route=route,
            planner_result=planner_result,
            plan={
                "ok": False,
                "planner_result": copy.deepcopy(planner_result),
                "steps": controlled_steps,
                "route_decision": copy.deepcopy(route_decision),
                "planner_owned_intent_routing": not fallback_used,
                "fallback_used": fallback_used,
            },
            execution=execution,
            final_answer=failure_reason,
            error=failure_reason,
            review=review,
            extra={
                "planner_owned_intent_routing": not fallback_used,
                "code_chain_v1_fallback_used": fallback_used,
            },
        )

    first_attempt = execute_code_chain_attempt(
        execution_runtime=execution_runtime,
        repo_root=repo_root,
        task_id=task_id,
        planner_result=planner_result,
        raw_steps=raw_steps,
        context=context,
        fallback_used=fallback_used,
        attempt_index=1,
        attempt_kind="initial",
    )
    attempts = [first_attempt]
    final_attempt = first_attempt
    repair_reason = ""

    if not first_attempt["ok"]:
        repair_reason = (
            "verification failed; requesting planner repair attempt: "
            + first_attempt["failure_reason"]
        )
        repair_context = {
            **copy.deepcopy(context),
            "repair_loop": True,
            "repair_attempt": 2,
            "repair_reason": repair_reason,
            "previous_failure": copy.deepcopy(first_attempt["execution_result"]),
            "previous_planner_result": copy.deepcopy(planner_result),
            "attempt_history": [attempt_summary(first_attempt)],
        }
        try:
            repair_planner_result = call_planner_like(
                agent,
                context=repair_context,
                user_input=text,
                route={**copy.deepcopy(route), "repair_loop": True, "repair_attempt": 2},
            )
        except Exception as exc:
            repair_planner_result = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "steps": [],
            }

        repair_raw_steps = extract_plan_steps(repair_planner_result)
        repair_controlled_steps = [
            step for step in repair_raw_steps if is_controlled_edit_step(step)
        ]
        if repair_controlled_steps:
            repair_attempt = execute_code_chain_attempt(
                execution_runtime=execution_runtime,
                repo_root=repo_root,
                task_id=task_id,
                planner_result=repair_planner_result,
                raw_steps=repair_raw_steps,
                context=repair_context,
                fallback_used=fallback_used,
                attempt_index=2,
                attempt_kind="repair",
            )
            attempts.append(repair_attempt)
            final_attempt = repair_attempt
        else:
            terminal = _execution_failure("planner did not produce a repair controlled mutation step")
            terminal["previous_failure"] = copy.deepcopy(first_attempt["execution_result"])
            terminal_attempt = {
                "attempt_index": 2,
                "attempt_kind": "repair",
                "ok": False,
                "planner_result": copy.deepcopy(repair_planner_result),
                "raw_steps": repair_raw_steps,
                "executable_steps": [],
                "execution_result": terminal,
                "failure_reason": terminal["message"],
            }
            attempts.append(terminal_attempt)
            final_attempt = terminal_attempt

    execution_result = final_attempt["execution_result"]
    executable_steps = final_attempt["executable_steps"]
    ok = bool(final_attempt["ok"])
    final_answer = text_value(
        execution_result.get("final_answer") if isinstance(execution_result, dict) else ""
    ) or ("controlled code fix completed" if ok else "controlled code fix failed")
    review = reviewable_result(
        ok=ok,
        task_id=task_id,
        goal=text_value(final_attempt["planner_result"].get("goal")) or text,
        steps=[step for attempt in attempts for step in attempt.get("executable_steps", [])],
        execution_result=execution_result if isinstance(execution_result, dict) else {},
        failure_reason=first_attempt["failure_reason"] if len(attempts) > 1 else "",
    )
    review["status"] = "ok" if ok else "failed"
    review["attempt_count"] = len(attempts)
    review["verification_history"] = verification_history_from_attempts(attempts)
    if len(attempts) > 1:
        review["failure_reason"] = first_attempt["failure_reason"]
    review["repair_reason"] = repair_reason
    review["final_result"] = "passed" if ok else "terminal_failure"
    review["changed_files"] = collect_changed_files(
        [result for attempt in attempts for result in attempt_results(attempt)]
    )
    review["changed_file_reasons"] = changed_file_reasons(
        [step for attempt in attempts for step in attempt.get("executable_steps", [])],
        review["changed_files"],
        text,
    )
    execution = copy.deepcopy(execution_result) if isinstance(execution_result, dict) else {"ok": False}
    execution["reviewable_result"] = copy.deepcopy(review)
    execution["code_chain_controlled_self_edit_bridge"] = True
    execution["planner_owned_intent_routing"] = not fallback_used
    execution["repair_loop_entered"] = len(attempts) > 1
    execution["attempt_history"] = [attempt_summary(attempt) for attempt in attempts]
    execution["original_failure"] = (
        copy.deepcopy(first_attempt["execution_result"]) if len(attempts) > 1 else {}
    )
    execution["verification_history"] = copy.deepcopy(review["verification_history"])
    repair_report = normalize_code_chain_repair_report(
        ok=ok,
        execution=execution,
        reviewable_result=review,
    )
    repair_evidence = export_code_chain_repair_evidence(
        repo_root=repo_root,
        task_id=task_id,
        repair_result_report=repair_report,
    )
    if repair_evidence:
        repair_report["evidence_path"] = repair_evidence["evidence_path"]
        repair_report["artifact_path"] = repair_evidence["artifact_path"]
        repair_report["evidence_type"] = repair_evidence["evidence_type"]
    execution["repair_result_report"] = copy.deepcopy(repair_report)
    execution["repair_result_evidence"] = copy.deepcopy(repair_evidence)
    review["repair_result_report"] = copy.deepcopy(repair_report)
    review["repair_result_evidence"] = copy.deepcopy(repair_evidence)

    return _make_response(
        agent=agent,
        ok=ok,
        context=context,
        route=route,
        planner_result=planner_result,
        plan={
            "ok": bool(controlled_steps),
            "planner_mode": "code_chain_controlled_self_edit_bridge_v2",
            "planner_result": copy.deepcopy(planner_result),
            "controlled_mutation_plan": copy.deepcopy(controlled_steps),
            "steps": copy.deepcopy(executable_steps),
            "attempt_history": [attempt_summary(attempt) for attempt in attempts],
            "route_decision": copy.deepcopy(route_decision),
            "planner_owned_intent_routing": not fallback_used,
            "fallback_used": fallback_used,
            "boundary": {
                "agent_loop_routes_on_planner_metadata": True,
                "agent_loop_keyword_detection_is_fallback_only": True,
                "planner_produces_plan": True,
                "runtime_owns_execution": True,
                "taskrunner_required": True,
                "step_executor_executes": True,
                "step_executor_endpoint_only": True,
                "runtime_file_service_required": True,
                "runtime_mutation_gateway_required": True,
                "authority_path": agent_execution_path()["authority_path"],
            },
        },
        execution=execution,
        final_answer=final_answer,
        error=None if ok else review.get("failure_reason") or final_answer,
        review=review,
        extra={
            "planner_owned_intent_routing": not fallback_used,
            "code_chain_v1_fallback_used": fallback_used,
            "controlled_mutation_plan_produced": bool(controlled_steps),
            "repair_loop_entered": len(attempts) > 1,
            "repair_result_report": copy.deepcopy(repair_report),
            "repair_result_evidence": copy.deepcopy(repair_evidence),
        },
    )


def planner_code_chain_route_decision(planner_result: dict[str, Any]) -> dict[str, Any]:
    payload = planner_result if isinstance(planner_result, dict) else {}
    candidates = [payload]
    for key in ("route", "route_metadata", "routing", "metadata", "intent"):
        value = payload.get(key)
        if isinstance(value, dict):
            candidates.append(value)

    for candidate in candidates:
        route_value = text_value(
            candidate.get("route")
            or candidate.get("execution_route")
            or candidate.get("mode")
        ).lower()
        task_kind = text_value(
            candidate.get("task_kind")
            or candidate.get("intent")
            or candidate.get("semantic_type")
        ).lower()
        code_chain_intent = bool(
            candidate.get("code_chain_intent")
            or candidate.get("code_chain_controlled_self_edit")
            or candidate.get("controlled_self_edit")
        )
        requires_controlled_mutation = bool(candidate.get("requires_controlled_mutation"))

        if (
            code_chain_intent
            or requires_controlled_mutation
            or route_value in CODE_CHAIN_ROUTE_VALUES
            or task_kind in CODE_CHAIN_TASK_KINDS
        ):
            return {
                "should_route": True,
                "source": "planner_route_metadata",
                "reason": "planner declared code-chain controlled edit intent",
                "route": route_value,
                "task_kind": task_kind,
                "code_chain_intent": code_chain_intent,
                "requires_controlled_mutation": requires_controlled_mutation,
            }

    return {
        "should_route": False,
        "source": "planner_route_metadata",
        "reason": "planner did not declare code-chain controlled edit intent",
        "route": "",
        "task_kind": "",
        "code_chain_intent": False,
        "requires_controlled_mutation": False,
    }


def execute_code_chain_attempt(
    *,
    execution_runtime: Any,
    repo_root: Path,
    task_id: str,
    planner_result: dict[str, Any],
    raw_steps: list[dict[str, Any]],
    context: dict[str, Any],
    fallback_used: bool,
    attempt_index: int,
    attempt_kind: str,
) -> dict[str, Any]:
    executable_steps = prepare_steps_for_runtime(raw_steps)
    task = {
        "id": task_id,
        "task_id": task_id,
        "goal": text_value(planner_result.get("goal")),
        "repo_root": str(repo_root),
        "target_repo_root": str(repo_root),
        "workspace_dir": str(repo_root / "workspace"),
        "planner_result": copy.deepcopy(planner_result),
        "steps": copy.deepcopy(executable_steps),
        "planner_owned_intent_routing": not fallback_used,
        "repair_attempt": int(attempt_index),
        "attempt_kind": str(attempt_kind),
    }
    attempt_context = {
        **copy.deepcopy(context),
        "repair_attempt": int(attempt_index),
        "attempt_kind": str(attempt_kind),
    }
    try:
        execution_result = execution_runtime.run_steps(
            steps=copy.deepcopy(executable_steps),
            task=copy.deepcopy(task),
            context=attempt_context,
        )
    except Exception as exc:
        execution_result = _execution_failure(f"{type(exc).__name__}: {exc}")

    ok = bool(execution_result.get("ok")) if isinstance(execution_result, dict) else False
    return {
        "attempt_index": int(attempt_index),
        "attempt_kind": str(attempt_kind),
        "ok": ok,
        "planner_result": copy.deepcopy(planner_result),
        "raw_steps": copy.deepcopy(raw_steps),
        "executable_steps": executable_steps,
        "execution_result": execution_result if isinstance(execution_result, dict) else {},
        "failure_reason": "" if ok else failure_reason_from_execution(execution_result),
    }


def attempt_summary(attempt: dict[str, Any]) -> dict[str, Any]:
    execution_result = attempt.get("execution_result") if isinstance(attempt, dict) else {}
    return {
        "attempt_index": attempt.get("attempt_index"),
        "attempt_kind": attempt.get("attempt_kind"),
        "ok": bool(attempt.get("ok")),
        "failure_reason": text_value(attempt.get("failure_reason")),
        "changed_files": collect_changed_files(attempt_results(attempt)),
        "verification": collect_verification(
            attempt_results(attempt),
            attempt.get("executable_steps") if isinstance(attempt.get("executable_steps"), list) else [],
        ),
        "message": text_value(
            execution_result.get("message") if isinstance(execution_result, dict) else ""
        ),
    }


def attempt_results(attempt: dict[str, Any]) -> list[dict[str, Any]]:
    execution_result = attempt.get("execution_result") if isinstance(attempt, dict) else {}
    if isinstance(execution_result, dict) and isinstance(execution_result.get("results"), list):
        return [item for item in execution_result["results"] if isinstance(item, dict)]
    return []


def verification_history_from_attempts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for attempt in attempts:
        verification = collect_verification(
            attempt_results(attempt),
            attempt.get("executable_steps") if isinstance(attempt.get("executable_steps"), list) else [],
        )
        history.append(
            {
                "attempt_index": attempt.get("attempt_index"),
                "attempt_kind": attempt.get("attempt_kind"),
                "ok": bool(attempt.get("ok")),
                "verification_command": verification["verification_command"],
                "verification_output_summary": verification["verification_output_summary"],
                "failure_reason": text_value(attempt.get("failure_reason")),
            }
        )
    return history


def failure_reason_from_execution(execution_result: Any) -> str:
    if not isinstance(execution_result, dict):
        return "invalid execution result"
    error = execution_result.get("error")
    if isinstance(error, dict):
        message = text_value(error.get("message") or error.get("type"))
        if message:
            return message
    if error is not None:
        message = text_value(error)
        if message:
            return message
    return text_value(
        execution_result.get("message")
        or execution_result.get("final_answer")
        or "controlled mutation execution failed"
    )


def extract_plan_steps(planner_result: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(planner_result, dict):
        return []
    for key in ("steps", "plan_steps", "actions", "tasks"):
        value = planner_result.get(key)
        if isinstance(value, list):
            return [copy.deepcopy(item) for item in value if isinstance(item, dict)]
    nested = planner_result.get("plan")
    if isinstance(nested, dict):
        return extract_plan_steps(nested)
    return []


def normalize_controlled_step(step: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(step) if isinstance(step, dict) else {}
    step_type = text_value(normalized.get("type")).lower()
    if step_type in {"controlled_edit", "code_fix", "code_fix_controlled_edit"}:
        normalized["type"] = "apply_patch"
        normalized.setdefault("controlled_edit_bridge", True)
    elif step_type in {"governed_mutation", "controlled_mutation"}:
        if isinstance(normalized.get("mutation"), dict):
            normalized["type"] = "governed_repair_mutation"
        else:
            normalized["type"] = "apply_patch"
        normalized.setdefault("controlled_edit_bridge", True)
    return normalized


def is_controlled_edit_step(step: dict[str, Any]) -> bool:
    step_type = text_value((step or {}).get("type")).lower()
    if step_type in {
        "apply_patch",
        "apply_unified_diff",
        "governed_repair_mutation",
        "controlled_edit",
        "code_fix",
        "code_fix_controlled_edit",
        "governed_mutation",
        "controlled_mutation",
    }:
        return True
    if isinstance((step or {}).get("edit_payload"), dict):
        return True
    if isinstance((step or {}).get("mutation"), dict):
        return True
    return False


def prepare_steps_for_runtime(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adapted: list[dict[str, Any]] = []
    for raw_step in steps:
        step = normalize_controlled_step(raw_step)
        step["code_chain_controlled_self_edit_bridge"] = True
        step.setdefault("runtime_handoff_prepared", True)
        adapted.append(step)
    return adapted


def runtime_owner_from_agent(agent: Any) -> Any:
    return getattr(agent, "execution_runtime", None)


def reviewable_result(
    *,
    ok: bool,
    task_id: str,
    goal: str,
    steps: list[dict[str, Any]],
    execution_result: dict[str, Any],
    failure_reason: str = "",
) -> dict[str, Any]:
    results = execution_result.get("results") if isinstance(execution_result.get("results"), list) else []
    changed_files = collect_changed_files(results)
    verification = collect_verification(results, steps)
    if not failure_reason and not ok:
        failure_reason = text_value(
            execution_result.get("message")
            or execution_result.get("final_answer")
            or execution_result.get("error")
            or "controlled mutation execution failed"
        )
    requires_review = review_required(execution_result, steps)
    return {
        "status": "ok" if ok else "failed",
        "ok": bool(ok),
        "task_id": task_id,
        "runtime_id": task_id,
        "changed_files": changed_files,
        "changed_file_reasons": changed_file_reasons(steps, changed_files, goal),
        "verification_command": verification["verification_command"],
        "verification_output_summary": verification["verification_output_summary"],
        "human_review_required": requires_review,
        "review_required": requires_review,
        "failure_reason": "" if ok else failure_reason,
    }


def collect_changed_files(results: list[dict[str, Any]]) -> list[str]:
    changed: list[str] = []

    def add(value: Any) -> None:
        text = text_value(value).replace("\\", "/")
        if text and text not in changed:
            changed.append(text)

    def visit(payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        values = payload.get("changed_files")
        if isinstance(values, list):
            for item in values:
                add(item)
        if bool(payload.get("changed")):
            add(payload.get("target_path"))
        result = payload.get("result")
        if isinstance(result, dict):
            visit(result)
        pipeline = payload.get("pipeline_result")
        if isinstance(pipeline, dict):
            visit(pipeline)
        for key in ("rollback_metadata", "repo_impact"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                visit(nested)

    for item in results:
        visit(item)
    return changed


def changed_file_reasons(
    steps: list[dict[str, Any]],
    changed_files: list[str],
    goal: str,
) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    for path in changed_files:
        reason = ""
        for step in steps:
            edit_payload = step.get("edit_payload") if isinstance(step.get("edit_payload"), dict) else {}
            target = text_value(
                step.get("target_path")
                or step.get("path")
                or step.get("file_path")
                or edit_payload.get("target_path")
            ).replace("\\", "/")
            if target == path:
                reason = text_value(step.get("reason") or step.get("repair_reason") or step.get("description"))
                break
        reasons.append({"path": path, "reason": reason or goal or "controlled code fix"})
    return reasons


def collect_verification(
    results: list[dict[str, Any]],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    commands: list[str] = []
    summaries: list[str] = []

    for step in steps:
        step_type = text_value(step.get("type")).lower()
        if step_type == "command":
            command = text_value(step.get("command"))
            if command and command not in commands:
                commands.append(command)
        elif step_type in {"verify", "verify_file", "verify_python_syntax", "python_syntax_check"}:
            target = text_value(step.get("path") or step.get("target_path") or step.get("file_path"))
            command = f"{step_type} {target}".strip()
            if command and command not in commands:
                commands.append(command)
        elif step.get("verify_python_syntax"):
            target = text_value(step.get("target_path") or step.get("path"))
            command = f"verify_python_syntax {target}".strip()
            if command and command not in commands:
                commands.append(command)

    def visit(payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        message = text_value(payload.get("message") or payload.get("final_answer"))
        if message and message not in summaries:
            summaries.append(message)
        result = payload.get("result")
        if isinstance(result, dict):
            stdout = text_value(result.get("stdout"))
            stderr = text_value(result.get("stderr"))
            returncode = result.get("returncode")
            if stdout:
                summaries.append(stdout[:400])
            if stderr:
                summaries.append(stderr[:400])
            if returncode is not None:
                summaries.append(f"returncode={returncode}")
            visit(result)
        verification = payload.get("verification")
        if isinstance(verification, dict):
            visit(verification)

    for item in results:
        visit(item)

    return {
        "verification_command": " && ".join(commands) if commands else "represented by controlled mutation verification metadata",
        "verification_output_summary": "; ".join(summaries[:6]) if summaries else "no verification output",
    }


def review_required(execution_result: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    if not bool(execution_result.get("ok")):
        return True
    for step in steps:
        if bool(step.get("review_required") or step.get("requires_review") or step.get("human_review_required")):
            return True
    for item in execution_result.get("results") or []:
        if not isinstance(item, dict):
            continue
        repo_impact = item.get("repo_impact")
        if isinstance(repo_impact, dict) and bool(repo_impact.get("requires_confirmation")):
            return True
    return False


def text_value(value: Any) -> str:
    return str(value or "").strip()


def _repo_root_from_agent(agent: Any) -> Path:
    extra = getattr(agent, "extra_kwargs", None)
    if isinstance(extra, dict):
        return Path(
            str(
                extra.get("repo_root")
                or extra.get("project_root")
                or extra.get("workspace_project_root")
                or "."
            )
        ).resolve()
    return Path(".").resolve()


def _execution_failure(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "summary": message,
        "message": message,
        "final_answer": message,
        "error": message,
        "results": [],
        "last_result": {},
        "execution_trace": [],
    }


def _make_response(
    *,
    agent: Any,
    ok: bool,
    context: dict[str, Any],
    route: dict[str, Any],
    planner_result: dict[str, Any],
    plan: dict[str, Any],
    execution: dict[str, Any],
    final_answer: str,
    error: str | None,
    review: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    execution_payload = copy.deepcopy(execution)
    execution_payload["execution_path"] = agent_execution_path()
    payload_extra = {
        "reviewable_result": copy.deepcopy(review),
        "code_chain_controlled_self_edit_bridge": True,
        "planner_runtime_dispatch": True,
        "execution_path": agent_execution_path(),
    }
    if extra:
        payload_extra.update(extra)
    maker = getattr(agent, "_make_agent_response", None)
    if callable(maker):
        return maker(
            ok=ok,
            mode="code_chain_controlled_self_edit_bridge",
            context=context,
            route=route,
            plan=plan,
            execution=execution_payload,
            final_answer=final_answer,
            error=error,
            extra=payload_extra,
        )
    return {
        "ok": ok,
        "mode": "code_chain_controlled_self_edit_bridge",
        "context": context,
        "route": route,
        "planner_result": copy.deepcopy(planner_result),
        "plan": plan,
        "execution": execution_payload,
        "final_answer": final_answer,
        "error": error,
        **payload_extra,
    }
