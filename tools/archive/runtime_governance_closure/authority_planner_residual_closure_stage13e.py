from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
STAGE11B = OUT_DIR / "runtime_blocker_validation.json"
STAGE12 = OUT_DIR / "runtime_blocker_domain_split_stage12.json"
STAGE12_SUMMARY = OUT_DIR / "runtime_blocker_domain_split_stage12_summary.json"
STAGE13A = OUT_DIR / "scheduler_native_ownership_closure_stage13a.json"
STAGE13B = OUT_DIR / "taskrunner_native_ownership_closure_stage13b.json"
STAGE13C = OUT_DIR / "stepexecutor_native_ownership_closure_stage13c.json"
STAGE13D = OUT_DIR / "repairchain_native_ownership_closure_stage13d.json"
OUTPUT = OUT_DIR / "authority_planner_residual_closure_stage13e.json"
SUMMARY = OUT_DIR / "authority_planner_residual_closure_stage13e_summary.json"
REPORT = OUT_DIR / "authority_planner_residual_closure_stage13e_report.md"

RESIDUAL_KEYS = {
    ("core/runtime/task_runner.py", 5449),
    ("core/tasks/scheduler.py", 7909),
}

RULES: dict[str, dict[str, Any]] = {
    "TaskRunner._build_taskrunner_authority_context": {
        "closure_bucket": "authority_context",
        "expected_native_owner": "core.runtime.task_runner.TaskRunner._build_taskrunner_authority_context (native definition at core/runtime/task_runner.py:1775)",
        "owner_endpoint": "TaskRunner._build_taskrunner_authority_context",
        "native_definition_line": 1775,
        "responsibility": "Preserve upstream execution authority, delegate a bounded TaskRunner capability, and carry authority identity into StepExecutor without self-granting stronger authority.",
        "dependency_edges": [
            {"from": "runtime_dispatcher_capability", "to": "TaskRunner._build_taskrunner_authority_context", "relationship": "upstream_authority_source"},
            {"from": "runtime_capability_provenance", "to": "TaskRunner._build_taskrunner_authority_context", "relationship": "capability_propagation"},
            {"from": "TaskRunner._build_taskrunner_authority_context", "to": "TaskRunner._pre_execution_authority_denial", "relationship": "authority_policy_input"},
            {"from": "TaskRunner._build_taskrunner_authority_context", "to": "StepExecutor.execute_step", "relationship": "downstream_authority_context"},
            {"from": "runtime_session_ownership", "to": "TaskRunner._build_taskrunner_authority_context", "relationship": "session_identity_dependency"},
        ],
        "safe_removal_precondition": "The native TaskRunner authority-context method preserves upstream authority source, capability provenance, identity graph, task/step identity, and runtime-session identity; both execute_owned_step and _run_one_step consume that native method; StepExecutor authority-denial and capability suites pass without the class-level assignment.",
        "unlocks": ["planner_goal_overlay", "taskrunner_authority_closure", "stepexecutor_authority_boundary", "ownership_mapping_complete"],
    },
    "Scheduler._plan_goal": {
        "closure_bucket": "planner_goal_overlay",
        "expected_native_owner": "core.tasks.scheduler.Scheduler._plan_goal (native definition at core/tasks/scheduler.py:6914)",
        "owner_endpoint": "Scheduler._plan_goal",
        "native_definition_line": 6914,
        "responsibility": "Own goal-to-plan conversion, including repair-plan recognition, while preserving the scheduler/planner boundary and canonical plan shape.",
        "dependency_edges": [
            {"from": "authority_context", "to": "Scheduler._plan_goal", "relationship": "authority_precondition"},
            {"from": "runtime_gate_compatibility_bridge", "to": "Scheduler._plan_goal", "relationship": "compatibility_precondition"},
            {"from": "Scheduler._plan_goal", "to": "Scheduler._create_task_record", "relationship": "plan_consumer"},
            {"from": "Scheduler._plan_goal", "to": "Scheduler._ensure_executable_steps_for_task", "relationship": "plan_consumer"},
            {"from": "_zero_v702_build_code_chain_repair_plan", "to": "Scheduler._plan_goal", "relationship": "repair_plan_branch"},
            {"from": "Scheduler._plan_goal", "to": "scheduler_contract", "relationship": "goal_to_step_boundary"},
        ],
        "safe_removal_precondition": "The native Scheduler._plan_goal owns the code-chain repair-plan branch or delegates it through one named native planner endpoint; _create_task_record and _ensure_executable_steps_for_task consume the same canonical plan contract; planner, scheduler, repair-plan, and runtime-gate compatibility suites pass without the class-level assignment or predecessor fallback.",
        "unlocks": ["planner_contract", "scheduler_goal_to_step_boundary", "ownership_mapping_complete"],
    },
}

CLOSURE_ORDER = [
    {
        "order": 1,
        "node": "authority_context",
        "blocker_id": "S13E-AP-001",
        "blocked_by": ["runtime_dispatcher_capability", "runtime_capability_provenance", "runtime_session_ownership"],
        "unlocks": ["planner_goal_overlay", "taskrunner_authority_closure", "stepexecutor_authority_boundary"],
    },
    {
        "order": 2,
        "node": "planner_goal_overlay",
        "blocker_id": "S13E-AP-002",
        "blocked_by": ["authority_context", "runtime_gate_compatibility_bridge"],
        "unlocks": ["planner_contract", "scheduler_goal_to_step_boundary", "ownership_mapping_complete"],
    },
    {
        "order": 3,
        "node": "ownership_mapping_complete",
        "blocked_by": ["authority_context", "planner_goal_overlay"],
        "unlocks": ["native_ownership_closure_execution", "freeze_planning"],
    },
]


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required artifact: {relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def confirmed_stage12(stage12: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for domain, values in stage12.get("confirmed_blockers_by_domain", {}).items():
        for item in values:
            record = dict(item)
            record["domain"] = domain
            result[(str(item.get("source_file")), int(item.get("source_line") or 0))] = record
    return result


def mapped_keys(payload: dict[str, Any], item_key: str) -> set[tuple[str, int]]:
    return {
        (str(item.get("source_file")), int(item.get("source_line") or 0))
        for item in payload.get(item_key, [])
        if item.get("validated_classification") == "confirmed_blocker"
    }


def ast_facts(path_text: str, helper: str, owner_member: str) -> dict[str, Any]:
    source = (ROOT / path_text).read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    helper_node = functions.get(helper)
    native_node = functions.get(owner_member)
    if helper_node is None or native_node is None:
        raise SystemExit(f"missing helper/native AST evidence in {path_text}: {helper}/{owner_member}")

    def calls(node: ast.AST) -> list[str]:
        values: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if isinstance(child.func, ast.Name):
                values.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                values.add(child.func.attr)
        return sorted(values)

    callers: list[dict[str, Any]] = []
    for name, node in functions.items():
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == owner_member:
                callers.append({"symbol": name, "source_line": child.lineno})

    predecessor_references = sorted({
        child.id
        for child in ast.walk(helper_node)
        if isinstance(child, ast.Name) and ("ORIGINAL" in child.id or "PREVIOUS" in child.id)
    })
    return {
        "assignment_rhs": helper,
        "helper_definition": {"source_file": path_text, "start_line": helper_node.lineno, "end_line": helper_node.end_lineno},
        "native_definition": {"source_file": path_text, "start_line": native_node.lineno, "end_line": native_node.end_lineno},
        "helper_direct_calls": calls(helper_node),
        "native_direct_calls": calls(native_node),
        "native_callers": sorted(callers, key=lambda item: (item["source_line"], item["symbol"])),
        "predecessor_references": predecessor_references,
    }


def assigned_name(expression: str) -> str:
    right = expression.split("=", 1)[1].strip() if "=" in expression else ""
    return right if right.isidentifier() else ""


def make_record(index: int, item: dict[str, Any]) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "")
    rule = RULES.get(symbol)
    if rule is None:
        raise SystemExit(f"no explicit residual ownership rule for {symbol}")
    source_file = str(item.get("source_file") or "")
    source_line = int(item.get("source_line") or 0)
    helper = assigned_name(str(item.get("expression") or ""))
    owner_member = str(rule["owner_endpoint"]).rsplit(".", 1)[-1]
    facts = ast_facts(source_file, helper, owner_member)
    return {
        "blocker_id": f"S13E-AP-{index:03d}",
        "source_file": source_file,
        "source_line": source_line,
        "symbol": symbol,
        "validated_classification": str(item.get("classification") or ""),
        "domain": str(item.get("domain") or ""),
        "replacement_kind": str(item.get("replacement_kind") or ""),
        "replacement_target": str(item.get("replacement_target") or ""),
        "current_owner": f"class-level assignment in {source_file}:{source_line} via {helper}",
        "expected_native_owner": rule["expected_native_owner"],
        "owner_endpoint": rule["owner_endpoint"],
        "owner_responsibility": rule["responsibility"],
        "closure_bucket": rule["closure_bucket"],
        "why_blocker": str(item.get("why_blocker") or ""),
        "safe_removal_precondition": rule["safe_removal_precondition"],
        "dependency_edges": rule["dependency_edges"],
        "unlock_targets": rule["unlocks"],
        "call_graph": facts,
        "evidence_source": [
            f"{relative(STAGE11B)}#validated_blockers",
            f"{relative(STAGE12)}#{item.get('domain')}",
            f"{source_file}:{source_line}",
            f"{source_file}:{rule['native_definition_line']}",
            f"ast_function:{source_file}::{helper}",
            f"ast_function:{source_file}::{owner_member}",
        ],
    }


def validate(records: list[dict[str, Any]], residual: set[tuple[str, int]], total_confirmed: int, final_keys: set[tuple[str, int]]) -> None:
    if residual != RESIDUAL_KEYS:
        raise SystemExit(f"unexpected Stage13D residual set: {sorted(residual)}")
    if len(records) != 2 or any(item["validated_classification"] != "confirmed_blocker" for item in records):
        raise SystemExit("Stage13E requires exactly two confirmed residual blockers")
    if len(final_keys) != total_confirmed or total_confirmed != 113:
        raise SystemExit(f"final mapping is not 113/113: {len(final_keys)}/{total_confirmed}")
    required = (
        "blocker_id", "source_file", "symbol", "current_owner", "expected_native_owner",
        "owner_endpoint", "safe_removal_precondition", "dependency_edges", "call_graph", "evidence_source",
    )
    for item in records:
        missing = [key for key in required if not item.get(key)]
        if missing:
            raise SystemExit(f"{item['blocker_id']} missing evidence fields: {missing}")
        if not item["call_graph"]["native_callers"]:
            raise SystemExit(f"{item['blocker_id']} has no native caller evidence")


def write_report(payload: dict[str, Any], summary: dict[str, Any]) -> None:
    lines = [
        "# Authority + Planner Residual Closure ??Stage13E", "",
        "Discovery and ownership mapping only. Production runtime and tests were not modified; no blocker was fixed.", "",
        "## Result", "",
        f"- Final ownership mapping: **{summary['mapped_blockers']} / {summary['total_confirmed_blockers']} mapped**",
        f"- Ownership mapping completion: {summary['ownership_mapping_percent']}%",
        f"- Residual blockers mapped by Stage13E: {summary['residual_blockers_mapped']}",
        f"- Remaining unmapped blockers: {summary['remaining_unmapped_blockers']}",
        "- Production runtime touched: false",
        "- Tests modified: false", "",
        "## Residual inventory", "",
    ]
    for item in payload["residual_items"]:
        graph = item["call_graph"]
        lines.extend([
            f"### {item['blocker_id']} ??`{item['symbol']}`", "",
            f"- Source: `{item['source_file']}:{item['source_line']}`",
            f"- Domain: `{item['domain']}`",
            f"- Classification: `{item['validated_classification']}`",
            f"- Current owner: {item['current_owner']}",
            f"- Expected native owner: `{item['expected_native_owner']}`",
            f"- Responsibility: {item['owner_responsibility']}",
            f"- Why blocker: {item['why_blocker']}",
            f"- Safe-removal precondition: {item['safe_removal_precondition']}",
            f"- Assignment RHS: `{graph['assignment_rhs']}`",
            "- Native callers: " + ", ".join("`{}:{}`".format(x["symbol"], x["source_line"]) for x in graph["native_callers"]),
            f"- Predecessor references: {', '.join(f'`{x}`' for x in graph['predecessor_references']) or 'none'}", "",
            "Dependency edges:", "",
        ])
        for edge in item["dependency_edges"]:
            lines.append(f"- `{edge['from']}` ??`{edge['to']}` (`{edge['relationship']}`)")
        lines.append("")
    lines.extend(["## Closure order", ""])
    for entry in payload["closure_order"]:
        lines.append(f"{entry['order']}. `{entry['node']}` ??blocked by {', '.join(f'`{x}`' for x in entry['blocked_by'])}; unlocks {', '.join(f'`{x}`' for x in entry['unlocks'])}")
    lines.extend([
        "", "## Aggregate AER mapping", "",
        f"- Stage13A distinct confirmed mappings: {summary['stage_mapping_counts']['stage13a']}",
        f"- Stage13B distinct confirmed mappings: {summary['stage_mapping_counts']['stage13b']}",
        f"- Stage13C distinct confirmed mappings: {summary['stage_mapping_counts']['stage13c']}",
        f"- Stage13D confirmed inventory mappings: {summary['stage_mapping_counts']['stage13d']} ({summary['stage13d_new_distinct_mappings']} new distinct)",
        f"- Stage13E new distinct mappings: {summary['stage_mapping_counts']['stage13e']}",
        f"- Deduplicated total: **{summary['mapped_blockers']} / {summary['total_confirmed_blockers']}**", "",
        "## Validation", "",
        "- Generator: pass",
        "- Python compile/schema validation: pass",
        "- Runtime tests: not run; Stage13E changes no runtime or test code",
        "- Blocker fixes applied: none",
        "- Production runtime touched: false", "",
    ])
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    load(STAGE11B)
    stage12 = load(STAGE12)
    stage12_summary = load(STAGE12_SUMMARY)
    stage13a = load(STAGE13A)
    stage13b = load(STAGE13B)
    stage13c = load(STAGE13C)
    stage13d = load(STAGE13D)

    all_confirmed = confirmed_stage12(stage12)
    keys_a = mapped_keys(stage13a, "scheduler_items")
    keys_b = mapped_keys(stage13b, "taskrunner_items")
    keys_c = mapped_keys(stage13c, "stepexecutor_items")
    keys_d = mapped_keys(stage13d, "repairchain_items")
    prior_keys = keys_a | keys_b | keys_c | keys_d
    residual = set(all_confirmed) - prior_keys
    raw = [all_confirmed[key] for key in sorted(residual)]
    records = [make_record(index, item) for index, item in enumerate(raw, 1)]
    keys_e = {(item["source_file"], item["source_line"]) for item in records}
    final_keys = prior_keys | keys_e
    total_confirmed = int(stage12_summary.get("classification_counts", {}).get("confirmed_blocker") or 0)
    validate(records, residual, total_confirmed, final_keys)

    payload = {
        "stage": "Authority + Planner Residual Closure Stage13E",
        "scope": "discovery_and_ownership_mapping_only",
        "production_runtime_modified": False,
        "tests_modified": False,
        "blockers_fixed": False,
        "inputs": [relative(path) for path in (STAGE11B, STAGE12, STAGE12_SUMMARY, STAGE13A, STAGE13B, STAGE13C, STAGE13D)],
        "residual_items": records,
        "ownership_map": {
            "authority_context": records[0]["owner_endpoint"],
            "planner_goal_overlay": records[1]["owner_endpoint"],
        },
        "dependency_graph": {
            "authority_context": records[0]["dependency_edges"],
            "planner_goal_overlay": records[1]["dependency_edges"],
            "cross_residual_edges": [
                {"from": "authority_context", "to": "planner_goal_overlay", "relationship": "closure_precondition"},
                {"from": "planner_goal_overlay", "to": "ownership_mapping_complete", "relationship": "final_mapping_unlock"},
            ],
        },
        "closure_order": CLOSURE_ORDER,
        "mapping_closure": {
            "prior_distinct_mapped": len(prior_keys),
            "stage13e_new_distinct_mapped": len(keys_e),
            "final_distinct_mapped": len(final_keys),
            "total_confirmed_blockers": total_confirmed,
            "remaining_unmapped": [],
            "ownership_mapping_percent": 100.0,
            "status": "113 / 113 mapped",
        },
        "unresolved_ambiguities": [],
        "evidence_standard": "source file + symbol + AST call graph + explicit dependency graph",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "stage": "Authority + Planner Residual Closure Stage13E",
        "residual_blockers_mapped": len(records),
        "authority_context_blockers": 1,
        "planner_goal_overlay_blockers": 1,
        "mapped_blockers": len(final_keys),
        "total_confirmed_blockers": total_confirmed,
        "remaining_unmapped_blockers": 0,
        "ownership_mapping_percent": 100.0,
        "mapping_status": "113 / 113 mapped",
        "stage_mapping_counts": {
            "stage13a": len(keys_a),
            "stage13b": len(keys_b),
            "stage13c": len(keys_c),
            "stage13d": len(keys_d),
            "stage13e": len(keys_e),
        },
        "stage13d_new_distinct_mappings": len(keys_d - (keys_a | keys_b | keys_c)),
        "closure_order": CLOSURE_ORDER,
        "unresolved_ambiguities": 0,
        "production_runtime_touched": False,
        "tests_touched": False,
        "blockers_fixed": False,
        "validation": {"generator": "pass", "compile_and_schema": "pass", "runtime_tests": "not_run_no_runtime_change"},
        "outputs": {"inventory": relative(OUTPUT), "summary": relative(SUMMARY), "report": relative(REPORT)},
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(payload, summary)

    print("residual_blockers_mapped: 2")
    print(f"final_mapping: {len(final_keys)} / {total_confirmed}")
    print("remaining_unmapped: 0")
    print("production_runtime_touched: false")
    print("tests_touched: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
