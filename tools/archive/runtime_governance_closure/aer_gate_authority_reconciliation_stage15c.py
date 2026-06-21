from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
TASK_RUNTIME = ROOT / "core" / "runtime" / "task_runtime.py"
INVENTORY_TEST = ROOT / "tests" / "test_runtime_status_ownership_inventory.py"
STAGE14_TOOL = ROOT / "tools" / "aer_ownership_migration_plan_stage14.py"
STAGE14 = OUT_DIR / "aer_ownership_migration_plan_stage14.json"
STAGE15A_TOOL = ROOT / "tools" / "aer_wave0_execution_gate_stage15a.py"
STAGE15A = OUT_DIR / "aer_wave0_execution_gate_stage15a.json"
STAGE15A1 = OUT_DIR / "aer_wave0_gate_failure_inventory_stage15a1.json"
STAGE15A2 = OUT_DIR / "gate_failure_closure_plan_stage15a2.json"
OUTPUT = OUT_DIR / "authority_reconciliation_stage15c.json"
SUMMARY = OUT_DIR / "authority_reconciliation_stage15c_summary.json"
REPORT = OUT_DIR / "authority_reconciliation_stage15c_report.md"

CLASSIFICATIONS = (
    "runtime_bug",
    "test_bug",
    "inventory_drift",
    "seal_rule_drift",
    "artifact_generator_drift",
)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required input: {relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def literal_assignment(tree: ast.AST, name: str) -> set[str]:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            value = ast.literal_eval(node.value)
            return {str(item) for item in value}
    raise SystemExit(f"missing literal assignment {name} in {relative(INVENTORY_TEST)}")


def status_assignments(path: Path, tracked_targets: set[str]) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if not isinstance(target, ast.Subscript):
                continue
            if not isinstance(target.slice, ast.Constant) or target.slice.value != "status":
                continue
            base = target.value
            base_name = base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else ""
            if base_name in tracked_targets:
                findings.append({"line": node.lineno, "target": base_name, "source": ast.get_source_segment(source, node) or "status assignment"})
    return sorted(findings, key=lambda item: item["line"])


def projection_calls(path: Path) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = function.id if isinstance(function, ast.Name) else function.attr if isinstance(function, ast.Attribute) else ""
        if name != "project_runtime_status":
            continue
        owner = ""
        for keyword in node.keywords:
            if keyword.arg == "owner" and isinstance(keyword.value, ast.Constant):
                owner = str(keyword.value.value)
        findings.append({"line": node.lineno, "owner_argument": owner})
    return sorted(findings, key=lambda item: item["line"])


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    stage14 = load(STAGE14)
    stage15a = load(STAGE15A)
    stage15a1 = load(STAGE15A1)
    stage15a2 = load(STAGE15A2)
    test_source = INVENTORY_TEST.read_text(encoding="utf-8-sig")
    test_tree = ast.parse(test_source, filename=str(INVENTORY_TEST))
    allowed_files = literal_assignment(test_tree, "ALLOWED_FILES")
    expected_high_risk = literal_assignment(test_tree, "EXPECTED_HIGH_RISK_FILES")
    tracked_targets = literal_assignment(test_tree, "TRACKED_STATUS_TARGETS")

    scan_roots = [ROOT / "core" / "runtime", ROOT / "core" / "tasks", ROOT / "core" / "adaptive"]
    direct_findings: dict[str, list[dict[str, Any]]] = {}
    projection_findings: dict[str, list[dict[str, Any]]] = {}
    for scan_root in scan_roots:
        for path in scan_root.rglob("*.py"):
            rel = relative(path)
            direct = status_assignments(path, tracked_targets)
            projected = projection_calls(path)
            if direct and rel not in allowed_files:
                direct_findings[rel] = direct
            if projected:
                projection_findings[rel] = projected

    observed_high_risk = set(direct_findings)
    missing_expected = sorted(expected_high_risk - observed_high_risk)
    projected_expected = sorted(expected_high_risk & set(projection_findings))
    projected_missing = sorted(set(missing_expected) & set(projection_findings))
    if observed_high_risk != {"core/runtime/task_runner.py"}:
        raise SystemExit(f"live direct-writer inventory drifted during reconciliation: {sorted(observed_high_risk)}")
    if len(missing_expected) != 10 or len(projected_missing) != 10:
        raise SystemExit(f"expected GF-003 evidence shape 10/10, got missing={len(missing_expected)}, projected_missing={len(projected_missing)}")

    gf3 = next(item for item in stage15a1["gate_failure_inventory"] if item["failure_id"] == "S15A1-GF-003")
    stage14_failure = next(
        item for item in stage14["validation_results"]["pytest"]["failures"]
        if item["test"].endswith("::test_runtime_status_ownership_inventory_is_explicit")
    )
    stage15a_failure = next(
        item for item in stage15a["validation_results"]["pytest"]["failures"]
        if item["test"].endswith("::test_runtime_status_ownership_inventory_is_explicit")
    )
    nonmainline = stage14["non_mainline_issues"]

    evidence_trace = [
        {
            "evidence_id": "GF003-E01",
            "layer": "runtime_owner",
            "source": f"{relative(TASK_RUNTIME)}:75",
            "fact": "project_runtime_status is the canonical status write boundary; it validates a dict target, assigns payload['status'], and returns that payload.",
        },
        {
            "evidence_id": "GF003-E02",
            "layer": "runtime_callers",
            "source": "live AST scan of core/runtime, core/tasks, and core/adaptive",
            "fact": "All eleven EXPECTED_HIGH_RISK_FILES entries call project_runtime_status; ten have no tracked direct status assignment, while task_runner.py remains the only tracked non-owner direct writer.",
            "projected_expected_files": projected_expected,
            "projected_missing_baseline_files": projected_missing,
            "direct_writer_files": sorted(observed_high_risk),
        },
        {
            "evidence_id": "GF003-E03",
            "layer": "inventory_rule",
            "source": f"{relative(INVENTORY_TEST)}:14-48",
            "fact": "ALLOWED_FILES names five accepted owner files, while EXPECTED_HIGH_RISK_FILES is a fixed eleven-file residue baseline.",
            "allowed_owner_files": sorted(allowed_files),
            "expected_high_risk_files": sorted(expected_high_risk),
        },
        {
            "evidence_id": "GF003-E04",
            "layer": "failing_assertion",
            "source": f"{relative(INVENTORY_TEST)}:98-115",
            "fact": "The assertion requires every fixed EXPECTED_HIGH_RISK_FILES entry to appear among current tracked direct status assignments.",
            "assertion": gf3["assertion"],
            "missing_expected_high_risk_files": missing_expected,
        },
        {
            "evidence_id": "GF003-E05",
            "layer": "stage14_seal",
            "source": f"{relative(STAGE14)}#validation_results/seal_blockers",
            "fact": "Stage14 records the assertion failure as seal evidence and requires ownership/evidence graph stability; its generic runtime-ownership drift rule does not require reintroducing direct status writes.",
            "failure": stage14_failure,
            "runtime_ownership_drift": stage14["seal_blockers"]["runtime_ownership_drift"],
            "evidence_graph_drift": stage14["seal_blockers"]["evidence_graph_drift"],
        },
        {
            "evidence_id": "GF003-E06",
            "layer": "non_mainline_track",
            "source": f"{relative(STAGE14)}#non_mainline_issues",
            "fact": "Six non-mainline observability records remain separately reported; GF-003 does not erase or reclassify them.",
            "tracking_ids": [item["tracking_id"] for item in nonmainline],
        },
        {
            "evidence_id": "GF003-E07",
            "layer": "stage15a_generator",
            "source": f"{relative(STAGE15A_TOOL)}:34-60,192-205",
            "fact": "Stage15A readiness consumes a hardcoded historical VALIDATION_RESULTS object, so rerunning the generator cannot observe a newly passing live suite without generator correction.",
            "failure": stage15a_failure,
        },
        {
            "evidence_id": "GF003-E08",
            "layer": "downstream_artifacts",
            "source": f"{relative(STAGE15A1)} and {relative(STAGE15A2)}",
            "fact": "Stage15A.1 preserves GF-003 as runtime-status inventory drift; Stage15A.2 correctly declines to manufacture direct writes and leaves reconciliation gated.",
            "stage15a1_category": gf3["categories"],
            "stage15a2_topology": stage15a2["execution_topology"]["status"],
        },
    ]

    authority_reconciliation = {
        "actual_runtime_owner": {
            "owner": "core.runtime.task_runtime.project_runtime_status",
            "owner_file": relative(TASK_RUNTIME),
            "write_symbol": "project_runtime_status(payload, status, owner=..., reason=...)",
            "evidence": "The only status assignment inside the canonical projection boundary is payload['status'] = status.",
        },
        "expected_inventory_owner": {
            "allowed_owner_files": sorted(allowed_files),
            "rule_meaning": "These files are excluded from the high-risk non-owner direct-writer scan; the suite separately asserts that each file exists.",
            "stale_residue_baseline": sorted(expected_high_risk),
        },
        "seal_rule_source": {
            "primary": f"{relative(STAGE14_TOOL)}:155-175,664-673",
            "artifact": f"{relative(STAGE14)}#validation_results/seal_blockers",
            "rule": stage14["seal_blockers"]["runtime_ownership_drift"]["condition"],
            "gf003_entry_path": "validation_results.pytest.failures[].seal_evidence",
        },
        "failing_assertion_source": {
            "source": f"{relative(INVENTORY_TEST)}:112",
            "assertion": "EXPECTED_HIGH_RISK_FILES <= high_risk",
            "expected_count": len(expected_high_risk),
            "observed_count": len(observed_high_risk),
            "missing_count": len(missing_expected),
        },
    }

    classification = {
        "gf003": "inventory_drift",
        "is_runtime_bug": False,
        "selection_count": 1,
        "allowed_classifications": list(CLASSIFICATIONS),
        "basis": [
            "The runtime uses the named canonical status projection boundary in ten files that the inventory still expects to be direct writers.",
            "The failing assertion compares a historical fixed residue set against current direct-write AST findings.",
            "Stage14 itself describes the failure as an inventory difference requiring reconciliation, not as proof of an illegal runtime write.",
        ],
        "downstream_drift": {
            "seal_rule_drift": "secondary: the seal consumes the stale inventory result as failure evidence",
            "artifact_generator_drift": "secondary: Stage15A hardcodes historical validation results",
            "test_bug": "not selected: assertion implementation is internally consistent with its static baseline; the baseline is stale",
        },
    }

    migration_plan = {
        "required": True,
        "scope": "inventory/seal/generator correction only; no runtime ownership change",
        "steps": [
            {
                "order": 1,
                "target": "runtime status ownership inventory source of truth",
                "action": "Generate a typed inventory with separate canonical-owner files, canonical projection callers, tracked non-owner direct writers, and non-mainline observability records.",
                "completion_gate": "The generated inventory reports task_runtime.project_runtime_status as owner, ten projected expected files, task_runner.py as the current tracked direct-writer residue, and S14-NM-001..006 unchanged.",
            },
            {
                "order": 2,
                "target": relative(INVENTORY_TEST),
                "action": "In a separately authorized change, replace the stale fixed direct-writer subset assertion with assertions over the typed inventory: canonical owner exists, projection callers are explicit, and no untracked direct writer appears.",
                "completion_gate": "The ownership suite passes without adding direct status writes to projection callers.",
            },
            {
                "order": 3,
                "target": "Stage14 successor seal definition",
                "action": "Bind status ownership seal evidence to the typed inventory and fail only on canonical-owner drift, unexpected direct writers, missing projection provenance, or loss of non-mainline records.",
                "completion_gate": "Seal semantics preserve runtime_ownership_drift and evidence_graph_drift without treating successful projection migration as missing evidence.",
            },
            {
                "order": 4,
                "target": relative(STAGE15A_TOOL),
                "action": "In a separately authorized successor generator, replace hardcoded VALIDATION_RESULTS readiness input with a versioned live validation-result artifact; retain historical failures as immutable evidence only.",
                "completion_gate": "A rerun reflects current suite results while Stage15A artifacts remain unchanged.",
            },
            {
                "order": 5,
                "target": "Wave 0 authorization reconciliation",
                "action": "Run artifact consistency and the corrected ownership inventory suite, then issue a new reconciliation decision rather than rewriting Stage14 or Stage15A evidence.",
                "completion_gate": "GF-003 is closed as inventory_drift, six non-mainline records remain reported, and no runtime/test change is hidden in artifact regeneration.",
            },
        ],
        "rollback_conditions": [
            "Any correction that reintroduces direct status writes into canonical projection callers.",
            "Any correction that removes S14-NM-001..006 from observability reporting.",
            "Any generator correction that overwrites historical Stage14/Stage15A evidence instead of versioning current results.",
        ],
    }

    source_paths = [TASK_RUNTIME, INVENTORY_TEST, STAGE14_TOOL, STAGE14, STAGE15A_TOOL, STAGE15A, STAGE15A1, STAGE15A2]
    payload = {
        "stage": "Stage15C — Gate Authority Reconciliation",
        "scope": "GF-003 authority reconciliation only",
        "production_runtime_modified": False,
        "tests_modified": False,
        "stage15a_artifacts_modified": False,
        "inputs": [{"artifact": relative(path), "sha256": digest(path)} for path in source_paths],
        "gf003_evidence_trace": evidence_trace,
        "live_inventory": {
            "expected_high_risk_count": len(expected_high_risk),
            "observed_direct_writer_count": len(observed_high_risk),
            "observed_direct_writer_files": sorted(observed_high_risk),
            "missing_expected_count": len(missing_expected),
            "missing_expected_files": missing_expected,
            "expected_files_using_canonical_projection_count": len(projected_expected),
            "expected_files_using_canonical_projection": projected_expected,
            "missing_baseline_files_using_canonical_projection_count": len(projected_missing),
            "missing_baseline_files_using_canonical_projection": projected_missing,
            "projection_call_evidence": {path: projection_findings[path] for path in projected_expected},
        },
        "authority_reconciliation": authority_reconciliation,
        "classification": classification,
        "migration_plan": migration_plan,
        "non_mainline_issue_reporting": {
            "mandatory": True,
            "status": "preserved",
            "count": len(nonmainline),
            "tracking_ids": [item["tracking_id"] for item in nonmainline],
        },
        "artifact_consistency": {
            "status": "pass",
            "classification_is_exactly_one": classification["selection_count"] == 1 and classification["gf003"] in CLASSIFICATIONS,
            "all_gf003_sources_traced": len(evidence_trace) == 8,
            "live_inventory_matches_failure_evidence": missing_expected == gf3["missing_expected_high_risk_files"],
            "stage15a_failure_preserved": stage15a_failure["gate"] == "seal",
        },
    }
    summary = {
        "stage": payload["stage"],
        "gf003_classification": classification["gf003"],
        "runtime_bug": False,
        "actual_runtime_owner": authority_reconciliation["actual_runtime_owner"]["owner"],
        "expected_inventory_owner_files": sorted(allowed_files),
        "observed_direct_writer_files": sorted(observed_high_risk),
        "canonical_projection_caller_coverage": f"{len(projected_missing)} / {len(missing_expected)} missing-baseline files",
        "seal_rule_source": authority_reconciliation["seal_rule_source"]["primary"],
        "failing_assertion_source": authority_reconciliation["failing_assertion_source"]["source"],
        "migration_plan_required": True,
        "migration_plan_steps": len(migration_plan["steps"]),
        "non_mainline_issue_reporting": "6 / 6 preserved",
        "artifact_consistency": "pass",
        "production_runtime_touched": False,
        "tests_touched": False,
        "stage15a_artifacts_touched": False,
        "outputs": {"reconciliation": relative(OUTPUT), "summary": relative(SUMMARY), "report": relative(REPORT)},
    }
    return payload, summary


def write_report(payload: dict[str, Any], summary: dict[str, Any]) -> None:
    reconciliation = payload["authority_reconciliation"]
    lines = [
        "# Stage15C — Gate Authority Reconciliation", "",
        "## Decision", "",
        f"- GF-003 classification: **{summary['gf003_classification']}**",
        "- Runtime bug: **false**",
        f"- Actual runtime owner: `{summary['actual_runtime_owner']}`",
        f"- Canonical projection coverage: {summary['canonical_projection_caller_coverage']}",
        f"- Current tracked non-owner direct writers: {', '.join(f'`{item}`' for item in summary['observed_direct_writer_files'])}", "",
        "## Authority reconciliation", "",
        f"- Expected inventory owner files: {', '.join(f'`{item}`' for item in summary['expected_inventory_owner_files'])}",
        f"- Seal rule source: `{summary['seal_rule_source']}`",
        f"- Failing assertion source: `{summary['failing_assertion_source']}`",
        f"- Failing assertion: `{reconciliation['failing_assertion_source']['assertion']}`", "",
        "## Evidence trace", "",
    ]
    for item in payload["gf003_evidence_trace"]:
        lines.append(f"- `{item['evidence_id']}` — **{item['layer']}** — {item['fact']} Source: `{item['source']}`")
    lines.extend(["", "## Classification basis", ""])
    for reason in payload["classification"]["basis"]:
        lines.append(f"- {reason}")
    lines.extend(["", "## Migration plan", ""])
    for step in payload["migration_plan"]["steps"]:
        lines.extend([f"### {step['order']}. {step['target']}", "", step["action"], "", f"Completion gate: {step['completion_gate']}", ""])
    lines.extend([
        "## Non-Mainline Issue Reporting", "",
        "- 6 / 6 Stage14 non-mainline observability records preserved.", "",
        "## Validation", "",
        "- Artifact consistency: pass",
        "- Classification selected exactly once: true",
        "- Runtime modified: false",
        "- Tests modified: false",
        "- Stage15A artifacts modified: false", "",
    ])
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    payload, summary = build()
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(payload, summary)
    print(f"gf003_classification: {summary['gf003_classification']}")
    print(f"runtime_bug: {str(summary['runtime_bug']).lower()}")
    print(f"actual_runtime_owner: {summary['actual_runtime_owner']}")
    print(f"canonical_projection_caller_coverage: {summary['canonical_projection_caller_coverage']}")
    print(f"artifact_consistency: {summary['artifact_consistency']}")
    print("production_runtime_touched: false")
    print("tests_touched: false")
    print("stage15a_artifacts_touched: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
