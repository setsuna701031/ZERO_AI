from __future__ import annotations

import ast
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = REPO_ROOT / "core" / "tasks" / "scheduler.py"
REPORT_PATH = REPO_ROOT / "scheduler_run_one_step_wrapper_diff_inventory.txt"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


TARGET_NAMES = {
    "_zero_v734_run_one_step",
    "_zero_v352_scheduler_run_one_step",
    "_zero_v7332_scheduler_run_one_step",
    "_zero_v7333_scheduler_run_one_step",
    "_zero_v7334_scheduler_run_one_step",
    "_zero_v7335_scheduler_run_one_step",
    "_zero_v7336_scheduler_run_one_step",
    "_zero_scheduler_run_one_step_v1",
    "_zero_scheduler_run_one_step_v2",
    "_zero_scheduler_run_one_step_v3",
    "_zero_scheduler_run_one_step_v4",
    "_zero_scheduler_run_one_step_v5",
    "_zero_scheduler_run_one_step_v6",
    "_zero_scheduler_run_one_step_v7",
    "_zero_scheduler_run_one_step_v8",
    "_zero_scheduler_run_one_step_v9",
    "_zero_scheduler_run_one_step_v10",
    "_zero_scheduler_run_one_step_v11",
    "_zero_scheduler_run_one_step_v12",
    "_zero_scheduler_run_one_step_v13",
    "_zero_scheduler_run_one_step_v14",
    "_zero_scheduler_run_one_step_v15",
    "_zero_scheduler_run_one_step_v16",
}


KEYWORDS = {
    "status": ("status", "state", "finished", "completed", "failed", "running"),
    "operator_bridge": ("operator_bridge", "Operator", "operator"),
    "runtime_identity": ("runtime_identity", "runtime_session_id", "session_id"),
    "goal_lineage": ("goal_lineage", "goal_lineage_id", "root_goal_id", "goal_id"),
    "queue": ("queue", "task_queue", "pending", "claimed"),
    "checkpoint": ("checkpoint", "snapshot", "resume"),
    "event": ("event", "emit", "runtime_event"),
    "evidence": ("evidence", "decision_evidence"),
    "authority": ("authority", "capability", "permission"),
    "dispatcher": ("dispatcher", "runtime_dispatcher"),
    "completion": ("complete", "completed_steps", "complete_id"),
    "exception": ("except", "Exception", "traceback", "error"),
}


def node_text(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def called_names(fn: ast.FunctionDef) -> list[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
    return sorted(names)


def assigned_names(fn: ast.FunctionDef) -> list[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
                elif isinstance(target, ast.Attribute):
                    names.add(target.attr)
                elif isinstance(target, ast.Subscript):
                    names.add(ast.unparse(target))
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
            elif isinstance(target, ast.Subscript):
                names.add(ast.unparse(target))
    return sorted(names)


def return_count(fn: ast.FunctionDef) -> int:
    return sum(1 for node in ast.walk(fn) if isinstance(node, ast.Return))


def raise_count(fn: ast.FunctionDef) -> int:
    return sum(1 for node in ast.walk(fn) if isinstance(node, ast.Raise))


def try_count(fn: ast.FunctionDef) -> int:
    return sum(1 for node in ast.walk(fn) if isinstance(node, ast.Try))


def keyword_hits(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for group, words in KEYWORDS.items():
        hits = sorted({word for word in words if word in text})
        if hits:
            result[group] = hits
    return result


def main() -> int:
    source = SCHEDULER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    functions: list[ast.FunctionDef] = [
        node for node in tree.body if isinstance(node, ast.FunctionDef)
    ]

    targets = [fn for fn in functions if fn.name in TARGET_NAMES]

    lines: list[str] = [
        "Scheduler run_one_step Wrapper Diff Inventory",
        "",
        f"scheduler_path: {SCHEDULER_PATH}",
        f"target_wrappers_found: {len(targets)}",
        "",
    ]

    for fn in targets:
        text = node_text(source, fn)
        hits = keyword_hits(text)
        calls = called_names(fn)
        assigns = assigned_names(fn)

        lines.extend(
            [
                "=" * 88,
                f"name: {fn.name}",
                f"line: {fn.lineno}",
                f"end_line: {getattr(fn, 'end_lineno', 'unknown')}",
                f"line_count: {getattr(fn, 'end_lineno', fn.lineno) - fn.lineno + 1 if getattr(fn, 'end_lineno', None) else 'unknown'}",
                f"returns: {return_count(fn)}",
                f"raises: {raise_count(fn)}",
                f"try_blocks: {try_count(fn)}",
                "",
                "Keyword domains:",
            ]
        )

        if hits:
            for group, words in hits.items():
                lines.append(f"- {group}: {', '.join(words)}")
        else:
            lines.append("- none")

        lines.extend(["", "Calls:"])
        if calls:
            for name in calls:
                lines.append(f"- {name}")
        else:
            lines.append("- none")

        lines.extend(["", "Assignments / Mutations:"])
        if assigns:
            for name in assigns:
                lines.append(f"- {name}")
        else:
            lines.append("- none")

        lines.extend(["", "Source:", "```python", text.rstrip(), "```", ""])

    lines.extend(
        [
            "=" * 88,
            "Non-Mainline Issue Reporting:",
            "- This inventory does not modify scheduler.py.",
            "- This inventory is intentionally verbose because old wrappers are still active.",
            "- Do not delete wrappers until their behavioral domains are merged into a canonical run_one_step.",
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())