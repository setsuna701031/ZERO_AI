from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
STAGE12_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12.json"
STAGE12_SUMMARY_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12_summary.json"
STAGE12_REPORT_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12_report.md"
OUTPUT_PATH = OUT_DIR / "scheduler_native_ownership_closure_stage13a.json"
SUMMARY_PATH = OUT_DIR / "scheduler_native_ownership_closure_stage13a_summary.json"
REPORT_PATH = OUT_DIR / "scheduler_native_ownership_closure_stage13a_report.md"

SCHEDULER_DOMAIN = "scheduler_contract"
EXPECTED_TOTAL = 52
EXPECTED_CONFIRMED = 45
CLASSIFICATIONS = (
    "confirmed_blocker",
    "compatibility_bridge",
    "false_positive",
    "non_mainline_issue",
)
BUCKETS = (
    "scheduler_state_ownership",
    "scheduler_queue_ownership",
    "scheduler_dispatch_ownership",
    "scheduler_retry_or_recovery_boundary",
    "scheduler_runtime_gate_dependency",
    "scheduler_legacy_metadata_dependency",
    "scheduler_test_or_validation_only",
    "scheduler_non_mainline_issue",
)

CLOSURE_ORDER = (
    {
        "order": 1,
        "bucket": "scheduler_legacy_metadata_dependency",
        "blocked_by": [],
        "unlocks": ["scheduler_state_ownership"],
    },
    {
        "order": 2,
        "bucket": "scheduler_state_ownership",
        "blocked_by": ["scheduler_legacy_metadata_dependency"],
        "unlocks": ["scheduler_queue_ownership"],
    },
    {
        "order": 3,
        "bucket": "scheduler_queue_ownership",
        "blocked_by": ["scheduler_state_ownership"],
        "unlocks": ["scheduler_runtime_gate_dependency", "scheduler_dispatch_ownership"],
    },
    {
        "order": 4,
        "bucket": "scheduler_runtime_gate_dependency",
        "blocked_by": ["scheduler_queue_ownership", "runtime_gate_compatibility_bridge"],
        "unlocks": ["scheduler_dispatch_ownership"],
    },
    {
        "order": 5,
        "bucket": "scheduler_dispatch_ownership",
        "blocked_by": ["scheduler_queue_ownership", "scheduler_runtime_gate_dependency"],
        "unlocks": ["scheduler_retry_or_recovery_boundary"],
    },
    {
        "order": 6,
        "bucket": "scheduler_retry_or_recovery_boundary",
        "blocked_by": ["scheduler_dispatch_ownership", "repair_chain"],
        "unlocks": ["scheduler_test_or_validation_only", "scheduler_non_mainline_issue"],
    },
    {
        "order": 7,
        "bucket": "scheduler_test_or_validation_only",
        "blocked_by": [
            "scheduler_state_ownership",
            "scheduler_queue_ownership",
            "scheduler_dispatch_ownership",
            "scheduler_retry_or_recovery_boundary",
        ],
        "unlocks": ["scheduler_non_mainline_issue"],
    },
    {
        "order": 8,
        "bucket": "scheduler_non_mainline_issue",
        "blocked_by": ["scheduler_test_or_validation_only"],
        "unlocks": [],
    },
)

RESPONSIBILITIES = {
    "scheduler_state_ownership": "Own scheduler task creation and durable repository-task state transitions.",
    "scheduler_queue_ownership": "Own queue hygiene, tick advancement, requeue decisions, and queue-facing state.",
    "scheduler_dispatch_ownership": "Own run-one-step dispatch, dispatch result handling, and scheduler execution orchestration.",
    "scheduler_retry_or_recovery_boundary": "Own the scheduler side of retry/recovery handoff without absorbing repair-chain ownership.",
    "scheduler_runtime_gate_dependency": "Consume the canonical runtime gate and authority contract without defining a competing gate.",
    "scheduler_legacy_metadata_dependency": "Retire or retain legacy scheduler metadata only after proving it is non-behavioral.",
    "scheduler_test_or_validation_only": "Retain validation-only evidence without promoting it into runtime ownership.",
    "scheduler_non_mainline_issue": "Track scheduler review and observability surfaces outside the execution mainline.",
}

SAFE_PRECONDITIONS = {
    "scheduler_state_ownership": "Native Scheduler methods own task creation and repository-task transitions, with state helper and no-direct-mutation contracts passing.",
    "scheduler_queue_ownership": "Native queue cleanup, tick, and requeue behavior preserves queue transition and scheduler lifecycle contracts.",
    "scheduler_dispatch_ownership": "One native Scheduler dispatch path owns run_one_step and result finalization across TaskRunner and StepExecutor boundaries.",
    "scheduler_retry_or_recovery_boundary": "Retry and recovery ownership is explicit at the scheduler/repair-chain boundary, including failure and resumability contracts.",
    "scheduler_runtime_gate_dependency": "The canonical runtime gate and authority propagation APIs cover all scheduler entry points without compatibility assignments.",
    "scheduler_legacy_metadata_dependency": "Metadata is proven non-executable and no runtime/test consumer relies on the legacy build marker for behavior.",
    "scheduler_test_or_validation_only": "Validation evidence remains covered by native ownership suites after runtime replacement inventory retirement.",
    "scheduler_non_mainline_issue": "Review/observability APIs have a named native owner and remain covered independently of mainline scheduler closure.",
}

BUCKET_ACTIONS = {
    "scheduler_state_ownership": "Plan native state-method promotion, then retire class-level replacement only after state contract parity.",
    "scheduler_queue_ownership": "Consolidate queue transitions under native Scheduler ownership and close duplicate tick/cleanup assignments in order.",
    "scheduler_dispatch_ownership": "Order run_one_step overlays chronologically, identify the final contract, and plan one native dispatch implementation.",
    "scheduler_retry_or_recovery_boundary": "Document the scheduler-to-repair handoff and close only the scheduler side after repair-chain prerequisites land.",
    "scheduler_runtime_gate_dependency": "Replace scheduler-local gate assumptions with the canonical runtime gate contract after upstream bridge closure.",
    "scheduler_legacy_metadata_dependency": "Keep as false positive metadata unless consumer evidence proves behavioral coupling.",
    "scheduler_test_or_validation_only": "Retain as test evidence and exclude from production blocker retirement work.",
    "scheduler_non_mainline_issue": "Preserve in the Non-Mainline Issue Report and assign a separate native ownership follow-up.",
}


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required Stage12 artifact: {relative(path)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return value


def stage12_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    confirmed = payload.get("confirmed_blockers_by_domain", {}).get(SCHEDULER_DOMAIN, [])
    if not isinstance(confirmed, list):
        raise SystemExit("Stage12 scheduler confirmed-blocker bucket must be a list")
    items.extend(item for item in confirmed if isinstance(item, dict))
    for classification in CLASSIFICATIONS[1:]:
        values = payload.get(classification, [])
        if not isinstance(values, list):
            raise SystemExit(f"Stage12 {classification} bucket must be a list")
        items.extend(
            item for item in values
            if isinstance(item, dict) and item.get("domain") == SCHEDULER_DOMAIN
        )
    return sorted(items, key=lambda item: (str(item.get("source_file")), int(item.get("source_line") or 0)))


def classify_bucket(item: dict[str, Any]) -> tuple[str, str | None]:
    classification = str(item.get("classification") or "")
    symbol = str(item.get("symbol") or "")
    expression = str(item.get("expression") or "")
    source = str(item.get("source_file") or "")
    member = symbol.rsplit(".", 1)[-1]

    if classification == "non_mainline_issue":
        return "scheduler_non_mainline_issue", None
    if source.startswith("tests/"):
        return "scheduler_test_or_validation_only", None
    if member in {"SCHEDULER_BUILD", "RETRYING_REPAIR_BRIDGE_VERSION"}:
        return "scheduler_legacy_metadata_dependency", None
    if "runtime_gate" in f"{symbol} {expression}" or "authority" in f"{symbol} {expression}".lower():
        return "scheduler_runtime_gate_dependency", None
    if any(token in member for token in ("retry", "repair", "recovery", "resum", "failure")):
        return "scheduler_retry_or_recovery_boundary", None
    if member in {"_handle_missing_repo_task", "_handle_run_one_step_exception"}:
        return "scheduler_retry_or_recovery_boundary", None
    if member in {
        "_mark_repo_task_finished",
        "_mark_repo_task_failed",
        "_mark_repo_task_queued",
        "create_task",
        "_create_task_record",
        "_try_force_repo_edit_at_create_task",
        "CODE_CHAIN_WORKFLOW_STEP_TYPES",
    }:
        return "scheduler_state_ownership", None
    if member in {
        "cleanup_task_queue_hygiene",
        "tick",
        "_sync_runner_result_and_requeue_if_ready",
    }:
        return "scheduler_queue_ownership", None
    if member in {
        "run_one_step",
        "_execute_simple_step",
        "_run_simple_task_tick",
        "_handle_dispatch_result",
        "_handle_missing_repo_task",
        "_handle_run_one_step_exception",
        "_finalize_dispatched_task",
    }:
        return "scheduler_dispatch_ownership", None
    return "scheduler_test_or_validation_only", f"no explicit scheduler bucket rule for {symbol}"


def cross_domain_dependencies(item: dict[str, Any], bucket: str) -> list[str]:
    member = str(item.get("symbol") or "").rsplit(".", 1)[-1]
    dependencies: set[str] = set()
    if bucket == "scheduler_runtime_gate_dependency":
        dependencies.update(("authority_contract", "runtime_gate_compatibility_bridge"))
    if bucket == "scheduler_retry_or_recovery_boundary":
        dependencies.add("repair_chain")
    if bucket == "scheduler_dispatch_ownership":
        dependencies.update(("taskrunner_contract", "step_executor_contract"))
    if member in {"_handle_missing_repo_task", "_handle_run_one_step_exception"}:
        dependencies.add("repair_chain")
    if member in {"_sync_runner_result_and_requeue_if_ready", "_run_simple_task_tick"}:
        dependencies.add("taskrunner_contract")
    if member in {"create_task", "_create_task_record", "_try_force_repo_edit_at_create_task"}:
        dependencies.add("planner_contract")
    return sorted(dependencies)


def dependency_edges(bucket: str, cross_domains: list[str]) -> list[dict[str, str]]:
    closure = next(item for item in CLOSURE_ORDER if item["bucket"] == bucket)
    edges = [
        {"direction": "upstream", "domain": dependency, "relationship": "blocked_by"}
        for dependency in closure["blocked_by"]
    ]
    edges.extend(
        {"direction": "downstream", "domain": dependency, "relationship": "unlocks"}
        for dependency in closure["unlocks"]
    )
    known = {(edge["direction"], edge["domain"]) for edge in edges}
    for dependency in cross_domains:
        if ("upstream", dependency) not in known:
            edges.append({"direction": "upstream", "domain": dependency, "relationship": "cross_domain_dependency"})
    return edges


def expected_owner(item: dict[str, Any]) -> str:
    member = str(item.get("symbol") or "").rsplit(".", 1)[-1]
    return f"core.tasks.scheduler.Scheduler.{member} (native definition)"


def current_owner(item: dict[str, Any]) -> str:
    source = str(item.get("source_file") or "")
    line = int(item.get("source_line") or 0)
    return f"class-level assignment in {source}:{line}"


def make_record(index: int, item: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    bucket, ambiguity = classify_bucket(item)
    cross_domains = cross_domain_dependencies(item, bucket)
    order = next(entry["order"] for entry in CLOSURE_ORDER if entry["bucket"] == bucket)
    stage12_precondition = str(item.get("safe_removal_precondition") or "").strip()
    stage13a_precondition = SAFE_PRECONDITIONS[bucket]
    combined_precondition = (
        f"{stage12_precondition} Stage13A scheduler condition: {stage13a_precondition}"
        if stage12_precondition
        else stage13a_precondition
    )
    record = {
        "blocker_id": f"S13A-SCHED-{index:03d}",
        "source_file": str(item.get("source_file") or ""),
        "source_line": int(item.get("source_line") or 0),
        "symbol": str(item.get("symbol") or ""),
        "validated_classification": str(item.get("classification") or ""),
        "replacement_kind": str(item.get("replacement_kind") or ""),
        "replacement_target": str(item.get("replacement_target") or ""),
        "current_owner": current_owner(item),
        "expected_native_owner": expected_owner(item),
        "scheduler_responsibility": RESPONSIBILITIES[bucket],
        "why_blocker": str(item.get("why_blocker") or ""),
        "safe_removal_precondition": combined_precondition,
        "dependency_edges": dependency_edges(bucket, cross_domains),
        "cross_domain_dependencies": cross_domains,
        "critical_chain_position": {
            "stage12_order": int(item.get("critical_chain_order") or 0),
            "stage13a_closure_order": order,
            "bucket": bucket,
        },
        "recommended_closure_action": BUCKET_ACTIONS[bucket],
        "evidence_source": [
            f"{relative(STAGE12_PATH)}#{item.get('classification')}",
            f"{item.get('source_file')}:{item.get('source_line')}",
        ],
        "closure_bucket": bucket,
    }
    return record, ambiguity


def count_map(keys: Iterable[str], values: Iterable[str]) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts[key] for key in keys}


def validate_records(records: list[dict[str, Any]], stage12_summary: dict[str, Any]) -> None:
    expected_scheduler = int(stage12_summary.get("domain_counts", {}).get(SCHEDULER_DOMAIN, -1))
    expected_confirmed = int(stage12_summary.get("confirmed_blocker_domain_counts", {}).get(SCHEDULER_DOMAIN, -1))
    if len(records) != expected_scheduler:
        raise SystemExit(f"scheduler count mismatch: records={len(records)}, Stage12={expected_scheduler}")
    if len(records) != EXPECTED_TOTAL or expected_scheduler != EXPECTED_TOTAL:
        raise SystemExit(f"expected {EXPECTED_TOTAL} scheduler records")
    confirmed = sum(record["validated_classification"] == "confirmed_blocker" for record in records)
    if confirmed != expected_confirmed or confirmed != EXPECTED_CONFIRMED:
        raise SystemExit(f"confirmed scheduler mismatch: records={confirmed}, Stage12={expected_confirmed}")
    required = ("source_file", "symbol", "replacement_target", "safe_removal_precondition")
    for record in records:
        missing = [field for field in required if not record.get(field)]
        if missing:
            raise SystemExit(f"{record['blocker_id']} missing required fields: {missing}")
    stage12_non_mainline = sum(
        record["validated_classification"] == "non_mainline_issue" for record in records
    )
    preserved_non_mainline = sum(
        record["closure_bucket"] == "scheduler_non_mainline_issue" for record in records
    )
    if stage12_non_mainline != preserved_non_mainline:
        raise SystemExit("scheduler non-mainline issues were not preserved")


def report_record(record: dict[str, Any]) -> list[str]:
    dependencies = ", ".join(f"`{item}`" for item in record["cross_domain_dependencies"]) or "none"
    return [
        f"- `{record['blocker_id']}` — `{record['source_file']}:{record['source_line']}` — `{record['symbol']}`",
        f"  - Classification: `{record['validated_classification']}`; replacement: `{record['replacement_target']}`",
        f"  - Current owner: {record['current_owner']}",
        f"  - Expected native owner: `{record['expected_native_owner']}`",
        f"  - Responsibility: {record['scheduler_responsibility']}",
        f"  - Why blocker/disposition: {record['why_blocker']}",
        f"  - Safe removal precondition: {record['safe_removal_precondition']}",
        f"  - Cross-domain dependencies: {dependencies}",
        f"  - Recommended action: {record['recommended_closure_action']}",
    ]


def write_report(records: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines = [
        "# Scheduler Native Ownership Closure Inventory — Stage13A",
        "",
        "Inventory, dependency analysis, and closure ordering only. No blocker was removed and no production runtime file was modified.",
        "",
        "## Summary",
        "",
        f"- Total scheduler items: {summary['total_scheduler_items']}",
        f"- Confirmed scheduler blockers: {summary['confirmed_scheduler_blockers']}",
        f"- Compatibility bridge scheduler items: {summary['compatibility_bridge_scheduler_items']}",
        f"- False-positive scheduler items: {summary['false_positive_scheduler_items']}",
        f"- Non-mainline scheduler items: {summary['non_mainline_scheduler_items']}",
        f"- Unresolved ambiguities: {summary['unresolved_ambiguity_count']}",
        "- Production runtime touched: false",
        "",
        "## Bucket counts",
        "",
    ]
    for bucket, count in summary["bucket_counts"].items():
        lines.append(f"- `{bucket}`: {count}")

    lines.extend(["", "## Closure order and dependency graph", ""])
    for entry in summary["closure_order"]:
        blocked = ", ".join(f"`{value}`" for value in entry["blocked_by"]) or "none"
        unlocks = ", ".join(f"`{value}`" for value in entry["unlocks"]) or "none"
        lines.append(f"{entry['order']}. `{entry['bucket']}` — blocked by: {blocked}; unlocks: {unlocks}")

    lines.extend(["", "## Cross-domain dependencies", ""])
    for domain, count in summary["cross_domain_dependency_counts"].items():
        lines.append(f"- `{domain}`: {count}")
    if not summary["cross_domain_dependency_counts"]:
        lines.append("- None.")

    lines.extend(["", "## Scheduler closure buckets", ""])
    for bucket in BUCKETS:
        selected = [record for record in records if record["closure_bucket"] == bucket]
        lines.extend([f"### {bucket} ({len(selected)})", ""])
        if not selected:
            lines.append("- None.")
        for record in selected:
            lines.extend(report_record(record))
        lines.append("")

    non_mainline = [record for record in records if record["validated_classification"] == "non_mainline_issue"]
    lines.extend(["## Non-Mainline Issue Report", ""])
    lines.append("Scheduler-domain non-mainline issues are preserved below. No additional outside-scheduler issue was discovered during Stage13A inventory generation.")
    lines.append("")
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
    if not STAGE12_REPORT_PATH.exists():
        raise SystemExit(f"missing required Stage12 artifact: {relative(STAGE12_REPORT_PATH)}")

    raw_items = stage12_items(stage12)
    records: list[dict[str, Any]] = []
    ambiguities: list[dict[str, str]] = []
    for index, item in enumerate(raw_items, 1):
        record, ambiguity = make_record(index, item)
        records.append(record)
        if ambiguity:
            ambiguities.append({"blocker_id": record["blocker_id"], "reason": ambiguity})
    validate_records(records, stage12_summary)

    classification_counts = count_map(
        CLASSIFICATIONS, (record["validated_classification"] for record in records)
    )
    bucket_counts = count_map(BUCKETS, (record["closure_bucket"] for record in records))
    cross_domain_counts = Counter(
        dependency
        for record in records
        for dependency in record["cross_domain_dependencies"]
    )
    by_bucket = {
        bucket: [record for record in records if record["closure_bucket"] == bucket]
        for bucket in BUCKETS
    }
    graph = {
        "nodes": [
            {
                **entry,
                "item_count": bucket_counts[entry["bucket"]],
                "upstream_dependencies": entry["blocked_by"],
                "downstream_dependencies": entry["unlocks"],
            }
            for entry in CLOSURE_ORDER
        ],
        "edges": [
            {"from": dependency, "to": entry["bucket"], "relationship": "blocked_by"}
            for entry in CLOSURE_ORDER
            for dependency in entry["blocked_by"]
        ] + [
            {"from": entry["bucket"], "to": unlocked, "relationship": "unlocks"}
            for entry in CLOSURE_ORDER
            for unlocked in entry["unlocks"]
        ],
    }

    payload = {
        "stage": "Scheduler Native Ownership Closure Inventory Stage13A",
        "scope": SCHEDULER_DOMAIN,
        "production_runtime_modified": False,
        "inputs": [relative(STAGE12_PATH), relative(STAGE12_SUMMARY_PATH), relative(STAGE12_REPORT_PATH)],
        "total_scheduler_items": len(records),
        "classification_counts": classification_counts,
        "bucket_counts": bucket_counts,
        "scheduler_items": records,
        "closure_buckets": by_bucket,
        "dependency_graph": graph,
        "cross_domain_dependency_counts": dict(sorted(cross_domain_counts.items())),
        "unresolved_ambiguities": ambiguities,
        "outside_scheduler_non_mainline_issues_discovered": [],
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "stage": "Scheduler Native Ownership Closure Inventory Stage13A",
        "total_scheduler_items": len(records),
        "confirmed_scheduler_blockers": classification_counts["confirmed_blocker"],
        "compatibility_bridge_scheduler_items": classification_counts["compatibility_bridge"],
        "false_positive_scheduler_items": classification_counts["false_positive"],
        "non_mainline_scheduler_items": classification_counts["non_mainline_issue"],
        "bucket_counts": bucket_counts,
        "closure_order": list(CLOSURE_ORDER),
        "cross_domain_dependency_counts": dict(sorted(cross_domain_counts.items())),
        "unresolved_ambiguity_count": len(ambiguities),
        "outside_scheduler_non_mainline_issue_count": 0,
        "production_runtime_touched": False,
        "outputs": {
            "inventory": relative(OUTPUT_PATH),
            "summary": relative(SUMMARY_PATH),
            "report": relative(REPORT_PATH),
        },
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(records, summary)

    print(f"scheduler_items: {len(records)}")
    print(f"classification_counts: {classification_counts}")
    print(f"bucket_counts: {bucket_counts}")
    print(f"cross_domain_dependency_counts: {dict(sorted(cross_domain_counts.items()))}")
    print(f"unresolved_ambiguity_count: {len(ambiguities)}")
    print("production_runtime_touched: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
