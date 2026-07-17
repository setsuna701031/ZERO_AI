from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

ROOT = Path.cwd()
CORE = ROOT / "core"
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory"
REPORT = OUT_DIR / "compatibility_inventory_report.md"
INVENTORY = OUT_DIR / "compatibility_inventory.json"
SUMMARY = OUT_DIR / "compatibility_inventory_summary.json"

KEYWORDS = ("compat", "compatibility", "fallback", "legacy")
TARGET_HINTS = (
    "core/runtime/execution_authority.py",
    "core/runtime/task_runner.py",
    "core/runtime/step_executor.py",
    "core/tasks/scheduler.py",
    "core/runtime/runtime_authority.py",
    "core/runtime/runtime_session_resume.py",
)
VERIFY_COMMANDS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]

@dataclass
class InventoryItem:
    path: str
    line: int
    keyword: str
    category: str
    risk: str
    disposition: str
    text: str


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except Exception:
        return path.as_posix()


def categorize(path: str, line_text: str) -> tuple[str, str, str]:
    lower = line_text.lower()
    p = path.replace("\\", "/").lower()

    if "zero_patch_" in lower or "_zero_patch" in lower:
        return "patch_residue", "high", "remove_before_seal"

    if "compatibilityreport" in line_text or "runtime_compatibility" in p or "compatibility report" in lower:
        return "abi_compatibility", "low", "keep_review_periodically"

    if "thin_bridge_is_compatibility_layer" in lower or "thin_bridge" in lower:
        return "migration_bridge", "medium", "keep_until_native_runtime_complete"

    if "legacy_direct_json_engineering_task_runner" in lower or "legacy_direct_engineering_task_route" in lower:
        return "legacy_route", "medium", "audit_for_retirement"

    if "legacy_runtime_dispatcher_migration_required" in lower:
        return "migration_blocker", "medium", "keep_as_blocker_signal"

    if "fallback" in lower and ("planner" in lower or "replan" in lower or "recovery" in lower):
        return "fallback_planning_or_recovery", "medium", "contract_review_required"

    if "except exception" in lower and "compat" in lower:
        return "import_compatibility_guard", "low", "review_after_import_stability"

    if any(token in p for token in ("task_runner.py", "scheduler.py", "step_executor.py", "execution_authority.py")):
        return "runtime_core_compatibility", "medium", "manual_review_before_removal"

    if "legacy" in lower:
        return "legacy_reference", "low", "inventory_only"

    if "fallback" in lower:
        return "fallback_reference", "low", "inventory_only"

    return "compatibility_reference", "low", "inventory_only"


def iter_py_files() -> Iterable[Path]:
    if not CORE.exists():
        return []
    return sorted(CORE.rglob("*.py"))


def collect_inventory() -> list[InventoryItem]:
    items: list[InventoryItem] = []
    pattern = re.compile(r"compat(?:ibility)?|fallback|legacy", re.IGNORECASE)
    for path in iter_py_files():
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        rpath = rel(path)
        for idx, line in enumerate(lines, start=1):
            matches = pattern.findall(line)
            if not matches:
                continue
            keyword = sorted(set(m.lower() for m in matches))[0]
            category, risk, disposition = categorize(rpath, line)
            items.append(
                InventoryItem(
                    path=rpath,
                    line=idx,
                    keyword=keyword,
                    category=category,
                    risk=risk,
                    disposition=disposition,
                    text=line.strip()[:260],
                )
            )
    return items


def run(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {"command": " ".join(cmd), "returncode": proc.returncode, "output": proc.stdout}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    items = collect_inventory()
    by_category = Counter(item.category for item in items)
    by_risk = Counter(item.risk for item in items)
    by_file = Counter(item.path for item in items)
    target_counts = {target: by_file.get(target, 0) for target in TARGET_HINTS}

    zero_patch_scan = []
    for path in iter_py_files():
        try:
            for idx, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                if "ZERO_PATCH_" in line or "_zero_patch" in line:
                    zero_patch_scan.append({"path": rel(path), "line": idx, "text": line.strip()})
        except Exception:
            continue

    verification = [run(cmd) for cmd in VERIFY_COMMANDS]
    verification_passed = all(item["returncode"] == 0 for item in verification)

    INVENTORY.write_text(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY.write_text(json.dumps({
        "total_items": len(items),
        "by_category": dict(by_category),
        "by_risk": dict(by_risk),
        "top_files": by_file.most_common(30),
        "target_counts": target_counts,
        "zero_patch_residue_count": len(zero_patch_scan),
        "zero_patch_residue": zero_patch_scan,
        "verification_passed": verification_passed,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    report_lines = [
        "# Runtime Compatibility Inventory Audit",
        "",
        "## Scope",
        "",
        "Inventory-only audit for `legacy`, `fallback`, and `compatibility` references after Runtime Patch Consolidation.",
        "This script does not modify runtime behavior.",
        "",
        "## Summary",
        "",
        f"- inventory items: {len(items)}",
        f"- ZERO_PATCH residue: {len(zero_patch_scan)}",
        f"- verification passed: {verification_passed}",
        "",
        "## Category counts",
        "",
    ]
    for key, count in by_category.most_common():
        report_lines.append(f"- `{key}`: {count}")
    report_lines.extend(["", "## Risk counts", ""])
    for key, count in by_risk.most_common():
        report_lines.append(f"- `{key}`: {count}")
    report_lines.extend(["", "## Target file counts", ""])
    for key, count in target_counts.items():
        report_lines.append(f"- `{key}`: {count}")
    report_lines.extend(["", "## Top files", ""])
    for path, count in by_file.most_common(25):
        report_lines.append(f"- `{path}`: {count}")
    report_lines.extend(["", "## High/medium risk samples", ""])
    for item in [x for x in items if x.risk in {"high", "medium"}][:80]:
        report_lines.append(f"- `{item.path}:{item.line}` `{item.category}` `{item.disposition}` — {item.text}")
    report_lines.extend(["", "## Verification", ""])
    for result in verification:
        status = "PASS" if result["returncode"] == 0 else "FAIL"
        report_lines.append(f"### {status}: `{result['command']}`")
        report_lines.append("```text")
        report_lines.append(result["output"].strip())
        report_lines.append("```")
        report_lines.append("")
    report_lines.extend(["", "## Outputs", "", f"- `{INVENTORY.relative_to(ROOT).as_posix()}`", f"- `{SUMMARY.relative_to(ROOT).as_posix()}`"])

    REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"inventory items: {len(items)}")
    print(f"ZERO_PATCH residue: {len(zero_patch_scan)}")
    print(f"report: {REPORT}")
    print(f"inventory: {INVENTORY}")
    print(f"summary: {SUMMARY}")
    print("verification passed" if verification_passed else "verification failed")
    return 0 if verification_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
