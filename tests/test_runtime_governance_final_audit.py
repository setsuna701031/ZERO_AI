from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.runtime_governance_final_audit import (
    BYPASS_MARKERS,
    FINAL_AUDIT_REQUIRED_FILES,
    GOVERNANCE_FLOW,
    REGRESSION_COMMANDS,
    assert_runtime_governance_final_audit_closed,
    governance_coverage_matrix,
    run_runtime_governance_final_audit,
)


def _write_minimal_governance_stack(root: Path) -> None:
    matrix = governance_coverage_matrix()
    for target in matrix:
        doc = root / target.doc_path
        test = root / target.test_path
        doc.parent.mkdir(parents=True, exist_ok=True)
        test.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(
            f"# {target.name}\n\n"
            "## Non-mainline findings\n\n"
            "parallel governance graph, hidden governance source, legacy governance path, "
            "cross-layer drift, resume drift, continuation drift, replan drift, "
            "fallback, wildcard, unknown, default, legacy, runtime, system, unsealed\n",
            encoding="utf-8",
        )
        test.write_text(
            "def test_marker():\n"
            "    assert 'drift bypass fallback parallel remint reissue unknown wildcard'\n",
            encoding="utf-8",
        )


def test_final_audit_matrix_covers_all_runtime_governance_closures() -> None:
    matrix = governance_coverage_matrix()
    names = tuple(target.name for target in matrix)

    assert names == GOVERNANCE_FLOW
    assert len(names) == 9
    assert len(set(names)) == len(names)


def test_final_audit_required_files_match_matrix() -> None:
    matrix_files = []
    for target in governance_coverage_matrix():
        matrix_files.extend([target.doc_path, target.test_path])

    assert tuple(matrix_files) == FINAL_AUDIT_REQUIRED_FILES


def test_final_audit_regression_commands_include_every_closure_test() -> None:
    command_text = "\n".join(REGRESSION_COMMANDS)

    for target in governance_coverage_matrix():
        assert target.test_path in command_text


def test_final_audit_non_mainline_watch_markers_are_explicit() -> None:
    required = {
        "parallel governance graph",
        "hidden governance source",
        "legacy governance path",
        "cross-layer drift",
        "resume drift",
        "continuation drift",
        "replan drift",
        "authority bypass",
        "mutation bypass",
        "evidence bypass",
        "persistence bypass",
    }

    assert required.issubset(set(BYPASS_MARKERS))


def test_final_audit_passes_on_complete_stack(tmp_path: Path) -> None:
    _write_minimal_governance_stack(tmp_path)

    report = assert_runtime_governance_final_audit_closed(tmp_path)

    assert report["valid"] is True
    assert report["missing"] == []
    assert set(report["sealed_targets"]) == set(GOVERNANCE_FLOW)


def test_final_audit_fails_when_required_closure_is_missing(tmp_path: Path) -> None:
    _write_minimal_governance_stack(tmp_path)
    (tmp_path / "tests/test_runtime_identity_closure.py").unlink()

    with pytest.raises(ValueError, match="runtime_governance_final_audit_missing:.*test_runtime_identity_closure.py"):
        assert_runtime_governance_final_audit_closed(tmp_path)


def test_final_audit_reports_missing_non_mainline_section_without_hiding_it(tmp_path: Path) -> None:
    _write_minimal_governance_stack(tmp_path)
    target = governance_coverage_matrix()[0]
    (tmp_path / target.doc_path).write_text("# no reporting section\n", encoding="utf-8")

    report = run_runtime_governance_final_audit(tmp_path)

    assert report["valid"] is True
    assert any(
        finding["target"] == target.name
        and finding["finding"] == "missing_explicit_non_mainline_section"
        for finding in report["findings"]
    )


def test_final_audit_reports_closure_with_no_visible_drift_or_bypass_terms(tmp_path: Path) -> None:
    _write_minimal_governance_stack(tmp_path)
    target = governance_coverage_matrix()[1]
    (tmp_path / target.doc_path).write_text("# title\n\n## Non-mainline findings\nunknown\n", encoding="utf-8")
    (tmp_path / target.test_path).write_text("def test_marker():\n    assert True\n", encoding="utf-8")

    report = run_runtime_governance_final_audit(tmp_path)

    assert any(
        finding["target"] == target.name
        and finding["finding"] == "closure_lacks_visible_drift_or_bypass_terms"
        for finding in report["findings"]
    )


def test_final_audit_reports_missing_sentinel_visibility(tmp_path: Path) -> None:
    _write_minimal_governance_stack(tmp_path)
    target = governance_coverage_matrix()[2]
    (tmp_path / target.doc_path).write_text(
        "# title\n\n## Non-mainline findings\nparallel governance graph and cross-layer drift\n",
        encoding="utf-8",
    )
    (tmp_path / target.test_path).write_text("def test_marker():\n    assert 'drift bypass'\n", encoding="utf-8")

    report = run_runtime_governance_final_audit(tmp_path)

    assert any(
        finding["target"] == target.name
        and finding["finding"] == "sentinel_identity_or_governance_values_not_visible"
        for finding in report["findings"]
    )


def test_final_audit_document_exists_in_package() -> None:
    path = Path("docs/architecture/runtime_governance_final_audit.md")

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Runtime Governance Final Audit" in text
    assert "Non-mainline findings" in text
    assert "pytest -q tests/test_runtime_governance_final_audit.py" in text
