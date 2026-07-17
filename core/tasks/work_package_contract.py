from __future__ import annotations

"""
ZERO Work Package Contract v6.4.

This module defines the operator-level work package contract.

Boundary:
- Contract/intake validation only.
- No scheduler execution.
- No repository mutation.
- Work package modes are explicit: explore / plan / execute / verify.

v6.4 closes the partial migration between the old workspace execution
contract and the v6.3 controlled core-write contract:
- one package-kind registry;
- one mode normalization path;
- execute-mode target validation is deferred to the execution guard so blocked
  execution returns a structured result instead of raising during contract
  validation.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.tasks.work_package_mode import WorkPackageMode


SCHEMA = "zero.work_package.v6_4"

SUPPORTED_PACKAGE_KINDS = frozenset(
    {
        "readonly_audit",
        "plan",
        "controlled_core_write_test",
    }
)
SUPPORTED_MODES = frozenset(mode.value for mode in WorkPackageMode)


class WorkPackageContractError(ValueError):
    """Raised when a work package does not satisfy the contract."""


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items: list[str] = []
        for item in value:
            text = _clean_text(item)
            if text:
                items.append(text)
        return items
    text = _clean_text(value)
    return [text] if text else []


def _normalize_relative_text(value: Any) -> str:
    return _clean_text(value).replace("\\", "/")


def _safe_relative_path(value: Any, *, field_name: str) -> str:
    text = _normalize_relative_text(value)
    if not text:
        raise WorkPackageContractError(f"{field_name}_required")

    candidate = Path(text)
    if candidate.is_absolute():
        raise WorkPackageContractError(f"{field_name}_must_be_relative")

    parts = candidate.parts
    if any(part in ("..", "") for part in parts):
        raise WorkPackageContractError(f"{field_name}_must_not_escape_repo")

    return text


def _execute_scope_path(value: Any, *, field_name: str) -> str:
    """
    Normalize execute-mode scope paths without blocking path-escape cases here.

    Execute-mode mutation safety belongs to the execution guard, not the contract
    parser. This keeps operator-facing blocked writes as structured intake
    results instead of leaking validation exceptions before policy/evidence code
    can run.
    """

    text = _normalize_relative_text(value)
    if not text:
        raise WorkPackageContractError(f"{field_name}_required")
    if Path(text).is_absolute():
        raise WorkPackageContractError(f"{field_name}_must_be_relative")
    return text


def _normalize_mode(value: Any) -> WorkPackageMode:
    text = _clean_text(value or WorkPackageMode.EXPLORE.value).lower()
    try:
        return WorkPackageMode(text)
    except ValueError as exc:
        raise WorkPackageContractError(f"unsupported_work_package_mode:{text}") from exc


@dataclass(frozen=True)
class WorkPackageRequest:
    """Validated operator work package request."""

    package_id: str
    kind: str
    title: str
    scope_paths: tuple[str, ...]
    mode: WorkPackageMode = WorkPackageMode.EXPLORE
    markers: tuple[str, ...] = field(default_factory=tuple)
    report_path: str = "workspace/work_package_report.md"
    instructions: str = ""
    approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def readonly(self) -> bool:
        return self.mode in {
            WorkPackageMode.EXPLORE,
            WorkPackageMode.PLAN,
            WorkPackageMode.VERIFY,
        }

    @property
    def mutation_allowed(self) -> bool:
        return self.mode == WorkPackageMode.EXECUTE and self.approval

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "package_id": self.package_id,
            "kind": self.kind,
            "title": self.title,
            "mode": self.mode.value,
            "scope_paths": list(self.scope_paths),
            "markers": list(self.markers),
            "report_path": self.report_path,
            "instructions": self.instructions,
            "approval": self.approval,
            "readonly": self.readonly,
            "mutation_allowed": self.mutation_allowed,
            "metadata": dict(self.metadata),
        }


DEFAULT_READONLY_AUDIT_MARKERS: tuple[str, ...] = (
    "previous_result",
    "last_step_result",
    "except TypeError",
    "fallback",
    "legacy",
    "adapter",
    "compatibility",
    "chat(",
    "generate(",
    "ask(",
)


def validate_work_package_request(payload: Mapping[str, Any]) -> WorkPackageRequest:
    """Validate and normalize a work package request."""

    if not isinstance(payload, Mapping):
        raise WorkPackageContractError("work_package_payload_must_be_mapping")

    kind = _clean_text(payload.get("kind") or payload.get("package_kind") or "readonly_audit")
    if kind not in SUPPORTED_PACKAGE_KINDS:
        raise WorkPackageContractError(f"unsupported_work_package_kind:{kind}")

    mode = _normalize_mode(payload.get("mode"))

    package_id = _clean_text(payload.get("package_id") or payload.get("id") or "work_package")
    if not package_id:
        raise WorkPackageContractError("package_id_required")

    title = _clean_text(payload.get("title") or package_id)
    if not title:
        raise WorkPackageContractError("title_required")

    raw_paths = payload.get("scope_paths")
    if raw_paths is None:
        raw_paths = payload.get("paths")
    scope_path_parser = _execute_scope_path if mode == WorkPackageMode.EXECUTE else _safe_relative_path
    scope_paths = tuple(
        scope_path_parser(path, field_name="scope_path") for path in _clean_list(raw_paths)
    )
    if not scope_paths:
        raise WorkPackageContractError("scope_paths_required")

    markers = tuple(_clean_list(payload.get("markers")))
    if not markers:
        markers = DEFAULT_READONLY_AUDIT_MARKERS

    report_path = _safe_relative_path(
        payload.get("report_path") or "workspace/work_package_report.md",
        field_name="report_path",
    )

    instructions = _clean_text(payload.get("instructions"))
    approval = bool(payload.get("approval") or payload.get("approved"))

    metadata = payload.get("metadata")
    if metadata is None:
        metadata_dict: dict[str, Any] = {}
    elif isinstance(metadata, Mapping):
        metadata_dict = dict(metadata)
    else:
        raise WorkPackageContractError("metadata_must_be_mapping")

    return WorkPackageRequest(
        package_id=package_id,
        kind=kind,
        title=title,
        scope_paths=tuple(str(path) for path in scope_paths if str(path).strip()),
        mode=mode,
        markers=tuple(str(marker) for marker in markers if str(marker).strip()),
        report_path=report_path,
        instructions=instructions,
        approval=approval,
        metadata=metadata_dict,
    )


def readonly_legacy_audit_package(
    *,
    package_id: str = "legacy_path_audit",
    scope_paths: Sequence[str],
    report_path: str = "workspace/legacy_path_audit.md",
    title: str = "Read-only legacy path audit",
    instructions: str = "",
    mode: str | WorkPackageMode = WorkPackageMode.EXPLORE,
) -> WorkPackageRequest:
    """Convenience constructor for the hidden-path audit use case."""

    mode_value = mode.value if isinstance(mode, WorkPackageMode) else str(mode)
    return validate_work_package_request(
        {
            "package_id": package_id,
            "kind": "readonly_audit",
            "mode": mode_value,
            "title": title,
            "scope_paths": list(scope_paths),
            "markers": list(DEFAULT_READONLY_AUDIT_MARKERS),
            "report_path": report_path,
            "instructions": instructions,
            "approval": False,
            "metadata": {
                "readonly": True,
                "mutation_allowed": False,
                "full_pytest_allowed": False,
            },
        }
    )


__all__ = [
    "DEFAULT_READONLY_AUDIT_MARKERS",
    "SCHEMA",
    "SUPPORTED_MODES",
    "SUPPORTED_PACKAGE_KINDS",
    "WorkPackageContractError",
    "WorkPackageRequest",
    "readonly_legacy_audit_package",
    "validate_work_package_request",
]
