from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "tasks" / "scheduler.py"
REPORT = ROOT / "scheduler_mainline_inventory.txt"
SELF_TOOL = "tools/scheduler_mainline_inventory.py"

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

TEXT_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".ps1",
    ".bat",
    ".sh",
}

ZERO_FAMILY_ORDER = (
    "zero_v7xx",
    "zero_v3xx",
    "zero_v1x",
    "zero_other",
    "stage",
    "legacy",
    "scheduler_compat",
    "other",
)

RUNTIME_SURFACE_FRAGMENTS = (
    "adapter",
    "authority",
    "boundary",
    "compat",
    "create_task",
    "dispatch",
    "entry",
    "fallback",
    "gateway",
    "operator",
    "queue",
    "review",
    "run_one_step",
    "runtime",
    "tick",
)

RUNTIME_CATEGORIES = {
    "execution",
    "queue",
    "repair",
    "runtime_boundary",
}

RUNTIME_BINDING_FAMILY_ORDER = (
    "path",
    "dispatch",
    "repo_state",
    "planning",
    "repair",
    "queue",
    "tick",
    "create_task",
    "review",
    "run_one_step",
    "build/constants",
    "unknown",
)


def _scheduler_binding_attr(name: object) -> str:
    return str(name or "").rsplit(".", 1)[-1]


def _is_scheduler_constant_assignment_name(name: object) -> bool:
    attr = _scheduler_binding_attr(name)
    return (
        attr == "SCHEDULER_BUILD"
        or attr.startswith("REPAIRABLE_")
        or attr.startswith("CODE_CHAIN_")
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def _iter_text_files() -> Iterable[Path]:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if _is_skipped(path):
            continue
        if not _is_text_file(path):
            continue
        yield path


def _safe_parse(path: Path) -> ast.Module:
    return ast.parse(_read_text(path), filename=str(path))


def _top_level_import_count(tree: ast.Module) -> int:
    return sum(isinstance(node, (ast.Import, ast.ImportFrom)) for node in tree.body)


def _top_level_classes(tree: ast.Module) -> list[ast.ClassDef]:
    return [node for node in tree.body if isinstance(node, ast.ClassDef)]


def _top_level_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _scheduler_class(tree: ast.Module) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Scheduler":
            return node
    raise RuntimeError("Scheduler class not found")


def _class_methods(cls: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    if isinstance(node, ast.Subscript):
        return _name_of(node.value)
    return ""


def _calls_in(node: ast.AST) -> list[str]:
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _name_of(child.func)
            if name:
                calls.append(name)
    return sorted(set(calls))


def _returns_single_forwarding_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = [
        stmt
        for stmt in node.body
        if not (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )
    ]
    if len(body) != 1:
        return False
    stmt = body[0]
    return isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call)


def _is_runtime_surface_text(*parts: object) -> bool:
    haystack = " ".join(str(part).lower() for part in parts if part is not None)
    return any(fragment in haystack for fragment in RUNTIME_SURFACE_FRAGMENTS)


def _is_runtime_binding_item(item: dict[str, object]) -> bool:
    if _is_scheduler_constant_assignment_name(item.get("name")):
        return False
    if str(item.get("category")) in RUNTIME_CATEGORIES:
        return True
    return _is_runtime_surface_text(
        item.get("name"),
        item.get("search_name"),
        item.get("assigned_value"),
        item.get("assigned_name"),
        " ".join(str(call) for call in item.get("calls", [])),
    )


def _binding_class(item: dict[str, object]) -> str:
    if _is_runtime_binding_item(item):
        return "runtime_binding"
    if str(item.get("kind")) == "assignment/wrapper":
        return "monkey_patch"
    if item.get("wrapper_only"):
        return "wrapper_only"
    return "ordinary"


def _attach_binding_classification(inventory_items: list[dict[str, object]]) -> None:
    for item in inventory_items:
        binding_class = _binding_class(item)
        item["binding_class"] = binding_class
        item["monkey_patch"] = str(item.get("kind")) == "assignment/wrapper"
        item["runtime_binding"] = binding_class == "runtime_binding"
        item["removal_safe"] = (
            int(item.get("active_refs", 0)) == 0
            and not bool(item["monkey_patch"])
            and not bool(item["runtime_binding"])
        )


def _unsafe_runtime_bindings(
    unsafe_bindings: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        item
        for item in unsafe_bindings
        if not _is_scheduler_constant_assignment_name(item.get("name"))
        if _is_runtime_surface_text(
            item.get("name"),
            item.get("assigned_value"),
            item.get("assigned_name"),
        )
    ]


def _unsafe_monkey_patches(
    unsafe_bindings: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        item
        for item in unsafe_bindings
        if _is_scheduler_constant_assignment_name(item.get("name"))
        or not _is_runtime_surface_text(
            item.get("name"),
            item.get("assigned_value"),
            item.get("assigned_name"),
        )
    ]


def _append_symbol_rows(report_lines: list[str], rows: list[dict[str, object]]) -> None:
    if not rows:
        report_lines.append("- <none>")
        return
    for item in rows:
        report_lines.append(
            f"- {item['name']} (line {item['line']}; active_refs={item['active_refs']}; "
            f"archived_refs={item['archived_refs']}; report_refs={item['report_refs']}; "
            f"binding_class={item['binding_class']})"
        )
        if item["kind"] == "assignment/wrapper":
            report_lines.append(f"  assigned_value: {item['assigned_value']}")
        report_lines.append(f"  reason: {item['reference_reason']}")


def _binding_functional_family(item: dict[str, object]) -> str:
    name = str(item.get("name") or "")
    assigned_name = str(item.get("assigned_name") or "")
    target_attr = _scheduler_binding_attr(name)
    rule_text = " ".join([target_attr, assigned_name]).lower()
    normalized_rule_text = re.sub(r"[^a-z0-9]+", "_", rule_text).strip("_")
    tokens = [token for token in normalized_rule_text.split("_") if token]

    def starts_with(prefix: str) -> bool:
        return any(token == prefix or token.startswith(prefix) for token in tokens)

    def contains(fragment: str) -> bool:
        return fragment in tokens or fragment in normalized_rule_text

    if _is_scheduler_constant_assignment_name(name):
        return "build/constants"
    if contains("run_one_step"):
        return "run_one_step"
    if starts_with("tick"):
        return "tick"
    if contains("create_task"):
        return "create_task"
    if starts_with("review") or contains("review"):
        return "review"
    if starts_with("dispatch") or contains("dispatch"):
        return "dispatch"
    if starts_with("repo") or contains("repo_task"):
        return "repo_state"
    if starts_with("queue") or contains("queue"):
        return "queue"
    if starts_with("repair") or contains("repair"):
        return "repair"
    if starts_with("path") or contains("path"):
        return "path"
    if starts_with("plan") or contains("normalize_replan"):
        return "planning"
    return "unknown"


def _runtime_binding_families(
    unsafe_bindings: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    families: dict[str, list[dict[str, object]]] = {
        family: [] for family in RUNTIME_BINDING_FAMILY_ORDER
    }
    for item in unsafe_bindings:
        family = _binding_functional_family(item)
        item["binding_family"] = family
        families.setdefault(family, []).append(item)
    return families


def _runtime_entrypoint_families(
    unsafe_runtime_entrypoints: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    families: dict[str, list[dict[str, object]]] = {
        family: [] for family in RUNTIME_BINDING_FAMILY_ORDER
    }
    for item in unsafe_runtime_entrypoints:
        family = _binding_functional_family(item)
        families.setdefault(family, []).append(item)
    return families


def _active_refs_summary(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "none"
    active_ref_counts = [int(row["active_refs"]) for row in rows]
    zero_count = sum(count == 0 for count in active_ref_counts)
    return (
        f"min={min(active_ref_counts)}, max={max(active_ref_counts)}, "
        f"zero_ref_bindings={zero_count}/{len(rows)}"
    )


def _consolidation_status_and_reason(
    family: str,
    binding_rows: list[dict[str, object]],
    runtime_entrypoint_rows: list[dict[str, object]],
) -> tuple[str, str]:
    binding_count = len(binding_rows)
    runtime_entrypoint_count = len(runtime_entrypoint_rows)
    zero_ref_bindings = sum(int(row["active_refs"]) == 0 for row in binding_rows)

    if family == "build/constants":
        return (
            "do_not_touch",
            "build and allowlist constants are monkey-patched compatibility markers, not wrapper-collapse targets.",
        )
    if family in {"planning", "review", "path", "unknown"}:
        if zero_ref_bindings or runtime_entrypoint_count:
            return (
                "candidate_for_family_audit",
                "family has zero-active-ref binding rows or dynamic runtime entrypoints; audit ownership before any consolidation.",
            )
        return (
            "keep_runtime_surface",
            "no zero-active-ref binding signal is present; keep the existing runtime surface.",
        )
    if family in {
        "run_one_step",
        "tick",
        "dispatch",
        "queue",
        "repair",
        "repo_state",
    }:
        if binding_count > 1:
            return (
                "candidate_for_wrapper_collapse",
                "multiple runtime/compatibility bindings exist in a protected family; collapse only after a dedicated behavior audit.",
            )
        return (
            "keep_runtime_surface",
            "protected runtime family with a single binding row; do not classify as safe removal.",
        )
    if family == "create_task":
        return (
            "keep_runtime_surface",
            "protected task creation surface; do not classify as safe removal.",
        )
    return (
        "do_not_touch",
        "unrecognized consolidation rule; preserve current binding behavior.",
    )


def _runtime_binding_consolidation_matrix(
    binding_families: dict[str, list[dict[str, object]]],
    entrypoint_families: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    matrix: list[dict[str, object]] = []
    for family in RUNTIME_BINDING_FAMILY_ORDER:
        binding_rows = sorted(
            binding_families.get(family, []),
            key=lambda row: int(row["line"]),
        )
        runtime_entrypoint_rows = sorted(
            entrypoint_families.get(family, []),
            key=lambda row: (str(row["kind"]), int(row["line"])),
        )
        status, reason = _consolidation_status_and_reason(
            family,
            binding_rows,
            runtime_entrypoint_rows,
        )
        matrix.append(
            {
                "family": family,
                "binding_count": len(binding_rows),
                "runtime_entrypoint_count": len(runtime_entrypoint_rows),
                "active_refs_summary": _active_refs_summary(binding_rows),
                "consolidation_status": status,
                "reason": reason,
            }
        )
    return matrix


def _append_runtime_binding_consolidation_matrix(
    report_lines: list[str],
    matrix: list[dict[str, object]],
) -> None:
    report_lines.append("Scheduler Runtime Binding Consolidation Matrix")
    report_lines.append("------------------------------------------------")
    report_lines.append(
        "Consolidation statuses are planning labels only; no row is a safe-removal classification."
    )
    report_lines.append("")
    for row in matrix:
        report_lines.append(f"{row['family']}:")
        report_lines.append(f"  binding_count: {row['binding_count']}")
        report_lines.append(
            f"  runtime_entrypoint_count: {row['runtime_entrypoint_count']}"
        )
        report_lines.append(f"  active_refs_summary: {row['active_refs_summary']}")
        report_lines.append(
            f"  consolidation_status: {row['consolidation_status']}"
        )
        report_lines.append(f"  reason: {row['reason']}")
        report_lines.append("")


def _append_runtime_binding_families(
    report_lines: list[str],
    families: dict[str, list[dict[str, object]]],
) -> None:
    report_lines.append("Runtime Binding Families")
    report_lines.append("------------------------")
    report_lines.append("Scheduler runtime bindings and monkey patches grouped by functional family.")
    report_lines.append("safe_to_remove is always false for these binding families.")
    report_lines.append("Classifier rules are deterministic and evaluated in this order:")
    report_lines.append("  1. SCHEDULER_BUILD, REPAIRABLE_*, CODE_CHAIN_* -> build/constants")
    report_lines.append("  2. run_one_step* -> run_one_step")
    report_lines.append("  3. tick* -> tick")
    report_lines.append("  4. create_task* -> create_task")
    report_lines.append("  5. review* -> review")
    report_lines.append("  6. dispatch* -> dispatch")
    report_lines.append("  7. repo* -> repo_state")
    report_lines.append("  8. queue* -> queue")
    report_lines.append("  9. repair* -> repair")
    report_lines.append("  10. path* -> path")
    report_lines.append("  11. plan* or normalize_replan* -> planning")
    report_lines.append("  12. otherwise -> unknown")
    report_lines.append("")
    for family in RUNTIME_BINDING_FAMILY_ORDER:
        rows = sorted(families.get(family, []), key=lambda row: int(row["line"]))
        any_active_refs_zero = any(int(row["active_refs"]) == 0 for row in rows)
        report_lines.append(f"{family}:")
        report_lines.append(f"  binding_count: {len(rows)}")
        report_lines.append(f"  any_active_refs_0: {any_active_refs_zero}")
        report_lines.append("  safe_to_remove: false")
        report_lines.append("  items:")
        if not rows:
            report_lines.append("    - <none>")
        else:
            for row in rows:
                report_lines.append(
                    f"    - {row['name']} (line {row['line']}; "
                    f"active_refs={row['active_refs']}; binding_class={row['binding_class']})"
                )
        report_lines.append("")


def _scheduler_method_assignments(tree: ast.Module) -> list[dict[str, object]]:
    assignments: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "Scheduler"
            ):
                value_name = _name_of(node.value)
                assignments.append(
                    {
                        "target": f"Scheduler.{target.attr}",
                        "attr": target.attr,
                        "value": ast.unparse(node.value),
                        "value_name": value_name,
                        "line": node.lineno,
                    }
                )
    return sorted(assignments, key=lambda row: int(row["line"]))


def _run_one_step_definitions(
    top_helpers: list[ast.FunctionDef | ast.AsyncFunctionDef],
    methods: list[ast.FunctionDef | ast.AsyncFunctionDef],
    assignments: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for method in methods:
        if "run_one_step" in method.name:
            rows.append(
                {
                    "kind": "scheduler_method",
                    "line": method.lineno,
                    "name": method.name,
                    "detail": "Scheduler method definition",
                }
            )
    for helper in top_helpers:
        if "run_one_step" in helper.name:
            rows.append(
                {
                    "kind": "top_level_helper",
                    "line": helper.lineno,
                    "name": helper.name,
                    "detail": "top-level function definition",
                }
            )
    for assignment in assignments:
        if "run_one_step" in str(assignment["target"]).lower() or "run_one_step" in str(
            assignment["value"]
        ).lower():
            rows.append(
                {
                    "kind": "scheduler_assignment",
                    "line": assignment["line"],
                    "name": assignment["target"],
                    "detail": str(assignment["value"])[:180],
                }
            )
    return sorted(rows, key=lambda row: int(row["line"]))


def _zero_family(name: str) -> str:
    lowered = name.lower()
    if re.search(r"(^|_)zero_v7\d+", lowered) or re.search(r"(^|_)v7\d+", lowered):
        return "zero_v7xx"
    if re.search(r"(^|_)zero_v3\d+", lowered) or re.search(r"(^|_)v3\d+", lowered):
        return "zero_v3xx"
    if re.search(r"(^|_)zero_v1\d+", lowered) or re.search(r"(^|_)v1\d+", lowered):
        return "zero_v1x"
    if "_zero" in lowered or lowered.startswith("zero_"):
        return "zero_other"
    if "stage" in lowered:
        return "stage"
    if "legacy" in lowered:
        return "legacy"
    if "compat" in lowered:
        return "scheduler_compat"
    return "other"


def _category_for_method(name: str, calls: list[str]) -> str:
    family = _zero_family(name)
    if family != "other":
        return family
    haystack = " ".join([name.lower(), *(call.lower() for call in calls)])
    if "run_one_step" in haystack or "execute" in haystack or "dispatch" in haystack:
        return "execution"
    if "queue" in haystack or "tick" in haystack:
        return "queue"
    if "repo" in haystack or "persist" in haystack:
        return "persistence"
    if "trace" in haystack or "audit" in haystack or "evidence" in haystack:
        return "evidence"
    if "repair" in haystack or "replan" in haystack:
        return "repair"
    if "runtime" in haystack or "authority" in haystack:
        return "runtime_boundary"
    return "other_private"


def _bucket_for_path(path: Path) -> str:
    rel = _rel(path)
    if rel == _rel(TARGET):
        return "target"
    if rel == _rel(REPORT):
        return "self_report"
    if rel == SELF_TOOL:
        return "self_tool"
    if rel.startswith("archive/") or "/archive/" in rel or "_archive_candidate/" in rel:
        return "archive"
    if rel.startswith("docs/") or "/docs/" in rel:
        return "doc"
    if path.suffix.lower() != ".py":
        return "report_or_text"
    if rel.startswith("tests/") or "/tests/" in rel:
        return "test"
    if rel.startswith("tools/") or "/tools/" in rel:
        return "tool"
    return "production"


def _definition_patterns(name: str) -> tuple[re.Pattern[str], ...]:
    escaped = re.escape(name)
    return (
        re.compile(rf"^\s*(async\s+def|def)\s+{escaped}\s*\("),
        re.compile(rf"^\s*class\s+{escaped}\s*[\(:]"),
        re.compile(rf"^\s*{escaped}\s*[:=]"),
        re.compile(rf"^\s*{escaped}\s*="),
    )


def _is_definition_line(name: str, line: str) -> bool:
    return any(pattern.search(line) for pattern in _definition_patterns(name))


def _reference_rows(names: list[str]) -> dict[str, list[dict[str, object]]]:
    unique_names = sorted(set(names), key=len, reverse=True)
    refs: dict[str, list[dict[str, object]]] = {name: [] for name in unique_names}
    if not unique_names:
        return refs
    matcher = re.compile(
        r"(?<![A-Za-z0-9_])("
        + "|".join(re.escape(name) for name in unique_names)
        + r")(?![A-Za-z0-9_])"
    )

    for path in _iter_text_files():
        try:
            text = _read_text(path)
        except Exception as exc:
            for name in unique_names:
                refs[name].append(
                    {
                        "path": _rel(path),
                        "line": 0,
                        "bucket": "read_error",
                        "is_definition": False,
                        "text": f"<read_error: {exc}>",
                    }
                )
            continue

        if not matcher.search(text):
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            for match in matcher.finditer(line):
                name = match.group(1)
                refs[name].append(
                    {
                        "path": _rel(path),
                        "line": line_no,
                        "bucket": _bucket_for_path(path),
                        "is_definition": _is_definition_line(name, line),
                        "text": stripped[:240],
                    }
                )

    return refs


def _active_refs(refs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        ref
        for ref in refs
        if not ref["is_definition"]
        and ref["bucket"] in {"target", "production", "test", "tool"}
    ]


def _archived_refs(refs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        ref
        for ref in refs
        if not ref["is_definition"]
        and ref["bucket"] == "archive"
    ]


def _report_refs(refs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        ref
        for ref in refs
        if not ref["is_definition"]
        and ref["bucket"] in {"doc", "report_or_text"}
    ]


def _classify_refs(refs: list[dict[str, object]]) -> tuple[str, str]:
    active = _active_refs(refs)
    archived = _archived_refs(refs)
    reports = _report_refs(refs)
    if active:
        buckets = {str(ref["bucket"]) for ref in active}
        return "C", f"active-code references exist: {', '.join(sorted(buckets))}"
    if archived or reports:
        return "B", "active_refs=0; archived/report references only"
    return "A", "no non-definition references found"


def _candidate_score(item: dict[str, object]) -> tuple[int, int, str]:
    label = str(item["reference_class"])
    family = str(item["family"])
    family_bonus = 8 if family != "other" else 0
    kind_bonus = {"assignment/wrapper": 2, "top_level_helper": 1}.get(str(item["kind"]), 0)
    label_weight = {"A": 100, "B": 50, "C": 0}[label]
    return (
        label_weight + family_bonus + kind_bonus,
        -int(item["active_refs"]),
        str(item["name"]),
    )


def _format_ref_summary(
    refs: list[dict[str, object]],
    *,
    limit: int = 8,
    active_only: bool = False,
    archived_only: bool = False,
    report_only: bool = False,
) -> list[str]:
    if active_only:
        relevant = _active_refs(refs)
    elif archived_only:
        relevant = _archived_refs(refs)
    elif report_only:
        relevant = _report_refs(refs)
    else:
        relevant = [
            ref
            for ref in refs
            if not ref["is_definition"]
            and ref["bucket"] not in {"self_tool", "self_report", "read_error"}
        ]
    if not relevant:
        return ["    - <none>"]
    lines: list[str] = []
    for ref in relevant[:limit]:
        lines.append(
            f"    - {ref['path']}:{ref['line']} [{ref['bucket']}] {ref['text']}"
        )
    if len(relevant) > limit:
        lines.append(f"    - ... truncated {len(relevant) - limit}")
    return lines


def _attach_reference_counts(
    inventory_items: list[dict[str, object]],
    refs: dict[str, list[dict[str, object]]],
) -> None:
    for item in inventory_items:
        item_refs = refs[str(item["search_name"])]
        label, reason = _classify_refs(item_refs)
        item["reference_class"] = label
        item["reference_reason"] = reason
        item["active_refs"] = len(_active_refs(item_refs))
        item["archived_refs"] = len(_archived_refs(item_refs))
        item["report_refs"] = len(_report_refs(item_refs))
        item["non_definition_refs"] = sum(
            1
            for ref in item_refs
            if not ref["is_definition"]
            and ref["bucket"] not in {"self_tool", "self_report", "read_error"}
        )


def _write_report() -> dict[str, object]:
    source = _read_text(TARGET)
    lines_in_file = source.splitlines()
    tree = _safe_parse(TARGET)
    scheduler = _scheduler_class(tree)

    top_helpers = _top_level_functions(tree)
    classes = _top_level_classes(tree)
    methods = _class_methods(scheduler)
    private_methods = [method for method in methods if method.name.startswith("_")]
    assignments = _scheduler_method_assignments(tree)
    run_one_step_rows = _run_one_step_definitions(top_helpers, methods, assignments)

    inventory_items: list[dict[str, object]] = []
    for helper in top_helpers:
        inventory_items.append(
            {
                "name": helper.name,
                "search_name": helper.name,
                "kind": "top_level_helper",
                "line": helper.lineno,
                "category": "top_level_helper",
                "family": _zero_family(helper.name),
                "calls": _calls_in(helper),
                "wrapper_only": _returns_single_forwarding_call(helper),
            }
        )
    for method in private_methods:
        calls = _calls_in(method)
        inventory_items.append(
            {
                "name": method.name,
                "search_name": method.name,
                "kind": "private_method",
                "line": method.lineno,
                "category": _category_for_method(method.name, calls),
                "family": _zero_family(method.name),
                "calls": calls,
                "wrapper_only": _returns_single_forwarding_call(method),
            }
        )
    for assignment in assignments:
        target = str(assignment["target"])
        value_name = str(assignment["value_name"])
        inventory_items.append(
            {
                "name": target,
                "search_name": target,
                "kind": "assignment/wrapper",
                "line": assignment["line"],
                "category": "scheduler_method_assignment",
                "family": _zero_family(" ".join([target, value_name, str(assignment["value"])])),
                "assigned_value": assignment["value"],
                "assigned_name": value_name,
                "calls": [],
                "wrapper_only": False,
            }
        )

    refs = _reference_rows([str(item["search_name"]) for item in inventory_items])
    _attach_reference_counts(inventory_items, refs)
    _attach_binding_classification(inventory_items)

    candidates = sorted(
        [item for item in inventory_items if item["removal_safe"]],
        key=_candidate_score,
        reverse=True,
    )

    safe_private_methods = sorted(
        [
            item
            for item in inventory_items
            if item["kind"] == "private_method" and item["removal_safe"]
        ],
        key=_candidate_score,
        reverse=True,
    )
    safe_top_level_helpers = sorted(
        [
            item
            for item in inventory_items
            if item["kind"] == "top_level_helper" and item["removal_safe"]
        ],
        key=_candidate_score,
        reverse=True,
    )
    unsafe_bindings = sorted(
        [
            item
            for item in inventory_items
            if item["kind"] == "assignment/wrapper" and item["monkey_patch"]
        ],
        key=lambda row: int(row["line"]),
    )
    unsafe_runtime_entrypoints = sorted(
        [item for item in inventory_items if item["runtime_binding"]],
        key=lambda row: (str(row["kind"]), int(row["line"])),
    )
    unsafe_runtime_bindings = _unsafe_runtime_bindings(unsafe_bindings)
    unsafe_monkey_patches = _unsafe_monkey_patches(unsafe_bindings)
    runtime_binding_families = _runtime_binding_families(unsafe_bindings)
    runtime_entrypoint_families = _runtime_entrypoint_families(unsafe_runtime_entrypoints)
    runtime_binding_consolidation_matrix = _runtime_binding_consolidation_matrix(
        runtime_binding_families,
        runtime_entrypoint_families,
    )

    grouped_candidates: dict[str, list[dict[str, object]]] = {
        "private_method": [],
        "top_level_helper": [],
        "assignment/wrapper": [],
    }
    for item in candidates:
        grouped_candidates[str(item["kind"])].append(item)

    family_groups: dict[str, list[dict[str, object]]] = {
        family: [] for family in ZERO_FAMILY_ORDER
    }
    for item in inventory_items:
        family = str(item["family"])
        if family != "other":
            family_groups.setdefault(family, []).append(item)

    private_categories: dict[str, list[dict[str, object]]] = {}
    for item in inventory_items:
        if item["kind"] == "private_method":
            private_categories.setdefault(str(item["category"]), []).append(item)

    report_lines: list[str] = []
    report_lines.append("Scheduler Mainline Closure Inventory")
    report_lines.append("")
    report_lines.append(f"repo_root: {ROOT}")
    report_lines.append(f"target: {TARGET.relative_to(ROOT)}")
    report_lines.append(f"total_lines: {len(lines_in_file)}")
    report_lines.append(f"import_count: {_top_level_import_count(tree)}")
    report_lines.append(f"class_count: {len(classes)}")
    report_lines.append(f"method_count_inside_Scheduler: {len(methods)}")
    report_lines.append(f"top_level_helper_function_count: {len(top_helpers)}")
    report_lines.append(f"scheduler_method_assignment_count: {len(assignments)}")
    report_lines.append("")

    report_lines.append("Safe removal")
    report_lines.append("-------------")
    report_lines.append("Rule: active_refs == 0 AND not monkey_patch AND not runtime_binding")
    report_lines.append("")
    report_lines.append("safe_private_methods:")
    _append_symbol_rows(report_lines, safe_private_methods)
    report_lines.append("")
    report_lines.append("safe_top_level_helpers:")
    _append_symbol_rows(report_lines, safe_top_level_helpers)
    report_lines.append("")

    report_lines.append(f"unsafe_bindings: {len(unsafe_bindings)}")
    report_lines.append("Split below into runtime_binding and monkey_patch.")
    report_lines.append("")

    report_lines.append("Unsafe runtime binding")
    report_lines.append("----------------------")
    report_lines.append("Scheduler assignments that expose runtime/dispatch/compatibility surfaces.")
    _append_symbol_rows(report_lines, unsafe_runtime_bindings)
    report_lines.append("")

    report_lines.append("Unsafe monkey patch")
    report_lines.append("-------------------")
    report_lines.append("Scheduler class or constant replacement assignments.")
    _append_symbol_rows(report_lines, unsafe_monkey_patches)
    report_lines.append("")

    _append_runtime_binding_families(report_lines, runtime_binding_families)
    _append_runtime_binding_consolidation_matrix(
        report_lines,
        runtime_binding_consolidation_matrix,
    )

    report_lines.append("Unsafe runtime entrypoints")
    report_lines.append("--------------------------")
    report_lines.append(f"unsafe_runtime_entrypoints: {len(unsafe_runtime_entrypoints)}")
    report_lines.append("Dynamic runtime entrypoints, dispatch surfaces, and compatibility surfaces.")
    _append_symbol_rows(report_lines, unsafe_runtime_entrypoints)
    report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("run_one_step Definitions And Bindings")
    report_lines.append("=" * 80)
    for row in run_one_step_rows:
        report_lines.append(
            f"- line {row['line']}: {row['name']} "
            f"({row['kind']}) -- {row['detail']}"
        )
    if not run_one_step_rows:
        report_lines.append("- <none>")
    report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Scheduler Method Assignments")
    report_lines.append("=" * 80)
    for assignment in assignments:
        report_lines.append(
            f"- line {assignment['line']}: {assignment['target']} = {assignment['value']}"
        )
    if not assignments:
        report_lines.append("- <none>")
    report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Zero / V / Stage / Legacy Helper Families")
    report_lines.append("=" * 80)
    for family in ZERO_FAMILY_ORDER:
        rows = sorted(family_groups.get(family, []), key=lambda item: int(item["line"]))
        if family == "other":
            continue
        report_lines.append(f"{family}: {len(rows)}")
        if rows:
            for item in rows:
                report_lines.append(
                    f"- line {item['line']}: {item['name']} "
                    f"({item['kind']}; active_refs={item['active_refs']}; "
                    f"archived_refs={item['archived_refs']}; "
                    f"report_refs={item['report_refs']}; class={item['reference_class']})"
                )
        else:
            report_lines.append("- <none>")
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Private Methods By Category")
    report_lines.append("=" * 80)
    for category in sorted(private_categories):
        rows = sorted(private_categories[category], key=lambda item: int(item["line"]))
        report_lines.append(f"{category}: {len(rows)}")
        for item in rows:
            report_lines.append(
                f"- line {item['line']}: {item['name']} "
                f"[active_refs={item['active_refs']}; archived_refs={item['archived_refs']}; "
                f"report_refs={item['report_refs']}; class={item['reference_class']}]"
            )
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Top-Level Helper Functions")
    report_lines.append("=" * 80)
    for helper in top_helpers:
        report_lines.append(f"- line {helper.lineno}: {helper.name}")
    if not top_helpers:
        report_lines.append("- <none>")
    report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Likely Removal Candidates -- Top 20 By Group")
    report_lines.append("=" * 80)
    report_lines.append(
        "Only symbols with active_refs=0 and no unsafe binding flags are listed."
    )
    report_lines.append("A = active_refs=0 and no archived/report references")
    report_lines.append("B = active_refs=0 with archived_refs or report_refs only")
    report_lines.append("C = active_refs > 0; excluded from this section")
    report_lines.append("")
    for group in ("private_method", "top_level_helper", "assignment/wrapper"):
        rows = grouped_candidates[group][:20]
        report_lines.append(f"{group}: {len(grouped_candidates[group])} candidates")
        if rows:
            for item in rows:
                name = str(item["name"])
                search_name = str(item["search_name"])
                report_lines.append(
                    f"- {name} (line {item['line']}, category={item['category']}, "
                    f"family={item['family']}, class={item['reference_class']})"
                )
                if item["kind"] == "assignment/wrapper":
                    report_lines.append(f"  assigned_value: {item['assigned_value']}")
                report_lines.append(f"  reason: {item['reference_reason']}")
                report_lines.append(f"  active_refs: {item['active_refs']}")
                report_lines.append(f"  archived_refs: {item['archived_refs']}")
                report_lines.append(f"  report_refs: {item['report_refs']}")
                report_lines.append(f"  non_definition_refs: {item['non_definition_refs']}")
                report_lines.append("  active_references:")
                report_lines.extend(_format_ref_summary(refs[search_name], active_only=True))
                report_lines.append("  archived_references:")
                report_lines.extend(_format_ref_summary(refs[search_name], archived_only=True))
                report_lines.append("  report_references:")
                report_lines.extend(_format_ref_summary(refs[search_name], report_only=True))
        else:
            report_lines.append("- <none>")
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Referenced / Not Removal Candidates")
    report_lines.append("=" * 80)
    for item in sorted(
        [row for row in inventory_items if row["reference_class"] == "C"],
        key=lambda row: (str(row["kind"]), int(row["line"])),
    ):
        name = str(item["name"])
        search_name = str(item["search_name"])
        report_lines.append(
            f"- {name} ({item['kind']}, line {item['line']}, category={item['category']}, "
            f"family={item['family']})"
        )
        if item["kind"] == "assignment/wrapper":
            report_lines.append(f"  assigned_value: {item['assigned_value']}")
        report_lines.append(f"  reason: {item['reference_reason']}")
        report_lines.append(f"  active_refs: {item['active_refs']}")
        report_lines.append(f"  archived_refs: {item['archived_refs']}")
        report_lines.append(f"  report_refs: {item['report_refs']}")
        report_lines.append(f"  non_definition_refs: {item['non_definition_refs']}")
        report_lines.append("  sample_active_references:")
        report_lines.extend(_format_ref_summary(refs[search_name], limit=5, active_only=True))
        report_lines.append("  sample_archived_references:")
        report_lines.extend(_format_ref_summary(refs[search_name], limit=5, archived_only=True))
        report_lines.append("  sample_report_references:")
        report_lines.extend(_format_ref_summary(refs[search_name], limit=5, report_only=True))
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Non-Mainline Issues")
    report_lines.append("=" * 80)
    report_lines.append("- Inventory only. No production code was changed.")
    report_lines.append("- Candidates are reference-based only; removal needs a follow-up package.")
    report_lines.append(
        "- Text search can count dynamic/string references and miss computed getattr usage."
    )
    report_lines.append(
        "- Scheduler method assignment candidates are conservative; instance dispatch can hide textual references."
    )
    report_lines.append("")

    REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    return {
        "items": inventory_items,
        "candidates": candidates,
        "grouped_candidates": grouped_candidates,
        "safe_private_methods": safe_private_methods,
        "safe_top_level_helpers": safe_top_level_helpers,
        "unsafe_bindings": unsafe_bindings,
        "unsafe_runtime_entrypoints": unsafe_runtime_entrypoints,
        "unsafe_runtime_bindings": unsafe_runtime_bindings,
        "unsafe_monkey_patches": unsafe_monkey_patches,
        "runtime_binding_families": runtime_binding_families,
        "runtime_entrypoint_families": runtime_entrypoint_families,
        "runtime_binding_consolidation_matrix": runtime_binding_consolidation_matrix,
        "report": REPORT,
        "counts": {
            "total_lines": len(lines_in_file),
            "import_count": _top_level_import_count(tree),
            "class_count": len(classes),
            "method_count_inside_Scheduler": len(methods),
            "top_level_helper_function_count": len(top_helpers),
            "scheduler_method_assignment_count": len(assignments),
        },
    }


def main() -> int:
    result = _write_report()
    grouped = result["grouped_candidates"]
    print("Scheduler mainline inventory complete")
    print(f"report: {Path(result['report']).relative_to(ROOT)}")
    counts = result["counts"]
    print(
        "counts: "
        f"total_lines={counts['total_lines']}, "
        f"imports={counts['import_count']}, "
        f"classes={counts['class_count']}, "
        f"Scheduler_methods={counts['method_count_inside_Scheduler']}, "
        f"top_level_helpers={counts['top_level_helper_function_count']}, "
        f"Scheduler_assignments={counts['scheduler_method_assignment_count']}"
    )
    print("top_20_likely_removal_candidates_by_group:")
    for group in ("private_method", "top_level_helper", "assignment/wrapper"):
        rows = grouped[group][:20]
        print(f"{group}:")
        if not rows:
            print("- <none>")
            continue
        for item in rows:
            print(
                f"- {item['name']} "
                f"(line {item['line']}, class {item['reference_class']}, "
                f"active_refs {item['active_refs']}, "
                f"archived_refs {item['archived_refs']}, "
                f"report_refs {item['report_refs']})"
            )
    print("classification_summary:")
    print(f"safe_private_methods={len(result['safe_private_methods'])}")
    print(f"safe_top_level_helpers={len(result['safe_top_level_helpers'])}")
    print(f"unsafe_bindings={len(result['unsafe_bindings'])}")
    print(f"unsafe_runtime_entrypoints={len(result['unsafe_runtime_entrypoints'])}")
    print("runtime_binding_families:")
    for family in RUNTIME_BINDING_FAMILY_ORDER:
        rows = result["runtime_binding_families"].get(family, [])
        any_active_refs_zero = any(int(row["active_refs"]) == 0 for row in rows)
        print(
            f"- {family}: count={len(rows)}, "
            f"any_active_refs_0={any_active_refs_zero}, safe_to_remove=False"
        )
    print("runtime_binding_consolidation_matrix:")
    for row in result["runtime_binding_consolidation_matrix"]:
        print(
            f"- {row['family']}: bindings={row['binding_count']}, "
            f"runtime_entrypoints={row['runtime_entrypoint_count']}, "
            f"active_refs={row['active_refs_summary']}, "
            f"status={row['consolidation_status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
