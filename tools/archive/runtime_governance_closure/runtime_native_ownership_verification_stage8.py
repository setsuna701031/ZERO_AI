
from __future__ import annotations

"""Runtime Native Ownership Verification Stage 8.

Inventory-only stage. It does not modify runtime behavior.

Inputs expected from prior stages:
- docs/architecture/runtime_compatibility_inventory/runtime_native_contract_test_generation_stage7_summary.json
- docs/architecture/runtime_compatibility_inventory/runtime_contract_ownership_mapping_stage5_summary.json
- tests/runtime_contracts/*

Outputs:
- docs/architecture/runtime_native_ownership/runtime_native_ownership_inventory.json
- docs/architecture/runtime_native_ownership/runtime_native_ownership_summary.json
- docs/architecture/runtime_native_ownership/runtime_native_ownership_report.md
"""

import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
COMPAT_DIR = ROOT / "docs" / "architecture" / "runtime_compatibility_inventory"

TARGET_FILES = [
    "core/runtime/execution_authority.py",
    "core/runtime/runtime_authority.py",
    "core/runtime/step_executor.py",
    "core/runtime/task_runner.py",
    "core/tasks/scheduler.py",
    "core/runtime/runtime_native_scheduler.py",
    "core/runtime/planner_runtime_dispatch.py",
    "core/runtime/runtime_recovery_executor.py",
    "core/runtime/runtime_replay_engine.py",
    "core/runtime/operator_integration_bridge.py",
]

OWNER_PATTERNS: list[tuple[str, str]] = [
    ("runtime_authority", r"RuntimeAuthority|runtime_authority|execution_authority|authority_gate|authority_policy"),
    ("step_executor", r"StepExecutor|step_executor|execute_step|register_handler|execution_authority"),
    ("task_runner", r"TaskRunner|task_runner|run_task|run_task_tick|runtime_state|operator_session"),
    ("scheduler", r"Scheduler|scheduler|run_one_step|scheduler_contract|runtime_native_scheduler"),
    ("planner", r"planner|replanner|planner_runtime|planning"),
    ("recovery", r"recovery|replay|checkpoint|failed_step|resume_payload"),
]

BRIDGE_PATTERNS: list[tuple[str, str]] = [
    ("temporary_bridge", r"thin_bridge|compatibility_layer|migration_bridge|bridge_is_compatibility|keep_until_native_runtime_complete"),
    ("compatibility_fallback", r"compatibility|compat|fallback|legacy"),
    ("blocker_signal", r"migration_required|blocker|blocked|deny|denied"),
    ("native_owner", r"Native|native|RuntimeAuthority|StepExecutor|TaskRunner|Scheduler"),
]

ZERO_PATCH_RE = re.compile(r"ZERO_PATCH_")
MONKEY_RE = re.compile(r"__zero_patch_|=\s*.*wrapped|setattr\(.*wrapped")

@dataclass
class OwnershipItem:
    path: str
    line: int
    owner_domain: str
    bridge_class: str
    risk: str
    action: str
    text: str


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def run(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {"cmd": cmd, "returncode": proc.returncode, "output": proc.stdout}


def detect_owner(line: str, path: str) -> str:
    path_l = path.replace("\\", "/").lower()
    if "execution_authority" in path_l or "runtime_authority" in path_l:
        return "runtime_authority"
    if "step_executor" in path_l:
        return "step_executor"
    if "task_runner" in path_l:
        return "task_runner"
    if "scheduler" in path_l:
        return "scheduler"
    if "planner" in path_l:
        return "planner"
    if "recovery" in path_l or "replay" in path_l:
        return "recovery"
    for owner, pattern in OWNER_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return owner
    return "unknown"


def detect_bridge(line: str) -> str:
    for bridge, pattern in BRIDGE_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return bridge
    return "none_or_native"


def classify_action(owner: str, bridge: str, line: str) -> tuple[str, str]:
    text_l = line.lower()
    if bridge == "temporary_bridge":
        return "medium", "bind_bridge_to_native_owner_before_retirement"
    if bridge == "compatibility_fallback":
        if "legacy_runtime_dispatcher_migration_required" in text_l or "migration_required" in text_l:
            return "medium", "keep_blocker_until_native_owner_complete"
        return "medium", "add_native_owner_contract_test_before_removal"
    if bridge == "blocker_signal":
        return "low", "keep_as_blocker_signal"
    if owner in {"runtime_authority", "step_executor", "task_runner", "scheduler"}:
        return "low", "native_owner_confirmed"
    return "low", "manual_review"


def iter_relevant_lines(path: Path):
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(errors="ignore")
    for idx, line in enumerate(text.splitlines(), start=1):
        if any(re.search(pat, line, re.IGNORECASE) for _, pat in OWNER_PATTERNS + BRIDGE_PATTERNS):
            yield idx, line.rstrip()


def scan() -> list[OwnershipItem]:
    items: list[OwnershipItem] = []
    for rel in TARGET_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        for line_no, line in iter_relevant_lines(path):
            owner = detect_owner(line, rel)
            bridge = detect_bridge(line)
            risk, action = classify_action(owner, bridge, line)
            items.append(
                OwnershipItem(
                    path=rel,
                    line=line_no,
                    owner_domain=owner,
                    bridge_class=bridge,
                    risk=risk,
                    action=action,
                    text=line.strip()[:240],
                )
            )
    return items


def count_zero_patch_and_monkey() -> tuple[int, int]:
    zero = 0
    monkey = 0
    for path in (ROOT / "core").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = path.read_text(errors="ignore")
        zero += len(ZERO_PATCH_RE.findall(text))
        # exclude normal variables named wrapped_report etc. by requiring patch/wrapped assignment pattern
        monkey += len(MONKEY_RE.findall(text))
    return zero, monkey


def write_report(summary: dict[str, Any], items: list[OwnershipItem], verification: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    inv_path = OUT_DIR / "runtime_native_ownership_inventory.json"
    summary_path = OUT_DIR / "runtime_native_ownership_summary.json"
    report_path = OUT_DIR / "runtime_native_ownership_report.md"

    inv_path.write_text(json.dumps([asdict(item) for item in items], indent=2, ensure_ascii=False), encoding="utf-8")
    summary["outputs"] = {
        "inventory": str(inv_path),
        "summary": str(summary_path),
        "report": str(report_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Runtime Native Ownership Verification Stage 8")
    lines.append("")
    lines.append("Inventory-only verification. This stage does not modify runtime behavior.")
    lines.append("")
    lines.append("## Summary")
    for key in [
        "ownership_items",
        "zero_patch_residue_count",
        "monkey_patch_residue_count",
        "native_contract_tests_passed",
        "verification_passed",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")
    lines.append("")
    lines.append("## Owner domain counts")
    for key, value in summary["owner_domain_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Bridge class counts")
    for key, value in summary["bridge_class_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Action counts")
    for key, value in summary["action_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Top files")
    for path, count in summary["top_files"][:20]:
        lines.append(f"- `{path}`: {count}")
    lines.append("")
    lines.append("## Medium risk samples")
    medium = [item for item in items if item.risk == "medium"][:80]
    for item in medium:
        lines.append(f"- `{item.path}:{item.line}` `{item.owner_domain}` `{item.bridge_class}` `{item.action}` — {item.text}")
    lines.append("")
    lines.append("## Verification")
    for entry in verification:
        status = "PASS" if entry["returncode"] == 0 else "FAIL"
        lines.append(f"### {status}: `{' '.join(entry['cmd'])}`")
        lines.append("```text")
        lines.append(entry["output"].rstrip())
        lines.append("```")
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stage5 = read_json(COMPAT_DIR / "runtime_contract_ownership_mapping_stage5_summary.json", {})
    stage7 = read_json(COMPAT_DIR / "runtime_native_contract_test_generation_stage7_summary.json", {})

    items = scan()
    zero_count, monkey_count = count_zero_patch_and_monkey()

    owner_counts = Counter(item.owner_domain for item in items)
    bridge_counts = Counter(item.bridge_class for item in items)
    action_counts = Counter(item.action for item in items)
    risk_counts = Counter(item.risk for item in items)
    file_counts = Counter(item.path for item in items)

    verification: list[dict[str, Any]] = []
    verification.append(run([sys.executable, "-m", "compileall", "tests/runtime_contracts"]))
    verification.append(run([sys.executable, "-m", "pytest", "-q", "tests/runtime_contracts"]))
    verification.append(run([sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"]))
    verification.append(run([sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"]))
    verification.append(run([sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"]))

    native_contract_tests_passed = verification[1]["returncode"] == 0
    verification_passed = all(entry["returncode"] == 0 for entry in verification) and zero_count == 0

    summary: dict[str, Any] = {
        "ownership_items": len(items),
        "owner_domain_counts": dict(owner_counts),
        "bridge_class_counts": dict(bridge_counts),
        "action_counts": dict(action_counts),
        "risk_counts": dict(risk_counts),
        "top_files": file_counts.most_common(30),
        "zero_patch_residue_count": zero_count,
        "monkey_patch_residue_count": monkey_count,
        "native_contract_tests_passed": native_contract_tests_passed,
        "stage5_native_contracts": stage5.get("native_contract_ownership_mapped") or stage5.get("native_contracts") or stage5.get("mapped") or None,
        "stage7_generated_tests": stage7.get("native_contract_tests_generated") or stage7.get("generated_tests") or None,
        "verification_passed": verification_passed,
    }

    write_report(summary, items, verification)

    print(f"ownership items: {summary['ownership_items']}")
    print(f"owner domain counts: {summary['owner_domain_counts']}")
    print(f"bridge class counts: {summary['bridge_class_counts']}")
    print(f"action counts: {summary['action_counts']}")
    print(f"ZERO_PATCH residue: {zero_count}")
    print(f"monkey patch residue: {monkey_count}")
    print(f"native contract tests passed: {native_contract_tests_passed}")
    print(f"report: {OUT_DIR / 'runtime_native_ownership_report.md'}")
    print(f"inventory: {OUT_DIR / 'runtime_native_ownership_inventory.json'}")
    print(f"summary: {OUT_DIR / 'runtime_native_ownership_summary.json'}")
    print("verification passed" if verification_passed else "verification failed")
    return 0 if verification_passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
