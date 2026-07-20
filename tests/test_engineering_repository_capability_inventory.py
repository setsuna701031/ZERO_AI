from __future__ import annotations

import json
from pathlib import Path

from cli.zero_engineering_capability_inventory import run
from core.engineering.engineering_repository_capability_inventory import build_repository_capability_inventory


def _repo(tmp_path: Path) -> Path:
    for part in ("core/engineering", "cli", "schemas", "tests"): (tmp_path / part).mkdir(parents=True, exist_ok=True)
    (tmp_path / "core/engineering/read_adapter.py").write_text("ADAPTER_ID='read'\nOPERATIONS=('read_text',)\nclass ReadOnlyWorkspaceAdapter: pass\n", encoding="utf-8")
    (tmp_path / "core/engineering/mutate.py").write_text("def execute_pipeline():\n atomic_commit()\n authorize_commit()\n operator_approval='required'\n mutation_authorization='required'\n rollback_transaction()\n", encoding="utf-8")
    (tmp_path / "core/engineering/orphan.py").write_text("ADAPTER_ID='orphan'\nOPERATIONS=('echo',)\nclass Adapter: pass\n", encoding="utf-8")
    (tmp_path / "core/engineering/engineering_runtime_workspace_controlled_executor.py").write_text("def execute_workspace_adapter(handoff): return handoff\n", encoding="utf-8")
    (tmp_path / "core/engineering/engineering_runtime_workspace_adapter_registry.py").write_text("def default_workspace_adapter_registry(): return {}\n", encoding="utf-8")
    (tmp_path / "core/engineering/engineering_runtime_execution_coordination.py").write_text(
        "from core.engineering.read_adapter import ReadOnlyWorkspaceAdapter\n"
        "from core.engineering.mutate import execute_pipeline\n"
        "from core.engineering.orphan import Adapter\n"
        "from core.engineering.engineering_runtime_workspace_controlled_executor import execute_workspace_adapter\n"
        "from core.engineering.engineering_runtime_workspace_adapter_registry import default_workspace_adapter_registry\n"
        "def coordinate(flow, handoff):\n"
        " if flow.get('execution_class') == 'read_only':\n  adapter=ReadOnlyWorkspaceAdapter(); reg=default_workspace_adapter_registry(); return execute_workspace_adapter(handoff)\n"
        " if flow.get('execution_class') == 'mutation': return execute_pipeline()\n", encoding="utf-8")
    (tmp_path / "core/engineering/engineering_runtime_orchestrator.py").write_text("from core.engineering.engineering_runtime_execution_coordination import coordinate\ndef orchestrate(flow, handoff): return coordinate(flow, handoff)\n", encoding="utf-8")
    (tmp_path / "core/engineering/reference.py").write_text("from x import build_reference_adapter_descriptor\nclass CanonicalEchoAdapter: pass\n", encoding="utf-8")
    (tmp_path / "core/engineering/linter_adapter.py").write_text("# filename alone is not evidence\n", encoding="utf-8")
    (tmp_path / "tests/test_fake.py").write_text("ADAPTER_ID='test_only'\n", encoding="utf-8")
    return tmp_path


def test_deterministic_ordering_classification_and_bounded_evidence(tmp_path):
    root = _repo(tmp_path); one = build_repository_capability_inventory(root); two = build_repository_capability_inventory(root)
    assert one == two and one["fingerprint"] == two["fingerprint"]
    assert one["records"] == sorted(one["records"], key=lambda r: (r["adapter_id"], r["production_module"]))
    records = {r["adapter_id"]: r for r in one["records"]}
    assert records["read"]["read_only"] is True and records["read"]["mutation_capable"] is False
    mutation = next(r for r in one["records"] if r["adapter_kind"] == "mutation_executor")
    assert mutation["mutation_capable"] is True
    assert mutation["requires_operator_approval"] is True and mutation["requires_mutation_authorization"] is True
    assert records["read"]["mainline_integration_status"] == "directly_integrated"
    assert records["orphan"]["mainline_integration_status"] == "available_but_not_integrated"
    assert records["orphan"]["classification_limitations"] == ["import_only_relationship_not_integration"]
    assert any(r["mainline_integration_status"] == "reference_only" for r in one["records"])
    assert all(not r["production_module"].startswith("tests/") for r in one["records"])
    assert "linter" not in one["coverage_summary"]["capability_ids"]
    assert any(g["capability_id"] == "linter" for g in one["gap_findings"])
    encoded = json.dumps(one)
    assert str(root) not in encoded and "atomic_commit()" not in encoded
    assert len(one["evidence"]) <= 512
    coordinator = next(r for r in one["records"] if r["ownership_role"] == "execution_coordinator")
    workspace = next(r for r in one["records"] if r["ownership_role"] == "delegated_workspace_executor")
    mutation = next(r for r in one["records"] if r["production_module"].endswith("mutate.py"))
    registry = next(r for r in one["records"] if r["ownership_role"] == "adapter_registry")
    assert coordinator["mainline_integration_status"] == "directly_integrated"
    assert workspace["mainline_integration_status"] == mutation["mainline_integration_status"] == "directly_integrated"
    assert workspace["production_module"] in coordinator["delegates_to"]
    assert coordinator["production_module"] in workspace["delegated_by"]
    assert {"call_evidence", "dispatch_evidence", "handoff_evidence", "delegation_evidence"} <= set(workspace["evidence_categories"])
    assert "registry_evidence" in registry["evidence_categories"]


def test_root_admission_and_path_escape_rejection(tmp_path):
    missing = build_repository_capability_inventory(tmp_path / "missing")
    assert missing["status"] == "rejected"
    assert ".." not in json.dumps(missing["evidence"])


def test_duplicate_ambiguity_closure_and_cli(tmp_path):
    root = _repo(tmp_path)
    (root / "core/engineering/read_two.py").write_text("ADAPTER_ID='read2'\nOPERATIONS=('read_text',)\nclass ReadOnlyWorkspaceAdapter: pass\n", encoding="utf-8")
    coordinator = root / "core/engineering/engineering_runtime_execution_coordination.py"
    coordinator.write_text(coordinator.read_text(encoding="utf-8") + "\nfrom core.engineering.read_two import ReadOnlyWorkspaceAdapter as ReadTwo\ndef dispatch_two(flow):\n if flow.get('execution_class') == 'read_only': return ReadTwo()\n", encoding="utf-8")
    value = build_repository_capability_inventory(root)
    assert any(f["status"] == "duplicate_candidate" and len(f["evidence_categories"]) >= 2 for f in value["duplicate_candidate_findings"])
    assert value["report"]["ambiguous_findings"]
    assert value["closure"] == {"status": "closed", "read_only": True, "repository_modified": False}
    inventory, code = run(["inventory", "--repository-root", str(root)])
    gaps, gap_code = run(["gaps", "--repository-root", str(root)])
    assert code == gap_code == 0 and inventory["schema"].endswith(".v1") and "gap_findings" in gaps


def test_test_only_call_and_single_category_do_not_prove_integration(tmp_path):
    root = _repo(tmp_path)
    (root / "core/engineering/test_called.py").write_text("ADAPTER_ID='test_called'\nOPERATIONS=('read_text',)\nclass ReadOnlyWorkspaceAdapter: pass\n", encoding="utf-8")
    (root / "tests/test_route.py").write_text("from core.engineering.test_called import ReadOnlyWorkspaceAdapter\ndef test_it(): ReadOnlyWorkspaceAdapter()\n", encoding="utf-8")
    value = build_repository_capability_inventory(root)
    record = next(r for r in value["records"] if r["adapter_id"] == "test_called")
    assert record["mainline_integration_status"] == "available_but_not_integrated"
    assert "test_route_evidence" in record["evidence_categories"]
    assert not any(f["status"] == "duplicate_candidate" and record["production_module"] in f["modules"] for f in value["duplicate_candidate_findings"])


def test_real_mainline_routes_and_layering():
    value = build_repository_capability_inventory(Path(__file__).parents[1])
    records = {r["production_module"]: r for r in value["records"]}
    coordinator = records["core/engineering/engineering_runtime_execution_coordination.py"]
    workspace = records["core/engineering/engineering_runtime_workspace_controlled_executor.py"]
    mutation = records["core/engineering/engineering_governed_workspace_mutation_executor.py"]
    assert coordinator["ownership_role"] == "execution_coordinator"
    assert workspace["ownership_role"] == "delegated_workspace_executor"
    assert mutation["ownership_role"] == "delegated_mutation_executor"
    assert workspace["mainline_integration_status"] == mutation["mainline_integration_status"] == "directly_integrated"
    assert workspace["production_module"] in coordinator["delegates_to"] and mutation["production_module"] in coordinator["delegates_to"]
    pair = {coordinator["production_module"], mutation["production_module"]}
    assert not any(f["status"] == "duplicate_candidate" and set(f["modules"]) == pair for f in value["duplicate_candidate_findings"])
