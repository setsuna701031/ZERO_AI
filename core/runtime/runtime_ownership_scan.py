from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.runtime.runtime_ownership_policy import (
    ALLOWED_GATEWAY_MODULES,
    FORBIDDEN_EXECUTION_CALLS,
    FORBIDDEN_WRITE_CALLS,
    ORCHESTRATION_ONLY_SURFACES,
    evaluate_ownership_findings,
)


def scan_runtime_ownership_paths(
    paths: Iterable[str | Path],
    *,
    repo_root: str | Path | None = None,
    owner: str = "",
    include_write_calls: bool = True,
) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    files = [Path(path) for path in paths]
    findings: list[dict[str, Any]] = []
    scanned: list[str] = []

    for path in files:
        resolved = path if path.is_absolute() else root / path
        if not resolved.exists() or resolved.suffix != ".py":
            continue
        relative = _relative_path(resolved, root)
        scanned.append(relative)
        findings.extend(
            _scan_python_file(
                resolved,
                relative_path=relative,
                owner=owner or _owner_from_path(relative),
                include_write_calls=include_write_calls,
            )
        )

    policy = evaluate_ownership_findings(findings, owner=owner)
    return {
        "schema": "runtime_ownership_scan_report.v1",
        "ok": bool(policy.get("ok")),
        "repo_root": str(root),
        "scanned_files": scanned,
        "finding_count": len(findings),
        "findings": findings,
        "policy": policy,
        "no_execution_added": True,
        "scan_only": True,
    }


def scan_default_runtime_ownership_surfaces(
    *,
    repo_root: str | Path | None = None,
    include_write_calls: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    paths = [
        root / "core" / "agent" / "agent_loop.py",
        root / "core" / "tasks" / "scheduler.py",
        root / "services" / "system_boot.py",
        root / "core" / "runtime" / "execution_gateway.py",
        root / "core" / "runtime" / "executor.py",
    ]
    return scan_runtime_ownership_paths(
        paths,
        repo_root=root,
        owner="runtime_ownership_default_surface",
        include_write_calls=include_write_calls,
    )


def _scan_python_file(
    path: Path,
    *,
    relative_path: str,
    owner: str,
    include_write_calls: bool,
) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError as exc:
        return [
            {
                "file_path": relative_path,
                "line": int(exc.lineno or 0),
                "owner": owner,
                "violation": True,
                "violation_type": "python_parse_error",
                "symbol": "syntax_error",
                "reason": str(exc),
                "evidence": {},
            }
        ]

    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        symbol = _call_symbol(node)
        if not symbol:
            continue
        finding = _classify_call(
            symbol,
            file_path=relative_path,
            line=int(getattr(node, "lineno", 0) or 0),
            owner=owner,
            include_write_calls=include_write_calls,
        )
        if finding:
            findings.append(finding)
    return findings


def _classify_call(
    symbol: str,
    *,
    file_path: str,
    line: int,
    owner: str,
    include_write_calls: bool,
) -> dict[str, Any] | None:
    normalized_file = file_path.replace("\\", "/")
    in_gateway = normalized_file in ALLOWED_GATEWAY_MODULES
    owner_is_orchestration = owner in ORCHESTRATION_ONLY_SURFACES or any(
        token in normalized_file for token in ("agent_loop.py", "scheduler.py", "system_boot.py")
    )

    if symbol in FORBIDDEN_EXECUTION_CALLS and not in_gateway:
        return _finding(
            file_path=file_path,
            line=line,
            owner=owner,
            violation_type="direct_execution_bypass",
            symbol=symbol,
            reason="execution must route through runtime.execution_gateway -> runtime.executor",
            evidence={"canonical_gateway_modules": sorted(ALLOWED_GATEWAY_MODULES)},
        )

    if include_write_calls and owner_is_orchestration and _write_symbol(symbol):
        return _finding(
            file_path=file_path,
            line=line,
            owner=owner,
            violation_type="direct_write_bypass",
            symbol=symbol,
            reason="orchestration surfaces must not directly perform write/mutation execution",
            evidence={"orchestration_only": True},
        )

    return None


def _finding(
    *,
    file_path: str,
    line: int,
    owner: str,
    violation_type: str,
    symbol: str,
    reason: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "file_path": file_path,
        "line": line,
        "owner": owner,
        "violation": True,
        "violation_type": violation_type,
        "symbol": symbol,
        "reason": reason,
        "evidence": copy.deepcopy(dict(evidence)),
    }


def _call_symbol(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = _attribute_base(func.value)
        if base:
            return f"{base}.{func.attr}"
        return func.attr
    return ""


def _attribute_base(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _attribute_base(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _write_symbol(symbol: str) -> bool:
    if symbol in FORBIDDEN_WRITE_CALLS:
        return True
    return any(symbol.endswith("." + item) for item in FORBIDDEN_WRITE_CALLS)


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _owner_from_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.endswith("agent_loop.py"):
        return "agent_loop"
    if normalized.endswith("scheduler.py"):
        return "scheduler"
    if normalized.endswith("system_boot.py"):
        return "system_boot"
    if normalized.endswith("execution_gateway.py"):
        return "execution_gateway"
    if normalized.endswith("executor.py"):
        return "executor"
    return "unknown"


def report_to_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


__all__ = [
    "report_to_json",
    "scan_default_runtime_ownership_surfaces",
    "scan_runtime_ownership_paths",
]
