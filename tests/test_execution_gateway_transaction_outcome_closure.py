from __future__ import annotations

from core.runtime.execution_gateway import build_runtime_execution_request


def test_execution_gateway_request_carries_transaction_boundary_and_allow_paths() -> None:
    request = build_runtime_execution_request(
        ["python", "-c", "print('ok')"],
        metadata={
            "target_file": "core/runtime/controlled_mutation_sandbox_executor.py",
        },
        allow_paths=[
            "core/runtime/controlled_mutation_sandbox_executor.py",
        ],
    )

    assert request.metadata["transaction_boundary"]["transaction_status"] == "opened"

    assert request.metadata["execution_boundary"]["allow_paths"] == [
        "core/runtime/controlled_mutation_sandbox_executor.py"
    ]

    assert request.metadata["allow_paths"] == [
        "core/runtime/controlled_mutation_sandbox_executor.py"
    ]