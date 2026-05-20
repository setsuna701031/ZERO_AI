from __future__ import annotations

import ast
from dataclasses import replace
import sys
from pathlib import Path
from typing import Any

import pytest

from core.runtime.execution_gateway import safe_subprocess_run
from core.runtime.executor import Executor
from core.runtime.governed_cross_session_handoff_contract import (
    build_governed_cross_session_handoff_contract,
    validate_governed_cross_session_handoff_contract,
)
from core.runtime.governed_runtime_continuation_session import (
    build_governed_runtime_continuation_record,
    validate_governed_runtime_continuation_record,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationVerificationRequirement,
)
from core.runtime.repair_transaction_execution_bridge import (
    execute_committed_runtime_repair_transaction,
)
from core.runtime.runtime_evidence_chain import validate_runtime_evidence_record
from core.runtime.runtime_execution_request import RuntimeExecutionRequest
from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
from core.runtime.runtime_recovery_coordinator import (
    RuntimeRecoveryCoordinator,
    RuntimeRecoveryRejected,
)
from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER = REPO_ROOT / "core" / "tasks" / "scheduler.py"
SCHEDULER_GATEWAY = REPO_ROOT / "core" / "tasks" / "scheduler_execution_gateway.py"
SYSTEM_BOOT = REPO_ROOT / "services" / "system_boot.py"
FREEZE_NOTE = REPO_ROOT / "docs" / "runtime_mainline_freeze.md"


def test_runtime_mainline_l4_freeze_preserves_sealed_metadata(tmp_path: Path) -> None:
    result = Executor(workspace_root=tmp_path / "executor").execute_request(
        RuntimeExecutionRequest(
            execution_type="subprocess",
            command=(sys.executable, "-c", "print('mainline-freeze')"),
            working_directory=str(tmp_path),
            timeout=20,
            metadata={
                "operation": "runtime_mainline_l4_freeze",
                "runtime_identity": {
                    "identity_id": "system:mainline_freeze",
                    "identity_type": "SYSTEM",
                    "source": "tests",
                },
                "authority_scope_id": "authority:mainline_freeze",
                "capability_scope_id": "capability:mainline_freeze",
                "provenance": {"test": "runtime_mainline_freeze_contract"},
            },
            lineage={
                "request_id": "mainline-freeze-request",
                "execution_start_id": "execution_start:mainline-freeze",
            },
            replay_id="replay:mainline-freeze",
        )
    )

    assert result.status == "succeeded"
    metadata = result.metadata
    evidence = metadata["runtime_evidence_record"]
    audit = metadata["runtime_audit_metadata"]
    execution_session = metadata["governed_runtime_execution_session"]
    replay_session = metadata["governed_runtime_replay_session"]

    assert metadata["governed_runtime_owner"] == "core.runtime.executor"
    assert metadata["governed_runtime_boundary_evaluated"] is True
    assert evidence["authority_metadata"]["runtime_identity"]["identity_type"] == "SYSTEM"
    assert evidence["authority_metadata"]["authority_scope_id"] == "authority:mainline_freeze"
    assert validate_runtime_evidence_record(evidence)["ok"] is True
    assert metadata["runtime_evidence_id"] == evidence["evidence_id"]
    assert audit["evidence_id"] == evidence["evidence_id"]
    assert audit["execution_session_id"] == evidence["execution_session_id"]
    assert audit["replay_session_id"] == evidence["replay_session_id"]
    assert result.side_effects[0].metadata["runtime_evidence_id"] == evidence["evidence_id"]
    assert result.side_effects[0].metadata["runtime_audit_metadata"]["evidence_id"] == evidence["evidence_id"]

    repair_result = _run_governed_repair(tmp_path)
    repair_metadata = repair_result.audit_record.metadata
    repair_evidence = repair_metadata["runtime_evidence_record"]
    repair_audit = repair_metadata["runtime_audit_metadata"]
    assert repair_result.completed is True
    assert validate_runtime_evidence_record(repair_evidence)["ok"] is True
    assert repair_metadata["runtime_evidence_id"] == repair_evidence["evidence_id"]
    assert repair_audit["evidence_id"] == repair_evidence["evidence_id"]
    assert repair_audit["mutation_transaction_id"] == repair_evidence["mutation_transaction_id"]
    assert repair_audit["mutation_request_id"] == repair_evidence["mutation_request_id"]

    recovery = _verify_recovery_with_repair_lineage(
        repair_metadata,
        source_session_id=execution_session["execution_session_id"],
    )
    recovery_governance = recovery.governance
    recovery_evidence = recovery_governance["runtime_evidence_record"]
    assert recovery_governance["runtime_evidence_id"] == recovery_evidence["evidence_id"]
    assert recovery_governance["runtime_audit_metadata"]["evidence_id"] == recovery_evidence["evidence_id"]
    assert recovery_governance["mutation_transaction_id"] == repair_evidence["mutation_transaction_id"]
    assert recovery_governance["mutation_request_id"] == repair_evidence["mutation_request_id"]
    assert recovery_governance["raw_recovery_execution_allowed"] is False

    continuation = build_governed_runtime_continuation_record(
        source_session_id=execution_session["execution_session_id"],
        replay_session_id=replay_session["replay_session_id"],
    )
    assert validate_governed_runtime_continuation_record(continuation)["continuation_valid"] is True

    handoff = build_governed_cross_session_handoff_contract(
        continuation_record=continuation,
        replay_session_report=replay_session,
        execution_session_report=execution_session,
        governance_closure_report={
            "closure_ready": True,
            "closure_state": "closed",
            "runtime_governance_freeze_candidate": True,
            "reason_codes": [],
        },
    )
    assert validate_governed_cross_session_handoff_contract(handoff)["ok"] is True
    assert handoff["lineage_valid"] is True
    assert handoff["source_session_id"] == execution_session["execution_session_id"]
    assert handoff["source_replay_session_id"] == replay_session["replay_session_id"]

    facade = safe_subprocess_run(
        (sys.executable, "-c", "print('mainline-facade')"),
        cwd=str(tmp_path),
        timeout=20,
    )
    facade_metadata = facade["metadata"]
    assert facade["ok"] is True
    assert facade_metadata["governed_runtime_owner"] == "core.runtime.executor"
    assert facade_metadata["runtime_evidence_id"] == (
        facade_metadata["runtime_evidence_record"]["evidence_id"]
    )
    assert facade_metadata["runtime_audit_metadata"]["execution_session_id"] == (
        facade_metadata["governed_runtime_execution_session_id"]
    )


def test_runtime_mainline_l4_freeze_rejects_recovery_without_governed_lineage() -> None:
    coordinator = _coordinator_with_failed_source()
    coordinator.create_recovery("mainline-recovery", "mainline-source")
    replayed = coordinator.run_recovery("mainline-recovery")
    coordinator._recoveries["mainline-recovery"] = replace(
        replayed,
        governance={
            "runtime_evidence_id": "",
            "runtime_evidence_record": {},
            "runtime_audit_metadata": {},
            "authority_metadata": {},
            "execution_session_id": "",
            "replay_session_id": "",
            "mutation_transaction_id": "",
            "mutation_request_id": "",
            "repair_transaction_id": "",
            "raw_recovery_execution_allowed": True,
        },
    )

    with pytest.raises(RuntimeRecoveryRejected):
        coordinator.verify_recovery("mainline-recovery")


def test_runtime_mainline_l4_freeze_keeps_scheduler_and_boot_as_compatibility_surfaces() -> None:
    scheduler_imports = _imported_modules(SCHEDULER)
    scheduler_gateway_imports = _imported_modules(SCHEDULER_GATEWAY)
    boot_imports = _imported_modules(SYSTEM_BOOT)
    scheduler_calls = _called_symbols(SCHEDULER)
    boot_calls = _called_symbols(SYSTEM_BOOT)

    assert "core.runtime.executor" not in scheduler_imports
    assert "core.runtime.executor.Executor" not in scheduler_imports
    assert "core.runtime.runtime_evidence_chain" not in scheduler_imports
    assert "core.runtime.runtime_recovery_coordinator" not in scheduler_imports
    assert not any(item.startswith("core.runtime.governed_runtime_") for item in scheduler_imports)
    assert "subprocess.run" not in scheduler_calls
    assert "subprocess.Popen" not in scheduler_calls
    assert "os.system" not in scheduler_calls

    assert "core.tasks.execution_gateway_runtime" in scheduler_gateway_imports
    assert "core.runtime.executor" not in scheduler_gateway_imports

    assert "core.runtime.runtime_mainline_evidence_seal" in boot_imports
    assert "core.runtime.runtime_governance_chain_seal" not in boot_imports
    assert "core.runtime.runtime_recovery_coordinator" not in boot_imports
    assert "core.runtime.executor" not in boot_imports
    assert "core.runtime.execution_gateway" not in boot_imports
    assert not any(item.startswith("core.runtime.governed_runtime_") for item in boot_imports)
    assert "subprocess.run" not in boot_calls
    assert "os.system" not in boot_calls


def test_runtime_mainline_freeze_note_records_l4_boundary() -> None:
    text = FREEZE_NOTE.read_text(encoding="utf-8")

    for phrase in (
        "Runtime Mainline Freeze / L4 Seal",
        "Sealed Runtime Boundaries",
        "Allowed Future Extension Surfaces",
        "Deferred Work",
        "Forbidden Future Regressions",
        "scheduler owning execution authority",
        "system_boot.py remains bootstrap wiring",
    ):
        assert phrase in text


def _run_governed_repair(tmp_path: Path) -> Any:
    workspace = tmp_path / "repair_workspace"
    sandbox = tmp_path / "repair_sandbox"
    rollback = tmp_path / "repair_rollback"
    reports = tmp_path / "repair_reports"
    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = create_runtime_repair_transaction(
        task_id="mainline_task",
        proposal_id="mainline_proposal",
        goal="prove mainline freeze repair lineage",
        scope_gate={"scope_allowed": True},
    )
    staged = stage_runtime_repair_mutation(
        transaction,
        {
            "op_type": "write_file",
            "target_path": "project/mainline_freeze.py",
            "content": "print('mainline freeze repair')\n",
        },
    )
    committed = commit_runtime_repair_transaction(staged)
    return execute_committed_runtime_repair_transaction(
        committed,
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        allowed_roots=("project",),
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.NONE,
    )


def _verify_recovery_with_repair_lineage(
    repair_metadata: dict[str, Any],
    *,
    source_session_id: str,
) -> Any:
    coordinator = _coordinator_with_failed_source(source_session_id)
    repair_evidence = repair_metadata["runtime_evidence_record"]
    repair_audit = repair_metadata["runtime_audit_metadata"]
    coordinator.create_recovery(
        "mainline-recovery",
        source_session_id,
        metadata={
            "lineage": {
                "mutation_transaction_id": repair_evidence["mutation_transaction_id"],
                "mutation_request_id": repair_evidence["mutation_request_id"],
                "repair_transaction_id": repair_audit["mutation_transaction_id"],
                "continuation_id": "continuation:mainline",
                "handoff_id": "handoff:mainline",
            },
            "authority": {"operator": "runtime_mainline_freeze_contract"},
            "audit_id": "audit:mainline-recovery",
        },
    )
    coordinator.run_recovery("mainline-recovery")
    return coordinator.verify_recovery("mainline-recovery")


def _coordinator_with_failed_source(
    source_session_id: str = "mainline-source",
) -> RuntimeRecoveryCoordinator:
    manager = RuntimeExecutionSessionManager()
    manager.create_session(source_session_id, f"{source_session_id}:lifecycle")
    manager.start_session(source_session_id)
    manager.fail_session(source_session_id)
    return RuntimeRecoveryCoordinator(session_manager=manager)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*")
    return modules


def _called_symbols(path: Path) -> set[str]:
    symbols: set[str] = set()
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Call):
            symbol = _attribute_chain(node.func)
            if symbol:
                symbols.add(symbol)
    return symbols


def _attribute_chain(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attribute_chain(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None
