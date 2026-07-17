from __future__ import annotations

from collections.abc import Mapping
from typing import Any


AUTHORITY_CONTEXT_SCHEMA = "zero.runtime.authority_context.v1"

AUTHORITY_CONTEXT_FIELDS = (
    "authority_phase",
    "authority_layer",
    "authority_role",
    "authority_source",
    "authority_policy",
    "authority_propagation_required",
    "execution_authority_granted",
    "can_execute_privileged_step",
    "received_authority",
    "execution_authority",
    "authority_chain",
)

AUTHORITY_CONTEXT_REQUIRED_FIELDS = (
    "authority_phase",
    "authority_layer",
    "authority_role",
    "authority_source",
    "authority_policy",
    "authority_propagation_required",
    "execution_authority_granted",
    "can_execute_privileged_step",
    "authority_chain",
)

AUTHORITY_CONTEXT_BOOLEAN_FIELDS = (
    "authority_propagation_required",
    "execution_authority_granted",
    "can_execute_privileged_step",
)

AUTHORITY_CONTEXT_MAPPING_FIELDS = (
    "received_authority",
    "execution_authority",
)

AUTHORITY_CONTEXT_LIST_FIELDS = (
    "authority_chain",
)


def authority_context_field_set() -> set[str]:
    return set(AUTHORITY_CONTEXT_FIELDS)


def authority_context_required_field_set() -> set[str]:
    return set(AUTHORITY_CONTEXT_REQUIRED_FIELDS)


def is_authority_context_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def missing_authority_context_fields(value: Mapping[str, Any]) -> list[str]:
    return [
        field
        for field in AUTHORITY_CONTEXT_REQUIRED_FIELDS
        if field not in value
    ]


def validate_authority_context_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "ok": False,
            "schema": AUTHORITY_CONTEXT_SCHEMA,
            "reason": "authority_context_not_mapping",
            "missing_fields": list(AUTHORITY_CONTEXT_REQUIRED_FIELDS),
        }

    missing_fields = missing_authority_context_fields(value)
    if missing_fields:
        return {
            "ok": False,
            "schema": AUTHORITY_CONTEXT_SCHEMA,
            "reason": "authority_context_missing_required_fields",
            "missing_fields": missing_fields,
        }

    invalid_boolean_fields = [
        field
        for field in AUTHORITY_CONTEXT_BOOLEAN_FIELDS
        if not isinstance(value.get(field), bool)
    ]
    if invalid_boolean_fields:
        return {
            "ok": False,
            "schema": AUTHORITY_CONTEXT_SCHEMA,
            "reason": "authority_context_invalid_boolean_fields",
            "invalid_fields": invalid_boolean_fields,
        }

    invalid_mapping_fields = [
        field
        for field in AUTHORITY_CONTEXT_MAPPING_FIELDS
        if field in value and value.get(field) is not None and not isinstance(value.get(field), Mapping)
    ]
    if invalid_mapping_fields:
        return {
            "ok": False,
            "schema": AUTHORITY_CONTEXT_SCHEMA,
            "reason": "authority_context_invalid_mapping_fields",
            "invalid_fields": invalid_mapping_fields,
        }

    invalid_list_fields = [
        field
        for field in AUTHORITY_CONTEXT_LIST_FIELDS
        if not isinstance(value.get(field), list)
    ]
    if invalid_list_fields:
        return {
            "ok": False,
            "schema": AUTHORITY_CONTEXT_SCHEMA,
            "reason": "authority_context_invalid_list_fields",
            "invalid_fields": invalid_list_fields,
        }

    return {
        "ok": True,
        "schema": AUTHORITY_CONTEXT_SCHEMA,
        "reason": "authority_context_shape_valid",
    }


def authority_context_contract_summary() -> dict[str, Any]:
    return {
        "schema": AUTHORITY_CONTEXT_SCHEMA,
        "fields": list(AUTHORITY_CONTEXT_FIELDS),
        "required_fields": list(AUTHORITY_CONTEXT_REQUIRED_FIELDS),
        "boolean_fields": list(AUTHORITY_CONTEXT_BOOLEAN_FIELDS),
        "mapping_fields": list(AUTHORITY_CONTEXT_MAPPING_FIELDS),
        "list_fields": list(AUTHORITY_CONTEXT_LIST_FIELDS),
    }
