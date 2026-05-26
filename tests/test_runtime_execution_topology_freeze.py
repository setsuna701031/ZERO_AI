from __future__ import annotations

from core.runtime.runtime_surface_registry import (
    RuntimeSurfaceKind,
    RuntimeSurfaceRisk,
    classify_runtime_surface,
    list_runtime_surfaces,
)


def test_runtime_execution_topology_freeze_contract() -> None:
    surfaces = list_runtime_surfaces()

    execution_surfaces = [
        surface for surface in surfaces if surface.kind is RuntimeSurfaceKind.EXECUTION
    ]
    mutation_surfaces = [surface for surface in surfaces if surface.mutation]
    read_only_surfaces = [surface for surface in surfaces if surface.read_only]

    assert len(execution_surfaces) > 0
    assert len(mutation_surfaces) > 0
    assert len(read_only_surfaces) > 0

    for surface in surfaces:
        if surface.side_effect:
            assert surface.requires_authority is True, surface.name
        if surface.requires_authority:
            assert surface.risk is not RuntimeSurfaceRisk.NONE, surface.name
        if surface.kind is RuntimeSurfaceKind.REVIEW_POLICY:
            assert surface.requires_authority is False, surface.name
        assert not (surface.read_only and surface.mutation), surface.name
        assert surface.anonymous is False, surface.name


def test_no_anonymous_mutation_is_registered_but_unknown_mutation_is_blocked() -> None:
    surfaces = list_runtime_surfaces()
    assert [surface.name for surface in surfaces if surface.anonymous and surface.mutation] == []

    anonymous = classify_runtime_surface("anonymous_runtime_mutation_surface")
    assert anonymous.anonymous is True
    assert anonymous.mutation is True
    assert anonymous.requires_authority is True
