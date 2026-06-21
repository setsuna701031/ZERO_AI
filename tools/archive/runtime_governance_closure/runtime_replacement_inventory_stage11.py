from __future__ import annotations

import ast
import json
import subprocess
import sys
import tokenize
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Iterable


ROOT = Path.cwd()
OUT_DIR = ROOT / "docs" / "architecture" / "runtime_native_ownership"
INVENTORY_PATH = OUT_DIR / "runtime_replacement_inventory.json"
SUMMARY_PATH = OUT_DIR / "runtime_replacement_summary.json"
REPORT_PATH = OUT_DIR / "runtime_replacement_report.md"
SCAN_ROOTS = (ROOT / "core", ROOT / "tests")

COMPATIBILITY_WORDS = (
    "compat",
    "fallback",
    "legacy",
    "shim",
    "bridge",
    "wrapper",
    "wrapped",
    "replacement",
    "registry",
    "adapter",
)
OWNER_ATTRIBUTES = {
    "dispatcher",
    "task_runner",
    "step_executor",
    "runtime_dispatcher",
    "operator_bridge",
    "planner_bridge",
    "authority_gate",
    "execution_authority",
    "runtime_authority",
    "recovery_executor",
    "replay_engine",
}
MAINLINE_METHODS = {
    "run_one_step",
    "run_task",
    "run_task_tick",
    "execute_step",
    "enforce",
    "enforce_execution_authority",
}
MAINLINE_DOMAINS = {"scheduler", "task_runner", "step_executor", "runtime_authority"}
SPECIAL_TARGETS = {
    "Scheduler.run_one_step",
    "Scheduler._handle_dispatch_result",
    "Scheduler._mark_repo_task_finished",
    "Scheduler._mark_repo_task_failed",
    "TaskRunner.run_task",
    "TaskRunner.run_task_tick",
    "StepExecutor.execute_step",
    "RuntimeExecutionAuthorityGate.enforce",
}
VERIFY_COMMANDS = (
    ("compileall", [sys.executable, "-m", "compileall", "tools", "core", "tests"]),
    ("runtime_contracts", [sys.executable, "-m", "pytest", "-q", "tests/runtime_contracts"]),
    ("runtime_evidence_freeze", [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"]),
    ("runtime_execution_ownership_migration", [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"]),
    ("runtime_mainline_freeze", [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"]),
    ("runtime_mode_propagation", [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"]),
    ("runner_scheduler_boundary_survival", [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"]),
)


@dataclass(frozen=True)
class ReplacementItem:
    source_path: str
    source_line: int
    expression: str
    owner_domain: str
    replacement_kind: str
    classification: str
    action: str
    reason: str
    chain_target: str
    suspected_native_owner: str
    special_target: str | None
    non_mainline_issue: bool


def slash(value: str) -> str:
    return value.replace("\\", "/")


def relative(path: Path) -> str:
    return slash(str(path.relative_to(ROOT)))


def iter_python_files() -> Iterable[Path]:
    for scan_root in SCAN_ROOTS:
        if scan_root.exists():
            yield from sorted(path for path in scan_root.rglob("*.py") if "__pycache__" not in path.parts)


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def compact_expression(source: str, node: ast.AST, fallback: str) -> str:
    segment = ast.get_source_segment(source, node) or fallback
    return " ".join(segment.strip().split())


def has_compatibility_word(*values: str) -> bool:
    text = " ".join(values).lower()
    return any(word in text for word in COMPATIBILITY_WORDS)


def owner_domain(path: str, target: str, expression: str) -> str:
    text = f"{path} {target} {expression}".lower()
    if "step_executor" in text or "stepexecutor" in text:
        return "step_executor"
    if "task_runner" in text or "taskrunner" in text:
        return "task_runner"
    if "scheduler" in text:
        return "scheduler"
    if "runtimeexecutionauthority" in text or "runtime_authority" in text or "execution_authority" in text or "authority_gate" in text:
        return "runtime_authority"
    if "planner" in text:
        return "planner"
    if "recovery" in text or "replay" in text:
        return "recovery"
    return "unknown"


def suspected_owner(domain: str, target: str) -> str:
    mapping = {
        "scheduler": "core.tasks.scheduler.Scheduler",
        "task_runner": "core.runtime.task_runner.TaskRunner",
        "step_executor": "core.runtime.step_executor.StepExecutor",
        "runtime_authority": "core.runtime.runtime_execution_authority_gate.RuntimeExecutionAuthorityGate",
        "planner": "core.planning.planner.Planner",
        "recovery": "core.runtime runtime recovery/replay owner",
    }
    if domain in mapping:
        return mapping[domain]
    root = target.split(".", 1)[0]
    return root if root and root not in {"self", "object", "builtins", "monkeypatch"} else "manual ownership resolution required"


def special_target(target: str) -> str | None:
    if target in SPECIAL_TARGETS:
        return target
    lowered = target.lower()
    if lowered.endswith(".enforce") and ("authority" in lowered or "execution_authority" in lowered):
        return "RuntimeAuthority / execution_authority enforce path"
    return None


def is_function_replacement_value(value: ast.AST) -> bool:
    if isinstance(value, (ast.Name, ast.Attribute, ast.Lambda)):
        return True
    return isinstance(value, ast.Call) and dotted(value.func) in {"staticmethod", "classmethod"}


def classify(
    *,
    path: str,
    target: str,
    expression: str,
    kind: str,
    domain: str,
    class_level: bool,
    attr_name: str,
) -> tuple[str, str, str]:
    if path.startswith("tests/"):
        return "TEST_ONLY", "retain_as_test_scaffolding", "tests/** replacement, fixture, fake, stub, spy, lambda, or monkeypatch"

    sensitive_text = f"{target} {expression}".lower()
    authority_sensitive = "authority" in sensitive_text and ("enforce" in sensitive_text or "gate" in sensitive_text)
    state_sensitive = any(term in sensitive_text for term in ("operator_session", "scheduler_state", "recovery_replay", "replay_recovery"))
    mainline_method = attr_name.lower() in MAINLINE_METHODS
    if class_level and ((domain in MAINLINE_DOMAINS) or mainline_method or authority_sensitive or state_sensitive):
        return "BLOCKER", "promote_into_native_class_before_removal", "class-level function replacement changes authority/ownership/execution mainline behavior"

    if kind == "builtins_registry_bridge":
        return "COMPATIBILITY_BRIDGE", "replace_with_owned_runtime_registry", "builtins registry is a process-global compatibility bridge"
    if target.startswith("self.") and target.count(".") == 1 and not has_compatibility_word(target, expression):
        return "NATIVE_OWNER", "retain_native_owner_assignment", "normal instance-owned runtime dependency assignment"
    if kind in {"runtime_owner_override", "compatibility_bridge_graft", "class_level_replacement"}:
        return "COMPATIBILITY_BRIDGE", "migrate_to_suspected_native_owner", "runtime replacement can be taken over by an explicit native owner"
    if kind == "class_level_state_override" and domain in {"planner", "recovery"}:
        return "COMPATIBILITY_BRIDGE", "migrate_class_state_to_suspected_native_owner", "class-level planner/recovery state override needs an explicit native owner"
    return "MANUAL_REVIEW", "manual_owner_and_behavior_review", "replacement shape is ambiguous and cannot be classified safely"


def make_item(
    *,
    path: str,
    line: int,
    expression: str,
    target: str,
    kind: str,
    class_level: bool,
    attr_name: str,
) -> ReplacementItem:
    domain = owner_domain(path, target, expression)
    classification, action, reason = classify(
        path=path,
        target=target,
        expression=expression,
        kind=kind,
        domain=domain,
        class_level=class_level,
        attr_name=attr_name,
    )
    marked = special_target(target)
    non_mainline = (
        not path.startswith("tests/")
        and marked is None
        and domain in {"scheduler", "task_runner", "step_executor", "runtime_authority", "recovery"}
        and classification in {"BLOCKER", "COMPATIBILITY_BRIDGE", "MANUAL_REVIEW"}
    )
    return ReplacementItem(
        source_path=path,
        source_line=line,
        expression=expression,
        owner_domain=domain,
        replacement_kind=kind,
        classification=classification,
        action=action,
        reason=reason,
        chain_target=target,
        suspected_native_owner=suspected_owner(domain, target),
        special_target=marked,
        non_mainline_issue=non_mainline,
    )


def scan_assignment(path: str, source: str, node: ast.Assign | ast.AnnAssign) -> list[ReplacementItem]:
    value = node.value
    if value is None:
        return []
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    expression = compact_expression(source, node, "assignment")
    items: list[ReplacementItem] = []
    for target_node in targets:
        if not isinstance(target_node, ast.Attribute):
            continue
        target = dotted(target_node)
        root = target.split(".", 1)[0]
        attr = target_node.attr
        class_level = bool(root[:1].isupper())
        function_replacement = class_level and is_function_replacement_value(value)
        owner_override = attr.lower() in OWNER_ATTRIBUTES
        compat_graft = has_compatibility_word(target, expression)
        if not (class_level or owner_override or compat_graft):
            continue
        if class_level:
            kind = "class_level_replacement" if function_replacement else "class_level_state_override"
        elif owner_override:
            kind = "runtime_owner_override"
        else:
            kind = "compatibility_bridge_graft"
        items.append(make_item(
            path=path,
            line=node.lineno,
            expression=expression,
            target=target,
            kind=kind,
            class_level=class_level,
            attr_name=attr,
        ))
    return items


def scan_setattr(path: str, source: str, node: ast.Call) -> ReplacementItem | None:
    func = dotted(node.func)
    if func not in {"setattr", "monkeypatch.setattr"} or len(node.args) < 2:
        return None
    target_object = dotted(node.args[0]) or compact_expression(source, node.args[0], "object")
    attr_node = node.args[1]
    attr = attr_node.value if isinstance(attr_node, ast.Constant) and isinstance(attr_node.value, str) else compact_expression(source, attr_node, "attribute")
    target = f"{target_object}.{attr}" if attr else target_object
    expression = compact_expression(source, node, "setattr(...)")
    is_test_patch = path.startswith("tests/") or func == "monkeypatch.setattr"
    builtins_registry = target_object == "builtins" and ("registry" in attr.lower() or has_compatibility_word(attr))
    owner_override = attr.lower() in OWNER_ATTRIBUTES
    compat_graft = has_compatibility_word(target, expression)
    class_level = bool(target_object[:1].isupper()) and len(node.args) >= 3
    if not (is_test_patch or builtins_registry or owner_override or compat_graft or class_level):
        return None
    if is_test_patch:
        kind = "test_monkeypatch"
    elif builtins_registry:
        kind = "builtins_registry_bridge"
    elif class_level:
        kind = "class_level_replacement"
    elif owner_override:
        kind = "runtime_owner_override"
    else:
        kind = "compatibility_bridge_graft"
    return make_item(
        path=path,
        line=node.lineno,
        expression=expression,
        target=target,
        kind=kind,
        class_level=class_level,
        attr_name=attr,
    )


def scan_file(path: Path) -> list[ReplacementItem]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []
    rel = relative(path)
    items: list[ReplacementItem] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            items.extend(scan_assignment(rel, source, node))
        elif isinstance(node, ast.Call):
            item = scan_setattr(rel, source, node)
            if item is not None:
                items.append(item)
    return items


def collect_replacements() -> list[ReplacementItem]:
    unique: dict[tuple[str, int, str, str], ReplacementItem] = {}
    for path in iter_python_files():
        for item in scan_file(path):
            key = (item.source_path, item.source_line, item.chain_target, item.replacement_kind)
            unique[key] = item
    return sorted(unique.values(), key=lambda item: (item.source_path, item.source_line, item.chain_target, item.replacement_kind))


def zero_patch_residue() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in iter_python_files():
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


def write_report(
    items: list[ReplacementItem],
    residues: list[dict[str, Any]],
    verification: list[dict[str, Any]],
    counts: Counter[str],
    owners: Counter[str],
    kinds: Counter[str],
    top_files: list[tuple[str, int]],
    non_mainline: list[ReplacementItem],
) -> None:
    lines = [
        "# Runtime Replacement Inventory — Stage 11",
        "",
        "Inventory and classification only. Stage 11 does not modify runtime production behavior.",
        "",
        "## Summary",
        "",
        f"- Replacement total: {len(items)}",
        f"- Blocker count: {counts['BLOCKER']}",
        f"- Compatibility bridge count: {counts['COMPATIBILITY_BRIDGE']}",
        f"- Test-only count: {counts['TEST_ONLY']}",
        f"- Native-owner count: {counts['NATIVE_OWNER']}",
        f"- Manual-review count: {counts['MANUAL_REVIEW']}",
        f"- ZERO_PATCH residue: {len(residues)}",
        f"- Non-mainline issues: {len(non_mainline)}",
        "",
        "## By classification",
        "",
    ]
    for name in ("TEST_ONLY", "NATIVE_OWNER", "COMPATIBILITY_BRIDGE", "BLOCKER", "MANUAL_REVIEW"):
        lines.append(f"- `{name}`: {counts[name]}")
    lines.extend(["", "## By owner domain", ""])
    for name in ("scheduler", "task_runner", "step_executor", "runtime_authority", "planner", "recovery", "unknown"):
        lines.append(f"- `{name}`: {owners[name]}")
    lines.extend(["", "## By replacement kind", ""])
    for name, count in kinds.most_common():
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Top files", ""])
    for path, count in top_files:
        lines.append(f"- `{path}`: {count}")

    lines.extend(["", "## Special mainline targets", ""])
    for target in sorted(SPECIAL_TARGETS):
        matches = [item for item in items if item.special_target == target]
        lines.append(f"### `{target}` ({len(matches)})")
        lines.append("")
        if matches:
            for item in matches:
                lines.append(f"- `{item.source_path}:{item.source_line}` `{item.classification}` — {item.expression}")
        else:
            lines.append("- No replacement detected.")
        lines.append("")
    authority_matches = [item for item in items if item.special_target == "RuntimeAuthority / execution_authority enforce path"]
    lines.append(f"### `RuntimeAuthority / execution_authority enforce path` ({len(authority_matches)})")
    lines.append("")
    if authority_matches:
        for item in authority_matches:
            lines.append(f"- `{item.source_path}:{item.source_line}` `{item.classification}` — {item.expression}")
    else:
        lines.append("- No replacement detected.")

    lines.extend(["", "## Blockers", ""])
    blockers = [item for item in items if item.classification == "BLOCKER"]
    if blockers:
        for item in blockers:
            lines.append(f"- `{item.source_path}:{item.source_line}` `{item.owner_domain}` `{item.chain_target}` — {item.reason}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Non-Mainline Issue Report", ""])
    lines.append(
        "These production findings are not one of the explicitly named Stage 11 mainline targets, but can still affect runtime ownership, authority, scheduler, task_runner, step_executor, or recovery/replay behavior."
    )
    lines.append("")
    non_mainline_files = Counter(item.source_path for item in non_mainline)
    for path, count in non_mainline_files.most_common():
        lines.append(f"- `{path}`: {count}")
    lines.extend(["", "### Detailed non-mainline findings", ""])
    if non_mainline:
        for item in non_mainline:
            lines.append(
                f"- `{item.source_path}:{item.source_line}` `{item.classification}` `{item.owner_domain}` "
                f"`{item.chain_target}` — {item.expression}"
            )
    else:
        lines.append("- None.")

    lines.extend(["", "## Verification", ""])
    lines.append(f"### {'PASS' if not residues else 'FAIL'}: active ZERO_PATCH identifier scan")
    lines.append("")
    lines.append(f"Active residue count: {len(residues)}")
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
        f"- `{relative(INVENTORY_PATH)}`",
        f"- `{relative(SUMMARY_PATH)}`",
        f"- `{relative(REPORT_PATH)}`",
        "",
    ])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = collect_replacements()
    residues = zero_patch_residue()
    verification = [run_verification(name, command) for name, command in VERIFY_COMMANDS]

    counts = Counter(item.classification for item in items)
    owners = Counter(item.owner_domain for item in items)
    kinds = Counter(item.replacement_kind for item in items)
    file_counts = Counter(item.source_path for item in items)
    top_files = file_counts.most_common(25)
    non_mainline = [item for item in items if item.non_mainline_issue]
    passed = not residues and all(result["passed"] for result in verification)

    inventory = {
        "stage": "Runtime Replacement Inventory Stage11",
        "scan_roots": ["core/**/*.py", "tests/**/*.py"],
        "replacement_total": len(items),
        "zero_patch_residue_count": len(residues),
        "replacement_chain": [asdict(item) for item in items],
    }
    INVENTORY_PATH.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "stage": "Runtime Replacement Inventory Stage11",
        "replacement_total": len(items),
        "by_classification": {name: counts[name] for name in ("TEST_ONLY", "NATIVE_OWNER", "COMPATIBILITY_BRIDGE", "BLOCKER", "MANUAL_REVIEW")},
        "by_owner_domain": {name: owners[name] for name in ("scheduler", "task_runner", "step_executor", "runtime_authority", "planner", "recovery", "unknown")},
        "by_replacement_kind": dict(kinds.most_common()),
        "blocker_count": counts["BLOCKER"],
        "compatibility_bridge_count": counts["COMPATIBILITY_BRIDGE"],
        "test_only_count": counts["TEST_ONLY"],
        "top_files": [{"path": path, "count": count} for path, count in top_files],
        "non_mainline_issue_count": len(non_mainline),
        "zero_patch_residue_count": len(residues),
        "native_contract_tests_passed": next((result["passed"] for result in verification if result["name"] == "runtime_contracts"), False),
        "verification_passed": passed,
        "verification": verification,
        "outputs": {
            "inventory": relative(INVENTORY_PATH),
            "summary": relative(SUMMARY_PATH),
            "report": relative(REPORT_PATH),
        },
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(items, residues, verification, counts, owners, kinds, top_files, non_mainline)

    print(f"replacement total: {len(items)}")
    print(f"by classification: {dict(counts)}")
    print(f"by owner domain: {dict(owners)}")
    print(f"non-mainline issues: {len(non_mainline)}")
    print(f"ZERO_PATCH residue: {len(residues)}")
    print("verification passed" if passed else "verification failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
