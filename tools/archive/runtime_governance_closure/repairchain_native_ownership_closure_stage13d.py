from __future__ import annotations

import ast
import json
import textwrap
from collections import Counter
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
OUTPUT = OUT_DIR / "repairchain_native_ownership_closure_stage13d.json"
SUMMARY = OUT_DIR / "repairchain_native_ownership_closure_stage13d_summary.json"
REPORT = OUT_DIR / "repairchain_native_ownership_closure_stage13d_report.md"

CLASSIFICATIONS = ("confirmed_blocker", "compatibility_bridge", "false_positive", "non_mainline_issue")
BUCKETS = (
    "repair_execution",
    "duplicate_repair",
    "recovery_chain",
    "retry_chain",
    "repair_authority",
    "repair_session",
    "repair_lineage",
    "repair_step_executor_dependency",
    "compatibility_bridge",
    "non_mainline_issue",
)
EXPECTED_TOTAL = 33
EXPECTED_CONFIRMED = 26

VALIDATION_RESULTS: dict[str, Any] = {
    "observed_on": "2026-06-21",
    "generator": {"status": "pass", "passed": 1, "failed": 0},
    "compileall": {"status": "pass", "passed": 1, "failed": 0},
    "repair_chain_suites": {
        "status": "fail", "passed": 37, "failed": 31, "duration_seconds": 372.81,
        "failure_summary": "30 repair runtime expectations observe blocked where retrying was expected; one native autonomous repair handler returned ok=false.",
    },
    "ownership_suites": {
        "status": "fail", "passed": 69, "failed": 2, "subtests_passed": 7, "duration_seconds": 27.05,
        "failures": [
            "tests/test_scheduler_runtime_ownership_closure.py::test_scheduler_constructs_one_endpoint_and_one_delegation_boundary",
            "tests/test_runtime_status_ownership_inventory.py::test_runtime_status_ownership_inventory_is_explicit",
        ],
    },
    "runtime_blocker_suites": {"status": "pass", "passed": 8, "failed": 0, "duration_seconds": 1.38},
    "total_test_passed": 114,
    "total_test_failed": 33,
    "failures_fixed": False,
}

CLOSURE_ORDER = (
    {"order": 1, "node": "authority", "blocked_by": ["authority_contract"], "unlocks": ["execution"]},
    {"order": 2, "node": "execution", "blocked_by": ["authority"], "unlocks": ["lineage"]},
    {"order": 3, "node": "lineage", "blocked_by": ["execution", "goal_lineage_contract"], "unlocks": ["runtime_session"]},
    {"order": 4, "node": "runtime_session", "blocked_by": ["lineage", "runtime_session_ownership"], "unlocks": ["recovery"]},
    {"order": 5, "node": "recovery", "blocked_by": ["runtime_session", "step_executor_contract"], "unlocks": ["retry"]},
    {"order": 6, "node": "retry", "blocked_by": ["recovery", "scheduler_contract"], "unlocks": ["duplicate_repair"]},
    {"order": 7, "node": "duplicate_repair", "blocked_by": ["retry", "scheduler_queue_ownership"], "unlocks": ["freeze_readiness"]},
)

# This table is an explicit ownership contract, not a token-scoring heuristic. Source
# and AST evidence are attached separately to every generated claim.
SYMBOL_RULES: dict[str, dict[str, Any]] = {
    "StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES": {
        "buckets": ["repair_execution", "recovery_chain", "repair_step_executor_dependency"],
        "boundaries": ["execution", "repair"],
        "owner": "core.runtime.step_executor.StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES (native definition)",
    },
    "StepExecutor.CODE_CHAIN_WORKFLOW_STEP_TYPES": {
        "buckets": ["repair_execution", "recovery_chain", "repair_step_executor_dependency"],
        "boundaries": ["execution", "repair"],
        "owner": "core.runtime.step_executor.StepExecutor.CODE_CHAIN_WORKFLOW_STEP_TYPES (native definition)",
    },
    "StepExecutor._handle_autonomous_repair_chain_step": {
        "buckets": ["repair_execution", "recovery_chain", "repair_step_executor_dependency", "repair_session", "repair_lineage"],
        "boundaries": ["execution", "repair", "lineage", "runtime_session"],
        "owner": "core.runtime.step_executor.StepExecutor._handle_autonomous_repair_chain_step (native definition)",
    },
    "TaskRunner.SIDE_EFFECT_STEP_TYPES": {
        "buckets": ["repair_execution", "recovery_chain"],
        "boundaries": ["execution", "repair"],
        "owner": "core.runtime.task_runner.TaskRunner.SIDE_EFFECT_STEP_TYPES (native definition)",
    },
    "TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES": {
        "buckets": ["repair_execution", "recovery_chain"],
        "boundaries": ["execution", "repair"],
        "owner": "core.runtime.task_runner.TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES (native definition)",
    },
    "TaskRunner._zero_v800_build_observation": {
        "buckets": ["recovery_chain", "repair_session", "repair_lineage"],
        "boundaries": ["repair", "lineage", "runtime_session"],
        "owner": "core.runtime.task_runner.TaskRunner._zero_v800_build_observation (native definition)",
    },
    "TaskRunner._zero_v800_decide_from_observation": {
        "buckets": ["repair_authority", "recovery_chain", "retry_chain", "repair_lineage"],
        "boundaries": ["authority", "repair", "lineage"],
        "owner": "core.runtime.task_runner.TaskRunner._zero_v800_decide_from_observation (native definition)",
    },
    "TaskRunner._zero_v800_last_step_type": {
        "buckets": ["recovery_chain", "retry_chain", "repair_session", "repair_lineage"],
        "boundaries": ["repair", "lineage", "runtime_session"],
        "owner": "core.runtime.task_runner.TaskRunner._zero_v800_last_step_type (native definition)",
    },
    "TaskRunner._zero_v800_represents_failed_step_observation": {
        "buckets": ["repair_authority", "recovery_chain", "retry_chain"],
        "boundaries": ["authority", "repair"],
        "owner": "core.runtime.task_runner.TaskRunner._zero_v800_represents_failed_step_observation (native definition)",
    },
    "TaskRunner._run_one_step": {
        "buckets": ["repair_execution", "repair_authority", "recovery_chain", "retry_chain", "repair_session", "repair_lineage"],
        "boundaries": ["execution", "authority", "repair", "lineage", "runtime_session"],
        "owner": "core.runtime.task_runner.TaskRunner._run_one_step (native definition)",
    },
    "Scheduler._is_repairable_failure": {
        "buckets": ["repair_authority", "recovery_chain", "retry_chain"],
        "boundaries": ["authority", "repair"],
        "owner": "core.tasks.scheduler.Scheduler._is_repairable_failure (native definition)",
    },
    "Scheduler.REPAIRABLE_STEP_TYPES": {
        "buckets": ["repair_authority", "recovery_chain", "retry_chain"],
        "boundaries": ["authority", "repair"],
        "owner": "core.tasks.scheduler.Scheduler.REPAIRABLE_STEP_TYPES (native definition)",
    },
    "Scheduler._find_active_duplicate_repair_task": {
        "buckets": ["duplicate_repair", "repair_authority", "recovery_chain", "retry_chain", "repair_session", "repair_lineage"],
        "boundaries": ["authority", "repair", "lineage", "runtime_session"],
        "owner": "core.tasks.scheduler.Scheduler._find_active_duplicate_repair_task (native definition)",
    },
    "Scheduler.SCHEDULER_BUILD": {
        "buckets": ["recovery_chain"],
        "boundaries": [],
        "owner": "core.tasks.scheduler.Scheduler.SCHEDULER_BUILD (non-behavioral metadata)",
    },
    "Scheduler.RETRYING_REPAIR_BRIDGE_VERSION": {
        "buckets": ["retry_chain"],
        "boundaries": [],
        "owner": "core.tasks.scheduler.Scheduler.RETRYING_REPAIR_BRIDGE_VERSION (non-behavioral metadata)",
    },
    "Scheduler._attach_autonomous_repair_chain_summary": {
        "buckets": ["recovery_chain", "repair_session", "repair_lineage", "non_mainline_issue"],
        "boundaries": ["repair", "lineage", "runtime_session"],
        "owner": "core.tasks.scheduler.Scheduler._attach_autonomous_repair_chain_summary (native observability boundary)",
    },
}

BOUNDARY_OWNERS = {
    "repair": "RuntimeNativeAutonomousRepairChain / scheduler repair handoff",
    "authority": "Scheduler repair eligibility and TaskRunner repair decision endpoints",
    "execution": "TaskRunner and StepExecutor native repair execution endpoints",
    "lineage": "repair-chain identity and goal-lineage contract",
    "runtime_session": "runtime-session repair continuation contract",
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


def repair_items(stage12: dict[str, Any]) -> list[dict[str, Any]]:
    result = list(stage12.get("confirmed_blockers_by_domain", {}).get("repair_chain", []))
    for classification in CLASSIFICATIONS[1:]:
        result.extend(item for item in stage12.get(classification, []) if item.get("domain") == "repair_chain")
    return sorted(result, key=lambda item: (str(item.get("source_file")), int(item.get("source_line") or 0)))


def assigned_name(expression: str) -> str:
    if "=" not in expression:
        return ""
    right = expression.split("=", 1)[1].strip()
    return right if right.isidentifier() else ""


def source_facts(path_text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    source = (ROOT / path_text).read_text(encoding="utf-8")
    tree = ast.parse(source)
    bodies: dict[str, str] = {}
    calls: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = ast.get_source_segment(source, node) or ""
        bodies[node.name] = segment
        called: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if isinstance(child.func, ast.Name):
                called.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                called.add(child.func.attr)
        calls[node.name] = sorted(called)
    return bodies, calls


def reachable_calls(name: str, call_map: dict[str, list[str]], limit: int = 3) -> list[str]:
    seen: set[str] = set()
    frontier = [(name, 0)]
    while frontier:
        current, depth = frontier.pop(0)
        if current in seen or depth > limit:
            continue
        seen.add(current)
        for called in call_map.get(current, []):
            if called in call_map:
                frontier.append((called, depth + 1))
    seen.discard(name)
    return sorted(seen)


def boundary(name: str, active: bool, helper: str, source_file: str, source_line: int) -> dict[str, Any]:
    evidence = [f"explicit_symbol_contract:{name}", f"source_assignment:{source_file}:{source_line}"] if active else []
    if active and helper:
        evidence.append(f"assignment_rhs:{helper}")
    return {"active": active, "owner": BOUNDARY_OWNERS[name], "evidence": evidence}


def dependency_edges(rule: dict[str, Any]) -> list[dict[str, str]]:
    active = set(rule["boundaries"])
    edges: list[dict[str, str]] = []
    for source, target, relationship, key in (
        ("authority_contract", "repair_chain", "repair_authority_dependency", "authority"),
        ("taskrunner_contract", "repair_chain", "repair_execution_dependency", "execution"),
        ("goal_lineage_contract", "repair_chain", "repair_lineage_dependency", "lineage"),
        ("runtime_session_ownership", "repair_chain", "repair_session_dependency", "runtime_session"),
    ):
        if key in active:
            edges.append({"from": source, "to": target, "relationship": relationship})
    if "repair_step_executor_dependency" in rule["buckets"]:
        edges.append({"from": "step_executor_contract", "to": "repair_chain", "relationship": "repair_step_executor_dependency"})
    if "retry_chain" in rule["buckets"]:
        edges.append({"from": "recovery_chain", "to": "retry_chain", "relationship": "continuation_dependency"})
    if "duplicate_repair" in rule["buckets"]:
        edges.append({"from": "retry_chain", "to": "duplicate_repair", "relationship": "duplicate_suppression_dependency"})
    return edges


def unlock_targets(rule: dict[str, Any]) -> list[str]:
    targets = []
    buckets = set(rule["buckets"])
    if buckets & {"repair_authority", "retry_chain", "duplicate_repair"}:
        targets.append("scheduler")
    if buckets & {"repair_execution", "recovery_chain", "repair_session", "repair_lineage"}:
        targets.append("taskrunner")
    if "repair_step_executor_dependency" in buckets:
        targets.append("stepexecutor")
    if buckets & {"recovery_chain", "retry_chain", "duplicate_repair"}:
        targets.append("repair")
    return targets


def make_record(index: int, item: dict[str, Any], facts: dict[str, tuple[dict[str, str], dict[str, list[str]]]]) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "")
    if symbol not in SYMBOL_RULES:
        raise SystemExit(f"no explicit RepairChain ownership rule for {symbol}")
    rule = SYMBOL_RULES[symbol]
    source_file = str(item.get("source_file") or "")
    source_line = int(item.get("source_line") or 0)
    helper = assigned_name(str(item.get("expression") or ""))
    bodies, call_map = facts[source_file]
    helper_body = textwrap.dedent(bodies.get(helper, ""))
    calls = call_map.get(helper, []) if helper else []
    reachable = reachable_calls(helper, call_map) if helper else []
    classification = str(item.get("classification") or "")
    buckets = list(rule["buckets"])
    if classification == "compatibility_bridge" and "compatibility_bridge" not in buckets:
        buckets.append("compatibility_bridge")
    if classification == "non_mainline_issue" and "non_mainline_issue" not in buckets:
        buckets.append("non_mainline_issue")
    stage12_precondition = str(item.get("safe_removal_precondition") or "").strip()
    native_condition = {
        "false_positive": "Retain as non-behavioral metadata; no executable blocker removal is required.",
        "non_mainline_issue": "A native observability owner and independent non-mainline validation exist before retiring this assignment.",
        "compatibility_bridge": "All bridge consumers use the canonical native RepairChain result contract before bridge retirement.",
    }.get(classification, "Native repair authority, execution, identity, session, recovery, retry, and duplicate suppression endpoints pass their ownership suites without this assignment.")
    source_evidence = [
        f"{relative(STAGE12)}#repair_chain",
        f"{source_file}:{source_line}",
        f"explicit_symbol_contract:{symbol}",
        f"assignment_rhs:{helper}" if helper else "class_state_or_metadata_assignment",
    ]
    if helper_body:
        source_evidence.append(f"ast_function:{source_file}::{helper}")
    return {
        "blocker_id": f"S13D-RC-{index:03d}",
        "source_file": source_file,
        "source_line": source_line,
        "symbol": symbol,
        "validated_classification": classification,
        "replacement_kind": str(item.get("replacement_kind") or ""),
        "replacement_target": str(item.get("replacement_target") or ""),
        "current_owner": f"class-level assignment in {source_file}:{source_line}",
        "expected_native_owner": rule["owner"],
        "ownership_buckets": buckets,
        "repair_boundary": boundary("repair", "repair" in rule["boundaries"], helper, source_file, source_line),
        "authority_boundary": boundary("authority", "authority" in rule["boundaries"], helper, source_file, source_line),
        "execution_boundary": boundary("execution", "execution" in rule["boundaries"], helper, source_file, source_line),
        "lineage_boundary": boundary("lineage", "lineage" in rule["boundaries"], helper, source_file, source_line),
        "runtime_session_boundary": boundary("runtime_session", "runtime_session" in rule["boundaries"], helper, source_file, source_line),
        "why_blocker": str(item.get("why_blocker") or ""),
        "safe_removal_precondition": f"{stage12_precondition} Stage13D condition: {native_condition}",
        "dependency_edges": [] if classification == "false_positive" else dependency_edges(rule),
        "unlock_targets": [] if classification == "false_positive" else unlock_targets(rule),
        "call_graph": {
            "assignment_rhs": helper or None,
            "direct_calls": calls,
            "reachable_local_helpers": reachable,
            "source_function_found": bool(helper_body),
        },
        "evidence_source": source_evidence,
    }


def count_map(keys: Iterable[str], values: Iterable[str]) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts[key] for key in keys}


def confirmed_keys(payload: dict[str, Any], item_key: str) -> set[tuple[str, int]]:
    return {
        (str(item.get("source_file")), int(item.get("source_line") or 0))
        for item in payload.get(item_key, [])
        if item.get("validated_classification") == "confirmed_blocker"
    }


def all_confirmed_stage12(stage12: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for domain, items in stage12.get("confirmed_blockers_by_domain", {}).items():
        for item in items:
            copied = dict(item)
            copied["domain"] = domain
            result[(str(item.get("source_file")), int(item.get("source_line") or 0))] = copied
    return result


def unlock_graph(records: list[dict[str, Any]], stage13a: dict[str, Any], stage13b: dict[str, Any], stage13c: dict[str, Any]) -> dict[str, Any]:
    confirmed = [record for record in records if record["validated_classification"] == "confirmed_blocker"]
    result: dict[str, Any] = {}
    prior = {
        "scheduler": (stage13a, "scheduler_items", "repair_chain"),
        "taskrunner": (stage13b, "taskrunner_items", "repair_chain_dependencies"),
        "stepexecutor": (stage13c, "stepexecutor_items", "repair_chain_dependency"),
    }
    for name, (payload, key, marker) in prior.items():
        dependencies = []
        for item in payload.get(key, []):
            haystack = json.dumps(item, sort_keys=True)
            if item.get("validated_classification") == "confirmed_blocker" and marker in haystack:
                dependencies.append({
                    "blocker_id": item.get("blocker_id"),
                    "symbol": item.get("symbol"),
                    "relationship": "unlocked_after_repairchain_closure",
                    "evidence_source": f"{relative({'scheduler': STAGE13A, 'taskrunner': STAGE13B, 'stepexecutor': STAGE13C}[name])}#{item.get('blocker_id')}",
                })
        result[name] = dependencies
    result["repair"] = [
        {"blocker_id": record["blocker_id"], "symbol": record["symbol"], "unlock_targets": record["unlock_targets"]}
        for record in confirmed
    ]
    return result


def validate(records: list[dict[str, Any]], stage12: dict[str, Any]) -> None:
    if len(records) != EXPECTED_TOTAL:
        raise SystemExit(f"expected {EXPECTED_TOTAL} RepairChain items, found {len(records)}")
    confirmed = sum(record["validated_classification"] == "confirmed_blocker" for record in records)
    if confirmed != EXPECTED_CONFIRMED:
        raise SystemExit(f"expected {EXPECTED_CONFIRMED} confirmed RepairChain blockers, found {confirmed}")
    if len(stage12.get("confirmed_blockers_by_domain", {}).get("repair_chain", [])) != EXPECTED_CONFIRMED:
        raise SystemExit("Stage12 RepairChain confirmed count drifted")
    required = (
        "blocker_id", "source_file", "symbol", "validated_classification", "replacement_kind",
        "replacement_target", "current_owner", "expected_native_owner", "repair_boundary",
        "authority_boundary", "execution_boundary", "lineage_boundary", "runtime_session_boundary",
        "why_blocker", "safe_removal_precondition", "dependency_edges", "unlock_targets", "evidence_source",
    )
    for record in records:
        missing = [field for field in required if field not in record or record[field] in (None, "")]
        if missing:
            raise SystemExit(f"{record['blocker_id']} missing fields: {missing}")
        if not record["evidence_source"] or not record["call_graph"]:
            raise SystemExit(f"{record['blocker_id']} lacks source/call graph evidence")


def write_report(payload: dict[str, Any], summary: dict[str, Any]) -> None:
    lines = [
        "# RepairChain Native Ownership Closure — Stage13D", "",
        "Discovery and ownership mapping only. No blocker was fixed, no ownership was migrated, and no production runtime file was modified.", "",
        "## Summary", "",
        f"- Total repair items: {summary['total_repair_items']}",
        f"- Confirmed blockers: {summary['confirmed_blockers']}",
        f"- Authority dependencies: {summary['authority_dependencies']}",
        f"- Lineage dependencies: {summary['lineage_dependencies']}",
        f"- Runtime-session dependencies: {summary['runtime_session_dependencies']}",
        f"- Recovery-chain dependencies: {summary['recovery_chain_dependencies']}",
        f"- Retry-chain dependencies: {summary['retry_chain_dependencies']}",
        f"- Duplicate-repair dependencies: {summary['duplicate_repair_dependencies']}",
        f"- Unresolved ambiguities: {summary['unresolved_ambiguities']}",
        f"- Ownership mapping: {summary['aer_closure_summary']['ownership_mapping_percent']}%",
        f"- Ownership closure: {summary['aer_closure_summary']['ownership_closure_percent']}%",
        f"- Freeze readiness: {summary['aer_closure_summary']['freeze_readiness_percent']}%",
        "- Production runtime touched: false", "",
        "## Ownership buckets", "",
    ]
    for bucket, count in summary["bucket_counts"].items():
        lines.append(f"- `{bucket}`: {count}")
    lines.extend(["", "## Dependency graph", ""])
    graph = payload["dependency_graph"]
    for key in ("repair_roots", "repair_owners", "repair_authority_endpoints", "repair_execution_endpoints", "repair_continuation_paths", "repair_resume_paths"):
        lines.append(f"### {key.replace('_', ' ').title()}")
        lines.append("")
        values = graph[key]
        if values:
            lines.extend(f"- `{value}`" for value in values)
        else:
            lines.append("- None")
        lines.append("")
    lines.extend(["## Closure order", ""])
    for entry in summary["closure_order"]:
        lines.append(f"{entry['order']}. `{entry['node']}` — blocked by {', '.join(entry['blocked_by']) or 'none'}; unlocks {', '.join(entry['unlocks']) or 'none'}")
    lines.extend(["", "## Unlock graph", ""])
    for target, count in summary["unlock_counts"].items():
        lines.append(f"- `{target}`: {count}")
    lines.extend(["", "## Ownership leak map", ""])
    leak = payload["ownership_leak_map"]
    lines.extend([
        f"- Current owners: {len(leak['current_owners'])}",
        f"- Expected owners: {len(leak['expected_owners'])}",
        f"- Ownership leak locations: {len(leak['ownership_leak_locations'])}",
        f"- Repair-native owner endpoints: {len(leak['repair_native_owner_endpoints'])}", "",
        "## RepairChain inventory", "",
    ])
    for record in payload["repairchain_items"]:
        lines.extend([
            f"- `{record['blocker_id']}` — `{record['source_file']}:{record['source_line']}` — `{record['symbol']}`",
            f"  - Classification: `{record['validated_classification']}`",
            f"  - Buckets: {', '.join(f'`{x}`' for x in record['ownership_buckets'])}",
            f"  - Current owner: {record['current_owner']}",
            f"  - Expected native owner: {record['expected_native_owner']}",
            f"  - Why blocker: {record['why_blocker']}",
            f"  - Safe removal precondition: {record['safe_removal_precondition']}",
            f"  - Unlock targets: {', '.join(record['unlock_targets']) or 'none'}",
        ])
    lines.extend(["", "## Non-Mainline Issue Report", ""])
    for record in payload["non_mainline_issues"]:
        lines.append(f"- `{record['blocker_id']}` — `{record['source_file']}:{record['source_line']}` — `{record['symbol']}`; retained separately as `{record['validated_classification']}`.")
    if not payload["non_mainline_issues"]:
        lines.append("- No RepairChain non-mainline issues found.")
    aer = summary["aer_closure_summary"]
    lines.extend([
        "", "## AER Closure Summary", "",
        f"- Total mapped blockers: {aer['total_mapped_blockers']}",
        f"- Remaining unmapped blockers: {aer['remaining_unmapped_blockers']}",
        f"- Ownership completion: {aer['ownership_mapping_percent']}%",
        f"- Freeze blockers: {aer['freeze_blockers']}",
        f"- Seal blockers: {aer['seal_blockers']}",
        f"- Critical suite blockers: {aer['critical_suite_blockers']}",
        f"- Remaining native ownership leaks: {aer['remaining_native_ownership_leaks']}",
        "", "## AER Status After Stage13D", "",
        f"- Scheduler impact: {aer['scheduler_impact']}",
        f"- TaskRunner impact: {aer['taskrunner_impact']}",
        f"- StepExecutor impact: {aer['stepexecutor_impact']}",
        f"- RepairChain impact: {aer['repairchain_impact']}",
        f"- Ownership Mapping: {aer['ownership_mapping_percent']}%",
        f"- Ownership Closure: {aer['ownership_closure_percent']}%",
        f"- Freeze Readiness: {aer['freeze_readiness_percent']}%",
        f"- Remaining stages before AER Seal: {aer['remaining_stages_before_aer_seal']}",
        "", "## Validation", "",
        f"- Generator: {summary['validation_results']['generator']['status']}",
        f"- Compileall: {summary['validation_results']['compileall']['status']}",
        f"- Repair-chain suites: {summary['validation_results']['repair_chain_suites']['passed']} passed, {summary['validation_results']['repair_chain_suites']['failed']} failed",
        f"- Ownership suites: {summary['validation_results']['ownership_suites']['passed']} passed, {summary['validation_results']['ownership_suites']['failed']} failed, {summary['validation_results']['ownership_suites']['subtests_passed']} subtests passed",
        f"- Runtime blocker suites: {summary['validation_results']['runtime_blocker_suites']['passed']} passed, {summary['validation_results']['runtime_blocker_suites']['failed']} failed",
        f"- Critical suite blockers: {summary['validation_results']['total_test_failed']}",
        "- Failures fixed: false",
        "- Production runtime touched: false", "",
    ])
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    stage11b = load(STAGE11B)
    load(STAGE11B_SUMMARY)
    stage12 = load(STAGE12)
    stage12_summary = load(STAGE12_SUMMARY)
    stage13a = load(STAGE13A)
    load(STAGE13A_SUMMARY)
    stage13b = load(STAGE13B)
    load(STAGE13B_SUMMARY)
    stage13c = load(STAGE13C)
    load(STAGE13C_SUMMARY)

    raw = repair_items(stage12)
    facts = {path: source_facts(path) for path in sorted({str(item["source_file"]) for item in raw})}
    records = [make_record(index, item, facts) for index, item in enumerate(raw, 1)]
    validate(records, stage12)

    classification_counts = count_map(CLASSIFICATIONS, (record["validated_classification"] for record in records))
    bucket_counts = {bucket: sum(bucket in record["ownership_buckets"] for record in records) for bucket in BUCKETS}
    unlocks = unlock_graph(records, stage13a, stage13b, stage13c)

    prior_keys = set().union(
        confirmed_keys(stage13a, "scheduler_items"),
        confirmed_keys(stage13b, "taskrunner_items"),
        confirmed_keys(stage13c, "stepexecutor_items"),
    )
    repair_keys = {
        (record["source_file"], record["source_line"])
        for record in records if record["validated_classification"] == "confirmed_blocker"
    }
    all_confirmed = all_confirmed_stage12(stage12)
    mapped_keys = prior_keys | repair_keys
    remaining = [item for key, item in all_confirmed.items() if key not in mapped_keys]
    total_confirmed = int(stage12_summary.get("classification_counts", {}).get("confirmed_blocker") or len(all_confirmed))
    mapping_percent = round(100.0 * len(mapped_keys) / total_confirmed, 1) if total_confirmed else 0.0

    confirmed_records = [record for record in records if record["validated_classification"] == "confirmed_blocker"]
    repair_roots = sorted({record["symbol"] for record in confirmed_records if "repair_authority" in record["ownership_buckets"]})
    repair_owners = sorted({record["expected_native_owner"] for record in records})
    authority_endpoints = sorted({record["expected_native_owner"] for record in confirmed_records if record["authority_boundary"]["active"]})
    execution_endpoints = sorted({record["expected_native_owner"] for record in confirmed_records if record["execution_boundary"]["active"]})
    continuation_paths = sorted({record["symbol"] for record in confirmed_records if "retry_chain" in record["ownership_buckets"]})
    resume_paths = sorted({record["symbol"] for record in confirmed_records if record["runtime_session_boundary"]["active"]})
    dependency_graph = {
        "repair_roots": repair_roots,
        "repair_owners": repair_owners,
        "repair_authority_endpoints": authority_endpoints,
        "repair_execution_endpoints": execution_endpoints,
        "repair_continuation_paths": continuation_paths,
        "repair_resume_paths": resume_paths,
        "item_dependency_edges": [edge for record in records for edge in record["dependency_edges"]],
        "item_call_graphs": {record["blocker_id"]: record["call_graph"] for record in records},
    }
    leak_map = {
        "current_owners": sorted({record["current_owner"] for record in records}),
        "expected_owners": repair_owners,
        "ownership_leak_locations": sorted({
            f"{record['source_file']}:{record['source_line']}"
            for record in records if record["validated_classification"] != "false_positive"
        }),
        "repair_native_owner_endpoints": sorted({
            record["expected_native_owner"]
            for record in confirmed_records
            if any(record[name]["active"] for name in ("authority_boundary", "execution_boundary", "lineage_boundary", "runtime_session_boundary"))
        }),
    }
    aer = {
        "stage13a_mapped_confirmed": len(confirmed_keys(stage13a, "scheduler_items")),
        "stage13b_mapped_confirmed": len(confirmed_keys(stage13b, "taskrunner_items")),
        "stage13c_mapped_confirmed": len(confirmed_keys(stage13c, "stepexecutor_items")),
        "stage13d_mapped_confirmed": len(repair_keys),
        "stage13d_new_distinct_mappings": len(repair_keys - prior_keys),
        "total_mapped_blockers": len(mapped_keys),
        "remaining_unmapped_blockers": len(remaining),
        "remaining_unmapped_inventory": [
            {"source_file": item.get("source_file"), "source_line": item.get("source_line"), "symbol": item.get("symbol"), "domain": item.get("domain")}
            for item in remaining
        ],
        "ownership_mapping_percent": mapping_percent,
        "ownership_closure_percent": 0.0,
        "freeze_readiness_percent": 0.0,
        "freeze_blockers": total_confirmed,
        "seal_blockers": total_confirmed,
        "critical_suite_blockers": VALIDATION_RESULTS["total_test_failed"],
        "remaining_native_ownership_leaks": total_confirmed,
        "scheduler_impact": f"{len(unlocks['scheduler'])} scheduler dependency paths are mapped to RepairChain closure prerequisites.",
        "taskrunner_impact": f"{len(unlocks['taskrunner'])} TaskRunner dependency paths are mapped to RepairChain closure prerequisites.",
        "stepexecutor_impact": f"{len(unlocks['stepexecutor'])} StepExecutor dependency paths are mapped; five RepairChain blockers overlap Stage13C ownership evidence.",
        "repairchain_impact": f"All {len(records)} RepairChain items are inventoried; {len(repair_keys)} are confirmed blockers and {len(repair_keys - prior_keys)} add distinct AER mappings.",
        "remaining_stages_before_aer_seal": "minimum 9 gated stages: remaining authority/planner mapping, seven RepairChain closure nodes, and freeze/seal validation",
    }
    payload = {
        "stage": "RepairChain Native Ownership Closure Stage13D",
        "scope": "discovery_and_ownership_mapping_only",
        "production_runtime_modified": False,
        "inputs": [relative(path) for path in (STAGE11B, STAGE11B_SUMMARY, STAGE12, STAGE12_SUMMARY, STAGE13A, STAGE13A_SUMMARY, STAGE13B, STAGE13B_SUMMARY, STAGE13C, STAGE13C_SUMMARY)],
        "stage11b_validated_blocker_count": len(stage11b.get("validated_blockers", [])),
        "total_repair_items": len(records),
        "classification_counts": classification_counts,
        "bucket_counts": bucket_counts,
        "repairchain_items": records,
        "ownership_buckets": {bucket: [record["blocker_id"] for record in records if bucket in record["ownership_buckets"]] for bucket in BUCKETS},
        "dependency_graph": dependency_graph,
        "unlock_graph": unlocks,
        "closure_order": list(CLOSURE_ORDER),
        "ownership_leak_map": leak_map,
        "non_mainline_issues": [record for record in records if record["validated_classification"] == "non_mainline_issue"],
        "unresolved_ambiguities": [],
        "aer_closure_summary": aer,
        "validation_results": VALIDATION_RESULTS,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "stage": "RepairChain Native Ownership Closure Stage13D",
        "total_repair_items": len(records),
        "confirmed_blockers": classification_counts["confirmed_blocker"],
        "compatibility_bridge_count": classification_counts["compatibility_bridge"],
        "false_positive_count": classification_counts["false_positive"],
        "non_mainline_issue_count": classification_counts["non_mainline_issue"],
        "bucket_counts": bucket_counts,
        "authority_dependencies": sum(record["authority_boundary"]["active"] for record in confirmed_records),
        "lineage_dependencies": sum(record["lineage_boundary"]["active"] for record in confirmed_records),
        "runtime_session_dependencies": sum(record["runtime_session_boundary"]["active"] for record in confirmed_records),
        "recovery_chain_dependencies": sum("recovery_chain" in record["ownership_buckets"] for record in confirmed_records),
        "retry_chain_dependencies": sum("retry_chain" in record["ownership_buckets"] for record in confirmed_records),
        "duplicate_repair_dependencies": sum("duplicate_repair" in record["ownership_buckets"] for record in confirmed_records),
        "unlock_counts": {name: len(items) for name, items in unlocks.items()},
        "closure_order": list(CLOSURE_ORDER),
        "unresolved_ambiguities": 0,
        "aer_closure_summary": aer,
        "validation_results": VALIDATION_RESULTS,
        "production_runtime_touched": False,
        "outputs": {"inventory": relative(OUTPUT), "summary": relative(SUMMARY), "report": relative(REPORT)},
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(payload, summary)

    print(f"total_repair_items: {len(records)}")
    print(f"classification_counts: {classification_counts}")
    print(f"bucket_counts: {bucket_counts}")
    print(f"unlock_counts: {summary['unlock_counts']}")
    print(f"ownership_mapping_percent: {mapping_percent}")
    print("production_runtime_touched: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
