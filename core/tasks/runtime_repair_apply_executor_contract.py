from __future__ import annotations

import hashlib
import json

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_repair_transaction_state_machine import (
    build_runtime_repair_transaction_transition,
)

from core.tasks.runtime_state_hygiene import (
    freeze_runtime_export,
    make_json_safe,
)


RUNTIME_REPAIR_APPLY_EXECUTOR_CONTRACT_TYPE = (
    "runtime_repair_apply_executor_contract"
)

RUNTIME_REPAIR_APPLY_EXECUTOR_CONTRACT_VERSION = (
    "runtime_repair_apply_executor_contract.v1"
)


def build_runtime_repair_apply_executor_contract(
    controlled_apply: Any,
) -> Dict[str, Any]:
    """
    Deterministic execution contract layer.

    This layer NEVER:
    - writes files
    - applies patches
    - executes shell commands
    - mutates runtime state
    - schedules tasks

    It only creates:
    - executor contract
    - execution receipt
    - rollback receipt
    - execution audit payload
    """

    apply_data = (
        controlled_apply
        if isinstance(
            controlled_apply,
            Mapping,
        )
        else {}
    )

    apply_plan = (
        apply_data.get("apply_plan")
        if isinstance(
            apply_data.get(
                "apply_plan"
            ),
            Mapping,
        )
        else {}
    )

    rollback_plan = (
        apply_data.get("rollback_plan")
        if isinstance(
            apply_data.get(
                "rollback_plan"
            ),
            Mapping,
        )
        else {}
    )

    current_state = _safe_text(
        apply_data.get(
            "current_state"
        )
    )

    target_state = _safe_text(
        apply_data.get(
            "target_state"
        )
    )

    transition = (
        build_runtime_repair_transaction_transition(
            transaction_id=apply_data.get(
                "transaction_id"
            ),
            task_id=apply_data.get(
                "task_id"
            ),
            proposal_id=apply_data.get(
                "proposal_id"
            ),
            current_state=current_state,
            next_state=target_state,
            reason=(
                "controlled_apply_executor_contract"
            ),
        )
    )

    contract_id = (
        _build_executor_contract_id(
            apply_data
        )
    )

    execution_receipt = (
        build_runtime_repair_execution_receipt(
            apply_data,
            contract_id=contract_id,
        )
    )

    rollback_receipt = (
        build_runtime_repair_rollback_receipt(
            apply_data,
            contract_id=contract_id,
        )
    )

    audit_payload = (
        build_runtime_repair_execution_audit_payload(
            apply_data,
            execution_receipt=execution_receipt,
            rollback_receipt=rollback_receipt,
        )
    )

    result = {
        "contract_type": (
            RUNTIME_REPAIR_APPLY_EXECUTOR_CONTRACT_TYPE
        ),
        "contract_version": (
            RUNTIME_REPAIR_APPLY_EXECUTOR_CONTRACT_VERSION
        ),
        "contract_id": contract_id,
        "transaction_id": _safe_text(
            apply_data.get(
                "transaction_id"
            )
        ),
        "task_id": _safe_text(
            apply_data.get(
                "task_id"
            )
        ),
        "proposal_id": _safe_text(
            apply_data.get(
                "proposal_id"
            )
        ),
        "execution_allowed": False,
        "real_mutation_allowed": False,
        "shell_execution_allowed": False,
        "filesystem_write_allowed": False,
        "dry_run_only": True,
        "apply_allowed": bool(
            apply_data.get(
                "apply_allowed"
            )
        ),
        "state_transition": (
            freeze_runtime_export(
                transition
            )
        ),
        "apply_plan": (
            freeze_runtime_export(
                apply_plan
            )
        ),
        "rollback_plan": (
            freeze_runtime_export(
                rollback_plan
            )
        ),
        "execution_receipt": (
            freeze_runtime_export(
                execution_receipt
            )
        ),
        "rollback_receipt": (
            freeze_runtime_export(
                rollback_receipt
            )
        ),
        "execution_audit_payload": (
            freeze_runtime_export(
                audit_payload
            )
        ),
        "human_summary": (
            build_runtime_repair_executor_summary(
                apply_data
            )
        ),
    }

    return freeze_runtime_export(
        result
    )


def build_runtime_repair_execution_receipt(
    controlled_apply: Mapping[str, Any],
    *,
    contract_id: str,
) -> Dict[str, Any]:
    apply_plan = (
        controlled_apply.get(
            "apply_plan"
        )
        if isinstance(
            controlled_apply.get(
                "apply_plan"
            ),
            Mapping,
        )
        else {}
    )

    return freeze_runtime_export(
        {
            "receipt_type": (
                "runtime_repair_execution_receipt"
            ),
            "contract_id": contract_id,
            "execution_status": (
                "dry_run_only"
            ),
            "mutation_count": (
                apply_plan.get(
                    "mutation_count",
                    0,
                )
            ),
            "execution_performed": False,
            "filesystem_modified": False,
            "commands_executed": False,
        }
    )


def build_runtime_repair_rollback_receipt(
    controlled_apply: Mapping[str, Any],
    *,
    contract_id: str,
) -> Dict[str, Any]:
    rollback_plan = (
        controlled_apply.get(
            "rollback_plan"
        )
        if isinstance(
            controlled_apply.get(
                "rollback_plan"
            ),
            Mapping,
        )
        else {}
    )

    return freeze_runtime_export(
        {
            "receipt_type": (
                "runtime_repair_rollback_receipt"
            ),
            "contract_id": contract_id,
            "rollback_status": (
                "not_required"
            ),
            "rollback_step_count": (
                rollback_plan.get(
                    "rollback_step_count",
                    0,
                )
            ),
            "rollback_performed": False,
        }
    )


def build_runtime_repair_execution_audit_payload(
    controlled_apply: Mapping[str, Any],
    *,
    execution_receipt: Mapping[str, Any],
    rollback_receipt: Mapping[str, Any],
) -> Dict[str, Any]:
    return freeze_runtime_export(
        {
            "audit_type": (
                "runtime_repair_execution_audit"
            ),
            "transaction_id": _safe_text(
                controlled_apply.get(
                    "transaction_id"
                )
            ),
            "task_id": _safe_text(
                controlled_apply.get(
                    "task_id"
                )
            ),
            "proposal_id": _safe_text(
                controlled_apply.get(
                    "proposal_id"
                )
            ),
            "execution_receipt": (
                freeze_runtime_export(
                    execution_receipt
                )
            ),
            "rollback_receipt": (
                freeze_runtime_export(
                    rollback_receipt
                )
            ),
            "dry_run_only": True,
            "execution_allowed": False,
        }
    )


def build_runtime_repair_executor_summary(
    controlled_apply: Mapping[str, Any],
) -> str:
    apply_allowed = bool(
        controlled_apply.get(
            "apply_allowed"
        )
    )

    if apply_allowed:
        return (
            "Executor contract prepared. "
            "Execution remains disabled."
        )

    blocked = (
        controlled_apply.get(
            "blocked_reasons"
        )
        if isinstance(
            controlled_apply.get(
                "blocked_reasons"
            ),
            list,
        )
        else []
    )

    if not blocked:
        return (
            "Executor contract blocked."
        )

    return (
        "Executor contract blocked: "
        + ", ".join(
            sorted(
                list(
                    set(
                        str(x)
                        for x in blocked
                    )
                )
            )
        )
    )


def _build_executor_contract_id(
    controlled_apply: Mapping[str, Any],
) -> str:
    payload = {
        "transaction_id": (
            controlled_apply.get(
                "transaction_id"
            )
        ),
        "task_id": (
            controlled_apply.get(
                "task_id"
            )
        ),
        "proposal_id": (
            controlled_apply.get(
                "proposal_id"
            )
        ),
        "current_state": (
            controlled_apply.get(
                "current_state"
            )
        ),
        "target_state": (
            controlled_apply.get(
                "target_state"
            )
        ),
    }

    encoded = json.dumps(
        make_json_safe(payload),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    digest = hashlib.sha1(
        encoded.encode(
            "utf-8"
        )
    ).hexdigest()[:12]

    transaction_id = _safe_text(
        controlled_apply.get(
            "transaction_id"
        )
    ) or "unknown"

    return (
        f"runtime_executor:"
        f"{transaction_id}:"
        f"{digest}"
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()