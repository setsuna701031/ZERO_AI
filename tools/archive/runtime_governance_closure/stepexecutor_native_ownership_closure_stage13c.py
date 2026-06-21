from __future__ import annotations

import ast
import json
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
STAGE11B_PATH = OUT_DIR / "runtime_blocker_validation.json"
STAGE11B_SUMMARY_PATH = OUT_DIR / "runtime_blocker_validation_summary.json"
STAGE12_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12.json"
STAGE12_SUMMARY_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12_summary.json"
STAGE13A_PATH = OUT_DIR / "scheduler_native_ownership_closure_stage13a.json"
STAGE13A_SUMMARY_PATH = OUT_DIR / "scheduler_native_ownership_closure_stage13a_summary.json"
STAGE13B_PATH = OUT_DIR / "taskrunner_native_ownership_closure_stage13b.json"
STAGE13B_SUMMARY_PATH = OUT_DIR / "taskrunner_native_ownership_closure_stage13b_summary.json"
OUTPUT_PATH = OUT_DIR / "stepexecutor_native_ownership_closure_stage13c.json"
SUMMARY_PATH = OUT_DIR / "stepexecutor_native_ownership_closure_stage13c_summary.json"
REPORT_PATH = OUT_DIR / "stepexecutor_native_ownership_closure_stage13c_report.md"

OWNER_PREFIX = "core.runtime.step_executor.StepExecutor"
EXPECTED_TOTAL = 30
EXPECTED_CONFIRMED = 26
CLASSIFICATIONS = (
    "confirmed_blocker",
    "compatibility_bridge",
    "false_positive",
    "non_mainline_issue",
)
BUCKETS = (
    "execution_ownership",
    "authority_propagation",
    "direct_overlay",
    "fallback_signature",
    "lineage_dependency",
    "runtime_session_dependency",
    "repair_chain_dependency",
    "compatibility_bridge",
    "non_mainline_issue",
)

CLOSURE_ORDER = (
    {
        "order": 1,
        "node": "authority_propagation",
        "blocked_by": ["authority_contract"],
        "unlocks": ["execution_ownership"],
    },
    {
        "order": 2,
        "node": "execution_ownership",
        "blocked_by": ["authority_propagation"],
        "unlocks": ["lineage_dependency", "runtime_session_dependency"],
    },
    {
        "order": 3,
        "node": "lineage_dependency",
        "blocked_by": ["execution_ownership", "goal_lineage_contract"],
        "unlocks": ["runtime_session_dependency"],
    },
    {
        "order": 4,
        "node": "runtime_session_dependency",
        "blocked_by": ["lineage_dependency", "runtime_session_ownership"],
        "unlocks": ["fallback_signature"],
    },
    {
        "order": 5,
        "node": "fallback_signature",
        "blocked_by": ["runtime_session_dependency", "taskrunner_contract"],
        "unlocks": ["repair_chain_dependency", "scheduler_contract"],
    },
    {
        "order": 6,
        "node": "repair_chain_dependency",
        "blocked_by": ["fallback_signature", "repair_chain"],
        "unlocks": ["freeze_readiness"],
    },
)

SAFE_PRECONDITIONS = {
    "execution_ownership": "One native StepExecutor.execute_step endpoint and one native handler registry pass execution-boundary ownership suites.",
    "authority_propagation": "Authority context and capability lineage arrive through TaskRunner and are enforced once by the native StepExecutor endpoint.",
    "fallback_signature": "TaskRunner and Scheduler call one canonical StepExecutor signature; TypeError arity fallback chains are no longer required.",
    "lineage_dependency": "Complete goal lineage is validated at the authority boundary and preserved in execution evidence.",
    "runtime_session_dependency": "Runtime-session identity and execution results use one native persistence owner across StepExecutor return paths.",
    "repair_chain_dependency": "Repair handlers, routing sets, and recovery result contracts are native and duplicate-free.",
    "compatibility_bridge": "Adapter payload consumers use the canonical public result contract before bridge retirement.",
    "non_mainline_issue": "A named native owner and independent validation exist for the non-mainline surface.",
}


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required artifact: {relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def all_stage12_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    confirmed_by_domain = payload.get("confirmed_blockers_by_domain", {})
    if not isinstance(confirmed_by_domain, dict):
        raise SystemExit("Stage12 confirmed_blockers_by_domain must be an object")
    for values in confirmed_by_domain.values():
        if isinstance(values, list):
            items.extend(item for item in values if isinstance(item, dict))
    for classification in CLASSIFICATIONS[1:]:
        values = payload.get(classification, [])
        if not isinstance(values, list):
            raise SystemExit(f"Stage12 {classification} must be a list")
        items.extend(item for item in values if isinstance(item, dict))
    selected = [
        item for item in items
        if str(item.get("replacement_target") or "").startswith(OWNER_PREFIX + ".")
        or str(item.get("symbol") or "").startswith("StepExecutor.")
    ]
    return sorted(selected, key=lambda item: (str(item.get("source_file")), int(item.get("source_line") or 0)))


def assigned_function_name(expression: str) -> str:
    if "=" not in expression:
        return ""
    candidate = expression.split("=", 1)[1].strip()
    return candidate if candidate.isidentifier() else ""


def function_sources(path_text: str) -> dict[str, str]:
    source = (ROOT / path_text).read_text(encoding="utf-8")
    tree = ast.parse(source)
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = ast.get_source_segment(source, node)
            if segment:
                result[node.name] = segment
    return result


def function_facts(function_name: str, sources: dict[str, str]) -> dict[str, Any]:
    body = sources.get(function_name, "")
    if not body:
        return {
            "body": "",
            "expanded_body": "",
            "predecessor_references": [],
            "called_helpers": [],
            "has_varargs": False,
            "has_typeerror_fallback": False,
        }
    try:
        tree = ast.parse(textwrap.dedent(body))
    except SyntaxError:
        return {
            "body": body,
            "expanded_body": body,
            "predecessor_references": [],
            "called_helpers": [],
            "has_varargs": False,
            "has_typeerror_fallback": False,
        }
    function_node = next(
        (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))),
        None,
    )
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    predecessors = sorted(
        name for name in names
        if "ORIGINAL" in name.upper() or "BASE_EXECUTE" in name.upper() or "BASE_STEP" in name.upper()
    )
    called = sorted({
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in sources
    })
    visited: set[str] = set()

    def expand(name: str) -> list[str]:
        if not name or name in visited or name not in sources:
            return []
        visited.add(name)
        segment = sources[name]
        parts = [segment]
        try:
            subtree = ast.parse(textwrap.dedent(segment))
        except SyntaxError:
            return parts
        nested_calls = {
            node.func.id for node in ast.walk(subtree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in sources
        }
        for called_name in sorted(nested_calls):
            parts.extend(expand(called_name))
        return parts

    expanded_body = "\n".join(expand(function_name))
    return {
        "body": body,
        "expanded_body": expanded_body,
        "predecessor_references": predecessors,
        "called_helpers": sorted(visited - {function_name}),
        "has_varargs": bool(function_node and (function_node.args.vararg or function_node.args.kwarg)),
        "has_typeerror_fallback": "TypeError" in names and "execute_step" in body,
    }


def boundary(active: bool, evidence: list[str], owner: str) -> dict[str, Any]:
    return {"active": active, "owner": owner, "evidence": evidence}


def classify_item(item: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "")
    member = symbol.rsplit(".", 1)[-1]
    domain = str(item.get("domain") or "")
    classification = str(item.get("classification") or "")
    body = str(facts["expanded_body"])
    lowered = body.lower()

    execution = member in {"execute_step", "__init__", "_register_builtin_handlers"}
    authority = domain == "authority_contract" or "authority" in member.lower() or any(
        token in lowered for token in ("authority_context", "execution_authority", "capability")
    )
    lineage = authority or any(token in lowered for token in ("goal_lineage", "root_goal_id", "source_goal_id", "lineage_id"))
    runtime_session = authority or any(token in lowered for token in ("runtime_session", "session_id", "runtime_state"))
    repair = domain == "repair_chain" or "repair" in member.lower()
    fallback = bool(
        facts["has_typeerror_fallback"]
        or "public_abi" in assigned_function_name(str(item.get("expression") or ""))
    )
    direct = str(item.get("expression") or "").lstrip().startswith("StepExecutor.")
    indirect = bool(facts["predecessor_references"])

    buckets: list[str] = []
    if execution:
        buckets.append("execution_ownership")
    if authority:
        buckets.append("authority_propagation")
    if direct:
        buckets.append("direct_overlay")
    if fallback:
        buckets.append("fallback_signature")
    if lineage:
        buckets.append("lineage_dependency")
    if runtime_session:
        buckets.append("runtime_session_dependency")
    if repair:
        buckets.append("repair_chain_dependency")
    if classification == "compatibility_bridge":
        buckets.append("compatibility_bridge")
    if classification == "non_mainline_issue":
        buckets.append("non_mainline_issue")
    return {
        "buckets": buckets,
        "execution": execution,
        "authority": authority,
        "lineage": lineage,
        "runtime_session": runtime_session,
        "repair": repair,
        "fallback": fallback,
        "direct": direct,
        "indirect": indirect,
    }


def primary_precondition(flags: dict[str, Any]) -> str:
    for bucket in (
        "authority_propagation",
        "execution_ownership",
        "lineage_dependency",
        "runtime_session_dependency",
        "fallback_signature",
        "repair_chain_dependency",
        "compatibility_bridge",
        "non_mainline_issue",
    ):
        if bucket in flags["buckets"]:
            return SAFE_PRECONDITIONS[bucket]
    return SAFE_PRECONDITIONS["execution_ownership"]


def dependency_edges(flags: dict[str, Any]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    mapping = (
        ("authority", "authority_contract", "authority_propagation"),
        ("lineage", "goal_lineage_contract", "lineage_dependency"),
        ("runtime_session", "runtime_session_ownership", "runtime_session_dependency"),
        ("repair", "repair_chain", "repair_chain_dependency"),
        ("fallback", "taskrunner_contract", "fallback_signature_dependency"),
    )
    for key, source, relationship in mapping:
        if flags[key]:
            edges.append({"from": source, "to": "step_executor_contract", "relationship": relationship})
    if flags["execution"]:
        edges.extend([
            {"from": "scheduler_contract", "to": "step_executor_contract", "relationship": "execution_caller"},
            {"from": "taskrunner_contract", "to": "step_executor_contract", "relationship": "execution_owner_boundary"},
        ])
    return edges


def make_record(index: int, item: dict[str, Any], sources: dict[str, dict[str, str]]) -> dict[str, Any]:
    source_file = str(item.get("source_file") or "")
    function_name = assigned_function_name(str(item.get("expression") or ""))
    facts = function_facts(function_name, sources[source_file])
    flags = classify_item(item, facts)
    member = str(item.get("symbol") or "").rsplit(".", 1)[-1]
    stage12_precondition = str(item.get("safe_removal_precondition") or "").strip()
    precondition = f"{stage12_precondition} Stage13C StepExecutor condition: {primary_precondition(flags)}"
    direct_evidence = [f"assignment:{item.get('expression')}"] if flags["direct"] else []
    return {
        "blocker_id": f"S13C-SE-{index:03d}",
        "source_file": source_file,
        "source_line": int(item.get("source_line") or 0),
        "symbol": str(item.get("symbol") or ""),
        "validated_classification": str(item.get("classification") or ""),
        "stage12_primary_domain": str(item.get("domain") or ""),
        "replacement_kind": str(item.get("replacement_kind") or ""),
        "replacement_target": str(item.get("replacement_target") or ""),
        "current_owner": f"class-level assignment in {source_file}:{item.get('source_line')}",
        "expected_native_owner": f"{OWNER_PREFIX}.{member} (native definition)",
        "execution_boundary": boundary(flags["execution"], direct_evidence, "StepExecutor"),
        "authority_boundary": boundary(flags["authority"], [f"stage12_domain:{item.get('domain')}"] if flags["authority"] else [], "RuntimeExecutionAuthority → TaskRunner → StepExecutor"),
        "lineage_boundary": boundary(flags["lineage"], [f"function_or_authority_chain:{function_name}:goal_lineage", f"{relative(STAGE13B_PATH)}#marker_counts.goal_lineage_dependency"] if flags["lineage"] else [], "goal_lineage_contract"),
        "runtime_session_boundary": boundary(flags["runtime_session"], [f"function_or_authority_chain:{function_name}:runtime_session_or_state", f"{relative(STAGE13B_PATH)}#marker_counts.runtime_session_dependency"] if flags["runtime_session"] else [], "runtime_session_ownership"),
        "repair_boundary": boundary(flags["repair"], [f"stage12_domain:{item.get('domain')}"] if flags["repair"] else [], "repair_chain"),
        "fallback_signature": flags["fallback"],
        "direct_overlay": flags["direct"],
        "indirect_overlay": flags["indirect"],
        "predecessor_references": facts["predecessor_references"],
        "called_helpers": facts["called_helpers"],
        "buckets": flags["buckets"],
        "why_blocker": str(item.get("why_blocker") or ""),
        "safe_removal_precondition": precondition,
        "dependency_edges": dependency_edges(flags),
        "unlock_targets": [
            target for target, active in (
                ("scheduler_contract", flags["execution"]),
                ("taskrunner_contract", flags["execution"] or flags["fallback"]),
                ("repair_chain", flags["repair"]),
            ) if active
        ],
        "evidence_source": [
            f"{relative(STAGE12_PATH)}#{item.get('domain')}",
            f"{source_file}:{item.get('source_line')}",
            f"assignment_rhs:{function_name}" if function_name else "class_state_assignment",
        ],
    }


def scheduler_unlock_graph(stage13a: dict[str, Any]) -> dict[str, Any]:
    edge_unlocks: list[dict[str, Any]] = []
    direct: list[dict[str, Any]] = []
    cumulative: list[dict[str, Any]] = []
    for item in stage13a.get("scheduler_items", []):
        if not isinstance(item, dict) or item.get("validated_classification") != "confirmed_blocker":
            continue
        dependencies = set(item.get("cross_domain_dependencies") or [])
        if "step_executor_contract" not in dependencies:
            continue
        record = {
            "blocker_id": item.get("blocker_id"),
            "symbol": item.get("symbol"),
            "dependencies": sorted(dependencies),
            "remaining_after_stepexecutor": sorted(dependencies - {"step_executor_contract"}),
            "evidence_source": f"{relative(STAGE13A_PATH)}#{item.get('blocker_id')}",
        }
        edge_unlocks.append(record)
        if dependencies == {"step_executor_contract"}:
            direct.append(record)
        if dependencies <= {"step_executor_contract", "taskrunner_contract"}:
            cumulative.append(record)
    return {
        "dependency_edges_unlocked": edge_unlocks,
        "directly_unlocked_by_stepexecutor_only": direct,
        "unlocked_after_taskrunner_and_stepexecutor": cumulative,
    }


def taskrunner_unlock_graph(stage13b: dict[str, Any]) -> dict[str, Any]:
    edge_unlocks: list[dict[str, Any]] = []
    direct: list[dict[str, Any]] = []
    for item in stage13b.get("taskrunner_items", []):
        if not isinstance(item, dict) or "step_executor_dependencies" not in (item.get("dependency_groups") or []):
            continue
        groups = set(item.get("dependency_groups") or [])
        record = {
            "blocker_id": item.get("blocker_id"),
            "symbol": item.get("symbol"),
            "dependency_groups": sorted(groups),
            "remaining_after_stepexecutor": sorted(groups - {"step_executor_dependencies"}),
            "evidence_source": f"{relative(STAGE13B_PATH)}#{item.get('blocker_id')}",
        }
        edge_unlocks.append(record)
        if groups == {"step_executor_dependencies"}:
            direct.append(record)
    return {
        "dependency_edges_unlocked": edge_unlocks,
        "directly_unlocked_by_stepexecutor_only": direct,
    }


def count_map(keys: Iterable[str], values: Iterable[str]) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts[key] for key in keys}


def validate(records: list[dict[str, Any]], stage11b: dict[str, Any]) -> None:
    if len(records) != EXPECTED_TOTAL:
        raise SystemExit(f"expected {EXPECTED_TOTAL} StepExecutor items, found {len(records)}")
    confirmed = sum(record["validated_classification"] == "confirmed_blocker" for record in records)
    if confirmed != EXPECTED_CONFIRMED:
        raise SystemExit(f"expected {EXPECTED_CONFIRMED} confirmed StepExecutor blockers, found {confirmed}")
    stage11b_total = sum(
        str(item.get("suspected_native_owner") or "").startswith(OWNER_PREFIX)
        for item in stage11b.get("validated_blockers", [])
        if isinstance(item, dict)
    )
    if stage11b_total != len(records):
        raise SystemExit(f"Stage11B/Stage13C StepExecutor mismatch: {stage11b_total} != {len(records)}")
    required = ("source_file", "symbol", "replacement_target", "safe_removal_precondition", "evidence_source")
    for record in records:
        missing = [field for field in required if not record.get(field)]
        if missing:
            raise SystemExit(f"{record['blocker_id']} missing fields: {missing}")


def report_record(record: dict[str, Any]) -> list[str]:
    buckets = ", ".join(f"`{value}`" for value in record["buckets"]) or "none"
    targets = ", ".join(f"`{value}`" for value in record["unlock_targets"]) or "none"
    return [
        f"- `{record['blocker_id']}` — `{record['source_file']}:{record['source_line']}` — `{record['symbol']}`",
        f"  - Classification/domain: `{record['validated_classification']}` / `{record['stage12_primary_domain']}`",
        f"  - Buckets: {buckets}",
        f"  - Direct/indirect overlay: {str(record['direct_overlay']).lower()} / {str(record['indirect_overlay']).lower()}",
        f"  - Current owner: {record['current_owner']}",
        f"  - Expected native owner: `{record['expected_native_owner']}`",
        f"  - Why blocker: {record['why_blocker']}",
        f"  - Safe removal precondition: {record['safe_removal_precondition']}",
        f"  - Unlock targets: {targets}",
    ]


def write_report(records: list[dict[str, Any]], summary: dict[str, Any], scheduler_graph: dict[str, Any], taskrunner_graph: dict[str, Any], repair_unlocks: list[dict[str, Any]]) -> None:
    lines = [
        "# StepExecutor Native Ownership Closure — Stage13C",
        "",
        "Discovery and ownership mapping only. No blocker was fixed and no production runtime file was modified.",
        "",
        "## Summary",
        "",
        f"- Total StepExecutor items: {summary['total_stepexecutor_items']}",
        f"- Confirmed blockers: {summary['confirmed_blockers']}",
        f"- Compatibility bridges: {summary['compatibility_bridge_count']}",
        f"- Direct overlays: {summary['direct_overlay_count']}",
        f"- Indirect overlays: {summary['indirect_overlay_count']}",
        f"- Fallback signatures: {summary['fallback_signature_count']}",
        f"- Authority propagation chains: {summary['authority_propagation_chain_count']}",
        f"- Lineage dependencies: {summary['lineage_dependency_count']}",
        f"- Runtime-session dependencies: {summary['runtime_session_dependency_count']}",
        f"- Repair-chain dependencies: {summary['repair_chain_dependency_count']}",
        f"- Unresolved ambiguities: {summary['unresolved_ambiguity_count']}",
        "- Production runtime touched: false",
        "",
        "## Bucket counts",
        "",
    ]
    for bucket, count in summary["bucket_counts"].items():
        lines.append(f"- `{bucket}`: {count}")
    lines.extend(["", "## Closure order", ""])
    for entry in summary["closure_order"]:
        blocked = ", ".join(f"`{value}`" for value in entry["blocked_by"]) or "none"
        unlocks = ", ".join(f"`{value}`" for value in entry["unlocks"]) or "none"
        lines.append(f"{entry['order']}. `{entry['node']}` — blocked by: {blocked}; unlocks: {unlocks}")

    lines.extend(["", "## Unlock graph", ""])
    lines.append(f"- Scheduler dependency edges unlocked: {len(scheduler_graph['dependency_edges_unlocked'])}")
    lines.append(f"- Scheduler blockers directly unlocked by StepExecutor only: {len(scheduler_graph['directly_unlocked_by_stepexecutor_only'])}")
    lines.append(f"- Scheduler blockers unlocked after TaskRunner + StepExecutor: {len(scheduler_graph['unlocked_after_taskrunner_and_stepexecutor'])}")
    lines.append(f"- TaskRunner dependency edges unlocked: {len(taskrunner_graph['dependency_edges_unlocked'])}")
    lines.append(f"- TaskRunner blockers directly unlocked by StepExecutor only: {len(taskrunner_graph['directly_unlocked_by_stepexecutor_only'])}")
    lines.append(f"- Repair-chain blockers owned by StepExecutor: {len(repair_unlocks)}")

    lines.extend(["", "## Ownership map", ""])
    for owner, details in summary["ownership_map"].items():
        lines.append(f"- `{owner}`: {details}")

    lines.extend(["", "## StepExecutor inventory", ""])
    for record in records:
        lines.extend(report_record(record))

    non_mainline = [record for record in records if record["validated_classification"] == "non_mainline_issue"]
    lines.extend(["", "## Non-Mainline Issue Report", ""])
    if not non_mainline:
        lines.append("No StepExecutor-owned non-mainline issue exists in Stage12, and no outside-domain issue was discovered during Stage13C analysis.")
    else:
        for record in non_mainline:
            lines.extend(report_record(record))

    impact = summary["aer_closure_impact"]
    lines.extend([
        "",
        "## AER Closure Impact",
        "",
        f"- Scheduler impact: {impact['scheduler_impact']}",
        f"- TaskRunner impact: {impact['taskrunner_impact']}",
        f"- RepairChain impact: {impact['repair_chain_impact']}",
        f"- Ownership Closure completion: {impact['ownership_closure_completion_percent']}% ({impact['ownership_closure_basis']})",
        f"- Freeze readiness: {impact['freeze_readiness_percent']}% ({impact['freeze_readiness_basis']})",
        "",
        "## Outputs",
        "",
        f"- `{relative(OUTPUT_PATH)}`",
        f"- `{relative(SUMMARY_PATH)}`",
        f"- `{relative(REPORT_PATH)}`",
        "",
    ])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    stage11b = load_json(STAGE11B_PATH)
    load_json(STAGE11B_SUMMARY_PATH)
    stage12 = load_json(STAGE12_PATH)
    stage12_summary = load_json(STAGE12_SUMMARY_PATH)
    stage13a = load_json(STAGE13A_PATH)
    stage13a_summary = load_json(STAGE13A_SUMMARY_PATH)
    stage13b = load_json(STAGE13B_PATH)
    stage13b_summary = load_json(STAGE13B_SUMMARY_PATH)

    raw_items = all_stage12_items(stage12)
    source_paths = sorted({str(item.get("source_file") or "") for item in raw_items})
    sources = {path: function_sources(path) for path in source_paths}
    records = [make_record(index, item, sources) for index, item in enumerate(raw_items, 1)]
    validate(records, stage11b)

    classification_counts = count_map(CLASSIFICATIONS, (record["validated_classification"] for record in records))
    bucket_counts = {
        bucket: sum(bucket in record["buckets"] for record in records)
        for bucket in BUCKETS
    }
    scheduler_graph = scheduler_unlock_graph(stage13a)
    taskrunner_graph = taskrunner_unlock_graph(stage13b)
    repair_unlocks = [
        {
            "blocker_id": record["blocker_id"],
            "symbol": record["symbol"],
            "evidence_source": record["evidence_source"],
        }
        for record in records if record["repair_boundary"]["active"]
    ]
    confirmed_mapped = (
        int(stage13a_summary.get("confirmed_scheduler_blockers") or 0)
        + int(stage13b_summary.get("confirmed_blockers") or 0)
        + classification_counts["confirmed_blocker"]
    )
    total_confirmed = int(stage12_summary.get("classification_counts", {}).get("confirmed_blocker") or 0)
    mapping_percent = round(100.0 * confirmed_mapped / total_confirmed, 1) if total_confirmed else 0.0
    ownership_map = {
        "current_execution_owner": "30 class-level StepExecutor assignments across execution, authority, repair, and adapter bridges",
        "expected_execution_owner": "core.runtime.step_executor.StepExecutor native methods and native class state",
        "ownership_leak_locations": sorted({f"{record['source_file']}:{record['source_line']}" for record in records}),
        "native_owner_endpoints": sorted({record["expected_native_owner"] for record in records}),
    }
    dependency_graph = {
        "closure_nodes": list(CLOSURE_ORDER),
        "item_dependency_edges": [edge for record in records for edge in record["dependency_edges"]],
        "direct_overlays": [record["blocker_id"] for record in records if record["direct_overlay"]],
        "indirect_overlays": [record["blocker_id"] for record in records if record["indirect_overlay"]],
        "fallback_chains": [record["blocker_id"] for record in records if record["fallback_signature"]],
        "authority_propagation_chains": [record["blocker_id"] for record in records if record["authority_boundary"]["active"]],
        "execution_ownership_chains": [record["blocker_id"] for record in records if record["execution_boundary"]["active"]],
    }
    aer_impact = {
        "scheduler_impact": f"Clears {len(scheduler_graph['dependency_edges_unlocked'])} StepExecutor dependency edges; {len(scheduler_graph['unlocked_after_taskrunner_and_stepexecutor'])} require TaskRunner closure too.",
        "taskrunner_impact": f"Clears {len(taskrunner_graph['dependency_edges_unlocked'])} StepExecutor dependency edges, including the 2 direct overlays identified in Stage13B.",
        "repair_chain_impact": f"Maps {len(repair_unlocks)} StepExecutor-owned repair blockers that gate repair-chain closure.",
        "ownership_closure_completion_percent": mapping_percent,
        "ownership_closure_basis": f"confirmed blocker ownership mapped in Stage13A/B/C: {confirmed_mapped}/{total_confirmed}",
        "freeze_readiness_percent": 0.0,
        "freeze_readiness_basis": "discovery only; 26 confirmed StepExecutor blockers remain and known ownership suites are not frozen",
    }

    payload = {
        "stage": "StepExecutor Native Ownership Closure Stage13C",
        "production_runtime_modified": False,
        "inputs": [
            relative(STAGE11B_PATH), relative(STAGE11B_SUMMARY_PATH),
            relative(STAGE12_PATH), relative(STAGE12_SUMMARY_PATH),
            relative(STAGE13A_PATH), relative(STAGE13A_SUMMARY_PATH),
            relative(STAGE13B_PATH), relative(STAGE13B_SUMMARY_PATH),
        ],
        "total_stepexecutor_items": len(records),
        "classification_counts": classification_counts,
        "bucket_counts": bucket_counts,
        "stepexecutor_items": records,
        "dependency_graph": dependency_graph,
        "unlock_graph": {
            "scheduler": scheduler_graph,
            "taskrunner": taskrunner_graph,
            "repair_chain": repair_unlocks,
        },
        "ownership_map": ownership_map,
        "unresolved_ambiguities": [],
        "non_mainline_issues": [record for record in records if record["validated_classification"] == "non_mainline_issue"],
        "outside_domain_non_mainline_issues_discovered": [],
        "aer_closure_impact": aer_impact,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "stage": "StepExecutor Native Ownership Closure Stage13C",
        "total_stepexecutor_items": len(records),
        "confirmed_blockers": classification_counts["confirmed_blocker"],
        "compatibility_bridge_count": classification_counts["compatibility_bridge"],
        "false_positive_count": classification_counts["false_positive"],
        "non_mainline_issue_count": classification_counts["non_mainline_issue"],
        "bucket_counts": bucket_counts,
        "direct_overlay_count": sum(record["direct_overlay"] for record in records),
        "indirect_overlay_count": sum(record["indirect_overlay"] for record in records),
        "fallback_signature_count": sum(record["fallback_signature"] for record in records),
        "authority_propagation_chain_count": sum(record["authority_boundary"]["active"] for record in records),
        "lineage_dependency_count": sum(record["lineage_boundary"]["active"] for record in records),
        "runtime_session_dependency_count": sum(record["runtime_session_boundary"]["active"] for record in records),
        "repair_chain_dependency_count": sum(record["repair_boundary"]["active"] for record in records),
        "unlock_counts": {
            "scheduler_dependency_edges": len(scheduler_graph["dependency_edges_unlocked"]),
            "scheduler_direct": len(scheduler_graph["directly_unlocked_by_stepexecutor_only"]),
            "scheduler_after_taskrunner_and_stepexecutor": len(scheduler_graph["unlocked_after_taskrunner_and_stepexecutor"]),
            "taskrunner_dependency_edges": len(taskrunner_graph["dependency_edges_unlocked"]),
            "taskrunner_direct": len(taskrunner_graph["directly_unlocked_by_stepexecutor_only"]),
            "repair_chain": len(repair_unlocks),
        },
        "closure_order": list(CLOSURE_ORDER),
        "ownership_map": ownership_map,
        "unresolved_ambiguity_count": 0,
        "production_runtime_touched": False,
        "aer_closure_impact": aer_impact,
        "outputs": {
            "inventory": relative(OUTPUT_PATH),
            "summary": relative(SUMMARY_PATH),
            "report": relative(REPORT_PATH),
        },
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(records, summary, scheduler_graph, taskrunner_graph, repair_unlocks)

    print(f"total_stepexecutor_items: {len(records)}")
    print(f"classification_counts: {classification_counts}")
    print(f"bucket_counts: {bucket_counts}")
    print(f"direct_overlays: {summary['direct_overlay_count']}")
    print(f"indirect_overlays: {summary['indirect_overlay_count']}")
    print(f"fallback_signatures: {summary['fallback_signature_count']}")
    print(f"unlock_counts: {summary['unlock_counts']}")
    print("unresolved_ambiguity_count: 0")
    print("production_runtime_touched: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
