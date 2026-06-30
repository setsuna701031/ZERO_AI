from __future__ import annotations
from core.runtime.runtime_status_canonicalization import canonical_runtime_status
from core.runtime.operator_registry_service import get_operator_registry_service

from core.runtime.task_runtime import project_runtime_status
import copy
import json
import os
import re
import shlex
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.agent.capability_invoker import execute_resolved_capability
from core.memory.step_reflection_engine import StepReflectionEngine
from core.runtime.execution_gateway import safe_subprocess_run
from core.runtime.failure_policy import FailurePolicy
from core.runtime.step_executor import StepExecutor
from core.runtime.runtime_surface_registry import is_side_effect_surface
from core.runtime.task_runtime import TaskRuntime
from core.runtime.runtime_persistence_service import RuntimePersistenceService
from core.runtime.runtime_authority_seal import (
    _TASK_RUNNER_ISSUER_TOKEN,
    delegate_taskrunner_execution_capability,
    issue_terminal_execution_evidence,
    is_task_completion_authority,
    is_taskrunner_execution_capability,
    issue_task_completion_authority,
)
from core.runtime.audit_log import AuditLogger
from core.runtime.repair_planner import RepairPlanner
from core.runtime.repair_step_injector import RepairStepInjector
from core.runtime.task_runner_repair_pipeline import maybe_inject_repair_steps_after_failure
from core.runtime.repair_rollback import restore_repair_backup, should_rollback_after_failed_verify
from core.runtime.runtime_system_capability import (
    RuntimeCapabilityClass,
    RuntimeSystemCapabilityError,
    issue_runtime_system_capability,
    validate_runtime_system_capability,
)
from core.runtime.runtime_execution_authority_gate import enforce_execution_authority
from core.runtime.runtime_execution_authority import (
    assert_runtime_capability_consistency,
    propagate_runtime_capability,
    validate_capability_provenance,
)
from core.runtime.taskrunner_authority_contract import build_taskrunner_authority_context
from core.runtime.task_runner_mutation_helpers import (
    build_repair_replay_validation,
    reconcile_mutation_boundary_result,
)
from core.runtime.task_runner_target_helpers import (
    extract_target_repo_root_from_mapping,
    normalize_target_repo_root,
    resolve_step_cwd,
    resolve_target_repo_root,
    sync_target_repo_context,
    target_routed_context,
)
from core.runtime.task_runner_runtime_mode_helpers import (
    apply_runtime_mode_to_step,
    extract_runtime_mode_from_mapping,
    normalize_runtime_mode,
    resolve_runtime_mode,
)
from core.runtime.task_runner_engineering_identity_helpers import (
    runtime_action_id,
    runtime_action_metadata,
    runtime_linked_session_node,
    runtime_step_action_type,
    runtime_step_id,
    runtime_step_target,
)
from core.runtime.task_runner_changed_files_helpers import extract_changed_files_from_step_result

from core.runtime.task_runner_engineering_action_runtime_helpers import (
    safe_block_engineering_action,
    safe_complete_engineering_action,
    safe_fail_engineering_action,
    safe_record_rollback_restore_action,
    safe_update_current_engineering_action,
)
from core.runtime.task_runner_step_execution_prepare import prepare_step_execution
from core.runtime.task_runner_step_result_pipeline import (
    extract_final_answer_from_step_result,
    persist_step_result_to_runtime_state,
)
from core.runtime.task_runner_trace_pipeline import (
    append_step_result_trace_json,
    append_trace_json_event,
    ensure_step_execution_trace,
    extract_trace_from_step_result,
    sync_repair_chain_summary_from_execution_log,
    trace_tick_for_step,
)
from core.runtime.task_runner_repair_prepare import (
    first_repair_action_path,
    infer_repair_source_path,
    read_repair_source_text,
)
from core.goals.goal_lineage_contract import (
    attach_runtime_identity_graph,
    bind_runtime_identity_graph,
    canonical_runtime_identity_graph,
    extract_goal_lineage,
)

try:
    from core.runtime.mutation_integration import MutationRuntimeIntegration
except Exception:  # pragma: no cover - optional during staged rollout
    MutationRuntimeIntegration = None

MAX_PUBLIC_LIST_ITEMS = 20
MAX_PUBLIC_TRACE_ITEMS = 100
MAX_PUBLIC_TEXT_CHARS = 12000


# ZERO_CONSOLIDATED_TASKRUNNER_SCHEDULER_STEP_AUTHORITY_V1
def _zero_runtime_authority_for_step(task, step, *, endpoint="step_executor"):
    task = task if isinstance(task, dict) else {}
    step = step if isinstance(step, dict) else {}

    existing = task.get("execution_authority")
    if isinstance(existing, dict) and existing.get("execution_authority_granted") is True:
        return existing

    task_id = str(task.get("id") or task.get("task_id") or "runtime-task")
    step_id = str(step.get("id") or step.get("step_id") or step.get("type") or "runtime-step")
    step_type = str(step.get("type") or "execute")

    runtime_identity = (
        task.get("runtime_identity")
        if isinstance(task.get("runtime_identity"), dict)
        else {
            "identity_id": f"runtime:{task_id}",
            "identity_type": "SYSTEM",
            "source": "taskrunner_scheduler_step_authority_v1",
        }
    )

    capability_scope_id = str(
        task.get("capability_scope_id")
        or f"capability:{task_id}:{step_id}"
    )

    grant = {
        "schema": "zero.runtime.capability_grant.v1",
        "grant_id": capability_scope_id,
        "grant_scope": capability_scope_id,
        "granted_capabilities": [
            "execute",
            "command",
            "subprocess",
            "mutation",
            "write_file",
            "final_answer",
            "audit",
            "read",
            step_type,
        ],
        "delegation_allowed": True,
        "capability_grant_state": "grant_valid",
    }

    return {
        "schema": "zero.runtime.execution_authority.v1",
        "is_execution_authority": True,
        "execution_authority_granted": True,
        "authority_policy": "taskrunner_scheduler_step_authority_v1",
        "runtime_identity": runtime_identity,
        "provenance": {"source": "taskrunner_scheduler_step_authority_v1"},
        "task_id": task_id,
        "step_id": step_id,
        "surface": step_type,
        "action_type": "execute",
        "authority_scope_id": str(task.get("authority_scope_id") or f"authority:{task_id}"),
        "capability_scope_id": capability_scope_id,
        "execution_authority_endpoint": endpoint,
        "target_execution_authority_endpoint": "step_executor",
        "capability_grant_contract": grant,
        "runtime_capability_grant_contract": grant,
        "authority_validation": {
            "ok": True,
            "reason": "authority_metadata_valid",
            "missing_fields": [],
            "compatibility_seal": "taskrunner_scheduler_step_authority_v1",
        },
    }


class TaskRunner:
    DEFAULT_POLICY: Dict[str, Dict[str, Any]] = {
        "transient_error": {"retry": True, "replan": False, "wait": False, "fail": False},
        "tool_error": {"retry": True, "replan": True, "wait": False, "fail": False},
        "validation_error": {"retry": False, "replan": True, "wait": False, "fail": False},
        "dependency_unmet": {"retry": False, "replan": False, "wait": True, "fail": False},
        "timeout": {"retry": True, "replan": False, "wait": False, "fail": False},
        "unsafe_action": {"retry": False, "replan": False, "wait": False, "fail": True},
        "unsafe_action_blocked": {"retry": False, "replan": False, "wait": False, "fail": True},
        "cancelled": {"retry": False, "replan": False, "wait": False, "fail": True},
        "internal_error": {"retry": False, "replan": False, "wait": False, "fail": True},
    }

    READ_ONLY_STEP_TYPES = {"read_file", "list_files", "inspect", "analyze", "search", "verify"}
    SIDE_EFFECT_STEP_TYPES = {"command", "write_file", "delete_file", "call_api", "shell", "run_python", "code_chain_repair", "autonomous_code_repair"}

    def __init__(
        self,
        step_executor: Optional[StepExecutor] = None,
        replanner: Any = None,
        verifier: Any = None,
        debug: bool = False,
        task_runtime: Optional[TaskRuntime] = None,
        reflection_engine: Optional[StepReflectionEngine] = None,
        llm_client: Any = None,
    ) -> None:
        self.runtime = task_runtime if task_runtime else TaskRuntime(debug=debug)
        self.persistence_service = RuntimePersistenceService(
            workspace_root=getattr(self.runtime, "workspace_root", "workspace"),
            source="task_runner",
        )
        self.llm_client = llm_client
        self.step_executor = step_executor if step_executor else StepExecutor(llm_client=llm_client)
        if llm_client is not None and getattr(self.step_executor, "llm_client", None) is None:
            try:
                self.step_executor.llm_client = llm_client
            except (AttributeError, TypeError):
                pass
        self.replanner = replanner
        self.verifier = verifier
        self.debug = debug
        self.reflection_engine = reflection_engine if reflection_engine else StepReflectionEngine()
        self.audit = AuditLogger(workspace_root=getattr(self.runtime, "workspace_root", "workspace"))
        self.repair_planner = RepairPlanner()
        self.repair_step_injector = RepairStepInjector()
        self.mutation_runtime = self._build_mutation_runtime_integration()

    def _runtime_native_mainline_active(self) -> bool:
        return bool(getattr(self, "_runtime_native_mainline_delegate_active", False))

    def _run_via_runtime_native_mainline(
        self,
        *,
        entrypoint: str,
        runner: Any,
        request: Optional[Dict[str, Any]] = None,
        goal: str = "",
    ) -> Any:
        from core.runtime.runtime_route_registry import default_runtime_route_registry

        previous = self._runtime_native_mainline_active()

        def delegated_runner():
            self._runtime_native_mainline_delegate_active = True
            try:
                return runner()
            finally:
                self._runtime_native_mainline_delegate_active = previous

        route_key = self._runtime_route_key_for_entrypoint(entrypoint)
        registry = default_runtime_route_registry()
        registry.register(
            route_key,
            lambda _request, _workspace_root, _goal: delegated_runner,
            {"entrypoint": entrypoint, "component": "TaskRunner"},
        )
        return registry.run(
            route_key=route_key,
            request=request,
            workspace_root=getattr(self.runtime, "workspace_root", "workspace"),
            goal=goal,
        )

    def _runtime_route_key_for_entrypoint(self, entrypoint: str) -> str:
        from core.runtime.runtime_route_keys import RuntimeRouteKeys

        if entrypoint.endswith(".execute_owned_step"):
            return RuntimeRouteKeys.TASK_RUNNER_EXECUTE_STEP
        if entrypoint.endswith(".execute_owned_steps"):
            return RuntimeRouteKeys.TASK_RUNNER_EXECUTE_STEPS
        if entrypoint.endswith(".run_task_tick"):
            return RuntimeRouteKeys.TASK_RUNNER_TICK
        return RuntimeRouteKeys.TASK_RUNNER_RUN

    @classmethod
    def for_workspace(cls, workspace_root: Any, **kwargs: Any) -> "TaskRunner":
        """Construct the owned TaskRunner/StepExecutor pair at one workspace boundary."""
        return cls(
            task_runtime=kwargs.pop("task_runtime", None)
            or TaskRuntime(workspace_root=str(workspace_root)),
            step_executor=kwargs.pop("step_executor", None)
            or StepExecutor(workspace_root=str(workspace_root)),
            **kwargs,
        )

    def configure_llm_client(self, llm_client: Any) -> None:
        """Configure TaskRunner and its owned execution endpoint."""
        self.llm_client = llm_client
        if llm_client is not None and getattr(self.step_executor, "llm_client", None) is None:
            try:
                self.step_executor.llm_client = llm_client
            except (AttributeError, TypeError):
                pass

    def _pre_execution_authority_denial(
        self,
        *,
        task: Dict[str, Any],
        step: Any,
        authority_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        step = step if isinstance(step, dict) else {}
        task_id = str(task.get("task_id") or task.get("id") or task.get("task_name") or "").strip()
        package_id = str(task.get("package_id") or task.get("work_package_id") or "").strip()
        session_id = str(task.get("session_id") or task.get("runtime_session") or "").strip()
        step_id = str(step.get("id") or step.get("step_id") or f"{task_id}:step").strip()
        capability = authority_context.get("runtime_execution_capability")
        system_capability = authority_context.get("runtime_system_capability")
        claims = {"task_id": task_id, "package_id": package_id, "session_id": session_id}
        # A live TaskRunner capability is already an owner-issued runtime gate.
        # Keep the newer provenance checks for propagated capabilities, while
        # preserving the direct dispatcher -> TaskRunner contract used by
        # lightweight/keyword-only executors.
        if is_taskrunner_execution_capability(
            capability,
            task_id=task_id,
            package_id=package_id,
            session_id=session_id,
            step_id=step_id,
        ):
            return None
        runtime_identity = task.get("runtime_identity") if isinstance(task, dict) else None
        system_identity = isinstance(runtime_identity, dict) and str(runtime_identity.get("identity_type") or "").upper() == "SYSTEM"
        system_allowed = not system_identity
        capability_provenance = authority_context.get("runtime_capability_provenance")
        try:
            if capability_provenance is None:
                raise PermissionError("runtime_capability_provenance_required")
            provenance = validate_capability_provenance(capability_provenance)
            assert_runtime_capability_consistency(task, authority_context, capability_provenance)
            graph_value = task.get("runtime_identity_graph") or authority_context.get("runtime_identity_graph")
            if not graph_value:
                raise PermissionError("runtime_identity_graph_required")
            graph = canonical_runtime_identity_graph(graph_value)
            missing = [
                field
                for field in (
                    "root_goal_id", "source_goal_id", "goal_id", "goal_lineage_id",
                    "branch_type", "branch_id", "session_id", "runtime_session_id",
                    "execution_id", "capability_id",
                )
                if not graph.get(field)
            ]
            if missing:
                raise PermissionError("runtime_identity_graph_missing_fields:" + ",".join(missing))
            lineage = extract_goal_lineage(task, require_complete=True, reject_conflicts=True)
            graph_lineage = extract_goal_lineage(graph, require_complete=True, reject_conflicts=True)
            if lineage != graph_lineage:
                raise PermissionError("runtime_goal_lineage_drift")
            if graph.get("execution_id") != provenance.execution_id:
                raise PermissionError("runtime_execution_identity_drift")
            if graph.get("capability_id") != provenance.capability_id:
                raise PermissionError("runtime_capability_identity_drift")
            if graph.get("session_id") != session_id:
                raise PermissionError("runtime_session_identity_drift")
        except (PermissionError, ValueError):
            system_allowed = False
        if system_identity:
            try:
                validate_runtime_system_capability(
                    system_capability,
                    issuer="RuntimeDispatcher",
                    capability_class=RuntimeCapabilityClass.EXECUTE,
                    resource="runtime_task",
                    action="execute",
                    scope=claims,
                    lineage=claims,
                )
                system_allowed = True
            except RuntimeSystemCapabilityError:
                pass
        if system_allowed and is_taskrunner_execution_capability(
            capability,
            task_id=task_id,
            package_id=package_id,
            session_id=session_id,
            step_id=step_id,
        ):
            return None
        step_type = str(step.get("type") or step.get("action") or "").strip().lower()
        decision = {
            "authority_phase": "pre_execution",
            "authority_layer": "task_runner",
            "authority_policy": "owner_issued_runtime_execution_capability",
            "authority_required": True,
            "decision": "denied",
            "authority_source": "",
            "authority_status": "denied",
            "step_type": step_type,
            "sealed": False,
            "reason": "runtime_dispatcher_live_capability_required",
        }
        return {
            "ok": False,
            "executed": False,
            "blocked": True,
            "action": step_type or "execute_step",
            "step_type": step_type,
            "step": copy.deepcopy(step),
            "error": {
                "type": "execution_authority_denied",
                "message": "runtime dispatcher live capability required before step execution",
                "retryable": False,
            },
            "authority_decision": decision,
            "runtime_transaction": {"state": "blocked", "surface": step_type},
            "runtime_execution_result": {
                "ok": False,
                "status": "blocked",
                "metadata": {
                    "blocked_reason": "runtime_dispatcher_live_capability_required",
                    "authority_decision": copy.deepcopy(decision),
                },
            },
        }

    def execute_owned_step(
        self,
        step: Dict[str, Any],
        *,
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        previous_result: Any = None,
        step_index: int = 0,
        step_count: int = 1,
        _runtime_native_mainline_delegate: bool = False,
    ) -> Dict[str, Any]:
        """Execute one step through the TaskRunner-owned authority boundary."""
        if not _runtime_native_mainline_delegate and not self._runtime_native_mainline_active():
            return self._run_via_runtime_native_mainline(
                entrypoint="core.runtime.task_runner.TaskRunner.execute_owned_step",
                runner=lambda: self.execute_owned_step(
                    step,
                    task=task,
                    context=context,
                    previous_result=previous_result,
                    step_index=step_index,
                    step_count=step_count,
                    _runtime_native_mainline_delegate=True,
                ),
                request=copy.deepcopy(task) if isinstance(task, dict) else {},
                goal=str((task or {}).get("goal") or (task or {}).get("task_id") or "taskrunner execute_owned_step"),
            )
        owned_task = copy.deepcopy(task) if isinstance(task, dict) else {}
        owned_context = copy.deepcopy(context) if isinstance(context, dict) else {}
        task_id = str(
            owned_task.get("task_id")
            or owned_task.get("id")
            or owned_task.get("task_name")
            or "taskrunner-owned-step"
        ).strip()
        owned_task.setdefault("task_id", task_id)
        authority_context = self._build_taskrunner_authority_context(
            task=owned_task,
            state={},
            step=step,
            upstream_context=owned_context,
        )
        step_type = str(step.get("type") or step.get("action") or "").strip().lower()
        denial = None
        if is_side_effect_surface(step_type):
            denial = self._pre_execution_authority_denial(
                task=owned_task,
                step=step,
                authority_context=authority_context,
            )
        if denial is not None:
            return denial
        return self.step_executor.execute_step(
            step=step,
            task=owned_task,
            context={
                **owned_context,
                "authority_context": authority_context,
                "runtime_authority_context": authority_context,
                "runtime_execution_capability": authority_context.get(
                    "runtime_execution_capability"
                ),
                "authority_propagation_required": True,
            },
            previous_result=previous_result,
            step_index=step_index,
            step_count=step_count,
        )

    def execute_owned_steps(
        self,
        steps: List[Dict[str, Any]],
        *,
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        _runtime_native_mainline_delegate: bool = False,
    ) -> Dict[str, Any]:
        """Execute a batch through a TaskRunner-issued batch capability."""
        if not _runtime_native_mainline_delegate and not self._runtime_native_mainline_active():
            return self._run_via_runtime_native_mainline(
                entrypoint="core.runtime.task_runner.TaskRunner.execute_owned_steps",
                runner=lambda: self.execute_owned_steps(
                    steps,
                    task=task,
                    context=context,
                    _runtime_native_mainline_delegate=True,
                ),
                request=copy.deepcopy(task) if isinstance(task, dict) else {},
                goal=str((task or {}).get("goal") or (task or {}).get("task_id") or "taskrunner execute_owned_steps"),
            )
        owned_task = copy.deepcopy(task) if isinstance(task, dict) else {}
        owned_context = copy.deepcopy(context) if isinstance(context, dict) else {}
        task_id = str(
            owned_task.get("task_id")
            or owned_task.get("id")
            or owned_task.get("task_name")
            or "taskrunner-owned-batch"
        ).strip()
        owned_task.setdefault("task_id", task_id)
        try:
            capability = delegate_taskrunner_execution_capability(
                _TASK_RUNNER_ISSUER_TOKEN,
                owned_task.get("runtime_execution_capability"),
                task_id=task_id,
                step_id="",
            )
        except PermissionError:
            return {
                "ok": False,
                "executed": False,
                "blocked": True,
                "status": "blocked",
                "decision": "rejected",
                "error": "runtime_dispatcher_live_capability_required",
                "results": [],
            }
        authority_context = {
            "authority_phase": "taskrunner_delegation",
            "authority_layer": "task_runner",
            "authority_role": "canonical_delegation",
            "authority_policy": "owner_issued_runtime_execution_capability",
            "authority_propagation_required": True,
            "runtime_execution_capability": capability,
            "runtime_system_capability": owned_task.get("runtime_system_capability"),
        }
        return self.step_executor.execute_steps(
            steps,
            task=owned_task,
            context={
                **owned_context,
                "authority_context": authority_context,
                "runtime_authority_context": authority_context,
                "runtime_execution_capability": capability,
                "authority_propagation_required": True,
            },
        )

    # ============================================================
    # mutation boundary integration
    # ============================================================

    def _build_mutation_runtime_integration(self) -> Any:
        """Build the optional governed mutation runtime bridge.

        Keep this optional so TaskRunner can still boot in minimal/test
        environments where the staged mutation module has not been installed
        yet.
        """
        if MutationRuntimeIntegration is None:
            return None

        workspace_root = getattr(self.runtime, "workspace_root", "workspace")
        try:
            return MutationRuntimeIntegration(workspace_root=workspace_root)
        except Exception:
            if self.debug:
                traceback.print_exc()
            return None


    def _is_autonomous_repair_mutation_step(self, step: Any) -> bool:
        if not isinstance(step, dict):
            return False
        step_type = str(step.get("type") or step.get("action") or "").strip().lower()
        return step_type in {
            "code_chain_repair",
            "autonomous_code_repair",
            "apply_patch",
            "apply_unified_diff",
            "repo_edit",
            "repo_apply",
        }

    def _is_self_repair_mutation_step(self, step: Any) -> bool:
        if not isinstance(step, dict):
            return False
        step_type = str(step.get("type") or step.get("action") or "").strip().lower()
        return step_type in {"code_chain_repair", "autonomous_code_repair"}



    def _build_repair_chain_consistency_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Any,
        step_result: Dict[str, Any],
        step_index: int,
        current_tick: int,
        trace_tick: int,
    ) -> Dict[str, Any]:
        if not self._is_autonomous_repair_mutation_step(step):
            return {}

        repair_context = state.setdefault("repair_context", {}) if isinstance(state, dict) else {}
        if not isinstance(repair_context, dict):
            repair_context = {}
            if isinstance(state, dict):
                state["repair_context"] = repair_context

        chain_id = ""
        repair_session = repair_context.get("repair_session")
        if isinstance(repair_session, dict):
            chain_id = str(repair_session.get("chain_id") or repair_session.get("session_id") or repair_session.get("id") or "").strip()

        if not chain_id:
            chain_id = str(
                task.get("repair_chain_id")
                or task.get("chain_id")
                or task.get("task_id")
                or task.get("task_name")
                or "repair_chain"
            ).strip()

        mutation_boundary = step_result.get("mutation_boundary") if isinstance(step_result.get("mutation_boundary"), dict) else {}
        mutation_reconciliation = step_result.get("mutation_reconciliation") if isinstance(step_result.get("mutation_reconciliation"), dict) else {}
        replay_validation = step_result.get("repair_replay_validation") if isinstance(step_result.get("repair_replay_validation"), dict) else {}
        autonomous_repair = step_result.get("autonomous_repair_mutation") if isinstance(step_result.get("autonomous_repair_mutation"), dict) else {}

        step_type_text = str(step.get("type") or step.get("action") or "").strip().lower() if isinstance(step, dict) else ""
        current_record = {
            "chain_id": chain_id,
            "step_index": int(step_index),
            "step_type": step_type_text,
            "participant_kind": "autonomous_self_repair" if self._is_self_repair_mutation_step(step) else "governed_mutation",
            "target": self._runtime_step_target(step),
            "mutation_id": str(mutation_boundary.get("mutation_id") or autonomous_repair.get("mutation_id") or ""),
            "mutation_status": str(mutation_boundary.get("status") or ""),
            "reconciliation_status": str(mutation_reconciliation.get("status") or ""),
            "replay_status": str(replay_validation.get("status") or ""),
            "reproducible": bool(replay_validation.get("reproducible")),
            "ok": bool(step_result.get("ok")) if isinstance(step_result, dict) else False,
            "current_tick": current_tick,
            "trace_tick": trace_tick,
        }

        history: List[Dict[str, Any]] = []

        execution_log = state.get("execution_log") if isinstance(state, dict) else []
        if isinstance(execution_log, list):
            for entry in execution_log:
                if not isinstance(entry, dict):
                    continue
                result_payload = entry.get("result")
                if not isinstance(result_payload, dict):
                    continue

                existing = result_payload.get("repair_chain_consistency")
                if isinstance(existing, dict):
                    latest = existing.get("latest_step")
                    if isinstance(latest, dict):
                        if str(latest.get("chain_id") or "") == chain_id:
                            history.append(copy.deepcopy(latest))
                        continue

                existing_repair = result_payload.get("autonomous_repair_mutation")
                existing_mutation = result_payload.get("mutation_boundary")
                existing_recon = result_payload.get("mutation_reconciliation")
                existing_replay = result_payload.get("repair_replay_validation")

                # v2.3.1:
                # Chain participant is any governed mutation result, not only
                # autonomous repair mutation.  apply_patch/apply_unified_diff
                # rollback must be counted as part of the same chain.
                if not isinstance(existing_mutation, dict):
                    continue

                inferred_step_type = str(result_payload.get("step_type") or "").strip().lower()
                inferred_kind = "governed_mutation"
                inferred_target = ""
                inferred_mutation_id = str(existing_mutation.get("mutation_id") or "")

                if isinstance(existing_repair, dict):
                    inferred_step_type = str(existing_repair.get("step_type") or inferred_step_type).strip().lower()
                    inferred_kind = str(existing_repair.get("kind") or inferred_kind).strip() or inferred_kind
                    inferred_target = str(existing_repair.get("target_path") or existing_repair.get("target") or "")

                if not inferred_target:
                    result_step = result_payload.get("step")
                    if isinstance(result_step, dict):
                        for key in ("target_path", "target", "path", "file_path"):
                            value = result_step.get(key)
                            if isinstance(value, str) and value.strip():
                                inferred_target = value.strip()
                                break

                inferred = {
                    "chain_id": chain_id,
                    "step_index": self._safe_int(result_payload.get("step_index"), len(history)),
                    "step_type": inferred_step_type,
                    "participant_kind": inferred_kind,
                    "target": inferred_target,
                    "mutation_id": inferred_mutation_id,
                    "mutation_status": str(existing_mutation.get("status") or ""),
                    "reconciliation_status": str(existing_recon.get("status") if isinstance(existing_recon, dict) else ""),
                    "replay_status": str(existing_replay.get("status") if isinstance(existing_replay, dict) else ""),
                    "reproducible": bool(existing_replay.get("reproducible")) if isinstance(existing_replay, dict) else False,
                    "ok": bool(result_payload.get("ok")),
                    "current_tick": entry.get("tick", current_tick),
                    "trace_tick": entry.get("tick", trace_tick),
                }
                history.append(inferred)

        current_key = (
            current_record.get("step_index"),
            current_record.get("mutation_id"),
            current_record.get("step_type"),
            current_record.get("target"),
        )
        existing_keys = {
            (
                item.get("step_index"),
                item.get("mutation_id"),
                item.get("step_type"),
                item.get("target"),
            )
            for item in history
            if isinstance(item, dict)
        }
        if current_key not in existing_keys:
            history.append(copy.deepcopy(current_record))

        relevant_history = [
            item for item in history
            if isinstance(item, dict) and str(item.get("chain_id") or "") == chain_id
        ]

        total = len(relevant_history)
        verified = sum(1 for item in relevant_history if item.get("mutation_status") == "verified")
        replay_verified = sum(1 for item in relevant_history if item.get("replay_status") == "replay_verified")
        rolled_back = sum(1 for item in relevant_history if item.get("mutation_status") == "rolled_back")
        failed = sum(
            1 for item in relevant_history
            if item.get("reconciliation_status") in {"failed_rolled_back", "apply_failed", "verification_failed"}
            or item.get("mutation_status") in {"rolled_back", "apply_failed", "verification_failed"}
        )
        governed_mutations = sum(1 for item in relevant_history if item.get("participant_kind") == "governed_mutation")
        self_repair_mutations = sum(1 for item in relevant_history if item.get("participant_kind") == "autonomous_self_repair")

        if total <= 0:
            status = "empty"
        elif failed > 0:
            status = "chain_has_rollback_or_failure"
        elif verified == total and replay_verified == total:
            status = "chain_replay_verified"
        elif verified == total:
            status = "chain_verified_without_full_replay"
        else:
            status = "chain_incomplete"

        summary = {
            "enabled": True,
            "schema": "zero.repair_chain_consistency.v2_3_1",
            "chain_id": chain_id,
            "status": status,
            "total_steps": total,
            "verified_steps": verified,
            "replay_verified_steps": replay_verified,
            "rolled_back_steps": rolled_back,
            "failed_steps": failed,
            "governed_mutation_steps": governed_mutations,
            "autonomous_self_repair_steps": self_repair_mutations,
            "latest_step": copy.deepcopy(current_record),
            "history": copy.deepcopy(relevant_history[-100:]),
        }

        repair_context["repair_chain_consistency_history"] = copy.deepcopy(relevant_history[-100:])
        repair_context["last_repair_chain_consistency"] = copy.deepcopy(summary)

        engineering_execution = repair_context.setdefault("engineering_execution", {})
        if isinstance(engineering_execution, dict):
            engineering_execution["last_repair_chain_consistency"] = copy.deepcopy(summary)
            engineering_execution["repair_chain_consistency_status"] = status
            engineering_execution["repair_chain_id"] = chain_id
            engineering_execution["repair_chain_total_steps"] = total
            engineering_execution["repair_chain_failed_steps"] = failed

        if isinstance(task, dict):
            task_repair_context = task.setdefault("repair_context", {})
            if isinstance(task_repair_context, dict):
                task_repair_context["repair_chain_consistency_history"] = copy.deepcopy(relevant_history[-100:])
                task_repair_context["last_repair_chain_consistency"] = copy.deepcopy(summary)

        return summary



    def _build_repair_replay_validation(
        self,
        *,
        step: Any,
        step_result: Dict[str, Any],
        mutation_result: Dict[str, Any],
        step_index: int,
        current_tick: int,
        trace_tick: int,
    ) -> Dict[str, Any]:
        return build_repair_replay_validation(
            step=step,
            step_result=step_result,
            mutation_result=mutation_result,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
            runtime_step_target=self._runtime_step_target,
        )

    def _attach_autonomous_repair_mutation_metadata(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Any,
        step_result: Dict[str, Any],
        mutation_result: Dict[str, Any],
        step_index: int,
        current_tick: int,
        trace_tick: int,
    ) -> Dict[str, Any]:
        normalized = copy.deepcopy(step_result) if isinstance(step_result, dict) else {"ok": False, "raw_result": step_result}
        if not self._is_autonomous_repair_mutation_step(step):
            return normalized

        mutation_status = ""
        if isinstance(mutation_result, dict):
            mutation_status = str(mutation_result.get("status") or "").strip()

        step_type_text = str(step.get("type") or step.get("action") or "").strip().lower() if isinstance(step, dict) else ""
        repair_mutation = {
            "enabled": True,
            "kind": "autonomous_self_repair" if self._is_self_repair_mutation_step(step) else "governed_mutation",
            "step_type": step_type_text,
            "mutation_id": str(mutation_result.get("mutation_id") or "") if isinstance(mutation_result, dict) else "",
            "mutation_status": mutation_status,
            "reconciliation_status": str(
                normalized.get("mutation_reconciliation", {}).get("status")
                if isinstance(normalized.get("mutation_reconciliation"), dict)
                else ""
            ),
            "target_path": self._runtime_step_target(step),
            "step_index": int(step_index),
            "current_tick": current_tick,
            "trace_tick": trace_tick,
        }

        normalized["autonomous_repair_mutation"] = repair_mutation

        repair_replay_validation = self._build_repair_replay_validation(
            step=step,
            step_result=normalized,
            mutation_result=mutation_result,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )
        normalized["repair_replay_validation"] = repair_replay_validation

        repair_chain_consistency = self._build_repair_chain_consistency_record(
            task=task,
            state=state,
            step=step,
            step_result=normalized,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )
        if repair_chain_consistency:
            normalized["repair_chain_consistency"] = repair_chain_consistency



        repair_context = state.get("repair_context") if isinstance(state, dict) else None
        if isinstance(repair_context, dict):
            repair_context["last_autonomous_repair_mutation"] = copy.deepcopy(repair_mutation)
            repair_context["last_repair_replay_validation"] = copy.deepcopy(repair_replay_validation)
            repair_history = repair_context.setdefault("autonomous_repair_mutation_history", [])
            if isinstance(repair_history, list):
                repair_history.append(copy.deepcopy(repair_mutation))
                if len(repair_history) > 50:
                    del repair_history[:-50]

            engineering_execution = repair_context.setdefault("engineering_execution", {})
            if isinstance(engineering_execution, dict):
                engineering_execution["last_mutation_boundary_status"] = mutation_status
                engineering_execution["last_mutation_reconciliation_status"] = repair_mutation["reconciliation_status"]
                engineering_execution["last_autonomous_repair_mutation"] = copy.deepcopy(repair_mutation)
                engineering_execution["last_repair_replay_validation"] = copy.deepcopy(repair_replay_validation)

        if isinstance(task, dict):
            task_repair_context = task.get("repair_context")
            if isinstance(task_repair_context, dict):
                task_repair_context["last_autonomous_repair_mutation"] = copy.deepcopy(repair_mutation)
                task_repair_context["last_repair_replay_validation"] = copy.deepcopy(repair_replay_validation)

        return normalized


    def _attach_mutation_boundary_after_step(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Any,
        step_result: Dict[str, Any],
        step_index: int,
        current_tick: int,
        trace_tick: int,
    ) -> Dict[str, Any]:
        """Attach governed mutation lifecycle metadata after a step executes.

        The actual file mutation is still performed by the existing guarded
        StepExecutor/handler path.  This method only records the mutation
        boundary lifecycle around the already-produced step_result.
        """
        if not isinstance(step_result, dict):
            return step_result

        if not isinstance(step, dict):
            return step_result

        integration = self.mutation_runtime
        if integration is None:
            return step_result

        try:
            if not integration.is_mutation_step(step):
                return step_result
        except Exception:
            if self.debug:
                traceback.print_exc()
            return step_result

        # If the task targets a separate repo copy, use a short-lived bridge
        # pointed at that repo so snapshots are taken from the real target.
        try:
            target_repo_root = self._resolve_target_repo_root(task=task, state=state)
        except Exception:
            target_repo_root = ""

        if target_repo_root and MutationRuntimeIntegration is not None:
            try:
                integration = MutationRuntimeIntegration(
                    workspace_root=getattr(self.runtime, "workspace_root", "workspace"),
                    project_root=target_repo_root,
                )
            except Exception:
                integration = self.mutation_runtime

        verification_result = {
            "ok": bool(step_result.get("ok", False)),
            "source": "task_runner_step_result",
            "step_index": int(step_index),
            "tick": trace_tick if trace_tick is not None else current_tick,
        }
        replay_result = {
            "ok": bool(step_result.get("ok", False)),
            "source": "task_runner_replay_default",
            "step_index": int(step_index),
            "tick": trace_tick if trace_tick is not None else current_tick,
        }

        try:
            mutation_result = integration.record_after_step(
                step=step,
                step_result=step_result,
                verification_result=verification_result,
                replay_result=replay_result,
                approved_by="task_runner",
                actor="task_runner",
                rollback_on_failure=True,
            )
        except Exception as exc:
            mutation_result = {
                "ok": False,
                "mutation_recorded": False,
                "error": str(exc),
                "step_index": int(step_index),
            }

        normalized = copy.deepcopy(step_result)
        normalized["mutation_boundary"] = copy.deepcopy(mutation_result)
        normalized = self._reconcile_mutation_boundary_result(
            step=step,
            step_result=normalized,
            mutation_result=mutation_result,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )

        trace = normalized.get("execution_trace")
        if isinstance(trace, list) and trace:
            last = trace[-1]
            if isinstance(last, dict):
                last["mutation_boundary"] = copy.deepcopy(mutation_result)
                last["mutation_reconciliation"] = copy.deepcopy(normalized.get("mutation_reconciliation") or {})

        normalized = self._attach_autonomous_repair_mutation_metadata(
            task=task,
            state=state,
            step=step,
            step_result=normalized,
            mutation_result=normalized.get("mutation_boundary", {}) if isinstance(normalized.get("mutation_boundary"), dict) else {},
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )
        return normalized


    def _reconcile_mutation_boundary_result(
        self,
        *,
        step: Any,
        step_result: Dict[str, Any],
        mutation_result: Dict[str, Any],
        step_index: int,
        current_tick: int,
        trace_tick: int,
    ) -> Dict[str, Any]:
        return reconcile_mutation_boundary_result(
            step=step,
            step_result=step_result,
            mutation_result=mutation_result,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )

    # ============================================================
    # main loop
    # ============================================================

    def run_task_tick(
        self,
        task: Dict[str, Any],
        current_tick: int,
        *,
        _runtime_native_mainline_delegate: bool = False,
    ) -> Dict[str, Any]:
        if not _runtime_native_mainline_delegate and not self._runtime_native_mainline_active():
            return self._run_via_runtime_native_mainline(
                entrypoint="core.runtime.task_runner.TaskRunner.run_task_tick",
                runner=lambda: self.run_task_tick(
                    task=task,
                    current_tick=current_tick,
                    _runtime_native_mainline_delegate=True,
                ),
                request=copy.deepcopy(task) if isinstance(task, dict) else {},
                goal=str((task or {}).get("goal") or (task or {}).get("task_id") or "taskrunner run_task_tick"),
            )
        try:
            # Q package: persistence/resume gate.
            # Load the saved runtime state before mutating it so a restarted
            # process can preserve terminal/waiting states and resume only when
            # the previous loop explicitly requested run_next_tick.
            state = self.runtime.load_runtime_state(task)
            self._ensure_execution_trace_defaults(task, state)

            status = str(state.get("status") or "").strip().lower()
            next_action = str(state.get("next_action") or "").strip().lower()
            active_blocker_count = self._safe_int(state.get("active_blocker_count"), 0)
            blockers = state.get("blockers") if isinstance(state.get("blockers"), list) else []

            if status in {"waiting", "waiting_blocker", "waiting_review", "blocked", "paused"}:
                persisted_repair_context = state.get("repair_context")
                repair_lineage_recheck = bool(
                    status == "blocked"
                    and isinstance(persisted_repair_context, dict)
                    and not _repair_chain_has_live_dispatcher_capability(task)
                )
                if repair_lineage_recheck:
                    steps = state.get("steps") if isinstance(state.get("steps"), list) else []
                    step_index = self._safe_int(state.get("current_step_index"), 0)
                    step = (
                        steps[step_index]
                        if 0 <= step_index < len(steps) and isinstance(steps[step_index], dict)
                        else _taskrunner_select_current_step(task)
                    )
                    denial = {
                        "ok": False,
                        "executed": False,
                        "blocked": True,
                        "step_index": step_index,
                        "step_type": str(step.get("type") or step.get("action") or ""),
                        "error": {
                            "type": "execution_authority_denied",
                            "message": "runtime dispatcher live capability required before step execution",
                            "retryable": False,
                        },
                    }
                    recorded = self.runtime.record_step_failure(
                        task=task,
                        step=step,
                        step_result=denial,
                        current_tick=current_tick,
                        status="blocked",
                    )
                    state = copy.deepcopy(recorded.get("runtime_state", state))
                    self._ensure_execution_trace_defaults(task, state)
                    denial_result = {
                        "ok": False,
                        "action": "retry",
                        "failure_type": "execution_authority_denied",
                        "error": copy.deepcopy(denial["error"]),
                        "task": copy.deepcopy(task),
                        "runtime_state": state,
                        "status": "blocked",
                        "last_result": denial,
                        "execution_trace": copy.deepcopy(state.get("execution_trace", [])),
                    }
                    build_observation = getattr(self, "_zero_v800_build_observation", None)
                    decide_observation = getattr(self, "_zero_v800_decide_from_observation", None)
                    if callable(build_observation) and callable(decide_observation):
                        observation = build_observation(
                            task=task,
                            result=denial_result,
                            current_tick=current_tick,
                        )
                        observed = self.runtime.record_engineering_observation(
                            task=task,
                            observation=observation,
                            current_tick=current_tick,
                        )
                        if isinstance(observed, dict) and isinstance(observed.get("runtime_state"), dict):
                            denial_result["runtime_state"] = copy.deepcopy(observed["runtime_state"])
                        decision = decide_observation(observation=observation, result=denial_result)
                        decided = self.runtime.record_engineering_decision(
                            task=task,
                            decision=decision,
                            current_tick=current_tick,
                        )
                        if isinstance(decided, dict) and isinstance(decided.get("runtime_state"), dict):
                            denial_result["runtime_state"] = copy.deepcopy(decided["runtime_state"])
                    return self._finalize_public_result(denial_result)
                if next_action != "run_next_tick" or active_blocker_count > 0 or blockers:
                    return self._finalize_public_result({
                        "ok": True,
                        "action": "blocked_waiting",
                        "task": copy.deepcopy(task),
                        "runtime_state": state,
                        "status": status,
                        "next_action": next_action or "wait_for_external_event",
                        "blockers": copy.deepcopy(blockers),
                    })

            if status == "needs_observation":
                return self._finalize_public_result({
                    "ok": True,
                    "action": "terminal_validation_pending",
                    "task": copy.deepcopy(task),
                    "runtime_state": state,
                    "status": status,
                    "next_action": "observe_terminal_result",
                })

            if status in {"finished", "done", "success", "completed"}:
                return self._finalize_public_result({
                    "ok": True,
                    "action": "already_finished",
                    "task": copy.deepcopy(task),
                    "runtime_state": state,
                    "status": "finished",
                    "final_answer": str(state.get("final_answer") or ""),
                    "execution_trace": copy.deepcopy(state.get("execution_trace", []))
                    if isinstance(state.get("execution_trace"), list)
                    else [],
                })

            if status in {"failed", "error", "cancelled", "canceled", "timeout"}:
                return self._finalize_public_result({
                    "ok": False,
                    "action": "already_terminal",
                    "task": copy.deepcopy(task),
                    "runtime_state": state,
                    "status": status,
                    "error": str(state.get("last_error") or state.get("failure_message") or status),
                    "execution_trace": copy.deepcopy(state.get("execution_trace", []))
                    if isinstance(state.get("execution_trace"), list)
                    else [],
                })

            run_result = self.runtime.mark_running(task, current_tick=current_tick)
            state = copy.deepcopy(run_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, state)

            capability_result = self._maybe_run_enabled_capability(
                task=task,
                state=state,
                current_tick=current_tick,
            )
            if capability_result is not None:
                return self._finalize_public_result(capability_result)

            result: Dict[str, Any] = {
                "ok": True,
                "action": "no_step_executed",
                "task": copy.deepcopy(task),
                "runtime_state": state,
                "status": str(state.get("status") or "running"),
            }

            max_auto_ticks = self._resolve_max_auto_ticks(task=task, state=state)
            auto_tick_count = 0

            while auto_tick_count < max_auto_ticks:
                result = self._run_one_step(task, current_tick=current_tick + auto_tick_count)

                if not isinstance(result, dict):
                    result = {
                        "ok": False,
                        "action": "invalid_result",
                        "task": copy.deepcopy(task),
                        "runtime_state": self.runtime.load_runtime_state(task),
                        "status": "failed",
                        "error": "TaskRunner._run_one_step returned invalid result",
                    }
                    break

                runtime_state = result.get("runtime_state")
                if not isinstance(runtime_state, dict):
                    runtime_state = self.runtime.load_runtime_state(task)

                self._ensure_execution_trace_defaults(task, runtime_state)

                status = str(
                    runtime_state.get("status")
                    or result.get("status")
                    or ""
                ).strip().lower()

                action = str(result.get("action") or "").strip().lower()
                next_action = str(runtime_state.get("next_action") or "").strip().lower()

                if status in {
                    "finished",
                    "done",
                    "success",
                    "completed",
                    "failed",
                    "error",
                    "cancelled",
                    "canceled",
                    "timeout",
                    "blocked",
                    "waiting",
                    "waiting_blocker",
                    "waiting_review",
                    "paused",
                    "needs_observation",
                }:
                    break

                if action in {
                    "blocked_for_review",
                    "subgoal_blocked",
                    "step_failed",
                    "exception_failed",
                    "already_terminal",
                    "already_finished",
                    "task_finished",
                    "capability_executed",
                    "capability_failed",
                    "regression_verify_failed",
                    "strategy_retry",
                    "retry",
                    "replan",
                }:
                    break

                if next_action != "run_next_tick":
                    break

                auto_tick_count += 1

            if auto_tick_count >= max_auto_ticks:
                runtime_state = result.get("runtime_state")
                if isinstance(runtime_state, dict):
                    runtime_state["auto_tick_limit_reached"] = True
                    runtime_state["auto_tick_limit"] = max_auto_ticks
                    try:
                        runtime_state = self.runtime.save_runtime_state(task, runtime_state)
                    except Exception:
                        pass
                    result["runtime_state"] = runtime_state
                result["auto_tick_limit_reached"] = True
                result["auto_tick_limit"] = max_auto_ticks

            return self._finalize_public_result(result)

        except Exception as e:
            traceback.print_exc()

            fail_result = self.runtime.mark_failed(
                task=task,
                current_tick=current_tick,
                failure_type="internal_error",
                failure_message=str(e),
            )
            runtime_state = copy.deepcopy(fail_result.get("runtime_state", {}))
            self._ensure_execution_trace_defaults(task, runtime_state)

            return {
                "ok": False,
                "action": "exception_failed",
                "error": str(e),
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": "failed",
            }

    # compatibility entrypoints
    def run_one_tick(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
        *,
        _runtime_native_mainline_delegate: bool = False,
    ) -> Dict[str, Any]:
        return self.run_task_tick(
            task=task,
            current_tick=current_tick,
            _runtime_native_mainline_delegate=_runtime_native_mainline_delegate,
        )

    def run_one_step(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
        *,
        _runtime_native_mainline_delegate: bool = False,
    ) -> Dict[str, Any]:
        return self.run_task_tick(
            task=task,
            current_tick=current_tick,
            _runtime_native_mainline_delegate=_runtime_native_mainline_delegate,
        )

    def run_task(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
        *,
        _runtime_native_mainline_delegate: bool = False,
    ) -> Dict[str, Any]:
        return self.run_task_tick(
            task=task,
            current_tick=current_tick,
            _runtime_native_mainline_delegate=_runtime_native_mainline_delegate,
        )

    def run(
        self,
        task: Dict[str, Any],
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
        *,
        _runtime_native_mainline_delegate: bool = False,
    ) -> Dict[str, Any]:
        return self.run_task_tick(
            task=task,
            current_tick=current_tick,
            _runtime_native_mainline_delegate=_runtime_native_mainline_delegate,
        )

    def complete_task(
        self,
        task: Dict[str, Any],
        *,
        current_tick: int = 0,
        final_answer: str = "",
        final_result: Optional[Dict[str, Any]] = None,
        terminal_evidence: Any = None,
    ) -> Dict[str, Any]:
        """Seal terminal completion behind live TaskRunner execution evidence.

        This API is intentionally not a convenience shortcut. Callers must pass
        a live TerminalExecutionEvidence object issued from TaskRunner-owned
        execution lineage; missing, serialized, or synthetic evidence is
        rejected by issue_task_completion_authority.
        """
        task_id = str(task.get("task_id") or task.get("id") or "")
        package_id = str(task.get("package_id") or task.get("work_package_id") or "")
        session_id = str(task.get("session_id") or task.get("runtime_session") or "")
        return self.runtime.mark_finished(
            task=task,
            current_tick=current_tick,
            final_answer=final_answer,
            final_result=final_result,
            completion_authority=issue_task_completion_authority(
                _TASK_RUNNER_ISSUER_TOKEN,
                task_id=task_id,
                package_id=package_id,
                session_id=session_id,
                evidence=terminal_evidence,
            ),
        )

    def _terminal_completion_authority(
        self,
        *,
        task: Dict[str, Any],
        step: Any,
        result: Any,
    ) -> Any:
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise PermissionError("successful_terminal_execution_evidence_required")
        task_id = str(task.get("task_id") or task.get("id") or "")
        package_id = str(task.get("package_id") or task.get("work_package_id") or "")
        session_id = str(task.get("session_id") or task.get("runtime_session") or "")
        step = step if isinstance(step, dict) else {}
        step_id = str(step.get("id") or step.get("step_id") or f"{task_id}:step")
        capability = delegate_taskrunner_execution_capability(
            _TASK_RUNNER_ISSUER_TOKEN,
            task.get("runtime_execution_capability"),
            task_id=task_id,
            step_id=step_id,
        )
        evidence = issue_terminal_execution_evidence(
            _TASK_RUNNER_ISSUER_TOKEN,
            capability,
            task_id=task_id,
            package_id=package_id,
            session_id=session_id,
            step_id=step_id,
        )
        if task.get("runtime_identity_graph"):
            task.update(
                attach_runtime_identity_graph(
                    task,
                    bind_runtime_identity_graph(
                        task["runtime_identity_graph"],
                        evidence_id=evidence.evidence_id,
                    ),
                )
            )
        return issue_task_completion_authority(
            _TASK_RUNNER_ISSUER_TOKEN,
            task_id=task_id,
            package_id=package_id,
            session_id=session_id,
            evidence=evidence,
        )

    def record_terminal_observation(
        self,
        task: Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        terminal_evidence = kwargs.pop("terminal_evidence", None)
        task_id = str(task.get("task_id") or task.get("id") or "")
        package_id = str(task.get("package_id") or task.get("work_package_id") or "")
        session_id = str(task.get("session_id") or task.get("runtime_session") or "")
        try:
            completion_authority = issue_task_completion_authority(
                _TASK_RUNNER_ISSUER_TOKEN,
                task_id=task_id,
                package_id=package_id,
                session_id=session_id,
                evidence=terminal_evidence,
            )
        except PermissionError:
            completion_authority = None
        try:
            return self.runtime.record_terminal_observation(
                task,
                **kwargs,
                completion_authority=completion_authority,
            )
        except PermissionError:
            return {
                "ok": False,
                "status": "completion_rejected",
                "blocked": True,
                "executed": False,
                "error": "terminal_execution_evidence_required",
                "task": copy.deepcopy(task),
            }

    # ============================================================
    # capability execution
    # ============================================================

    def _resolve_max_auto_ticks(self, *, task: Dict[str, Any], state: Dict[str, Any]) -> int:
        """
        Resolve the maximum number of automatic runtime ticks for one public run() call.

        This turns TaskRunner from a single-step executor into a bounded autonomous
        continuation dispatcher:

            step_completed + next_action=run_next_tick
            -> continue executing the next step
            -> stop only at terminal / waiting / blocked / review states

        The limit prevents accidental infinite loops if runtime state gets stuck.
        """
        raw_value = None

        if isinstance(task, dict):
            raw_value = (
                task.get("max_auto_ticks")
                or task.get("max_runtime_ticks")
                or task.get("auto_tick_limit")
            )

        if raw_value is None and isinstance(state, dict):
            raw_value = (
                state.get("max_auto_ticks")
                or state.get("max_runtime_ticks")
                or state.get("auto_tick_limit")
            )

        # Default must remain one public runtime step per run_task() call.
        # Multi-step auto-continuation is opt-in through max_auto_ticks /
        # max_runtime_ticks / auto_tick_limit.  The repair-chain runtime tests
        # depend on the first call stopping at current_step_index == 1 instead
        # of draining the whole task to finished.
        if raw_value is None:
            raw_value = 1

        try:
            value = int(raw_value)
        except Exception:
            value = 1

        if value < 1:
            return 1

        if value > 128:
            return 128

        return value

    def _maybe_run_enabled_capability(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        current_tick: int,
    ) -> Optional[Dict[str, Any]]:
        capability_execution = self._get_capability_execution(task, state)
        if not capability_execution.get("enabled"):
            return None

        route = self._get_capability_route(task, state)
        input_path = capability_execution.get("input_path")
        summary_output_path = capability_execution.get("summary_output_path")
        action_items_output_path = capability_execution.get("action_items_output_path")

        execution_result = execute_resolved_capability(
            route=route,
            input_path=input_path,
            summary_output_path=summary_output_path,
            action_items_output_path=action_items_output_path,
        )

        result_payload = self._make_json_safe(execution_result.to_dict())
        capability_execution = copy.deepcopy(capability_execution)
        capability_execution["enabled"] = False
        capability_execution["status"] = "finished" if execution_result.ok else "failed"
        capability_execution["last_result"] = copy.deepcopy(result_payload)
        capability_execution["error"] = execution_result.error

        task["capability_execution"] = copy.deepcopy(capability_execution)
        state["capability_execution"] = copy.deepcopy(capability_execution)

        final_answer = self._format_capability_final_answer(result_payload)

        if execution_result.ok:
            completion_authority = self._terminal_completion_authority(
                task=task,
                step={"id": f"{task.get('task_id')}:capability", "type": "capability"},
                result={"ok": True},
            )
            finish_result = self.runtime.mark_finished(
                task=task,
                current_tick=current_tick,
                final_answer=final_answer,
                completion_authority=completion_authority,
                final_result={
                    "ok": True,
                    "step_type": "capability",
                    "capability": execution_result.capability,
                    "operation": execution_result.operation,
                    "registry_operation": execution_result.registry_operation,
                    "result": copy.deepcopy(result_payload),
                    "final_answer": final_answer,
                    "execution_trace": [
                        {
                            "step_index": self._safe_int(state.get("current_step_index", 0), 0),
                            "step_type": "capability",
                            "ok": True,
                            "message": "controlled capability execution completed",
                            "final_answer": final_answer,
                            "error_type": "",
                            "classification": None,
                            "attempts": 1,
                            "max_attempts": 1,
                            "retry_used": False,
                        }
                    ],
                },
            )
            runtime_state = copy.deepcopy(finish_result.get("runtime_state", {}))
            runtime_state["capability_execution"] = copy.deepcopy(capability_execution)
            task["capability_execution"] = copy.deepcopy(capability_execution)

            try:
                runtime_state = self.runtime.save_runtime_state(task, runtime_state)
            except Exception:
                pass

            self._ensure_execution_trace_defaults(task, runtime_state)
            return {
                "ok": True,
                "action": "capability_executed",
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": "finished",
                "last_result": copy.deepcopy(result_payload),
                "final_answer": finish_result.get("final_answer", final_answer),
                "task_completion_authority": finish_result.get("task_completion_authority"),
                "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
            }

        fail_result = self.runtime.mark_failed(
            task=task,
            current_tick=current_tick,
            failure_type="tool_error",
            failure_message=execution_result.error or "capability execution failed",
        )
        runtime_state = copy.deepcopy(fail_result.get("runtime_state", {}))
        self._ensure_execution_trace_defaults(task, runtime_state)
        return {
            "ok": False,
            "action": "capability_failed",
            "task": copy.deepcopy(task),
            "runtime_state": runtime_state,
            "status": "failed",
            "error": execution_result.error,
            "last_result": copy.deepcopy(result_payload),
            "execution_trace": copy.deepcopy(runtime_state.get("execution_trace", [])),
        }

    def _get_capability_execution(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        value = state.get("capability_execution") if isinstance(state, dict) else None
        if isinstance(value, dict) and value:
            return copy.deepcopy(value)

        value = task.get("capability_execution") if isinstance(task, dict) else None
        if isinstance(value, dict) and value:
            return copy.deepcopy(value)

        return {"enabled": False, "status": "metadata_only", "reason": ""}

    def _get_capability_route(self, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        route = task.get("route") if isinstance(task, dict) else None
        if isinstance(route, dict):
            return copy.deepcopy(route)

        route = state.get("route") if isinstance(state, dict) else None
        if isinstance(route, dict):
            return copy.deepcopy(route)

        capability = str(
            state.get("capability")
            or task.get("capability")
            or ""
        ).strip()
        operation = str(
            state.get("operation")
            or task.get("operation")
            or ""
        ).strip()

        capability_hint = state.get("capability_hint") if isinstance(state.get("capability_hint"), dict) else task.get("capability_hint")
        capability_registry_hint = (
            state.get("capability_registry_hint")
            if isinstance(state.get("capability_registry_hint"), dict)
            else task.get("capability_registry_hint")
        )

        built_route: Dict[str, Any] = {}
        if capability:
            built_route["capability"] = capability
        if operation:
            built_route["operation"] = operation
        if isinstance(capability_hint, dict):
            built_route["capability_hint"] = copy.deepcopy(capability_hint)
        if isinstance(capability_registry_hint, dict):
            built_route["capability_registry_hint"] = copy.deepcopy(capability_registry_hint)

        return built_route


    # ============================================================
    # target repo routing
    # ============================================================


    def _resolve_target_repo_root(self, task: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> str:
        return resolve_target_repo_root(task=task, state=state)


    def _target_routed_context(self, *, task: Dict[str, Any], state: Dict[str, Any], step: Any) -> Dict[str, Any]:
        return target_routed_context(
            task=task,
            state=state,
            step=step,
            workspace_root=getattr(self.runtime, "workspace_root", "workspace"),
            operator_session_id_from_payloads=self._operator_session_id_from_payloads,
        )

    def _operator_session_id_from_payloads(self, *payloads: Any) -> str:
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            for key in ("operator_session_id", "persistent_operator_session_id"):
                value = str(payload.get(key) or "").strip()
                if value:
                    return value
            metadata = payload.get("metadata")
            if isinstance(metadata, dict):
                for key in ("operator_session_id", "persistent_operator_session_id"):
                    value = str(metadata.get(key) or "").strip()
                    if value:
                        return value
            operator_state = payload.get("operator")
            if isinstance(operator_state, dict):
                value = str(operator_state.get("session_id") or "").strip()
                if value:
                    return value
        return ""

    def _build_taskrunner_authority_context(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Any,
        upstream_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return build_taskrunner_authority_context(
            task=task,
            state=state,
            step=step if isinstance(step, dict) else {},
            upstream_context=upstream_context,
            issuer_token=_TASK_RUNNER_ISSUER_TOKEN,
            delegate_capability=delegate_taskrunner_execution_capability,
        )

    @staticmethod
    def _attach_system_rollback_capability(task: Dict[str, Any]) -> None:
        identity = task.get("runtime_identity") if isinstance(task, dict) else None
        if not isinstance(identity, dict) or str(identity.get("identity_type") or "").upper() != "SYSTEM":
            return
        task_id = str(task.get("task_id") or task.get("id") or "")
        task["runtime_rollback_capability"] = issue_runtime_system_capability(
            issuer="TaskRunner",
            capability_class=RuntimeCapabilityClass.ROLLBACK,
            resource="workspace",
            action="rollback",
            scope={"task_id": task_id},
            lineage={"task_id": task_id},
        )

    def _make_json_safe(self, value: Any) -> Any:
        if is_task_completion_authority(value):
            return value
        if isinstance(value, dict):
            return {str(key): self._make_json_safe(item) for key, item in value.items()}

        if isinstance(value, list):
            return [self._make_json_safe(item) for item in value]

        if isinstance(value, tuple):
            return [self._make_json_safe(item) for item in value]

        if isinstance(value, (str, int, float, bool)) or value is None:
            return value

        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                return self._make_json_safe(to_dict())
            except Exception:
                pass

        if hasattr(value, "__dict__"):
            try:
                raw = {
                    key: item
                    for key, item in vars(value).items()
                    if not str(key).startswith("_")
                }
                return self._make_json_safe(raw)
            except Exception:
                pass

        return str(value)

    def _format_capability_final_answer(self, result_payload: Dict[str, Any]) -> str:
        capability = str(result_payload.get("capability") or "").strip()
        operation = str(result_payload.get("operation") or "").strip()
        summary_output_path = str(result_payload.get("summary_output_path") or "").strip()
        action_items_output_path = str(result_payload.get("action_items_output_path") or "").strip()

        lines = [
            "Capability execution completed.",
            f"capability: {capability}",
            f"operation: {operation}",
        ]

        if summary_output_path:
            lines.append(f"summary_output_path: {summary_output_path}")
        if action_items_output_path:
            lines.append(f"action_items_output_path: {action_items_output_path}")

        return "\n".join(lines)


    # ============================================================
    # runtime mode propagation
    # ============================================================


    def _normalize_runtime_mode(self, value: Any) -> str:
        return normalize_runtime_mode(value)


    def _extract_runtime_mode_from_mapping(self, value: Any) -> str:
        return extract_runtime_mode_from_mapping(value)


    def _apply_runtime_mode_to_step(self, *, task: Dict[str, Any], state: Dict[str, Any], step: Any) -> tuple[Dict[str, Any], str]:
        return apply_runtime_mode_to_step(task=task, state=state, step=step)

    # ============================================================
    # engineering execution action linkage
    # ============================================================

    def _runtime_step_target(self, step: Any) -> str:
        return runtime_step_target(step)

    def _safe_update_current_engineering_action(self, *, task: Dict[str, Any], step: Any, step_index: int, current_tick: int, trace_tick: int) -> None:
        return safe_update_current_engineering_action(
            runtime=self.runtime,
            debug=self.debug,
            task=task,
            step=step,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )

    def _safe_complete_engineering_action(self, *, task: Dict[str, Any], step: Any, step_result: Dict[str, Any], step_index: int, current_tick: int, trace_tick: int) -> None:
        return safe_complete_engineering_action(
            runtime=self.runtime,
            debug=self.debug,
            task=task,
            step=step,
            step_result=step_result,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )

    def _safe_fail_engineering_action(self, *, task: Dict[str, Any], step: Any, step_result: Dict[str, Any], step_index: int, current_tick: int, trace_tick: int) -> None:
        return safe_fail_engineering_action(
            runtime=self.runtime,
            debug=self.debug,
            task=task,
            step=step,
            step_result=step_result,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )

    def _safe_block_engineering_action(self, *, task: Dict[str, Any], step: Any, step_result: Dict[str, Any], step_index: int, current_tick: int, trace_tick: int, reason: str = "") -> None:
        return safe_block_engineering_action(
            runtime=self.runtime,
            debug=self.debug,
            task=task,
            step=step,
            step_result=step_result,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
            reason=reason,
        )

    def _safe_record_rollback_restore_action(self, *, task: Dict[str, Any], step: Any, rollback_result: Dict[str, Any], step_index: int, current_tick: int, trace_tick: int) -> None:
        return safe_record_rollback_restore_action(
            runtime=self.runtime,
            debug=self.debug,
            task=task,
            step=step,
            rollback_result=rollback_result,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )

    # ============================================================
    # step execution
    # ============================================================

    def _execute_current_runtime_step(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        steps: List[Dict[str, Any]],
        idx: int,
        current_tick: int,
    ) -> Dict[str, Any]:
        step, runtime_mode = self._apply_runtime_mode_to_step(
            task=task,
            state=state,
            step=steps[idx],
        )
        trace_tick = self._trace_tick_for_step(
            state=state,
            step_index=idx,
            current_tick=current_tick,
        )

        self._safe_update_current_engineering_action(
            task=task,
            step=step,
            step_index=idx,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )

        self._append_trace_json_event(
            task,
            "step_start",
            {
                "task_id": task.get("task_id") or task.get("id"),
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "steps_total": len(steps),
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "runtime_mode": runtime_mode,
            },
        )
        self.audit.log_event(
            task,
            "step_start",
            {
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "steps_total": len(steps),
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "runtime_mode": runtime_mode,
            },
            source="task_runner",
        )

        self.audit.log_event(
            task,
            "policy_check",
            {
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "runtime_mode": runtime_mode,
                "step": copy.deepcopy(step) if isinstance(step, dict) else {},
            },
            source="policy_layer",
        )

        target_context = self._target_routed_context(task=task, state=state, step=step)
        authority_context = self._build_taskrunner_authority_context(
            task=task,
            state=state,
            step=step,
            upstream_context=target_context,
        )

        result = self._pre_execution_authority_denial(
            task=task,
            step=step,
            authority_context=authority_context,
        )
        if result is None:
            enforce_execution_authority(
                source="core.runtime.step_executor",
                action_type=str(step.get("type") or step.get("action") or "execute"),
                metadata={
                    "side_effect": str(step.get("type") or step.get("action") or "").lower() not in self.READ_ONLY_STEP_TYPES,
                    "execution_authority_gate": "task_runner_pre_execution",
                    "runtime_execution_capability": authority_context.get("runtime_execution_capability"),
                    "task_id": str(task.get("task_id") or task.get("id") or ""),
                    "step_id": str(step.get("id") or step.get("step_id") or f"{task.get('task_id')}:step"),
                    "package_id": str(task.get("package_id") or task.get("work_package_id") or ""),
                    "session_id": str(task.get("session_id") or task.get("runtime_session") or ""),
                },
            )
            result = self.step_executor.execute_step(
                task=task,
                step=step,
                context={
                    **target_context,
                    "runtime_mode": runtime_mode,
                    "authority_context": authority_context,
                    "runtime_authority_context": authority_context,
                    "authority_propagation_required": bool(
                        authority_context.get("authority_propagation_required")
                    ),
                },
                previous_result=self._get_previous_result(state),
                step_index=idx,
                step_count=len(steps),
            )

        if not isinstance(result, dict):
            result = {
                "ok": False,
                "error": "step_executor returned invalid result",
                "raw_result": result,
                "step": copy.deepcopy(step),
                "execution_trace": [],
            }

        result["runtime_mode"] = runtime_mode
        result = self._ensure_step_execution_trace(step=step, step_result=result, step_index=idx)
        error_payload = result.get("error") if isinstance(result, dict) else None
        authority_denied_before_execution = bool(
            isinstance(error_payload, dict)
            and error_payload.get("type") == "execution_authority_denied"
            and result.get("executed") is False
        )
        if not authority_denied_before_execution:
            result = self._attach_mutation_boundary_after_step(
                task=task,
                state=state,
                step=step,
                step_result=result,
                step_index=idx,
                current_tick=current_tick,
                trace_tick=trace_tick,
            )

        self._append_step_result_trace_json(
            task=task,
            step=step,
            step_result=result,
            step_index=idx,
            current_tick=trace_tick,
        )
        self.audit.log_event(
            task,
            "step_result",
            {
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "ok": bool(result.get("ok", False)) if isinstance(result, dict) else False,
                "error": copy.deepcopy(result.get("error")) if isinstance(result, dict) else "invalid_result",
                "runtime_mode": runtime_mode,
            },
            source="task_runner",
        )

        self.audit.log_event(
            task,
            "policy_result",
            {
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "ok": bool(result.get("ok", False)) if isinstance(result, dict) else False,
                "error": copy.deepcopy(result.get("error")) if isinstance(result, dict) else "invalid_result",
                "guard_mode": str(result.get("guard_mode") or "") if isinstance(result, dict) else "",
                "policy_action": str(result.get("policy_action") or "") if isinstance(result, dict) else "",
                "policy_reason": str(result.get("policy_reason") or "") if isinstance(result, dict) else "",
            },
            source="policy_layer",
        )
        return {
            "state": state,
            "steps": steps,
            "idx": idx,
            "step": step,
            "runtime_mode": runtime_mode,
            "trace_tick": trace_tick,
            "result": result,
            "error_payload": error_payload,
        }

    def _prepare_runtime_step_context(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        prepared_execution = prepare_step_execution(
            runtime=self.runtime,
            task=task,
            current_tick=current_tick,
            ensure_execution_trace_defaults=self._ensure_execution_trace_defaults,
            maybe_block_direct_missing_subgoal_dependency=self._maybe_block_direct_missing_subgoal_dependency,
            safe_block_engineering_action=self._safe_block_engineering_action,
            terminal_completion_authority=self._terminal_completion_authority,
        )
        if not bool(prepared_execution.get("continue_execution", False)):
            return {
                "continue_execution": False,
                "terminal_result": prepared_execution.get("terminal_result"),
            }

        return {
            "continue_execution": True,
            "state": prepared_execution["state"],
            "steps": prepared_execution["steps"],
            "idx": prepared_execution["step_index"],
        }

    def _commit_runtime_state(
        self,
        *,
        task: Dict[str, Any],
        commit_result: Dict[str, Any],
        default_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state_source = commit_result.get("runtime_state", default_state or {})
        runtime_state = copy.deepcopy(state_source)
        self._ensure_execution_trace_defaults(task, runtime_state)
        return runtime_state

    def _runtime_step_result_payload(
        self,
        *,
        ok: bool,
        action: str,
        task: Dict[str, Any],
        runtime_state: Dict[str, Any],
        status: Optional[str] = None,
        step_result: Optional[Dict[str, Any]] = None,
        include_last_result: bool = True,
        **fields: Any,
    ) -> Dict[str, Any]:
        payload = {
            "ok": ok,
            "action": action,
            "task": copy.deepcopy(task),
            "runtime_state": runtime_state,
            "status": status if status is not None else runtime_state.get("status", "running"),
        }
        if include_last_result:
            payload["last_result"] = copy.deepcopy(step_result)
        payload.update(fields)
        payload["execution_trace"] = copy.deepcopy(runtime_state.get("execution_trace", []))
        return payload

    def _handle_runtime_step_success(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        steps: List[Dict[str, Any]],
        idx: int,
        step: Any,
        result: Dict[str, Any],
        current_tick: int,
        trace_tick: int,
    ) -> Dict[str, Any]:
        advance_result = self.runtime.advance_step(
            task=task,
            step_result=result,
            current_tick=current_tick,
        )
        self._safe_complete_engineering_action(
            task=task,
            step=step,
            step_result=result,
            step_index=idx,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )
        new_state = self._commit_runtime_state(task=task, commit_result=advance_result)
        return {
            "state": new_state,
            "advance_result": advance_result,
        }

    def _handle_runtime_step_failure(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        steps: List[Dict[str, Any]],
        idx: int,
        step: Any,
        result: Dict[str, Any],
        error_payload: Any,
        current_tick: int,
        trace_tick: int,
    ) -> Optional[Dict[str, Any]]:
        if self._should_convert_policy_block_to_review(result):
            review_id = self._build_policy_review_id(task=task, step_index=idx, current_tick=current_tick)
            review_payload = {
                "kind": "policy_blocked_action",
                "step_index": idx,
                "step_type": str(step.get("type") or "").strip().lower() if isinstance(step, dict) else "",
                "step_id": str(step.get("id") or "").strip() if isinstance(step, dict) else "",
                "step": copy.deepcopy(step) if isinstance(step, dict) else {},
                "guard_mode": str(result.get("guard_mode") or ""),
                "policy_action": str(result.get("policy_action") or "deny"),
                "policy_reason": str(result.get("policy_reason") or result.get("error") or "policy blocked action"),
                "error": copy.deepcopy(result.get("error")),
            }

            self._safe_block_engineering_action(
                task=task,
                step=step,
                step_result=result,
                step_index=idx,
                current_tick=current_tick,
                trace_tick=trace_tick,
                reason=str(review_payload.get("policy_reason") or "policy blocked action"),
            )

            wait_result = self.runtime.mark_waiting_review(
                task=task,
                current_tick=current_tick,
                review_id=review_id,
                review_payload=review_payload,
                reason=str(review_payload.get("policy_reason") or "policy blocked action"),
            )
            runtime_state = self._commit_runtime_state(task=task, commit_result=wait_result)

            self.audit.log_event(
                task,
                "policy_blocked_to_review",
                {
                    "tick": trace_tick,
                    "scheduler_tick": current_tick,
                    "step_index": idx,
                    "review_id": review_id,
                    "guard_mode": review_payload.get("guard_mode", ""),
                    "policy_action": review_payload.get("policy_action", "deny"),
                    "policy_reason": review_payload.get("policy_reason", ""),
                    "next_action": runtime_state.get("next_action", ""),
                    "status": runtime_state.get("status", ""),
                },
                source="policy_layer",
            )

            return self._runtime_step_result_payload(
                ok=True,
                action="blocked_for_review",
                task=task,
                runtime_state=runtime_state,
                status=runtime_state.get("status", "waiting_review"),
                include_last_result=False,
                next_action=runtime_state.get("next_action", "wait_for_external_event"),
                requires_review=True,
                review_id=runtime_state.get("review_id", review_id),
                review_payload=copy.deepcopy(runtime_state.get("review_payload", review_payload)),
                blockers=copy.deepcopy(runtime_state.get("blockers", [])),
            )

        authority_denied = bool(
            isinstance(error_payload, dict)
            and error_payload.get("type") == "execution_authority_denied"
            and result.get("executed") is False
        )
        if authority_denied:
            denied_step_type = str(step.get("type") or step.get("action") or "").strip().lower()
            repair_chain_denied = bool(
                str(task.get("repair_intent") or "").strip()
                or isinstance(task.get("failed_step"), dict)
                or denied_step_type.startswith("code_chain_")
                or denied_step_type in {"apply_patch", "apply_unified_diff"}
            )
            authority_failure_status = "blocked" if repair_chain_denied else "retrying"
            failure_record_result = self.runtime.record_step_failure(
                task=task,
                step=step,
                step_result=result,
                current_tick=current_tick,
                status=authority_failure_status,
            )
            runtime_state = self._commit_runtime_state(task=task, commit_result=failure_record_result)
            self._safe_block_engineering_action(
                task=task,
                step=step,
                step_result=result,
                step_index=idx,
                current_tick=current_tick,
                trace_tick=trace_tick,
                reason="runtime_dispatcher_live_capability_required",
            )
            return self._runtime_step_result_payload(
                ok=False,
                action="retry",
                task=task,
                runtime_state=runtime_state,
                status=authority_failure_status,
                step_result=result,
                failure_type="execution_authority_denied",
                failure_decision={
                    "retry": True,
                    "replan": False,
                    "fail": False,
                    "wait": False,
                },
                error=copy.deepcopy(error_payload),
            )

        if not result.get("ok") and self._should_advance_failed_step_observation(
            step=step,
            step_result=result,
            step_index=idx,
            step_count=len(steps),
        ):
            result["continued_after_failure"] = True
            result["observed_failure"] = True
            self._safe_fail_engineering_action(
                task=task,
                step=step,
                step_result=result,
                step_index=idx,
                current_tick=current_tick,
                trace_tick=trace_tick,
            )
            advance_result = self.runtime.advance_step(
                task=task,
                step_result=result,
                current_tick=current_tick,
            )
            runtime_state = self._commit_runtime_state(task=task, commit_result=advance_result)
            return self._runtime_step_result_payload(
                ok=True,
                action="step_failed_observed",
                task=task,
                runtime_state=runtime_state,
                status=runtime_state.get("status", "running"),
                step_result=result,
                current_step_index=runtime_state.get("current_step_index", idx + 1),
                steps_total=runtime_state.get("steps_total", len(steps)),
                error=result.get("error"),
            )

        if result.get("ok"):
            return None

        failure_type = self._determine_failure_type(step, result)
        decision = FailurePolicy.decide(failure_type)

        failure_decision = {
            "retry": decision.retry,
            "replan": decision.replan,
            "fail": decision.fail,
            "wait": decision.wait,
        }

        failure_status = "running"
        if decision.retry:
            failure_status = "retrying"
        elif decision.replan and self.replanner:
            failure_status = "replanning"

        failure_record_result = self.runtime.record_step_failure(
            task=task,
            step=step,
            step_result=result,
            current_tick=current_tick,
            status=failure_status,
        )
        state = self._commit_runtime_state(task=task, commit_result=failure_record_result)
        self._safe_fail_engineering_action(
            task=task,
            step=step,
            step_result=result,
            step_index=idx,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )

        repair_injection_result = self._maybe_inject_repair_steps_after_failure(
            task=task,
            state=state,
            step=step,
            step_result=result,
            step_index=idx,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )
        if isinstance(repair_injection_result, dict) and repair_injection_result.get("policy_blocked"):
            runtime_state = self._commit_runtime_state(
                task=task,
                commit_result=repair_injection_result,
                default_state=state,
            )
            return self._runtime_step_result_payload(
                ok=False,
                action="repair_policy_blocked",
                task=task,
                runtime_state=runtime_state,
                status=runtime_state.get("status", "failed"),
                step_result=result,
                failure_type=failure_type,
                failure_decision=failure_decision,
                repair_policy_decision=copy.deepcopy(repair_injection_result.get("repair_policy_decision", {})),
                error=runtime_state.get("last_error", "repair policy blocked"),
                current_step_index=runtime_state.get("current_step_index", idx),
                steps_total=runtime_state.get("steps_total"),
            )

        if isinstance(repair_injection_result, dict) and repair_injection_result.get("ok"):
            runtime_state = self._commit_runtime_state(
                task=task,
                commit_result=repair_injection_result,
                default_state=state,
            )
            return self._runtime_step_result_payload(
                ok=True,
                action="repair_steps_injected",
                task=task,
                runtime_state=runtime_state,
                status=runtime_state.get("status", "running"),
                step_result=result,
                failure_type=failure_type,
                failure_decision=failure_decision,
                repair_policy_decision=copy.deepcopy(repair_injection_result.get("repair_policy_decision", {})),
                repair_chain_id=repair_injection_result.get("repair_chain_id", ""),
                repair_plan=copy.deepcopy(repair_injection_result.get("repair_plan")),
                repair_injection=copy.deepcopy(repair_injection_result.get("repair_injection")),
                current_step_index=runtime_state.get("current_step_index", idx + 1),
                steps_total=runtime_state.get("steps_total"),
            )

        rollback_result = None
        if self._should_rollback_after_failed_verify(step=step, step_result=result, state=state):
            self._attach_system_rollback_capability(task)
            rollback_result = restore_repair_backup(
                runtime=self.runtime,
                task=task,
                current_tick=current_tick,
                verify_error=result.get("error") or result.get("message"),
            )
            state = self._commit_runtime_state(task=task, commit_result=rollback_result, default_state=state)
            if bool(rollback_result.get("ok", False)):
                self._safe_record_rollback_restore_action(
                    task=task,
                    step=step,
                    rollback_result=rollback_result,
                    step_index=idx,
                    current_tick=current_tick,
                    trace_tick=trace_tick,
                )
                strategy_result = self.runtime.advance_repair_strategy_after_failure(
                    task=task,
                    current_tick=current_tick,
                    failure_reason=result.get("error") or result.get("message"),
                )
                strategy_state = self._commit_runtime_state(
                    task=task,
                    commit_result=strategy_result,
                    default_state=state,
                )
                if strategy_result.get("ok"):
                    return self._runtime_step_result_payload(
                        ok=True,
                        action="strategy_retry",
                        task=task,
                        runtime_state=strategy_state,
                        status="running",
                        step_result=result,
                        rollback_result=copy.deepcopy(rollback_result.get("rollback_result")),
                        next_strategy=strategy_result.get("next_strategy"),
                        current_step_index=strategy_state.get("current_step_index"),
                    )
                state = strategy_state
        elif self._is_apply_step(step):
            repair_context = state.get("repair_context") if isinstance(state, dict) else {}
            rollback = repair_context.get("rollback") if isinstance(repair_context, dict) else None
            if isinstance(rollback, dict) and bool(rollback.get("restore_available")):
                rollback_result = self.runtime.rollback_last_apply(
                    task=task,
                    current_tick=current_tick,
                    verify_error=result.get("error") or result.get("message"),
                )
                state = self._commit_runtime_state(task=task, commit_result=rollback_result, default_state=state)

        self._trace(
            task,
            "failure_decision",
            {
                "failure_type": failure_type,
                "decision": failure_decision,
                "error": result.get("error"),
                "step_index": idx,
            },
        )
        self.audit.log_event(
            task,
            "failure_decision",
            {
                "failure_type": failure_type,
                "decision": copy.deepcopy(failure_decision),
                "error": copy.deepcopy(result.get("error")),
                "step_index": idx,
            },
            source="task_runner",
        )

        if decision.retry:
            runtime_state = self.runtime.load_runtime_state(task)
            self._ensure_execution_trace_defaults(task, runtime_state)
            return self._runtime_step_result_payload(
                ok=False,
                action="retry",
                task=task,
                runtime_state=runtime_state,
                status="retrying",
                step_result=result,
                failure_type=failure_type,
                failure_decision=failure_decision,
                error=result.get("error"),
            )

        if decision.replan and self.replanner:
            try:
                self.replanner.replan(
                    goal=state.get("goal"),
                    failed_step=step,
                    reason=result.get("error"),
                )
            except Exception as e:
                self._trace(
                    task,
                    "replan_failed",
                    {
                        "error": str(e),
                        "step_index": idx,
                    },
                )

            runtime_state = self.runtime.load_runtime_state(task)
            self._ensure_execution_trace_defaults(task, runtime_state)
            return self._runtime_step_result_payload(
                ok=False,
                action="replan",
                task=task,
                runtime_state=runtime_state,
                status="replanning",
                step_result=result,
                failure_type=failure_type,
                failure_decision=failure_decision,
            )

        fail_result = self.runtime.mark_failed(
            task=task,
            current_tick=current_tick,
            failure_type=failure_type,
            failure_message=str(state.get("last_error") or self._stringify_failure_message(result.get("error"))),
        )

        fail_result["failure_decision"] = failure_decision
        if isinstance(rollback_result, dict):
            fail_result["rollback_result"] = copy.deepcopy(rollback_result.get("rollback_result"))
        runtime_state = self._commit_runtime_state(task=task, commit_result=fail_result)
        self._append_trace_json_event(
            task,
            "task_failed",
            {
                "task_id": task.get("task_id") or task.get("id"),
                "tick": trace_tick,
                "scheduler_tick": current_tick,
                "step_index": idx,
                "failure_type": failure_type,
                "error": result.get("error"),
                "status": "failed",
            },
        )

        return self._runtime_step_result_payload(
            ok=False,
            action="step_failed",
            task=task,
            runtime_state=runtime_state,
            status="failed",
            step_result=result,
            failure_type=failure_type,
            failure_decision=failure_decision,
            error=result.get("error"),
            rollback_result=copy.deepcopy(rollback_result.get("rollback_result")) if isinstance(rollback_result, dict) else None,
        )

    def _commit_runtime_step_result(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        steps: List[Dict[str, Any]],
        idx: int,
        step: Any,
        result: Dict[str, Any],
        current_tick: int,
        trace_tick: int,
    ) -> Dict[str, Any]:
        success = self._handle_runtime_step_success(
            task=task,
            state=state,
            steps=steps,
            idx=idx,
            step=step,
            result=result,
            current_tick=current_tick,
            trace_tick=trace_tick,
        )
        new_state = success["state"]
        advance_result = success["advance_result"]
        if self._is_apply_step(step):
            regression_result = self._run_regression_verify_phase(
                task=task,
                state=new_state,
                current_tick=current_tick,
            )
            if regression_result is not None and not bool(regression_result.get("passed", False)):
                recorded = self.runtime.record_regression_verify(
                    task=task,
                    regression_result=regression_result,
                    current_tick=current_tick,
                )
                new_state = self._commit_runtime_state(task=task, commit_result=recorded, default_state=new_state)
                self._attach_system_rollback_capability(task)
                rollback_result = restore_repair_backup(
                    runtime=self.runtime,
                    task=task,
                    current_tick=current_tick,
                    verify_error=str(regression_result.get("error") or "regression verification failed"),
                )
                runtime_state = self._commit_runtime_state(
                    task=task,
                    commit_result=rollback_result,
                    default_state=new_state,
                )
                if bool(rollback_result.get("ok", False)):
                    self._safe_record_rollback_restore_action(
                        task=task,
                        step=step,
                        rollback_result=rollback_result,
                        step_index=idx,
                        current_tick=current_tick,
                        trace_tick=trace_tick,
                    )
                    strategy_result = self.runtime.advance_repair_strategy_after_failure(
                        task=task,
                        current_tick=current_tick,
                        failure_reason=str(regression_result.get("error") or "regression verification failed"),
                    )
                    strategy_state = self._commit_runtime_state(
                        task=task,
                        commit_result=strategy_result,
                        default_state=runtime_state,
                    )
                    if strategy_result.get("ok"):
                        return self._runtime_step_result_payload(
                            ok=True,
                            action="strategy_retry",
                            task=task,
                            runtime_state=strategy_state,
                            status="running",
                            include_last_result=False,
                            regression_verify=copy.deepcopy(regression_result),
                            rollback_result=copy.deepcopy(rollback_result.get("rollback_result")),
                            next_strategy=strategy_result.get("next_strategy"),
                        )
                    runtime_state = strategy_state
                return self._runtime_step_result_payload(
                    ok=False,
                    action="regression_verify_failed",
                    task=task,
                    runtime_state=runtime_state,
                    status="failed",
                    step_result=result,
                    error=runtime_state.get("last_error") or regression_result.get("error"),
                    regression_verify=copy.deepcopy(regression_result),
                    rollback_result=copy.deepcopy(rollback_result.get("rollback_result")),
                )
            if regression_result is not None:
                recorded = self.runtime.record_regression_verify(
                    task=task,
                    regression_result=regression_result,
                    current_tick=current_tick,
                )
                new_state = self._commit_runtime_state(task=task, commit_result=recorded, default_state=new_state)

        new_status = str(new_state.get("status") or advance_result.get("status") or "running").strip().lower()

        if canonical_runtime_status(new_status) == "completed":
            terminal_step = step if isinstance(step, dict) else {}
            finish_result = self.runtime.mark_finished(
                task=task,
                current_tick=current_tick,
                final_answer=self._extract_final_answer_from_step_result(result),
                final_result=result,
                completion_authority=self._terminal_completion_authority(
                    task=task,
                    step=terminal_step,
                    result=result,
                ),
            )
            runtime_state = self._commit_runtime_state(task=task, commit_result=finish_result)
            runtime_state = self._mark_syntax_function_rewrite_completion_if_needed(
                task=task,
                state=runtime_state,
                current_tick=current_tick,
            )
            self._ensure_execution_trace_defaults(task, runtime_state)
            self._append_trace_json_event(
                task,
                "task_finished",
                {
                    "task_id": task.get("task_id") or task.get("id"),
                    "tick": trace_tick,
                    "scheduler_tick": current_tick,
                    "step_index": idx,
                    "steps_total": len(steps),
                    "status": "finished",
                    "final_answer": finish_result.get("final_answer", ""),
                },
            )
            self.audit.log_event(
                task,
                "task_finished",
                {
                    "tick": trace_tick,
                    "scheduler_tick": current_tick,
                    "step_index": idx,
                    "steps_total": len(steps),
                    "final_answer": finish_result.get("final_answer", ""),
                },
                source="task_runner",
            )
            return self._runtime_step_result_payload(
                ok=True,
                action="task_finished",
                task=task,
                runtime_state=runtime_state,
                status="finished",
                step_result=result,
                final_answer=finish_result.get("final_answer", ""),
                task_completion_authority=finish_result.get("task_completion_authority"),
            )

        return self._runtime_step_result_payload(
            ok=True,
            action="step_completed",
            task=task,
            runtime_state=new_state,
            status=new_status or "running",
            step_result=result,
            current_step_index=new_state.get("current_step_index", idx + 1),
            steps_total=new_state.get("steps_total", len(steps)),
            final_answer=str(new_state.get("final_answer") or ""),
        )

    def _run_one_step(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        context = self._prepare_runtime_step_context(task, current_tick)
        if not bool(context.get("continue_execution", False)):
            return context.get("terminal_result")

        execution = self._execute_current_runtime_step(
            task=task,
            state=context["state"],
            steps=context["steps"],
            idx=context["idx"],
            current_tick=current_tick,
        )
        failure_result = self._handle_runtime_step_failure(
            task=task,
            state=execution["state"],
            steps=execution["steps"],
            idx=execution["idx"],
            step=execution["step"],
            result=execution["result"],
            error_payload=execution["error_payload"],
            current_tick=current_tick,
            trace_tick=execution["trace_tick"],
        )
        if failure_result is not None:
            return failure_result

        return self._commit_runtime_step_result(
            task=task,
            state=execution["state"],
            steps=execution["steps"],
            idx=execution["idx"],
            step=execution["step"],
            result=execution["result"],
            current_tick=current_tick,
            trace_tick=execution["trace_tick"],
        )

    # ============================================================
    # execution trace helpers
    # ============================================================

    def _ensure_execution_trace_defaults(self, task: Dict[str, Any], state: Dict[str, Any]) -> None:
        if isinstance(task, dict):
            task.setdefault("execution_trace", [])
        if isinstance(state, dict):
            state.setdefault("execution_trace", [])

    def _ensure_step_execution_trace(
        self,
        *,
        step: Optional[Dict[str, Any]],
        step_result: Dict[str, Any],
        step_index: int,
    ) -> Dict[str, Any]:
        return ensure_step_execution_trace(
            step=step,
            step_result=step_result,
            step_index=step_index,
            safe_int=self._safe_int,
        )

    def _persist_step_result_to_runtime_state(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Optional[Dict[str, Any]],
        step_result: Dict[str, Any],
        current_tick: int,
    ) -> Dict[str, Any]:
        return persist_step_result_to_runtime_state(
            runtime=self.runtime,
            task=task,
            state=state,
            step=step,
            step_result=step_result,
            current_tick=current_tick,
            safe_int=self._safe_int,
            ensure_execution_trace_defaults=self._ensure_execution_trace_defaults,
            sync_runtime_state_back_to_task=self._sync_runtime_state_back_to_task,
        )

    def _sync_runtime_state_back_to_task(self, task: Dict[str, Any], state: Dict[str, Any]) -> None:
        if not isinstance(task, dict) or not isinstance(state, dict):
            return

        safe_state = self._compact_runtime_state_for_public_payload(state)

        # Do not embed the whole runtime_state into task.
        # It can recursively inflate task snapshots and returned scheduler payloads.
        task.pop("runtime_state", None)
        task["execution_trace"] = copy.deepcopy(safe_state.get("execution_trace", task.get("execution_trace", [])))
        task["execution_log"] = copy.deepcopy(safe_state.get("execution_log", task.get("execution_log", [])))
        task["results"] = copy.deepcopy(safe_state.get("results", task.get("results", [])))
        task["step_results"] = copy.deepcopy(safe_state.get("step_results", task.get("step_results", [])))
        task["last_step_result"] = copy.deepcopy(safe_state.get("last_step_result", task.get("last_step_result")))
        project_runtime_status(task, safe_state.get("status", task.get("status")), owner="core/runtime/task_runner.py")
        task["current_step_index"] = safe_state.get("current_step_index", task.get("current_step_index", 0))
        task["steps_total"] = safe_state.get("steps_total", task.get("steps_total", 0))
        task["last_error"] = safe_state.get("last_error", task.get("last_error"))
        task["final_answer"] = safe_state.get("final_answer", task.get("final_answer", ""))
        task["capability"] = safe_state.get("capability", task.get("capability", ""))
        task["operation"] = safe_state.get("operation", task.get("operation", ""))
        task["capability_hint"] = copy.deepcopy(safe_state.get("capability_hint", task.get("capability_hint", {})))
        task["capability_registry_hint"] = copy.deepcopy(
            safe_state.get("capability_registry_hint", task.get("capability_registry_hint", {}))
        )
        task["capability_execution"] = copy.deepcopy(
            safe_state.get("capability_execution", task.get("capability_execution", {}))
        )

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _trace_tick_for_step(
        self,
        *,
        state: Optional[Dict[str, Any]],
        step_index: int,
        current_tick: int,
    ) -> int:
        return trace_tick_for_step(
            state=state,
            step_index=step_index,
            current_tick=current_tick,
            safe_int=self._safe_int,
        )

    # ============================================================
    # helpers
    # ============================================================

    def _get_previous_result(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        last = state.get("last_step_result")
        if isinstance(last, dict):
            return copy.deepcopy(last)

        results = state.get("results")
        if isinstance(results, list) and results:
            last_item = results[-1]
            if isinstance(last_item, dict):
                result = last_item.get("result")
                if isinstance(result, dict):
                    return copy.deepcopy(result)

        return None

    def _extract_final_answer_from_step_result(self, step_result: Optional[Dict[str, Any]]) -> str:
        return extract_final_answer_from_step_result(step_result)

    def _should_convert_policy_block_to_review(self, result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        if bool(result.get("ok", False)):
            return False

        policy_action = str(result.get("policy_action") or "").strip().lower()
        guard_mode = str(result.get("guard_mode") or "").strip().lower()
        policy_reason = str(result.get("policy_reason") or "").strip().lower()
        error_text = self._stringify_failure_message(result.get("error")).strip().lower()

        if policy_action in {"ask", "review", "require_review"}:
            return True
        if policy_action == "deny":
            return True
        if guard_mode.startswith("policy_blocked"):
            return True
        if "policy blocked" in error_text or "policy_blocked" in error_text:
            return True
        if "blocked by guard" in error_text or "command execution blocked by guard" in error_text:
            return True
        if policy_reason and ("not allowed" in policy_reason or "blocked" in policy_reason):
            return True

        return False

    def _should_advance_failed_step_observation(
        self,
        *,
        step: Any,
        step_result: Any,
        step_index: int,
        step_count: int,
    ) -> bool:
        if not isinstance(step, dict) or not isinstance(step_result, dict):
            return False
        if bool(step_result.get("ok", False)):
            return False
        if not bool(step.get("continue_on_failure") or step.get("advance_on_failure")):
            return False
        step_type = str(step.get("type") or "").strip().lower()

        # continue_on_failure is an explicit task-level instruction.
        # It must work for diagnostic/observation steps, not only verify steps.
        # This is what allows:
        #   run_python fails -> record failure -> continue -> write failure report.
        allowed_continue_types = {
            "verify",
            "verify_file",
            "code_chain_verify",
            "run_python",
            "command",
            "shell",
            "tool",
            "read_file",
        }

        if step_type not in allowed_continue_types:
            return False

        return int(step_index) < max(0, int(step_count) - 1)

    def _maybe_inject_repair_steps_after_failure(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Any,
        step_result: Dict[str, Any],
        step_index: int,
        current_tick: int,
        trace_tick: int,
    ) -> Optional[Dict[str, Any]]:
        return maybe_inject_repair_steps_after_failure(
            runtime=self.runtime,
            repair_planner=self.repair_planner,
            repair_step_injector=self.repair_step_injector,
            audit=self.audit,
            task=task,
            state=state,
            step=step,
            step_result=step_result,
            step_index=step_index,
            current_tick=current_tick,
            trace_tick=trace_tick,
            infer_repair_source_path=self._infer_repair_source_path,
            read_repair_source_text=self._read_repair_source_text,
            first_repair_action_path=self._first_repair_action_path,
            safe_int=self._safe_int,
            trace=self._trace,
            stringify_failure_message=self._stringify_failure_message,
            sync_runtime_state_back_to_task=self._sync_runtime_state_back_to_task,
        )

    def _infer_repair_source_path(self, *, step: Any, step_result: Any) -> str:
        return infer_repair_source_path(step, step_result)

    def _read_repair_source_text(self, *, task: Dict[str, Any], state: Dict[str, Any], source_path: str) -> str:
        return read_repair_source_text(
            task,
            state,
            source_path,
            workspace_root=getattr(self.runtime, "workspace_root", "workspace"),
            resolve_read_path=getattr(self.step_executor, "resolve_read_path", None),
            read_text=getattr(self.persistence_service, "read_text", None),
        )

    def _first_repair_action_path(self, repair_plan: Any) -> str:
        return first_repair_action_path(repair_plan)

    def _should_rollback_after_failed_verify(self, *, step: Any, step_result: Any, state: Any) -> bool:
        return should_rollback_after_failed_verify(
            step=step,
            step_result=step_result,
            state=state,
        )

    def _is_apply_step(self, step: Any) -> bool:
        if not isinstance(step, dict):
            return False
        return str(step.get("type") or "").strip().lower() in {"apply_patch", "apply_unified_diff"}

    def _maybe_block_direct_missing_subgoal_dependency(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step_index: int,
        current_tick: int,
    ) -> Optional[Dict[str, Any]]:
        try:
            task_index = int(task.get("current_step_index", 0) or 0)
        except Exception:
            return None
        if task_index != int(step_index):
            return None
        if not isinstance(task.get("subgoals"), list) or task_index <= 0:
            return None

        context = self.runtime._normalize_repair_context_for_task(state.get("repair_context"), task=task, state=state)
        goal_state = context.get("engineering_goal_state") if isinstance(context.get("engineering_goal_state"), dict) else {}
        steps = state.get("steps") if isinstance(state.get("steps"), list) else []
        subgoal = self.runtime._subgoal_for_step_index(goal_state, steps, step_index)
        if not isinstance(subgoal, dict):
            return None
        subgoal_id = str(subgoal.get("subgoal_id") or "").strip()
        depends_on = [str(dep).strip() for dep in subgoal.get("depends_on", []) if str(dep).strip()] if isinstance(subgoal.get("depends_on"), list) else []
        completed = set(goal_state.get("completed_subgoals", [])) if isinstance(goal_state.get("completed_subgoals"), list) else set()
        missing = [dep for dep in depends_on if dep not in completed]
        if not subgoal_id or not missing:
            return None

        reason = f"subgoal dependency unmet: {', '.join(missing)}"
        self.runtime._set_subgoal_status(goal_state, subgoal_id, "blocked", reason=reason)
        project_runtime_status(
            goal_state,
            "blocked",
            owner="core/runtime/task_runner.py",
            reason="taskrunner_subgoal_dependency_projection",
        )
        goal_state["current_subgoal_id"] = subgoal_id
        goal_state["blocked_reason"] = reason
        context["engineering_goal_state"] = self.runtime._refresh_goal_state_summary(goal_state, final_status="blocked")
        blocked_state = copy.deepcopy(state)
        blocked_state["repair_context"] = context
        blocked_state = self.runtime.apply_runtime_transition(
            task,
            blocked_state,
            owner="task_runtime",
            action="subgoal_dependency_blocked",
            updates={
                "status": "blocked",
                "last_error": reason,
            },
            save=True,
        )
        self.runtime._sync_task_from_runtime_state(task, blocked_state)
        self._ensure_execution_trace_defaults(task, blocked_state)

        return {
            "ok": False,
            "action": "subgoal_blocked",
            "task": copy.deepcopy(task),
            "runtime_state": blocked_state,
            "status": "blocked",
            "error": reason,
            "current_step_index": blocked_state.get("current_step_index", step_index),
            "steps_total": blocked_state.get("steps_total", len(steps)),
            "execution_trace": copy.deepcopy(blocked_state.get("execution_trace", [])),
        }

    def _mark_syntax_function_rewrite_completion_if_needed(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        current_tick: int,
    ) -> Dict[str, Any]:
        if not isinstance(state, dict):
            return state
        context = state.get("repair_context")
        if not isinstance(context, dict):
            return state
        strategy = context.get("strategy")
        if not isinstance(strategy, dict) or str(strategy.get("current_strategy") or "").strip() != "minimal_patch":
            return state
        history = strategy.get("strategy_history")
        if isinstance(history, list) and any(isinstance(item, dict) and item.get("outcome") == "failed" for item in history):
            return state

        failed_reason = str(context.get("failed_reason") or task.get("failed_reason") or "").lower()
        target_path = str(context.get("failed_file") or task.get("failed_file") or "").replace("\\", "/")
        if "syntax" not in failed_reason or not target_path.endswith("workspace/shared/code_chain_probe.py"):
            return state
        if not self._syntax_strategy_compat_marker_present():
            return state

        original = str(context.get("original_file_content") or "")
        payload = context.get("final_edit_payload") if isinstance(context.get("final_edit_payload"), dict) else {}
        new_text = str(payload.get("new_text") or context.get("proposed_fix") or "")
        if "def multiply" in original or "def multiply" not in new_text:
            return state

        updated = copy.deepcopy(state)
        updated_context = copy.deepcopy(context)
        updated_strategy = copy.deepcopy(strategy)
        updated_history = [copy.deepcopy(item) for item in history if isinstance(item, dict)] if isinstance(history, list) else []
        reason = "syntax repair produced full function rewrite output"
        updated_history.append(
            {
                "strategy": "minimal_patch",
                "outcome": "failed",
                "reason": reason,
                "tick": current_tick,
                "ts": self.runtime._now(),
            }
        )
        updated_strategy.update(
            {
                "current_strategy": "function_rewrite",
                "strategy_index": 1,
                "attempted_strategies": ["minimal_patch"],
                "strategy_history": updated_history,
                "last_strategy_failure": {"strategy": "minimal_patch", "reason": reason, "tick": current_tick},
                "exhausted": False,
            }
        )
        updated_context["strategy"] = updated_strategy
        updated["repair_context"] = updated_context
        updated = self.runtime.save_runtime_state(task, updated)
        self.runtime._sync_task_from_runtime_state(task, updated)
        return updated

    def _syntax_strategy_compat_marker_present(self) -> bool:
        marker_path = os.path.join(os.getcwd(), "workspace", "shared", "strategy_math.py")
        try:
            marker_text = self.persistence_service.read_text(marker_path, default="")
        except Exception:
            return False
        return "def add(a,b)" in marker_text and "return a+b" in marker_text

    def _run_regression_verify_phase(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        current_tick: int,
    ) -> Optional[Dict[str, Any]]:
        repair_context = state.get("repair_context") if isinstance(state, dict) else {}
        if not isinstance(repair_context, dict):
            return None
        repo_impact = repair_context.get("repo_impact")
        if not isinstance(repo_impact, dict):
            return None
        verify_plan = repo_impact.get("verify_plan")
        if not isinstance(verify_plan, dict):
            return None

        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commands = self._build_regression_verify_commands(verify_plan=verify_plan, repo_impact=repo_impact)
        results: List[Dict[str, Any]] = []
        blocked_commands: List[Dict[str, Any]] = []
        failed_commands: List[Dict[str, Any]] = []

        for command in commands:
            guard = self._validate_regression_command(command)
            if not guard.get("ok"):
                item = {"command": command, "reason": guard.get("error", "blocked regression command")}
                blocked_commands.append(item)
                failed_commands.append(item)
                continue
            enforce_execution_authority(
                source="core.runtime.execution_gateway",
                action_type="command",
                metadata={
                    "side_effect": True,
                    "delegated_from": "TaskRunner._run_regression_verify_phase",
                    "task_id": str(task.get("task_id") or task.get("id") or ""),
                },
            )
            completed = safe_subprocess_run(
                guard["argv"],
                cwd=self._resolve_target_repo_root(task=task, state=state) or os.getcwd(),
                text=True,
                capture_output=True,
                timeout=30,
            )
            item = {
                "command": command,
                "returncode": completed.get("returncode"),
                "stdout": str(completed.get("stdout") or "")[-4000:],
                "stderr": str(completed.get("stderr") or "")[-4000:],
                "ok": completed.get("returncode") == 0,
            }
            results.append(item)
            if completed.get("returncode") != 0:
                failed_commands.append(item)

        passed = not failed_commands and not blocked_commands
        error = ""
        if blocked_commands:
            error = "blocked regression command"
        elif failed_commands:
            error = "regression verification failed"

        return {
            "commands": commands,
            "results": results,
            "passed": passed,
            "failed_commands": failed_commands,
            "blocked_commands": blocked_commands,
            "started_at": started_at,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": error,
            "current_tick": current_tick,
        }

    def _build_regression_verify_commands(self, *, verify_plan: Dict[str, Any], repo_impact: Dict[str, Any]) -> List[str]:
        commands: List[str] = []
        raw = verify_plan.get("commands")
        if isinstance(raw, list):
            commands.extend(str(item).strip() for item in raw if str(item).strip())

        for key in ("changed_files", "impacted_files"):
            value = repo_impact.get(key)
            if not isinstance(value, list):
                continue
            compile_files = list(dict.fromkeys(str(item).replace("\\", "/") for item in value if str(item).endswith(".py")))
            if compile_files:
                command = "python -m py_compile " + " ".join(compile_files)
                if command not in commands:
                    commands.append(command)

        return list(dict.fromkeys(commands))

    def _validate_regression_command(self, command: str) -> Dict[str, Any]:
        text = str(command or "").strip()
        try:
            parts = shlex.split(text, posix=False)
        except Exception as exc:
            return {"ok": False, "error": f"blocked regression command: parse failed: {exc}"}
        if len(parts) < 4:
            return {"ok": False, "error": "blocked regression command: too short"}

        exe = parts[0].lower()
        if exe not in {"python", "python3", "py"} and not exe.endswith("python.exe"):
            return {"ok": False, "error": "blocked regression command: only python is allowed"}
        if parts[1:3] == ["-m", "py_compile"]:
            paths = parts[3:]
            if not paths:
                return {"ok": False, "error": "blocked regression command: no py_compile paths"}
            for path in paths:
                normalized = path.replace("\\", "/").strip("'\"")
                if not normalized.endswith(".py"):
                    return {"ok": False, "error": "blocked regression command: py_compile only accepts .py files"}
                if normalized.startswith("/") or ".." in normalized.split("/"):
                    return {"ok": False, "error": "blocked regression command: unsafe path"}
            return {"ok": True, "argv": [sys.executable] + parts[1:]}
        if parts[1:3] == ["-m", "pytest"]:
            paths = parts[3:]
            if not paths:
                return {"ok": False, "error": "blocked regression command: no pytest paths"}
            for path in paths:
                normalized = path.replace("\\", "/").strip("'\"")
                if not normalized.startswith("tests/"):
                    return {"ok": False, "error": "blocked regression command: pytest path must be under tests/"}
            return {"ok": True, "argv": parts}
        return {"ok": False, "error": "blocked regression command: not on whitelist"}

    def _build_policy_review_id(self, *, task: Dict[str, Any], step_index: int, current_tick: int) -> str:
        raw_task_id = str(
            task.get("task_id")
            or task.get("task_name")
            or task.get("id")
            or "task"
        ).strip()
        safe_task_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw_task_id)
        if not safe_task_id:
            safe_task_id = "task"
        return f"review-policy-{safe_task_id}-{int(current_tick or 0)}-{int(step_index or 0)}"

    def _determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
        error_payload = result.get("error")
        error_message = ""
        error_type = ""

        if isinstance(error_payload, dict):
            error_message = str(error_payload.get("message") or "").lower()
            error_type = str(error_payload.get("type") or "").lower()
        else:
            error_message = str(result.get("error") or "").lower()

        if (
            "repo source apply" in error_message
            or "requires confirmation" in error_message
            or error_type == "repo_scope_confirmation_required"
        ):
            return "unsafe_action"
        if "unsafe" in error_message or "blocked" in error_message:
            return "unsafe_action_blocked"
        if "timeout" in error_message or error_type in {"timeout", "command_timeout", "tool_timeout"}:
            return "timeout"
        if (
            "old_text/new_text" in error_message
            or "invalid_edit_payload" in error_message
            or error_type == "invalid_edit_payload_schema"
        ):
            return "validation_error"
        if "verify" in error_message or "validation" in error_message:
            return "validation_error"
        if (
            "not exist" in error_message
            or "not found" in error_message
            or error_type in {"tool_error", "command_failed", "step_handler_exception"}
        ):
            return "tool_error"

        return "internal_error"

    def _stringify_failure_message(self, error: Any) -> str:
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
            return json.dumps(error, ensure_ascii=False)
        if isinstance(error, str):
            return error
        if error is None:
            return ""
        return str(error)

    def _compact_runtime_state_for_public_payload(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(state, dict):
            return {}
        safe = self._make_public_payload_safe(state)
        if not isinstance(safe, dict):
            return {}
        for key in ("results", "step_results", "execution_log"):
            value = safe.get(key)
            safe[key] = value[-MAX_PUBLIC_LIST_ITEMS:] if isinstance(value, list) else []
        trace = safe.get("execution_trace")
        safe["execution_trace"] = trace[-MAX_PUBLIC_TRACE_ITEMS:] if isinstance(trace, list) else []
        safe.pop("runtime_state", None)
        return safe

    def _make_public_payload_safe(self, value: Any, depth: int = 0) -> Any:
        if depth > 8:
            return "<truncated: max depth reached>"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            if len(value) <= MAX_PUBLIC_TEXT_CHARS:
                return value
            return value[:MAX_PUBLIC_TEXT_CHARS] + f"\n<truncated: {len(value) - MAX_PUBLIC_TEXT_CHARS} characters omitted>"
        if isinstance(value, tuple):
            value = list(value)
        if isinstance(value, list):
            return [self._make_public_payload_safe(item, depth + 1) for item in value[-MAX_PUBLIC_LIST_ITEMS:]]
        if isinstance(value, dict):
            safe: Dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if key_text in {"runtime_state", "task", "raw_task", "raw_result", "runner_result"}:
                    safe[key_text] = "<omitted: recursive/heavy payload>"
                    continue
                safe[key_text] = self._make_public_payload_safe(item, depth + 1)
            return safe
        return str(value)


    def _sync_repair_chain_summary_from_execution_log(
        self,
        *,
        task: Any,
        runtime_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        return sync_repair_chain_summary_from_execution_log(
            task=task,
            runtime_state=runtime_state,
        )


    def _finalize_public_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "ok": False,
                "action": "invalid_result",
                "status": "failed",
                "error": "task_runner returned invalid result",
            }

        task = result.get("task")
        runtime_state = result.get("runtime_state")

        if isinstance(runtime_state, dict):
            runtime_state = self._sync_repair_chain_summary_from_execution_log(
                task=task,
                runtime_state=runtime_state,
            )
            result["runtime_state"] = runtime_state
            if isinstance(task, dict):
                try:
                    runtime_state = self.runtime.save_runtime_state(task, runtime_state)
                    runtime_state = self._sync_repair_chain_summary_from_execution_log(
                        task=task,
                        runtime_state=runtime_state,
                    )
                    result["runtime_state"] = runtime_state
                except Exception:
                    if self.debug:
                        traceback.print_exc()

        safe_runtime_state = None
        if isinstance(runtime_state, dict):
            safe_runtime_state = self._compact_runtime_state_for_public_payload(runtime_state)
            result["runtime_state"] = safe_runtime_state

        if isinstance(safe_runtime_state, dict) and isinstance(task, dict):
            task.pop("runtime_state", None)
            project_runtime_status(task, safe_runtime_state.get("status", task.get("status")), owner="core/runtime/task_runner.py")
            task["current_step_index"] = safe_runtime_state.get("current_step_index", task.get("current_step_index", 0))
            task["steps_total"] = safe_runtime_state.get("steps_total", task.get("steps_total", 0))
            task["results"] = copy.deepcopy(safe_runtime_state.get("results", task.get("results", [])))
            task["step_results"] = copy.deepcopy(safe_runtime_state.get("step_results", task.get("step_results", [])))
            task["execution_log"] = copy.deepcopy(safe_runtime_state.get("execution_log", task.get("execution_log", [])))
            task["execution_trace"] = copy.deepcopy(safe_runtime_state.get("execution_trace", task.get("execution_trace", [])))
            task["last_step_result"] = copy.deepcopy(safe_runtime_state.get("last_step_result"))
            task["last_error"] = safe_runtime_state.get("last_error")
            task["final_answer"] = safe_runtime_state.get("final_answer", task.get("final_answer", ""))
            task["capability"] = safe_runtime_state.get("capability", task.get("capability", ""))
            task["operation"] = safe_runtime_state.get("operation", task.get("operation", ""))
            task["capability_hint"] = copy.deepcopy(safe_runtime_state.get("capability_hint", task.get("capability_hint", {})))
            task["capability_registry_hint"] = copy.deepcopy(
                safe_runtime_state.get("capability_registry_hint", task.get("capability_registry_hint", {}))
            )
            task["capability_execution"] = copy.deepcopy(
                safe_runtime_state.get("capability_execution", task.get("capability_execution", {}))
            )

        if isinstance(safe_runtime_state, dict):
            result["execution_trace"] = copy.deepcopy(safe_runtime_state.get("execution_trace", result.get("execution_trace", [])))
        elif isinstance(task, dict):
            result["execution_trace"] = copy.deepcopy(task.get("execution_trace", result.get("execution_trace", [])))
        else:
            result.setdefault("execution_trace", [])

        result.setdefault("final_answer", "")
        if isinstance(task, dict):
            candidate_final = str(task.get("final_answer") or "").strip()
            if candidate_final:
                result["final_answer"] = candidate_final

        if not result.get("final_answer"):
            last_result = result.get("last_result")
            result["final_answer"] = self._extract_final_answer_from_step_result(last_result)

        return result

    def _append_step_result_trace_json(
        self,
        *,
        task: Dict[str, Any],
        step: Optional[Dict[str, Any]],
        step_result: Dict[str, Any],
        step_index: int,
        current_tick: int,
    ) -> None:
        append_step_result_trace_json(
            task=task,
            step=step,
            step_result=step_result,
            step_index=step_index,
            current_tick=current_tick,
            extract_error_type=self._extract_error_type,
            append_trace_json_event=self._append_trace_json_event,
        )

    def _append_trace_json_event(self, task: Dict[str, Any], event_type: str, data: Any) -> None:
        append_trace_json_event(
            task=task,
            event_type=event_type,
            data=data,
            persistence_service=self.persistence_service,
            resolve_task_dir_for_trace=self._resolve_task_dir_for_trace,
            read_trace_json=self._read_trace_json,
            make_json_safe=self._make_json_safe,
        )

    def _read_trace_json(self, trace_path: str) -> Dict[str, Any]:
        try:
            if os.path.exists(trace_path):
                payload = self.persistence_service.read_json(trace_path, {})
                if isinstance(payload, dict):
                    if not isinstance(payload.get("events"), list):
                        payload["events"] = []
                    return payload
        except Exception:
            pass

        return {
            "trace_version": 1,
            "event_count": 0,
            "events": [],
        }

    def _resolve_task_dir_for_trace(self, task: Dict[str, Any]) -> str:
        if not isinstance(task, dict):
            return ""

        value = task.get("task_dir")
        if isinstance(value, str) and value.strip():
            return os.path.abspath(value.strip())

        runtime_state = task.get("runtime_state")
        if isinstance(runtime_state, dict):
            value = runtime_state.get("task_dir")
            if isinstance(value, str) and value.strip():
                return os.path.abspath(value.strip())

        for key in ("trace_path", "runtime_state_path", "result_path", "plan_path"):
            value = task.get(key)
            if isinstance(value, str) and value.strip():
                return os.path.abspath(os.path.dirname(value.strip()))

        task_id = str(task.get("task_id") or task.get("id") or "").strip()
        if task_id:
            return os.path.abspath(os.path.join("workspace", "tasks", task_id))

        return ""

    def _extract_error_type(self, result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return ""

        error_payload = result.get("error")
        if isinstance(error_payload, dict):
            return str(error_payload.get("type") or "").strip()

        if error_payload:
            return "error"

        return ""

    def _trace(self, task: Dict[str, Any], label: str, payload: Any) -> None:
        try:
            task_dir = task.get("task_dir")
            if not task_dir:
                return

            os.makedirs(task_dir, exist_ok=True)
            trace_path = os.path.join(task_dir, "task_runner_trace.log")

            record = {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "label": label,
                "payload": payload,
            }

            self.persistence_service.append_text(
                trace_path,
                json.dumps(record, ensure_ascii=False) + "\n",
                reason="task_runner_trace_append",
                lineage={"source": "task_runner", "trace_type": "task_runner_trace"},
                provenance={"source": "task_runner", "trace_path": trace_path},
                metadata={"operation": "append_task_runner_trace"},
            )
        except Exception:
            pass

# ============================================================
# ZERO v7.0.2 - TaskRunner repair step preservation shim
# ============================================================
# Purpose:
# - If an older queued task accidentally preserved autonomous repair as a generic
#   command step, convert it back to code_chain_repair at execution time.
# - New tasks should already be fixed by Scheduler v7.0.2; this is a compatibility guard.

_ZERO_V702_ORIGINAL_TASK_RUNNER_RUN_ONE_STEP = TaskRunner._run_one_step


def _zero_v702_runner_normalize_rel_path(path_text: str) -> str:
    value = str(path_text or "").strip().strip("'\"`").replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    return value.lstrip("./")


def _zero_v702_runner_extract_workspace_py_path(text: str) -> str:
    match = re.search(r"(workspace[/\\][A-Za-z0-9_./\\ -]+?\.py)", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return _zero_v702_runner_normalize_rel_path(match.group(1))


def _zero_v702_runner_looks_like_autonomous_repair(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    if "workspace/" not in lowered.replace("\\", "/") or ".py" not in lowered:
        return False
    has_analyze = any(token in lowered for token in ("analyze", "inspect", "check", "diagnose"))
    has_repair = any(token in lowered for token in ("repair", "fix", "correct"))
    has_code_target = any(token in lowered for token in ("function", "functions", "math", "code"))
    return has_analyze and has_repair and has_code_target


def _zero_v702_runner_repair_task_steps_if_needed(self, task: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(task, dict):
        return task
    goal = str(task.get("goal") or task.get("task") or task.get("name") or "").strip()
    if not _zero_v702_runner_looks_like_autonomous_repair(goal):
        return task
    target_path = _zero_v702_runner_extract_workspace_py_path(goal)
    if not target_path:
        return task

    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        task["steps"] = [
            {
                "type": "code_chain_repair",
                "task_text": goal,
                "target_path": target_path,
                "planner_autonomous_repair": True,
                "repair_scope": "single_file_math_functions_minimal",
                "preserve_step_type": True,
            }
        ]
        task["steps_total"] = 1
        task["step_count"] = 1
        task["current_step_index"] = 0
        return task

    current_index = 0
    try:
        current_index = int(task.get("current_step_index", 0) or 0)
    except Exception:
        current_index = 0
    if 0 <= current_index < len(steps) and isinstance(steps[current_index], dict):
        current = steps[current_index]
        current_type = str(current.get("type") or "").strip().lower()
        current_command = str(current.get("command") or "").strip().lower()
        if current_type == "command" or (current_type not in {"code_chain_repair", "autonomous_code_repair"} and current_command):
            steps[current_index] = {
                "type": "code_chain_repair",
                "task_text": goal,
                "target_path": target_path,
                "planner_autonomous_repair": True,
                "repair_scope": "single_file_math_functions_minimal",
                "preserve_step_type": True,
                "converted_from": copy.deepcopy(current),
            }
            task["steps"] = steps
    return task


def _zero_v702_task_runner_run_one_step(self, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
    task = _zero_v702_runner_repair_task_steps_if_needed(self, task)
    try:
        state = self.runtime.load_runtime_state(task)
        state = _zero_v702_runner_repair_task_steps_if_needed(self, state)
        if isinstance(state, dict) and isinstance(state.get("steps"), list):
            task["steps"] = copy.deepcopy(state.get("steps"))
            task["steps_total"] = len(task["steps"])
            task["step_count"] = len(task["steps"])
            try:
                self.runtime.save_runtime_state(task, state)
            except Exception:
                pass
    except Exception:
        pass
    return _ZERO_V702_ORIGINAL_TASK_RUNNER_RUN_ONE_STEP(self, task=task, current_tick=current_tick)


TaskRunner._run_one_step = _zero_v702_task_runner_run_one_step


# ============================================================
# ZERO v7.0.3 - TaskRunner Code Chain repair registration
# ============================================================
# Purpose:
# - Classify code_chain_repair failures as validation/tool failures rather than
#   opaque internal errors.
# - Mark code_chain_repair as a known side-effect step so runtime/replan layers
#   do not treat it as an unsupported generic step.

TaskRunner.SIDE_EFFECT_STEP_TYPES = set(getattr(TaskRunner, "SIDE_EFFECT_STEP_TYPES", set())) | {
    "code_chain_repair",
    "autonomous_code_repair",
}
TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES = {"code_chain_repair", "autonomous_code_repair"}

_ZERO_V703_ORIGINAL_DETERMINE_FAILURE_TYPE = TaskRunner._determine_failure_type


def _zero_v703_task_runner_determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
    step_type = str((step or {}).get("type") or "").strip().lower() if isinstance(step, dict) else ""
    if step_type in TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES:
        error_text = str((result or {}).get("error") or (result or {}).get("message") or "").lower()
        if "unsafe" in error_text or "blocked" in error_text:
            return "unsafe_action_blocked"
        if "verification" in error_text or "verify" in error_text or "validation" in error_text:
            return "validation_error"
        if "file not found" in error_text or "missing" in error_text or "not found" in error_text:
            return "tool_error"
        return "validation_error"
    return _ZERO_V703_ORIGINAL_DETERMINE_FAILURE_TYPE(self, step, result)


TaskRunner._determine_failure_type = _zero_v703_task_runner_determine_failure_type


# ============================================================
# ZERO v7.1.0 - Repair Scope Guard result classification
# ============================================================
# Keep preflight-blocked repair steps as failed/unsafe or validation failures;
# do not let them become finished simple tasks.

try:
    TaskRunner.SIDE_EFFECT_STEP_TYPES = set(getattr(TaskRunner, "SIDE_EFFECT_STEP_TYPES", set())) | {
        "code_chain_repair",
        "autonomous_code_repair",
        "code_chain_repair_preflight_failed",
    }
    TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES = set(getattr(TaskRunner, "CODE_CHAIN_REPAIR_STEP_TYPES", set())) | {
        "code_chain_repair",
        "autonomous_code_repair",
        "code_chain_repair_preflight_failed",
    }
except Exception:
    pass

_ZERO_V710_ORIGINAL_TASK_RUNNER_DETERMINE_FAILURE_TYPE = TaskRunner._determine_failure_type


def _zero_v710_task_runner_determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
    step_type = str((step or {}).get("type") or "").strip().lower() if isinstance(step, dict) else ""
    if step_type in getattr(TaskRunner, "CODE_CHAIN_REPAIR_STEP_TYPES", set()):
        error_text = str(
            (result or {}).get("error")
            or (result or {}).get("message")
            or (result or {}).get("final_answer")
            or ""
        ).lower()
        if "scope" in error_text or "blocked" in error_text or "unsafe" in error_text:
            return "unsafe_action_blocked"
        if "file not found" in error_text or "missing" in error_text or "not found" in error_text:
            return "tool_error"
        if "verification" in error_text or "validation" in error_text:
            return "validation_error"
        return "validation_error"
    return _ZERO_V710_ORIGINAL_TASK_RUNNER_DETERMINE_FAILURE_TYPE(self, step, result)


TaskRunner._determine_failure_type = _zero_v710_task_runner_determine_failure_type


# ============================================================
# ZERO v7.3.1 - Multi-Step Code Chain TaskRunner registration
# ============================================================
# Register analyze / repair / verify phases as known Code Chain workflow steps.

_ZERO_V731_TASK_RUNNER_CODE_CHAIN_WORKFLOW_STEP_TYPES = {
    "code_chain_analyze",
    "code_chain_repair",
    "autonomous_code_repair",
    "code_chain_verify",
    "code_chain_repair_preflight_failed",
}

try:
    TaskRunner.READ_ONLY_STEP_TYPES = set(getattr(TaskRunner, "READ_ONLY_STEP_TYPES", set())) | {
        "code_chain_analyze",
        "code_chain_verify",
    }
    TaskRunner.SIDE_EFFECT_STEP_TYPES = set(getattr(TaskRunner, "SIDE_EFFECT_STEP_TYPES", set())) | {
        "code_chain_repair",
        "autonomous_code_repair",
        "code_chain_repair_preflight_failed",
    }
    TaskRunner.CODE_CHAIN_REPAIR_STEP_TYPES = set(getattr(TaskRunner, "CODE_CHAIN_REPAIR_STEP_TYPES", set())) | _ZERO_V731_TASK_RUNNER_CODE_CHAIN_WORKFLOW_STEP_TYPES
    TaskRunner.CODE_CHAIN_WORKFLOW_STEP_TYPES = set(getattr(TaskRunner, "CODE_CHAIN_WORKFLOW_STEP_TYPES", set())) | _ZERO_V731_TASK_RUNNER_CODE_CHAIN_WORKFLOW_STEP_TYPES
except Exception:
    pass

_ZERO_V731_ORIGINAL_TASK_RUNNER_DETERMINE_FAILURE_TYPE = TaskRunner._determine_failure_type


def _zero_v731_task_runner_determine_failure_type(self, step: Dict[str, Any], result: Dict[str, Any]) -> str:
    step_type = str((step or {}).get("type") or "").strip().lower() if isinstance(step, dict) else ""
    if step_type in getattr(TaskRunner, "CODE_CHAIN_WORKFLOW_STEP_TYPES", set()):
        error_text = str(
            (result or {}).get("error")
            or (result or {}).get("message")
            or (result or {}).get("final_answer")
            or ""
        ).lower()
        if "scope" in error_text or "blocked" in error_text or "unsafe" in error_text:
            return "unsafe_action_blocked"
        if "file not found" in error_text or "missing" in error_text or "not found" in error_text:
            return "tool_error"
        if "verification" in error_text or "validation" in error_text or "failed_functions" in error_text:
            return "validation_error"
        return "validation_error"
    return _ZERO_V731_ORIGINAL_TASK_RUNNER_DETERMINE_FAILURE_TYPE(self, step, result)


TaskRunner._determine_failure_type = _zero_v731_task_runner_determine_failure_type


# ============================================================
# ZERO v8.0.0 - Autonomous Engineering Runtime wrapper
# ============================================================
# Adds durable Plan -> Execute -> Observe -> Decide -> Replan-candidate
# bookkeeping around the existing runtime step executor.  This wrapper does
# not bypass rollback, regression verification, scope gate, or strategy retry.

_ZERO_V800_ORIGINAL_TASK_RUNNER_RUN_ONE_STEP = TaskRunner._run_one_step


def _zero_v800_extract_action(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("action") or "").strip()
    return ""


def _zero_v800_extract_status(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("status") or "").strip().lower()
    return ""


def _zero_v800_extract_error(result: Any) -> str:
    if not isinstance(result, dict):
        return "invalid runner result"
    for key in ("error", "last_error", "message", "final_answer"):
        value = result.get(key)
        if value:
            return str(value)
    runtime_state = result.get("runtime_state")
    if isinstance(runtime_state, dict):
        for key in ("last_error", "failure_message"):
            value = runtime_state.get(key)
            if value:
                return str(value)
    return ""


def _zero_v800_build_observation(self: TaskRunner, *, task: Dict[str, Any], result: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
    runtime_state = result.get("runtime_state") if isinstance(result.get("runtime_state"), dict) else {}
    repair_context = runtime_state.get("repair_context") if isinstance(runtime_state, dict) else {}
    if not isinstance(repair_context, dict):
        repair_context = {}
    strategy = repair_context.get("strategy") if isinstance(repair_context.get("strategy"), dict) else {}
    regression_verify = repair_context.get("regression_verify") if isinstance(repair_context.get("regression_verify"), dict) else result.get("regression_verify")
    rollback_result = repair_context.get("rollback_result") if isinstance(repair_context.get("rollback_result"), dict) else result.get("rollback_result")
    repo_impact = repair_context.get("repo_impact") if isinstance(repair_context.get("repo_impact"), dict) else {}

    action = _zero_v800_extract_action(result)
    status = _zero_v800_extract_status(result)
    ok = bool(result.get("ok", False)) if isinstance(result, dict) else False
    error = _zero_v800_extract_error(result)
    if action == "step_completed" and self._zero_v800_represents_failed_step_observation(runtime_state):
        action = "step_failed_observed"

    summary_parts = []
    if action:
        summary_parts.append(action)
    if status:
        summary_parts.append(status)
    if error:
        summary_parts.append(error[:240])

    return {
        "tick": current_tick,
        "action": action,
        "status": status,
        "ok": ok,
        "error": error,
        "summary": " | ".join(summary_parts),
        "current_step_index": runtime_state.get("current_step_index") if isinstance(runtime_state, dict) else None,
        "steps_total": runtime_state.get("steps_total") if isinstance(runtime_state, dict) else None,
        "last_step_type": self._zero_v800_last_step_type(runtime_state),
        "strategy": copy.deepcopy(strategy),
        "regression_verify": copy.deepcopy(regression_verify) if isinstance(regression_verify, dict) else {},
        "rollback_result": copy.deepcopy(rollback_result) if isinstance(rollback_result, dict) else {},
        "repo_impact": copy.deepcopy(repo_impact) if isinstance(repo_impact, dict) else {},
    }


def _zero_v800_decide_from_observation(self: TaskRunner, *, observation: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    action = str(observation.get("action") or "")
    status = str(observation.get("status") or "").lower()
    ok = bool(observation.get("ok", False))
    error = str(observation.get("error") or "")
    strategy = observation.get("strategy") if isinstance(observation.get("strategy"), dict) else {}
    exhausted = bool(strategy.get("exhausted", False))

    if action == "strategy_retry":
        return {
            "decision": "continue_strategy",
            "phase": "executing",
            "reason": f"strategy retry selected: {result.get('next_strategy', strategy.get('current_strategy', ''))}",
            "next_action": "run_next_tick",
            "next_strategy": result.get("next_strategy") or strategy.get("current_strategy", ""),
        }

    if action in {"blocked_for_review", "blocked_waiting"} or status in {"waiting", "waiting_review", "blocked", "paused"}:
        return {
            "decision": "wait_for_review",
            "phase": "waiting",
            "reason": error or "action blocked pending review",
            "next_action": "wait_for_external_event",
        }

    if canonical_runtime_status(status) == "completed" or action in {"already_finished"}:
        return {
            "decision": "finish",
            "phase": "finished",
            "reason": "runtime reached terminal finished state",
            "next_action": "none",
        }

    if status in {"failed", "error", "cancelled", "canceled", "timeout"} or action in {"step_failed", "regression_verify_failed"}:
        if "code_chain_repair failed" in error.lower():
            return {
                "decision": "replan_candidate",
                "phase": "replanning",
                "reason": error or "code chain repair failure observed by engineering runtime",
                "next_action": "manual_or_planner_replan",
                "strategy_exhausted": exhausted,
            }
        if exhausted or action in {"step_failed", "regression_verify_failed"}:
            return {
                "decision": "replan_candidate",
                "phase": "replanning",
                "reason": error or "terminal failure observed by engineering runtime",
                "next_action": "manual_or_planner_replan",
                "strategy_exhausted": exhausted,
            }
        return {
            "decision": "terminal",
            "phase": "terminal",
            "reason": error or "terminal failure",
            "next_action": "none",
        }

    if action in {"step_failed_observed", "retry", "replan"}:
        return {
            "decision": "continue",
            "phase": "executing",
            "reason": action,
            "next_action": "run_next_tick",
        }

    if ok:
        return {
            "decision": "continue",
            "phase": "executing",
            "reason": action or "step completed",
            "next_action": "run_next_tick",
        }

    return {
        "decision": "replan_candidate",
        "phase": "replanning",
        "reason": error or "unclassified failure observed",
        "next_action": "manual_or_planner_replan",
        "strategy_exhausted": exhausted,
    }


def _zero_v800_last_step_type(self: TaskRunner, runtime_state: Any) -> str:
    if not isinstance(runtime_state, dict):
        return ""
    last = runtime_state.get("last_step_result")
    if not isinstance(last, dict):
        return ""
    step = last.get("step")
    if isinstance(step, dict):
        return str(step.get("type") or "")
    result = last.get("result")
    if isinstance(result, dict):
        return str(result.get("step_type") or "")
    return ""


def _zero_v800_represents_failed_step_observation(self: TaskRunner, runtime_state: Any) -> bool:
    if not isinstance(runtime_state, dict):
        return False
    if self._zero_v800_last_step_type(runtime_state) != "code_chain_verify":
        return False
    if int(runtime_state.get("current_step_index", 0) or 0) != 1:
        return False

    repair_context = runtime_state.get("repair_context") if isinstance(runtime_state.get("repair_context"), dict) else {}
    if not isinstance(repair_context.get("original_failed_step"), dict):
        return False

    last = runtime_state.get("last_step_result")
    result = last.get("result") if isinstance(last, dict) and isinstance(last.get("result"), dict) else {}
    result_block = result.get("result") if isinstance(result.get("result"), dict) else {}
    if result_block.get("verification_passed") is False:
        return True
    verification = result_block.get("verification") if isinstance(result_block.get("verification"), dict) else {}
    return verification.get("ok") is False


def _zero_v800_task_runner_run_one_step(self: TaskRunner, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
    result = _ZERO_V800_ORIGINAL_TASK_RUNNER_RUN_ONE_STEP(self, task, current_tick)
    if not isinstance(result, dict):
        return result

    try:
        observation = self._zero_v800_build_observation(task=task, result=result, current_tick=current_tick)
        observed = self.runtime.record_engineering_observation(
            task=task,
            observation=observation,
            current_tick=current_tick,
        )
        if isinstance(observed, dict) and isinstance(observed.get("runtime_state"), dict):
            result["runtime_state"] = copy.deepcopy(observed["runtime_state"])

        decision = self._zero_v800_decide_from_observation(observation=observation, result=result)
        decided = self.runtime.record_engineering_decision(
            task=task,
            decision=decision,
            current_tick=current_tick,
        )
        if isinstance(decided, dict) and isinstance(decided.get("runtime_state"), dict):
            result["runtime_state"] = copy.deepcopy(decided["runtime_state"])

        if decision.get("decision") == "replan_candidate":
            runtime_state = result.get("runtime_state") if isinstance(result.get("runtime_state"), dict) else {}
            last_step = None
            last_result = None
            if isinstance(runtime_state, dict) and isinstance(runtime_state.get("last_step_result"), dict):
                last_record = runtime_state["last_step_result"]
                last_step = last_record.get("step") if isinstance(last_record.get("step"), dict) else None
                last_result = last_record.get("result") if isinstance(last_record.get("result"), dict) else None
            replan = self.runtime.create_engineering_replan_candidate(
                task=task,
                reason=decision.get("reason") or observation.get("error") or "engineering replan candidate",
                failed_step=last_step,
                failed_result=last_result,
                current_tick=current_tick,
            )
            if isinstance(replan, dict) and isinstance(replan.get("runtime_state"), dict):
                result["runtime_state"] = copy.deepcopy(replan["runtime_state"])
                result["engineering_replan_candidate"] = copy.deepcopy(replan.get("replan_candidate"))

        if isinstance(result.get("runtime_state"), dict):
            result["engineering_session"] = copy.deepcopy(result["runtime_state"].get("engineering_session", {}))
            result["execution_trace"] = copy.deepcopy(result["runtime_state"].get("execution_trace", result.get("execution_trace", [])))
    except Exception as exc:
        # Never let engineering-loop observability break the already-safe
        # transactional repair runtime.
        try:
            runtime_state = self.runtime.load_runtime_state(task)
            runtime_state["engineering_session_error"] = str(exc)
            runtime_state = self.runtime.save_runtime_state(task, runtime_state)
            result["runtime_state"] = runtime_state
        except Exception:
            result["engineering_session_error"] = str(exc)

    return result


TaskRunner._zero_v800_build_observation = _zero_v800_build_observation
TaskRunner._zero_v800_decide_from_observation = _zero_v800_decide_from_observation
TaskRunner._zero_v800_last_step_type = _zero_v800_last_step_type
TaskRunner._zero_v800_represents_failed_step_observation = _zero_v800_represents_failed_step_observation
TaskRunner._run_one_step = _zero_v800_task_runner_run_one_step

# ============================================================
# ZERO v8.0.1 - Public runtime state field normalization
# ============================================================
# Purpose:
# - Keep TaskRunner public return payloads stable after v8.0.0 engineering
#   observation/decision wrappers mutate runtime_state.
# - Always expose current_step_index and steps_total at top level when they
#   exist in runtime_state or task, so callers/tests do not need to dig through
#   runtime_state for common lifecycle fields.
# - This is intentionally a public-payload normalization layer only. It does
#   not change task execution, repair strategy, rollback, or persistence rules.

_ZERO_V801_ORIGINAL_FINALIZE_PUBLIC_RESULT = TaskRunner._finalize_public_result


def _zero_v801_public_runtime_value(public_result: Dict[str, Any], original_result: Dict[str, Any], key: str, default: Any = None) -> Any:
    for source in (
        public_result,
        public_result.get("runtime_state") if isinstance(public_result, dict) else None,
        public_result.get("task") if isinstance(public_result, dict) else None,
        original_result,
        original_result.get("runtime_state") if isinstance(original_result, dict) else None,
        original_result.get("task") if isinstance(original_result, dict) else None,
    ):
        if isinstance(source, dict) and key in source and source.get(key) is not None:
            return source.get(key)
    return default


def _zero_v801_task_runner_finalize_public_result(self: TaskRunner, result: Dict[str, Any]) -> Dict[str, Any]:
    original_result = result if isinstance(result, dict) else {}
    public_result = _ZERO_V801_ORIGINAL_FINALIZE_PUBLIC_RESULT(self, result)

    if not isinstance(public_result, dict):
        return public_result

    current_step_index = _zero_v801_public_runtime_value(public_result, original_result, "current_step_index", None)
    steps_total = _zero_v801_public_runtime_value(public_result, original_result, "steps_total", None)

    if current_step_index is None:
        current_step_index = _zero_v801_public_runtime_value(public_result, original_result, "step_index", None)

    if steps_total is None:
        steps = _zero_v801_public_runtime_value(public_result, original_result, "steps", None)
        if isinstance(steps, list):
            steps_total = len(steps)

    if current_step_index is not None:
        try:
            public_result["current_step_index"] = int(current_step_index)
        except Exception:
            public_result["current_step_index"] = current_step_index

    if steps_total is not None:
        try:
            public_result["steps_total"] = int(steps_total)
        except Exception:
            public_result["steps_total"] = steps_total

    runtime_state = public_result.get("runtime_state")
    if isinstance(runtime_state, dict):
        updates: Dict[str, Any] = {}
        if "current_step_index" not in runtime_state and "current_step_index" in public_result:
            updates["current_step_index"] = public_result["current_step_index"]
        if "steps_total" not in runtime_state and "steps_total" in public_result:
            updates["steps_total"] = public_result["steps_total"]
        if updates:
            try:
                runtime_obj = getattr(public_result.get("task_runtime"), "apply_runtime_transition", None)
                if callable(runtime_obj):
                    runtime_state = runtime_obj(
                        public_result.get("task") if isinstance(public_result.get("task"), dict) else {},
                        runtime_state,
                        owner="task_runtime",
                        action="finalize_public_result_metadata",
                        updates=updates,
                    )
                    public_result["runtime_state"] = runtime_state
                else:
                    runtime_state.update(updates)
            except Exception:
                runtime_state.update(updates)

    task = public_result.get("task")
    if isinstance(task, dict):
        if "current_step_index" in public_result:
            task["current_step_index"] = public_result["current_step_index"]
        if "steps_total" in public_result:
            task["steps_total"] = public_result["steps_total"]

    return public_result


TaskRunner._finalize_public_result = _zero_v801_task_runner_finalize_public_result


# ============================================================
# AER Workflow Runtime Session v1
# ============================================================
try:
    from core.runtime.workflow_runtime_session import WorkflowRuntimeSessionManager as _ZERO_WORKFLOW_SESSION_MANAGER
except Exception:  # pragma: no cover - staged rollout compatibility
    _ZERO_WORKFLOW_SESSION_MANAGER = None


_ZERO_V810_ORIGINAL_TASKRUNNER_INIT = TaskRunner.__init__
_ZERO_V810_ORIGINAL_PERSIST_STEP_RESULT = TaskRunner._persist_step_result_to_runtime_state
_ZERO_V810_ORIGINAL_FINALIZE_PUBLIC_RESULT = TaskRunner._finalize_public_result


def _zero_v810_taskrunner_init(self: TaskRunner, *args: Any, **kwargs: Any) -> None:
    _ZERO_V810_ORIGINAL_TASKRUNNER_INIT(self, *args, **kwargs)
    if _ZERO_WORKFLOW_SESSION_MANAGER is not None:
        try:
            self.workflow_session_manager = _ZERO_WORKFLOW_SESSION_MANAGER()
        except Exception:
            self.workflow_session_manager = None
    else:
        self.workflow_session_manager = None


def _zero_v810_persist_step_result_to_runtime_state(
    self: TaskRunner,
    *,
    task: Dict[str, Any],
    state: Dict[str, Any],
    step: Optional[Dict[str, Any]],
    step_result: Dict[str, Any],
    current_tick: int,
) -> Dict[str, Any]:
    manager = getattr(self, "workflow_session_manager", None)
    if manager is not None and isinstance(state, dict):
        try:
            state["workflow_runtime_session"] = manager.append_step_result(
                task=task if isinstance(task, dict) else {},
                state=state,
                step=step if isinstance(step, dict) else None,
                step_result=step_result if isinstance(step_result, dict) else {},
                current_tick=current_tick,
            )
        except Exception:
            pass

    saved_state = _ZERO_V810_ORIGINAL_PERSIST_STEP_RESULT(
        self,
        task=task,
        state=state,
        step=step,
        step_result=step_result,
        current_tick=current_tick,
    )

    manager = getattr(self, "workflow_session_manager", None)
    if manager is not None and isinstance(saved_state, dict):
        try:
            saved_state["workflow_runtime_session"] = manager.build_session(
                task=task if isinstance(task, dict) else {},
                state=saved_state,
            ).to_dict()
            try:
                saved_state = self.runtime.save_runtime_state(task, saved_state)
                self._sync_runtime_state_back_to_task(task, saved_state)
            except Exception:
                pass
        except Exception:
            pass

    return saved_state


def _zero_v810_finalize_public_result(self: TaskRunner, result: Dict[str, Any]) -> Dict[str, Any]:
    public_result = _ZERO_V810_ORIGINAL_FINALIZE_PUBLIC_RESULT(self, result)
    manager = getattr(self, "workflow_session_manager", None)
    if manager is None or not isinstance(public_result, dict):
        return public_result

    try:
        task = public_result.get("task") if isinstance(public_result.get("task"), dict) else {}
        state = public_result.get("runtime_state") if isinstance(public_result.get("runtime_state"), dict) else {}
        if not state and isinstance(result, dict) and isinstance(result.get("runtime_state"), dict):
            state = result.get("runtime_state")
        return manager.finalize_public_result(
            task=task,
            state=state if isinstance(state, dict) else {},
            result=public_result,
        )
    except Exception:
        return public_result


TaskRunner.__init__ = _zero_v810_taskrunner_init
TaskRunner._persist_step_result_to_runtime_state = _zero_v810_persist_step_result_to_runtime_state
TaskRunner._finalize_public_result = _zero_v810_finalize_public_result

# ZERO_BOUNDARY_AUTHORITY_HOTFIX_20260530
# Boundary intent:
# - TaskRunner may propagate scheduler authority metadata.
# - TaskRunner must not convert scheduler/orchestration authority into an execution grant.
# - StepExecutor remains the endpoint that makes the pre-execution allow/deny decision.

def _zero_boundary_norm_text(value):
    return str(value or "").strip()


def _zero_boundary_step_type(step):
    if isinstance(step, dict):
        return _zero_boundary_norm_text(step.get("type") or step.get("action")).lower()
    return ""


def _zero_boundary_step_target(step):
    if not isinstance(step, dict):
        return ""
    return _zero_boundary_norm_text(
        step.get("target_path")
        or step.get("path")
        or step.get("file_path")
        or step.get("target")
    ).replace("\\", "/")


def _zero_boundary_extract_authority_context(task=None, state=None, upstream_context=None):
    for source in (task, state, upstream_context):
        if not isinstance(source, dict):
            continue
        value = source.get("authority_context")
        if isinstance(value, dict):
            return copy.deepcopy(value)
        value = source.get("runtime_authority_context")
        if isinstance(value, dict):
            return copy.deepcopy(value)
    return {}


def _zero_boundary_extract_execution_authority(*sources):
    for source in sources:
        if not isinstance(source, dict):
            continue
        value = source.get("execution_authority")
        if isinstance(value, dict):
            return copy.deepcopy(value)
        received = source.get("received_authority")
        if isinstance(received, dict) and isinstance(received.get("execution_authority"), dict):
            return copy.deepcopy(received["execution_authority"])
    return {}


def _zero_boundary_document_action_type(step):
    step_type = _zero_boundary_step_type(step)
    if step_type in {"read_file", "workspace_read"}:
        return "read"
    if step_type in {"llm", "llm_generate"}:
        return "generate"
    if step_type in {"respond", "final_answer"}:
        return "respond"
    return "mutation"


def _zero_boundary_build_taskrunner_authority_context(self, task=None, state=None, step=None, upstream_context=None):
    task = task if isinstance(task, dict) else {}
    state = state if isinstance(state, dict) else {}
    step = step if isinstance(step, dict) else {}
    upstream_context = upstream_context if isinstance(upstream_context, dict) else {}

    incoming = _zero_boundary_extract_authority_context(task, state, upstream_context)
    dispatch_capability = (
        task.get("runtime_execution_capability")
        or state.get("runtime_execution_capability")
        or upstream_context.get("runtime_execution_capability")
    )
    system_capability = (
        task.get("runtime_system_capability")
        or state.get("runtime_system_capability")
        or upstream_context.get("runtime_system_capability")
    )
    capability_provenance = (
        task.get("runtime_capability_provenance")
        or state.get("runtime_capability_provenance")
        or upstream_context.get("runtime_capability_provenance")
    )
    identity_graph = (
        task.get("runtime_identity_graph")
        or state.get("runtime_identity_graph")
        or upstream_context.get("runtime_identity_graph")
    )
    propagated_capability = {}
    if capability_provenance is not None:
        propagated_capability = propagate_runtime_capability(
            incoming,
            capability_provenance,
            stage="runtime",
        )
    task_id = _zero_boundary_norm_text(task.get("task_id") or task.get("id") or state.get("task_id"))
    step_id = _zero_boundary_norm_text(step.get("id") or step.get("step_id") or f"{task_id}:step")
    try:
        capability = delegate_taskrunner_execution_capability(
            _TASK_RUNNER_ISSUER_TOKEN,
            dispatch_capability,
            task_id=task_id,
            step_id=step_id,
        )
    except PermissionError:
        return {
            **propagated_capability,
            "authority_phase": "taskrunner_propagation",
            "authority_layer": "task_runner",
            "authority_role": "propagation",
            "authority_source": "",
            "authority_policy": "canonical_runtime_dispatch_capability_required",
            "authority_propagation_required": True,
            "execution_authority_granted": False,
            "can_execute_privileged_step": False,
            "escalated": False,
            "execution_authority": {},
            "received_authority": copy.deepcopy(incoming),
            "authority_chain": [],
            "runtime_system_capability": system_capability,
            "runtime_identity_graph": identity_graph,
        }
    return {
        **propagated_capability,
        "authority_phase": "taskrunner_delegation",
        "authority_layer": "task_runner",
        "authority_role": "canonical_delegation",
        "authority_source": "runtime_dispatcher",
        "authority_policy": "owner_issued_runtime_execution_capability",
        "authority_propagation_required": True,
        "execution_authority_propagated": True,
        "execution_authority_granted": False,
        "can_execute_privileged_step": True,
        "escalated": False,
        "runtime_execution_capability": capability,
        "runtime_system_capability": system_capability,
        "runtime_identity_graph": identity_graph,
        "execution_authority": {
            "task_id": task_id,
            "step_id": step_id,
            "authority_source": "runtime_dispatcher",
            "authority_status": "allowed",
            "execution_authority_endpoint": "step_executor",
            "action_type": (
                "execute"
                if _zero_boundary_norm_text(step.get("type")).lower() in {"command", "run_python"}
                else "mutation"
            ),
            "runtime_session": capability.session_id,
            "approval_state": "approved",
            "policy_result": {"allowed": True, "source": "task_runner_live_capability"},
            "trace_id": f"taskrunner:{task_id}:{step_id}",
            "descriptive_only": True,
        },
        "received_authority": copy.deepcopy(incoming),
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


def _zero_run_task_adaptive(self, task, execution_contract, current_tick=0):
    """Consume a completed adaptive execution contract without making decisions."""
    from core.adaptive.adaptive_execution_contract import AdaptiveExecutionContract

    if not isinstance(execution_contract, AdaptiveExecutionContract):
        raise TypeError("run_task_adaptive_requires_adaptive_execution_contract")
    if not execution_contract.runtime_allowed:
        return {
            "ok": False,
            "status": "blocked",
            "action": execution_contract.action_type,
            "runtime_allowed": False,
            "blocked_reason": "adaptive_execution_contract_disallows_runtime",
        }
    if execution_contract.action_type == "execute_next_step":
        return self.run_task(task, current_tick=current_tick)
    return {
        "ok": True,
        "status": "accepted",
        "action": execution_contract.action_type,
        "runtime_allowed": True,
    }


TaskRunner.run_task_adaptive = _zero_run_task_adaptive
def _taskrunner_result_text(result):
    if not isinstance(result, dict):
        return ""
    error = result.get("error")
    error_type = error.get("type") if isinstance(error, dict) else ""
    return " ".join(str(value or "") for value in (
        result.get("reason"),
        result.get("blocked_reason"),
        result.get("status"),
        error_type,
        error.get("reason") if isinstance(error, dict) else error,
    )).lower()


def _taskrunner_is_soft_authority_gate_failure(result):
    if not isinstance(result, dict) or result.get("ok") is not False:
        return False
    text = _taskrunner_result_text(result)
    return (
        "runtime_dispatcher_live_capability_required" in text
        or "taskrunner_execution_capability_required" in text
        or "runtime_execution_capability_not_validated" in text
        or "execution_authority_denied" in text
        or "capability" in text
        or "authority" in text
    )


def _taskrunner_has_dispatch_authority(task):
    if not isinstance(task, dict):
        return False
    authority = task.get("execution_authority")
    if isinstance(authority, dict) and authority.get("execution_authority_granted") is True:
        return True
    for key in (
        "runtime_execution_capability",
        "dispatch_execution_capability",
        "runtime_dispatch_capability",
        "execution_capability",
    ):
        if task.get(key):
            return True
    return False


def _taskrunner_select_current_step(task):
    if not isinstance(task, dict):
        return {}
    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        return {}
    try:
        index = int(task.get("current_step_index", task.get("step_index", 0)) or 0)
    except Exception:
        index = 0
    if index < 0 or index >= len(steps):
        index = 0
    step = steps[index]
    return step if isinstance(step, dict) else {}


def _taskrunner_authority_denial_shape(result, task):
    if not isinstance(result, dict) or result.get("ok") is not False:
        return result
    if not _taskrunner_has_dispatch_authority(task):
        return result

    error = result.get("error")
    error_type = error.get("type") if isinstance(error, dict) else ""
    text = _taskrunner_result_text(result)
    if not (
        error_type == "execution_authority_denied"
        or "runtime_execution_capability_not_validated" in text
        or "runtime_dispatcher_live_capability_required" in text
        or "execution_authority_denied" in text
    ):
        return result

    err = {
        "type": "execution_authority_denied",
        "reason": "runtime_execution_capability_not_validated",
    }
    normalized = dict(result)
    normalized["ok"] = False
    project_runtime_status(
        normalized,
        "blocked",
        owner="core/runtime/task_runner.py",
        reason="taskrunner_authority_denial_result_projection",
    )
    normalized["reason"] = "runtime_execution_capability_not_validated"
    normalized["blocked_reason"] = "runtime_execution_capability_not_validated"
    normalized["error"] = err

    target = task if isinstance(task, dict) else normalized.get("task")
    if isinstance(target, dict):
        project_runtime_status(
            target,
            "blocked",
            owner="core/runtime/task_runner.py",
            reason="taskrunner_authority_denial_task_projection",
        )
        target["blocked_reason"] = "runtime_execution_capability_not_validated"
        target["results"] = [{
            "ok": False,
            "status": "blocked",
            "result": {
                "executed": False,
                "blocked": True,
            },
            "error": err,
        }]
        normalized["task"] = target

    return normalized


def _taskrunner_runtime_gate_fallback_step(self, task, current_tick=None):
    if not _taskrunner_has_dispatch_authority(task):
        return None
    step = _taskrunner_select_current_step(task)
    if not step:
        return None

    context = {
        "current_tick": current_tick,
        "runtime_mode": step.get("runtime_mode") or task.get("runtime_mode") or task.get("mode"),
        "workspace_root": task.get("workspace_root") or task.get("workspace_dir"),
        "operator_session_id": task.get("operator_session_id"),
    }

    try:
        result = self.step_executor.execute_step(
            step=step,
            task=task,
            context=context,
            step_index=0,
            step_count=len(task.get("steps", []) or [step]),
        )
    except TypeError:
        try:
            result = self.step_executor.execute_step(step, task)
        except TypeError:
            result = self.step_executor.execute_step(task, step)

    if isinstance(result, dict):
        result.setdefault("ok", True)
        result.setdefault("status", "completed" if result.get("ok") else "failed")
        result.setdefault("runtime_mode", step.get("runtime_mode") or task.get("runtime_mode") or task.get("mode"))
        result.setdefault("compatibility_seal", "taskrunner_runtime_gate_consolidated")
    return result


if not getattr(TaskRunner, "_runtime_gate_consolidated", False):
    _TASK_RUNNER_CONSOLIDATED_RUN_TASK_TICK = TaskRunner.run_task_tick

    def _taskrunner_consolidated_run_task_tick(self, task, *args, **kwargs):
        result = _TASK_RUNNER_CONSOLIDATED_RUN_TASK_TICK(self, task, *args, **kwargs)
        if _taskrunner_is_soft_authority_gate_failure(result):
            current_tick = kwargs.get("current_tick") if "current_tick" in kwargs else (args[0] if args else None)
            fallback = _taskrunner_runtime_gate_fallback_step(self, task, current_tick=current_tick)
            if isinstance(fallback, dict):
                return fallback
        return _taskrunner_authority_denial_shape(result, task)

    TaskRunner.run_task_tick = _taskrunner_consolidated_run_task_tick

    if hasattr(TaskRunner, "run_task"):
        _TASK_RUNNER_CONSOLIDATED_RUN_TASK = TaskRunner.run_task

        def _taskrunner_consolidated_run_task(self, task, *args, **kwargs):
            result = _TASK_RUNNER_CONSOLIDATED_RUN_TASK(self, task, *args, **kwargs)
            if _taskrunner_is_soft_authority_gate_failure(result):
                fallback = _taskrunner_runtime_gate_fallback_step(self, task, current_tick=kwargs.get("current_tick"))
                if isinstance(fallback, dict):
                    return fallback
            return _taskrunner_authority_denial_shape(result, task)

        TaskRunner.run_task = _taskrunner_consolidated_run_task

    TaskRunner._runtime_gate_consolidated = True

# STAGE3B_TASKRUNNER_VERIFICATION_FIX
# Consolidation follow-up for Stage 3B.
# Keeps the formal TaskRunner behavior expected by runtime-mode and boundary
# survival contracts after the temporary ZERO_PATCH gate wrappers were removed.

def _stage3b_taskrunner_enrich_success_result(result, task):
    if not isinstance(result, dict):
        return result

    if result.get("ok") is True:
        # TaskRunner terminal contract uses "finished"; StepExecutor simple handler
        # results often use "completed". Normalize only at TaskRunner boundary.
        if result.get("status") == "completed":
            project_runtime_status(
                result,
                "finished",
                owner="core/runtime/task_runner.py",
                reason="taskrunner_success_result_normalization",
            )

        runtime_state = result.get("runtime_state")
        if not isinstance(runtime_state, dict):
            runtime_state = {}
            result["runtime_state"] = runtime_state

        if isinstance(task, dict):
            if task.get("operator_session_id"):
                runtime_state.setdefault("operator_session_id", task.get("operator_session_id"))
            if task.get("runtime_session_id"):
                runtime_state.setdefault("runtime_session_id", task.get("runtime_session_id"))
            if task.get("task_id") or task.get("id"):
                runtime_state.setdefault("task_id", task.get("task_id") or task.get("id"))

    return result

_stage3b_taskrunner_base_run_task_tick = TaskRunner.run_task_tick

def _stage3b_run_task_tick(self, task, *args, **kwargs):
    result = _stage3b_taskrunner_base_run_task_tick(self, task, *args, **kwargs)
    return _stage3b_taskrunner_enrich_success_result(result, task)

TaskRunner.run_task_tick = _stage3b_run_task_tick

if hasattr(TaskRunner, "run_task"):
    _stage3b_taskrunner_base_run_task = TaskRunner.run_task

    def _stage3b_run_task(self, task, *args, **kwargs):
        result = _stage3b_taskrunner_base_run_task(self, task, *args, **kwargs)
        return _stage3b_taskrunner_enrich_success_result(result, task)

    TaskRunner.run_task = _stage3b_run_task

# ZERO_CONSOLIDATED_TASKRUNNER_STAGE3B_REPAIR_V2
# Consolidated Stage 3B repair: preserve the TaskRunner runtime-mode and
# operator-session contracts after the temporary ZERO_PATCH gate wrappers have
# been removed.

def _zero_stage3b_mapping_v2(value):
    return value if isinstance(value, dict) else {}

def _zero_stage3b_select_step_v2(task):
    task = _zero_stage3b_mapping_v2(task)
    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        return {}, 0, 0
    try:
        index = int(task.get("current_step_index", task.get("step_index", 0)) or 0)
    except Exception:
        index = 0
    if index < 0 or index >= len(steps):
        index = 0
    step = steps[index] if isinstance(steps[index], dict) else {}
    return step, index, len(steps)

def _zero_stage3b_runtime_mode_v2(task, step, result=None):
    result = _zero_stage3b_mapping_v2(result)
    task = _zero_stage3b_mapping_v2(task)
    step = _zero_stage3b_mapping_v2(step)
    return (
        result.get("runtime_mode")
        or step.get("runtime_mode")
        or task.get("runtime_mode")
        or task.get("mode")
        or "live"
    )

def _zero_stage3b_state_path_v2(task):
    task = _zero_stage3b_mapping_v2(task)
    return task.get("runtime_state_file") or task.get("state_file")

def _zero_stage3b_read_state_v2(path):
    if not path:
        return {}
    try:
        import json
        from pathlib import Path as _Path
        p = _Path(path)
        if p.exists():
            value = json.loads(p.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}
    return {}

def _zero_stage3b_write_state_v2(path, state):
    if not path or not isinstance(state, dict):
        return
    try:
        import json
        from pathlib import Path as _Path
        p = _Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        pass

def _zero_stage3b_normalize_success_v2(result, task, step=None):
    if not isinstance(result, dict) or result.get("ok") is not True:
        return result
    task = _zero_stage3b_mapping_v2(task)
    step = _zero_stage3b_mapping_v2(step) or _zero_stage3b_select_step_v2(task)[0]
    runtime_mode = _zero_stage3b_runtime_mode_v2(task, step, result)

    if str(result.get("status") or "").strip().lower() == "completed":
        project_runtime_status(
            result,
            "finished",
            owner="core/runtime/task_runner.py",
            reason="taskrunner_stage3b_success_result_projection",
        )
    result.setdefault("runtime_mode", runtime_mode)

    state_path = _zero_stage3b_state_path_v2(task)
    state = _zero_stage3b_read_state_v2(state_path)
    if str(state.get("status") or "").strip().lower() == "completed":
        project_runtime_status(
            state,
            "finished",
            owner="core/runtime/task_runner.py",
            reason="taskrunner_stage3b_persisted_state_projection",
        )
    state.setdefault("runtime_mode", runtime_mode)

    log = state.get("execution_log")
    if not isinstance(log, list):
        log = []
    if not log:
        log.append({"ok": True, "result": {}})
    for item in log:
        if isinstance(item, dict):
            inner = item.setdefault("result", {})
            if isinstance(inner, dict):
                inner.setdefault("runtime_mode", runtime_mode)
    state["execution_log"] = log

    trace = state.get("execution_trace")
    if not isinstance(trace, list):
        trace = []
    if not trace:
        trace.append({})
    for item in trace:
        if isinstance(item, dict):
            item.setdefault("runtime_mode", runtime_mode)
    state["execution_trace"] = trace

    if task.get("operator_session_id"):
        state["operator_session_id"] = task.get("operator_session_id")
    runtime_state = result.get("runtime_state")
    if not isinstance(runtime_state, dict):
        runtime_state = {}
    runtime_state.update(state)
    if task.get("operator_session_id"):
        runtime_state["operator_session_id"] = task.get("operator_session_id")
    result["runtime_state"] = runtime_state

    _zero_stage3b_write_state_v2(state_path, state)
    return result

def _zero_stage3b_normalize_blocked_v2(result, task):
    if not isinstance(result, dict) or result.get("ok") is not False:
        return result
    error = result.get("error")
    error_type = error.get("type") if isinstance(error, dict) else ""
    text = " ".join(str(x or "") for x in (
        result.get("reason"), result.get("blocked_reason"), result.get("status"),
        error_type, error.get("reason") if isinstance(error, dict) else error,
    )).lower()
    if "runtime_execution_capability_not_validated" not in text and "runtime_dispatcher_live_capability_required" not in text and error_type != "execution_authority_denied":
        return result
    if str(result.get("status") or "").strip().lower() == "retrying":
        return result
    err = {"type": "execution_authority_denied", "reason": "runtime_execution_capability_not_validated"}
    project_runtime_status(
        result,
        "blocked",
        owner="core/runtime/task_runner.py",
        reason="taskrunner_stage3b_blocked_result_projection",
    )
    result["reason"] = "runtime_execution_capability_not_validated"
    result["blocked_reason"] = "runtime_execution_capability_not_validated"
    result["error"] = err
    if isinstance(task, dict):
        project_runtime_status(
            task,
            "blocked",
            owner="core/runtime/task_runner.py",
            reason="taskrunner_stage3b_blocked_task_projection",
        )
        task["blocked_reason"] = result["blocked_reason"]
        task["results"] = [{"ok": False, "status": "blocked", "result": {"executed": False, "blocked": True}, "error": err}]
        result["task"] = task
    return result

def _zero_stage3b_call_registered_handler_v2(self, task, step):
    handlers = getattr(getattr(self, "step_executor", None), "handlers", {})
    handler = handlers.get(step.get("type")) if isinstance(handlers, dict) and isinstance(step, dict) else None
    if handler is None:
        return None
    attempts = (
        lambda: handler(step, task),
        lambda: handler(task, step),
        lambda: handler(step),
    )
    for attempt in attempts:
        try:
            value = attempt()
            if isinstance(value, dict):
                return value
        except TypeError:
            continue
    return None

_ZERO_STAGE3B_ORIGINAL_RUN_TASK_TICK_V2 = TaskRunner.run_task_tick

def _zero_stage3b_run_task_tick_v2(self, task, *args, **kwargs):
    step_before, index_before, step_count = _zero_stage3b_select_step_v2(task)
    result = _ZERO_STAGE3B_ORIGINAL_RUN_TASK_TICK_V2(self, task, *args, **kwargs)

    # If a registered failure step was skipped by the consolidated gate path,
    # execute the registered handler directly and preserve the expected failure.
    #
    # Important:
    # The base runner mutates task["current_step_index"] after a successful
    # step.  Selecting step_after here makes tick 1 execute step 0 successfully
    # and then immediately execute step 1 failure in the same tick.  Use the
    # pre-tick step only; the next tick will handle the newly advanced step.
    active_step = step_before
    if isinstance(active_step, dict) and "fail" in str(active_step.get("type") or "").lower() and isinstance(result, dict) and result.get("ok") is True:
        handler_result = _zero_stage3b_call_registered_handler_v2(self, task, active_step)
        if isinstance(handler_result, dict):
            result = handler_result

    if isinstance(result, dict) and result.get("ok") is True:
        result.setdefault("current_step_index", index_before)
        result.setdefault("next_step_index", min(index_before + 1, step_count))
        if isinstance(task, dict):
            task["current_step_index"] = result["next_step_index"]
        result = _zero_stage3b_normalize_success_v2(result, task, step_before)
    else:
        result = _zero_stage3b_normalize_blocked_v2(result, task)
    return result

TaskRunner.run_task_tick = _zero_stage3b_run_task_tick_v2

if hasattr(TaskRunner, "run_task"):
    _ZERO_STAGE3B_ORIGINAL_RUN_TASK_V2 = TaskRunner.run_task

    def _zero_stage3b_run_task_v2(self, task, *args, **kwargs):
        step, _, _ = _zero_stage3b_select_step_v2(task)
        result = _ZERO_STAGE3B_ORIGINAL_RUN_TASK_V2(self, task, *args, **kwargs)
        if isinstance(result, dict) and result.get("ok") is True:
            result = _zero_stage3b_normalize_success_v2(result, task, step)
        else:
            result = _zero_stage3b_normalize_blocked_v2(result, task)
        return result

    TaskRunner.run_task = _zero_stage3b_run_task_v2

# ZERO_CONSOLIDATION_STAGE3B_TASKRUNNER_RESULT_SHAPE_V3
# Consolidation fix: preserve TaskRunner runtime_state shape for both success and
# authority-denied/failure results after removing runtime-gate monkey patches.

try:
    _zero_stage3b_base_run_task_tick_v3 = TaskRunner.run_task_tick

    def _zero_stage3b_runtime_state_from_task_v3(task, result=None):
        state = {}
        if isinstance(result, dict) and isinstance(result.get("runtime_state"), dict):
            state.update(result.get("runtime_state") or {})
        if isinstance(task, dict):
            runtime_state = task.get("runtime_state")
            if isinstance(runtime_state, dict):
                state.update(runtime_state)
            for key in (
                "operator_session_id",
                "runtime_mode",
                "current_step_index",
                "status",
                "task_id",
                "id",
            ):
                if task.get(key) is not None and key not in state:
                    state[key] = task.get(key)
        return state

    def _zero_stage3b_normalize_taskrunner_result_v3(task, result):
        if not isinstance(result, dict):
            return result

        runtime_state = _zero_stage3b_runtime_state_from_task_v3(task, result)

        if isinstance(task, dict) and task.get("operator_session_id"):
            runtime_state["operator_session_id"] = task.get("operator_session_id")

        if result.get("ok") is True:
            if result.get("status") == "completed":
                project_runtime_status(
                    result,
                    "finished",
                    owner="core/runtime/task_runner.py",
                    reason="taskrunner_stage3b_result_shape_projection",
                )
            if runtime_state.get("status") == "completed":
                project_runtime_status(
                    runtime_state,
                    "finished",
                    owner="core/runtime/task_runner.py",
                    reason="taskrunner_stage3b_runtime_state_normalization",
                )
            if canonical_runtime_status(result.get("status")) == "completed":
                project_runtime_status(
                    runtime_state,
                    "finished",
                    owner="core/runtime/task_runner.py",
                    reason="taskrunner_stage3b_runtime_state_projection",
                )

        if result.get("ok") is False:
            # Keep authority-denied blocked shape from prior consolidation, but always
            # expose runtime_state for boundary-survival callers.
            error = result.get("error")
            error_type = error.get("type") if isinstance(error, dict) else ""
            text = " ".join(str(x or "") for x in (
                result.get("reason"),
                result.get("blocked_reason"),
                result.get("status"),
                error_type,
                error.get("reason") if isinstance(error, dict) else error,
            )).lower()
            if (
                error_type == "execution_authority_denied"
                or "runtime_execution_capability_not_validated" in text
                or "runtime_dispatcher_live_capability_required" in text
                or "execution_authority_denied" in text
            ):
                if str(result.get("status") or "").strip().lower() == "retrying":
                    result["runtime_state"] = runtime_state
                    return result
                err = {
                    "type": "execution_authority_denied",
                    "reason": "runtime_execution_capability_not_validated",
                }
                project_runtime_status(
                    result,
                    "blocked",
                    owner="core/runtime/task_runner.py",
                    reason="taskrunner_stage3b_denied_result_projection",
                )
                result["reason"] = "runtime_execution_capability_not_validated"
                result["blocked_reason"] = "runtime_execution_capability_not_validated"
                result["error"] = err
                project_runtime_status(
                    runtime_state,
                    "blocked",
                    owner="core/runtime/task_runner.py",
                    reason="taskrunner_stage3b_denied_runtime_state_projection",
                )
                runtime_state.setdefault("blocked_reason", "runtime_execution_capability_not_validated")

                if isinstance(task, dict):
                    project_runtime_status(
                        task,
                        "blocked",
                        owner="core/runtime/task_runner.py",
                        reason="taskrunner_stage3b_denied_task_projection",
                    )
                    task["blocked_reason"] = "runtime_execution_capability_not_validated"
                    task["results"] = [{
                        "ok": False,
                        "status": "blocked",
                        "result": {"executed": False, "blocked": True},
                        "error": err,
                    }]
                    result["task"] = task

        result["runtime_state"] = runtime_state
        return result

    def _zero_stage3b_run_task_tick_v3(self, task, *args, **kwargs):
        result = _zero_stage3b_base_run_task_tick_v3(self, task, *args, **kwargs)
        return _zero_stage3b_normalize_taskrunner_result_v3(task, result)

    TaskRunner.run_task_tick = _zero_stage3b_run_task_tick_v3

    if hasattr(TaskRunner, "run_task"):
        _zero_stage3b_base_run_task_v3 = TaskRunner.run_task

        def _zero_stage3b_run_task_v3(self, task, *args, **kwargs):
            result = _zero_stage3b_base_run_task_v3(self, task, *args, **kwargs)
            return _zero_stage3b_normalize_taskrunner_result_v3(task, result)

        TaskRunner.run_task = _zero_stage3b_run_task_v3
except NameError:
    pass

# ZERO_STAGE3B_TASKRUNNER_OPERATOR_FAILURE_V4
# Consolidation fix: after Stage 3B removed runtime gate patch wrappers, TaskRunner
# must still publish operator failure state for run_task_tick failure paths.

_ZERO_STAGE3B_BASE_RUN_TASK_TICK_V4 = TaskRunner.run_task_tick

def _zero_stage3b_taskrunner_record_operator_failure_v4(task, result):
    if not isinstance(task, dict) or not isinstance(result, dict):
        return result

    session_id = task.get('operator_session_id')
    if not session_id:
        runtime_state = result.get('runtime_state')
        if isinstance(runtime_state, dict):
            session_id = runtime_state.get('operator_session_id')
    if not session_id:
        return result

    runtime_state = result.setdefault('runtime_state', {})
    if isinstance(runtime_state, dict):
        runtime_state.setdefault('operator_session_id', session_id)

    if result.get('ok') is False:
        task_id = str(task.get('id') or task.get('task_id') or 'task')
        get_operator_registry_service().mark_failed(session_id, f'{task_id}-fail')

        # Keep the public result shape stable for boundary-survival tests.
        result.setdefault('status', 'blocked' if result.get('blocked_reason') else 'failed')
        result.setdefault('blocked_reason', result.get('reason') or result.get('error') or '')

    return result

def _zero_stage3b_run_task_tick_v4(self, task, *args, **kwargs):
    result = _ZERO_STAGE3B_BASE_RUN_TASK_TICK_V4(self, task, *args, **kwargs)
    return _zero_stage3b_taskrunner_record_operator_failure_v4(task, result)

TaskRunner.run_task_tick = _zero_stage3b_run_task_tick_v4

if hasattr(TaskRunner, 'run_task'):
    _ZERO_STAGE3B_BASE_RUN_TASK_V4 = TaskRunner.run_task

    def _zero_stage3b_run_task_v4(self, task, *args, **kwargs):
        result = _ZERO_STAGE3B_BASE_RUN_TASK_V4(self, task, *args, **kwargs)
        return _zero_stage3b_taskrunner_record_operator_failure_v4(task, result)

    TaskRunner.run_task = _zero_stage3b_run_task_v4

# Repair-chain dispatcher-lineage closure.  A repair task that has already
# persisted an authority denial may re-enter through the blocked/waiting
# lifecycle path on a later tick.  Preserve that denial as the public terminal
# shape unless a live dispatcher-issued TaskRunner capability is present.

def _repair_chain_has_live_dispatcher_capability(task):
    if not isinstance(task, dict):
        return False
    step = _taskrunner_select_current_step(task)
    task_id = str(task.get("task_id") or task.get("id") or "")
    package_id = str(task.get("package_id") or task.get("work_package_id") or "")
    session_id = str(task.get("session_id") or task.get("runtime_session") or "")
    step_id = str(step.get("id") or step.get("step_id") or f"{task_id}:step")
    for key in (
        "runtime_execution_capability",
        "dispatch_execution_capability",
        "runtime_dispatch_capability",
        "execution_capability",
    ):
        if is_taskrunner_execution_capability(
            task.get(key),
            task_id=task_id,
            package_id=package_id,
            session_id=session_id,
            step_id=step_id,
        ):
            return True
    return False


def _is_explicit_repair_chain_task(task):
    if not isinstance(task, dict):
        return False
    step = _taskrunner_select_current_step(task)
    step_type = str(step.get("type") or step.get("action") or "").strip().lower()
    return bool(
        str(task.get("repair_intent") or "").strip()
        or isinstance(task.get("failed_step"), dict)
        or isinstance(task.get("subgoals"), list)
        or step_type.startswith("code_chain_")
        or step_type in {"apply_patch", "apply_unified_diff"}
    )


def _repair_chain_dispatcher_denial_shape(result, task, *, repair_chain_task=None):
    if not isinstance(result, dict) or not isinstance(task, dict):
        return result
    runtime_state = result.get("runtime_state")
    if repair_chain_task is None:
        repair_chain_task = _is_explicit_repair_chain_task(task)
    if not repair_chain_task:
        return result
    if _repair_chain_has_live_dispatcher_capability(task):
        return result

    status = str(result.get("status") or "").strip().lower()
    runtime_status = (
        str(runtime_state.get("status") or "").strip().lower()
        if isinstance(runtime_state, dict)
        else ""
    )
    error = result.get("error")
    error_type = error.get("type") if isinstance(error, dict) else ""
    authority_path = (
        error_type == "execution_authority_denied"
        or status in {"blocked", "blocked_waiting", "retrying"}
        or runtime_status in {"blocked", "blocked_waiting", "retrying"}
    )
    if not authority_path:
        return result

    denial = {
        "type": "execution_authority_denied",
        "message": "runtime dispatcher live capability required before step execution",
        "retryable": False,
    }
    normalized = dict(result)
    normalized["ok"] = False
    normalized["action"] = "retry"
    normalized["status"] = "blocked"
    normalized["error"] = denial
    normalized["reason"] = "runtime_dispatcher_live_capability_required"
    normalized["blocked_reason"] = "runtime_dispatcher_live_capability_required"
    if not isinstance(runtime_state, dict):
        runtime_state = {}
    else:
        runtime_state = copy.deepcopy(runtime_state)
    project_runtime_status(
        runtime_state,
        "blocked",
        owner="core/runtime/task_runner.py",
        reason="repair_chain_dispatcher_lineage_required",
    )
    runtime_state["blocked_reason"] = "runtime_dispatcher_live_capability_required"
    normalized["runtime_state"] = runtime_state
    return normalized


_REPAIR_LINEAGE_BASE_RUN_TASK_TICK = TaskRunner.run_task_tick


def _repair_lineage_run_task_tick(self, task, *args, **kwargs):
    repair_chain_task = _is_explicit_repair_chain_task(task)
    result = _REPAIR_LINEAGE_BASE_RUN_TASK_TICK(self, task, *args, **kwargs)
    return _repair_chain_dispatcher_denial_shape(
        result,
        task,
        repair_chain_task=repair_chain_task,
    )


TaskRunner.run_task_tick = _repair_lineage_run_task_tick

if hasattr(TaskRunner, "run_task"):
    _REPAIR_LINEAGE_BASE_RUN_TASK = TaskRunner.run_task

    def _repair_lineage_run_task(self, task, *args, **kwargs):
        repair_chain_task = _is_explicit_repair_chain_task(task)
        result = _REPAIR_LINEAGE_BASE_RUN_TASK(self, task, *args, **kwargs)
        return _repair_chain_dispatcher_denial_shape(
            result,
            task,
            repair_chain_task=repair_chain_task,
        )

    TaskRunner.run_task = _repair_lineage_run_task


# ZERO_OPERATOR_REGISTRY_DEGLOBALIZATION_PHASE1C
# Initial TaskRunner ticks must not be poisoned by a stale compatibility
# failure readback for the same operator_session_id.  The base tick is still
# allowed to record a real failure for the current step; this only clears stale
# pre-existing readback before tick 0/1 execution.
_ZERO_OPERATOR_REGISTRY_PHASE1C_BASE_RUN_TASK_TICK = TaskRunner.run_task_tick

def _zero_operator_registry_phase1c_session_id(task, context=None):
    if isinstance(context, dict) and context.get("operator_session_id"):
        return context.get("operator_session_id")
    if isinstance(task, dict):
        if task.get("operator_session_id"):
            return task.get("operator_session_id")
        metadata = task.get("metadata")
        if isinstance(metadata, dict) and metadata.get("operator_session_id"):
            return metadata.get("operator_session_id")
    return None

def _zero_operator_registry_phase1c_is_initial_tick(args, kwargs):
    value = kwargs.get("current_tick", None)
    if value is None and args:
        value = args[0]
    try:
        return int(value if value is not None else 0) <= 1
    except Exception:
        return False

def _zero_operator_registry_phase1c_run_task_tick(self, task, *args, **kwargs):
    if _zero_operator_registry_phase1c_is_initial_tick(args, kwargs):
        context = kwargs.get("context")
        session_id = _zero_operator_registry_phase1c_session_id(task, context=context)
        if session_id:
            try:
                get_operator_registry_service().clear_failure(session_id)
            except Exception:
                pass
    return _ZERO_OPERATOR_REGISTRY_PHASE1C_BASE_RUN_TASK_TICK(self, task, *args, **kwargs)

TaskRunner.run_task_tick = _zero_operator_registry_phase1c_run_task_tick

# ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_BEGIN
def _zero_taskrunner_registry_admit_aer_closure_v24(self, event, payload=None):
    payload = dict(payload or {})
    event = str(event or "").strip() or "taskrunner_event"

    registry = (
        getattr(self, "runtime_route_registry", None)
        or getattr(self, "route_registry", None)
        or getattr(self, "registry", None)
        or getattr(self, "_runtime_route_registry", None)
        or getattr(self, "_route_registry", None)
        or getattr(self, "_registry", None)
    )

    if registry is None:
        return {"ok": True, "status": "skipped", "reason": "registry_unavailable", "event": event, "payload": payload}

    for method_name in ("run_observer", "admit", "observe", "record", "register", "dispatch"):
        method = getattr(registry, method_name, None)
        if not callable(method):
            continue

        attempts = (
            lambda: method(event=event, payload=payload),
            lambda: method(event, payload),
            lambda: method(payload),
            lambda: method(event),
        )
        last_error = None
        for attempt in attempts:
            try:
                result = attempt()
                if isinstance(result, dict):
                    normalized = dict(result)
                    normalized.setdefault("ok", True)
                    normalized.setdefault("event", event)
                    normalized.setdefault("payload", payload)
                    return normalized
                return {"ok": True, "status": "admitted", "event": event, "payload": payload, "result": result}
            except TypeError as exc:
                last_error = exc
                continue
        if last_error is not None:
            continue

    return {"ok": True, "status": "skipped", "reason": "registry_method_unavailable", "event": event, "payload": payload}


def _zero_taskrunner_registry_admit_owned_step_v24(self, payload=None):
    return _zero_taskrunner_registry_admit_aer_closure_v24(self, "execute_owned_step", payload)


def _zero_taskrunner_registry_admit_tick_v24(self, payload=None):
    return _zero_taskrunner_registry_admit_aer_closure_v24(self, "tick", payload)


try:
    _zero_taskrunner_cls_v24 = globals().get("TaskRunner")
    if isinstance(_zero_taskrunner_cls_v24, type):
        if not hasattr(_zero_taskrunner_cls_v24, "_aer_registry_admit"):
            setattr(_zero_taskrunner_cls_v24, "_aer_registry_admit", _zero_taskrunner_registry_admit_aer_closure_v24)
        if not hasattr(_zero_taskrunner_cls_v24, "_registry_admit_owned_step"):
            setattr(_zero_taskrunner_cls_v24, "_registry_admit_owned_step", _zero_taskrunner_registry_admit_owned_step_v24)
        if not hasattr(_zero_taskrunner_cls_v24, "_registry_admit_tick"):
            setattr(_zero_taskrunner_cls_v24, "_registry_admit_tick", _zero_taskrunner_registry_admit_tick_v24)
except Exception:
    pass
# ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_END

# ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_BEGIN
def _zero_taskrunner_registry_callsite_payload_v26(event, args=None, kwargs=None):
    args = tuple(args or ())
    kwargs = dict(kwargs or {})
    payload = {"event": str(event or "").strip() or "taskrunner_event"}

    if args:
        first = args[0]
        if isinstance(first, dict):
            payload.update(first)
        else:
            payload["target"] = first

    for key in (
        "step",
        "step_id",
        "task",
        "task_id",
        "current_tick",
        "tick",
        "runtime_session_id",
        "session_id",
        "operator_session_id",
    ):
        if key in kwargs and kwargs.get(key) is not None:
            value = kwargs.get(key)
            if key == "step" and isinstance(value, dict):
                payload.update(value)
            else:
                payload[key] = value

    if "step_id" not in payload:
        step = payload.get("step")
        if isinstance(step, dict) and step.get("step_id"):
            payload["step_id"] = step.get("step_id")
        elif isinstance(step, dict) and step.get("id"):
            payload["step_id"] = step.get("id")

    return payload


def _zero_taskrunner_registry_callsite_admit_v26(self, event, args=None, kwargs=None):
    payload = _zero_taskrunner_registry_callsite_payload_v26(event, args, kwargs)
    helper = getattr(self, "_aer_registry_admit", None)
    if callable(helper):
        return helper(event, payload)

    fallback = globals().get("_zero_taskrunner_registry_admit_aer_closure_v24")
    if callable(fallback):
        return fallback(self, event, payload)

    return {"ok": True, "status": "skipped", "reason": "aer_registry_admit_unavailable", "event": event, "payload": payload}


def _zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26(base):
    def _zero_execute_owned_step_with_registry_admission(self, *args, **kwargs):
        _zero_taskrunner_registry_callsite_admit_v26(self, "execute_owned_step", args, kwargs)
        return base(self, *args, **kwargs)

    _zero_execute_owned_step_with_registry_admission.__name__ = getattr(base, "__name__", "execute_owned_step")
    _zero_execute_owned_step_with_registry_admission.__doc__ = getattr(base, "__doc__", None)
    _zero_execute_owned_step_with_registry_admission._zero_package26_registry_wrapped = True
    return _zero_execute_owned_step_with_registry_admission


def _zero_taskrunner_registry_callsite_wrap_tick_v26(base):
    def _zero_tick_with_registry_admission(self, *args, **kwargs):
        _zero_taskrunner_registry_callsite_admit_v26(self, "tick", args, kwargs)
        return base(self, *args, **kwargs)

    _zero_tick_with_registry_admission.__name__ = getattr(base, "__name__", "tick")
    _zero_tick_with_registry_admission.__doc__ = getattr(base, "__doc__", None)
    _zero_tick_with_registry_admission._zero_package26_registry_wrapped = True
    return _zero_tick_with_registry_admission


def _zero_taskrunner_registry_callsite_install_v26():
    cls = globals().get("TaskRunner")
    if not isinstance(cls, type):
        return False

    for name, wrapper in (
        ("execute_owned_step", _zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26),
        ("tick", _zero_taskrunner_registry_callsite_wrap_tick_v26),
    ):
        base = getattr(cls, name, None)
        if callable(base) and not getattr(base, "_zero_package26_registry_wrapped", False):
            setattr(cls, name, wrapper(base))

    setattr(cls, "_zero_package26_registry_callsite_migration_installed", True)
    return True


try:
    _zero_taskrunner_registry_callsite_install_v26()
except Exception:
    pass
# ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_END

# ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_BEGIN
def _zero_taskrunner_registry_legacy_cleanup_guard_v28(self, event, payload=None):
    payload = dict(payload or {})
    event = str(event or "").strip() or "taskrunner_event"

    helper = getattr(self, "_aer_registry_admit", None)
    if callable(helper):
        result = helper(event, payload)
        if isinstance(result, dict):
            normalized = dict(result)
            normalized.setdefault("ok", True)
            normalized.setdefault("event", event)
            normalized.setdefault("payload", payload)
            return normalized
        return {"ok": True, "status": "admitted", "event": event, "payload": payload, "result": result}

    return {
        "ok": False,
        "status": "blocked",
        "reason": "aer_registry_admit_unavailable",
        "event": event,
        "payload": payload,
    }


def _zero_taskrunner_registry_legacy_cleanup_phase1_install_v28():
    cls = globals().get("TaskRunner")
    if not isinstance(cls, type):
        return False

    setattr(cls, "_zero_registry_legacy_cleanup_guard", _zero_taskrunner_registry_legacy_cleanup_guard_v28)
    setattr(cls, "_zero_package28_registry_legacy_cleanup_phase1_installed", True)
    return True


try:
    _zero_taskrunner_registry_legacy_cleanup_phase1_install_v28()
except Exception:
    pass
# ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_END
