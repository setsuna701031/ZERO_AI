from __future__ import annotations

import hashlib
import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    ".cache",
    "cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".html",
    ".rs",
    ".go",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".sh",
    ".ps1",
}

DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
CONFIG_EXTENSIONS = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}
CONFIG_FILENAMES = {
    ".env",
    ".gitignore",
    "dockerfile",
    "makefile",
    "pytest.ini",
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
}


@dataclass(frozen=True)
class RepoFileRecord:
    path: str
    classification: str
    suffix: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "classification": self.classification,
            "suffix": self.suffix,
        }


@dataclass(frozen=True)
class RepoScanResult:
    repo_root: str
    scan_id: str
    files: tuple[RepoFileRecord, ...]
    ignored_directories: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "scan_id": self.scan_id,
            "files": [item.to_dict() for item in self.files],
            "ignored_directories": list(self.ignored_directories),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ImpactedFileRecord:
    path: str
    classification: str
    reasons: tuple[str, ...]
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "classification": self.classification,
            "reasons": list(self.reasons),
            "score": self.score,
        }


@dataclass(frozen=True)
class ImpactedFilePlan:
    plan_id: str
    task: str
    files: tuple[ImpactedFileRecord, ...]
    reasons: tuple[str, ...]
    classification: str
    source_scan_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task": self.task,
            "files": [item.to_dict() for item in self.files],
            "reasons": list(self.reasons),
            "classification": self.classification,
            "source_scan_id": self.source_scan_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ImpactedPlan:
    changed_files: tuple[str, ...]
    impacted_modules: tuple[str, ...]
    verification_targets: tuple[str, ...]
    rollback_scope: tuple[str, ...]
    impacted_runtime_surfaces: tuple[str, ...]
    mutation_risk: dict[str, Any] = field(default_factory=dict)
    verification_owners: dict[str, tuple[str, ...]] = field(default_factory=dict)
    impacted_runtime_topology: dict[str, Any] = field(default_factory=dict)
    import_graph: dict[str, tuple[str, ...]] = field(default_factory=dict)
    caller_graph: dict[str, tuple[str, ...]] = field(default_factory=dict)
    dependency_graph: dict[str, tuple[str, ...]] = field(default_factory=dict)
    source_scan_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_files": list(self.changed_files),
            "impacted_modules": list(self.impacted_modules),
            "verification_targets": list(self.verification_targets),
            "rollback_scope": list(self.rollback_scope),
            "impacted_runtime_surfaces": list(self.impacted_runtime_surfaces),
            "mutation_risk": dict(self.mutation_risk),
            "verification_owners": {
                key: list(value) for key, value in sorted(self.verification_owners.items())
            },
            "impacted_runtime_topology": dict(self.impacted_runtime_topology),
            "import_graph": {
                key: list(value) for key, value in sorted(self.import_graph.items())
            },
            "caller_graph": {
                key: list(value) for key, value in sorted(self.caller_graph.items())
            },
            "dependency_graph": {
                key: list(value) for key, value in sorted(self.dependency_graph.items())
            },
            "source_scan_id": self.source_scan_id,
            "metadata": dict(self.metadata),
        }


def scan_repo(root: str | Path) -> RepoScanResult:
    """Return a deterministic read-only file inventory for a repository root."""

    repo_root = Path(root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise ValueError(f"repo_root_not_directory:{repo_root}")

    files: list[RepoFileRecord] = []
    ignored: set[str] = set()

    for directory_text, dirnames, filenames in os.walk(repo_root):
        directory = Path(directory_text)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            if _should_ignore_dir(dirname):
                ignored.add(_relative_path(repo_root, directory / dirname))
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            path = directory / filename
            relative = _relative_path(repo_root, path)
            files.append(
                RepoFileRecord(
                    path=relative,
                    classification=classify_repo_file(relative),
                    suffix=path.suffix.lower(),
                )
            )

    payload = {
        "repo_root": str(repo_root),
        "files": [item.to_dict() for item in files],
        "ignored_directories": sorted(ignored),
    }
    return RepoScanResult(
        repo_root=str(repo_root),
        scan_id="repo-scan-" + _stable_hash(payload)[:16],
        files=tuple(files),
        ignored_directories=tuple(sorted(ignored)),
        metadata=_read_only_metadata(surface="repo_scan"),
    )


def build_impacted_file_plan(
    task: str,
    *,
    repo_root: str | Path | None = None,
    scan: RepoScanResult | None = None,
    max_files: int = 20,
) -> ImpactedFilePlan:
    """Build a conservative read-only impacted file plan from task/path tokens."""

    task_text = str(task or "").strip()
    if not task_text:
        raise ValueError("task_required")
    if scan is None:
        if repo_root is None:
            raise ValueError("repo_root_or_scan_required")
        scan = scan_repo(repo_root)

    task_tokens = _tokens(task_text)
    impacted: list[ImpactedFileRecord] = []

    for record in scan.files:
        score, reasons = _score_file_for_task(record, task_tokens)
        if score <= 0:
            continue
        impacted.append(
            ImpactedFileRecord(
                path=record.path,
                classification=record.classification,
                reasons=tuple(reasons),
                score=score,
            )
        )

    impacted.sort(key=lambda item: (-item.score, item.path))
    impacted = impacted[: max(0, int(max_files))]

    classification = _plan_classification(impacted)
    reasons = _plan_reasons(impacted, task_tokens)
    payload = {
        "task": task_text,
        "source_scan_id": scan.scan_id,
        "files": [item.to_dict() for item in impacted],
        "classification": classification,
    }
    return ImpactedFilePlan(
        plan_id="impacted-file-plan-" + _stable_hash(payload)[:16],
        task=task_text,
        files=tuple(impacted),
        reasons=tuple(reasons),
        classification=classification,
        source_scan_id=scan.scan_id,
        metadata=_read_only_metadata(surface="impacted_file_plan"),
    )


def build_impacted_plan(
    task: str,
    *,
    changed_files: Iterable[str] | None = None,
    repo_root: str | Path | None = None,
    scan: RepoScanResult | None = None,
    max_files: int = 50,
) -> ImpactedPlan:
    """Infer repo-aware impact, verification, and rollback scope.

    This is intentionally read-only. It produces the governed runtime's planning
    artifact; it does not grant mutation, execution, or patch authority.
    """

    task_text = str(task or "").strip()
    if not task_text:
        raise ValueError("task_required")
    if scan is None:
        if repo_root is None:
            raise ValueError("repo_root_or_scan_required")
        scan = scan_repo(repo_root)

    file_index = {record.path: record for record in scan.files}
    module_to_path = _python_module_index(scan.files)
    import_graph = _build_import_graph(
        repo_root=Path(scan.repo_root),
        files=scan.files,
    )
    dependency_graph = _resolve_dependency_graph(
        import_graph=import_graph,
        module_to_path=module_to_path,
    )
    caller_graph = _reverse_graph(dependency_graph)

    normalized_changed = tuple(
        path
        for path in _unique_sorted(
            _normalize_plan_path(path) for path in (changed_files or ())
        )
    )

    if normalized_changed:
        seed_files = list(normalized_changed)
    else:
        file_plan = build_impacted_file_plan(
            task_text,
            scan=scan,
            max_files=max_files,
        )
        seed_files = [item.path for item in file_plan.files]

    impacted = _expand_impacted_modules(
        seed_files=seed_files,
        dependency_graph=dependency_graph,
        caller_graph=caller_graph,
        file_index=file_index,
        max_files=max_files,
    )
    verification_targets = _infer_verification_targets(
        changed_files=seed_files,
        impacted_modules=impacted,
        files=scan.files,
    )
    rollback_scope = _infer_rollback_scope(seed_files, impacted)
    runtime_surfaces = _infer_runtime_surfaces(rollback_scope)
    mutation_risk = _infer_mutation_risk(
        changed_files=seed_files,
        impacted_modules=impacted,
        verification_targets=verification_targets,
    )
    verification_owners = _infer_verification_owners(
        impacted_modules=impacted,
        verification_targets=verification_targets,
    )
    impacted_runtime_topology = _infer_impacted_runtime_topology(
        changed_files=seed_files,
        impacted_modules=impacted,
        dependency_graph=dependency_graph,
        caller_graph=caller_graph,
        runtime_surfaces=runtime_surfaces,
        mutation_risk=mutation_risk,
    )

    payload = {
        "task": task_text,
        "changed_files": seed_files,
        "impacted_modules": impacted,
        "verification_targets": verification_targets,
        "rollback_scope": rollback_scope,
        "mutation_risk": mutation_risk,
        "verification_owners": verification_owners,
        "source_scan_id": scan.scan_id,
    }

    return ImpactedPlan(
        changed_files=tuple(seed_files),
        impacted_modules=tuple(impacted),
        verification_targets=tuple(verification_targets),
        rollback_scope=tuple(rollback_scope),
        impacted_runtime_surfaces=tuple(runtime_surfaces),
        mutation_risk=mutation_risk,
        verification_owners={
            key: tuple(value) for key, value in verification_owners.items()
        },
        impacted_runtime_topology=impacted_runtime_topology,
        import_graph={key: tuple(value) for key, value in import_graph.items()},
        caller_graph={key: tuple(value) for key, value in caller_graph.items()},
        dependency_graph={key: tuple(value) for key, value in dependency_graph.items()},
        source_scan_id=scan.scan_id,
        metadata={
            **_read_only_metadata(surface="impacted_plan"),
            "plan_id": "impacted-plan-" + _stable_hash(payload)[:16],
            "dependency_awareness": True,
            "verification_target_inference": True,
            "rollback_scope_inference": True,
            "mutation_risk_inference": True,
            "verification_ownership_inference": True,
            "runtime_topology_inference": True,
        },
    )


def infer_impacted_plan(
    task: str,
    *,
    changed_files: Iterable[str] | None = None,
    repo_root: str | Path | None = None,
    scan: RepoScanResult | None = None,
    max_files: int = 50,
) -> ImpactedPlan:
    return build_impacted_plan(
        task,
        changed_files=changed_files,
        repo_root=repo_root,
        scan=scan,
        max_files=max_files,
    )


def classify_repo_file(path: str | Path) -> str:
    relative = str(path).replace("\\", "/")
    parts = [part.lower() for part in relative.split("/") if part]
    name = parts[-1] if parts else ""
    suffix = Path(relative).suffix.lower()

    if "tests" in parts or name.startswith("test_") or name.endswith("_test.py"):
        return "test"
    if "docs" in parts or suffix in DOC_EXTENSIONS:
        return "docs"
    if name in CONFIG_FILENAMES or suffix in CONFIG_EXTENSIONS:
        return "config"
    if suffix in SOURCE_EXTENSIONS:
        return "source"
    return "other"


def _score_file_for_task(
    record: RepoFileRecord,
    task_tokens: set[str],
) -> tuple[int, list[str]]:
    path_tokens = _tokens(record.path)
    name_tokens = _tokens(Path(record.path).name)
    matches = sorted(task_tokens.intersection(path_tokens))
    name_matches = sorted(task_tokens.intersection(name_tokens))

    score = 0
    reasons: list[str] = []

    if matches:
        score += len(matches) * 2
        reasons.append("path token match: " + ", ".join(matches))
    if name_matches:
        score += len(name_matches)
        reasons.append("filename token match: " + ", ".join(name_matches))

    classification_token = "doc" if record.classification == "docs" else record.classification
    if classification_token in task_tokens or record.classification in task_tokens:
        score += 2
        reasons.append(f"classification match: {record.classification}")
    if record.classification == "test" and {"test", "tests", "pytest", "coverage"}.intersection(task_tokens):
        score += 2
        reasons.append("test intent match")
    if record.classification == "docs" and {"doc", "docs", "document", "documentation"}.intersection(task_tokens):
        score += 2
        reasons.append("documentation intent match")
    if record.classification == "config" and {"config", "configuration", "settings"}.intersection(task_tokens):
        score += 2
        reasons.append("configuration intent match")

    return score, reasons


def _plan_classification(files: Iterable[ImpactedFileRecord]) -> str:
    classifications = {item.classification for item in files}
    if not classifications:
        return "no_direct_match"
    if len(classifications) == 1:
        return next(iter(classifications))
    return "mixed"


def _plan_reasons(files: Iterable[ImpactedFileRecord], task_tokens: set[str]) -> list[str]:
    file_list = list(files)
    if not file_list:
        return ["no conservative path or classification match found"]
    return [
        "read-only impacted file plan",
        f"matched {len(file_list)} file(s)",
        "task tokens: " + ", ".join(sorted(task_tokens)),
    ]


def _read_only_metadata(*, surface: str) -> dict[str, Any]:
    return {
        "surface": surface,
        "read_only": True,
        "mutation_allowed": False,
        "execution_allowed": False,
        "patch_apply_allowed": False,
        "autonomous_execution_allowed": False,
    }


def _python_module_index(files: Iterable[RepoFileRecord]) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in files:
        if record.suffix != ".py":
            continue
        path = record.path
        module = path[:-3].replace("/", ".")
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        result[module] = path
    return result


def _build_import_graph(
    *,
    repo_root: Path,
    files: Iterable[RepoFileRecord],
) -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {}
    for record in files:
        if record.suffix != ".py":
            continue
        path = record.path
        absolute = repo_root / path
        imports: list[str] = []
        try:
            tree = ast.parse(absolute.read_text(encoding="utf-8"))
        except Exception:
            graph[path] = ()
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names if alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = _resolve_import_from_module(path, node)
                if module:
                    imports.append(module)
                    imports.extend(
                        f"{module}.{alias.name}"
                        for alias in node.names
                        if alias.name and alias.name != "*"
                    )
        graph[path] = tuple(_unique_sorted(imports))
    return graph


def _resolve_dependency_graph(
    *,
    import_graph: dict[str, tuple[str, ...]],
    module_to_path: dict[str, str],
) -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {}
    for path, imports in import_graph.items():
        deps: list[str] = []
        for module in imports:
            candidates = _module_candidates(module)
            for candidate in candidates:
                dependency = module_to_path.get(candidate)
                if dependency and dependency != path:
                    deps.append(dependency)
                    break
        graph[path] = tuple(_unique_sorted(deps))
    return graph


def _reverse_graph(graph: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    reversed_graph: dict[str, list[str]] = {}
    for source, targets in graph.items():
        reversed_graph.setdefault(source, [])
        for target in targets:
            reversed_graph.setdefault(target, []).append(source)
    return {key: tuple(_unique_sorted(value)) for key, value in reversed_graph.items()}


def _expand_impacted_modules(
    *,
    seed_files: list[str],
    dependency_graph: dict[str, tuple[str, ...]],
    caller_graph: dict[str, tuple[str, ...]],
    file_index: dict[str, RepoFileRecord],
    max_files: int,
) -> list[str]:
    seen: set[str] = set()
    queue: list[str] = list(seed_files)
    while queue and len(seen) < max_files:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        if current not in file_index:
            continue
        for related in dependency_graph.get(current, ()) + caller_graph.get(current, ()):
            if related not in seen:
                queue.append(related)
    return _unique_sorted(seen)


def _infer_verification_targets(
    *,
    changed_files: list[str],
    impacted_modules: list[str],
    files: Iterable[RepoFileRecord],
) -> list[str]:
    test_files = [record.path for record in files if record.classification == "test"]
    if not test_files:
        return []

    source_tokens = set()
    for path in changed_files + impacted_modules:
        source_tokens.update(_tokens(Path(path).stem.replace("test_", "")))

    targets: list[str] = []
    for path in test_files:
        test_tokens = _tokens(Path(path).stem.replace("test_", ""))
        if source_tokens.intersection(test_tokens):
            targets.append(path)

    for path in changed_files:
        if path in test_files:
            targets.append(path)

    if not targets and changed_files:
        top_level = {path.split("/", 1)[0] for path in changed_files if "/" in path}
        for path in test_files:
            if any(surface in _tokens(path) for surface in top_level):
                targets.append(path)

    return _unique_sorted(targets)


def _infer_rollback_scope(
    changed_files: list[str],
    impacted_modules: list[str],
) -> list[str]:
    return _unique_sorted(list(changed_files) + list(impacted_modules))


def _infer_runtime_surfaces(paths: Iterable[str]) -> list[str]:
    surfaces: set[str] = set()
    for path in paths:
        parts = [part for part in str(path).split("/") if part]
        if not parts:
            continue
        if len(parts) == 1:
            surfaces.add(parts[0])
        else:
            surfaces.add("/".join(parts[:2]))
    return _unique_sorted(surfaces)


def _infer_mutation_risk(
    *,
    changed_files: list[str],
    impacted_modules: list[str],
    verification_targets: list[str],
) -> dict[str, Any]:
    reasons: list[str] = []
    level = "low"
    all_paths = set(changed_files) | set(impacted_modules)
    if len(all_paths) > 5:
        level = "medium"
        reasons.append("multi_module_impact")
    if any(path.startswith("core/runtime/") for path in all_paths):
        level = "high"
        reasons.append("runtime_kernel_surface")
    if any(path.startswith("core/tasks/") for path in all_paths):
        if level == "low":
            level = "medium"
        reasons.append("task_lifecycle_surface")
    if not verification_targets:
        if level == "low":
            level = "medium"
        reasons.append("no_targeted_verification_found")
    return {
        "level": level,
        "reasons": reasons,
        "requires_verification": True,
        "requires_rollback_snapshot": True,
        "impacted_count": len(all_paths),
    }


def _infer_verification_owners(
    *,
    impacted_modules: list[str],
    verification_targets: list[str],
) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for module in impacted_modules:
        module_tokens = _tokens(Path(module).stem.replace("test_", ""))
        matches: list[str] = []
        for target in verification_targets:
            target_tokens = _tokens(Path(target).stem.replace("test_", ""))
            if module == target or module_tokens.intersection(target_tokens):
                matches.append(target)
        owners[module] = _unique_sorted(matches)
    return owners


def _infer_impacted_runtime_topology(
    *,
    changed_files: list[str],
    impacted_modules: list[str],
    dependency_graph: dict[str, tuple[str, ...]],
    caller_graph: dict[str, tuple[str, ...]],
    runtime_surfaces: list[str],
    mutation_risk: dict[str, Any],
) -> dict[str, Any]:
    nodes = _unique_sorted(set(changed_files) | set(impacted_modules))
    edges: list[dict[str, str]] = []
    node_set = set(nodes)
    for source in nodes:
        for target in dependency_graph.get(source, ()):
            if target in node_set:
                edges.append({"source": source, "target": target, "kind": "imports"})
        for target in caller_graph.get(source, ()):
            if target in node_set:
                edges.append({"source": target, "target": source, "kind": "calls_or_imports"})
    return {
        "nodes": nodes,
        "edges": edges,
        "runtime_surfaces": list(runtime_surfaces),
        "entry_files": list(changed_files),
        "risk_level": str(mutation_risk.get("level") or "low"),
        "runtime_dependency_chains": _runtime_dependency_chains(
            entry_files=changed_files,
            dependency_graph=dependency_graph,
            caller_graph=caller_graph,
            node_set=node_set,
        ),
        "mutation_blast_radius": {
            "impacted_nodes": len(nodes),
            "impacted_edges": len(edges),
            "surfaces": list(runtime_surfaces),
            "recursive_dependency_impact": _recursive_dependency_impact(
                entry_files=changed_files,
                dependency_graph=dependency_graph,
                caller_graph=caller_graph,
            ),
        },
        "runtime_ownership_surfaces": _runtime_ownership_surfaces(nodes),
        "verification_topology_mapping": {
            "requires_targeted_verification": True,
            "risk_level": str(mutation_risk.get("level") or "low"),
            "surface_count": len(runtime_surfaces),
        },
        "transaction_risk_score": _transaction_risk_score(
            node_count=len(nodes),
            edge_count=len(edges),
            risk_level=str(mutation_risk.get("level") or "low"),
        ),
        "transitive": True,
    }


def _runtime_dependency_chains(
    *,
    entry_files: list[str],
    dependency_graph: dict[str, tuple[str, ...]],
    caller_graph: dict[str, tuple[str, ...]],
    node_set: set[str],
) -> list[dict[str, Any]]:
    chains: list[dict[str, Any]] = []
    for entry in entry_files:
        dependencies = [path for path in dependency_graph.get(entry, ()) if path in node_set]
        callers = [path for path in caller_graph.get(entry, ()) if path in node_set]
        chains.append(
            {
                "entry": entry,
                "dependencies": dependencies,
                "callers": callers,
                "recursive": bool(dependencies or callers),
            }
        )
    return chains


def _runtime_ownership_surfaces(paths: Iterable[str]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for path in paths:
        parts = [part for part in str(path).split("/") if part]
        owner = "/".join(parts[:2]) if len(parts) > 1 else (parts[0] if parts else "root")
        owners.setdefault(owner, []).append(path)
    return {key: _unique_sorted(value) for key, value in sorted(owners.items())}


def _recursive_dependency_impact(
    *,
    entry_files: list[str],
    dependency_graph: dict[str, tuple[str, ...]],
    caller_graph: dict[str, tuple[str, ...]],
) -> dict[str, Any]:
    seen: set[str] = set()
    queue = list(entry_files)
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        queue.extend(path for path in dependency_graph.get(current, ()) if path not in seen)
        queue.extend(path for path in caller_graph.get(current, ()) if path not in seen)
    return {
        "entry_count": len(entry_files),
        "reachable_count": len(seen),
        "recursive": len(seen) > len(entry_files),
    }


def _transaction_risk_score(*, node_count: int, edge_count: int, risk_level: str) -> int:
    base = {"low": 1, "medium": 3, "high": 5}.get(risk_level, 1)
    return min(10, base + min(3, node_count // 3) + min(2, edge_count // 4))


def _resolve_import_from_module(path: str, node: ast.ImportFrom) -> str:
    module = node.module or ""
    if not node.level:
        return module
    package_parts = path[:-3].split("/")[:-1]
    if path.endswith("/__init__.py"):
        package_parts = path[:-12].split("/") if path[:-12] else []
    base_parts = package_parts[: max(0, len(package_parts) - node.level + 1)]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(part for part in base_parts if part)


def _module_candidates(module: str) -> list[str]:
    parts = [part for part in str(module).split(".") if part]
    candidates: list[str] = []
    for index in range(len(parts), 0, -1):
        candidates.append(".".join(parts[:index]))
    return candidates


def _normalize_plan_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lstrip("./")


def _unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def _should_ignore_dir(name: str) -> bool:
    return str(name).strip().lower() in IGNORED_DIR_NAMES


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^A-Za-z0-9]+", str(value).lower())
        if len(token) >= 3
    }


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
