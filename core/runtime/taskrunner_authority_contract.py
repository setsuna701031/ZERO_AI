"""Canonical TaskRunner authority-context propagation contract."""

from __future__ import annotations

import copy
from typing import Any, Callable, Mapping

from core.goals.goal_lineage_contract import extract_goal_lineage
from core.runtime.runtime_execution_authority import propagate_runtime_capability


AUTHORITY_PROPAGATION_DOMAINS = (
    "authority_context",
    "runtime_session",
    "goal_lineage",
    "continuation_chain",
    "repair_chain",
)


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_value(sources: tuple[Mapping[str, Any], ...], *keys: str) -> Any:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return copy.deepcopy(value)
    return None


def _incoming_authority_context(sources: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    for source in sources:
        for key in ("authority_context", "runtime_authority_context"):
            value = source.get(key)
            if isinstance(value, Mapping):
                return _mapping(value)
    return {}


def _propagation_domains(sources: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    propagated: dict[str, Any] = {}
    identity = _first_value(sources, "runtime_identity")
    identity_graph = _first_value(sources, "runtime_identity_graph")
    if identity is not None:
        propagated["runtime_identity"] = identity
    if identity_graph is not None:
        propagated["runtime_identity_graph"] = identity_graph

    lineage: dict[str, Any] = {}
    for source in sources:
        try:
            candidate = extract_goal_lineage(source)
        except (TypeError, ValueError):
            candidate = {}
        if candidate.get("goal_lineage_id") and candidate.get("branch_id"):
            lineage = copy.deepcopy(candidate)
            break
    if lineage:
        propagated["goal_lineage"] = lineage

    for key in (
        "session_id",
        "runtime_session_id",
        "operator_session_id",
        "persistent_operator_session_id",
        "continuation_id",
        "parent_continuation_id",
        "continuation_chain",
        "continuation_lineage",
        "repair_chain_id",
        "repair_context",
    ):
        value = _first_value(sources, key)
        if value is not None:
            propagated[key] = value
    return propagated


def build_taskrunner_authority_context(
    *,
    task: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
    step: Mapping[str, Any] | None,
    upstream_context: Mapping[str, Any] | None,
    issuer_token: object,
    delegate_capability: Callable[..., Any],
) -> dict[str, Any]:
    """Propagate dispatcher authority without creating an execution grant.

    Runtime identity, session, goal lineage, continuation, and repair-chain
    metadata travel with the canonical capability. TaskRunner remains a
    delegate; StepExecutor remains the execution authority endpoint.
    """

    task_payload = _mapping(task)
    state_payload = _mapping(state)
    step_payload = _mapping(step)
    upstream_payload = _mapping(upstream_context)
    sources = (task_payload, state_payload, upstream_payload)
    incoming = _incoming_authority_context(sources)
    domains = _propagation_domains((incoming, *sources))

    dispatch_capability = _first_value(
        sources,
        "runtime_execution_capability",
    )
    system_capability = _first_value(sources, "runtime_system_capability")
    capability_provenance = _first_value(sources, "runtime_capability_provenance")
    propagated_capability: dict[str, Any] = {}
    if capability_provenance is not None:
        propagated_capability = propagate_runtime_capability(
            incoming,
            capability_provenance,
            stage="runtime",
        )

    task_id = _text(
        task_payload.get("task_id")
        or task_payload.get("id")
        or state_payload.get("task_id")
    )
    step_id = _text(
        step_payload.get("id")
        or step_payload.get("step_id")
        or f"{task_id}:step"
    )

    common = {
        **propagated_capability,
        **domains,
        "authority_layer": "task_runner",
        "authority_propagation_required": True,
        "execution_authority_granted": False,
        "escalated": False,
        "received_authority": copy.deepcopy(incoming),
        "runtime_system_capability": system_capability,
    }
    try:
        capability = delegate_capability(
            issuer_token,
            dispatch_capability,
            task_id=task_id,
            step_id=step_id,
        )
    except PermissionError:
        return {
            **common,
            "authority_phase": "taskrunner_propagation",
            "authority_role": "propagation",
            "authority_source": "",
            "authority_policy": "canonical_runtime_dispatch_capability_required",
            "can_execute_privileged_step": False,
            "execution_authority": {},
            "authority_chain": [],
        }

    step_type = _text(step_payload.get("type") or step_payload.get("action")).lower()
    return {
        **common,
        "authority_phase": "taskrunner_delegation",
        "authority_role": "canonical_delegation",
        "authority_source": "runtime_dispatcher",
        "authority_policy": "owner_issued_runtime_execution_capability",
        "execution_authority_propagated": True,
        "can_execute_privileged_step": True,
        "runtime_execution_capability": capability,
        "execution_authority": {
            "task_id": task_id,
            "step_id": step_id,
            "authority_source": "runtime_dispatcher",
            "authority_status": "allowed",
            "execution_authority_endpoint": "step_executor",
            "action_type": "execute" if step_type in {"command", "run_python"} else "mutation",
            "runtime_session": capability.session_id,
            "approval_state": "approved",
            "policy_result": {"allowed": True, "source": "task_runner_live_capability"},
            "trace_id": f"taskrunner:{task_id}:{step_id}",
            "descriptive_only": True,
        },
        "authority_chain": copy.deepcopy(incoming.get("authority_chain", [])) + [
            {
                "layer": "task_runner",
                "authority_role": "canonical_delegation",
                "execution_authority_propagated": True,
                "execution_authority_granted": False,
                "can_execute_privileged_step": True,
            }
        ],
    }


__all__ = ["AUTHORITY_PROPAGATION_DOMAINS", "build_taskrunner_authority_context"]
