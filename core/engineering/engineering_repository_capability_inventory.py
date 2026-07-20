from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.engineering.repository_analysis_common import AdmittedRepositoryRoot, artifact, relative_path_valid
from core.engineering.repository_root_admission import admit_repository_root

SCHEMA = "zero.engineering.repository_capability_inventory.v1"
ID_KEY = "repository_capability_inventory_id"
PREFIX = "engineering-capability-inventory-"
MAX_FILES = 2000
MAX_SOURCE_BYTES = 512 * 1024
MAX_RECORDS = 256
MAX_EVIDENCE = 512
ADMITTED_PREFIXES = ("core/engineering/", "cli/", "schemas/", "tests/")
REQUIRED_CAPABILITIES = (
    "change_generation", "dependency_analysis", "evidence_collection", "formatter",
    "linter", "model_backed_engineering_assistance", "patch_preparation", "repository_topology",
    "rollback", "source_reading", "static_analysis", "test_execution", "type_checker",
    "verification", "workspace_mutation",
)


def _strings(node: ast.AST) -> list[str]:
    values: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            values.append(child.value)
    return values


def _names(node: ast.AST) -> set[str]:
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)} | {
        child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)
    } | {alias.asname or alias.name.rsplit(".", 1)[-1] for child in ast.walk(node)
         if isinstance(child, (ast.Import, ast.ImportFrom)) for alias in child.names}


def _assigned(tree: ast.AST) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            for target in targets:
                if isinstance(target, ast.Name) and value is not None:
                    try:
                        result[target.id] = ast.literal_eval(value)
                    except (ValueError, TypeError):
                        pass
    return result


def _imports(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            result.update((base + "." + alias.name).strip(".") for alias in node.names)
    return result


def _capabilities(names: set[str], strings: set[str], assigned: Mapping[str, Any]) -> list[str]:
    assigned_tokens = {str(item) for value in assigned.values() for item in (value if isinstance(value, (list, tuple, set)) else (value,))}
    haystack = names | assigned_tokens
    rules = {
        "source_reading": {"read_text", "read_bytes"},
        "repository_topology": {"build_repository_topology", "repository_topology"},
        "dependency_analysis": {"build_repository_dependency_analysis", "python_import_edges"},
        "static_analysis": {"ast", "parse"},
        "test_execution": {"pytest", "test_execution"},
        "formatter": {"formatter", "format_code"},
        "linter": {"linter", "lint"},
        "type_checker": {"type_checker", "mypy", "pyright"},
        "change_generation": {"proposed_change_set", "change_generation"},
        "patch_preparation": {"patch", "diff_proposal", "stage_mutations"},
        "workspace_mutation": {"atomic_commit", "execute_pipeline"},
        "verification": {"verify_engineering_runtime", "verify_post_commit", "verification"},
        "rollback": {"rollback_transaction", "rollback"},
        "evidence_collection": {"build_engineering_runtime_evidence", "build_execution_evidence", "evidence"},
        "model_backed_engineering_assistance": {"model_backed_engineering_assistance", "model_adapter"},
    }
    return sorted(capability for capability, signals in rules.items() if haystack & signals)


def _record(path: str, tree: ast.AST, digest: str) -> dict[str, Any] | None:
    assigned = _assigned(tree); names = _names(tree); strings = set(_strings(tree)); imports = _imports(tree)
    classes = sorted(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    functions = sorted(node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    operations = assigned.get("OPERATIONS", assigned.get("supported_operations", ()))
    if not isinstance(operations, (list, tuple)): operations = ()
    adapter_id = assigned.get("ADAPTER_ID") or assigned.get("adapter_id")
    is_reference = path.endswith("engineering_runtime_reference_adapters.py") or (
        "build_reference_adapter_descriptor" in names and any(name.endswith("Adapter") for name in classes)
    )
    is_workspace = "ReadOnlyWorkspaceAdapter" in classes
    is_mutation = bool({"atomic_commit", "execute_pipeline", "stage_mutations"} & names)
    is_boundary = path.endswith(("engineering_runtime_execution_coordination.py", "engineering_runtime_orchestrator.py", "_registry.py", "_protocol.py", "_controlled_executor.py"))
    declarative_adapter = bool(adapter_id and operations and any(name.endswith("Adapter") for name in classes))
    if not (declarative_adapter or is_reference or is_workspace or is_mutation or is_boundary): return None
    if not adapter_id:
        adapter_id = "module:" + path[:-3].replace("/", ".")
    capabilities = _capabilities(names, strings, assigned)
    read_only = True if is_reference or is_workspace else False if is_mutation else None
    mutation_capable = True if is_mutation else False if read_only is True else None
    requires_approval = True if is_mutation and ("operator_approval" in strings or "operator_approval" in names) else False if read_only else None
    requires_authorization = True if is_mutation and ("mutation_authorization" in strings or "mutation_authorization" in names or "authorize_commit" in names) else False if read_only else None
    activation = bool({"activation_token", "activation_eligibility", "activation_authorization"} & (names | strings))
    status = "confirmed" if capabilities and (read_only is not None or is_boundary) else "partially_confirmed"
    kind = "reference_adapter" if is_reference else "workspace_adapter" if is_workspace else "mutation_executor" if is_mutation else "execution_boundary"
    return {
        "adapter_id": str(adapter_id), "adapter_kind": kind, "owner_domain": "engineering",
        "production_module": path, "protocol_or_contract": sorted(x for x in imports if "protocol" in x or "common" in x)[:12],
        "capability_ids": capabilities, "operation_types": sorted(str(x) for x in operations)[:32],
        "read_only": read_only, "mutation_capable": mutation_capable,
        "requires_operator_approval": requires_approval,
        "requires_mutation_authorization": requires_authorization,
        "requires_activation": activation, "requires_activation_token": activation,
        "workspace_scope_type": "repository_relative" if is_workspace or is_mutation else "not_evidenced",
        "execution_boundary": is_boundary or is_mutation,
        "mainline_integration_status": "pending_analysis", "mainline_integration_evidence": [],
        "schema_ids": sorted(s for s in strings if s.startswith("zero.engineering."))[:16],
        "cli_entry_points": [], "test_coverage_files": [], "status": status,
        "findings": [], "source_sha256": digest, "class_symbols": classes[:16], "function_symbols": functions[:32],
    }


def _discover(admitted: AdmittedRepositoryRoot) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    if admitted.root is None: return [], [], ["repository_root_not_admitted"]
    root = admitted.root; parsed: dict[str, tuple[ast.AST, str]] = {}; warnings: set[str] = set()
    candidates: list[Path] = []
    for prefix in ADMITTED_PREFIXES:
        base = root / prefix.rstrip("/")
        if base.is_dir(): candidates.extend(base.rglob("*.py")); candidates.extend(base.rglob("*.json"))
    for path in sorted(set(candidates), key=lambda p: p.as_posix())[:MAX_FILES]:
        try:
            if path.is_symlink() or path.resolve().relative_to(root) is None: continue
            rel = path.relative_to(root).as_posix()
            if not relative_path_valid(rel) or path.stat().st_size > MAX_SOURCE_BYTES: warnings.add("source_skipped"); continue
            data = path.read_bytes(); digest = hashlib.sha256(data).hexdigest()
            if path.suffix == ".py": parsed[rel] = (ast.parse(data.decode("utf-8-sig"), filename=rel), digest)
        except (OSError, UnicodeError, SyntaxError, ValueError): warnings.add("source_skipped")
    repository_capabilities = sorted({cap for rel, (tree, _) in parsed.items() if rel.startswith("core/engineering/") and not rel.endswith("engineering_repository_capability_inventory.py")
                                      for cap in _capabilities(_names(tree), set(_strings(tree)), _assigned(tree))})
    records = [record for rel, (tree, digest) in parsed.items() if (record := _record(rel, tree, digest))]
    production = [r for r in records if r["production_module"].startswith("core/engineering/")]
    all_imports = {rel: _imports(tree) for rel, (tree, _) in parsed.items()}
    for record in production:
        stem = Path(record["production_module"]).stem
        routes = sorted(rel for rel, imports in all_imports.items() if any(item.endswith(stem) or item.endswith("." + stem) or ("." + stem + ".") in item for item in imports))
        mainline = [p for p in routes if p.endswith("engineering_runtime_orchestrator.py") or p.endswith("engineering_runtime_execution_coordination.py")]
        indirect = [p for p in routes if p.startswith("core/engineering/")]
        if mainline: integration = "directly_integrated"; evidence = mainline
        elif indirect: integration = "indirectly_integrated"; evidence = indirect[:12]
        elif record["adapter_kind"] == "reference_adapter": integration = "reference_only"; evidence = []
        else: integration = "available_but_not_integrated"; evidence = []
        record["mainline_integration_status"] = integration
        record["mainline_integration_evidence"] = evidence
        record["cli_entry_points"] = [p for p in routes if p.startswith("cli/")][:12]
        record["test_coverage_files"] = [p for p in routes if p.startswith("tests/")][:24]
    return sorted(production, key=lambda r: (r["adapter_id"], r["production_module"]))[:MAX_RECORDS], repository_capabilities, sorted(warnings)


def build_repository_capability_inventory(repository_root: Any) -> dict[str, Any]:
    admitted = admit_repository_root(repository_root); records, discovered, warnings = _discover(admitted)
    gaps = [{"capability_id": cap, "status": "missing", "finding": "no_implementation_supported_evidence"}
            for cap in REQUIRED_CAPABILITIES if cap not in discovered]
    duplicates = []
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            overlap = sorted(set(left["capability_ids"]) & set(right["capability_ids"]))
            if overlap and left["adapter_kind"] == right["adapter_kind"] and left["adapter_kind"] in {"reference_adapter", "workspace_adapter", "mutation_executor"}:
                duplicates.append({"status": "duplicate_candidate", "modules": sorted([left["production_module"], right["production_module"]]), "overlapping_capability_ids": overlap})
    evidence = [{"evidence_id": "capability-evidence-" + hashlib.sha256((r["production_module"] + r["source_sha256"]).encode()).hexdigest()[:24],
                 "source_relative_path": r["production_module"], "source_sha256": r["source_sha256"],
                 "observation": {"adapter_kind": r["adapter_kind"], "capability_ids": r["capability_ids"], "status": r["status"]}}
                for r in records][:MAX_EVIDENCE]
    confirmed = [r["adapter_id"] for r in records if r["status"] == "confirmed"]
    ambiguous = [r["adapter_id"] for r in records if r["status"] == "partially_confirmed"]
    unintegrated_mutation = next((r for r in records if r["adapter_kind"] == "mutation_executor" and r["mainline_integration_status"] == "available_but_not_integrated"), None)
    recommendation = ({"package_id": "engineering-governed-workspace-mutation-mainline-integration", "basis": unintegrated_mutation["production_module"]}
                      if unintegrated_mutation else {"package_id": "engineering-capability-" + gaps[0]["capability_id"].replace("_", "-"), "basis": gaps[0]["capability_id"]}
                      if gaps else {"package_id": "engineering-adapter-integration-closure", "basis": "available_but_not_integrated"})
    payload = {
        "root_admission": admitted.artifact, "records": records,
        "integration_map": [{"adapter_id": r["adapter_id"], "production_module": r["production_module"], "status": r["mainline_integration_status"], "evidence": r["mainline_integration_evidence"]} for r in records],
        "gap_findings": gaps, "duplicate_candidate_findings": duplicates,
        "coverage_summary": {"adapter_count": len(records), "capability_ids": discovered, "required_capability_count": len(REQUIRED_CAPABILITIES), "missing_capability_count": len(gaps)},
        "evidence": evidence, "report": {"confirmed_facts": confirmed, "inferences": ["duplicate candidates are structural overlap findings only"], "ambiguous_findings": ambiguous, "recommended_next_development_package": recommendation},
        "closure": {"status": "closed" if admitted.artifact.get("status") == "admitted" else "rejected", "read_only": True, "repository_modified": False},
        "warnings": warnings,
    }
    return artifact(SCHEMA, "inventoried" if admitted.artifact.get("status") == "admitted" else "rejected", payload, ID_KEY, PREFIX)


def inspect_repository_capability_inventory(value: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema": value.get("schema"), "status": value.get("status"), "repository_capability_inventory_id": value.get(ID_KEY), "fingerprint": value.get("fingerprint"), "record_count": len(value.get("records", [])), "gap_count": len(value.get("gap_findings", []))}


__all__ = ["build_repository_capability_inventory", "inspect_repository_capability_inventory"]
