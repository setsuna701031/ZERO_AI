"""Compatibility import for the dependency-neutral projection contract."""

from core.result_projection import (
    DEFAULT_RUNTIME_RESULT_PROJECTION_CONTRACT,
    ProjectionAdapterRegistry,
    ProjectionAdapterManifest,
    RUNTIME_RESULT_PROJECTION_ADAPTERS,
    RuntimeResultProjectionContract,
    bounded_json_projection,
    detach_internal_result,
    mapping_projection,
    project_result_for,
)

__all__ = [
    "DEFAULT_RUNTIME_RESULT_PROJECTION_CONTRACT",
    "ProjectionAdapterRegistry",
    "ProjectionAdapterManifest",
    "RUNTIME_RESULT_PROJECTION_ADAPTERS",
    "RuntimeResultProjectionContract",
    "bounded_json_projection",
    "detach_internal_result",
    "mapping_projection",
    "project_result_for",
]
