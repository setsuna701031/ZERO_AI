from __future__ import annotations

import copy
import json
from pathlib import Path

import cli.zero_autonomous_loop as cli


def _batch(path: Path, tasks: list[object] | None = None) -> dict:
    payload = {
        "schema": "zero.runtime.autonomous_task_batch.v1",
        "tasks": tasks if tasks is not None else [
            {"task_id": "one", "goal": "goal one", "metadata": {"source": "test"}},
            {"task_id": "two", "goal": "goal two"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_loads_valid_batch_without_modifying_source(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    payload = _batch(path)
    before = copy.deepcopy(payload)
    loaded = cli.load_task_batch(path)

    assert loaded["ok"] is True
    assert loaded["tasks"] == payload["tasks"]
    assert payload == before


def test_dry_run_and_controlled_forward_expected_arguments(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"task_id": "one", "goal": "unchanged goal"}])
    calls: list[dict] = []

    def runner(goal: str, **kwargs: object) -> dict:
        calls.append({"goal": goal, **kwargs})
        return {"ok": True}

    dry, dry_code = cli.run_autonomous_loop_cli(
        path, natural_task_runner=runner, result_path=tmp_path / "dry.json"
    )
    controlled, controlled_code = cli.run_autonomous_loop_cli(
        path, controlled=True, natural_task_runner=runner,
        target_root="target", workspace_root="intake",
        result_path=tmp_path / "controlled.json",
    )

    assert dry_code == controlled_code == 0
    assert dry["controlled"] is False
    assert controlled["controlled"] is True
    assert calls[0]["controlled"] is False
    assert calls[1] == {
        "goal": "unchanged goal", "controlled": True,
        "target_root": "target", "workspace_root": "intake",
    }


def test_tasks_run_in_order_and_identity_metadata_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    original = _batch(path)
    calls: list[str] = []
    result, code = cli.run_autonomous_loop_cli(
        path,
        natural_task_runner=lambda goal, **kwargs: calls.append(goal) or {"ok": True},
        result_path=tmp_path / "result.json",
    )
    iterations = result["loop_result"]["iteration_results"]

    assert code == 0
    assert calls == ["goal one", "goal two"]
    assert [item["task_id"] for item in iterations] == ["one", "two"]
    assert iterations[0]["metadata"] == {"source": "test"}
    assert [item["goal"] for item in iterations] == ["goal one", "goal two"]
    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert result["tasks_received"] == 2
    assert result["autonomous_task_creation"] is False
    assert result["requested_changes_modified"] is False
    assert result["runtime_loop_closed"] is True


def test_loop_configuration_is_forwarded(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path)
    captured: dict = {}

    class Loop:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def run(self, tasks: list[object]) -> dict:
            captured["tasks"] = copy.deepcopy(tasks)
            return {"loop_status": "completed", "runtime_loop_closed": True}

    result, code = cli.run_autonomous_loop_cli(
        path, max_iterations=1, stop_on_error=True,
        result_path=tmp_path / "result.json", loop_class=Loop,
    )

    assert code == 0
    assert captured["max_iterations"] == 1
    assert captured["stop_on_error"] is True
    assert len(captured["tasks"]) == 2
    assert result["max_iterations"] == 1


def test_missing_invalid_json_schema_and_goal_are_exit_two(tmp_path: Path) -> None:
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    invalid_schema = tmp_path / "schema.json"
    invalid_schema.write_text(json.dumps({"schema": "wrong", "tasks": []}), encoding="utf-8")
    empty_goal = tmp_path / "goal.json"
    _batch(empty_goal, [{"goal": "  "}])

    cases = [tmp_path / "missing.json", invalid_json, invalid_schema, empty_goal]
    for index, path in enumerate(cases):
        calls: list[str] = []
        result, code = cli.run_autonomous_loop_cli(
            path,
            natural_task_runner=lambda goal, **kwargs: calls.append(goal) or {"ok": True},
            result_path=tmp_path / f"result-{index}.json",
        )
        assert code == 2
        assert result["ok"] is False
        assert calls == []


def test_invalid_max_iterations_does_not_execute(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path)
    calls: list[str] = []
    result, code = cli.run_autonomous_loop_cli(
        path, max_iterations=0,
        natural_task_runner=lambda goal, **kwargs: calls.append(goal) or {"ok": True},
        result_path=tmp_path / "result.json",
    )

    assert code == 2
    assert result["denial_reason"] == "max_iterations_must_be_greater_than_zero"
    assert calls == []


def test_result_is_utf8_json_and_exit_one_for_noncompleted_loop(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": "失敗任務"}])
    result_path = tmp_path / "nested" / "result.json"
    result, code = cli.run_autonomous_loop_cli(
        path,
        natural_task_runner=lambda goal, **kwargs: {"ok": False, "denial_reason": "failed"},
        result_path=result_path,
    )
    saved = json.loads(result_path.read_text(encoding="utf-8"))

    assert code == 1
    assert result["loop_result"]["loop_status"] == "completed_with_failures"
    assert saved == result


def test_main_accepts_both_command_forms(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [])
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    assert cli.main([str(path), "--result-path", str(first)]) == 0
    assert cli.main(["run", str(path), "--result-path", str(second)]) == 0
    assert first.exists() and second.exists()


def test_observe_workspace_flag_injects_observer_and_summarizes(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"task_id": "one", "goal": "observe goal"}])

    class Observer:
        def __init__(self, workspace_root: str) -> None:
            assert workspace_root == str(tmp_path)

        def observe(self, **kwargs: object) -> dict:
            return {
                "observer_status": "observed_with_issues",
                "observation_complete": True,
                "issues": ["missing:file.txt"],
            }

    result, code = cli.run_autonomous_loop_cli(
        path,
        target_root=str(tmp_path),
        observe_workspace=True,
        observer_factory=Observer,
        natural_task_runner=lambda goal, **kwargs: {
            "ok": True, "changed_files": ["file.txt"]
        },
        result_path=tmp_path / "result.json",
    )

    assert code == 0
    assert result["workspace_observer_enabled"] is True
    assert result["observed_iterations"] == 1
    assert result["observation_issue_count"] == 1
    assert result["loop_result"]["iteration_results"][0]["workspace_observation"]


def test_observer_issue_does_not_change_cli_exit_code(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": "observe goal"}])
    result, code = cli.run_autonomous_loop_cli(
        path,
        target_root=str(tmp_path),
        observe_workspace=True,
        natural_task_runner=lambda goal, **kwargs: {
            "ok": True, "changed_files": ["missing.txt"]
        },
        result_path=tmp_path / "result.json",
    )

    assert code == 0
    assert result["observation_issue_count"] == 1


def test_advise_repair_flag_enables_advisor_with_or_without_observer(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": "advice goal"}])
    without_observation, code = cli.run_autonomous_loop_cli(
        path,
        advise_repair=True,
        natural_task_runner=lambda goal, **kwargs: {"ok": True},
        result_path=tmp_path / "without.json",
    )
    with_observation, observed_code = cli.run_autonomous_loop_cli(
        path,
        target_root=str(tmp_path),
        advise_repair=True,
        observe_workspace=True,
        natural_task_runner=lambda goal, **kwargs: {
            "ok": False, "validation_passed": False
        },
        result_path=tmp_path / "with.json",
    )

    first_advice = without_observation["loop_result"]["iteration_results"][0]["repair_advice"]
    second_advice = with_observation["loop_result"]["iteration_results"][0]["repair_advice"]
    assert code == 0
    assert observed_code == 1
    assert without_observation["repair_advisor_enabled"] is True
    assert first_advice["advisor_status"] == "insufficient_evidence"
    assert second_advice["failure_category"] == "validation_failure"
    assert with_observation["repair_advised_iterations"] == 1
    assert json.loads((tmp_path / "with.json").read_text(encoding="utf-8")) == with_observation


def test_repair_advisor_disabled_by_default_and_issue_does_not_change_exit(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": "advice goal"}])

    class Advisor:
        def advise(self, **kwargs: object) -> dict:
            return {
                "advisor_status": "manual_review_required",
                "repair_needed": True,
            }

    disabled, disabled_code = cli.run_autonomous_loop_cli(
        path,
        natural_task_runner=lambda goal, **kwargs: {"ok": True},
        result_path=tmp_path / "disabled.json",
    )
    enabled, enabled_code = cli.run_autonomous_loop_cli(
        path, advise_repair=True, repair_advisor_factory=Advisor,
        natural_task_runner=lambda goal, **kwargs: {"ok": True},
        result_path=tmp_path / "enabled.json",
    )

    assert disabled_code == enabled_code == 0
    assert disabled["repair_advisor_enabled"] is False
    assert enabled["manual_review_required_count"] == 1


def test_bounded_retry_cli_retries_and_saves_result(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"task_id": "one", "goal": "same goal"}])
    calls: list[str] = []

    def runner(goal: str, **kwargs: object) -> dict:
        calls.append(goal)
        if len(calls) == 1:
            return {"ok": False, "validation_passed": False}
        return {"ok": True, "validation_passed": True}

    result_path = tmp_path / "result.json"
    result, code = cli.run_autonomous_loop_cli(
        path,
        bounded_retry=True,
        repair_max_attempts=2,
        natural_task_runner=runner,
        result_path=result_path,
    )
    saved = json.loads(result_path.read_text(encoding="utf-8"))

    assert code == 0
    assert calls == ["same goal", "same goal"]
    assert result["bounded_retry_enabled"] is True
    assert result["repair_advisor_enabled"] is True
    assert result["repair_max_attempts"] == 2
    assert result["retried_tasks"] == 1
    assert result["retry_attempt_count"] == 1
    assert result["loop_result"]["tasks_received"] == 1
    assert saved == result


def test_invalid_repair_max_attempts_is_exit_two_without_execution(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": "goal"}])
    calls: list[str] = []
    result, code = cli.run_autonomous_loop_cli(
        path,
        bounded_retry=True,
        repair_max_attempts=0,
        natural_task_runner=lambda goal, **kwargs: calls.append(goal) or {"ok": True},
        result_path=tmp_path / "result.json",
    )

    assert code == 2
    assert calls == []
    assert result["denial_reason"] == "repair_max_attempts_must_be_greater_than_zero"


def test_bounded_retry_disabled_keeps_old_single_run_behavior(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": "goal"}])
    calls: list[str] = []
    result, code = cli.run_autonomous_loop_cli(
        path,
        natural_task_runner=lambda goal, **kwargs: calls.append(goal) or {"ok": True},
        result_path=tmp_path / "result.json",
    )
    assert code == 0
    assert calls == ["goal"]
    assert result["bounded_retry_enabled"] is False
    assert result["retried_tasks"] == 0


def test_propose_changes_cli_enables_advisor_and_saves_proposal(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"task_id": "one", "goal": "proposal goal"}])
    result_path = tmp_path / "proposal.json"
    result, code = cli.run_autonomous_loop_cli(
        path,
        propose_changes=True,
        natural_task_runner=lambda goal, **kwargs: {
            "ok": False, "validation_passed": False,
            "changed_files": ["workspace/a.txt"],
        },
        result_path=result_path,
    )

    iteration = result["loop_result"]["iteration_results"][0]
    assert code == 1
    assert result["change_proposal_engine_enabled"] is True
    assert result["repair_advisor_enabled"] is True
    assert result["proposed_change_iterations"] == 1
    assert result["manual_approval_required_count"] == 1
    assert iteration["change_proposal"]["proposal_status"] == "proposal_created"
    assert iteration["change_proposal"]["autonomous_apply_allowed"] is False
    assert json.loads(result_path.read_text(encoding="utf-8")) == result


def test_proposal_disabled_by_default_and_issue_does_not_change_exit(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": "proposal goal"}])

    class BlockedEngine:
        def propose(self, **kwargs: object) -> dict:
            return {
                "proposal_status": "proposal_blocked_by_safety",
                "approval_status": "pending",
            }

    disabled, disabled_code = cli.run_autonomous_loop_cli(
        path,
        natural_task_runner=lambda goal, **kwargs: {"ok": True},
        result_path=tmp_path / "disabled.json",
    )
    enabled, enabled_code = cli.run_autonomous_loop_cli(
        path, propose_changes=True,
        change_proposal_engine_factory=BlockedEngine,
        natural_task_runner=lambda goal, **kwargs: {"ok": True},
        result_path=tmp_path / "enabled.json",
    )

    assert disabled_code == enabled_code == 0
    assert disabled["change_proposal_engine_enabled"] is False
    assert enabled["blocked_proposal_count"] == 1


def test_proposal_coexists_with_observer_advisor_and_bounded_retry(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": "combined goal"}])
    calls: list[str] = []

    def runner(goal: str, **kwargs: object) -> dict:
        calls.append(goal)
        return (
            {"ok": False, "validation_passed": False, "changed_files": ["a.txt"]}
            if len(calls) == 1 else
            {"ok": True, "validation_passed": True, "changed_files": ["a.txt"]}
        )

    result, code = cli.run_autonomous_loop_cli(
        path,
        target_root=str(tmp_path),
        observe_workspace=True,
        advise_repair=True,
        bounded_retry=True,
        propose_changes=True,
        natural_task_runner=runner,
        result_path=tmp_path / "combined.json",
    )

    assert code == 0
    assert calls == ["combined goal", "combined goal"]
    assert result["bounded_retry_enabled"] is True
    assert result["change_proposal_engine_enabled"] is True


def test_autonomous_cli_reports_pending_approval_without_approve_flag(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": "proposal goal"}])
    result, code = cli.run_autonomous_loop_cli(
        path,
        propose_changes=True,
        natural_task_runner=lambda goal, **kwargs: {
            "ok": False, "validation_passed": False,
            "changed_files": ["workspace/a.txt"],
        },
        result_path=tmp_path / "result.json",
    )
    parser_options = cli.build_parser()._option_string_actions

    assert code == 1
    assert result["operator_approval_required_count"] == 1
    assert result["pending_approval_count"] == 1
    assert result["execution_plan_required_count"] == 1
    assert result["execution_plan_not_built_count"] == 1
    assert "--approve" not in parser_options
    assert "--build-plan" not in parser_options
    iteration = result["loop_result"]["iteration_results"][0]
    assert iteration["operator_approval"] is None
    assert iteration["execution_plan_status"] == "not_built"


def test_autonomous_cli_projects_review_statistics_without_review_flags(tmp_path: Path) -> None:
    from core.runtime.runtime_execution_plan_review_gate import review_execution_plan
    from tests.test_runtime_execution_plan_review_gate import NOW, plan, review

    execution_plan = plan()
    approved = review_execution_plan(execution_plan, review(execution_plan), now=NOW)
    rejected = review_execution_plan(execution_plan, review(execution_plan, "rejected"), now=NOW)
    path = tmp_path / "tasks.json"
    _batch(path, [
        {"goal": "pending", "metadata": {"execution_plan": execution_plan}},
        {"goal": "approved", "metadata": {"execution_plan": execution_plan,
            "execution_plan_review_result": approved}},
        {"goal": "rejected", "metadata": {"execution_plan": execution_plan,
            "execution_plan_review_result": rejected}},
    ])
    result, code = cli.run_autonomous_loop_cli(
        path, controlled=True, natural_task_runner=lambda goal, **kwargs: {"ok": True},
        result_path=tmp_path / "result.json")
    options = cli.build_parser()._option_string_actions

    assert code == 0
    assert result["review_pending_count"] == 1
    assert result["review_approved_count"] == 1
    assert result["review_rejected_count"] == 1
    assert result["executor_admission_ready_count"] == 1
    assert not {"--auto-review", "--review-plan", "--executor", "--apply", "--patch", "--mutate"} & set(options)


def test_autonomous_cli_projects_controlled_execution_statistics(tmp_path: Path) -> None:
    from core.runtime.runtime_execution_plan_review_gate import review_execution_plan
    from tests.test_runtime_execution_plan_review_gate import NOW, plan, review

    execution_plan = plan(); approved = review_execution_plan(execution_plan, review(execution_plan), now=NOW)
    common = {"execution_plan": execution_plan, "execution_plan_review_result": approved,
              "operator_execution_request": {"request_id": "r"}}
    path = tmp_path / "tasks.json"
    _batch(path, [
        {"goal": "ready", "metadata": common},
        {"goal": "done", "metadata": {**common, "controlled_execution_result": {
            "contract": "zero.runtime.controlled_execution_activation.v1",
            "activation_status": "completed", "token": {"token_status": "issued"}}}},
        {"goal": "blocked", "metadata": {**common, "controlled_execution_result": {
            "contract": "zero.runtime.controlled_execution_activation.v1",
            "activation_status": "blocked", "token": {"token_status": "denied"}}}},
    ])
    result, code = cli.run_autonomous_loop_cli(
        path, controlled=True, natural_task_runner=lambda goal, **kwargs: {"ok": True},
        result_path=tmp_path / "result.json")
    options = set(cli.build_parser()._option_string_actions)
    assert code == 0
    assert result["controlled_execution_ready_for_dry_run_count"] == 1
    assert result["controlled_execution_completed_count"] == 1
    assert result["controlled_execution_blocked_count"] == 1
    assert result["executor_token_issued_count"] == 1
    assert result["executor_token_denied_count"] == 1
    assert not {"--auto-run", "--apply", "--mutate", "--commit"} & options


def test_autonomous_cli_projects_active_authorization_statistics(tmp_path: Path) -> None:
    activation = {"contract": "zero.runtime.controlled_execution_activation.v1",
                  "activation_status": "completed", "token": {"token_status": "issued"}}
    def metadata(status=None):
        value = {"controlled_execution_result": activation}
        if status: value["active_authorization_result"] = {
            "contract": "zero.runtime.active_execution_authorization.v1",
            "authorization_status": status, "authorization_valid": status != "invalid",
            "active_execution_prepared": status == "authorized"}
        return value
    path = tmp_path / "tasks.json"; _batch(path, [
        {"goal": "required", "metadata": metadata()}, {"goal": "authorized", "metadata": metadata("authorized")},
        {"goal": "rejected", "metadata": metadata("rejected")}, {"goal": "invalid", "metadata": metadata("invalid")}])
    result, code = cli.run_autonomous_loop_cli(path, controlled=True,
        natural_task_runner=lambda goal, **kwargs: {"ok": True}, result_path=tmp_path / "result.json")
    assert code == 0
    assert result["active_authorization_operator_required_count"] == 1
    assert result["active_authorization_authorized_count"] == 1
    assert result["active_authorization_rejected_count"] == 1
    assert result["active_authorization_invalid_count"] == 1
    assert not {"--auto-authorize", "--active-run", "--execute", "--apply", "--mutate", "--commit"} & set(cli.build_parser()._option_string_actions)


def test_autonomous_cli_projects_transactional_statistics_without_execute_flag(tmp_path: Path) -> None:
    def metadata(status):
        return {"transactional_execution_result": {
            "transaction_status": status, "transaction_committed": status == "committed",
            "validation_executed": status in {"committed", "rolled_back"},
            "validation_passed": status == "committed", "rollback_executed": status == "rolled_back",
            "rollback_verified": status == "rolled_back", "git_commit_performed": False}}
    path = tmp_path / "tasks.json"
    _batch(path, [{"goal": status, "metadata": metadata(status)}
                  for status in ("committed", "rolled_back", "blocked", "rollback_failed")])
    result, code = cli.run_autonomous_loop_cli(path, controlled=True,
        natural_task_runner=lambda goal, **kwargs: {"ok": True}, result_path=tmp_path / "result.json")
    assert code == 0
    assert result["transactional_execution_committed_count"] == 1
    assert result["transactional_execution_rolled_back_count"] == 1
    assert result["transactional_execution_blocked_count"] == 1
    assert result["transactional_execution_critical_failure_count"] == 1
    assert "--auto-execute" not in cli.build_parser()._option_string_actions
