from __future__ import annotations

from pathlib import Path


def test_apply_patch_plan_is_only_called_by_runtime_pipeline() -> None:
    offenders: list[str] = []

    for path in Path("core").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")

        if "apply_patch_plan(" not in text:
            continue

        normalized = path.as_posix()
        if normalized == "core/runtime/mutation_patch_apply.py":
            continue
        if normalized == "core/runtime/mutation_runtime_pipeline.py":
            continue

        offenders.append(normalized)

    assert offenders == []


def test_run_mutation_runtime_pipeline_is_only_called_by_gateway() -> None:
    offenders: list[str] = []

    for path in Path("core").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")

        if "run_mutation_runtime_pipeline(" not in text:
            continue

        normalized = path.as_posix()
        if normalized == "core/runtime/mutation_runtime_pipeline.py":
            continue
        if normalized == "core/runtime/mutation_gateway.py":
            continue

        offenders.append(normalized)

    assert offenders == []


def test_governed_mutation_gateway_exists_as_public_entrypoint() -> None:
    from core.runtime.mutation_gateway import MutationGatewayRequest, run_governed_mutation

    assert MutationGatewayRequest is not None
    assert callable(run_governed_mutation)