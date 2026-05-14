from __future__ import annotations

from pathlib import Path


FORBIDDEN_CALLERS = {
    "apply_runtime_repair_transaction_sandbox(": {
        "core/tasks/runtime_repair_apply_transaction.py",
    },
    "commit_runtime_repair_transaction_temp_workspace(": {
        "core/tasks/runtime_repair_apply_transaction.py",
    },
    "apply_patch_plan(": {
        "core/runtime/mutation_patch_apply.py",
        "core/runtime/mutation_runtime_pipeline.py",
    },
    "run_mutation_runtime_pipeline(": {
        "core/runtime/mutation_gateway.py",
        "core/runtime/mutation_runtime_pipeline.py",
    },
}


def test_runtime_execution_boundary_guard() -> None:
    violations: list[str] = []

    for path in Path("core").rglob("*.py"):
        normalized = path.as_posix()

        source = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        for forbidden_call, allowed_files in FORBIDDEN_CALLERS.items():
            if forbidden_call not in source:
                continue

            if normalized not in allowed_files:
                violations.append(
                    f"{normalized} illegally references {forbidden_call}"
                )

    assert not violations, "\n".join(violations)