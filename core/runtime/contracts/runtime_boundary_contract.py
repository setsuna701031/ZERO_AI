from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RUNTIME_BOUNDARY_SCHEMA = "zero.runtime.boundary.v1"

RUNTIME_BOUNDARY_COMPONENTS = (
    "scheduler",
    "task_runner",
    "dispatcher",
    "operator",
)

RUNTIME_BOUNDARY_DIRECTIONS = (
    "scheduler->dispatcher",
    "scheduler->task_runner",
    "scheduler->operator",
    "dispatcher->scheduler",
    "dispatcher->task_runner",
    "task_runner->dispatcher",
    "task_runner->operator",
    "operator->dispatcher",
)

RUNTIME_BOUNDARY_FIELDS = (
    "source_component",
    "target_component",
    "boundary_direction",
    "boundary_family",
    "boundary_status",
)

RUNTIME_BOUNDARY_REQUIRED_FIELDS = (
    "source_component",
    "target_component",
    "boundary_direction",
)


def normalize_boundary_component(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def normalize_boundary_direction(source_component: Any, target_component: Any) -> str:
    source = normalize_boundary_component(source_component)
    target = normalize_boundary_component(target_component)
    return f"{source}->{target}"


def is_known_runtime_boundary_component(value: Any) -> bool:
    return normalize_boundary_component(value) in RUNTIME_BOUNDARY_COMPONENTS


def is_known_runtime_boundary_direction(value: Any) -> bool:
    return str(value or "").strip().lower().replace(" ", "") in RUNTIME_BOUNDARY_DIRECTIONS


def validate_runtime_boundary_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "ok": False,
            "schema": RUNTIME_BOUNDARY_SCHEMA,
            "reason": "runtime_boundary_not_mapping",
            "missing_fields": list(RUNTIME_BOUNDARY_REQUIRED_FIELDS),
        }

    missing_fields = [
        field
        for field in RUNTIME_BOUNDARY_REQUIRED_FIELDS
        if not str(value.get(field) or "").strip()
    ]
    if missing_fields:
        return {
            "ok": False,
            "schema": RUNTIME_BOUNDARY_SCHEMA,
            "reason": "runtime_boundary_missing_required_fields",
            "missing_fields": missing_fields,
        }

    source_component = normalize_boundary_component(value.get("source_component"))
    target_component = normalize_boundary_component(value.get("target_component"))
    boundary_direction = str(value.get("boundary_direction") or "").strip().lower().replace(" ", "")
    expected_direction = normalize_boundary_direction(source_component, target_component)

    invalid_components = [
        field
        for field, component in (
            ("source_component", source_component),
            ("target_component", target_component),
        )
        if component not in RUNTIME_BOUNDARY_COMPONENTS
    ]
    if invalid_components:
        return {
            "ok": False,
            "schema": RUNTIME_BOUNDARY_SCHEMA,
            "reason": "runtime_boundary_unknown_components",
            "invalid_fields": invalid_components,
        }

    if boundary_direction != expected_direction:
        return {
            "ok": False,
            "schema": RUNTIME_BOUNDARY_SCHEMA,
            "reason": "runtime_boundary_direction_mismatch",
            "expected_direction": expected_direction,
            "actual_direction": boundary_direction,
        }

    if boundary_direction not in RUNTIME_BOUNDARY_DIRECTIONS:
        return {
            "ok": False,
            "schema": RUNTIME_BOUNDARY_SCHEMA,
            "reason": "runtime_boundary_unknown_direction",
            "actual_direction": boundary_direction,
        }

    return {
        "ok": True,
        "schema": RUNTIME_BOUNDARY_SCHEMA,
        "reason": "runtime_boundary_shape_valid",
    }


def runtime_boundary_contract_summary() -> dict[str, Any]:
    return {
        "schema": RUNTIME_BOUNDARY_SCHEMA,
        "components": list(RUNTIME_BOUNDARY_COMPONENTS),
        "directions": list(RUNTIME_BOUNDARY_DIRECTIONS),
        "fields": list(RUNTIME_BOUNDARY_FIELDS),
        "required_fields": list(RUNTIME_BOUNDARY_REQUIRED_FIELDS),
    }
