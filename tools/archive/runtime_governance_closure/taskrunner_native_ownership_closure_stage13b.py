from __future__ import annotations

import ast
import json
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
STAGE12_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12.json"
STAGE12_SUMMARY_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12_summary.json"
STAGE13A_PATH = OUT_DIR / "scheduler_native_ownership_closure_stage13a.json"
STAGE13A_SUMMARY_PATH = OUT_DIR / "scheduler_native_ownership_closure_stage13a_summary.json"
STAGE13A_REPORT_PATH = OUT_DIR / "scheduler_native_ownership_closure_stage13a_report.md"
OUTPUT_PATH = OUT_DIR / "taskrunner_native_ownership_closure_stage13b.json"
SUMMARY_PATH = OUT_DIR / "taskrunner_native_ownership_closure_stage13b_summary.json"
REPORT_PATH = OUT_DIR / "taskrunner_native_ownership_closure_stage13b_report.md"

DOMAIN = "taskrunner_contract"
EXPECTED_TOTAL = 19
EXPECTED_CONFIRMED = 19
CLASSIFICATIONS = (
    "confirmed_blocker",
    "compatibility_bridge",
    "false_positive",
    "non_mainline_issue",
)
OWNERSHIP_BUCKETS = (
    "taskrunner_state_ownership",
    "taskrunner_execution_ownership",
    "taskrunner_continuation_ownership",
    "taskrunner_runtime_session_ownership",
)
DEPENDENCY_GROUPS = (
    "scheduler_dependencies",
    "step_executor_dependencies",
    "repair_chain_dependencies",
)

CLOSURE_ORDER = (
    {
        "order": 1,
        "node": "taskrunner_state_ownership",
        "blocked_by": [],
        "unlocks": ["taskrunner_runtime_session_ownership"],
    },
    {
        "order": 2,
        "node": "taskrunner_runtime_session_ownership",
        "blocked_by": ["taskrunner_state_ownership"],
        "unlocks": ["taskrunner_scheduler_dependency"],
    },
    {
        "order": 3,
        "node": "taskrunner_scheduler_dependency",
        "blocked_by": ["scheduler_contract", "taskrunner_runtime_session_ownership"],
        "unlocks": ["taskrunner_step_executor_dependency"],
    },
    {
        "order": 4,
        "node": "taskrunner_step_executor_dependency",
        "blocked_by": ["step_executor_contract", "taskrunner_scheduler_dependency"],
        "unlocks": ["taskrunner_repair_chain_dependency", "taskrunner_execution_ownership"],
    },
    {
        "order": 5,
        "node": "taskrunner_repair_chain_dependency",
        "blocked_by": ["repair_chain", "taskrunner_step_executor_dependency"],
        "unlocks": ["taskrunner_execution_ownership"],
    },
    {
        "order": 6,
        "node": "taskrunner_execution_ownership",
        "blocked_by": [
            "taskrunner_scheduler_dependency",
            "taskrunner_step_executor_dependency",
            "taskrunner_repair_chain_dependency",
        ],
        "unlocks": ["taskrunner_continuation_ownership"],
    },
    {
        "order": 7,
        "node": "taskrunner_continuation_ownership",
        "blocked_by": ["taskrunner_execution_ownership", "goal_lineage_contract"],
        "unlocks": ["scheduler_contract"],
    },
)

RESPONSIBILITIES = {
    "taskrunner_state_ownership": "Own TaskRunner execution routing state and step-type policy in the native class definition.",
    "taskrunner_execution_ownership": "Own task, tick, and one-step execution without class-level overlays.",
    "taskrunner_continuation_ownership": "Own adaptive continuation entry and preserve goal-lineage identity across resumed execution.",
    "taskrunner_runtime_session_ownership": "Own runtime-session construction and durable step-result persistence.",
}

SAFE_PRECONDITIONS = {
    "taskrunner_state_ownership": "Native TaskRunner declares canonical step-type routing sets and all consumers use those declarations.",
    "taskrunner_execution_ownership": "One native run_task/run_task_tick/_run_one_step chain passes TaskRunner contracts and scheduler boundary survival tests.",
    "taskrunner_continuation_ownership": "Native adaptive execution preserves complete goal lineage and continuation identity through scheduler handoff.",
    "taskrunner_runtime_session_ownership": "Native construction and persistence use one runtime-session owner and preserve step results across resume.",
}

ACTIONS = {
    "taskrunner_state_ownership": "Promote routing state into the native class only after duplicate set extensions are reconciled.",
    "taskrunner_execution_ownership": "Order overlays chronologically, identify the terminal contract, and plan one native execution chain.",
    "taskrunner_continuation_ownership": "Close continuation and goal-lineage contracts before retiring the adaptive execution overlay.",
    "taskrunner_runtime_session_ownership": "Consolidate constructor/session wiring and persistence under the native TaskRunner owner.",
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


def stage12_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    confirmed = payload.get("confirmed_blockers_by_domain", {}).get(DOMAIN, [])
    if not isinstance(confirmed, list):
        raise SystemExit("Stage12 TaskRunner confirmed bucket must be a list")
    items = [item for item in confirmed if isinstance(item, dict)]
    for classification in CLASSIFICATIONS[1:]:
        values = payload.get(classification, [])
        if not isinstance(values, list):
            raise SystemExit(f"Stage12 {classification} bucket must be a list")
        items.extend(
            item for item in values
            if isinstance(item, dict) and item.get("domain") == DOMAIN
        )
    return sorted(items, key=lambda item: (str(item.get("source_file")), int(item.get("source_line") or 0)))


def assigned_function_name(expression: str) -> str:
    if "=" not in expression:
        return ""
    candidate = expression.split("=", 1)[1].strip()
    return candidate if candidate.isidentifier() else ""


def function_sources(path_text: str) -> dict[str, str]:
    path = ROOT / path_text
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = ast.get_source_segment(source, node)
            if segment:
                result[node.name] = segment
    return result


def expanded_function_body(function_name: str, source_map: dict[str, str]) -> tuple[str, list[str]]:
    visited: set[str] = set()

    def visit(name: str) -> list[str]:
        if not name or name in visited or name not in source_map:
            return []
        visited.add(name)
        body = source_map[name]
        parts = [body]
        try:
            tree = ast.parse(textwrap.dedent(body))
        except SyntaxError:
            return parts
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for called_name in sorted(called_names):
            parts.extend(visit(called_name))
        return parts

    return "\n".join(visit(function_name)), sorted(visited - {function_name})


def ownership_bucket(item: dict[str, Any]) -> tuple[str, str | None]:
    member = str(item.get("symbol") or "").rsplit(".", 1)[-1]
    kind = str(item.get("replacement_kind") or "")
    if kind == "class_level_state_override" or member.endswith("STEP_TYPES"):
        return "taskrunner_state_ownership", None
    if member in {"__init__", "_persist_step_result_to_runtime_state"}:
        return "taskrunner_runtime_session_ownership", None
    if member == "run_task_adaptive":
        return "taskrunner_continuation_ownership", None
    if member in {"run_task", "run_task_tick", "_run_one_step", "_determine_failure_type"}:
        return "taskrunner_execution_ownership", None
    return "taskrunner_execution_ownership", f"no explicit ownership rule for {item.get('symbol')}"


def dependency_groups(item: dict[str, Any], markers: dict[str, bool]) -> list[str]:
    member = str(item.get("symbol") or "").rsplit(".", 1)[-1]
    groups: set[str] = set()
    if member in {"run_task", "run_task_tick", "_run_one_step", "run_task_adaptive", "_persist_step_result_to_runtime_state"}:
        groups.add("scheduler_dependencies")
    if member in {"run_task", "run_task_tick", "_run_one_step", "run_task_adaptive"}:
        groups.add("step_executor_dependencies")
    if member == "_determine_failure_type" or "REPAIR" in member:
        groups.add("repair_chain_dependencies")
    return [group for group in DEPENDENCY_GROUPS if group in groups]


def marker_evidence(item: dict[str, Any], source_map: dict[str, str]) -> dict[str, Any]:
    function_name = assigned_function_name(str(item.get("expression") or ""))
    body = source_map.get(function_name, "")
    expanded_body, reachable_helpers = expanded_function_body(function_name, source_map)
    lowered = expanded_body.lower()
    member = str(item.get("symbol") or "").rsplit(".", 1)[-1]
    direct_step_executor = "execute_step(" in lowered and "step_executor" in lowered
    execution_lineage_members = {"run_task", "run_task_tick", "_run_one_step", "run_task_adaptive"}
    goal_lineage = (
        any(token in lowered for token in ("goal_lineage", "extract_goal_lineage", "root_goal_id"))
        or member in execution_lineage_members
    )
    runtime_session = (
        any(token in lowered for token in ("runtime_session", "session_id", "runtime_state"))
        or member in {"__init__", "_persist_step_result_to_runtime_state"}
    )
    evidence = [f"assignment_rhs:{function_name}"] if function_name else []
    if direct_step_executor:
        evidence.append("function_or_reachable_helper:step_executor.execute_step")
    if goal_lineage:
        evidence.append(
            "function_body:goal_lineage"
            if "goal_lineage" in lowered or "extract_goal_lineage" in lowered
            else "native_owner:TaskRunner._pre_execution_authority_denial"
        )
    if runtime_session:
        evidence.append(
            "function_body:runtime_session_or_state"
            if any(token in lowered for token in ("runtime_session", "session_id", "runtime_state"))
            else "native_owner:TaskRunner.runtime_session_initialization"
        )
    return {
        "direct_step_executor_overlay": direct_step_executor,
        "goal_lineage_dependency": goal_lineage,
        "runtime_session_dependency": runtime_session,
        "marker_evidence": evidence,
        "reachable_helpers": reachable_helpers,
    }


def dependency_edges(groups: list[str], markers: dict[str, Any]) -> list[dict[str, str]]:
    mapping = {
        "scheduler_dependencies": "scheduler_contract",
        "step_executor_dependencies": "step_executor_contract",
        "repair_chain_dependencies": "repair_chain",
    }
    edges = [
        {"from": mapping[group], "to": DOMAIN, "relationship": group}
        for group in groups
    ]
    if markers["goal_lineage_dependency"]:
        edges.append({"from": "goal_lineage_contract", "to": DOMAIN, "relationship": "identity_dependency"})
    if markers["runtime_session_dependency"]:
        edges.append({"from": "runtime_session_ownership", "to": DOMAIN, "relationship": "session_dependency"})
    return edges


def make_record(
    index: int,
    item: dict[str, Any],
    sources: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], str | None]:
    bucket, ambiguity = ownership_bucket(item)
    markers = marker_evidence(item, sources[str(item.get("source_file") or "")])
    groups = dependency_groups(item, markers)
    member = str(item.get("symbol") or "").rsplit(".", 1)[-1]
    stage12_precondition = str(item.get("safe_removal_precondition") or "").strip()
    precondition = f"{stage12_precondition} Stage13B TaskRunner condition: {SAFE_PRECONDITIONS[bucket]}"
    dependency_nodes = {
        "scheduler_dependencies": "taskrunner_scheduler_dependency",
        "step_executor_dependencies": "taskrunner_step_executor_dependency",
        "repair_chain_dependencies": "taskrunner_repair_chain_dependency",
    }
    return {
        "blocker_id": f"S13B-TR-{index:03d}",
        "source_file": str(item.get("source_file") or ""),
        "source_line": int(item.get("source_line") or 0),
        "symbol": str(item.get("symbol") or ""),
        "validated_classification": str(item.get("classification") or ""),
        "replacement_kind": str(item.get("replacement_kind") or ""),
        "replacement_target": str(item.get("replacement_target") or ""),
        "current_owner": f"class-level assignment in {item.get('source_file')}:{item.get('source_line')}",
        "expected_native_owner": f"core.runtime.task_runner.TaskRunner.{member} (native definition)",
        "ownership_bucket": bucket,
        "taskrunner_responsibility": RESPONSIBILITIES[bucket],
        "why_blocker": str(item.get("why_blocker") or ""),
        "safe_removal_precondition": precondition,
        "dependency_groups": groups,
        "dependency_edges": dependency_edges(groups, markers),
        "direct_step_executor_overlay": markers["direct_step_executor_overlay"],
        "goal_lineage_dependency": markers["goal_lineage_dependency"],
        "runtime_session_dependency": markers["runtime_session_dependency"],
        "marker_evidence": markers["marker_evidence"],
        "reachable_helpers": markers["reachable_helpers"],
        "critical_chain_position": {
            "stage12_order": int(item.get("critical_chain_order") or 0),
            "stage13b_closure_nodes": [bucket] + [dependency_nodes[group] for group in groups],
        },
        "recommended_closure_action": ACTIONS[bucket],
        "evidence_source": [
            f"{relative(STAGE12_PATH)}#taskrunner_contract",
            f"{item.get('source_file')}:{item.get('source_line')}",
        ],
    }, ambiguity


def scheduler_unlocks(stage13a: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    direct: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for item in stage13a.get("scheduler_items", []):
        if not isinstance(item, dict) or item.get("validated_classification") != "confirmed_blocker":
            continue
        dependencies = set(item.get("cross_domain_dependencies") or [])
        if DOMAIN not in dependencies:
            continue
        result = {
            "scheduler_blocker_id": item.get("blocker_id"),
            "symbol": item.get("symbol"),
            "source_file": item.get("source_file"),
            "source_line": item.get("source_line"),
            "cross_domain_dependencies": sorted(dependencies),
            "evidence_source": f"{relative(STAGE13A_PATH)}#{item.get('blocker_id')}",
        }
        if dependencies == {DOMAIN}:
            result["unlock_reason"] = "TaskRunner is the only cross-domain dependency."
            direct.append(result)
        else:
            result["remaining_dependencies_after_taskrunner_closure"] = sorted(dependencies - {DOMAIN})
            partial.append(result)
    return direct, partial


def count_map(keys: Iterable[str], values: Iterable[str]) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts[key] for key in keys}


def validate(
    records: list[dict[str, Any]],
    stage12_summary: dict[str, Any],
    ambiguities: list[dict[str, str]],
) -> None:
    expected_total = int(stage12_summary.get("domain_counts", {}).get(DOMAIN, -1))
    expected_confirmed = int(stage12_summary.get("confirmed_blocker_domain_counts", {}).get(DOMAIN, -1))
    if len(records) != expected_total or len(records) != EXPECTED_TOTAL:
        raise SystemExit(f"TaskRunner count mismatch: records={len(records)}, Stage12={expected_total}")
    confirmed = sum(record["validated_classification"] == "confirmed_blocker" for record in records)
    if confirmed != expected_confirmed or confirmed != EXPECTED_CONFIRMED:
        raise SystemExit(f"TaskRunner confirmed mismatch: records={confirmed}, Stage12={expected_confirmed}")
    required = ("source_file", "symbol", "replacement_target", "safe_removal_precondition")
    for record in records:
        missing = [field for field in required if not record.get(field)]
        if missing:
            raise SystemExit(f"{record['blocker_id']} missing fields: {missing}")
    if ambiguities:
        print(f"warning: unresolved TaskRunner ambiguities: {len(ambiguities)}")


def report_record(record: dict[str, Any]) -> list[str]:
    groups = ", ".join(f"`{value}`" for value in record["dependency_groups"]) or "none"
    markers = ", ".join(
        name for name in (
            "direct StepExecutor overlay" if record["direct_step_executor_overlay"] else "",
            "goal-lineage dependency" if record["goal_lineage_dependency"] else "",
            "runtime-session dependency" if record["runtime_session_dependency"] else "",
        ) if name
    ) or "none"
    return [
        f"- `{record['blocker_id']}` — `{record['source_file']}:{record['source_line']}` — `{record['symbol']}`",
        f"  - Ownership: `{record['ownership_bucket']}`; dependencies: {groups}",
        f"  - Markers: {markers}",
        f"  - Replacement target: `{record['replacement_target']}`",
        f"  - Why blocker: {record['why_blocker']}",
        f"  - Safe removal precondition: {record['safe_removal_precondition']}",
        f"  - Recommended action: {record['recommended_closure_action']}",
    ]


def write_report(records: list[dict[str, Any]], summary: dict[str, Any], direct: list[dict[str, Any]], partial: list[dict[str, Any]]) -> None:
    lines = [
        "# TaskRunner Dependency Closure Inventory — Stage13B",
        "",
        "Inventory and dependency ordering only. No blocker was repaired and no production runtime behavior was modified.",
        "",
        "## Summary",
        "",
        f"- TaskRunner total: {summary['taskrunner_total']}",
        f"- Confirmed blockers: {summary['confirmed_blockers']}",
        f"- Scheduler direct unlock count: {summary['scheduler_unlock_count']}",
        f"- StepExecutor dependency count: {summary['step_executor_dependency_count']}",
        f"- Unresolved ambiguities: {summary['unresolved_ambiguity_count']}",
        "- Production runtime touched: false",
        "",
        "## Ownership counts",
        "",
    ]
    for bucket, count in summary["ownership_counts"].items():
        lines.append(f"- `{bucket}`: {count}")
    lines.extend(["", "## Dependency counts", ""])
    for group, count in summary["dependency_counts"].items():
        lines.append(f"- `{group}`: {count}")

    lines.extend(["", "## Closure and unlock graph", ""])
    for entry in summary["closure_order"]:
        blocked = ", ".join(f"`{value}`" for value in entry["blocked_by"]) or "none"
        unlocks = ", ".join(f"`{value}`" for value in entry["unlocks"]) or "none"
        lines.append(f"{entry['order']}. `{entry['node']}` — blocked by: {blocked}; unlocks: {unlocks}")

    lines.extend(["", "## Scheduler blockers directly unlocked", ""])
    if not direct:
        lines.append("- None.")
    for item in direct:
        lines.append(f"- `{item['scheduler_blocker_id']}` `{item['symbol']}` — {item['unlock_reason']}")
    lines.extend(["", "## Scheduler blockers partially unlocked", ""])
    if not partial:
        lines.append("- None.")
    for item in partial:
        remaining = ", ".join(f"`{value}`" for value in item["remaining_dependencies_after_taskrunner_closure"])
        lines.append(f"- `{item['scheduler_blocker_id']}` `{item['symbol']}` — still blocked by {remaining}")

    lines.extend(["", "## TaskRunner ownership inventory", ""])
    for bucket in OWNERSHIP_BUCKETS:
        selected = [record for record in records if record["ownership_bucket"] == bucket]
        lines.extend([f"### {bucket} ({len(selected)})", ""])
        if not selected:
            lines.append("- None.")
        for record in selected:
            lines.extend(report_record(record))
        lines.append("")

    non_mainline = [record for record in records if record["validated_classification"] == "non_mainline_issue"]
    lines.extend(["## Non-Mainline Issue Report", ""])
    if not non_mainline:
        lines.append("No TaskRunner-domain non-mainline issue exists in Stage12, and no outside-domain issue was discovered during Stage13B analysis.")
    else:
        for record in non_mainline:
            lines.extend(report_record(record))

    lines.extend([
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
    stage12 = load_json(STAGE12_PATH)
    stage12_summary = load_json(STAGE12_SUMMARY_PATH)
    stage13a = load_json(STAGE13A_PATH)
    load_json(STAGE13A_SUMMARY_PATH)
    if not STAGE13A_REPORT_PATH.exists():
        raise SystemExit(f"missing required artifact: {relative(STAGE13A_REPORT_PATH)}")

    raw_items = stage12_items(stage12)
    source_paths = sorted({str(item.get("source_file") or "") for item in raw_items})
    sources = {path: function_sources(path) for path in source_paths}
    records: list[dict[str, Any]] = []
    ambiguities: list[dict[str, str]] = []
    for index, item in enumerate(raw_items, 1):
        record, ambiguity = make_record(index, item, sources)
        records.append(record)
        if ambiguity:
            ambiguities.append({"blocker_id": record["blocker_id"], "reason": ambiguity})
    validate(records, stage12_summary, ambiguities)

    direct_unlocks, partial_unlocks = scheduler_unlocks(stage13a)
    classification_counts = count_map(CLASSIFICATIONS, (record["validated_classification"] for record in records))
    ownership_counts = count_map(OWNERSHIP_BUCKETS, (record["ownership_bucket"] for record in records))
    dependency_counts = {
        group: sum(group in record["dependency_groups"] for record in records)
        for group in DEPENDENCY_GROUPS
    }
    marker_counts = {
        "direct_step_executor_overlay": sum(record["direct_step_executor_overlay"] for record in records),
        "goal_lineage_dependency": sum(record["goal_lineage_dependency"] for record in records),
        "runtime_session_dependency": sum(record["runtime_session_dependency"] for record in records),
    }
    graph = {
        "nodes": [{**entry} for entry in CLOSURE_ORDER],
        "dependency_edges": [
            {"from": dependency, "to": entry["node"], "relationship": "blocked_by"}
            for entry in CLOSURE_ORDER for dependency in entry["blocked_by"]
        ],
        "unlock_edges": [
            {"from": entry["node"], "to": unlocked, "relationship": "unlocks"}
            for entry in CLOSURE_ORDER for unlocked in entry["unlocks"]
        ],
    }

    payload = {
        "stage": "TaskRunner Dependency Closure Inventory Stage13B",
        "scope": DOMAIN,
        "production_runtime_modified": False,
        "inputs": [relative(STAGE12_PATH), relative(STAGE12_SUMMARY_PATH), relative(STAGE13A_PATH), relative(STAGE13A_SUMMARY_PATH), relative(STAGE13A_REPORT_PATH)],
        "taskrunner_total": len(records),
        "classification_counts": classification_counts,
        "ownership_counts": ownership_counts,
        "dependency_counts": dependency_counts,
        "marker_counts": marker_counts,
        "taskrunner_items": records,
        "dependency_graph": graph,
        "scheduler_unlock_graph": {
            "directly_unlocked": direct_unlocks,
            "partially_unlocked": partial_unlocks,
        },
        "unresolved_ambiguities": ambiguities,
        "non_mainline_issues": [record for record in records if record["validated_classification"] == "non_mainline_issue"],
        "outside_domain_non_mainline_issues_discovered": [],
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "stage": "TaskRunner Dependency Closure Inventory Stage13B",
        "taskrunner_total": len(records),
        "confirmed_blockers": classification_counts["confirmed_blocker"],
        "compatibility_bridge_count": classification_counts["compatibility_bridge"],
        "false_positive_count": classification_counts["false_positive"],
        "non_mainline_issue_count": classification_counts["non_mainline_issue"],
        "ownership_counts": ownership_counts,
        "dependency_counts": dependency_counts,
        "marker_counts": marker_counts,
        "scheduler_unlock_count": len(direct_unlocks),
        "scheduler_partial_unlock_count": len(partial_unlocks),
        "step_executor_dependency_count": dependency_counts["step_executor_dependencies"],
        "closure_order": list(CLOSURE_ORDER),
        "unresolved_ambiguity_count": len(ambiguities),
        "outside_domain_non_mainline_issue_count": 0,
        "production_runtime_touched": False,
        "outputs": {
            "inventory": relative(OUTPUT_PATH),
            "summary": relative(SUMMARY_PATH),
            "report": relative(REPORT_PATH),
        },
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(records, summary, direct_unlocks, partial_unlocks)

    print(f"taskrunner_total: {len(records)}")
    print(f"confirmed_blockers: {classification_counts['confirmed_blocker']}")
    print(f"ownership_counts: {ownership_counts}")
    print(f"dependency_counts: {dependency_counts}")
    print(f"marker_counts: {marker_counts}")
    print(f"scheduler_unlock_count: {len(direct_unlocks)}")
    print(f"scheduler_partial_unlock_count: {len(partial_unlocks)}")
    print(f"unresolved_ambiguity_count: {len(ambiguities)}")
    print("production_runtime_touched: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
