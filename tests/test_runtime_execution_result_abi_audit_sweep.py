from __future__ import annotations

from pathlib import Path


def test_runtime_event_bus_execution_payload_keeps_canonical_fields() -> None:
    from core.runtime.runtime_event_bus import RuntimeEventBus

    event = RuntimeEventBus().publish(
        "runtime.kernel",
        "execution_result_recorded",
        payload={
            "ok": True,
            "verification": {"ok": True},
            "target_path": "core/runtime/event_bus_target.py",
        },
    )

    assert event.payload["executed"] is True
    assert event.payload["blocked"] is False
    assert event.payload["failed"] is False
    assert event.payload["verification_passed"] is True
    assert event.payload["changed_files"] == ["core/runtime/event_bus_target.py"]
    assert event.payload["impacted_files"] == ["core/runtime/event_bus_target.py"]
    assert event.payload["evidence"]["mutation_summary"]


def test_runtime_kernel_state_checkpoint_uses_canonical_execution_payload() -> None:
    from core.runtime.runtime_kernel_state import RuntimeKernelStateMachine

    checkpoint = RuntimeKernelStateMachine().checkpoint(
        {
            "execution_result": {
                "ok": True,
                "verification": {"ok": True},
                "operations": [
                    {
                        "op_type": "write_file",
                        "target_path": "core/runtime/kernel_state_target.py",
                    },
                ],
            },
        }
    )

    execution_result = checkpoint.payload["execution_result"]
    assert execution_result["executed"] is True
    assert execution_result["failed"] is False
    assert execution_result["verification_passed"] is True
    assert execution_result["changed_files"] == ["core/runtime/kernel_state_target.py"]
    assert execution_result["impacted_files"] == ["core/runtime/kernel_state_target.py"]
    assert execution_result["evidence"]["mutation_summary"]


def test_runtime_transaction_coordinator_preserves_execution_file_fields() -> None:
    from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator

    coordinator = RuntimeTransactionCoordinator()
    coordinator.begin_transaction(transaction_id="tx-abi-audit")
    result = coordinator.bind_execution(
        "tx-abi-audit",
        "execution-1",
        metadata={
            "ok": True,
            "changed_files": ["core/runtime/transaction_target.py"],
        },
    )

    metadata = result.to_metadata()["metadata"]
    assert metadata["changed_files"] == ["core/runtime/transaction_target.py"]
    assert metadata["impacted_files"] == ["core/runtime/transaction_target.py"]
    assert metadata["executed"] is True
    assert metadata["failed"] is False
    assert metadata["evidence"]["mutation_summary"]


def test_abi_adjacent_runtime_surfaces_import_canonical_helpers() -> None:
    root = Path(__file__).resolve().parents[1]

    for relative_path in (
        "core/runtime/runtime_event_bus.py",
        "core/runtime/runtime_kernel_state.py",
        "core/runtime/runtime_transaction_coordinator.py",
    ):
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "runtime_execution_result_fields" in source


def test_runtime_step_executor_does_not_define_parallel_execution_semantics() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "core/runtime/runtime_step_executor.py"

    if not path.exists():
        assert not path.exists()
        return

    source = path.read_text(encoding="utf-8")
    assert "runtime_execution_result_fields" in source
    assert "verification_passed = bool(" not in source
    assert "failed = bool(" not in source
