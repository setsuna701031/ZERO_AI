from __future__ import annotations

from pathlib import Path


DOC = Path("docs/contracts/runtime/recovery_runtime_binding_policy_v1.md")


def _text() -> str:
    assert DOC.exists(), f"missing {DOC}"
    return DOC.read_text(encoding="utf-8")


def test_binding_policy_declares_contract_id_and_authority() -> None:
    text = _text()

    assert "Package 181: Recovery Runtime Binding Policy" in text
    assert "zero.runtime.recovery.binding_policy.v1" in text
    assert "allowed entry name policy" in text
    assert "kill-switch default rule" in text
    assert "canonical event preservation rule" in text


def test_binding_policy_allows_only_single_entry() -> None:
    text = _text()

    assert "Only this entry is allowed" in text
    assert "runtime_recovery_single_entry" in text


def test_binding_policy_requires_preflight_before_binding() -> None:
    text = _text()

    required = [
        "The kill switch exists and defaults off/safe.",
        "Recovery enablement defaults to false.",
        "Canonical event schema is preserved.",
        "Dry-run route report exists and remains non-emitting.",
        "Observation report exists and remains non-executing.",
        "Preflight eligibility exists before any binding changes Runtime state.",
        "Runtime modules are not called during policy validation.",
        "Non-mainline issues are reported explicitly.",
        "Long validation commands are handed back for local execution unless explicitly allowed.",
    ]
    for phrase in required:
        assert phrase in text


def test_binding_policy_denies_active_capabilities_by_default() -> None:
    text = _text()

    for capability in [
        "recovery_execution",
        "recovery_enablement",
        "runtime_mainline_wiring",
        "runtime_mutation",
        "event_emission",
        "scheduler_call",
        "operator_call",
        "dispatcher_call",
        "supervisor_call",
        "native_runtime_call",
        "persistence_write",
        "replay_action",
        "audit_emission",
        "journal_event",
        "subprocess_call",
        "file_io",
    ]:
        assert capability in text


def test_binding_policy_result_shape_is_plain_and_non_executing() -> None:
    text = _text()

    for field in [
        "contract",
        "prepared",
        "blocked",
        "denied",
        "status",
        "single_entry_only",
        "kill_switch_state",
        "recovery_enabled",
        "canonical_event",
        "policy_only",
        "executes_recovery",
        "side_effects_performed",
        "plain_dict_only",
    ]:
        assert field in text


def test_binding_policy_does_not_authorize_runtime_binding() -> None:
    text = _text()

    assert "does not authorize active Runtime wiring" in text
    assert "implement Runtime binding" in text
