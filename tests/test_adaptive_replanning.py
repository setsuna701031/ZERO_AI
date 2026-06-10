from core.adaptive import AdaptiveAction, AdaptiveReplanner, DeviationReport


def _report(reason: str, recoverable: bool = True) -> DeviationReport:
    return DeviationReport("task", "failed-step", {}, {}, True, reason, "high", recoverable)


def test_artifact_missing_produces_replan_decision() -> None:
    decision = AdaptiveReplanner().decide(_report("artifact_missing"), step={"id": "failed-step"})

    assert decision.action is AdaptiveAction.REPLAN
    assert decision.resume_from_step_id == "failed-step"


def test_transient_failure_retry_is_bounded() -> None:
    replanner = AdaptiveReplanner(max_retries=2)

    assert replanner.decide(_report("transient_error"), step={}, retry_count=0).action is AdaptiveAction.RETRY
    assert replanner.decide(_report("transient_error"), step={}, retry_count=1).action is AdaptiveAction.RETRY
    exhausted = replanner.decide(_report("transient_error"), step={}, retry_count=2)
    assert exhausted.action is AdaptiveAction.BLOCK
    assert exhausted.reason == "retry_limit_exhausted"


def test_contract_violation_blocks_without_replan() -> None:
    decision = AdaptiveReplanner().decide(_report("contract_violation", False), step={})

    assert decision.action is AdaptiveAction.BLOCK
    assert decision.requires_user_review is True
