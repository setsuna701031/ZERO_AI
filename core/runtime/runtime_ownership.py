from __future__ import annotations

from enum import Enum
from typing import Any


class RuntimeOwner(str, Enum):
    SCHEDULER = "scheduler"
    STEP_EXECUTOR = "step_executor"
    ORCHESTRATOR = "orchestrator"
    REPAIR_CHAIN = "repair_chain"
    MONITOR = "monitor"
    SYSTEM = "system"


class RuntimeResource(str, Enum):
    QUEUE_STATE = "queue_state"
    EXECUTION_RESULT = "execution_result"
    RUNTIME_EVENT = "runtime_event"
    RUNTIME_INCIDENT = "runtime_incident"
    RUNTIME_SNAPSHOT = "runtime_snapshot"
    ORCHESTRATION_STATE = "orchestration_state"
    REPAIR_STATE = "repair_state"


class RuntimeAction(str, Enum):
    READ = "read"
    WRITE = "write"
    EMIT = "emit"
    TRANSITION = "transition"
    DISPATCH = "dispatch"
    SNAPSHOT = "snapshot"
    REPLAY = "replay"


class RuntimeAuthorityError(PermissionError):
    pass


AuthorityRule = tuple[RuntimeOwner, RuntimeResource, RuntimeAction]


_ALLOWED_RULES: frozenset[AuthorityRule] = frozenset(
    {
        (RuntimeOwner.SCHEDULER, RuntimeResource.QUEUE_STATE, RuntimeAction.WRITE),
        (RuntimeOwner.SCHEDULER, RuntimeResource.QUEUE_STATE, RuntimeAction.TRANSITION),
        (RuntimeOwner.SCHEDULER, RuntimeResource.EXECUTION_RESULT, RuntimeAction.READ),
        (RuntimeOwner.SCHEDULER, RuntimeResource.RUNTIME_EVENT, RuntimeAction.EMIT),
        (
            RuntimeOwner.STEP_EXECUTOR,
            RuntimeResource.EXECUTION_RESULT,
            RuntimeAction.WRITE,
        ),
        (RuntimeOwner.STEP_EXECUTOR, RuntimeResource.RUNTIME_EVENT, RuntimeAction.EMIT),
        (
            RuntimeOwner.STEP_EXECUTOR,
            RuntimeResource.RUNTIME_INCIDENT,
            RuntimeAction.EMIT,
        ),
        (RuntimeOwner.ORCHESTRATOR, RuntimeResource.QUEUE_STATE, RuntimeAction.READ),
        (
            RuntimeOwner.ORCHESTRATOR,
            RuntimeResource.EXECUTION_RESULT,
            RuntimeAction.READ,
        ),
        (
            RuntimeOwner.ORCHESTRATOR,
            RuntimeResource.ORCHESTRATION_STATE,
            RuntimeAction.DISPATCH,
        ),
        (RuntimeOwner.ORCHESTRATOR, RuntimeResource.RUNTIME_EVENT, RuntimeAction.EMIT),
        (
            RuntimeOwner.MONITOR,
            RuntimeResource.RUNTIME_SNAPSHOT,
            RuntimeAction.SNAPSHOT,
        ),
        (
            RuntimeOwner.REPAIR_CHAIN,
            RuntimeResource.EXECUTION_RESULT,
            RuntimeAction.READ,
        ),
        (
            RuntimeOwner.REPAIR_CHAIN,
            RuntimeResource.RUNTIME_INCIDENT,
            RuntimeAction.READ,
        ),
        (RuntimeOwner.REPAIR_CHAIN, RuntimeResource.REPAIR_STATE, RuntimeAction.WRITE),
        (RuntimeOwner.REPAIR_CHAIN, RuntimeResource.RUNTIME_EVENT, RuntimeAction.EMIT),
        (
            RuntimeOwner.REPAIR_CHAIN,
            RuntimeResource.RUNTIME_INCIDENT,
            RuntimeAction.EMIT,
        ),
    }
    | {
        (RuntimeOwner.MONITOR, resource, RuntimeAction.READ)
        for resource in RuntimeResource
    }
)


def _coerce_enum(enum_type: type[Enum], value: Any) -> Enum | None:
    if isinstance(value, enum_type):
        return value

    try:
        return enum_type(value)
    except ValueError:
        pass

    if isinstance(value, str):
        try:
            return enum_type[value]
        except KeyError:
            return None

    return None


def can_access(owner: Any, resource: Any, action: Any) -> bool:
    runtime_owner = _coerce_enum(RuntimeOwner, owner)
    runtime_resource = _coerce_enum(RuntimeResource, resource)
    runtime_action = _coerce_enum(RuntimeAction, action)

    if runtime_owner is None or runtime_resource is None or runtime_action is None:
        return False

    if runtime_owner is RuntimeOwner.SYSTEM:
        return True

    return (runtime_owner, runtime_resource, runtime_action) in _ALLOWED_RULES


def assert_runtime_authority(owner: Any, resource: Any, action: Any) -> None:
    if can_access(owner, resource, action):
        return

    raise RuntimeAuthorityError(
        f"runtime authority denied: owner={owner!r}, resource={resource!r}, action={action!r}"
    )
