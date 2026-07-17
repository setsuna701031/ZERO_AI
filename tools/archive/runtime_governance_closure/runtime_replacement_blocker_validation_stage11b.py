from __future__ import annotations

import json
import subprocess
import sys
import tokenize
from collections import Counter, defaultdict
from io import StringIO
from pathlib import Path
from typing import Any, Iterable


ROOT = Path.cwd()
INVENTORY_PATH = ROOT / "docs" / "architecture" / "runtime_native_ownership" / "runtime_replacement_inventory.json"
SUMMARY_INPUT_PATH = ROOT / "docs" / "architecture" / "runtime_native_ownership" / "runtime_replacement_summary.json"
REPORT_INPUT_PATH = ROOT / "docs" / "architecture" / "runtime_native_ownership" / "runtime_replacement_report.md"
OUT_DIR = INVENTORY_PATH.parent
VALIDATION_PATH = OUT_DIR / "runtime_blocker_validation.json"
SUMMARY_PATH = OUT_DIR / "runtime_blocker_validation_summary.json"
REPORT_PATH = OUT_DIR / "runtime_blocker_validation_report.md"

VALIDATED_CLASSES = (
    "confirmed_blocker",
    "downgrade_to_compatibility_bridge",
    "downgrade_to_native_owner",
    "false_positive",
    "test_only",
    "non_mainline_issue",
)

CRITICAL_TARGETS = {
    "Scheduler.run_one_step",
    "Scheduler._handle_dispatch_result",
    "Scheduler._mark_repo_task_finished",
    "Scheduler._mark_repo_task_failed",
    "Scheduler._mark_repo_task_queued",
    "Scheduler._finalize_dispatched_task",
    "TaskRunner.run_task",
    "TaskRunner.run_task_tick",
    "StepExecutor.execute_step",
    "RuntimeExecutionAuthorityGate.enforce",
}

METADATA_STATE_NAMES = {
    "SCHEDULER_BUILD",
    "RETRYING_REPAIR_BRIDGE_VERSION",
}

COMPATIBILITY_SHAPE_HINTS = (
    "adapter_payload",
    "public_result",
    "effective_status_and_answer",
    "normalize_replan_metadata",
    "normalize_step_scope",
    "resolve_step_path",
    "resolve_read_path",
    "resolve_guard_target_path",
    "needs_scheduler_path_resolution",
)

NON_MAINLINE_HINTS = (
    "get_queue_snapshot",
    "get_queue_rows",
    "get_review_queue",
    "approve_review_item",
    "reject_review_item",
    "attach_autonomous_repair_chain_summary",
)

EXECUTION_HINTS = (
    "run_",
    "execute",
    "tick",
    "create_task",
    "mark_repo_task",
    "handle_dispatch",
    "handle_missing_repo_task",
    "handle_run_one_step_exception",
    "finalize_dispatched_task",
    "register_builtin_handlers",
    "determine_failure_type",
    "repairable_failure",
    "cleanup_task_queue",
    "persist_step_result",
    "authority",
    "repair_chain_handler",
    "build_observation",
    "decide_from_observation",
    "represents_failed_step_observation",
    "sync_runner_result",
    "plan_goal",
    "try_force_repo_edit",
    "create_task_record",
    "duplicate_repair_task",
    "last_step_type",
)

CHAIN_NAMES = (
    "scheduler_chain",
    "task_runner_chain",
    "step_executor_chain",
    "authority_chain",
    "recovery_chain",
)

VERIFY_COMMANDS = (
    ("compileall", [sys.executable, "-m", "compileall", "tools", "core", "tests"]),
    ("runtime_contracts", [sys.executable, "-m", "pytest", "-q", "tests/runtime_contracts"]),
    ("runtime_evidence_freeze", [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"]),
    ("runtime_execution_ownership_migration", [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"]),
    ("runtime_mainline_freeze", [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"]),
    ("runtime_mode_propagation", [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"]),
    ("runner_scheduler_boundary_survival", [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"]),
)


def slash(value: str) -> str:
    return value.replace("\\", "/")


def relative(path: Path) -> str:
    return slash(str(path.relative_to(ROOT)))


def load_blockers() -> list[dict[str, Any]]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    chain = payload.get("replacement_chain")
    if not isinstance(chain, list):
        raise SystemExit("Stage11 inventory must contain replacement_chain")
    blockers = [item for item in chain if isinstance(item, dict) and item.get("classification") == "BLOCKER"]
    if len(blockers) != 142:
        raise SystemExit(f"expected 142 Stage11 blockers, found {len(blockers)}")
    return blockers


def source_context(path_text: str, line_number: int, radius: int = 2) -> tuple[str, str, str, bool]:
    path = ROOT / slash(path_text)
    if not path.exists() or not path.is_file():
        return "", "", "", False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not 1 <= line_number <= len(lines):
        return "", "", "", False
    before_start = max(0, line_number - radius - 1)
    after_end = min(len(lines), line_number + radius)
    before = "\n".join(f"{index + 1}: {lines[index]}" for index in range(before_start, line_number - 1))
    current = lines[line_number - 1]
    after = "\n".join(f"{index + 1}: {lines[index]}" for index in range(line_number, after_end))
    return before, current, after, True


def authority_enforce_target(target: str, expression: str) -> bool:
    text = f"{target} {expression}".lower()
    return "enforce" in text and ("authority" in text or "execution_authority" in text)


def validate_classification(item: dict[str, Any], current_line: str, source_exists: bool) -> tuple[str, str, str, str, bool]:
    path = slash(str(item.get("source_path") or ""))
    target = str(item.get("chain_target") or "")
    expression = str(item.get("expression") or "")
    kind = str(item.get("replacement_kind") or "")
    attr = target.rsplit(".", 1)[-1]
    lowered = f"{target} {expression}".lower()

    if path.startswith("tests/"):
        return "test_only", "retain_test_scaffolding", "replacement is confined to tests/**", "high", False
    if not source_exists or target not in current_line:
        return "false_positive", "remove_from_blocker_inventory", "source location no longer contains the reported replacement target", "high", False
    if target in CRITICAL_TARGETS or authority_enforce_target(target, expression):
        return "confirmed_blocker", "plan_native_method_retirement", "replacement directly intercepts a named runtime execution or authority chain", "high", False

    if kind == "class_level_state_override":
        if attr in METADATA_STATE_NAMES:
            return "false_positive", "retain_as_non_behavioral_metadata", "class metadata/version marker does not itself replace executable runtime behavior", "high", False
        if any(token in attr for token in ("STEP_TYPES", "REPAIRABLE")):
            return "confirmed_blocker", "move_routing_state_into_native_class_definition", "class-level routing allowlist changes scheduler/task_runner/step_executor execution selection", "high", False
        return "downgrade_to_compatibility_bridge", "migrate_class_state_to_native_owner", "class state graft is compatibility debt but not a method replacement", "medium", False

    if any(hint in lowered for hint in COMPATIBILITY_SHAPE_HINTS):
        return "downgrade_to_compatibility_bridge", "contract_then_move_shape_bridge_to_native_owner", "replacement normalizes path, payload, result, or metadata shape without owning the primary execution decision", "high", False

    if any(hint in lowered for hint in NON_MAINLINE_HINTS):
        return "non_mainline_issue", "track_in_domain_retirement_plan", "replacement is outside the named execution mainline but still affects scheduler/runtime ownership or observability", "high", True

    if kind == "class_level_replacement" and any(hint in lowered for hint in EXECUTION_HINTS):
        return "confirmed_blocker", "plan_native_method_retirement", "class-level executable replacement changes runtime execution, state transition, authority, or recovery behavior", "high", False

    if kind == "class_level_replacement" and attr == "__init__":
        return "confirmed_blocker", "fold_constructor_wrapper_into_native_owner", "class-level constructor replacement changes runtime dependency ownership", "high", False

    if target.startswith("self.") and target.count(".") == 1:
        return "downgrade_to_native_owner", "retain_native_instance_assignment", "direct self-owned instance assignment is native ownership, not a class replacement", "high", False

    if any(word in lowered for word in ("compat", "fallback", "legacy", "shim", "wrapper", "adapter", "bridge")):
        return "downgrade_to_compatibility_bridge", "contract_then_migrate_bridge", "compatibility graft remains migration debt but is not proven to own the primary execution path", "medium", False

    return "non_mainline_issue", "manual_domain_retirement_review", "class replacement is not a named mainline chain but can still influence runtime ownership", "medium", True


def validate_item(item: dict[str, Any]) -> dict[str, Any]:
    path = slash(str(item.get("source_path") or ""))
    line = int(item.get("source_line") or 0)
    before, current, after, source_exists = source_context(path, line)
    validated, action, reason, confidence, non_mainline = validate_classification(item, current, source_exists)
    return {
        "source_path": path,
        "source_line": line,
        "expression": str(item.get("expression") or ""),
        "owner_domain": str(item.get("owner_domain") or "unknown"),
        "replacement_kind": str(item.get("replacement_kind") or "unknown"),
        "original_classification": str(item.get("classification") or ""),
        "validated_classification": validated,
        "action": action,
        "reason": reason,
        "chain_target": str(item.get("chain_target") or ""),
        "suspected_native_owner": str(item.get("suspected_native_owner") or "manual ownership resolution required"),
        "context_before": before,
        "context_after": after,
        "confidence": confidence,
        "non_mainline_issue": non_mainline,
    }


def critical_chain(item: dict[str, Any]) -> str:
    domain = str(item.get("owner_domain") or "unknown")
    target = str(item.get("chain_target") or "").lower()
    expression = str(item.get("expression") or "").lower()
    text = f"{target} {expression}"
    if "authority" in text:
        return "authority_chain"
    if domain == "scheduler":
        return "scheduler_chain"
    if domain == "task_runner":
        return "task_runner_chain"
    if domain == "step_executor":
        return "step_executor_chain"
    if domain == "recovery" or "recovery" in text or "replay" in text:
        return "recovery_chain"
    return "other"


def zero_patch_residue() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for root_name in ("core", "tests"):
        root = ROOT / root_name
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                source = path.read_text(encoding="utf-8")
                for token in tokenize.generate_tokens(StringIO(source).readline):
                    if token.type == tokenize.NAME and (token.string.startswith("ZERO_PATCH_") or token.string.startswith("__zero_patch_")):
                        findings.append({"source_path": relative(path), "source_line": token.start[0], "identifier": token.string})
            except (SyntaxError, UnicodeDecodeError, tokenize.TokenError):
                continue
    return findings


def run_verification(name: str, command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return {
        "name": name,
        "command": " ".join(command),
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def top_files(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(item.get("source_path") or "") for item in items)
    return [{"path": path, "count": count} for path, count in counts.most_common(20)]


def report_lines_for_items(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- None."]
    return [
        f"- `{item['source_path']}:{item['source_line']}` `{item['owner_domain']}` `{item['chain_target']}` — {item['reason']}"
        for item in items
    ]


def write_report(
    validated: list[dict[str, Any]],
    counts: Counter[str],
    chains: dict[str, list[dict[str, Any]]],
    residues: list[dict[str, Any]],
    verification: list[dict[str, Any]],
) -> None:
    confirmed = [item for item in validated if item["validated_classification"] == "confirmed_blocker"]
    downgraded = [item for item in validated if item["validated_classification"].startswith("downgrade_to_")]
    non_mainline = [item for item in validated if item["validated_classification"] == "non_mainline_issue"]
    recommendation = "Stage12 confirmed blocker retirement planning" if len(confirmed) <= 20 else "Stage12 blocker domain split"

    lines = [
        "# Runtime Replacement Blocker Validation — Stage 11B",
        "",
        "Validation and reporting only. Stage 11B does not modify production runtime behavior.",
        "",
        "## Summary",
        "",
        f"- Total blockers input: {len(validated)}",
        f"- Confirmed blocker: {counts['confirmed_blocker']}",
        f"- Downgrade to compatibility bridge: {counts['downgrade_to_compatibility_bridge']}",
        f"- Downgrade to native owner: {counts['downgrade_to_native_owner']}",
        f"- False positive: {counts['false_positive']}",
        f"- Test only: {counts['test_only']}",
        f"- Non-mainline issue: {counts['non_mainline_issue']}",
        f"- ZERO_PATCH residue: {len(residues)}",
        f"- Recommended next stage: {recommendation}",
        "",
        "## Top confirmed blocker files",
        "",
    ]
    for item in top_files(confirmed):
        lines.append(f"- `{item['path']}`: {item['count']}")
    lines.extend(["", "## Top downgrade files", ""])
    for item in top_files(downgraded):
        lines.append(f"- `{item['path']}`: {item['count']}")

    lines.extend(["", "## Critical chains", ""])
    for chain_name in CHAIN_NAMES:
        chain_items = chains.get(chain_name, [])
        confirmed_count = sum(item["validated_classification"] == "confirmed_blocker" for item in chain_items)
        lines.extend([f"### {chain_name.replace('_', ' ').title()}", "", f"- Items: {len(chain_items)}", f"- Confirmed blockers: {confirmed_count}", ""])
        lines.extend(report_lines_for_items(chain_items))
        lines.append("")

    lines.extend(["## Confirmed blockers", ""])
    lines.extend(report_lines_for_items(confirmed))
    lines.extend(["", "## Downgrades", ""])
    lines.extend(report_lines_for_items(downgraded))

    lines.extend(["", "## Non-Mainline Issue Report", ""])
    lines.append(
        "These replacements are not confirmed named-mainline blockers, but they still affect runtime ownership, authority, scheduler, task_runner, step_executor, or recovery/replay concerns and remain explicitly tracked."
    )
    lines.append("")
    lines.extend(report_lines_for_items(non_mainline))

    lines.extend(["", "## Verification", ""])
    lines.extend([f"### {'PASS' if not residues else 'FAIL'}: active ZERO_PATCH identifier scan", "", f"Active residue count: {len(residues)}"])
    for finding in residues:
        lines.append(f"- `{finding['source_path']}:{finding['source_line']}` — `{finding['identifier']}`")
    for result in verification:
        lines.extend(["", f"### {'PASS' if result['passed'] else 'FAIL'}: `{result['command']}`", "", "```text"])
        output = "\n".join(part for part in (result["stdout"], result["stderr"]) if part)
        lines.append(output[-7000:] if output else "")
        lines.append("```")

    lines.extend([
        "",
        "## Outputs",
        "",
        f"- `{relative(VALIDATION_PATH)}`",
        f"- `{relative(SUMMARY_PATH)}`",
        f"- `{relative(REPORT_PATH)}`",
        "",
    ])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if not INVENTORY_PATH.exists():
        raise SystemExit(f"missing Stage11 inventory: {INVENTORY_PATH}")
    blockers = load_blockers()
    validated = [validate_item(item) for item in blockers]
    counts = Counter(item["validated_classification"] for item in validated)
    if set(counts) - set(VALIDATED_CLASSES):
        raise SystemExit(f"unexpected validated classifications: {set(counts) - set(VALIDATED_CLASSES)}")

    chains: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in validated:
        chains[critical_chain(item)].append(item)

    residues = zero_patch_residue()
    verification = [run_verification(name, command) for name, command in VERIFY_COMMANDS]
    passed = len(validated) == len(blockers) == 142 and not residues and all(result["passed"] for result in verification)
    confirmed = [item for item in validated if item["validated_classification"] == "confirmed_blocker"]
    downgraded = [item for item in validated if item["validated_classification"].startswith("downgrade_to_")]
    non_mainline = [item for item in validated if item["validated_classification"] == "non_mainline_issue"]
    recommendation = "Stage12 confirmed blocker retirement planning" if len(confirmed) <= 20 else "Stage12 blocker domain split"

    validation_payload = {
        "stage": "Runtime Replacement Blocker Validation Stage11B",
        "input": relative(INVENTORY_PATH),
        "total_blockers_input": len(blockers),
        "validated_blockers": validated,
        "critical_chains": {name: items for name, items in sorted(chains.items())},
        "zero_patch_residue_count": len(residues),
    }
    VALIDATION_PATH.write_text(json.dumps(validation_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary_payload = {
        "stage": "Runtime Replacement Blocker Validation Stage11B",
        "total_blockers_input": len(blockers),
        "by_validated_classification": {name: counts[name] for name in VALIDATED_CLASSES},
        "confirmed_blocker_count": counts["confirmed_blocker"],
        "downgrade_to_compatibility_bridge_count": counts["downgrade_to_compatibility_bridge"],
        "downgrade_to_native_owner_count": counts["downgrade_to_native_owner"],
        "false_positive_count": counts["false_positive"],
        "test_only_count": counts["test_only"],
        "non_mainline_issue_count": counts["non_mainline_issue"],
        "top_confirmed_blocker_files": top_files(confirmed),
        "top_downgrade_files": top_files(downgraded),
        "critical_chain_counts": {
            name: {
                "total": len(chains.get(name, [])),
                "confirmed_blocker": sum(item["validated_classification"] == "confirmed_blocker" for item in chains.get(name, [])),
            }
            for name in CHAIN_NAMES
        },
        "recommended_next_stage": recommendation,
        "zero_patch_residue_count": len(residues),
        "native_contract_tests_passed": next((result["passed"] for result in verification if result["name"] == "runtime_contracts"), False),
        "verification_passed": passed,
        "verification": verification,
        "outputs": {
            "validation": relative(VALIDATION_PATH),
            "summary": relative(SUMMARY_PATH),
            "report": relative(REPORT_PATH),
        },
    }
    SUMMARY_PATH.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(validated, counts, chains, residues, verification)

    print(f"total blockers input: {len(blockers)}")
    print(f"validated classifications: {dict(counts)}")
    print(f"recommended next stage: {recommendation}")
    print(f"ZERO_PATCH residue: {len(residues)}")
    print("verification passed" if passed else "verification failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
