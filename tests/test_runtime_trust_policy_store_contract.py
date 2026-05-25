from __future__ import annotations

import json


def test_missing_trust_policy_store_rejects() -> None:
    from core.runtime.runtime_trust_policy_store import RuntimeTrustPolicyStore

    store = RuntimeTrustPolicyStore()

    assert store.ok is False
    assert "missing_trust_policy" in store.validation["reasons"]
    assert "missing_policy_metadata" in store.validation["reasons"]


def test_store_rejects_malformed_policy() -> None:
    from core.runtime.runtime_trust_policy_store import RuntimeTrustPolicyStore

    store = RuntimeTrustPolicyStore({"policy_id": "policy-without-workers"})

    assert store.ok is False
    assert "missing_trusted_workers" in store.validation["reasons"]


def test_store_loads_policy_from_json_file(tmp_path) -> None:
    from core.runtime.runtime_trust_policy_store import RuntimeTrustPolicyStore

    policy_path = tmp_path / "trust_policy.json"
    policy_path.write_text(json.dumps(_policy()), encoding="utf-8")
    store = RuntimeTrustPolicyStore(policy_path)

    assert store.ok is True
    assert store.validation["source_kind"] == "file"
    assert store.validation["policy_id"] == "worker-policy"
    assert store.validation["policy_version"] == "v3"


def test_store_rotation_aware_lookup_active_revoked_retired() -> None:
    from core.runtime.runtime_trust_policy_store import RuntimeTrustPolicyStore

    store = RuntimeTrustPolicyStore(
        {
            "policy_id": "worker-policy",
            "policy_version": "v3",
            "trusted_workers": [
                _worker("worker-active", "active-key", "active"),
                _worker("worker-revoked", "revoked-key", "revoked"),
                _worker("worker-retired", "retired-key", "retired"),
            ],
        }
    )

    active = store.lookup_worker("worker-active")
    revoked = store.lookup_worker("worker-revoked")
    retired_new = store.lookup_worker("worker-retired")
    retired_historical = store.lookup_worker("worker-retired", historical=True)

    assert active["ok"] is True
    assert active["trust_key"] == "active-key"
    assert active["rotation"]["state"] == "active"
    assert revoked["ok"] is False
    assert "revoked_worker_id" in revoked["reasons"]
    assert retired_new["ok"] is False
    assert "retired_trust_material" in retired_new["reasons"]
    assert retired_historical["ok"] is True
    assert retired_historical["worker_state"] == "retired"


def test_store_unknown_worker_rejects() -> None:
    from core.runtime.runtime_trust_policy_store import RuntimeTrustPolicyStore

    result = RuntimeTrustPolicyStore(_policy()).lookup_worker("missing-worker")

    assert result["ok"] is False
    assert "unknown_worker_id" in result["reasons"]


def _policy() -> dict[str, object]:
    return {
        "policy_id": "worker-policy",
        "policy_version": "v3",
        "trusted_workers": [_worker("worker-alpha", "alpha-secret", "active")],
    }


def _worker(worker_id: str, trust_key: str, state: str) -> dict[str, object]:
    return {
        "worker_id": worker_id,
        "trust_key": trust_key,
        "status": state,
        "rotation": {"state": state, "key_id": f"{worker_id}-{state}"},
    }
