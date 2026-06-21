from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
STAGE11B = OUT_DIR / "runtime_blocker_validation.json"
STAGE11B_SUMMARY = OUT_DIR / "runtime_blocker_validation_summary.json"
STAGE12 = OUT_DIR / "runtime_blocker_domain_split_stage12.json"
STAGE12_SUMMARY = OUT_DIR / "runtime_blocker_domain_split_stage12_summary.json"
STAGE13A = OUT_DIR / "scheduler_native_ownership_closure_stage13a.json"
STAGE13A_SUMMARY = OUT_DIR / "scheduler_native_ownership_closure_stage13a_summary.json"
STAGE13B = OUT_DIR / "taskrunner_native_ownership_closure_stage13b.json"
STAGE13B_SUMMARY = OUT_DIR / "taskrunner_native_ownership_closure_stage13b_summary.json"
STAGE13C = OUT_DIR / "stepexecutor_native_ownership_closure_stage13c.json"
STAGE13C_SUMMARY = OUT_DIR / "stepexecutor_native_ownership_closure_stage13c_summary.json"
STAGE13D = OUT_DIR / "repairchain_native_ownership_closure_stage13d.json"
STAGE13D_SUMMARY = OUT_DIR / "repairchain_native_ownership_closure_stage13d_summary.json"
STAGE13E = OUT_DIR / "authority_planner_residual_closure_stage13e.json"
STAGE13E_SUMMARY = OUT_DIR / "authority_planner_residual_closure_stage13e_summary.json"
OUTPUT = OUT_DIR / "aer_ownership_migration_plan_stage14.json"
SUMMARY = OUT_DIR / "aer_ownership_migration_plan_stage14_summary.json"
REPORT = OUT_DIR / "aer_ownership_migration_plan_stage14_report.md"

STAGE_SOURCES = (
    ("stage13a", STAGE13A, "scheduler_items"),
    ("stage13b", STAGE13B, "taskrunner_items"),
    ("stage13c", STAGE13C, "stepexecutor_items"),
    ("stage13d", STAGE13D, "repairchain_items"),
    ("stage13e", STAGE13E, "residual_items"),
)

PRIMARY_DOMAIN = {
    "authority_contract": "authority_context",
    "planner_contract": "planner_goal_overlay",
    "scheduler_contract": "scheduler",
    "taskrunner_contract": "taskrunner",
    "step_executor_contract": "stepexecutor",
    "repair_chain": "repairchain",
}

DOMAIN_WAVE = {
    "authority_context": 1,
    "planner_goal_overlay": 2,
    "scheduler": 3,
    "taskrunner": 4,
    "stepexecutor": 5,
    "repairchain": 7,
}

DOMAIN_CLOSURE_GRAPH = {
    "authority_context": {
        "upstream": ["wave_0_evidence_lock"],
        "downstream": ["planner_goal_overlay", "taskrunner", "stepexecutor"],
    },
    "planner_goal_overlay": {
        "upstream": ["authority_context", "runtime_gate_compatibility_bridge"],
        "downstream": ["scheduler"],
    },
    "scheduler": {
        "upstream": ["planner_goal_overlay"],
        "downstream": ["taskrunner", "scheduler_direct_call_seal"],
    },
    "taskrunner": {
        "upstream": ["scheduler", "runtime_gate_compatibility_bridge"],
        "downstream": ["stepexecutor", "lineage", "runtime_session"],
    },
    "stepexecutor": {
        "upstream": ["taskrunner", "authority_context"],
        "downstream": ["lineage", "runtime_session", "repairchain"],
    },
    "repairchain": {
        "upstream": ["scheduler", "taskrunner", "stepexecutor", "lineage", "runtime_session"],
        "downstream": ["compatibility_bridge", "freeze_validation"],
    },
}

VALIDATION_SUITES = {
    "authority_context": [
        "tests/test_runtime_ownership_gate_contract.py",
        "tests/test_runtime_execution_ownership_seal.py",
        "tests/test_runtime_execution_ownership_migration_contract.py",
    ],
    "planner_goal_overlay": [
        "tests/test_scheduler_runtime_ownership_closure.py",
        "tests/test_runtime_ownership_execution_path_seal.py",
    ],
    "scheduler": [
        "tests/test_scheduler_runtime_ownership_closure.py",
        "tests/test_runtime_execution_ownership_seal.py",
        "tests/test_runtime_ownership_execution_path_seal.py",
    ],
    "taskrunner": [
        "tests/test_runtime_execution_ownership_migration_contract.py",
        "tests/test_runtime_ownership_gate_contract.py",
        "tests/test_runtime_ownership_contract.py",
    ],
    "stepexecutor": [
        "tests/test_runtime_execution_ownership_seal.py",
        "tests/test_runtime_ownership_execution_path_seal.py",
        "tests/test_runtime_ownership_enforcement.py",
    ],
    "repairchain": [
        "tests/test_runtime_native_autonomous_repair_chain_v1.py",
        "tests/test_runtime_native_autonomous_repair_chain_v2_integration.py",
        "tests/test_runtime_native_autonomous_repair_chain_seal_v1.py",
        "tests/test_runtime_blockers.py",
    ],
    "lineage": [
        "tests/test_runtime_execution_ownership_migration_contract.py",
        "tests/test_runtime_ownership_isolation_fabric_seal_v1.py",
    ],
    "runtime_session": [
        "tests/test_runtime_ownership_contract.py",
        "tests/test_runtime_status_ownership_inventory.py",
    ],
    "compatibility_bridge": [
        "tests/test_runtime_ownership_gate_contract.py",
        "tests/test_runtime_ownership_enforcement_phase3.py",
    ],
    "non_mainline_observability": [
        "tests/test_runtime_status_ownership_inventory.py",
        "tests/test_runtime_audit_artifact.py",
    ],
}

MIGRATION_ACTIONS = {
    "authority_context": "Promote the mapped authority-context behavior into the named native owner, preserve upstream capability provenance, and retire only the corresponding class-level assignment after its authority gate passes.",
    "planner_goal_overlay": "Promote the repair-plan branch into the native planner owner or one named native delegate, preserve canonical goal-to-step output, then retire the overlay and predecessor fallback.",
    "scheduler": "Move scheduler state, queue, dispatch, or retry-boundary behavior into the mapped native Scheduler endpoint and remove direct execution ownership from orchestration.",
    "taskrunner": "Move task execution, continuation, routing state, and persistence behavior into the mapped native TaskRunner endpoint while preserving scheduler and StepExecutor boundaries.",
    "stepexecutor": "Consolidate handler registration, execution, authority attachment, and fallback signatures in the mapped native StepExecutor endpoint.",
    "repairchain": "Consolidate repair eligibility, recovery, retry, duplicate suppression, and repair execution behavior under the mapped native repair owner.",
}

ROLLBACK_CONDITIONS = {
    "authority_context": "Rollback the wave if authority source, capability provenance, task/step identity, denial behavior, or runtime-session identity changes.",
    "planner_goal_overlay": "Rollback if canonical plan shape, repair-plan recognition, planner fallback behavior, or scheduler plan consumers diverge.",
    "scheduler": "Rollback if queue transitions, dispatch results, task finalization, retry handoff, or the scheduler no-direct-execution invariant regresses.",
    "taskrunner": "Rollback if task/tick execution, continuation identity, persistence, or scheduler/StepExecutor delegation changes.",
    "stepexecutor": "Rollback if handler routing, execution results, authority denial, fallback signatures, or adapter contracts diverge.",
    "repairchain": "Rollback if repair eligibility, recovery continuation, retry limits, duplicate suppression, lineage, or repair-session persistence diverges.",
}

RELATION_DOWNSTREAM = {
    "unlocks", "plan_consumer", "downstream_authority_context", "goal_to_step_boundary",
    "repair_plan_branch_output", "execution_caller_output", "final_mapping_unlock",
}

VALIDATION_RESULTS: dict[str, Any] = {
    "status": "failed_with_recorded_freeze_and_seal_evidence",
    "observed_on": "2026-06-21",
    "generator": "pass",
    "compileall": "pass",
    "pytest": {
        "status": "fail",
        "passed": 82,
        "failed": 2,
        "subtests_passed": 7,
        "duration_seconds": 13.27,
        "failures": [
            {
                "test": "tests/test_scheduler_runtime_ownership_closure.py::test_scheduler_constructs_one_endpoint_and_one_delegation_boundary",
                "freeze_evidence": "Scheduler contains six direct execute_step/execute_steps calls; Wave 3 cannot complete until the direct-call seal passes.",
            },
            {
                "test": "tests/test_runtime_status_ownership_inventory.py::test_runtime_status_ownership_inventory_is_explicit",
                "seal_evidence": "Expected high-risk status-writer inventory differs from the current source scan; ownership inventory evidence must be reconciled before seal.",
            },
        ],
    },
}


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required artifact: {relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def stable_unique(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = json.dumps(value, sort_keys=True, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


def stage12_confirmed(stage12: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for domain, values in stage12.get("confirmed_blockers_by_domain", {}).items():
        for item in values:
            copied = dict(item)
            copied["domain"] = domain
            result[(str(item.get("source_file")), int(item.get("source_line") or 0))] = copied
    return result


def merge_stage_records(payloads: dict[str, dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    merged: dict[tuple[str, int], dict[str, Any]] = {}
    for stage, _, item_key in STAGE_SOURCES:
        for item in payloads[stage].get(item_key, []):
            if item.get("validated_classification") != "confirmed_blocker":
                continue
            key = (str(item.get("source_file")), int(item.get("source_line") or 0))
            if key not in merged:
                merged[key] = {"canonical": dict(item), "sources": []}
            merged[key]["sources"].append({"stage": stage, "record": dict(item)})
    return merged


def record_values(sources: list[dict[str, Any]], field: str) -> list[Any]:
    return [source["record"][field] for source in sources if source["record"].get(field) not in (None, "", [])]


def cross_domains(sources: list[dict[str, Any]], primary: str) -> list[str]:
    domains = [primary]
    records = [source["record"] for source in sources]
    if any(record.get("goal_lineage_dependency") is True for record in records):
        domains.append("lineage")
    if any(record.get("runtime_session_dependency") is True for record in records):
        domains.append("runtime_session")
    if any("lineage_dependency" in record.get("buckets", []) for record in records):
        domains.append("lineage")
    if any("runtime_session_dependency" in record.get("buckets", []) for record in records):
        domains.append("runtime_session")
    if any("repair_lineage" in record.get("ownership_buckets", []) for record in records):
        domains.append("lineage")
    if any("repair_session" in record.get("ownership_buckets", []) for record in records):
        domains.append("runtime_session")
    if any(record.get("lineage_boundary", {}).get("active") is True for record in records):
        domains.append("lineage")
    if any(record.get("runtime_session_boundary", {}).get("active") is True for record in records):
        domains.append("runtime_session")
    return stable_unique(domains)


def normalize_edges(sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for source in sources:
        for edge in source["record"].get("dependency_edges", []):
            if not isinstance(edge, dict):
                continue
            if edge.get("direction") and edge.get("domain"):
                result.append({
                    "from": str(edge["domain"]) if edge["direction"] == "upstream" else "mapped_blocker",
                    "to": "mapped_blocker" if edge["direction"] == "upstream" else str(edge["domain"]),
                    "relationship": str(edge.get("relationship") or edge["direction"]),
                    "evidence_stage": source["stage"],
                })
            elif edge.get("from") and edge.get("to"):
                result.append({
                    "from": str(edge["from"]),
                    "to": str(edge["to"]),
                    "relationship": str(edge.get("relationship") or "dependency"),
                    "evidence_stage": source["stage"],
                })
    return stable_unique(result)


def domain_closure_edges(primary: str, primary_contract: str) -> list[dict[str, str]]:
    graph = DOMAIN_CLOSURE_GRAPH[primary]
    return [
        {"from": value, "to": primary_contract, "relationship": "wave_upstream_dependency", "evidence_stage": "stage12_and_stage14_wave_order"}
        for value in graph["upstream"]
    ] + [
        {"from": primary_contract, "to": value, "relationship": "wave_downstream_unlock", "evidence_stage": "stage12_and_stage14_wave_order"}
        for value in graph["downstream"]
    ]


def upstream_downstream(edges: list[dict[str, str]], primary_contract: str, symbol: str, unlock_values: list[Any]) -> tuple[list[str], list[str]]:
    targets = {"mapped_blocker", primary_contract, symbol, "repair_chain" if primary_contract == "repair_chain" else ""}
    upstream: list[str] = []
    downstream: list[str] = []
    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        relationship = edge["relationship"]
        if target in targets:
            upstream.append(source)
        elif source in targets or relationship in RELATION_DOWNSTREAM:
            downstream.append(target)
        else:
            upstream.append(source)
            downstream.append(target)
    for value in unlock_values:
        if isinstance(value, str):
            downstream.append(value)
        elif isinstance(value, list):
            downstream.extend(str(item) for item in value)
    return sorted(set(filter(None, upstream))), sorted(set(filter(None, downstream)))


def risk_level(primary: str, sources: list[dict[str, Any]]) -> str:
    records = [source["record"] for source in sources]
    if primary in {"authority_context", "scheduler", "taskrunner", "stepexecutor"}:
        return "critical"
    if any(record.get("fallback_signature") or "duplicate_repair" in record.get("ownership_buckets", []) for record in records):
        return "critical"
    return "high"


def validation_gate(domains: list[str]) -> dict[str, Any]:
    suites = stable_unique(suite for domain in domains for suite in VALIDATION_SUITES[domain])
    return {
        "required_suites": suites,
        "pass_condition": "All named suites pass with no ownership, authority, lineage, session, blocker, or artifact regression.",
        "evidence_condition": "The blocker-specific source assignment is absent only after native-owner evidence and dependency edges remain stable.",
    }


def migration_record(
    key: tuple[str, int],
    merged: dict[str, Any],
    stage12_item: dict[str, Any],
) -> dict[str, Any]:
    canonical = merged["canonical"]
    sources = merged["sources"]
    stage12_domain = str(stage12_item["domain"])
    primary = PRIMARY_DOMAIN[stage12_domain]
    domains = cross_domains(sources, primary)
    edges = stable_unique(normalize_edges(sources) + domain_closure_edges(primary, stage12_domain))
    unlock_values = record_values(sources, "unlock_targets")
    upstream, downstream = upstream_downstream(edges, stage12_domain, str(canonical.get("symbol")), unlock_values)
    native_owner = str(
        canonical.get("expected_native_owner")
        or canonical.get("native_owner")
        or canonical.get("owner_endpoint")
        or stage12_item.get("replacement_target")
    )
    safe_conditions = record_values(sources, "safe_removal_precondition")
    evidence = stable_unique(
        value
        for source in sources
        for value in source["record"].get("evidence_source", [])
    )
    aliases = [
        {"stage": source["stage"], "blocker_id": source["record"].get("blocker_id")}
        for source in sources
    ]
    return {
        "blocker_id": str(canonical.get("blocker_id")),
        "blocker_aliases": aliases,
        "current_owner": str(canonical.get("current_owner") or f"class-level assignment in {key[0]}:{key[1]}"),
        "native_owner": native_owner,
        "source_file": key[0],
        "source_line": key[1],
        "symbol": str(canonical.get("symbol") or stage12_item.get("symbol")),
        "stage12_domain": stage12_domain,
        "migration_domains": domains,
        "primary_migration_wave": DOMAIN_WAVE[primary],
        "dependency_edges": edges,
        "upstream_dependencies": upstream,
        "downstream_unlocks": downstream,
        "migration_action": MIGRATION_ACTIONS[primary],
        "safe_removal_precondition": " ".join(stable_unique(str(value) for value in safe_conditions)),
        "validation_gate": validation_gate(domains),
        "rollback_condition": ROLLBACK_CONDITIONS[primary],
        "risk_level": risk_level(primary, sources),
        "freeze_gate": {
            "required": True,
            "condition": "Native owner is active, blocker assignment is retired, dependency graph is stable, and validation_gate passes before AER freeze.",
        },
        "seal_gate": {
            "required": True,
            "condition": "Freeze evidence remains valid with no runtime ownership drift, evidence graph drift, compatibility residue, or non-mainline residue.",
        },
        "evidence_source": evidence,
    }


def ancillary_record(index: int, item: dict[str, Any], kind: str) -> dict[str, Any]:
    prefix = "CB" if kind == "compatibility_bridge" else "NM"
    domain = kind if kind == "compatibility_bridge" else "non_mainline_observability"
    action = (
        "Retire only after every consumer uses the canonical native contract; preserve the bridge until Wave 8 validation passes."
        if kind == "compatibility_bridge"
        else "Assign a named native observability owner, preserve evidence output, and retire the non-mainline assignment only after independent artifact validation."
    )
    return {
        "tracking_id": f"S14-{prefix}-{index:03d}",
        "validated_classification": str(item.get("classification") or kind),
        "migration_domain": domain,
        "source_file": str(item.get("source_file") or ""),
        "source_line": int(item.get("source_line") or 0),
        "symbol": str(item.get("symbol") or ""),
        "current_owner": f"class-level assignment in {item.get('source_file')}:{item.get('source_line')}",
        "native_owner": str(item.get("replacement_target") or "named native owner required"),
        "migration_action": action,
        "safe_removal_precondition": str(item.get("safe_removal_precondition") or ""),
        "validation_gate": validation_gate([domain]),
        "seal_gate": True,
        "evidence_source": [f"{relative(STAGE12)}#{kind}", f"{item.get('source_file')}:{item.get('source_line')}"],
    }


def scheduler_direct_calls() -> list[dict[str, Any]]:
    path = ROOT / "core" / "tasks" / "scheduler.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def owner(node: ast.AST) -> str:
        current: ast.AST | None = node
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current.name
            current = parents.get(current)
        return "module"

    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"execute_step", "execute_steps"}:
            result.append({"source_file": relative(path), "source_line": node.lineno, "caller": owner(node), "call": node.func.attr})
    return sorted(result, key=lambda item: (item["source_line"], item["caller"], item["call"]))


def wave_definition(number: int, blockers: list[dict[str, Any]], bridges: list[dict[str, Any]], nonmainline: list[dict[str, Any]]) -> dict[str, Any]:
    names = {
        0: "evidence and invariant lock",
        1: "authority context migration",
        2: "planner goal overlay migration",
        3: "scheduler direct-call seal",
        4: "taskrunner execution ownership",
        5: "stepexecutor fallback / execution ownership",
        6: "lineage + runtime-session boundary",
        7: "repairchain recovery / retry / duplicate repair",
        8: "compatibility bridge retirement",
        9: "freeze validation",
        10: "seal validation",
    }
    included: list[str]
    if number == 0:
        included = [item["blocker_id"] for item in blockers]
    elif number in {1, 2, 3, 4, 5, 7}:
        included = [item["blocker_id"] for item in blockers if item["primary_migration_wave"] == number]
    elif number == 6:
        included = [item["blocker_id"] for item in blockers if set(item["migration_domains"]) & {"lineage", "runtime_session"}]
    elif number == 8:
        included = [item["tracking_id"] for item in bridges]
    elif number == 9:
        included = [item["blocker_id"] for item in blockers]
    else:
        included = [item["blocker_id"] for item in blockers] + [item["tracking_id"] for item in bridges + nonmainline]

    cannot_start = {
        0: [], 1: [0], 2: [1], 3: [2], 4: [3], 5: [4], 6: [5], 7: [6], 8: [7], 9: [8], 10: [9],
    }[number]
    suites: list[str] = []
    domain_by_wave = {
        1: ["authority_context"], 2: ["planner_goal_overlay"], 3: ["scheduler"],
        4: ["taskrunner"], 5: ["stepexecutor"], 6: ["lineage", "runtime_session"],
        7: ["repairchain"], 8: ["compatibility_bridge"],
        9: list(VALIDATION_SUITES), 10: list(VALIDATION_SUITES),
    }
    for domain in domain_by_wave.get(number, []):
        suites.extend(VALIDATION_SUITES[domain])
    suites = stable_unique(suites)
    return {
        "wave": number,
        "name": names[number],
        "included_blockers": included,
        "included_blocker_count": len(included),
        "required_preconditions": [
            "Prior-wave completion evidence is immutable and linked to blocker IDs.",
            "Every included blocker retains its mapped native owner, dependency edges, and safe-removal precondition.",
        ] + (["All 113 source assignments and native-owner invariants are snapshotted before migration begins."] if number == 0 else []),
        "expected_unlocks": [f"wave_{number + 1}" if number < 10 else "aer_seal"],
        "validation_suites": suites,
        "rollback_condition": "Rollback the entire wave if any included blocker validation gate fails or ownership/evidence drift is detected.",
        "cannot_start_until_dependencies": [f"wave_{value}_complete" for value in cannot_start],
        "completion_criteria": "All included records satisfy native-owner, safe-removal, validation, rollback-evidence, freeze-gate, and seal-gate requirements.",
    }


def write_report(payload: dict[str, Any], summary: dict[str, Any]) -> None:
    lines = [
        "# AER Ownership Migration Plan — Stage14", "",
        "Planning only. No production runtime or test file was modified, and no blocker was fixed.", "",
        "## Summary", "",
        f"- Confirmed blockers planned: {summary['total_confirmed_blockers_planned']}",
        f"- Migration waves: {summary['migration_waves_count']}",
        f"- Freeze blockers: {summary['freeze_blockers_count']}",
        f"- Seal blockers: {summary['seal_blockers_count']}",
        f"- Compatibility bridges tracked separately: {summary['compatibility_bridge_count']}",
        f"- Non-mainline issues tracked separately: {summary['non_mainline_issue_count']}",
        f"- Highest-risk domains: {', '.join(summary['highest_risk_domains'])}",
        f"- First executable migration wave: {summary['first_executable_migration_wave']}",
        "- Production runtime touched: false",
        "- Tests touched: false", "",
        "## Ordered migration waves", "",
    ]
    for wave in payload["migration_waves"]:
        lines.extend([
            f"### Wave {wave['wave']}: {wave['name']}", "",
            f"- Included records: {wave['included_blocker_count']}",
            f"- Cannot start until: {', '.join(wave['cannot_start_until_dependencies']) or 'none'}",
            f"- Validation suites: {', '.join(f'`{x}`' for x in wave['validation_suites']) or 'evidence/schema validation'}",
            f"- Completion: {wave['completion_criteria']}",
            f"- Rollback: {wave['rollback_condition']}", "",
        ])
    lines.extend(["## Migration domain counts", ""])
    for domain, count in summary["migration_domain_counts"].items():
        lines.append(f"- `{domain}`: {count}")
    lines.extend(["", "## Freeze blockers", ""])
    freeze = payload["freeze_blockers"]
    lines.extend([
        f"- Confirmed blocker records: {len(freeze['all_confirmed_blockers'])}",
        f"- Critical suite blockers: {freeze['critical_suite_blockers']['count']}",
        f"- Direct StepExecutor call seals: {len(freeze['direct_stepexecutor_call_seals'])}",
        f"- Authority propagation blockers: {len(freeze['authority_propagation_blockers'])}",
        f"- Goal-lineage integrity blockers: {len(freeze['goal_lineage_integrity_blockers'])}",
        f"- Runtime-session blockers: {len(freeze['runtime_session_blockers'])}",
        f"- Repair-chain blockers: {len(freeze['repair_chain_blocker_groups']['all'])}", "",
        "## Seal blockers", "",
        f"- Distinct actionable records: {summary['seal_blockers_count']}",
        f"- Runtime ownership drift gate: {payload['seal_blockers']['runtime_ownership_drift']['condition']}",
        f"- Evidence graph drift gate: {payload['seal_blockers']['evidence_graph_drift']['condition']}",
        f"- Compatibility bridge residue: {len(payload['seal_blockers']['compatibility_bridge_residue'])}",
        f"- Non-mainline observability residue: {len(payload['seal_blockers']['non_mainline_observability_residue'])}", "",
        "## Confirmed blocker plan", "",
    ])
    for item in payload["blocker_migration_plan"]:
        lines.extend([
            f"- `{item['blocker_id']}` — `{item['source_file']}:{item['source_line']}` — `{item['symbol']}`",
            f"  - Domains: {', '.join(f'`{x}`' for x in item['migration_domains'])}",
            f"  - Native owner: `{item['native_owner']}`",
            f"  - Risk: `{item['risk_level']}`; primary wave: {item['primary_migration_wave']}",
            f"  - Safe removal: {item['safe_removal_precondition']}",
        ])
    lines.extend(["", "## Compatibility Bridge Retirement Track", ""])
    for item in payload["compatibility_bridges"]:
        lines.append(f"- `{item['tracking_id']}` — `{item['source_file']}:{item['source_line']}` — `{item['symbol']}`")
    lines.extend(["", "## Non-Mainline Issue Report", ""])
    for item in payload["non_mainline_issues"]:
        lines.append(f"- `{item['tracking_id']}` — `{item['source_file']}:{item['source_line']}` — `{item['symbol']}`")
    validation = summary["validation_results"]
    lines.extend([
        "", "## Validation", "",
        f"- Generator: {validation['generator']}",
        f"- Compileall: {validation['compileall']}",
        f"- Pytest: {validation['pytest']['passed']} passed, {validation['pytest']['failed']} failed, {validation['pytest']['subtests_passed']} subtests passed",
        f"- Overall: {validation['status']}",
        "- Failing tests were recorded as freeze/seal evidence and were not fixed.",
        "- Production runtime touched: false",
        "- Tests touched: false", "",
    ])
    if validation["pytest"]["failures"]:
        lines.extend(["### Recorded validation failures", ""])
        for failure in validation["pytest"]["failures"]:
            evidence = failure.get("freeze_evidence") or failure.get("seal_evidence") or "Recorded as migration evidence."
            lines.append(f"- `{failure['test']}` — {evidence}")
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def validate(blockers: list[dict[str, Any]], stage13e: dict[str, Any], bridges: list[dict[str, Any]], nonmainline: list[dict[str, Any]]) -> None:
    if stage13e.get("mapping_closure", {}).get("status") != "113 / 113 mapped":
        raise SystemExit("Stage13E 113/113 mapping is required as source of truth")
    if len(blockers) != 113 or len({(item["source_file"], item["source_line"]) for item in blockers}) != 113:
        raise SystemExit(f"expected 113 distinct confirmed blocker plans, found {len(blockers)}")
    if len({item["blocker_id"] for item in blockers}) != 113:
        raise SystemExit("canonical blocker IDs are not unique")
    if len(bridges) != 15 or len(nonmainline) != 6:
        raise SystemExit(f"bridge/non-mainline separation drifted: {len(bridges)}/{len(nonmainline)}")
    required = (
        "blocker_id", "current_owner", "native_owner", "source_file", "symbol", "dependency_edges",
        "upstream_dependencies", "downstream_unlocks", "migration_action", "safe_removal_precondition",
        "validation_gate", "rollback_condition", "risk_level", "freeze_gate", "seal_gate",
    )
    for item in blockers:
        missing = [field for field in required if field not in item or item[field] in (None, "")]
        if missing:
            raise SystemExit(f"{item['blocker_id']} missing plan fields: {missing}")
        if not item["safe_removal_precondition"] or not item["evidence_source"]:
            raise SystemExit(f"{item['blocker_id']} lacks safe-removal/evidence backing")


def main() -> int:
    inputs = [
        STAGE11B, STAGE11B_SUMMARY, STAGE12, STAGE12_SUMMARY,
        STAGE13A, STAGE13A_SUMMARY, STAGE13B, STAGE13B_SUMMARY,
        STAGE13C, STAGE13C_SUMMARY, STAGE13D, STAGE13D_SUMMARY,
        STAGE13E, STAGE13E_SUMMARY,
    ]
    loaded = {path: load(path) for path in inputs}
    stage12 = loaded[STAGE12]
    stage13e = loaded[STAGE13E]
    payloads = {stage: loaded[path] for stage, path, _ in STAGE_SOURCES}
    stage12_map = stage12_confirmed(stage12)
    merged = merge_stage_records(payloads)
    if set(merged) != set(stage12_map):
        missing = sorted(set(stage12_map) - set(merged))
        extra = sorted(set(merged) - set(stage12_map))
        raise SystemExit(f"Stage13/Stage12 mapping mismatch; missing={missing}, extra={extra}")

    blockers = [migration_record(key, merged[key], stage12_map[key]) for key in sorted(merged)]
    bridges = [ancillary_record(index, item, "compatibility_bridge") for index, item in enumerate(sorted(stage12.get("compatibility_bridge", []), key=lambda x: (str(x.get("source_file")), int(x.get("source_line") or 0))), 1)]
    nonmainline = [ancillary_record(index, item, "non_mainline_observability") for index, item in enumerate(sorted(stage12.get("non_mainline_issue", []), key=lambda x: (str(x.get("source_file")), int(x.get("source_line") or 0))), 1)]
    validate(blockers, stage13e, bridges, nonmainline)

    domain_counts = Counter(domain for item in blockers for domain in item["migration_domains"])
    domain_counts["compatibility_bridge"] = len(bridges)
    domain_counts["non_mainline_observability"] = len(nonmainline)
    all_domains = (
        "authority_context", "planner_goal_overlay", "scheduler", "taskrunner", "stepexecutor",
        "repairchain", "lineage", "runtime_session", "compatibility_bridge", "non_mainline_observability",
    )
    domain_counts_ordered = {domain: domain_counts[domain] for domain in all_domains}
    waves = [wave_definition(number, blockers, bridges, nonmainline) for number in range(11)]
    direct_calls = scheduler_direct_calls()

    authority_ids = [item["blocker_id"] for item in blockers if "authority_context" in item["migration_domains"] or any("authority" in edge["relationship"] for edge in item["dependency_edges"])]
    lineage_ids = [item["blocker_id"] for item in blockers if "lineage" in item["migration_domains"]]
    session_ids = [item["blocker_id"] for item in blockers if "runtime_session" in item["migration_domains"]]
    repair_items = [item for item in blockers if "repairchain" in item["migration_domains"]]
    repair_groups = defaultdict(list)
    for item in repair_items:
        source_records = merged[(item["source_file"], item["source_line"])]["sources"]
        labels = set(label for source in source_records for label in source["record"].get("ownership_buckets", []))
        if "duplicate_repair" in labels:
            repair_groups["duplicate_repair"].append(item["blocker_id"])
        if "retry_chain" in labels:
            repair_groups["retry_chain"].append(item["blocker_id"])
        if "recovery_chain" in labels or not labels:
            repair_groups["recovery_chain"].append(item["blocker_id"])

    freeze_blockers = {
        "all_confirmed_blockers": [item["blocker_id"] for item in blockers],
        "critical_suite_blockers": {
            "count": int(VALIDATION_RESULTS.get("pytest", {}).get("failed") or 0),
            "failures": VALIDATION_RESULTS.get("pytest", {}).get("failures", []),
        },
        "direct_stepexecutor_call_seals": direct_calls,
        "authority_propagation_blockers": sorted(set(authority_ids)),
        "goal_lineage_integrity_blockers": lineage_ids,
        "runtime_session_blockers": session_ids,
        "repair_chain_blocker_groups": {
            "all": [item["blocker_id"] for item in repair_items],
            "recovery_chain": sorted(repair_groups["recovery_chain"]),
            "retry_chain": sorted(repair_groups["retry_chain"]),
            "duplicate_repair": sorted(repair_groups["duplicate_repair"]),
        },
    }
    seal_ids = [item["blocker_id"] for item in blockers] + [item["tracking_id"] for item in bridges + nonmainline]
    seal_blockers = {
        "all_actionable_records": seal_ids,
        "runtime_ownership_drift": {
            "condition": "No class-level replacement, direct execution ownership, or owner endpoint drift may reappear after freeze.",
            "evidence": ["113 blocker freeze records", "scheduler direct StepExecutor call scan", "ownership suites"],
        },
        "evidence_graph_drift": {
            "condition": "Source symbols, native owners, dependency edges, and validation evidence hashes remain stable from freeze through seal.",
            "evidence": [relative(STAGE13E), relative(OUTPUT)],
        },
        "compatibility_bridge_residue": [item["tracking_id"] for item in bridges],
        "non_mainline_observability_residue": [item["tracking_id"] for item in nonmainline],
    }
    risk_domain_counts = Counter(
        domain
        for item in blockers if item["risk_level"] == "critical"
        for domain in item["migration_domains"]
        if domain not in {"lineage", "runtime_session"}
    )
    highest_risk = [domain for domain, _ in sorted(risk_domain_counts.items(), key=lambda pair: (-pair[1], pair[0]))]

    payload = {
        "stage": "AER Ownership Migration Plan Stage14",
        "scope": "migration_plan_only",
        "source_of_truth": {"artifact": relative(STAGE13E), "mapping_status": "113 / 113 mapped"},
        "production_runtime_modified": False,
        "tests_modified": False,
        "blockers_fixed": False,
        "inputs": [relative(path) for path in inputs],
        "total_confirmed_blockers_planned": len(blockers),
        "migration_domain_counts": domain_counts_ordered,
        "blocker_migration_plan": blockers,
        "migration_graph": {
            "nodes": [item["blocker_id"] for item in blockers],
            "dependency_edges": [dict(edge, blocker_id=item["blocker_id"]) for item in blockers for edge in item["dependency_edges"]],
            "wave_edges": [{"from": f"wave_{number}", "to": f"wave_{number + 1}", "relationship": "cannot_start_until_previous_complete"} for number in range(10)],
        },
        "migration_waves": waves,
        "freeze_blockers": freeze_blockers,
        "seal_blockers": seal_blockers,
        "compatibility_bridges": bridges,
        "non_mainline_issues": nonmainline,
        "validation_results": VALIDATION_RESULTS,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "stage": "AER Ownership Migration Plan Stage14",
        "total_confirmed_blockers_planned": len(blockers),
        "migration_waves_count": len(waves),
        "freeze_blockers_count": len(freeze_blockers["all_confirmed_blockers"]),
        "seal_blockers_count": len(seal_blockers["all_actionable_records"]),
        "critical_suite_blockers_count": freeze_blockers["critical_suite_blockers"]["count"],
        "direct_stepexecutor_call_seal_count": len(direct_calls),
        "compatibility_bridge_count": len(bridges),
        "non_mainline_issue_count": len(nonmainline),
        "migration_domain_counts": domain_counts_ordered,
        "risk_counts": dict(sorted(Counter(item["risk_level"] for item in blockers).items())),
        "highest_risk_domains": highest_risk,
        "first_executable_migration_wave": "Wave 1: authority context migration (after Wave 0 evidence and invariant lock)",
        "validation_results": VALIDATION_RESULTS,
        "production_runtime_touched": False,
        "tests_touched": False,
        "blockers_fixed": False,
        "deterministic_output": True,
        "outputs": {"plan": relative(OUTPUT), "summary": relative(SUMMARY), "report": relative(REPORT)},
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(payload, summary)

    print(f"total_confirmed_blockers_planned: {len(blockers)}")
    print(f"migration_waves_count: {len(waves)}")
    print(f"freeze_blockers_count: {len(freeze_blockers['all_confirmed_blockers'])}")
    print(f"seal_blockers_count: {len(seal_blockers['all_actionable_records'])}")
    print(f"direct_stepexecutor_call_seal_count: {len(direct_calls)}")
    print("production_runtime_touched: false")
    print("tests_touched: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
