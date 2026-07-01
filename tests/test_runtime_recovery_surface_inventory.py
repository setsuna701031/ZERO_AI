from __future__ import annotations

from pathlib import Path


DOC = Path("docs/runtime_recovery_surface_inventory.md")


def _text() -> str:
    assert DOC.exists(), f"missing {DOC}"
    return DOC.read_text(encoding="utf-8")


def test_inventory_lists_runtime_surfaces_as_unbound_or_declarative() -> None:
    text = _text()

    for surface in [
        "runtime_recovery_single_entry",
        "Scheduler",
        "Operator",
        "Dispatcher",
        "Supervisor",
        "Native Runtime",
        "Recovery Executor",
    ]:
        assert surface in text

    assert "not bound" in text
    assert "not created" in text


def test_inventory_states_do_not_authorize_active_binding() -> None:
    text = _text()

    for state in [
        "not_declared",
        "declared_only",
        "dry_run_only",
        "observe_only",
        "preflight_only",
        "bound_disabled",
        "bound_guarded",
        "enabled_controlled",
    ]:
        assert state in text

    assert "No Runtime surface may become `bound_disabled`, `bound_guarded`, or `enabled_controlled`" in text


def test_inventory_is_static_contract_data_only() -> None:
    text = _text()

    required = [
        "Inventory is static contract data.",
        "Inventory does not scan source files.",
        "Inventory does not import Runtime modules.",
        "Inventory does not call Runtime behavior.",
        "Inventory does not emit events.",
        "Inventory does not mutate state.",
        "Inventory does not enable Recovery.",
    ]
    for phrase in required:
        assert phrase in text


def test_inventory_preserves_canonical_event_fields() -> None:
    text = _text()

    for field in [
        "contract",
        "source_surface",
        "entry_id",
        "route_id",
        "gate_state",
        "event_emitted",
    ]:
        assert field in text


def test_inventory_forbids_runtime_calls() -> None:
    text = _text()

    for phrase in [
        "call Scheduler",
        "call Operator",
        "call Dispatcher",
        "call Supervisor",
        "call Native Runtime",
        "create or call a Recovery Executor",
        "run broad validation",
    ]:
        assert phrase in text
