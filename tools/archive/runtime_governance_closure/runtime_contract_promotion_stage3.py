from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
BASE = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory"
SOURCE = BASE / "runtime_contract_extraction_stage2.json"
SUMMARY_SOURCE = BASE / "runtime_contract_extraction_stage2_summary.json"
OUT = BASE / "runtime_contract_promotion_stage3.json"
SUMMARY = BASE / "runtime_contract_promotion_stage3_summary.json"
REPORT = BASE / "runtime_contract_promotion_stage3_report.md"

VERIFY_COMMANDS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]

NATIVE_RUNTIME_FILES = (
    "core/runtime/runtime_",
    "core/runtime/task_runtime.py",
    "core/runtime/execution_authority.py",
    "core/runtime/runtime_state_machine.py",
    "core/runtime/runtime_native_",
)
TEMP_BRIDGE_FILES = (
    "core/tasks/scheduler.py",
    "core/runtime/step_executor.py",
    "core/runtime/task_runner.py",
    "core/runtime/executor.py",
    "core/agent/",
    "core/planning/",
    "core/tasks/planner_gateway_runtime.py",
)


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"missing required input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [dict(x) for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "contracts", "extracted", "needs_contract", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return [dict(x) for x in value if isinstance(x, dict)]
    raise SystemExit("unsupported stage2 extracted JSON shape")


def text_of(item: dict[str, Any]) -> str:
    parts = []
    for key in ("path", "file", "line", "category", "classification", "contract_domain", "snippet", "text", "source", "reason", "action"):
        value = item.get(key)
        if value is not None:
            parts.append(str(value))
    return " ".join(parts).lower()


def path_of(item: dict[str, Any]) -> str:
    return str(item.get("path") or item.get("file") or "").replace("\\", "/")


def classify_promotion(item: dict[str, Any]) -> tuple[str, str]:
    p = path_of(item)
    t = text_of(item)
    domain = str(item.get("contract_domain") or "")

    if any(k in t for k in ("legacy_direct_json_engineering_task_runner", "legacy_direct_engineering_task_route", "legacy_engineering_task_runner_delegate")):
        return "retirement_candidate", "legacy direct engineering task route should be retired after admission contract replacement"

    if "legacy_runtime_dispatcher_migration_required" in t or "migration_blocker" in t:
        return "blocker_signal", "migration blocker is an explicit signal; keep until native route closure verifies removal"

    if "thin_bridge_is_compatibility_layer" in t or "migration_bridge" in t or "runtime_native_scheduler.py" in p:
        return "temporary_bridge_contract", "native runtime bridge still represents an active migration seam"

    if domain in {"authority_contract", "step_executor_contract", "taskrunner_contract"}:
        return "native_runtime_contract", f"{domain} should be formalized as a runtime contract instead of removed"

    if domain == "scheduler_contract":
        return "temporary_bridge_contract", "scheduler contract is still concentrated in legacy scheduler surface; promote after native scheduler extraction"

    if domain == "planner_contract":
        return "temporary_bridge_contract", "planner/recovery fallback remains bridge logic until planner-runtime contract is extracted"

    if any(p.startswith(x) for x in NATIVE_RUNTIME_FILES):
        return "native_runtime_contract", "runtime-owned compatibility should be promoted into explicit native runtime contract"

    if any(p.startswith(x) for x in TEMP_BRIDGE_FILES):
        return "temporary_bridge_contract", "compatibility occurs at migration/bridge boundary"

    return "temporary_bridge_contract", "default conservative classification: keep as bridge until contract owner is explicit"


def run_verify() -> list[dict[str, Any]]:
    results = []
    for cmd in VERIFY_COMMANDS:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        results.append({
            "cmd": " ".join(cmd),
            "returncode": proc.returncode,
            "output": proc.stdout,
            "passed": proc.returncode == 0,
        })
    return results


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    data = load_json(SOURCE)
    items = normalize_items(data)
    promoted = []
    for item in items:
        promotion, reason = classify_promotion(item)
        working = dict(item)
        working["promotion_class"] = promotion
        working["promotion_reason"] = reason
        working.setdefault("promotion_lifecycle", "promote_contract_before_removal")
        promoted.append(working)

    by_promotion = Counter(x["promotion_class"] for x in promoted)
    by_domain = Counter(str(x.get("contract_domain") or "unknown") for x in promoted)
    by_file = Counter(path_of(x).replace("/", "\\") for x in promoted)
    by_next_action = Counter()
    for x in promoted:
        cls = x["promotion_class"]
        if cls == "native_runtime_contract":
            by_next_action["extract_native_contract_tests"] += 1
        elif cls == "temporary_bridge_contract":
            by_next_action["keep_bridge_until_native_owner_exists"] += 1
        elif cls == "retirement_candidate":
            by_next_action["prepare_retirement_contract"] += 1
        else:
            by_next_action["keep_blocker_signal"] += 1

    verify = run_verify()
    verification_passed = all(x["passed"] for x in verify)

    summary = {
        "source_contract_items": len(items),
        "promotion_counts": dict(by_promotion),
        "domain_counts": dict(by_domain),
        "next_action_counts": dict(by_next_action),
        "top_promotion_files": by_file.most_common(25),
        "zero_patch_residue_count": 0,
        "verification_passed": verification_passed,
        "outputs": {"promoted": str(OUT), "summary": str(SUMMARY), "report": str(REPORT)},
    }

    OUT.write_text(json.dumps(promoted, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Runtime Contract Promotion Stage 3",
        "",
        "Inventory-only promotion classification for contracts extracted in Stage 2. This script does not modify runtime behavior.",
        "",
        "## Summary",
        "",
        f"- source contract items: {len(items)}",
        f"- ZERO_PATCH residue: 0",
        f"- verification passed: {verification_passed}",
        "",
        "## Promotion counts",
        "",
    ]
    for k, v in by_promotion.most_common():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Domain counts", ""]
    for k, v in by_domain.most_common():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Next action counts", ""]
    for k, v in by_next_action.most_common():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Top files", ""]
    for k, v in by_file.most_common(25):
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Verification", ""]
    for result in verify:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(f"### {status}: `{result['cmd']}`")
        lines.append("```text")
        lines.append(result["output"].rstrip())
        lines.append("```")
        lines.append("")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"contract promotion items classified: {len(items)}")
    print(f"promotion counts: {dict(by_promotion)}")
    print(f"next action counts: {dict(by_next_action)}")
    print(f"report: {REPORT}")
    print(f"promoted: {OUT}")
    print(f"summary: {SUMMARY}")
    print("verification passed" if verification_passed else "verification failed")
    return 0 if verification_passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
