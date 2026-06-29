from __future__ import annotations

from pathlib import Path

from core.engineering.repo_scan import (
    build_impacted_plan,
    build_impacted_file_plan,
    classify_repo_file,
    scan_repo,
)


import pytest

pytestmark = [pytest.mark.contract]

def test_repo_scan_is_read_only_and_skips_ignored_directories(tmp_path: Path) -> None:
    _write(tmp_path / "core" / "runtime" / "alpha_engine.py", "print('alpha')\n")
    _write(tmp_path / "tests" / "test_alpha_engine.py", "def test_alpha(): pass\n")
    _write(tmp_path / "docs" / "alpha_engine.md", "# Alpha\n")
    _write(tmp_path / ".git" / "HEAD", "ref: main\n")
    _write(tmp_path / "__pycache__" / "ignored.pyc", "ignored\n")
    _write(tmp_path / "node_modules" / "pkg" / "index.js", "ignored\n")
    _write(tmp_path / "dist" / "bundle.js", "ignored\n")
    _write(tmp_path / ".cache" / "item", "ignored\n")

    scan = scan_repo(tmp_path)
    payload = scan.to_dict()
    paths = {item["path"] for item in payload["files"]}

    assert scan.scan_id.startswith("repo-scan-")
    assert payload["metadata"]["read_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["patch_apply_allowed"] is False
    assert payload["metadata"]["autonomous_execution_allowed"] is False

    assert "core/runtime/alpha_engine.py" in paths
    assert "tests/test_alpha_engine.py" in paths
    assert "docs/alpha_engine.md" in paths
    assert ".git/HEAD" not in paths
    assert "__pycache__/ignored.pyc" not in paths
    assert "node_modules/pkg/index.js" not in paths
    assert "dist/bundle.js" not in paths
    assert ".cache/item" not in paths


def test_repo_scan_classifies_source_test_docs_and_config() -> None:
    assert classify_repo_file("core/runtime/example.py") == "source"
    assert classify_repo_file("tests/test_example.py") == "test"
    assert classify_repo_file("docs/example.md") == "docs"
    assert classify_repo_file("pyproject.toml") == "config"
    assert classify_repo_file("assets/logo.png") == "other"


def test_impacted_file_plan_contains_task_files_reasons_and_classification(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "core" / "runtime" / "alpha_engine.py", "print('alpha')\n")
    _write(tmp_path / "tests" / "test_alpha_engine.py", "def test_alpha(): pass\n")
    _write(tmp_path / "docs" / "alpha_engine.md", "# Alpha\n")
    _write(tmp_path / "pyproject.toml", "[tool.pytest.ini_options]\n")

    scan = scan_repo(tmp_path)
    plan = build_impacted_file_plan(
        "Update alpha engine tests and docs",
        scan=scan,
    )
    payload = plan.to_dict()
    paths = [item["path"] for item in payload["files"]]

    assert payload["plan_id"].startswith("impacted-file-plan-")
    assert payload["task"] == "Update alpha engine tests and docs"
    assert payload["source_scan_id"] == scan.scan_id
    assert payload["classification"] in {"mixed", "test", "docs", "source"}
    assert payload["reasons"]
    assert "core/runtime/alpha_engine.py" in paths
    assert "tests/test_alpha_engine.py" in paths
    assert "docs/alpha_engine.md" in paths

    for item in payload["files"]:
        assert item["classification"] in {"source", "test", "docs", "config", "other"}
        assert item["reasons"]
        assert item["score"] > 0

    assert payload["metadata"]["read_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False


def test_impacted_file_plan_has_no_mutation_or_execution_authority(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "core" / "planning" / "planner.py", "class Planner: pass\n")

    plan = build_impacted_file_plan(
        "Inspect planning contract",
        repo_root=tmp_path,
    )
    payload = plan.to_dict()

    forbidden_success_fields = {
        "runtime_evidence_id",
        "runtime_audit_metadata",
        "governed_mutation_lineage",
        "verification_result",
        "rollback_eligibility",
        "recovery_eligibility",
        "execution_summary",
        "diff_proposal",
        "authority_approval",
    }

    assert forbidden_success_fields.isdisjoint(payload)
    assert payload["metadata"]["read_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["patch_apply_allowed"] is False
    assert payload["metadata"]["autonomous_execution_allowed"] is False


def test_impacted_file_plan_feeds_loop_as_planning_artifact_not_success(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "docs" / "interactive_engineering_loop.md", "# Loop\n")

    plan = build_impacted_file_plan(
        "Document interactive engineering loop",
        repo_root=tmp_path,
    )
    loop_artifact = {
        "loop_state": "planning",
        "repo_scan_plan": plan.to_dict(),
        "plan_id": plan.plan_id,
        "impacted_files": [item.path for item in plan.files],
    }

    assert loop_artifact["loop_state"] == "planning"
    assert loop_artifact["repo_scan_plan"]["metadata"]["read_only"] is True
    assert "runtime_evidence_id" not in loop_artifact
    assert "governed_mutation_lineage" not in loop_artifact
    assert "execution_summary" not in loop_artifact


def test_impacted_plan_infers_transitive_topology_risk_and_verification_owners(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "core" / "runtime" / "alpha.py", "from core.runtime import beta\n")
    _write(tmp_path / "core" / "runtime" / "beta.py", "from core.runtime import gamma\n")
    _write(tmp_path / "core" / "runtime" / "gamma.py", "VALUE = 1\n")
    _write(tmp_path / "tests" / "test_alpha.py", "def test_alpha(): pass\n")

    plan = build_impacted_plan(
        "Update alpha runtime",
        changed_files=("core/runtime/alpha.py",),
        repo_root=tmp_path,
    )
    payload = plan.to_dict()

    assert "core/runtime/alpha.py" in payload["changed_files"]
    assert "core/runtime/beta.py" in payload["impacted_modules"]
    assert "core/runtime/gamma.py" in payload["impacted_modules"]
    assert payload["verification_targets"] == ["tests/test_alpha.py"]
    assert payload["mutation_risk"]["level"] == "high"
    assert payload["verification_owners"]["core/runtime/alpha.py"] == ["tests/test_alpha.py"]
    assert payload["impacted_runtime_topology"]["transitive"] is True
    assert payload["impacted_runtime_topology"]["risk_level"] == "high"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
