from __future__ import annotations

from enum import Enum
from typing import Any

from core.runtime.runtime_system_capability import (
    RuntimeCapabilityClass,
    SYSTEM_CAPABILITY_INVENTORY,
)


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

# Public inventory aliases keep policy review in the ownership module while
# token issuance and validation remain isolated in runtime_system_capability.
SYSTEM_PERMISSION_CLASSES = RuntimeCapabilityClass
SYSTEM_EXPLICIT_CAPABILITIES = SYSTEM_CAPABILITY_INVENTORY


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

# SYSTEM is retained as a metadata/bootstrapping owner, but it is no longer a
# wildcard policy authority. SYSTEM can only perform explicitly listed
# low-risk observability operations. Any runtime mutation, transition, dispatch,
# or execution-result write must be performed by the concrete runtime owner or
# by a live capability/token authority in the domain-specific authority modules.
_SYSTEM_ALLOWED_RULES: frozenset[AuthorityRule] = frozenset(
    (RuntimeOwner.SYSTEM, RuntimeResource(resource), RuntimeAction(action))
    for capability_class in (RuntimeCapabilityClass.READ, RuntimeCapabilityClass.WRITE)
    for resource, action in SYSTEM_CAPABILITY_INVENTORY[capability_class]
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


def system_authority_rules() -> frozenset[AuthorityRule]:
    """Return the explicitly scoped SYSTEM policy rules.

    This is intentionally narrow and inspectable. Do not replace it with a
    blanket SYSTEM bypass; SYSTEM metadata identities are not policy authority.
    """
    return _SYSTEM_ALLOWED_RULES


def can_access(owner: Any, resource: Any, action: Any) -> bool:
    runtime_owner = _coerce_enum(RuntimeOwner, owner)
    runtime_resource = _coerce_enum(RuntimeResource, resource)
    runtime_action = _coerce_enum(RuntimeAction, action)

    if runtime_owner is None or runtime_resource is None or runtime_action is None:
        return False

    rule = (runtime_owner, runtime_resource, runtime_action)
    if runtime_owner is RuntimeOwner.SYSTEM:
        return rule in _SYSTEM_ALLOWED_RULES

    return rule in _ALLOWED_RULES


def assert_runtime_authority(owner: Any, resource: Any, action: Any) -> None:
    if can_access(owner, resource, action):
        return

    raise RuntimeAuthorityError(
        f"runtime authority denied: owner={owner!r}, resource={resource!r}, action={action!r}"
    )
