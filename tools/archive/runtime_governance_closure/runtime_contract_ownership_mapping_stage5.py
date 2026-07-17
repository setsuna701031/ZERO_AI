from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
BASE = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory"
SOURCE = BASE / "runtime_native_contract_test_extraction_stage4.json"
REPORT = BASE / "runtime_contract_ownership_mapping_stage5_report.md"
MAPPING = BASE / "runtime_contract_ownership_mapping_stage5.json"
SUMMARY = BASE / "runtime_contract_ownership_mapping_stage5_summary.json"

VERIFY_COMMANDS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]

OWNER_RULES = [
    ("core/runtime/execution_authority.py", "RuntimeExecutionAuthorityGate", "runtime_authority"),
    ("core/runtime/runtime_authority.py", "RuntimeAuthority", "runtime_authority"),
    ("core/runtime/step_executor.py", "StepExecutor", "step_executor"),
    ("core/runtime/task_runner.py", "TaskRunner", "task_runner"),
    ("core/runtime/task_runtime.py", "TaskRuntime", "task_runtime"),
    ("core/tasks/scheduler.py", "NativeRuntimeSchedulerBoundary", "scheduler"),
    ("core/runtime/runtime_native_scheduler.py", "NativeRuntimeScheduler", "scheduler"),
    ("core/runtime/executor.py", "RuntimeExecutor", "runtime_executor"),
]

TEST_HINTS = {
    "runtime_authority": [
        "tests/test_runtime_execution_ownership_migration_contract.py",
        "tests/test_runtime_mainline_freeze_contract.py",
    ],
    "step_executor": [
        "tests/test_runtime_mode_propagation.py",
        "tests/test_runner_scheduler_boundary_survival.py",
    ],
    "task_runner": [
        "tests/test_runtime_mode_propagation.py",
        "tests/test_runner_scheduler_boundary_survival.py",
    ],
    "scheduler": [
        "tests/test_runner_scheduler_boundary_survival.py",
    ],
    "runtime_executor": [
        "tests/test_runtime_evidence_freeze.py",
    ],
    "task_runtime": [
        "tests/test_runtime_mode_propagation.py",
    ],
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_path(value: Any) -> str:
    return str(value or "").replace("\\", "/")


def classify_owner(item: dict[str, Any]) -> tuple[str, str]:
    path = norm_path(item.get("path") or item.get("file") or "")
    domain = str(item.get("contract_domain") or item.get("domain") or "").strip()
    text = " ".join(str(item.get(k) or "") for k in ("text", "snippet", "line_text", "assertion_hint", "category")).lower()

    for needle, owner, owner_domain in OWNER_RULES:
        if norm_path(needle) in path:
            return owner, owner_domain

    if "authority" in domain or "authority" in text:
        return "RuntimeExecutionAuthorityGate", "runtime_authority"
    if "step_executor" in domain or "step executor" in text or "step_executor" in text:
        return "StepExecutor", "step_executor"
    if "taskrunner" in domain or "task_runner" in path or "taskrunner" in text:
        return "TaskRunner", "task_runner"
    if "scheduler" in domain or "scheduler" in path or "scheduler" in text:
        return "NativeRuntimeSchedulerBoundary", "scheduler"
    if "planner" in domain or "planner" in path:
        return "PlannerRuntimeContract", "planner"
    return "RuntimeContractOwnerReview", "needs_owner_review"


def action_for(item: dict[str, Any], owner_domain: str) -> str:
    hint = str(item.get("assertion_hint") or "").strip()
    if hint == "execution_authority_is_explicit_and_enforced":
        return "extract_native_authority_contract_test"
    if hint == "planning_or_recovery_fallback_has_contract_evidence":
        return "extract_planning_recovery_contract_test"
    if owner_domain == "needs_owner_review":
        return "manual_owner_review_before_promotion"
    return "bind_compatibility_path_to_native_owner_test"


def bridge_dependency(item: dict[str, Any], owner_domain: str) -> str:
    path = norm_path(item.get("path") or item.get("file") or "")
    text = " ".join(str(item.get(k) or "") for k in ("text", "snippet", "line_text", "category")).lower()
    if "fallback" in text:
        return "fallback_bridge"
    if "legacy" in text:
        return "legacy_bridge"
    if "compat" in text:
        return "compatibility_bridge"
    if "scheduler" in path and owner_domain != "scheduler":
        return "scheduler_boundary_bridge"
    return "none_or_native"


def read_items() -> list[dict[str, Any]]:
    if not SOURCE.exists():
        raise SystemExit(f"missing source: {SOURCE}")
    data = load_json(SOURCE)
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            return [x for x in data["items"] if isinstance(x, dict)]
        if isinstance(data.get("extracted"), list):
            return [x for x in data["extracted"] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    raise SystemExit("source has unsupported shape")


def run_verify() -> tuple[bool, list[dict[str, Any]]]:
    results = []
    ok = True
    for cmd in VERIFY_COMMANDS:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        passed = proc.returncode == 0
        ok = ok and passed
        results.append({"command": " ".join(cmd), "passed": passed, "output": proc.stdout})
    return ok, results


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    items = read_items()
    mapped = []
    for idx, item in enumerate(items, 1):
        owner, owner_domain = classify_owner(item)
        bridge = bridge_dependency(item, owner_domain)
        tests = TEST_HINTS.get(owner_domain, [])
        mapped.append({
            "id": f"native-contract-owner-{idx:04d}",
            "source": item,
            "native_owner": owner,
            "owner_domain": owner_domain,
            "bridge_dependency": bridge,
            "retirement_prerequisite": "native_owner_contract_test_passes" if owner_domain != "needs_owner_review" else "manual_owner_mapping_required",
            "test_coverage_candidates": tests,
            "next_action": action_for(item, owner_domain),
        })

    by_owner = Counter(x["native_owner"] for x in mapped)
    by_domain = Counter(x["owner_domain"] for x in mapped)
    by_bridge = Counter(x["bridge_dependency"] for x in mapped)
    by_action = Counter(x["next_action"] for x in mapped)
    uncovered = [x for x in mapped if not x["test_coverage_candidates"]]

    zero_patch = []
    for path in (ROOT / "core").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "ZERO_PATCH_" in text:
            zero_patch.append(str(path.relative_to(ROOT)))

    verification_passed, verification = run_verify()

    summary = {
        "source_native_contract_items": len(items),
        "mapped_items": len(mapped),
        "by_native_owner": dict(by_owner),
        "by_owner_domain": dict(by_domain),
        "by_bridge_dependency": dict(by_bridge),
        "by_next_action": dict(by_action),
        "uncovered_test_candidate_count": len(uncovered),
        "zero_patch_residue_count": len(zero_patch),
        "zero_patch_residue": zero_patch,
        "verification_passed": verification_passed,
        "outputs": {
            "mapping": str(MAPPING),
            "summary": str(SUMMARY),
            "report": str(REPORT),
        },
    }

    MAPPING.write_text(json.dumps(mapped, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Runtime Contract Ownership Mapping Stage 5",
        "",
        "Inventory-only mapping from native runtime contract candidates to native owners.",
        "No runtime behavior is modified.",
        "",
        "## Summary",
        "",
        f"- source native contract items: {len(items)}",
        f"- mapped items: {len(mapped)}",
        f"- ZERO_PATCH residue: {len(zero_patch)}",
        f"- verification passed: {verification_passed}",
        "",
        "## Owner domain counts",
        "",
    ]
    for key, value in by_domain.most_common():
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Native owner counts", ""]
    for key, value in by_owner.most_common():
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Bridge dependency counts", ""]
    for key, value in by_bridge.most_common():
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Next action counts", ""]
    for key, value in by_action.most_common():
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Verification", ""]
    for result in verification:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(f"### {status}: `{result['command']}`")
        lines.append("```text")
        lines.append(result["output"].rstrip())
        lines.append("```")
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"native contract ownership mapped: {len(mapped)}")
    print(f"owner domain counts: {dict(by_domain)}")
    print(f"bridge dependency counts: {dict(by_bridge)}")
    print(f"next action counts: {dict(by_action)}")
    print(f"ZERO_PATCH residue: {len(zero_patch)}")
    print(f"report: {REPORT}")
    print(f"mapping: {MAPPING}")
    print(f"summary: {SUMMARY}")
    print("verification passed" if verification_passed else "verification failed")
    return 0 if verification_passed and not zero_patch else 1

if __name__ == "__main__":
    raise SystemExit(main())
