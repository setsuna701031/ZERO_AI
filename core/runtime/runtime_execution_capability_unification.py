from __future__ import annotations

"""Canonical audit for runtime execution authority and capability layers.

This module is deliberately descriptive and policy-only.  It does not issue
capabilities, validate live execution, run commands, mutate files, or repair
state.  Its purpose is to keep the runtime wording and rule ownership unified:

Execution Authority -> Capability Token -> Runtime Action

Execution authority decides whether a side-effect may be attempted.  Capability
objects are scoped bearer proofs for one part of that decision.  Runtime actions
are the side effects that can only occur after the policy and token layers agree.
"""

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_execution_authority_policy import (
    CANONICAL_EXECUTION_AUTHORITY_MATRIX,
    CANONICAL_EXECUTION_AUTHORITY_PATH,
)
from core.runtime.runtime_system_capability import (
    RuntimeCapabilityClass,
    SYSTEM_CAPABILITY_INVENTORY,
)

EXECUTION_AUTHORITY_LAYER = "execution_authority"
CAPABILITY_TOKEN_LAYER = "capability_token"
RUNTIME_ACTION_LAYER = "runtime_action"

RUNTIME_EXECUTION_CAPABILITY_FLOW = (
    EXECUTION_AUTHORITY_LAYER,
    CAPABILITY_TOKEN_LAYER,
    RUNTIME_ACTION_LAYER,
)

LAYER_RESPONSIBILITIES: dict[str, str] = {
    EXECUTION_AUTHORITY_LAYER: "decides whether a runtime side effect may be attempted",
    CAPABILITY_TOKEN_LAYER: "proves scoped, live, lineage-bound permission for the decided request",
    RUNTIME_ACTION_LAYER: "performs the concrete runtime side effect after the prior layers pass",
}

PROHIBITED_LAYER_COLLAPSES = (
    (CAPABILITY_TOKEN_LAYER, EXECUTION_AUTHORITY_LAYER),
    (RUNTIME_ACTION_LAYER, EXECUTION_AUTHORITY_LAYER),
    (RUNTIME_ACTION_LAYER, CAPABILITY_TOKEN_LAYER),
)


@dataclass(frozen=True)
class RuntimeExecutionCapabilityUnificationAudit:
    ok: bool
    reason: str
    canonical_flow: tuple[str, ...] = RUNTIME_EXECUTION_CAPABILITY_FLOW
    findings: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", _fingerprint(self.to_dict(include_fingerprint=False)))

    def to_dict(self, *, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "schema": "zero.runtime_execution_capability_unification_audit.v1",
            "ok": self.ok,
            "reason": self.reason,
            "canonical_flow": list(self.canonical_flow),
            "findings": copy.deepcopy(list(self.findings)),
            "no_execution_performed": True,
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.fingerprint == _fingerprint(self.to_dict(include_fingerprint=False))
        return payload


def audit_runtime_execution_capability_unification() -> RuntimeExecutionCapabilityUnificationAudit:
    """Return a stable policy audit for authority/capability/action separation."""

    findings: list[dict[str, Any]] = []
    findings.extend(_audit_execution_authority_matrix())
    findings.extend(_audit_system_capability_inventory())
    findings.extend(_audit_canonical_flow())
    failures = tuple(finding for finding in findings if finding.get("ok") is False)
    return RuntimeExecutionCapabilityUnificationAudit(
        ok=not failures,
        reason="runtime_execution_capability_layers_unified" if not failures else "runtime_execution_capability_layer_conflict",
        findings=tuple(findings),
    )


def describe_runtime_execution_capability_flow() -> dict[str, Any]:
    return {
        "schema": "zero.runtime_execution_capability_flow.v1",
        "canonical_flow": list(RUNTIME_EXECUTION_CAPABILITY_FLOW),
        "responsibilities": copy.deepcopy(LAYER_RESPONSIBILITIES),
        "canonical_execution_path": list(CANONICAL_EXECUTION_AUTHORITY_PATH),
        "rule": "execution_authority_decides_capability_token_proves_runtime_action_executes",
        "no_execution_performed": True,
    }


def _audit_canonical_flow() -> list[dict[str, Any]]:
    return [
        {
            "ok": RUNTIME_EXECUTION_CAPABILITY_FLOW == (
                EXECUTION_AUTHORITY_LAYER,
                CAPABILITY_TOKEN_LAYER,
                RUNTIME_ACTION_LAYER,
            ),
            "name": "canonical_flow_order",
            "flow": list(RUNTIME_EXECUTION_CAPABILITY_FLOW),
        },
        {
            "ok": all(left != right for left, right in PROHIBITED_LAYER_COLLAPSES),
            "name": "layer_names_are_not_collapsed",
            "prohibited_collapses": [list(pair) for pair in PROHIBITED_LAYER_COLLAPSES],
        },
    ]


def _audit_execution_authority_matrix() -> list[dict[str, Any]]:
    execute_rows = {
        name: row for name, row in CANONICAL_EXECUTION_AUTHORITY_MATRIX.items() if bool(row.get("may_execute"))
    }
    return [
        {
            "ok": bool(execute_rows),
            "name": "execution_authority_has_explicit_action_owners",
            "owners": sorted(execute_rows),
        },
        {
            "ok": all(row.get("role") == "EXECUTE" for row in execute_rows.values()),
            "name": "only_execute_role_may_perform_runtime_action",
            "owners": sorted(execute_rows),
        },
        {
            "ok": all(bool(row.get("requires_gate")) for row in execute_rows.values()),
            "name": "runtime_actions_require_execution_gate",
            "owners": sorted(execute_rows),
        },
    ]


def _audit_system_capability_inventory() -> list[dict[str, Any]]:
    grants = {str(key.value): sorted(value) for key, value in SYSTEM_CAPABILITY_INVENTORY.items()}
    return [
        {
            "ok": set(SYSTEM_CAPABILITY_INVENTORY) == set(RuntimeCapabilityClass),
            "name": "system_capability_inventory_covers_all_classes",
            "classes": sorted(grants),
        },
        {
            "ok": SYSTEM_CAPABILITY_INVENTORY[RuntimeCapabilityClass.ADMIN] == frozenset(),
            "name": "system_capability_admin_does_not_grant_authority",
        },
        {
            "ok": all("*" not in grant for grant_set in SYSTEM_CAPABILITY_INVENTORY.values() for grant in grant_set),
            "name": "system_capability_inventory_has_no_wildcards",
        },
    ]


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "CAPABILITY_TOKEN_LAYER",
    "EXECUTION_AUTHORITY_LAYER",
    "LAYER_RESPONSIBILITIES",
    "PROHIBITED_LAYER_COLLAPSES",
    "RUNTIME_ACTION_LAYER",
    "RUNTIME_EXECUTION_CAPABILITY_FLOW",
    "RuntimeExecutionCapabilityUnificationAudit",
    "audit_runtime_execution_capability_unification",
    "describe_runtime_execution_capability_flow",
]
