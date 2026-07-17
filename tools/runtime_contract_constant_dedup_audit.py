from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "runtime_contract_constant_dedup.txt"

CONTRACT_IMPORT_ROOT = "core.runtime.contracts"

SKIP_DIRS = {
    ".git",
    ".agents",
    ".codex",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "workspace",
    "cache",
    "data",
    "logs",
    "memory",
    "run",
    "htmlcov",
    "dist",
    "build",
}

TEXT_EXTENSIONS = {".py"}

CONTRACT_TARGETS = {
    "authority_context": {
        "contract": "core.runtime.contracts.authority_context_contract",
        "tokens": (
            "authority_context",
            "authority_chain",
            "execution_authority_granted",
            "can_execute_privileged_step",
            "authority_propagation_required",
        ),
        "constant_patterns": (
            "AUTHORITY_CONTEXT",
            "AUTHORITY_CHAIN",
            "EXECUTION_AUTHORITY",
        ),
    },
    "runtime_identity": {
        "contract": "core.runtime.contracts.runtime_identity_contract",
        "tokens": (
            "runtime_identity",
            "runtime_session_id",
            "session_id",
            "goal_lineage_id",
            "branch_id",
        ),
        "constant_patterns": (
            "RUNTIME_IDENTITY",
            "IDENTITY_FIELDS",
            "SESSION_ID",
            "GOAL_LINEAGE",
        ),
    },
    "runtime_session": {
        "contract": "core.runtime.contracts.runtime_session_contract",
        "tokens": (
            "runtime_session",
            "session_status",
            "terminal_status",
            "active_status",
            "finished",
            "failed",
            "queued",
            "running",
        ),
        "constant_patterns": (
            "SESSION_STATUS",
            "TERMINAL_STATUSES",
            "ACTIVE_STATUSES",
            "STATUS_ALIASES",
            "TASK_STATUS",
            "RUNTIME_STATUS",
        ),
    },
    "runtime_execution": {
        "contract": "core.runtime.contracts.runtime_execution_contract",
        "tokens": (
            "execution_id",
            "runtime_execution",
            "execution_mode",
            "execution_authority",
            "repair_replay",
        ),
        "constant_patterns": (
            "EXECUTION_STATUS",
            "RUNTIME_EXECUTION",
            "EXECUTION_MODE",
            "CHECKPOINT_TYPE",
        ),
    },
    "runtime_boundary": {
        "contract": "core.runtime.contracts.runtime_boundary_contract",
        "tokens": (
            "scheduler",
            "task_runner",
            "dispatcher",
            "operator",
            "boundary_direction",
            "runtime_boundary",
        ),
        "constant_patterns": (
            "RUNTIME_BOUNDARY",
            "BOUNDARY_DIRECTION",
            "BOUNDARY_COMPONENT",
            "BOUNDARY_STATUS",
        ),
    },
}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _iter_py_files() -> Iterable[Path]:
    for path in ROOT.rglob("*.py"):
        if not path.is_file():
            continue
        if _is_skipped(path):
            continue
        yield path


def _safe_parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(_read_text(path), filename=str(path))
    except SyntaxError:
        return None


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Subscript):
        return _name_of(node.value)
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    if isinstance(node, ast.Tuple):
        return "tuple"
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Set):
        return "set"
    if isinstance(node, ast.Dict):
        return "dict"
    return type(node).__name__


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets: list[ast.AST]
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    else:
        targets = [node.target]

    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, ast.Attribute):
            names.append(_name_of(target))
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                name = _name_of(item)
                if name:
                    names.append(name)
    return names


def _literal_string_values(node: ast.AST | None) -> list[str]:
    if node is None:
        return []
    values: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            values.append(child.value)
    return values


def _imported_contracts(tree: ast.Module) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            if module.startswith(CONTRACT_IMPORT_ROOT):
                imported.add(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(CONTRACT_IMPORT_ROOT):
                    imported.add(alias.name)
    return imported


def _family_for_assignment(name: str, value: ast.AST | None) -> str:
    if value is None:
        return ""
    normalized_name = name.upper()
    literal_text = " ".join(_literal_string_values(value)).lower()
    value_type = _name_of(value).lower()
    haystack = " ".join([normalized_name.lower(), literal_text, value_type])

    for family, rules in CONTRACT_TARGETS.items():
        if any(pattern in normalized_name for pattern in rules["constant_patterns"]):
            return family
        if any(token.lower() in haystack for token in rules["tokens"]):
            return family
    return ""


def _scan_constant_candidates() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in _iter_py_files():
        rel = _rel(path)
        if rel.startswith("core/runtime/contracts/"):
            continue

        tree = _safe_parse(path)
        if tree is None:
            continue

        imported_contracts = _imported_contracts(tree)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            names = _assigned_names(node)
            if not names:
                continue

            value = node.value if isinstance(node, ast.AnnAssign) else node.value
            for name in names:
                family = _family_for_assignment(name, value)
                if not family:
                    continue
                contract = CONTRACT_TARGETS[family]["contract"]
                rows.append(
                    {
                        "path": rel,
                        "line": int(getattr(node, "lineno", 0) or 0),
                        "name": name,
                        "family": family,
                        "contract": contract,
                        "already_imports_contract": contract in imported_contracts,
                        "value_type": _name_of(value),
                        "literal_sample": ", ".join(_literal_string_values(value)[:8]),
                    }
                )
    return sorted(rows, key=lambda row: (str(row["family"]), str(row["path"]), int(row["line"]), str(row["name"])))


def _risk_for_row(row: dict[str, object]) -> str:
    path = str(row["path"])
    name = str(row["name"])
    if path.startswith("tests/"):
        return "test_only"
    if path.startswith("tools/"):
        return "tooling"
    if name.isupper():
        return "constant_candidate"
    return "local_assignment_review"


def _write_report() -> dict[str, object]:
    rows = _scan_constant_candidates()
    family_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    direct_candidates: list[dict[str, object]] = []

    for row in rows:
        family = str(row["family"])
        family_counts[family] = family_counts.get(family, 0) + 1
        risk = _risk_for_row(row)
        row["risk"] = risk
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
        if risk == "constant_candidate" and not bool(row["already_imports_contract"]):
            direct_candidates.append(row)

    lines: list[str] = []
    lines.append("Runtime Contract Constant Dedup Audit")
    lines.append("")
    lines.append("Scope")
    lines.append("-----")
    lines.append("Audit only. No production code modified.")
    lines.append("Goal: find repeated runtime contract constants that may later be replaced by core.runtime.contracts imports.")
    lines.append("")

    lines.append("Summary")
    lines.append("-------")
    lines.append(f"candidate_rows: {len(rows)}")
    lines.append(f"direct_constant_candidates_without_contract_import: {len(direct_candidates)}")
    lines.append("")

    lines.append("Family Counts")
    lines.append("-------------")
    if family_counts:
        for key in sorted(family_counts):
            lines.append(f"- {key}: {family_counts[key]}")
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Risk Counts")
    lines.append("-----------")
    if risk_counts:
        for key in sorted(risk_counts):
            lines.append(f"- {key}: {risk_counts[key]}")
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Direct Constant Candidates")
    lines.append("--------------------------")
    if direct_candidates:
        for row in direct_candidates:
            lines.append(
                f"- {row['path']}:{row['line']} | family={row['family']} | "
                f"name={row['name']} | suggested_contract={row['contract']} | "
                f"value_type={row['value_type']} | literals={row['literal_sample']}"
            )
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("All Candidate Rows")
    lines.append("------------------")
    if rows:
        for row in rows:
            lines.append(
                f"- {row['path']}:{row['line']} | family={row['family']} | "
                f"risk={row['risk']} | name={row['name']} | "
                f"already_imports_contract={row['already_imports_contract']} | "
                f"suggested_contract={row['contract']} | value_type={row['value_type']} | "
                f"literals={row['literal_sample']}"
            )
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Recommended Next Step")
    lines.append("---------------------")
    lines.append("Do not bulk-rewrite all candidates.")
    lines.append("Start with one family only, preferably runtime_session, and replace constants only where behavior is provably identical.")
    lines.append("Keep Scheduler freeze intact; do not touch Scheduler unless a dedicated behavior audit says so.")
    lines.append("")

    lines.append("Non-Mainline Issues")
    lines.append("-------------------")
    lines.append("- Audit only. No production code was changed.")
    lines.append("- Candidate rows are heuristic; each replacement needs manual behavior comparison before code changes.")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return {
        "report": REPORT,
        "candidate_rows": len(rows),
        "direct_constant_candidates": len(direct_candidates),
        "family_counts": family_counts,
        "risk_counts": risk_counts,
    }


def main() -> int:
    result = _write_report()
    print("Runtime contract constant dedup audit complete")
    print(f"report: {Path(result['report']).relative_to(ROOT)}")
    print(
        "counts: "
        f"candidate_rows={result['candidate_rows']}, "
        f"direct_constant_candidates={result['direct_constant_candidates']}"
    )
    print("family_counts:")
    if result["family_counts"]:
        for key in sorted(result["family_counts"]):
            print(f"- {key}: {result['family_counts'][key]}")
    else:
        print("- <none>")
    print("risk_counts:")
    if result["risk_counts"]:
        for key in sorted(result["risk_counts"]):
            print(f"- {key}: {result['risk_counts'][key]}")
    else:
        print("- <none>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
