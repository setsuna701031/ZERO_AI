from __future__ import annotations


def test_scheduler_run_one_step_active_layer_is_v16() -> None:
    from core.tasks.scheduler import Scheduler

    assert Scheduler.run_one_step.__name__ == "_zero_scheduler_run_one_step_v16"


def test_scheduler_run_one_step_v16_may_wrap_v15_or_v12() -> None:
    import core.tasks.scheduler as scheduler_module

    # Phase 3 consolidation allows v16 to bypass v13-v15 after their
    # responsibilities are moved into the operator completion pipeline.
    assert scheduler_module._zero_scheduler_base_run_one_step_v16.__name__ in {
        "_zero_scheduler_run_one_step_v15",
        "_zero_scheduler_run_one_step_v8",
    }


def test_scheduler_run_one_step_legacy_chain_before_operator_pipeline_is_preserved() -> None:
    import core.tasks.scheduler as scheduler_module

    expected = {
        "_zero_scheduler_base_run_one_step_v8": "_zero_scheduler_run_one_step_v5",
        "_zero_scheduler_base_run_one_step_v6": "_zero_scheduler_run_one_step_v5",
    }

    for base_name, expected_name in expected.items():
        assert getattr(scheduler_module, base_name).__name__ == expected_name


def test_scheduler_operator_pipeline_helpers_exist_for_v13_to_v16_consolidation() -> None:
    import core.tasks.scheduler as scheduler_module

    assert callable(scheduler_module._zero_scheduler_run_operator_completion_pipeline)
    assert callable(scheduler_module._zero_scheduler_mark_operator_complete_if_ok)
    assert callable(scheduler_module._zero_scheduler_mark_operator_complete_or_failed)
    assert callable(scheduler_module._zero_scheduler_mark_failed_step_if_needed)
    assert callable(scheduler_module._zero_scheduler_mark_failed_if_ok_without_completion)
