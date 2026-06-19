from __future__ import annotations

import ast
from pathlib import Path

from core.runtime.runtime_mutation_guard import RuntimeMutationGuard
from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

ROOT = Path(__file__).resolve().parents[1]

RUNTIME_OWNERSHIP_FILE = ROOT / "core/runtime/runtime_ownership.py"
RUNTIME_MUTATION_GUARD_FILE = ROOT / "core/runtime/runtime_mutation_guard.py"
RUNTIME_AUTHORITY_SEAL_FILE = ROOT / "core/runtime/runtime_authority_seal.py"
SYSTEM_METADATA_FILES = {
    "core/runtime/execution_gateway.py",
    "core/runtime/runtime_file_service.py",
}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_source(path), filename=str(path))


def _string_constants(path: Path) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.add(node.value)
    return values


def test_system_owner_is_currently_unrestricted_in_runtime_ownership() -> None:
    source = _source(RUNTIME_OWNERSHIP_FILE)

    assert 'SYSTEM = "system"' in source
    assert "if runtime_owner is RuntimeOwner.SYSTEM" in source
    assert "return True" in source[source.index("if runtime_owner is RuntimeOwner.SYSTEM") :]

    matrix = [
        (resource.value, action.value, can_access(RuntimeOwner.SYSTEM, resource, action))
        for resource in RuntimeResource
        for action in RuntimeAction
    ]
    denied = [(resource, action) for resource, action, allowed in matrix if not allowed]

    assert not denied, {"system_wildcard_denials": denied}


def test_mutation_guard_inherits_system_wildcard_from_can_access() -> None:
    source = _source(RUNTIME_MUTATION_GUARD_FILE)

    assert "from core.runtime.runtime_ownership import can_access" in source

    request = RuntimeMutationGuard.validate(
        RuntimeOwner.SYSTEM,
        RuntimeResource.QUEUE_STATE,
        RuntimeAction.WRITE,
        reason="audit_current_system_wildcard",
    )

    assert request.allowed is True
    assert request.owner is RuntimeOwner.SYSTEM
    assert request.resource is RuntimeResource.QUEUE_STATE
    assert request.action is RuntimeAction.WRITE


def test_live_authority_seal_uses_private_tokens_not_system_string() -> None:
    source = _source(RUNTIME_AUTHORITY_SEAL_FILE)

    assert "_RUNTIME_DISPATCHER_ISSUER_TOKEN = object()" in source
    assert "_TASK_RUNNER_ISSUER_TOKEN = object()" in source
    assert "_WORK_PACKAGE_SCHEDULER_ISSUER_TOKEN = object()" in source
    assert "RuntimeOwner.SYSTEM" not in source
    assert '"SYSTEM"' not in _string_constants(RUNTIME_AUTHORITY_SEAL_FILE)


def test_system_metadata_identities_are_present_but_separate_from_policy_authority() -> None:
    findings: dict[str, bool] = {}
    for rel in sorted(SYSTEM_METADATA_FILES):
        source = _source(ROOT / rel)
        findings[rel] = '"identity_type": "SYSTEM"' in source or "'identity_type': 'SYSTEM'" in source

    assert all(findings.values()), findings


def test_next_seal_targets_are_explicit() -> None:
    targets = {
        "core/runtime/runtime_ownership.py",
        "core/runtime/runtime_mutation_guard.py",
        "core/runtime/runtime_authority_seal.py",
        "core/runtime/runtime_execution_authority_gate.py",
        "core/runtime/runtime_execution_authority_policy.py",
        "core/runtime/runtime_evidence_authority.py",
    }

    existing = {target for target in targets if (ROOT / target).exists()}

    assert existing == targets
