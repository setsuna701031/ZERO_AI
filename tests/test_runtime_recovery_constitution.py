from __future__ import annotations

import json
from pathlib import Path


def _source_chain() -> list[dict[str, str]]:
    return [
        {"evidence_id": "ev-1", "transaction_id": "tx-recovery"},
        {"evidence_id": "ev-2", "previous_evidence_id": "ev-1", "transaction_id": "tx-recovery"},
    ]


def test_recovery_continuity_is_preserved() -> None:
    from core.runtime.runtime_recovery_reconstruction import (
        build_runtime_recovery_reconstruction_contract,
        validate_runtime_recovery_reconstruction,
    )

    contract = build_runtime_recovery_reconstruction_contract(
        source_transaction_id="tx-recovery",
        source_evidence_chain=_source_chain(),
        reconstruction_state="consistent",
        reconstructed_runtime_state={"status": "recovered", "state_id": "state-recovered"},
    )
    report = validate_runtime_recovery_reconstruction(contract)

    assert contract["recovery_constitution_status"] == "canonical"
    assert report["recovery_constitution_status"] == "canonical"
    assert report["continuity_verified"] is True
    assert report["constitutional_continuity"]["recovery_source_state"]["source_transaction_id"] == "tx-recovery"
    assert report["constitutional_continuity"]["recovery_target_state"]["state_id"] == "state-recovered"
    assert report["block_recommended"] is False


def test_recovery_enforcement_snapshot_survives_reconstruction_serialization() -> None:
    from core.runtime.runtime_recovery_reconstruction import (
        build_runtime_recovery_reconstruction_contract,
        validate_runtime_recovery_reconstruction,
    )

    contract = build_runtime_recovery_reconstruction_contract(
        source_transaction_id="tx-recovery",
        source_evidence_chain=_source_chain(),
        reconstructed_runtime_state={"status": "recovered"},
    )
    restored = json.loads(json.dumps(contract, sort_keys=True, default=str))
    report = validate_runtime_recovery_reconstruction(restored)

    assert restored["enforcement_snapshot"]["schema"] == "runtime_enforcement_decision.v1"
    assert report["enforcement_snapshot"]["schema"] == "runtime_enforcement_decision.v1"
    assert report["enforcement_visibility"] is True


def test_recovery_continuity_break_becomes_review_required() -> None:
    from core.runtime.runtime_recovery_reconstruction import (
        build_runtime_recovery_reconstruction_contract,
    )

    contract = build_runtime_recovery_reconstruction_contract(
        source_transaction_id="tx-recovery",
        source_evidence_chain=[],
        reconstructed_runtime_state={"status": "recovered"},
    )

    assert contract["recovery_constitution_status"] == "review_required"
    assert contract["review_required"] is True
    assert "missing_recovery_evidence" in contract["continuity_break"]


def test_recovery_target_forbidden_terminal_regression_is_block_recommended() -> None:
    from core.runtime.runtime_recovery_reconstruction import recovery_constitution_summary
    from core.runtime.runtime_status_transition import runtime_status_transition_payload

    summary = recovery_constitution_summary(
        recovery_id="recovery-regression",
        recovery_lineage=["tx-recovery"],
        recovery_source_state={"source_transaction_id": "tx-recovery", "source_evidence_count": 1},
        recovery_target_state={"status": "sealed"},
        transition=runtime_status_transition_payload("recovered", "sealed", source="test"),
    )

    assert summary["recovery_constitution_status"] == "block_recommended"
    assert "recovery_target_forbidden_terminal_regression" in summary["continuity_break"]


def test_recovery_missing_lineage_requires_review_without_blocking() -> None:
    from core.runtime.runtime_recovery_reconstruction import recovery_constitution_summary

    summary = recovery_constitution_summary(
        recovery_id="recovery-review",
        recovery_lineage=[],
        recovery_source_state={"source_transaction_id": "tx-recovery", "source_evidence_count": 1},
        recovery_target_state={"status": "recovered"},
        transition={"from_status": "recovering", "to_status": "recovered", "allowed": True},
        transition_evidence={"transition_evidence_id": "ev"},
    )

    assert summary["recovery_constitution_status"] == "review_required"
    assert summary["review_required"] is True
    assert summary["block_recommended"] is False
    assert "missing_recovery_lineage" in summary["continuity_break"]


def test_forbidden_layers_do_not_import_recovery_constitution_helpers() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = _forbidden_runtime_surfaces(root)
    markers = (
        "RuntimeEnforcementMode",
        "recovery_constitution_summary",
        "recovery_constitution_status",
    )

    for path in forbidden:
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source


def _forbidden_runtime_surfaces(root: Path) -> list[Path]:
    direct = [
        root / "core/tasks/scheduler.py",
        root / "core/agent/agent_loop.py",
        root / "core/runtime/step_executor.py",
        root / "core/runtime/repair_transaction_execution_bridge.py",
        root / "app.py",
        root / "services/system_boot.py",
    ]
    directories = [root / "tools", root / "core/tools", root / "ui"]
    paths = [path for path in direct if path.exists()]
    for directory in directories:
        if directory.exists():
            paths.extend(
                path
                for path in directory.rglob("*.py")
                if "__pycache__" not in path.parts
            )
    return paths
