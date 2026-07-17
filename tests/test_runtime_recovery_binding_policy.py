from core.runtime.aer_runtime_recovery_binding_policy import (
    RECOVERY_RUNTIME_BINDING_POLICY_CONTRACT,
    RECOVERY_RUNTIME_BINDING_POLICY_ENTRY,
    prepare_recovery_runtime_binding_policy,
)


def test_binding_policy_prepared_single_entry_only():
    report = prepare_recovery_runtime_binding_policy(metadata={"a": ("b",)})
    assert report["contract"] == RECOVERY_RUNTIME_BINDING_POLICY_CONTRACT
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["binding_entry"] == RECOVERY_RUNTIME_BINDING_POLICY_ENTRY
    assert report["single_entry_only"] is True
    assert report["binds_runtime"] is False
    assert report["binding_enabled"] is False
    assert report["route_enabled"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["runtime_mainline_wiring_allowed"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True
    assert report["metadata"] == {"a": ["b"]}


def test_binding_policy_blocks_non_single_entry():
    report = prepare_recovery_runtime_binding_policy(requested_entry="scheduler")
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["denied"] is False
    assert report["binding_entry"] is None
    assert "runtime_recovery_single_entry" in report["reason"]


def test_binding_policy_denies_enablement_request():
    report = prepare_recovery_runtime_binding_policy(request_enablement=True)
    assert report["prepared"] is False
    assert report["blocked"] is False
    assert report["denied"] is True
    assert report["recovery_enabled"] is False


def test_binding_policy_has_strict_public_surface():
    import core.runtime.aer_runtime_recovery_binding_policy as module

    assert module.__all__ == [
        "RECOVERY_RUNTIME_BINDING_POLICY_CONTRACT",
        "RECOVERY_RUNTIME_BINDING_POLICY_ALLOWED_STATUSES",
        "RECOVERY_RUNTIME_BINDING_POLICY_ENTRY",
        "RECOVERY_RUNTIME_BINDING_POLICY_ALLOWED_SURFACES",
        "RECOVERY_RUNTIME_BINDING_POLICY_OBSERVE_ONLY_SURFACES",
        "RECOVERY_RUNTIME_BINDING_POLICY_DENIED_CAPABILITIES",
        "prepare_recovery_runtime_binding_policy",
    ]


def test_binding_policy_source_has_no_forbidden_runtime_tokens():
    from pathlib import Path

    source = Path("core/runtime/aer_runtime_recovery_binding_policy.py").read_text(encoding="utf-8")
    forbidden = ("subprocess.", "open(", ".write(", "emit_event", "Scheduler(", "TaskRunner(")
    for token in forbidden:
        assert token not in source
