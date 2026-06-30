from __future__ import annotations

import inspect
import json
from pathlib import Path

from core.runtime.runtime_contract_seal import (

    REQUIRED_CONTRACT_CHAINS,
    build_runtime_contract_seal,
)
from core.runtime.runtime_contract_seal_evidence import (
    export_runtime_contract_seal_evidence,
)
from core.runtime.runtime_evidence_surface import list_evidence
from core.runtime.runtime_execution_authority_evidence import (
    export_execution_authority_evidence,
)
from core.runtime.runtime_execution_authority_gate import RuntimeExecutionAuthorityGate
from core.runtime.runtime_mutation_audit_evidence import (
    export_runtime_mutation_audit_evidence,
)
from core.runtime.runtime_ownership_evidence import export_runtime_ownership_evidence
from core.runtime.runtime_recovery_evidence import export_runtime_recovery_evidence
from core.runtime.runtime_transition_evidence import (
    build_runtime_transition_evidence,
    export_runtime_transition_evidence,
)
from core.runtime.runtime_transition_record import RuntimeTransitionRecord
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy, pytest.mark.integration]



def test_runtime_contract_seal_fails_when_any_chain_is_missing(tmp_path: Path) -> None:
    task_id = "contract-missing"
    _export_contract_chain_evidence(
        tmp_path,
        task_id,
        include_mutation=False,
    )

    report = build_runtime_contract_seal(task_id=task_id, repo_root=tmp_path)
    payload = report.to_dict()

    assert report.sealed is False
    assert report.status == "failed"
    assert report.reason == "runtime_contract_missing_required_chain"
    assert report.mutation_evidence_status["present"] is False
    assert report.evidence_registry_status["ok"] is False
    assert payload["missing_chains"] == ["mutation_audit"]


def test_runtime_contract_seal_passes_only_when_all_runtime_chains_exist(
    tmp_path: Path,
) -> None:
    task_id = "contract-sealed"
    _export_contract_chain_evidence(tmp_path, task_id)

    report = build_runtime_contract_seal(
        task_id=task_id,
        repo_root=tmp_path,
        metadata={"seal_scope": "aer_final"},
    )
    payload = report.to_dict()

    assert report.sealed is True
    assert report.status == "sealed"
    assert report.reason == "runtime_contract_seal_complete"
    assert report.missing_chains == ()
    assert payload["ownership_status"]["status"] == "present"
    assert payload["execution_authority_status"]["status"] == "present"
    assert payload["recovery_evidence_status"]["status"] == "present"
    assert payload["transition_evidence_status"]["status"] == "present"
    assert payload["mutation_evidence_status"]["status"] == "present"
    assert payload["evidence_registry_status"]["required_evidence_types"] == list(
        REQUIRED_CONTRACT_CHAINS
    )
    assert payload["evidence_registry_status"]["ok"] is True
    assert payload["metadata"]["no_execution_performed"] is True


def test_runtime_contract_seal_exports_and_registers_evidence(tmp_path: Path) -> None:
    task_id = "contract-export"
    _export_contract_chain_evidence(tmp_path, task_id)
    report = build_runtime_contract_seal(task_id=task_id, repo_root=tmp_path)

    export = export_runtime_contract_seal_evidence(
        repo_root=tmp_path,
        task_id=task_id,
        seal_report=report,
    )

    evidence_path = Path(export["evidence_path"])
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    indexed = list_evidence(task_id, repo_root=tmp_path)

    assert evidence_path == (
        tmp_path
        / "workspace"
        / "evidence"
        / "runtime_contract"
        / "contract-export_runtime_contract_seal.json"
    )
    assert payload["sealed"] is True
    assert payload["status"] == "sealed"
    assert indexed[-1]["evidence_type"] == "runtime_contract_seal"
    assert indexed[-1]["metadata"]["sealed"] is True
    assert Path(indexed[-1]["path"]) == evidence_path


def test_runtime_contract_seal_modules_do_not_import_or_execute_runtime_surfaces() -> None:
    import core.runtime.runtime_contract_seal as contract_seal
    import core.runtime.runtime_contract_seal_evidence as contract_seal_evidence

    source = "\n".join(
        [
            inspect.getsource(contract_seal),
            inspect.getsource(contract_seal_evidence),
        ]
    )

    assert "from core.agent import agent_loop" not in source
    assert "from core.tasks import scheduler" not in source
    assert "from core.runtime.execution_gateway" not in source
    assert "from core.runtime.executor" not in source
    assert "from core.runtime.step_executor" not in source
    assert "import subprocess" not in source
    assert "os.system" not in source
    assert "run_mutation_runtime_pipeline(" not in source
    assert "run_governed_mutation_runtime(" not in source
    assert "run_recovery(" not in source
    assert "execute_recovery(" not in source


def _export_contract_chain_evidence(
    repo_root: Path,
    task_id: str,
    *,
    include_mutation: bool = True,
) -> None:
    export_runtime_ownership_evidence(
        repo_root=repo_root,
        task_id=task_id,
        ownership_report={
            "schema": "runtime_ownership_scan_report.v1",
            "ok": True,
            "policy": {"violation_count": 0, "violations": []},
        },
    )

    decision = RuntimeExecutionAuthorityGate().enforce(
        source="runtime.execution_gateway",
        action_type="command",
        metadata={"side_effect": True, "task_id": task_id},
    )
    export_execution_authority_evidence(
        repo_root=repo_root,
        task_id=task_id,
        decision=decision,
        metadata={"authority_path": "runtime.execution_gateway -> runtime.executor"},
    )

    export_runtime_recovery_evidence(
        repo_root=repo_root,
        task_id=task_id,
        recovery_report={
            "schema": "runtime_recovery_report.v1",
            "recovery_id": f"{task_id}-recovery",
            "status": "verified",
        },
    )

    export_runtime_transition_evidence(
        repo_root=repo_root,
        task_id=task_id,
        transition_evidence=build_runtime_transition_evidence(
            _transition_record(f"{task_id}-transition", lifecycle_id=task_id)
        ),
    )

    if include_mutation:
        export_runtime_mutation_audit_evidence(
            repo_root=repo_root,
            task_id=task_id,
            mutation_audit={
                "schema": "runtime_mutation_audit.v1",
                "audit_id": f"{task_id}-audit",
                "session_id": f"{task_id}-mutation-session",
                "status": "approved",
                "events": [],
            },
        )


def _transition_record(transition_id: str, *, lifecycle_id: str) -> RuntimeTransitionRecord:
    return RuntimeTransitionRecord(
        transition_id=transition_id,
        source="runtime_lifecycle_coordinator",
        from_state="verified",
        to_state="sealed",
        normalized_from_state="SESSION_RESTORED",
        normalized_to_state="SESSION_SEALED",
        canonical_from_status="runtime_verified",
        canonical_to_status="runtime_sealed",
        allowed=True,
        reason="transition_allowed",
        status="transitioned",
        enforcement_mode="AUDIT_ONLY",
        enforcement_allowed=True,
        enforcement_classification="observe_only",
        blocked=False,
        would_block=False,
        guard_ok=True,
        guard_reason="transition_allowed",
        lifecycle_id=lifecycle_id,
        artifact_id="artifact-runtime-contract",
        artifact_type="session",
        metadata={"seal": "runtime_contract"},
        evidence={"contract": {"allowed": True}},
    )
