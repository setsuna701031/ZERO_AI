from core.runtime.runtime_capability_strategy import RuntimeCapabilityStrategy


def strategy(mode="cpu_only", *, workers=4, compute="cpu", tools=("python",), network="offline_safe", constraints=()):
    return RuntimeCapabilityStrategy.create({
        "profile_id": "profile-test", "profile_fingerprint": "profile-fingerprint-test",
        "recommended_mode": mode,
        "execution_preferences": {
            "preferred_compute": compute,
            "preferred_accelerator_kind": "cuda" if compute == "accelerator" else None,
            "parallelism": {"max_workers": workers, "reason": "test_bound"},
            "memory_policy": {"mode": "constrained" if mode == "memory_constrained" else "balanced", "reason": "test"},
            "storage_policy": {"mode": "bounded", "minimum_free_bytes": None},
            "network_policy": {"mode": network, "outbound_required": False},
        },
        "tool_preferences": [{"name": name} for name in tools], "model_preferences": [],
        "constraints": [{"code": code} for code in constraints], "reasons": [], "diagnostics": [],
    }).to_dict()
