from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.runtime.runtime_ownership import can_access


@dataclass(frozen=True)
class RuntimeMutationRequest:
    owner: Any
    resource: Any
    action: Any
    allowed: bool
    reason: str | None = None
    metadata: Any = None
    rejected_reason: str | None = None


class RuntimeMutationRejected(PermissionError):
    def __init__(self, request: RuntimeMutationRequest) -> None:
        self.request = request
        super().__init__(request.rejected_reason)


class RuntimeMutationGuard:
    @staticmethod
    def validate(
        owner: Any,
        resource: Any,
        action: Any,
        reason: str | None = None,
        metadata: Any = None,
    ) -> RuntimeMutationRequest:
        return guard_mutation(
            owner=owner,
            resource=resource,
            action=action,
            reason=reason,
            metadata=metadata,
        )


def guard_mutation(
    owner: Any,
    resource: Any,
    action: Any,
    reason: str | None = None,
    metadata: Any = None,
) -> RuntimeMutationRequest:
    allowed = can_access(owner, resource, action)

    if allowed:
        return RuntimeMutationRequest(
            owner=owner,
            resource=resource,
            action=action,
            allowed=True,
            reason=reason,
            metadata=metadata,
            rejected_reason=None,
        )

    rejected_reason = (
        "runtime mutation rejected: "
        f"owner={owner!r}, resource={resource!r}, action={action!r}"
    )
    request = RuntimeMutationRequest(
        owner=owner,
        resource=resource,
        action=action,
        allowed=False,
        reason=reason,
        metadata=metadata,
        rejected_reason=rejected_reason,
    )
    raise RuntimeMutationRejected(request)
