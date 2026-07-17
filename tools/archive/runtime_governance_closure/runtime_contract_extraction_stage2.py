from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
BASE = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory"
CLASSIFIED = BASE / "compatibility_classification_stage1.json"
OUT_JSON = BASE / "runtime_contract_extraction_stage2.json"
OUT_SUMMARY = BASE / "runtime_contract_extraction_stage2_summary.json"
OUT_REPORT = BASE / "runtime_contract_extraction_stage2_report.md"

VERIFY_COMMANDS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]


def load_items() -> list[dict[str, Any]]:
    if not CLASSIFIED.exists():
        raise SystemExit(f"missing classified inventory: {CLASSIFIED}")
    data = json.loads(CLASSIFIED.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("items", "classified", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    raise SystemExit("unsupported classification JSON shape")


def norm_path(item: dict[str, Any]) -> str:
    return str(item.get("path") or item.get("file") or "").replace("/", "\\")


def line_text(item: dict[str, Any]) -> str:
    return str(item.get("line_text") or item.get("text") or item.get("snippet") or item.get("source") or "")


def category(item: dict[str, Any]) -> str:
    return str(item.get("category") or "unknown")


def classification(item: dict[str, Any]) -> str:
    return str(item.get("classification") or item.get("action") or item.get("recommendation") or "")


def infer_contract_domain(item: dict[str, Any]) -> str:
    p = norm_path(item).lower()
    text = (line_text(item) + " " + category(item)).lower()
    if "scheduler" in p or "scheduler" in text:
        return "scheduler_contract"
    if "execution_authority" in p or "authority" in text:
        return "authority_contract"
    if "step_executor" in p or "step_executor" in text:
        return "step_executor_contract"
    if "task_runner" in p or "taskrunner" in text or "task_runner" in text:
        return "taskrunner_contract"
    if "planner" in p or "replanner" in p or "fallback_planning" in text:
        return "planner_contract"
    if "recovery" in p or "replay" in p or "recovery" in text or "replay" in text:
        return "recovery_replay_contract"
    if "agent_loop" in p or "legacy_route" in text:
        return "agent_route_contract"
    if "bridge" in p or "migration_bridge" in text or "thin_bridge" in text:
        return "migration_bridge_contract"
    if "runtime" in p or "runtime_core" in text or "compatibility" in text:
        return "runtime_contract"
    return "uncategorized_contract"


def infer_lifecycle(item: dict[str, Any]) -> str:
    cls = classification(item)
    cat = category(item)
    text = line_text(item).lower()
    if cls == "retire_candidate":
        return "safe_to_retire_candidate"
    if cls == "blocker_signal" or cat == "migration_blocker":
        return "must_keep_blocker_signal"
    if cls == "keep" or cat in {"abi_compatibility", "import_compatibility_guard"}:
        return "must_keep"
    if "thin_bridge" in text or cat == "migration_bridge":
        return "keep_until_native_runtime_complete"
    if cls == "needs_contract":
        return "extract_contract_before_removal"
    return "review_required"


def infer_native_target(item: dict[str, Any]) -> str:
    domain = infer_contract_domain(item)
    mapping = {
        "scheduler_contract": "core.runtime.runtime_native_scheduler",
        "authority_contract": "core.runtime.execution_authority / runtime_authority_seal",
        "step_executor_contract": "core.runtime.step_executor authority entry",
        "taskrunner_contract": "core.runtime.task_runner runtime gate",
        "planner_contract": "core.runtime.runtime_native_targeted_pytest_planner / planner contract",
        "recovery_replay_contract": "core.runtime.recovery_replay_closure",
        "agent_route_contract": "core.agent.agent_loop native runtime route",
        "migration_bridge_contract": "native runtime bridge replacement",
        "runtime_contract": "core.runtime native runtime contracts",
    }
    return mapping.get(domain, "manual native target review")


def run_verification() -> tuple[bool, list[dict[str, Any]]]:
    results = []
    ok = True
    for cmd in VERIFY_COMMANDS:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        if proc.returncode != 0:
            ok = False
        results.append({
            "command": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        })
    return ok, results


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    items = load_items()
    needs = [item for item in items if classification(item) == "needs_contract"]

    extracted = []
    by_domain = Counter()
    by_lifecycle = Counter()
    by_file = Counter()

    for item in needs:
        p = norm_path(item)
        domain = infer_contract_domain(item)
        lifecycle = infer_lifecycle(item)
        native_target = infer_native_target(item)
        record = dict(item)
        record["contract_domain"] = domain
        record["contract_lifecycle"] = lifecycle
        record["native_runtime_target"] = native_target
        record["recommended_next_action"] = (
            "write explicit contract test before removal"
            if lifecycle == "extract_contract_before_removal"
            else lifecycle
        )
        extracted.append(record)
        by_domain[domain] += 1
        by_lifecycle[lifecycle] += 1
        by_file[p] += 1

    verify_ok, verification = run_verification()
    summary = {
        "source_items": len(items),
        "needs_contract_items": len(needs),
        "by_contract_domain": dict(by_domain.most_common()),
        "by_contract_lifecycle": dict(by_lifecycle.most_common()),
        "top_contract_files": by_file.most_common(25),
        "zero_patch_residue_count": 0,
        "verification_passed": verify_ok,
        "outputs": {
            "extracted": str(OUT_JSON),
            "summary": str(OUT_SUMMARY),
            "report": str(OUT_REPORT),
        },
    }

    OUT_JSON.write_text(json.dumps(extracted, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    report = [
        "# Runtime Contract Extraction Stage 2",
        "",
        "Inventory-only extraction for medium-risk compatibility items classified as `needs_contract`.",
        "This script does not modify runtime behavior.",
        "",
        "## Summary",
        f"- source items: {len(items)}",
        f"- needs_contract items: {len(needs)}",
        f"- verification passed: {verify_ok}",
        "",
        "## Contract domains",
    ]
    for key, value in by_domain.most_common():
        report.append(f"- `{key}`: {value}")
    report += ["", "## Contract lifecycle"]
    for key, value in by_lifecycle.most_common():
        report.append(f"- `{key}`: {value}")
    report += ["", "## Top files"]
    for key, value in by_file.most_common(25):
        report.append(f"- `{key}`: {value}")
    report += ["", "## Verification"]
    for item in verification:
        status = "PASS" if item["returncode"] == 0 else "FAIL"
        report.append(f"### {status}: `{item['command']}`")
        report.append("```text")
        report.append((item["stdout"] or item["stderr"] or "").strip())
        report.append("```")
        report.append("")
    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")

    print(f"needs_contract items extracted: {len(needs)}")
    print(f"contract domain counts: {dict(by_domain.most_common())}")
    print(f"contract lifecycle counts: {dict(by_lifecycle.most_common())}")
    print(f"report: {OUT_REPORT}")
    print(f"extracted: {OUT_JSON}")
    print(f"summary: {OUT_SUMMARY}")
    print("verification passed" if verify_ok else "verification failed")
    return 0 if verify_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
