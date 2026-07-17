from __future__ import annotations

import copy

from core.runtime.runtime_autonomous_loop import RuntimeAutonomousLoop


def _success(goal: str) -> dict:
    return {"ok": True, "changed_files": [f"{goal}.txt"]}


def test_empty_queue_and_invalid_configuration_close_safely() -> None:
    empty = RuntimeAutonomousLoop(_success).run([])
    invalid = RuntimeAutonomousLoop(_success, max_iterations=0).run(["one"])

    assert empty["loop_status"] == "empty_queue"
    assert empty["runtime_loop_closed"] is True
    assert invalid["loop_status"] == "denied_invalid_configuration"
    assert invalid["iterations_completed"] == 0


def test_single_success_is_controlled_and_deterministic() -> None:
    first = RuntimeAutonomousLoop(_success).run_once("one")
    second = RuntimeAutonomousLoop(_success).run_once("one")

    assert first["loop_status"] == "completed"
    assert first["completed_count"] == 1
    assert first["controlled"] is True
    assert first["autonomous_task_creation"] is False
    assert first["goal_mutation_allowed"] is False
    assert first["iteration_results"][0]["task_reference"] == (
        second["iteration_results"][0]["task_reference"]
    )


def test_run_accepts_single_string_without_splitting_it() -> None:
    calls: list[str] = []
    result = RuntimeAutonomousLoop(
        lambda goal: calls.append(goal) or {"ok": True}
    ).run("whole goal")

    assert calls == ["whole goal"]
    assert result["tasks_received"] == 1


def test_multiple_tasks_run_in_order_without_mutating_inputs() -> None:
    calls: list[str] = []
    tasks = ["one", {"task_id": "two-id", "goal": "two", "metadata": {"x": 1}}]
    before = copy.deepcopy(tasks)

    result = RuntimeAutonomousLoop(
        lambda goal: calls.append(goal) or {"ok": True}
    ).run(tasks)

    assert calls == ["one", "two"]
    assert tasks == before
    assert [item["goal"] for item in result["iteration_results"]] == ["one", "two"]
    assert result["tasks_received"] == 2
    assert result["iterations_completed"] == 2
    assert result["tasks_remaining"] == 0


def test_mixed_results_and_iteration_limit() -> None:
    mixed = RuntimeAutonomousLoop(
        lambda goal: {"ok": goal != "bad", "denial_reason": "failed" if goal == "bad" else ""}
    ).run(["good", "bad"])
    limited = RuntimeAutonomousLoop(_success, max_iterations=2).run(["a", "b", "c"])

    assert mixed["loop_status"] == "completed_with_failures"
    assert mixed["completed_count"] == 1
    assert mixed["failed_count"] == 1
    assert limited["loop_status"] == "iteration_limit_reached"
    assert limited["iterations_completed"] == 2
    assert limited["tasks_remaining"] == 1


def test_runner_exception_stop_on_error_false_continues() -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        if goal == "bad":
            raise ValueError("boom")
        return {"ok": True}

    result = RuntimeAutonomousLoop(runner, stop_on_error=False).run(["bad", "good"])

    assert calls == ["bad", "good"]
    assert result["loop_status"] == "completed_with_failures"
    assert result["iteration_results"][0]["error_type"] == "ValueError"
    assert result["iterations_completed"] == 2


def test_runner_exception_stop_on_error_true_stops() -> None:
    def runner(goal: str) -> dict:
        raise RuntimeError("boom")

    result = RuntimeAutonomousLoop(runner, stop_on_error=True).run(["bad", "never"])

    assert result["loop_status"] == "runner_error"
    assert result["iterations_completed"] == 1
    assert result["tasks_remaining"] == 1
    assert result["iteration_results"][0]["loop_continues"] is False


def test_advisor_metadata_is_retained_as_read_only() -> None:
    metadata = {
        "memory_context": {"memory_status": "loaded"},
        "decision_advice": {"recommended_paths": ["a.txt"]},
        "planner_advisor_bridge": {"preferred_paths": ["a.txt"]},
    }
    task = {"goal": "keep goal", "metadata": metadata}
    before = copy.deepcopy(task)

    result = RuntimeAutonomousLoop(_success).run([task])
    advisory = result["iteration_results"][0]["advisory_metadata"]

    assert task == before
    assert result["iteration_results"][0]["goal"] == "keep goal"
    assert advisory["memory_context"] == metadata["memory_context"]
    assert advisory["decision_advice"] == metadata["decision_advice"]
    assert advisory["planner_advisor_bridge"] == metadata["planner_advisor_bridge"]
    assert advisory["read_only"] is True
    assert advisory["decision_authority"] is False
    assert advisory["requested_changes_modified"] is False


def test_activity_log_compatible_append_contract() -> None:
    class Activity:
        def __init__(self) -> None:
            self.goals: list[str] = []

        def append(self, **kwargs: object) -> dict:
            self.goals.append(str(kwargs["goal"]))
            return {"ok": True, "activity_status": "recorded"}

    activity = Activity()
    result = RuntimeAutonomousLoop(_success, activity).run(["one"])

    assert activity.goals == ["one"]
    assert result["iteration_results"][0]["activity_recorded"] is True
    assert result["runtime_loop_closed"] is True


def test_observer_receives_runner_data_and_is_injected() -> None:
    calls: list[dict] = []

    def observer(**kwargs: object) -> dict:
        calls.append(copy.deepcopy(kwargs))
        return {
            "observer_status": "observed",
            "observation_complete": True,
            "issues": [],
        }

    result = RuntimeAutonomousLoop(
        lambda goal: {"ok": True, "changed_files": ["a.txt"]},
        observer=observer,
    ).run([{"task_id": "one", "goal": "keep goal"}])
    iteration = result["iteration_results"][0]

    assert calls[0]["goal"] == "keep goal"
    assert calls[0]["task_id"] == "one"
    assert calls[0]["changed_files"] == ["a.txt"]
    assert calls[0]["runner_result"]["ok"] is True
    assert iteration["workspace_observed"] is True
    assert iteration["observation_status"] == "observed"


def test_observer_none_and_exception_do_not_change_task_result() -> None:
    disabled = RuntimeAutonomousLoop(_success).run(["one"])

    def broken(**kwargs: object) -> dict:
        raise RuntimeError("observer failed")

    failed_observer = RuntimeAutonomousLoop(_success, observer=broken).run(["one"])

    assert disabled["loop_status"] == "completed"
    assert disabled["iteration_results"][0]["observation_status"] == "disabled"
    assert failed_observer["loop_status"] == "completed"
    assert failed_observer["iteration_results"][0]["task_completed"] is True
    assert failed_observer["iteration_results"][0]["observation_status"] == "observer_error"


def test_repair_advisor_receives_sources_and_is_injected() -> None:
    calls: list[dict] = []

    def advisor(**kwargs: object) -> dict:
        calls.append(copy.deepcopy(kwargs))
        return {
            "advisor_status": "repair_advised",
            "repair_needed": True,
        }

    task = {
        "task_id": "one", "goal": "keep goal",
        "metadata": {
            "memory_context": {"experience_count": 1},
            "decision_advice": {"risk_flags": ["x"]},
            "planner_advisor_bridge": {"avoid_risk_flags": ["x"]},
        },
    }
    before = copy.deepcopy(task)
    result = RuntimeAutonomousLoop(
        lambda goal: {"ok": False, "validation_passed": False},
        observer=lambda **kwargs: {
            "observer_status": "observed", "observation_complete": True,
        },
        repair_advisor=advisor,
    ).run([task])
    iteration = result["iteration_results"][0]

    assert task == before
    assert calls[0]["goal"] == "keep goal"
    assert calls[0]["task_id"] == "one"
    assert calls[0]["runner_result"]["validation_passed"] is False
    assert calls[0]["workspace_observation"]["observer_status"] == "observed"
    assert calls[0]["memory_context"] == {"experience_count": 1}
    assert iteration["repair_advised"] is True
    assert iteration["repair_advisor_status"] == "repair_advised"


def test_repair_advisor_none_and_exception_do_not_change_loop_outcome() -> None:
    baseline = RuntimeAutonomousLoop(_success).run(["one"])

    def broken(**kwargs: object) -> dict:
        raise ValueError("advisor failed")

    advised = RuntimeAutonomousLoop(_success, repair_advisor=broken).run(["one"])

    assert baseline["iteration_results"][0]["repair_advisor_status"] == "disabled"
    assert advised["loop_status"] == baseline["loop_status"] == "completed"
    assert advised["iteration_results"][0]["runner_ok"] is True
    assert advised["iteration_results"][0]["task_completed"] is True
    assert advised["iteration_results"][0]["repair_advisor_status"] == "advisor_error"


def test_repair_advisor_reads_natural_task_package_metadata() -> None:
    captured: dict = {}

    def advisor(**kwargs: object) -> dict:
        captured.update(kwargs)
        return {"advisor_status": "repair_not_needed", "repair_needed": False}

    result = RuntimeAutonomousLoop(
        lambda goal: {
            "ok": True,
            "validation_passed": True,
            "package": {"metadata": {
                "memory_context": {"experience_count": 3},
                "decision_advice": {"risk_flags": ["validation_failure_risk"]},
                "planner_advisor_bridge": {"avoid_risk_flags": ["validation_failure_risk"]},
            }},
        },
        repair_advisor=advisor,
    ).run(["one"])

    assert result["loop_status"] == "completed"
    assert captured["memory_context"] == {"experience_count": 3}
    assert captured["decision_advice"]["risk_flags"] == ["validation_failure_risk"]
    assert captured["planner_advisor_bridge"]["avoid_risk_flags"] == ["validation_failure_risk"]


def test_bounded_retry_is_optional_and_does_not_expand_queue() -> None:
    from core.runtime.runtime_bounded_repair_retry_loop import (
        RuntimeBoundedRepairRetryLoop,
    )
    from core.runtime.runtime_repair_advisor import RuntimeRepairAdvisor

    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        if len(calls) == 1:
            return {"ok": False, "validation_passed": False}
        return {"ok": True, "validation_passed": True}

    bounded = RuntimeBoundedRepairRetryLoop(
        task_runner=runner,
        repair_advisor=RuntimeRepairAdvisor(),
        max_attempts=2,
        allow_bounded_retry=True,
    )
    task = {"task_id": "one", "goal": "same goal", "metadata": {"x": 1}}
    before = copy.deepcopy(task)
    result = RuntimeAutonomousLoop(
        task_runner=runner,
        bounded_repair_retry_loop=bounded,
    ).run([task])
    iteration = result["iteration_results"][0]

    assert task == before
    assert calls == ["same goal", "same goal"]
    assert result["tasks_received"] == 1
    assert result["iterations_completed"] == 1
    assert result["loop_status"] == "completed"
    assert iteration["runner_ok"] is True
    assert iteration["task_completed"] is True
    assert iteration["bounded_retry_result"]["retry_count"] == 1


def test_bounded_retry_disabled_preserves_single_execution() -> None:
    calls: list[str] = []
    result = RuntimeAutonomousLoop(
        lambda goal: calls.append(goal) or {"ok": False, "validation_passed": False}
    ).run(["goal"])
    assert calls == ["goal"]
    assert result["iteration_results"][0]["bounded_retry_result"] == {}


def test_change_proposal_engine_receives_sources_and_is_injected() -> None:
    captured: dict = {}

    def engine(**kwargs: object) -> dict:
        captured.update(copy.deepcopy(kwargs))
        return {
            "proposal_status": "proposal_created",
            "approval_status": "pending",
        }

    task = {
        "task_id": "one", "goal": "keep goal",
        "metadata": {"memory_context": {"experience_count": 1}},
    }
    before = copy.deepcopy(task)
    result = RuntimeAutonomousLoop(
        lambda goal: {"ok": False, "validation_passed": False},
        observer=lambda **kwargs: {
            "observer_status": "observed", "observation_complete": True,
        },
        repair_advisor=lambda **kwargs: {
            "advisor_status": "repair_advised", "repair_needed": True,
            "failure_category": "validation_failure",
        },
        change_proposal_engine=engine,
    ).run([task])
    iteration = result["iteration_results"][0]

    assert task == before
    assert captured["goal"] == "keep goal"
    assert captured["task_id"] == "one"
    assert captured["runner_result"]["validation_passed"] is False
    assert captured["workspace_observation"]["observer_status"] == "observed"
    assert captured["repair_advice"]["repair_needed"] is True
    assert captured["memory_context"] == {"experience_count": 1}
    assert iteration["change_proposed"] is True
    assert iteration["change_proposal_status"] == "proposal_created"


def test_change_proposal_disabled_and_error_do_not_change_outcome() -> None:
    baseline = RuntimeAutonomousLoop(_success).run(["one"])

    def broken(**kwargs: object) -> dict:
        raise RuntimeError("proposal")

    proposed = RuntimeAutonomousLoop(
        _success, change_proposal_engine=broken
    ).run(["one"])

    assert baseline["iteration_results"][0]["change_proposal_status"] == "disabled"
    assert proposed["loop_status"] == baseline["loop_status"] == "completed"
    assert proposed["iteration_results"][0]["runner_ok"] is True
    assert proposed["iteration_results"][0]["task_completed"] is True
    assert proposed["iteration_results"][0]["change_proposal_status"] == "proposal_error"


def test_change_proposal_is_pending_and_never_auto_approved() -> None:
    gate_calls: list[object] = []

    class Gate:
        def review(self, **kwargs: object) -> dict:
            gate_calls.append(kwargs)
            return {"approval_status": "approved"}

    result = RuntimeAutonomousLoop(
        _success,
        change_proposal_engine=lambda **kwargs: {
            "proposal_status": "proposal_created",
            "requires_operator_approval": True,
            "approval_status": "pending",
        },
        approval_gate=Gate(),
    ).run(["one"])
    iteration = result["iteration_results"][0]

    assert gate_calls == []
    assert iteration["approval_required"] is True
    assert iteration["approval_status"] == "pending"
    assert iteration["operator_approval"] is None
    assert iteration["apply_admission_required"] is True
    assert iteration["apply_admission_status"] == "not_evaluated"
    assert iteration["execution_plan_required"] is True
    assert iteration["execution_plan_status"] == "not_built"
    assert result["loop_status"] == "completed"


def test_execution_plan_review_is_projected_without_building_or_execution() -> None:
    from core.runtime.runtime_execution_plan_review_gate import review_execution_plan
    from tests.test_runtime_execution_plan_review_gate import NOW, plan, review

    execution_plan = plan()
    approved = review_execution_plan(execution_plan, review(execution_plan), now=NOW)
    rejected = review_execution_plan(execution_plan, review(execution_plan, "rejected"), now=NOW)
    tasks = [
        {"goal": "pending", "metadata": {"execution_plan": execution_plan}},
        {"goal": "approved", "metadata": {"execution_plan": execution_plan,
            "execution_plan_review_result": approved}},
        {"goal": "rejected", "metadata": {"execution_plan": execution_plan,
            "execution_plan_review_result": rejected}},
    ]
    before = copy.deepcopy(tasks)
    result = RuntimeAutonomousLoop(_success).run(tasks)
    projected = result["iteration_results"]

    assert tasks == before
    assert [item["review_status"] for item in projected] == ["pending", "approved", "rejected"]
    assert [item["executor_admission_ready"] for item in projected] == [False, True, False]
    assert all(item["execution_allowed"] is False for item in projected)
    assert all(item["execution_plan_status"] == "built" for item in projected)


def test_controlled_execution_states_are_read_only_projections() -> None:
    from core.runtime.runtime_execution_plan_review_gate import review_execution_plan
    from tests.test_runtime_execution_plan_review_gate import NOW, plan, review

    execution_plan = plan()
    approved = review_execution_plan(execution_plan, review(execution_plan), now=NOW)
    request = {"contract": "zero.runtime.operator_execution_request.v1", "request_id": "r"}
    completed = {"contract": "zero.runtime.controlled_execution_activation.v1",
                 "activation_status": "completed", "token": {"token_status": "issued"}}
    blocked = {"contract": "zero.runtime.controlled_execution_activation.v1",
               "activation_status": "blocked", "token": {"token_status": "denied"}}
    tasks = [
        {"goal": "request", "metadata": {"execution_plan": execution_plan,
            "execution_plan_review_result": approved}},
        {"goal": "ready", "metadata": {"execution_plan": execution_plan,
            "execution_plan_review_result": approved, "operator_execution_request": request}},
        {"goal": "done", "metadata": {"execution_plan": execution_plan,
            "execution_plan_review_result": approved, "operator_execution_request": request,
            "controlled_execution_result": completed}},
        {"goal": "blocked", "metadata": {"execution_plan": execution_plan,
            "execution_plan_review_result": approved, "operator_execution_request": request,
            "controlled_execution_result": blocked}},
    ]
    before = copy.deepcopy(tasks)
    items = RuntimeAutonomousLoop(_success).run(tasks)["iteration_results"]
    assert tasks == before
    assert [x["controlled_execution_status"] for x in items] == [
        "operator_request_required", "ready_for_dry_run", "completed", "blocked"]
    assert [x["executor_token_status"] for x in items] == [
        "not_issued", "not_issued", "issued", "denied"]
    assert all(x["active_execution_ready"] is False and x["execution_allowed"] is False for x in items)


def test_active_authorization_states_are_read_only_projections() -> None:
    activation = {"contract": "zero.runtime.controlled_execution_activation.v1",
                  "activation_status": "completed", "token": {"token_status": "issued"}}
    request = {"authorization_id": "a"}
    def result(status, prepared=False): return {
        "contract": "zero.runtime.active_execution_authorization.v1",
        "authorization_status": status, "authorization_valid": status != "invalid",
        "active_execution_prepared": prepared}
    base = {"controlled_execution_result": activation}
    tasks = [{"goal": "required", "metadata": base},
             {"goal": "pending", "metadata": {**base, "active_authorization": request}},
             {"goal": "authorized", "metadata": {**base, "active_authorization": request,
                "active_authorization_result": result("authorized", True)}},
             {"goal": "rejected", "metadata": {**base, "active_authorization_result": result("rejected")}},
             {"goal": "invalid", "metadata": {**base, "active_authorization_result": result("invalid")}}]
    before = copy.deepcopy(tasks); items = RuntimeAutonomousLoop(_success).run(tasks)["iteration_results"]
    assert tasks == before
    assert [x["active_authorization_status"] for x in items] == [
        "operator_authorization_required", "pending", "authorized", "rejected", "invalid"]
    assert [x["active_execution_prepared"] for x in items] == [False, False, True, False, False]
    assert all(x["active_execution_ready"] is False and x["execution_allowed"] is False for x in items)


def test_transactional_execution_states_are_read_only_projections() -> None:
    prepared = {"contract": "zero.runtime.active_execution_authorization.v1",
        "authorization_status": "authorized", "authorization_valid": True,
        "active_execution_prepared": True}
    invocation = {"invocation_request_id": "i"}
    bundle = {"candidate_bundle_id": "b", "files": [{"relative_path": "a.txt"}]}
    def transaction(status):
        return {"transaction_status": status, "transaction_committed": status == "committed",
            "validation_executed": status in {"committed", "rolled_back"},
            "validation_passed": status == "committed", "rollback_executed": status == "rolled_back",
            "rollback_verified": True if status == "rolled_back" else None,
            "git_commit_performed": False}
    tasks = [
        {"goal": "invocation", "metadata": {"active_authorization_result": prepared}},
        {"goal": "bundle", "metadata": {"active_authorization_result": prepared,
            "active_executor_invocation_request": invocation}},
        {"goal": "ready", "metadata": {"active_authorization_result": prepared,
            "active_executor_invocation_request": invocation, "candidate_mutation_bundle": bundle}},
        *[{"goal": status, "metadata": {"transactional_execution_result": transaction(status)}}
          for status in ("committed", "rolled_back", "blocked", "rollback_failed")],
    ]
    before = copy.deepcopy(tasks)
    items = RuntimeAutonomousLoop(_success).run(tasks)["iteration_results"]
    assert tasks == before
    assert [item["transactional_execution_status"] for item in items] == [
        "operator_invocation_required", "candidate_bundle_required", "ready",
        "committed", "rolled_back", "blocked", "critical_failure"]
    assert items[3]["transaction_committed"] is True
    assert items[4]["rollback_executed"] is True and items[4]["rollback_verified"] is True
    assert all(item["git_commit_performed"] is False for item in items)
