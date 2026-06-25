from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "scheduler_run_one_step_chain_probe_report.txt"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    import core.tasks.scheduler as scheduler_module

    Scheduler = scheduler_module.Scheduler

    names = [
        "_ZERO_V734_ORIGINAL_RUN_ONE_STEP",
        "_ZERO_V352_ORIGINAL_SCHEDULER_RUN_ONE_STEP",
        "_ZERO_V7332_ORIGINAL_SCHEDULER_RUN_ONE_STEP",
        "_ZERO_V7333_ORIGINAL_SCHEDULER_RUN_ONE_STEP",
        "_ZERO_V7334_ORIGINAL_SCHEDULER_RUN_ONE_STEP",
        "_ZERO_V7335_ORIGINAL_SCHEDULER_RUN_ONE_STEP",
        "_ZERO_V7336_ORIGINAL_SCHEDULER_RUN_ONE_STEP",
        "_zero_scheduler_base_run_one_step_v3",
        "_zero_scheduler_base_run_one_step_v4",
        "_zero_scheduler_base_run_one_step_v5",
        "_zero_scheduler_base_run_one_step_v6",
        "_zero_scheduler_base_run_one_step_v7",
        "_zero_scheduler_base_run_one_step_v8",
        "_zero_scheduler_base_run_one_step_v9",
        "_zero_scheduler_base_run_one_step_v10",
        "_zero_scheduler_base_run_one_step_v11",
        "_zero_scheduler_base_run_one_step_v12",
        "_zero_scheduler_base_run_one_step_v13",
        "_zero_scheduler_base_run_one_step_v14",
        "_zero_scheduler_base_run_one_step_v15",
        "_zero_scheduler_base_run_one_step_v16",
    ]

    lines = [
        "Scheduler run_one_step Chain Probe",
        "",
        f"repo_root: {REPO_ROOT}",
        f"final Scheduler.run_one_step: {getattr(Scheduler.run_one_step, '__name__', repr(Scheduler.run_one_step))}",
        "",
        "Captured Base Chain:",
    ]

    for name in names:
        value = getattr(scheduler_module, name, None)
        lines.append(f"- {name}: {getattr(value, '__name__', repr(value))}")

    lines.extend(["", "Direct wrapper definitions present:"])

    for name in sorted(dir(scheduler_module)):
        if "run_one_step" in name and name.startswith("_zero"):
            value = getattr(scheduler_module, name)
            if callable(value):
                lines.append(f"- {name}: {getattr(value, '__name__', repr(value))}")

    lines.extend(
        [
            "",
            "Non-Mainline Issue Reporting:",
            "- This probe does not modify scheduler.py.",
            "- The active Scheduler.run_one_step endpoint is expected to be _zero_scheduler_run_one_step_v16.",
            "- Consolidation should preserve the final observable behavior before deleting old wrappers.",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())