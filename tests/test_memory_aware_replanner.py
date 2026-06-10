from core.adaptive import (
    AdaptiveAction,
    AdaptiveMemoryContextBuilder,
    AdaptiveReplanner,
    DeviationReport,
    MemoryAwareReplanner,
)


def _report(reason: str, recoverable: bool = True) -> DeviationReport:
    return DeviationReport("task-1", "step-1", {}, {}, True, reason, "high", recoverable)


class LegacyReplanner:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, report, *, step, retry_count=0, replan_count=0):
        self.calls += 1
        return AdaptiveReplanner().decide(
            report,
            step=step,
            retry_count=retry_count,
            replan_count=replan_count,
        )

    def revise(self, **kwargs):
        return AdaptiveReplanner().revise(**kwargs)


def test_no_repository_and_legacy_api_remain_operational() -> None:
    legacy = LegacyReplanner()
    wrapper = MemoryAwareReplanner(legacy)

    decision = wrapper.decide(_report("artifact_missing"), step={"id": "step-1"})

    assert decision.action is AdaptiveAction.REPLAN
    assert legacy.calls == 1
    assert wrapper.last_memory_context.related_issues == []


def test_memory_context_does_not_change_adaptive_decision() -> None:
    report = _report("transient_error")
    replanner = AdaptiveReplanner(max_retries=2)
    expected = replanner.decide(report, step={}, retry_count=0)
    context = AdaptiveMemoryContextBuilder().build(report)

    actual = replanner.decide(
        report,
        step={},
        retry_count=0,
        adaptive_memory_context=context,
    )

    assert actual == expected
    assert actual.action is AdaptiveAction.RETRY


def test_contract_violation_still_blocks_with_memory_context() -> None:
    report = _report("contract_violation", False)
    context = AdaptiveMemoryContextBuilder().build(report)

    decision = AdaptiveReplanner().decide(
        report,
        step={},
        adaptive_memory_context=context,
    )

    assert decision.action is AdaptiveAction.BLOCK
    assert decision.requires_user_review is True
