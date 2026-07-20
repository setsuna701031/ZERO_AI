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


def _import_bindings(tree: ast.AST) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                result[alias.asname or alias.name] = ((node.module or "") + "." + alias.name).strip(".")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.rsplit(".", 1)[-1]] = alias.name
    return result


def _calls(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name): result.add(node.func.id)
            elif isinstance(node.func, ast.Attribute): result.add(node.func.attr)
    return result


def _evidence(category: str, source: str, symbol: str) -> dict[str, str]:
    material = f"{category}\0{source}\0{symbol}"
    return {"category": category, "source_relative_path": source, "symbol": symbol,
            "evidence_fingerprint": hashlib.sha256(material.encode("utf-8")).hexdigest()}


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
    kind = "reference_adapter" if is_reference else "workspace_adapter" if is_workspace else "execution_boundary" if is_boundary else "mutation_executor"
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
        "integration_confidence": "ambiguous", "ownership_role": "unresolved",
        "delegates_to": [], "delegated_by": [], "evidence_categories": [],
        "classification_reason": "routing_not_analyzed", "classification_limitations": [],
        "integration_evidence": [],
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
    bindings = {rel: _import_bindings(tree) for rel, (tree, _) in parsed.items()}
    calls = {rel: _calls(tree) for rel, (tree, _) in parsed.items()}
    strings = {rel: set(_strings(tree)) for rel, (tree, _) in parsed.items()}
    record_by_module = {r["production_module"]: r for r in production}

    def target_module(binding: str) -> str | None:
        parts = binding.split(".")
        if "engineering" in parts:
            index = parts.index("engineering")
            if index + 1 >= len(parts): return None
            return "core/engineering/" + parts[index + 1] + ".py"
        if parts and parts[0].startswith("engineering_"):
            return "core/engineering/" + parts[0] + ".py"
        return None

    edges: dict[str, set[str]] = {module: set() for module in record_by_module}
    route_evidence: dict[str, list[dict[str, str]]] = {module: [] for module in record_by_module}
    for source, imported in bindings.items():
        source_production = source.startswith("core/engineering/")
        for local, binding in imported.items():
            target = target_module(binding)
            if target not in record_by_module: continue
            route_evidence[target].append(_evidence("import_evidence", source, local))
            if local in calls[source]:
                category = "test_route_evidence" if source.startswith("tests/") else "call_evidence"
                route_evidence[target].append(_evidence(category, source, local))
                if source_production and source in record_by_module: edges[source].add(target)
                if source_production and ("execution_class" in strings[source] or {"read_only", "mutation"} & strings[source]):
                    route_evidence[target].append(_evidence("dispatch_evidence", source, local))
                if source_production and "handoff" in " ".join(_names(parsed[source][0])):
                    route_evidence[target].append(_evidence("handoff_evidence", source, local))
                if source_production and ("registry" in local or "registry" in binding):
                    route_evidence[target].append(_evidence("registry_evidence", source, local))
        if source in record_by_module and any("protocol" in item for item in all_imports[source]):
            route_evidence[source].append(_evidence("protocol_evidence", source, "protocol_contract"))

    roots = {p for p in record_by_module if p.endswith("engineering_runtime_orchestrator.py")}
    reachable = set(roots)
    changed = True
    while changed:
        changed = False
        for source in sorted(reachable):
            for target in sorted(edges.get(source, ())):
                if target not in reachable: reachable.add(target); changed = True

    for source, targets in edges.items():
        record_by_module[source]["delegates_to"] = sorted(targets)
        for target in targets:
            record_by_module[target]["delegated_by"].append(source)
            route_evidence[target].append(_evidence("delegation_evidence", source, Path(target).stem))
    for module in record_by_module:
        route_evidence[module].append(_evidence("ownership_evidence", module, "module_responsibility"))
    for record in production:
        stem = Path(record["production_module"]).stem
        routes = sorted(rel for rel, imports in all_imports.items() if any(item.endswith(stem) or item.endswith("." + stem) or ("." + stem + ".") in item for item in imports))
        module = record["production_module"]
        items = sorted(route_evidence[module], key=lambda item: (item["category"], item["source_relative_path"], item["symbol"]))[:32]
        categories = sorted({item["category"] for item in items})
        production_calls = [item for item in items if item["category"] == "call_evidence"]
        direct_owner_call = any(item["source_relative_path"].endswith(("engineering_runtime_orchestrator.py", "engineering_runtime_execution_coordination.py")) for item in production_calls)
        if module.endswith("engineering_runtime_orchestrator.py"): role = "execution_boundary_owner"
        elif module.endswith("engineering_runtime_execution_coordination.py"): role = "execution_coordinator"
        elif module.endswith("engineering_runtime_workspace_controlled_executor.py"): role = "delegated_workspace_executor"
        elif module.endswith("engineering_governed_workspace_mutation_executor.py"): role = "delegated_mutation_executor"
        elif record["adapter_kind"] == "mutation_executor": role = "low_level_mutation_implementation"
        elif record["adapter_kind"] == "workspace_adapter": role = "workspace_adapter_implementation"
        elif "registry" in module: role = "adapter_registry"
        elif "protocol" in module: role = "adapter_protocol"
        elif record["adapter_kind"] == "reference_adapter": role = "reference_adapter"
        else: role = "execution_boundary"
        if role in {"execution_boundary_owner", "execution_coordinator"}: integration = "directly_integrated"; confidence = "confirmed"; reason = "mainline_execution_ownership"
        elif record["adapter_kind"] == "reference_adapter": integration = "reference_only"; confidence = "confirmed"; reason = "explicit_reference_implementation_without_mainline_binding"
        elif direct_owner_call: integration = "directly_integrated"; confidence = "confirmed"; reason = "production_owner_calls_implementation"
        elif module in reachable and production_calls: integration = "indirectly_integrated"; confidence = "strong"; reason = "reachable_production_delegation_route"
        elif production_calls: integration = "indirectly_integrated"; confidence = "partial"; reason = "production_call_exists_but_mainline_reachability_is_partial"
        else: integration = "available_but_not_integrated"; confidence = "strong" if "test_route_evidence" in categories else "partial"; reason = "no_production_call_dispatch_registry_handoff_or_delegation_route"
        evidence = sorted({item["source_relative_path"] for item in items if item["category"] != "import_evidence"})[:12]
        record["mainline_integration_status"] = integration
        record["mainline_integration_evidence"] = evidence
        record["integration_confidence"] = confidence
        record["ownership_role"] = role
        record["delegated_by"] = sorted(set(record["delegated_by"]))
        record["evidence_categories"] = categories
        record["classification_reason"] = reason
        route_categories = set(categories) - {"ownership_evidence"}
        record["classification_limitations"] = (["import_only_relationship_not_integration"] if route_categories == {"import_evidence"} else [])
        record["integration_evidence"] = items
        record["cli_entry_points"] = [p for p in routes if p.startswith("cli/")][:12]
        record["test_coverage_files"] = sorted({item["source_relative_path"] for item in items if item["category"] == "test_route_evidence"})[:24]
    return sorted(production, key=lambda r: (r["adapter_id"], r["production_module"]))[:MAX_RECORDS], repository_capabilities, sorted(warnings)


def build_repository_capability_inventory(repository_root: Any) -> dict[str, Any]:
    admitted = admit_repository_root(repository_root); records, discovered, warnings = _discover(admitted)
    gaps = [{"capability_id": cap, "status": "missing", "finding": "no_implementation_supported_evidence"}
            for cap in REQUIRED_CAPABILITIES if cap not in discovered]
    duplicates = []
    delegation_graph = {r["production_module"]: set(r["delegates_to"]) for r in records}
    def delegated_path(source: str, target: str) -> bool:
        pending = list(delegation_graph.get(source, ())); seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target: return True
            if current not in seen: seen.add(current); pending.extend(delegation_graph.get(current, ()))
        return False
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            overlap = sorted(set(left["capability_ids"]) & set(right["capability_ids"]))
            if not overlap: continue
            left_module, right_module = left["production_module"], right["production_module"]
            delegated = delegated_path(left_module, right_module) or delegated_path(right_module, left_module)
            categories = sorted((set(left["evidence_categories"]) | set(right["evidence_categories"])) - {"import_evidence", "ownership_evidence"})
            reachable_pair = all(item["mainline_integration_status"] in {"directly_integrated", "indirectly_integrated"} for item in (left, right))
            if delegated:
                finding_status = "layered_responsibility"
            elif left["ownership_role"] == right["ownership_role"] and reachable_pair and len(categories) >= 2:
                finding_status = "duplicate_candidate"
            else:
                finding_status = "ambiguous_overlap"
            duplicates.append({"status": finding_status, "modules": sorted([left_module, right_module]),
                               "overlapping_capability_ids": overlap, "evidence_categories": categories[:9]})
    evidence = [{"evidence_id": "capability-evidence-" + hashlib.sha256((r["production_module"] + r["source_sha256"]).encode()).hexdigest()[:24],
                 "source_relative_path": r["production_module"], "source_sha256": r["source_sha256"],
                 "observation": {"adapter_kind": r["adapter_kind"], "capability_ids": r["capability_ids"], "status": r["status"],
                                 "integration_status": r["mainline_integration_status"], "ownership_role": r["ownership_role"],
                                 "evidence_categories": r["evidence_categories"]}}
                for r in records][:MAX_EVIDENCE]
    confirmed = [r["adapter_id"] for r in records if r["status"] == "confirmed"]
    ambiguous = [r["adapter_id"] for r in records if r["status"] == "partially_confirmed"]
    unintegrated_mutation = next((r for r in records if r["adapter_kind"] == "mutation_executor" and r["mainline_integration_status"] == "available_but_not_integrated"), None)
    recommendation = ({"package_id": "engineering-governed-workspace-mutation-mainline-integration", "basis": unintegrated_mutation["production_module"]}
                      if unintegrated_mutation else {"package_id": "engineering-capability-inventory-ambiguity-resolution", "basis": "remaining_ambiguous_ownership"}
                      if ambiguous else {"package_id": "engineering-capability-" + gaps[0]["capability_id"].replace("_", "-"), "basis": gaps[0]["capability_id"]}
                      if gaps else {"package_id": "engineering-adapter-integration-closure", "basis": "available_but_not_integrated"})
    payload = {
        "root_admission": admitted.artifact, "records": records,
        "integration_map": [{"adapter_id": r["adapter_id"], "production_module": r["production_module"], "status": r["mainline_integration_status"], "evidence": r["mainline_integration_evidence"],
                             "integration_confidence": r["integration_confidence"], "ownership_role": r["ownership_role"],
                             "delegates_to": r["delegates_to"], "delegated_by": r["delegated_by"], "evidence_categories": r["evidence_categories"],
                             "classification_reason": r["classification_reason"], "classification_limitations": r["classification_limitations"]} for r in records],
        "gap_findings": gaps, "duplicate_candidate_findings": duplicates,
        "coverage_summary": {"adapter_count": len(records), "capability_ids": discovered, "required_capability_count": len(REQUIRED_CAPABILITIES), "missing_capability_count": len(gaps)},
        "evidence": evidence, "report": {"confirmed_facts": confirmed, "inferences": ["overlap findings require routing and ownership evidence"], "ambiguous_findings": ambiguous,
                                          "confirmed_repository_facts": [r["production_module"] for r in records if r["integration_confidence"] == "confirmed"],
                                          "supported_inferences": [f for f in duplicates if f["status"] in {"layered_responsibility", "parallel_architecture_candidate"}],
                                          "unresolved_ambiguity": [f for f in duplicates if f["status"] == "ambiguous_overlap"],
                                          "recommended_next_development_package": recommendation},
        "closure": {"status": "closed" if admitted.artifact.get("status") == "admitted" else "rejected", "read_only": True, "repository_modified": False},
        "warnings": warnings,
    }
    return artifact(SCHEMA, "inventoried" if admitted.artifact.get("status") == "admitted" else "rejected", payload, ID_KEY, PREFIX)


def inspect_repository_capability_inventory(value: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema": value.get("schema"), "status": value.get("status"), "repository_capability_inventory_id": value.get(ID_KEY), "fingerprint": value.get("fingerprint"), "record_count": len(value.get("records", [])), "gap_count": len(value.get("gap_findings", []))}


__all__ = ["build_repository_capability_inventory", "inspect_repository_capability_inventory"]
