from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
VALIDATION_PATH = OUT_DIR / "runtime_blocker_validation.json"
VALIDATION_SUMMARY_PATH = OUT_DIR / "runtime_blocker_validation_summary.json"
VALIDATION_REPORT_PATH = OUT_DIR / "runtime_blocker_validation_report.md"
OUTPUT_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12.json"
SUMMARY_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12_summary.json"
REPORT_PATH = OUT_DIR / "runtime_blocker_domain_split_stage12_report.md"

EXPECTED_TOTAL = 142
OUTPUT_CLASSES = (
    "confirmed_blocker",
    "compatibility_bridge",
    "false_positive",
    "non_mainline_issue",
)
DOMAIN_ORDER = (
    "authority_contract",
    "runtime_gate_compatibility_bridge",
    "planner_contract",
    "scheduler_contract",
    "taskrunner_contract",
    "step_executor_contract",
    "repair_chain",
)
CRITICAL_CHAINS = (
    "authority_chain",
    "runtime_gate_chain",
    "planner_chain",
    "scheduler_chain",
    "task_runner_chain",
    "step_executor_chain",
    "recovery_chain",
)

DOMAIN_DEPENDENCIES = {
    "authority_contract": [],
    "runtime_gate_compatibility_bridge": ["authority_contract"],
    "planner_contract": ["authority_contract", "runtime_gate_compatibility_bridge"],
    "scheduler_contract": ["planner_contract"],
    "taskrunner_contract": ["scheduler_contract", "runtime_gate_compatibility_bridge"],
    "step_executor_contract": ["taskrunner_contract", "authority_contract"],
    "repair_chain": [
        "scheduler_contract",
        "taskrunner_contract",
        "step_executor_contract",
    ],
}

SAFE_REMOVAL_PRECONDITIONS = {
    "authority_contract": "Native authority decisions and capability propagation cover every affected entry point with authority contract tests passing.",
    "runtime_gate_compatibility_bridge": "All callers use one native runtime gate and canonical payload/result shape; bridge behavior is contract-tested before removal.",
    "planner_contract": "Native planning owns goal-to-step creation and preserves planner/scheduler boundary contracts without replacement assignment.",
    "scheduler_contract": "Native scheduler dispatch, queue transition, and task finalization paths pass ownership and mainline freeze suites.",
    "taskrunner_contract": "Native TaskRunner owns task/tick execution, result persistence, and failure classification across scheduler boundaries.",
    "step_executor_contract": "Native StepExecutor owns handler registration, execution dispatch, and result adaptation with no class-level grafts.",
    "repair_chain": "Native recovery owns repair eligibility, duplicate suppression, last-step observation, and repair workflow routing end to end.",
}


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing Stage11B artifact: {relative(path)}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {relative(path)}")
    return payload


def normalized_class(item: dict[str, Any]) -> str:
    value = str(item.get("validated_classification") or "")
    if value == "downgrade_to_compatibility_bridge":
        return "compatibility_bridge"
    if value in OUTPUT_CLASSES:
        return value
    raise SystemExit(f"unsupported Stage11B classification {value!r} for {item.get('chain_target')!r}")


def item_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("chain_target", "expression", "owner_domain")
    ).lower()


def domain_for(item: dict[str, Any], classification: str) -> str:
    text = item_text(item)
    target = str(item.get("chain_target") or "").lower()
    owner = str(item.get("owner_domain") or "").lower()

    if classification == "compatibility_bridge" or "runtime_gate" in text:
        return "runtime_gate_compatibility_bridge"
    if "authority" in text:
        return "authority_contract"
    if "plan_goal" in target or "planner" in text:
        return "planner_contract"
    repair_tokens = (
        "repair",
        "recovery",
        "replay",
        "duplicate_repair_task",
        "zero_v800",
        "represents_failed_step_observation",
    )
    if any(token in text for token in repair_tokens):
        return "repair_chain"
    if owner == "step_executor":
        return "step_executor_contract"
    if owner == "task_runner":
        return "taskrunner_contract"
    return "scheduler_contract"


def chain_for(domain: str) -> str:
    return {
        "authority_contract": "authority_chain",
        "runtime_gate_compatibility_bridge": "runtime_gate_chain",
        "planner_contract": "planner_chain",
        "scheduler_contract": "scheduler_chain",
        "taskrunner_contract": "task_runner_chain",
        "step_executor_contract": "step_executor_chain",
        "repair_chain": "recovery_chain",
    }[domain]


def replacement_target(item: dict[str, Any]) -> str:
    owner = str(item.get("suspected_native_owner") or "manual ownership resolution required")
    symbol = str(item.get("chain_target") or "")
    member = symbol.rsplit(".", 1)[-1] if "." in symbol else symbol
    if owner == "manual ownership resolution required" or not member:
        return owner
    return f"{owner}.{member}"


def why(item: dict[str, Any], classification: str) -> str:
    reason = str(item.get("reason") or "Stage11B supplied no rationale")
    if classification == "confirmed_blocker":
        return reason
    if classification == "compatibility_bridge":
        return f"Bridge blocker: {reason}"
    if classification == "false_positive":
        return f"Not an executable blocker: {reason}"
    return f"Non-mainline ownership issue retained for closure: {reason}"


def split_item(item: dict[str, Any]) -> dict[str, Any]:
    classification = normalized_class(item)
    domain = domain_for(item, classification)
    order = DOMAIN_ORDER.index(domain) + 1
    return {
        "classification": classification,
        "domain": domain,
        "source_file": str(item.get("source_path") or ""),
        "source_line": int(item.get("source_line") or 0),
        "symbol": str(item.get("chain_target") or ""),
        "why_blocker": why(item, classification),
        "replacement_target": replacement_target(item),
        "safe_removal_precondition": SAFE_REMOVAL_PRECONDITIONS[domain],
        "critical_chain": chain_for(domain),
        "critical_chain_order": order,
        "critical_chain_order_label": f"{order}. {domain}",
        "depends_on_domains": DOMAIN_DEPENDENCIES[domain],
        "stage11b_classification": str(item.get("validated_classification") or ""),
        "stage11b_action": str(item.get("action") or ""),
        "replacement_kind": str(item.get("replacement_kind") or ""),
        "expression": str(item.get("expression") or ""),
    }


def assert_corrections(items: list[dict[str, Any]]) -> None:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_symbol[item["symbol"]].append(item)

    required = {
        "TaskRunner._runtime_gate_consolidated": "compatibility_bridge",
        "Scheduler._find_active_duplicate_repair_task": "confirmed_blocker",
        "TaskRunner._zero_v800_last_step_type": "confirmed_blocker",
    }
    for symbol, expected in required.items():
        matches = by_symbol.get(symbol, [])
        if not matches:
            raise SystemExit(f"required Stage11B correction target missing: {symbol}")
        if any(item["classification"] != expected for item in matches):
            actual = sorted({item["classification"] for item in matches})
            raise SystemExit(f"{symbol} must be {expected}, found {actual}")


def count_map(keys: Iterable[str], values: Iterable[str]) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts[key] for key in keys}


def report_item(item: dict[str, Any]) -> list[str]:
    return [
        f"- `{item['source_file']}:{item['source_line']}` — `{item['symbol']}`",
        f"  - Why blocker/disposition: {item['why_blocker']}",
        f"  - Replacement target: `{item['replacement_target']}`",
        f"  - Safe removal precondition: {item['safe_removal_precondition']}",
        f"  - Critical chain order: {item['critical_chain_order_label']}",
    ]


def write_report(items: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines = [
        "# Runtime Blocker Domain Split — Stage12",
        "",
        "Domain decomposition and ordering only. No blocker was repaired and no production runtime file was modified by this stage.",
        "",
        "## Summary",
        "",
        f"- Total blockers processed: {summary['total_blockers_processed']}",
        f"- Confirmed blockers: {summary['classification_counts']['confirmed_blocker']}",
        f"- Compatibility bridges: {summary['compatibility_bridge_count']}",
        f"- False positives: {summary['false_positive_count']}",
        f"- Non-mainline issues: {summary['non_mainline_issue_count']}",
        "- Production runtime touched: no",
        "",
        "## Critical-chain order",
        "",
    ]
    for entry in summary["critical_chain_order"]:
        dependencies = ", ".join(f"`{value}`" for value in entry["depends_on"]) or "none"
        lines.append(
            f"{entry['order']}. `{entry['domain']}` (`{entry['chain']}`; {entry['count']} items; depends on: {dependencies})"
        )

    lines.extend(["", "## Domain counts", ""])
    for domain, count in summary["domain_counts"].items():
        confirmed_count = summary["confirmed_blocker_domain_counts"][domain]
        lines.append(f"- `{domain}`: {count} total; {confirmed_count} confirmed blockers")

    confirmed = [item for item in items if item["classification"] == "confirmed_blocker"]
    lines.extend(["", "## Confirmed Blockers by Domain", ""])
    for domain in DOMAIN_ORDER:
        domain_items = [item for item in confirmed if item["domain"] == domain]
        lines.extend([f"### {domain} ({len(domain_items)})", ""])
        if not domain_items:
            lines.append("- None.")
        for item in domain_items:
            lines.extend(report_item(item))
        lines.append("")

    sections = (
        ("compatibility_bridge", "Compatibility Bridge Report"),
        ("false_positive", "False Positive Report"),
        ("non_mainline_issue", "Non-Mainline Issue Report"),
    )
    for classification, heading in sections:
        selected = [item for item in items if item["classification"] == classification]
        lines.extend([f"## {heading}", "", f"Count: {len(selected)}", ""])
        if not selected:
            lines.append("- None.")
        for item in selected:
            lines.extend(report_item(item))
        lines.append("")

    lines.extend([
        "## Inputs",
        "",
        f"- `{relative(Path(__file__))}`",
        f"- `{relative(VALIDATION_PATH)}`",
        f"- `{relative(VALIDATION_SUMMARY_PATH)}`",
        f"- `{relative(VALIDATION_REPORT_PATH)}`",
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
    validation = load_json(VALIDATION_PATH)
    validation_summary = load_json(VALIDATION_SUMMARY_PATH)
    if not VALIDATION_REPORT_PATH.exists():
        raise SystemExit(f"missing Stage11B artifact: {relative(VALIDATION_REPORT_PATH)}")

    raw_items = validation.get("validated_blockers")
    if not isinstance(raw_items, list) or not all(isinstance(item, dict) for item in raw_items):
        raise SystemExit("Stage11B validation must contain validated_blockers objects")
    if len(raw_items) != EXPECTED_TOTAL:
        raise SystemExit(f"expected {EXPECTED_TOTAL} Stage11B blockers, found {len(raw_items)}")
    if validation_summary.get("total_blockers_input") != EXPECTED_TOTAL:
        raise SystemExit("Stage11B summary total does not match the expected 142 blockers")

    items = [split_item(item) for item in raw_items]
    assert_corrections(items)
    classification_counts = count_map(OUTPUT_CLASSES, (item["classification"] for item in items))
    if sum(classification_counts.values()) != EXPECTED_TOTAL:
        raise SystemExit("Stage12 classifications do not account for all 142 blockers")

    domain_counts = count_map(DOMAIN_ORDER, (item["domain"] for item in items))
    chain_counts = count_map(CRITICAL_CHAINS, (item["critical_chain"] for item in items))
    grouped = {
        classification: [item for item in items if item["classification"] == classification]
        for classification in OUTPUT_CLASSES
    }
    confirmed_by_domain = {
        domain: [
            item for item in grouped["confirmed_blocker"] if item["domain"] == domain
        ]
        for domain in DOMAIN_ORDER
    }
    critical_chain_order = [
        {
            "order": index,
            "domain": domain,
            "chain": chain_for(domain),
            "depends_on": DOMAIN_DEPENDENCIES[domain],
            "count": domain_counts[domain],
            "confirmed_blocker_count": len(confirmed_by_domain[domain]),
        }
        for index, domain in enumerate(DOMAIN_ORDER, 1)
    ]

    payload = {
        "stage": "Runtime Blocker Domain Split Stage12",
        "purpose": "domain split, dependency chain, and critical-chain ordering only",
        "production_runtime_modified": False,
        "inputs": [
            relative(Path(__file__).with_name("runtime_replacement_blocker_validation_stage11b.py")),
            relative(VALIDATION_PATH),
            relative(VALIDATION_SUMMARY_PATH),
            relative(VALIDATION_REPORT_PATH),
        ],
        "total_blockers_processed": len(items),
        "classification_counts": classification_counts,
        "domain_counts": domain_counts,
        "critical_chain_counts": chain_counts,
        "critical_chain_order": critical_chain_order,
        "confirmed_blockers_by_domain": confirmed_by_domain,
        "compatibility_bridge": grouped["compatibility_bridge"],
        "false_positive": grouped["false_positive"],
        "non_mainline_issue": grouped["non_mainline_issue"],
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "stage": "Runtime Blocker Domain Split Stage12",
        "total_blockers_processed": len(items),
        "classification_counts": classification_counts,
        "domain_counts": domain_counts,
        "confirmed_blocker_domain_counts": {
            domain: len(confirmed_by_domain[domain]) for domain in DOMAIN_ORDER
        },
        "critical_chain_counts": chain_counts,
        "critical_chain_order": critical_chain_order,
        "compatibility_bridge_count": classification_counts["compatibility_bridge"],
        "false_positive_count": classification_counts["false_positive"],
        "non_mainline_issue_count": classification_counts["non_mainline_issue"],
        "required_corrections_enforced": {
            "TaskRunner._runtime_gate_consolidated": "compatibility_bridge",
            "Scheduler._find_active_duplicate_repair_task": "confirmed_blocker",
            "TaskRunner._zero_v800_last_step_type": "confirmed_blocker",
        },
        "production_runtime_modified": False,
        "outputs": {
            "domain_split": relative(OUTPUT_PATH),
            "summary": relative(SUMMARY_PATH),
            "report": relative(REPORT_PATH),
        },
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(items, summary)

    print(f"processed: {len(items)}")
    print(f"classification_counts: {classification_counts}")
    print(f"domain_counts: {domain_counts}")
    print(f"critical_chain_counts: {chain_counts}")
    print("production_runtime_modified: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
