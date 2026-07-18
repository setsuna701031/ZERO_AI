from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_verification_validation import validate_runtime_integration_verification

SCHEMA = "zero.runtime.capability_strategy_runtime_integration_closure.v1"
STATUSES = frozenset({"closed", "not_closed", "rejected", "invalid"})

def close_runtime_integration(verification: Any) -> dict[str, Any]:
    valid = validate_runtime_integration_verification(verification).valid
    source_status = verification.get("status") if isinstance(verification, Mapping) else None
    status = ({"verified": "closed", "not_verified": "not_closed", "rejected": "rejected", "invalid": "invalid"}.get(source_status, "invalid") if valid else "invalid")
    value = verification if isinstance(verification, Mapping) else {}
    links = {k: value.get(k) for k in value if k.startswith("source_")}
    payload = None
    if status == "closed":
        payload = {"final_wiring_id": value.get("source_integration_wiring_id"),
                   "final_wiring_fingerprint": value.get("source_integration_wiring_fingerprint"),
                   "passive_integration_payload": deepcopy(value.get("verification_payload")),
                   "closure_evidence": deepcopy(value.get("evidence"))}
    base = {"schema": SCHEMA, "status": status,
            "source_verification_id": value.get("verification_id"),
            "source_verification_fingerprint": value.get("fingerprint"), **links,
            "closure_payload": payload,
            "reasons": [{"closed": "verified_runtime_integration_chain_closed", "not_closed": "unverified_chain_not_closed", "rejected": "rejected_chain_closed_fail_safe", "invalid": "invalid_verification_chain"}[status]],
            "boundary": {"sealed": True, "read_only": True, "verification_closed": status == "closed",
                         "passive_closure": True, "runtime_activation": False, "execution_started": False,
                         "authority_granted": False, "scope_expansion": False, "constraint_weakening": False,
                         "live_binding": False}}
    return _identified(base, "closure_id", "capability-strategy-runtime-integration-closure-")

build_runtime_integration_closure = close_runtime_integration
__all__ = ["SCHEMA", "STATUSES", "build_runtime_integration_closure", "close_runtime_integration"]
