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
    (tmp_path / "core/engineering/engineering_runtime_execution_coordination.py").write_text("from core.engineering.read_adapter import ReadOnlyWorkspaceAdapter\n", encoding="utf-8")
    (tmp_path / "core/engineering/engineering_runtime_orchestrator.py").write_text("from core.engineering.engineering_runtime_execution_coordination import coordinate\n", encoding="utf-8")
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
    assert any(r["mainline_integration_status"] == "reference_only" for r in one["records"])
    assert all(not r["production_module"].startswith("tests/") for r in one["records"])
    assert "linter" not in one["coverage_summary"]["capability_ids"]
    assert any(g["capability_id"] == "linter" for g in one["gap_findings"])
    encoded = json.dumps(one)
    assert str(root) not in encoded and "atomic_commit()" not in encoded
    assert len(one["evidence"]) <= 512


def test_root_admission_and_path_escape_rejection(tmp_path):
    missing = build_repository_capability_inventory(tmp_path / "missing")
    assert missing["status"] == "rejected"
    assert ".." not in json.dumps(missing["evidence"])


def test_duplicate_ambiguity_closure_and_cli(tmp_path):
    root = _repo(tmp_path)
    (root / "core/engineering/read_two.py").write_text("ADAPTER_ID='read2'\nOPERATIONS=('read_text',)\nclass ReadOnlyWorkspaceAdapter: pass\n", encoding="utf-8")
    value = build_repository_capability_inventory(root)
    assert value["duplicate_candidate_findings"]
    assert value["report"]["ambiguous_findings"]
    assert value["closure"] == {"status": "closed", "read_only": True, "repository_modified": False}
    inventory, code = run(["inventory", "--repository-root", str(root)])
    gaps, gap_code = run(["gaps", "--repository-root", str(root)])
    assert code == gap_code == 0 and inventory["schema"].endswith(".v1") and "gap_findings" in gaps
