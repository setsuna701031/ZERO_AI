import ast
from pathlib import Path

import pytest

from core.adaptive import AdaptiveDispatcher, AdaptivePlan
from core.evidence import EvidenceContract
from core.runtime.task_runner import TaskRunner


def test_dispatcher_returns_evidence_contract_not_runtime_acceptance() -> None:
    contract = AdaptiveDispatcher().dispatch(
        AdaptivePlan("goal-1", None, "request_evidence", "missing", evidence_required=["report"])
    )
    assert isinstance(contract, EvidenceContract)


def test_runtime_rejects_evidence_contract_and_does_not_validate() -> None:
    contract = EvidenceContract("plan-1", "goal-1", None, "missing", ["report"])
    with pytest.raises(TypeError, match="requires_adaptive_execution_contract"):
        TaskRunner().run_task_adaptive({"task_id": "task-1"}, execution_contract=contract)

    path = Path(__file__).resolve().parents[1] / "core" / "runtime" / "task_runner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name.startswith("core.evidence") for name in imports)


def test_evidence_collection_and_validation_do_not_import_runtime_or_memory() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "core/evidence/evidence_contract.py",
        "core/evidence/evidence_record.py",
        "core/evidence/evidence_collector.py",
        "core/evidence/evidence_validator.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any(name.startswith(("core.runtime", "core.memory")) for name in imports)
