from __future__ import annotations

import inspect


def test_scheduler_run_one_step_active_layer_is_v16() -> None:
    from core.tasks.scheduler import Scheduler

    assert Scheduler.run_one_step.__name__ == "_zero_scheduler_run_one_step_v16"


def test_scheduler_run_one_step_v16_wraps_v15() -> None:
    import core.tasks.scheduler as scheduler_module

    assert scheduler_module._zero_scheduler_base_run_one_step_v16.__name__ == "_zero_scheduler_run_one_step_v15"


def test_scheduler_run_one_step_legacy_chain_order_is_preserved() -> None:
    import core.tasks.scheduler as scheduler_module

    expected = {
        "_zero_scheduler_base_run_one_step_v16": "_zero_scheduler_run_one_step_v15",
        "_zero_scheduler_base_run_one_step_v15": "_zero_scheduler_run_one_step_v14",
        "_zero_scheduler_base_run_one_step_v14": "_zero_scheduler_run_one_step_v13",
        "_zero_scheduler_base_run_one_step_v13": "_zero_scheduler_run_one_step_v12",
        "_zero_scheduler_base_run_one_step_v12": "_zero_scheduler_run_one_step_v11",
        "_zero_scheduler_base_run_one_step_v11": "_zero_scheduler_run_one_step_v10",
        "_zero_scheduler_base_run_one_step_v10": "_zero_scheduler_run_one_step_v9",
        "_zero_scheduler_base_run_one_step_v9": "_zero_scheduler_run_one_step_v8",
        "_zero_scheduler_base_run_one_step_v8": "_zero_scheduler_run_one_step_v7",
        "_zero_scheduler_base_run_one_step_v7": "_zero_scheduler_run_one_step_v6",
        "_zero_scheduler_base_run_one_step_v6": "_zero_scheduler_run_one_step_v5",
        "_zero_scheduler_base_run_one_step_v5": "_zero_scheduler_run_one_step_v4",
        "_zero_scheduler_base_run_one_step_v4": "_zero_scheduler_run_one_step_v3",
        "_zero_scheduler_base_run_one_step_v3": "_zero_scheduler_run_one_step_v2",
    }

    for base_name, expected_name in expected.items():
        assert getattr(scheduler_module, base_name).__name__ == expected_name
