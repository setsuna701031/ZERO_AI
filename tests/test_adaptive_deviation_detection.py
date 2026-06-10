from core.adaptive import DeviationDetector


def test_no_deviation_continues() -> None:
    report = DeviationDetector().detect(
        task_id="task-1",
        step={"id": "step-1", "expected": {"ok": True}},
        step_result={"ok": True, "message": "done"},
    )

    assert report.deviation_detected is False
    assert report.reason == "no_deviation"


def test_failed_step_produces_deviation_report() -> None:
    report = DeviationDetector().detect(
        task_id="task-1",
        step={"id": "step-2"},
        step_result={"ok": False, "error": "failed"},
    )

    assert report.deviation_detected is True
    assert report.step_id == "step-2"
    assert report.reason == "step_failed"


def test_contract_violation_is_unrecoverable() -> None:
    report = DeviationDetector().detect(
        task_id="task-1",
        step={"id": "step-3"},
        step_result={"ok": False, "error": {"type": "contract_violation", "message": "bad output"}},
    )

    assert report.reason == "contract_violation"
    assert report.recoverable is False
