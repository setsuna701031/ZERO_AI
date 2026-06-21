from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
REPORT = OUT_DIR / "runtime_monkey_patch_report.md"
INVENTORY = OUT_DIR / "runtime_monkey_patch_inventory.json"
SUMMARY = OUT_DIR / "runtime_monkey_patch_summary.json"

TARGET_ROOTS = [ROOT / "core", ROOT / "tests"]
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

SUSPICIOUS_ASSIGN_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\s*=\s*[^=].*(?:wrapped|wrapper|patch|shim|compat)", re.I)
SETATTR_RE = re.compile(r"\bsetattr\s*\(", re.I)
ZERO_PATCH_RE = re.compile(r"ZERO_PATCH_|__zero_patch_", re.I)

FALSE_POSITIVE_NAMES = {
    "wrapped_report",
    "wrapped_payload",
    "wrapped_result",
    "compatibility_report",
}

@dataclass
class MonkeyPatchItem:
    path: str
    line: int
    kind: str
    owner_domain: str
    action: str
    text: str
    reason: str


def iter_py_files() -> list[Path]:
    files: list[Path] = []
    for root in TARGET_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            files.append(p)
    return sorted(files)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("/", "\\")
    except ValueError:
        return str(path).replace("/", "\\")


def owner_for(path: str, text: str) -> str:
    low = (path + " " + text).lower()
    if "scheduler" in low:
        return "scheduler"
    if "step_executor" in low or "stepexecutor" in low:
        return "step_executor"
    if "task_runner" in low or "taskrunner" in low:
        return "task_runner"
    if "authority" in low:
        return "runtime_authority"
    if "recovery" in low:
        return "recovery"
    if "planner" in low:
        return "planner"
    return "unknown"


def classify_text(path: str, line_no: int, text: str) -> MonkeyPatchItem | None:
    stripped = text.strip()
    if not stripped or stripped.startswith("#"):
        return None
    # Obvious false positives from ordinary variables, not method injection.
    left = stripped.split("=", 1)[0].strip() if "=" in stripped else stripped
    if left in FALSE_POSITIVE_NAMES:
        return None
    if ZERO_PATCH_RE.search(stripped):
        return MonkeyPatchItem(path, line_no, "zero_patch_residue", owner_for(path, stripped), "remove_or_consolidate_before_release", stripped, "ZERO_PATCH marker residue")
    if SETATTR_RE.search(stripped):
        return MonkeyPatchItem(path, line_no, "setattr_runtime_injection", owner_for(path, stripped), "manual_review_or_promote_to_native_owner", stripped, "setattr can mutate runtime behavior dynamically")
    if SUSPICIOUS_ASSIGN_RE.search(stripped):
        return MonkeyPatchItem(path, line_no, "class_method_assignment", owner_for(path, stripped), "manual_review_or_promote_to_native_owner", stripped, "class/module attribute assignment may be monkey patching")
    return None


def scan_ast(path: Path, source: str) -> list[MonkeyPatchItem]:
    items: list[MonkeyPatchItem] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return items
    path_s = rel(path)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr":
            text = lines[node.lineno - 1].strip() if 0 < node.lineno <= len(lines) else "setattr(...)"
            item = MonkeyPatchItem(path_s, node.lineno, "setattr_runtime_injection", owner_for(path_s, text), "manual_review_or_promote_to_native_owner", text, "AST detected setattr call")
            if item not in items:
                items.append(item)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    # Flag only risky direct method replacement shapes, not normal instance fields.
                    text = lines[node.lineno - 1].strip() if 0 < node.lineno <= len(lines) else "attribute assignment"
                    if any(k in text.lower() for k in ("wrapped", "wrapper", "patch", "shim", "compat")):
                        item = MonkeyPatchItem(path_s, node.lineno, "class_method_assignment", owner_for(path_s, text), "manual_review_or_promote_to_native_owner", text, "AST detected attribute assignment with patch/wrapper wording")
                        if item not in items:
                            items.append(item)
    return items


def collect() -> list[MonkeyPatchItem]:
    seen: set[tuple[str, int, str, str]] = set()
    items: list[MonkeyPatchItem] = []
    for p in iter_py_files():
        try:
            source = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            source = p.read_text(encoding="utf-8-sig")
        path_s = rel(p)
        for idx, line in enumerate(source.splitlines(), start=1):
            item = classify_text(path_s, idx, line)
            if item:
                key = (item.path, item.line, item.kind, item.text)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
        for item in scan_ast(p, source):
            key = (item.path, item.line, item.kind, item.text)
            if key not in seen:
                seen.add(key)
                items.append(item)
    return sorted(items, key=lambda x: (x.path, x.line, x.kind))


def run(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {
        "cmd": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ok": proc.returncode == 0,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = collect()
    by_kind: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for item in items:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        by_owner[item.owner_domain] = by_owner.get(item.owner_domain, 0) + 1
        by_action[item.action] = by_action.get(item.action, 0) + 1

    zero_patch_residue = [item for item in items if item.kind == "zero_patch_residue"]
    monkey_patch_items = [item for item in items if item.kind != "zero_patch_residue"]

    verifications = []
    tests_dir = ROOT / "tests" / "runtime_contracts"
    if tests_dir.exists():
        verifications.append(run([sys.executable, "-m", "compileall", "tests/runtime_contracts"]))
        verifications.append(run([sys.executable, "-m", "pytest", "-q", "tests/runtime_contracts"]))
    for test in [
        "tests/test_runtime_evidence_freeze.py",
        "tests/test_runtime_execution_ownership_migration_contract.py",
        "tests/test_runtime_mainline_freeze_contract.py",
        "tests/test_runtime_mode_propagation.py",
        "tests/test_runner_scheduler_boundary_survival.py",
    ]:
        if (ROOT / test).exists():
            verifications.append(run([sys.executable, "-m", "pytest", "-q", test]))

    verification_passed = all(v["ok"] for v in verifications)

    inventory = [asdict(item) for item in items]
    INVENTORY.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "monkey_patch_items": len(monkey_patch_items),
        "zero_patch_residue_count": len(zero_patch_residue),
        "by_kind": by_kind,
        "by_owner_domain": by_owner,
        "by_action": by_action,
        "native_contract_tests_passed": any(v["ok"] and "tests/runtime_contracts" in v["cmd"] and "pytest" in v["cmd"] for v in verifications),
        "verification_passed": verification_passed,
        "outputs": {
            "inventory": str(INVENTORY),
            "summary": str(SUMMARY),
            "report": str(REPORT),
        },
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Runtime Monkey Patch Elimination Audit - Stage 9",
        "",
        "Inventory-only audit for remaining runtime monkey-patch style residue after Native Ownership Stage 8.",
        "This script does not modify runtime behavior.",
        "",
        "## Summary",
        "",
        f"- monkey patch items: {len(monkey_patch_items)}",
        f"- ZERO_PATCH residue: {len(zero_patch_residue)}",
        f"- verification passed: {verification_passed}",
        "",
        "## Counts by kind",
        "",
    ]
    for k, v in sorted(by_kind.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- `{k}`: {v}")
    lines.extend(["", "## Counts by owner domain", ""])
    for k, v in sorted(by_owner.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- `{k}`: {v}")
    lines.extend(["", "## Items", ""])
    if items:
        for item in items:
            lines.append(f"- `{item.path}:{item.line}` `{item.kind}` `{item.owner_domain}` `{item.action}` — {item.text}")
    else:
        lines.append("No monkey-patch style residue detected.")
    lines.extend(["", "## Verification", ""])
    for v in verifications:
        status = "PASS" if v["ok"] else "FAIL"
        lines.append(f"### {status}: `{v['cmd']}`")
        body = (v["stdout"] + ("\n" + v["stderr"] if v["stderr"] else "")).strip()
        lines.append("```text")
        lines.append(body[-4000:] if body else "")
        lines.append("```")
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"monkey patch items: {len(monkey_patch_items)}")
    print(f"ZERO_PATCH residue: {len(zero_patch_residue)}")
    print(f"native contract tests passed: {summary['native_contract_tests_passed']}")
    print(f"report: {REPORT}")
    print(f"inventory: {INVENTORY}")
    print(f"summary: {SUMMARY}")
    print("verification passed" if verification_passed else "verification failed")
    return 0 if verification_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
