from core.runtime.runtime_supervisor_loop import (
    SUPERVISOR_ACTION_BLOCK,
    SUPERVISOR_ACTION_CONTINUE,
    SUPERVISOR_ACTION_ESCALATE,
    SUPERVISOR_ACTION_THROTTLE,
    SUPERVISOR_STATUS_BLOCKED,
    SUPERVISOR_STATUS_DEGRADED,
    SUPERVISOR_STATUS_ESCALATE,
    SUPERVISOR_STATUS_HEALTHY,
    RuntimeSupervisorLoop,
    evaluate_runtime_supervisor_loop,
)


def test_supervisor_reports_healthy_runtime_with_recovery_successes():
    decision = evaluate_runtime_supervisor_loop(
        [
            {
                "source": "runtime_loop",
                "status": "resumed",
                "event_type": "recovery_completed",
                "payload": {"recovered": True},
            }
        ]
    )

    payload = decision.to_dict()

    assert payload["verified"] is True
    assert payload["status"] == SUPERVISOR_STATUS_HEALTHY
    assert payload["action"] == SUPERVISOR_ACTION_CONTINUE
    assert payload["health_score"] >= 90


def test_supervisor_degrades_after_multiple_failures():
    decision = evaluate_runtime_supervisor_loop(
        [
            {
                "source": "step_executor",
                "status": "failed",
                "event_type": "step_failure",
                "payload": {"failure_type": "tool_error"},
            },
            {
                "source": "step_executor",
                "status": "failed",
                "event_type": "step_failure",
                "payload": {"failure_type": "validation_error"},
            },
        ],
        max_repeated_failures_before_escalate=3,
    )

    payload = decision.to_dict()

    assert payload["status"] == SUPERVISOR_STATUS_DEGRADED
    assert payload["action"] == SUPERVISOR_ACTION_THROTTLE
    assert "runtime_degraded" in payload["reasons"]


def test_supervisor_escalates_repeated_same_failure():
    decision = evaluate_runtime_supervisor_loop(
        [
            {
                "source": "step_executor",
                "status": "failed",
                "event_type": "step_failure",
                "payload": {"failure_type": "tool_error"},
            },
            {
                "source": "step_executor",
                "status": "failed",
                "event_type": "step_failure",
                "payload": {"failure_type": "tool_error"},
            },
        ]
    )

    payload = decision.to_dict()

    assert payload["status"] == SUPERVISOR_STATUS_ESCALATE
    assert payload["action"] == SUPERVISOR_ACTION_ESCALATE
    assert "repeated_failure_escalation" in payload["reasons"]


def test_supervisor_blocks_after_failure_limit():
    events = [
        {
            "source": "runtime",
            "status": "failed",
            "event_type": "failure",
            "payload": {"failure_type": f"error-{idx}"},
        }
        for idx in range(5)
    ]

    decision = evaluate_runtime_supervisor_loop(
        events,
        max_failures_before_block=5,
        max_repeated_failures_before_escalate=10,
    )

    payload = decision.to_dict()

    assert payload["status"] == SUPERVISOR_STATUS_BLOCKED
    assert payload["action"] == SUPERVISOR_ACTION_BLOCK
    assert "failure_limit_exceeded" in payload["reasons"]


def test_supervisor_loop_accumulates_observations_incrementally():
    supervisor = RuntimeSupervisorLoop(max_repeated_failures_before_escalate=3)

    supervisor.observe(
        source="runtime_loop",
        status="resumed",
        event_type="recovery_completed",
        payload={"recovered": True},
    )
    supervisor.observe(
        source="step_executor",
        status="failed",
        event_type="step_failure",
        payload={"failure_type": "tool_error"},
    )

    decision = supervisor.evaluate()
    payload = decision.to_dict()

    assert payload["verified"] is True
    assert payload["recovery_count"] == 1
    assert payload["failure_count"] == 1
    assert len(payload["observations"]) == 2
