from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
BASE = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory"
PROMOTED = BASE / "runtime_contract_promotion_stage3.json"
SUMMARY = BASE / "runtime_native_contract_test_extraction_stage4_summary.json"
REPORT = BASE / "runtime_native_contract_test_extraction_stage4_report.md"
EXTRACTED = BASE / "runtime_native_contract_test_extraction_stage4.json"

VERIFY_COMMANDS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]

DOMAIN_TEST_MAP = {
    "scheduler_contract": [
        "tests/test_runner_scheduler_boundary_survival.py",
        "tests/test_runtime_mode_propagation.py",
    ],
    "taskrunner_contract": [
        "tests/test_runtime_mode_propagation.py",
        "tests/test_runner_scheduler_boundary_survival.py",
    ],
    "step_executor_contract": [
        "tests/test_runtime_mode_propagation.py",
        "tests/test_runtime_execution_ownership_migration_contract.py",
    ],
    "authority_contract": [
        "tests/test_runtime_execution_ownership_migration_contract.py",
        "tests/test_runtime_mainline_freeze_contract.py",
    ],
    "planner_contract": [
        "tests/test_runtime_mainline_freeze_contract.py",
        "tests/test_runtime_evidence_freeze.py",
    ],
}

NATIVE_OWNER_MAP = {
    "scheduler_contract": "RuntimeNativeScheduler / Scheduler boundary contract",
    "taskrunner_contract": "TaskRunner runtime gate contract",
    "step_executor_contract": "StepExecutor authority entry contract",
    "authority_contract": "RuntimeExecutionAuthorityGate contract",
    "planner_contract": "Planner runtime dispatch / recovery planning contract",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_assertion_hint(item: dict[str, Any]) -> str:
    text = " ".join(str(item.get(k, "")) for k in ("line_text", "snippet", "marker", "category", "path"))
    lower = text.lower()
    if "operator_session" in lower or "completed_steps" in lower or "failed_step" in lower:
        return "operator_session_state_survives_boundary"
    if "runtime_mode" in lower or "replay" in lower:
        return "runtime_mode_propagates_to_result_state_and_trace"
    if "authority" in lower or "capability" in lower or "execution_authority" in lower:
        return "execution_authority_is_explicit_and_enforced"
    if "fallback" in lower and ("planner" in lower or "replan" in lower or "recovery" in lower):
        return "planning_or_recovery_fallback_has_contract_evidence"
    if "compat" in lower or "legacy" in lower:
        return "legacy_compatibility_path_has_native_owner_or_blocker"
    return "native_contract_behavior_is_preserved"


def file_to_test_name(path: str, domain: str, index: int) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", path.replace("core/", "").replace("core\\", "")).strip("_").lower()
    dom = domain.replace("_contract", "")
    return f"test_native_{dom}_{stem}_{index:03d}"


def main() -> int:
    if not PROMOTED.exists():
        raise SystemExit(f"missing input: {PROMOTED}")

    BASE.mkdir(parents=True, exist_ok=True)
    promoted = load_json(PROMOTED)
    items = promoted.get("items", promoted) if isinstance(promoted, dict) else promoted
    if not isinstance(items, list):
        raise SystemExit("runtime_contract_promotion_stage3.json must contain a list or {'items': list}")

    native_items = [dict(item) for item in items if str(item.get("promotion") or item.get("promotion_class") or "") == "native_runtime_contract"]
    if not native_items:
        # Some script versions use contract_promotion.
        native_items = [dict(item) for item in items if str(item.get("contract_promotion") or "") == "native_runtime_contract"]

    extracted: list[dict[str, Any]] = []
    by_domain = Counter()
    by_file = Counter()
    by_hint = Counter()

    for idx, item in enumerate(native_items, start=1):
        domain = str(item.get("contract_domain") or item.get("domain") or "runtime_contract")
        path = str(item.get("path") or "")
        hint = classify_assertion_hint(item)
        test_targets = DOMAIN_TEST_MAP.get(domain, ["tests/test_runtime_mainline_freeze_contract.py"])
        record = {
            "contract_id": f"native-contract-{idx:03d}",
            "source_path": path,
            "source_line": item.get("line"),
            "contract_domain": domain,
            "native_owner": NATIVE_OWNER_MAP.get(domain, "Native Runtime contract owner required"),
            "assertion_hint": hint,
            "recommended_test_name": file_to_test_name(path or domain, domain, idx),
            "recommended_test_targets": test_targets,
            "source_category": item.get("category"),
            "source_action": item.get("action"),
            "source_text": item.get("line_text") or item.get("snippet") or item.get("text"),
            "next_action": "extract_native_contract_test",
        }
        extracted.append(record)
        by_domain[domain] += 1
        if path:
            by_file[path] += 1
        by_hint[hint] += 1

    EXTRACTED.write_text(json.dumps({"items": extracted}, indent=2, ensure_ascii=False), encoding="utf-8")

    verification = []
    ok_all = True
    for cmd in VERIFY_COMMANDS:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        ok = proc.returncode == 0
        ok_all = ok_all and ok
        verification.append({
            "command": " ".join(cmd),
            "ok": ok,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        })

    zero_patch_residue = []
    for path in (ROOT / "core").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "ZERO_PATCH_" in text:
            zero_patch_residue.append(str(path.relative_to(ROOT)))

    summary = {
        "source_contract_items": len(items),
        "native_runtime_contract_items": len(extracted),
        "by_contract_domain": dict(by_domain),
        "by_source_file_top": by_file.most_common(25),
        "by_assertion_hint": dict(by_hint),
        "zero_patch_residue_count": len(zero_patch_residue),
        "zero_patch_residue": zero_patch_residue,
        "verification_passed": bool(ok_all and not zero_patch_residue),
        "outputs": {
            "extracted": str(EXTRACTED),
            "summary": str(SUMMARY),
            "report": str(REPORT),
        },
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Runtime Native Contract Test Extraction Stage 4",
        "",
        "Inventory-only extraction for native runtime contracts. This script does not modify runtime behavior.",
        "",
        "## Summary",
        "",
        f"- source contract items: {len(items)}",
        f"- native runtime contract items: {len(extracted)}",
        f"- ZERO_PATCH residue: {len(zero_patch_residue)}",
        f"- verification passed: {bool(ok_all and not zero_patch_residue)}",
        "",
        "## Domain counts",
        "",
    ]
    for k, v in by_domain.most_common():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Assertion hint counts", ""]
    for k, v in by_hint.most_common():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Top source files", ""]
    for k, v in by_file.most_common(25):
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Recommended extraction order", "", "1. authority_contract", "2. step_executor_contract", "3. taskrunner_contract", "4. scheduler_contract", "5. planner_contract", "", "## Verification", ""]
    for item in verification:
        status = "PASS" if item["ok"] else "FAIL"
        lines.append(f"### {status}: `{item['command']}`")
        out = (item.get("stdout") or item.get("stderr") or "").strip()
        lines.append("```text")
        lines.append(out[-4000:] if out else "")
        lines.append("```")
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"native runtime contract test items extracted: {len(extracted)}")
    print(f"domain counts: {dict(by_domain)}")
    print(f"assertion hint counts: {dict(by_hint)}")
    print(f"ZERO_PATCH residue: {len(zero_patch_residue)}")
    print(f"report: {REPORT}")
    print(f"extracted: {EXTRACTED}")
    print(f"summary: {SUMMARY}")
    print("verification passed" if summary["verification_passed"] else "verification failed")
    return 0 if summary["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
