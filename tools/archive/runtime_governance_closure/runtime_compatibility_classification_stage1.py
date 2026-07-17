from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
INVENTORY = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory" / "compatibility_inventory.json"
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory"
REPORT = OUT_DIR / "compatibility_classification_stage1_report.md"
CLASSIFIED = OUT_DIR / "compatibility_classification_stage1.json"
SUMMARY = OUT_DIR / "compatibility_classification_stage1_summary.json"

VERIFY_COMMANDS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]

BLOCKER_HINTS = (
    "migration_required",
    "migration_blocker",
    "blocked",
    "required",
)

KEEP_HINTS = (
    "abi_compatibility",
    "import_compatibility_guard",
    "migration_bridge",
)

CONTRACT_HINTS = (
    "fallback_planning_or_recovery",
    "runtime_core_compatibility",
)

RETIRE_HINTS = (
    "legacy_route",
)

TARGET_HOTSPOTS = {
    "core/tasks/scheduler.py",
    "core/runtime/step_executor.py",
    "core/runtime/task_runner.py",
    "core/runtime/execution_authority.py",
    "core/agent/agent_loop.py",
}


def _load_inventory() -> list[dict[str, Any]]:
    if not INVENTORY.exists():
        raise SystemExit(f"missing inventory: {INVENTORY}")
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("compatibility_inventory.json must be a list")
    return [item for item in data if isinstance(item, dict)]


def _text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(k, "")) for k in ("category", "action", "line_text", "snippet", "path", "marker")).lower()


def classify(item: dict[str, Any]) -> tuple[str, str]:
    category = str(item.get("category") or "").strip()
    risk = str(item.get("risk") or "").strip()
    action = str(item.get("action") or "").strip()
    text = _text(item)

    if category == "migration_blocker" or "keep_as_blocker_signal" in action or any(h in text for h in BLOCKER_HINTS):
        return "blocker_signal", "migration blocker / explicit required signal must stay visible"

    if category in KEEP_HINTS or "keep_until_native_runtime_complete" in action:
        return "keep", "explicit ABI/import/migration bridge compatibility"

    if category in RETIRE_HINTS or "audit_for_retirement" in action:
        return "retire_candidate", "legacy route is explicitly marked for retirement audit"

    if category in CONTRACT_HINTS or "contract_review_required" in action or "manual_review_before_removal" in action:
        return "needs_contract", "core/fallback behavior requires contract before removal"

    if risk == "medium":
        return "needs_contract", "medium risk item requires manual contract classification"

    return "keep", "low risk reference retained by default"


def run_verify() -> tuple[bool, list[dict[str, Any]]]:
    results = []
    ok = True
    for command in VERIFY_COMMANDS:
        proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        passed = proc.returncode == 0
        ok = ok and passed
        results.append({
            "command": " ".join(command),
            "returncode": proc.returncode,
            "passed": passed,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        })
    return ok, results


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    inventory = _load_inventory()
    medium = [item for item in inventory if str(item.get("risk") or "") == "medium"]

    classified = []
    for item in medium:
        bucket, reason = classify(item)
        enriched = dict(item)
        enriched["classification"] = bucket
        enriched["classification_reason"] = reason
        classified.append(enriched)

    by_class = Counter(item["classification"] for item in classified)
    by_file = Counter(str(item.get("path") or "") for item in classified)
    by_category = Counter(str(item.get("category") or "") for item in classified)
    by_class_file = defaultdict(Counter)
    for item in classified:
        by_class_file[item["classification"]][str(item.get("path") or "")] += 1

    zero_patch = [item for item in inventory if "ZERO_PATCH" in _text(item)]
    verification_passed, verification = run_verify()

    CLASSIFIED.write_text(json.dumps(classified, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "source_inventory_items": len(inventory),
        "medium_items_classified": len(classified),
        "classification_counts": dict(by_class),
        "category_counts": dict(by_category),
        "top_medium_files": by_file.most_common(25),
        "target_hotspot_counts": {path: by_file.get(path, 0) for path in sorted(TARGET_HOTSPOTS)},
        "zero_patch_residue_count": len(zero_patch),
        "verification_passed": verification_passed,
        "outputs": {
            "classified": str(CLASSIFIED),
            "summary": str(SUMMARY),
            "report": str(REPORT),
        },
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = []
    lines.append("# Runtime Compatibility Classification Stage 1")
    lines.append("")
    lines.append("Inventory-only classification of medium-risk compatibility, fallback, and legacy references.")
    lines.append("This script does not modify runtime behavior.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- source inventory items: {len(inventory)}")
    lines.append(f"- medium items classified: {len(classified)}")
    lines.append(f"- ZERO_PATCH residue: {len(zero_patch)}")
    lines.append(f"- verification passed: {verification_passed}")
    lines.append("")
    lines.append("## Classification counts")
    lines.append("")
    for key, count in by_class.most_common():
        lines.append(f"- `{key}`: {count}")
    lines.append("")
    lines.append("## Medium category counts")
    lines.append("")
    for key, count in by_category.most_common():
        lines.append(f"- `{key}`: {count}")
    lines.append("")
    lines.append("## Target hotspot counts")
    lines.append("")
    for path in sorted(TARGET_HOTSPOTS):
        lines.append(f"- `{path}`: {by_file.get(path, 0)}")
    lines.append("")
    lines.append("## Top medium files")
    lines.append("")
    for path, count in by_file.most_common(25):
        lines.append(f"- `{path}`: {count}")
    lines.append("")
    lines.append("## Classification file breakdown")
    for cls, counter in sorted(by_class_file.items()):
        lines.append("")
        lines.append(f"### `{cls}`")
        for path, count in counter.most_common(15):
            lines.append(f"- `{path}`: {count}")
    lines.append("")
    lines.append("## Verification")
    lines.append("")
    for result in verification:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(f"### {status}: `{result['command']}`")
        lines.append("```text")
        lines.append((result["stdout"] or "").strip())
        if result["stderr"]:
            lines.append("STDERR:")
            lines.append(result["stderr"].strip())
        lines.append("```")
        lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append(f"- `{CLASSIFIED}`")
    lines.append(f"- `{SUMMARY}`")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"medium items classified: {len(classified)}")
    print(f"classification counts: {dict(by_class)}")
    print(f"ZERO_PATCH residue: {len(zero_patch)}")
    print(f"report: {REPORT}")
    print(f"classified: {CLASSIFIED}")
    print(f"summary: {SUMMARY}")
    print("verification passed" if verification_passed else "verification failed")
    return 0 if verification_passed and len(zero_patch) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
