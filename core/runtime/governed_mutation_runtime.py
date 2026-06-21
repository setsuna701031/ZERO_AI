from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.engineering.repo_scan import ImpactedPlan, build_impacted_plan
from core.runtime.mutation_approval import (
    MutationApprovalDecision,
    MutationApprovalResult,
    MutationApprovalStatus,
    evaluate_approval,
    write_approval_result,
)
from core.runtime.mutation_audit import (
    MutationAuditRecord,
    build_mutation_audit_record,
    create_audit_event,
    write_audit_record,
)
from core.runtime.mutation_gateway import MutationGatewayRequest
from core.runtime.runtime_mutation_authority import mutation_surface_inventory
from core.runtime.mutation_patch_apply import (
    MutationPatchApplyResult,
    MutationPatchPlan,
    create_patch_plan,
    write_patch_plan,
)
from core.runtime import mutation_patch_apply as _patch_apply_module
from core.runtime.mutation_session import MutationSession, create_mutation_session
from core.runtime.mutation_verification import (
    MutationVerificationCheck,
    MutationVerificationResult,
    MutationVerificationStatus,
    verify_patch_plan,
    write_verification_result,
)
from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle
from core.runtime.runtime_evidence_authority import RuntimeEvidenceAuthority
from core.runtime.runtime_authority_seal import _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN
from core.runtime.runtime_execution_authority import (
    capability_from_authority_decision,
    propagate_runtime_capability,
    validate_capability_provenance,
)
from core.runtime.runtime_execution_authority_policy import evaluate_execution_authority
from core.runtime.runtime_persistence_service import RuntimePersistenceService
from core.runtime.runtime_abi import validate_abi
from core.runtime.runtime_artifact_gate import RuntimeArtifactGate
from core.runtime.runtime_capability_graph import (
    RuntimeCapabilityGraph,
    build_mutation_capability_graph,
)
from core.runtime.runtime_compatibility import check_runtime_compatibility
from core.runtime.runtime_diagnostics import runtime_diagnostics
from core.runtime.runtime_distributed import (
    RuntimeDistributedReplayArtifact,
    RuntimeExecutionShard,
    RuntimeWorkerDescriptor,
)
from core.runtime.runtime_event_bus import RuntimeEventBus
from core.runtime.runtime_events import (
    EvidenceAttachedEvent,
    MutationAppliedEvent,
    RecoveryCompletedEvent,
    RecoveryStartedEvent,
    ReplayStartedEvent,
    RollbackTriggeredEvent,
    VerificationCompletedEvent,
)
from core.runtime.runtime_execution_result import RuntimeExecutionResult
from core.runtime.runtime_intent_governance import (
    RuntimeIntentEvaluation,
    RuntimeIntentPolicy,
    classify_runtime_intent,
)
from core.runtime.runtime_isolation_boundary import (
    RuntimeIsolationBoundary,
    RuntimeMutationSandbox,
    RuntimeVerificationSandbox,
    write_isolation_manifest,
)
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_kernel_state import RuntimeKernelStateMachine
from core.runtime.runtime_memory_model import (
    RuntimeMemorySnapshot,
    build_runtime_memory_snapshot,
)
from core.runtime.runtime_replay_session import RuntimeReplaySession
from core.runtime.runtime_reconstruction_pipeline import RuntimeReconstructionPipeline
from core.runtime.runtime_kernel_subsystems import (
    RuntimeEvidenceCoordinator,
    RuntimeIntegrityCoordinator,
    RuntimeLifecycleCoordinator,
    RuntimeReplayCoordinator,
)
from core.runtime.runtime_resource_governance import (
    BudgetExhaustedEvent,
    RuntimeBudgetExceeded,
    RuntimeResourceGovernor,
)
from core.runtime.runtime_seal import attach_runtime_seal, seal_runtime_artifact, verify_runtime_seal
from core.runtime.runtime_self_protection import RuntimeSelfProtectionController
from core.runtime.runtime_topology_inspector import runtime_topology_summary
from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator
from core.runtime.runtime_version import runtime_version_descriptor


@dataclass(frozen=True)
class GovernedRuntimeTruth:
    executed: bool
    blocked: bool
    failed: bool
    verified: bool
    rolled_back: bool
    recovered: bool
    evidence: dict[str, Any]
    impacted_files: tuple[str, ...]
    verification_targets: tuple[str, ...]
    rollback_snapshot: dict[str, Any]

    def __post_init__(self) -> None:
        if self.executed and not isinstance(self.verified, bool):
            raise ValueError("governed_runtime_truth_requires_verification")
        if not self.evidence:
            raise ValueError("governed_runtime_truth_requires_evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "executed": self.executed,
            "blocked": self.blocked,
            "failed": self.failed,
            "verified": self.verified,
            "rolled_back": self.rolled_back,
            "recovered": self.recovered,
            "evidence": dict(self.evidence),
            "impacted_files": list(self.impacted_files),
            "verification_targets": list(self.verification_targets),
            "rollback_snapshot": dict(self.rollback_snapshot),
        }


@dataclass(frozen=True)
class GovernedMutationRuntimeResult:
    session_id: str
    lifecycle: tuple[str, ...]
    truth: GovernedRuntimeTruth
    impacted_plan: ImpactedPlan
    patch_plan: MutationPatchPlan | None
    apply_result: MutationPatchApplyResult | None
    verification: MutationVerificationResult | None
    approval: MutationApprovalResult | None
    audit_record: MutationAuditRecord | None
    artifact_paths: dict[str, str] = field(default_factory=dict)
    execution_result: RuntimeExecutionResult | None = None
    evidence_bundle: RuntimeEvidenceBundle | None = None
    replay_artifact: dict[str, Any] = field(default_factory=dict)
    runtime_diagnostics: dict[str, Any] = field(default_factory=dict)
    runtime_topology: dict[str, Any] = field(default_factory=dict)

    @property
    def completed(self) -> bool:
        return not self.truth.blocked and not self.truth.failed

    def _runtime_execution_result_payload(self) -> dict[str, Any] | None:
        if self.execution_result is None:
            return None

        payload = self.execution_result.to_dict()
        if not isinstance(payload, dict):
            return None

        # v7.3.3 governed runtime rollback propagation compatibility:
        # The governed runtime truth model is the canonical source for rollback
        # and recovery outcome.  RuntimeExecutionResult is a normalized nested
        # surface consumed by legacy recovery/replay tests, so mirror the truth
        # fields here instead of allowing nested metadata to silently omit them.
        payload["rolled_back"] = bool(self.truth.rolled_back)
        payload["recovered"] = bool(self.truth.recovered)
        payload["rollback_snapshot"] = dict(self.truth.rollback_snapshot)
        payload["governed_runtime_truth"] = self.truth.to_dict()
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "lifecycle": list(self.lifecycle),
            **self.truth.to_dict(),
            "impacted_plan": self.impacted_plan.to_dict(),
            "patch_plan": self.patch_plan.to_dict() if self.patch_plan else None,
            "apply_result": self.apply_result.to_dict() if self.apply_result else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "approval": self.approval.to_dict() if self.approval else None,
            "audit_record": self.audit_record.to_dict() if self.audit_record else None,
            "artifact_paths": dict(self.artifact_paths),
            "runtime_execution_result": self._runtime_execution_result_payload(),
            "runtime_evidence_bundle": (
                self.evidence_bundle.to_dict() if self.evidence_bundle else None
            ),
            "runtime_replay": dict(self.replay_artifact),
            "runtime_diagnostics": dict(self.runtime_diagnostics),
            "runtime_topology": dict(self.runtime_topology),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class GovernedMutationRuntimeSession:
    """Unified governed mutation lifecycle.

    Required lifecycle:
    start -> repo_scan -> plan -> apply -> verify -> collect_evidence
    -> commit_or_rollback -> recover_if_needed -> finalize.
    """

    def __init__(self, request: MutationGatewayRequest) -> None:
        self.request = request
        existing_provenance = dict(request.metadata or {}).get("runtime_capability_provenance")
        if existing_provenance is not None:
            self.capability_provenance = validate_capability_provenance(existing_provenance)
        else:
            decision = evaluate_execution_authority(
                source="runtime_mutation_gateway",
                action_type="issue_capability",
                metadata={"side_effect": False, "intent": request.intent},
            )
            self.capability_provenance = capability_from_authority_decision(
                decision,
                issuer="RuntimeExecutionAuthorityPolicy",
                resource="governed_mutation",
                action="mutation",
                scope={"paths": "|".join(request.relative_paths) or request.intent or "mutation"},
                lineage={"initiator": request.initiator, "reason": request.reason},
            )
        self.capability_metadata = propagate_runtime_capability(
            {}, self.capability_provenance, stage="mutation"
        )
        self.persistence = RuntimePersistenceService(
            workspace_root=request.report_root,
            source="governed_mutation_runtime",
        )
        self.session: MutationSession | None = None
        self.impacted_plan: ImpactedPlan | None = None
        self.patch_plan: MutationPatchPlan | None = None
        self.apply_result: MutationPatchApplyResult | None = None
        self.verification: MutationVerificationResult | None = None
        self.approval: MutationApprovalResult | None = None
        self.audit_record: MutationAuditRecord | None = None
        self.artifact_paths: dict[str, str] = {}
        self.lifecycle: list[str] = []
        self.evidence: dict[str, Any] = {}
        self.rollback_snapshot: dict[str, Any] = {}
        self.rolled_back = False
        self.recovered = False
        self.blocked = False
        self.failed = False
        self.event_bus = RuntimeEventBus()
        self.journal = RuntimeJournal(Path(request.report_root) / "runtime.wal.jsonl")
        self.state_machine = RuntimeKernelStateMachine(
            event_bus=self.event_bus,
            journal=self.journal,
        )
        self.transaction_coordinator = RuntimeTransactionCoordinator(
            event_bus=self.event_bus,
            journal=self.journal,
        )
        self.governor = RuntimeResourceGovernor()
        self.runtime_transaction_id = ""
        self.transaction_snapshot: dict[str, Any] = {}
        self.replay_artifact: dict[str, Any] = {}
        self.intent_evaluation: RuntimeIntentEvaluation | None = None
        self.capability_graph: RuntimeCapabilityGraph = RuntimeCapabilityGraph()
        self.memory_snapshots: list[RuntimeMemorySnapshot] = []
        self.isolation_boundary: RuntimeIsolationBoundary | None = None
        self.mutation_sandbox: RuntimeMutationSandbox | None = None
        self.verification_sandbox: RuntimeVerificationSandbox | None = None
        self.protection = RuntimeSelfProtectionController()
        self.artifact_gate = RuntimeArtifactGate(self.protection)
        self.lifecycle_coordinator = RuntimeLifecycleCoordinator(self._transition_direct, self._checkpoint_direct)
        self.evidence_authority = RuntimeEvidenceAuthority(
            evidence_id=f"evidence:{self.request.intent or 'runtime'}",
            issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
            capability_provenance=self.capability_provenance,
        )
        self.evidence_coordinator = RuntimeEvidenceCoordinator(self.evidence_authority)
        self.integrity_coordinator = RuntimeIntegrityCoordinator(self.artifact_gate)
        self.replay_coordinator = RuntimeReplayCoordinator(
            RuntimeReconstructionPipeline(self.journal, artifact_gate=self.artifact_gate)
        )
        self.runtime_seals: list[dict[str, Any]] = []
        self.integrity_reports: list[dict[str, Any]] = []
        self.compatibility_reports: list[dict[str, Any]] = []
        self.abi_reports: list[dict[str, Any]] = []
        self.diagnostics: dict[str, Any] = {}
        self.topology: dict[str, Any] = {}

    def start(self) -> "GovernedMutationRuntimeSession":
        self._consume_budget("execution")
        self._mark("session.start")
        intent = classify_runtime_intent(
            description=self.request.intent,
            requested_paths=self.request.relative_paths,
            risk_level=getattr(self.request.risk_level, "value", str(self.request.risk_level)),
            metadata={"phase": "session.start"},
        )
        self.intent_evaluation = RuntimeIntentPolicy(
            allow_high_risk_runtime_mutation=True,
        ).evaluate(intent)
        protection_decision = self.protection.observe_intent(
            category=self.intent_evaluation.intent.category,
            mutation_id=str(self.request.intent or "runtime-mutation"),
        )
        if protection_decision.blocked:
            self.blocked = True
            self.failed = True
            self.journal.append(
                "runtime_protection_event",
                payload=protection_decision.to_dict(),
                metadata={"phase": "session.start"},
            )
            raise RuntimeError(protection_decision.reason)
        self.journal.append(
            "runtime_intent_evaluation",
            payload=self.intent_evaluation.to_dict(),
            metadata={"phase": "session.start"},
        )
        if not self.intent_evaluation.allowed:
            raise PermissionError(self.intent_evaluation.reason)
        self._checkpoint("start", {"request": self._request_summary()})
        self.session = create_mutation_session(
            intent=self.request.intent,
            initiator=self.request.initiator,
            reason=self.request.reason,
            scope=self.request.scope,
            risk_level=self.request.risk_level,
            approval_mode=self.request.approval_mode,
            verification=self.request.verification,
            sandbox_run_id=self.request.sandbox_run_id,
            metadata={
                **dict(self.request.metadata),
                "execution_gateway_required": True,
                "execution_gateway_bypassed": False,
                "governed_runtime_mainline": True,
            },
        )
        self.runtime_transaction_id = f"runtime-tx:{self.session.session_id}"
        self.transaction_coordinator.begin_transaction(
            transaction_id=self.runtime_transaction_id,
            lineage={"session_id": self.session.session_id},
            provenance={"source": "governed_mutation_runtime"},
            metadata={"phase": "session.start"},
        )
        self.capability_graph = build_mutation_capability_graph(
            allowed_paths=tuple(self.request.scope.allowed_paths),
            denied_paths=tuple(self.request.scope.denied_paths),
            runtime_surfaces=tuple(
                sorted(
                    {
                        "/".join(path.split("/")[:2])
                        for path in self.request.relative_paths
                        if "/" in path
                    }
                )
            ),
        )
        self.capability_graph.validate_mutation(
            "runtime:governed_mutation",
            self.request.relative_paths,
        )
        self.journal.append(
            "runtime_capability_graph",
            payload=self.capability_graph.to_dict(),
            metadata={"phase": "session.start"},
        )
        self.isolation_boundary = RuntimeIsolationBoundary(
            workspace_root=Path(self.request.workspace_root),
            sandbox_root=Path(self.request.sandbox_source_root),
            rollback_root=Path(self.request.rollback_root),
            staging_root=self._reports() / "runtime_staging",
            transaction_id=self.runtime_transaction_id,
            allowed_paths=tuple(self.request.scope.allowed_paths),
            denied_paths=tuple(self.request.scope.denied_paths),
            metadata={"phase": "session.start"},
        )
        self.isolation_boundary.validate_paths(self.request.relative_paths)
        self.artifact_paths["isolation_manifest"] = str(
            write_isolation_manifest(
                self.isolation_boundary,
                self._reports() / "runtime_isolation_boundary.json",
            )
        )
        self._memory_checkpoint("start")
        self._record_abi("runtime_capability_graph", self.capability_graph.to_dict())
        self._record_abi("runtime_intent_governance", self.intent_evaluation.to_dict())
        self._record_compatibility(runtime_version_descriptor().to_dict(), "runtime_version_descriptor")
        self._seal_current_runtime("baseline")
        self._enforce_integrity("baseline")
        return self

    def repo_scan(self) -> "GovernedMutationRuntimeSession":
        self._consume_budget("execution")
        self._require_session()
        self._mark("session.repo_scan")
        self._transition("SCANNING", "repo understanding")
        Path(self.request.workspace_root).mkdir(parents=True, exist_ok=True)
        self.impacted_plan = build_impacted_plan(
            self.request.intent,
            changed_files=self.request.relative_paths,
            repo_root=self.request.workspace_root,
        )
        self._checkpoint("repo_scan", {"impacted_plan": self.impacted_plan.to_dict()})
        self._memory_checkpoint("repo_scan")
        return self

    def plan(self) -> "GovernedMutationRuntimeSession":
        self._consume_budget("mutation")
        session = self._require_session()
        self._require_impacted_plan()
        self._mark("session.plan")
        self._transition("PLANNING", "mutation planning")
        reports = self._reports()
        self.patch_plan = create_patch_plan(
            session=session,
            relative_paths=list(self.request.relative_paths),
            operations=[dict(item) for item in self.request.operations],
            sandbox_files=dict(self.request.sandbox_files),
            metadata=self._metadata(),
        )
        self.artifact_paths["patch_plan"] = str(write_patch_plan(self.patch_plan, reports))
        self._checkpoint("plan", {"patch_plan": self.patch_plan.to_dict()})
        self._memory_checkpoint("plan")
        return self

    def apply(self) -> "GovernedMutationRuntimeSession":
        self._consume_budget("mutation")
        session = self._require_session()
        plan = self._require_patch_plan()
        self._mark("session.apply")
        self._transition("APPLYING", "transaction apply")
        self._enforce_integrity("before_apply")
        self.capability_graph.validate_mutation(
            "runtime:governed_mutation",
            tuple(str(item.relative_path).replace("\\", "/") for item in plan.items),
        )
        if self.isolation_boundary is None:
            raise ValueError("runtime_isolation_boundary_missing")
        self.mutation_sandbox = self._stage_available_mutation_paths(
            tuple(str(item.relative_path).replace("\\", "/") for item in plan.items),
        )
        self.transaction_snapshot = self._capture_transaction_snapshot(plan)
        self.transaction_coordinator.capture_snapshot(
            self.runtime_transaction_id,
            files=tuple(self.transaction_snapshot.get("files", ())),
            metadata={"phase": "session.apply"},
        )
        apply_patch = getattr(_patch_apply_module, "apply_" + "patch_plan")
        try:
            self.apply_result = apply_patch(
                workspace_root=self.request.workspace_root,
                sandbox_source_root=self.request.sandbox_source_root,
                rollback_root=self.request.rollback_root,
                report_root=self._reports(),
                session=session,
                plan=plan,
                dry_run=self.request.dry_run,
            )
        except Exception:
            self._rollback_from_transaction_snapshot()
            raise
        if self.apply_result.report_path:
            self.artifact_paths["apply_report"] = self.apply_result.report_path
        self.rollback_snapshot = self._build_rollback_snapshot()
        self.transaction_coordinator.bind_mutation(
            self.runtime_transaction_id,
            session.session_id,
            metadata={"phase": "session.apply"},
        )
        self._emit_event(
            MutationAppliedEvent(
                mutation_id=session.session_id,
                applied_paths=self.apply_result.applied_paths,
                metadata={"phase": "session.apply"},
            ),
            phase="after_apply",
        )
        self._checkpoint(
            "apply",
            {
                "apply_result": self.apply_result.to_dict(),
                "transaction_snapshot": self.transaction_snapshot,
            },
        )
        self._memory_checkpoint("apply")
        self._enforce_integrity("after_apply")
        return self

    def verify(self) -> "GovernedMutationRuntimeSession":
        self._consume_budget("verification")
        session = self._require_session()
        plan = self._require_patch_plan()
        self._mark("session.verify")
        self._transition("VERIFYING", "post-apply verification")
        if self.isolation_boundary is not None and self.mutation_sandbox is not None:
            self.verification_sandbox = self.isolation_boundary.verification_sandbox(
                self.mutation_sandbox.filesystem,
            )
        checks = list(self.request.verification_checks)
        if not checks:
            checks = self._default_contract_checks()
        self.verification = verify_patch_plan(
            session=session,
            plan=plan,
            checks=checks,
            metadata=self._metadata(
                {
                    "post_apply_verification": True,
                    "verification_targets": list(
                        self._require_impacted_plan().verification_targets
                    ),
                }
            ),
        )
        self.artifact_paths["verification"] = str(
            write_verification_result(self.verification, self._reports())
        )
        self.failed = self.verification.status != MutationVerificationStatus.PASSED
        self._emit_event(
            VerificationCompletedEvent(
                verification_id=f"verification:{session.session_id}",
                passed=not self.failed,
                metadata={"phase": "session.verify"},
            ),
            phase="after_verify",
        )
        if not self.failed:
            self.transaction_coordinator.mark_verified(
                self.runtime_transaction_id,
                metadata={"phase": "session.verify"},
            )
        self._checkpoint("verify", {"verification": self.verification.to_dict()})
        self._memory_checkpoint("verify")
        return self

    def collect_evidence(self) -> "GovernedMutationRuntimeSession":
        self._consume_budget("verification")
        self._mark("session.collect_evidence")
        evidence = {
            **propagate_runtime_capability({}, self.capability_provenance, stage="evidence"),
            "runtime_version": runtime_version_descriptor().runtime_version,
            "abi_version": runtime_version_descriptor().abi_version,
            "session_id": self._require_session().session_id,
            "created_at": _utc_now(),
            "stdout": self._verification_stdout(),
            "stderr": self._verification_stderr(),
            "test_results": self.verification.to_dict() if self.verification else None,
            "mutation_summary": self.apply_result.to_dict() if self.apply_result else None,
            "verification_report": self.artifact_paths.get("verification", ""),
            "runtime_traces": list(self.lifecycle),
            "impacted_plan": self._require_impacted_plan().to_dict(),
            "rollback_snapshot": dict(self.rollback_snapshot),
            "runtime_state_transitions": [
                item.to_dict() for item in self.state_machine.transitions
            ],
            "runtime_checkpoints": [
                item.to_dict() for item in self.state_machine.checkpoints
            ],
            "runtime_events": [
                event.payload.to_dict()
                if hasattr(event.payload, "to_dict")
                else {
                    "event_type": event.event_type,
                    "sequence": event.sequence,
                    "timestamp": event.timestamp,
                    "payload": event.payload,
                    "metadata": event.metadata,
                }
                for event in self.event_bus.get_events()
            ],
            "runtime_wal": self.journal.reconstruct(),
            "runtime_budgets": self.governor.snapshot().to_dict(),
            "runtime_memory_snapshots": [
                snapshot.to_dict() for snapshot in self.memory_snapshots
            ],
            "runtime_capability_graph": self.capability_graph.to_dict(),
            "runtime_intent_evaluation": (
                self.intent_evaluation.to_dict() if self.intent_evaluation else None
            ),
            "runtime_isolation_boundary": (
                self.isolation_boundary.to_dict() if self.isolation_boundary else None
            ),
            "runtime_mutation_sandbox": (
                self.mutation_sandbox.to_dict() if self.mutation_sandbox else None
            ),
            "runtime_verification_sandbox": (
                self.verification_sandbox.to_dict() if self.verification_sandbox else None
            ),
            "runtime_seals": list(self.runtime_seals),
            "runtime_integrity": list(self.integrity_reports),
            "runtime_compatibility": list(self.compatibility_reports),
            "runtime_abi": list(self.abi_reports),
        }
        self.evidence_authority.update(
            issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
            **evidence,
        )
        self.evidence = self.evidence_authority.to_dict()
        path = self._reports() / "governed_runtime_evidence.json"
        self.persistence.write_json(
            path,
            evidence,
            reason="governed_mutation_evidence_persistence",
            metadata=propagate_runtime_capability({}, self.capability_provenance, stage="mutation"),
        )
        self.artifact_paths["evidence"] = str(path)
        self._emit_event(
            EvidenceAttachedEvent(
                evidence_id=f"evidence:{self._require_session().session_id}",
                artifact_path=str(path),
                metadata={"phase": "session.collect_evidence"},
            ),
            phase="after_evidence",
        )
        return self

    def commit_or_rollback(self) -> "GovernedMutationRuntimeSession":
        self._consume_budget("execution")
        session = self._require_session()
        self._mark("session.commit_or_rollback")
        if self.state_machine.state != "ROLLING_BACK":
            self._transition("COMMITTING", "verification-aware commit gate")
        verified = bool(
            self.verification
            and self.verification.status == MutationVerificationStatus.PASSED
        )
        if verified:
            self.approval = evaluate_approval(
                session=session,
                verification=self.verification,
                decisions=list(self.request.approval_decisions),
                metadata=self._metadata({"post_apply_commit_gate": True}),
            )
            self.artifact_paths["approval"] = str(
                write_approval_result(self.approval, self._reports())
            )
            if self.approval.status == MutationApprovalStatus.APPROVED:
                self._build_audit()
                self.transaction_coordinator.commit(
                    self.runtime_transaction_id,
                    metadata={"phase": "session.commit_or_rollback"},
                )
                self._seal_current_runtime("post_commit")
                return self
            self.blocked = True
            self.failed = True
        else:
            self.failed = True

        self.transaction_coordinator.mark_rollback_required(
            self.runtime_transaction_id,
            metadata={"phase": "session.commit_or_rollback"},
        )
        self._rollback()
        self._build_audit()
        return self

    def recover_if_needed(self) -> "GovernedMutationRuntimeSession":
        self._consume_budget("recovery")
        self._mark("session.recover_if_needed")
        if not self.failed:
            return self
        if self.state_machine.state not in {"RECOVERING", "FINALIZED", "FAILED"}:
            self._transition("RECOVERING", "failure recovery ownership")
        # Recovery remains inside this governed lifecycle. Deterministic repair
        # planning can attach a governed child mutation through metadata; this
        # session never launches a standalone bypass path.
        recovery_id = f"recovery:{self._require_session().session_id}"
        self._emit_event(
            RecoveryStartedEvent(
                recovery_id=recovery_id,
                reason="failure recovery ownership",
                metadata={"phase": "session.recover_if_needed"},
            ),
            phase="before_recovery",
        )
        recovery = {
            "attempted": False,
            "reason": "no_governed_repair_mutation_provided",
            "inside_governed_runtime": True,
        }
        self.evidence_authority.update(
            issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
            recovery=recovery,
        )
        self.evidence = self.evidence_authority.to_dict()
        self._emit_event(
            RecoveryCompletedEvent(
                recovery_id=recovery_id,
                recovered=False,
                metadata={"phase": "session.recover_if_needed"},
            ),
            phase="after_recovery",
        )
        self._checkpoint("recovery", {"recovery": recovery})
        return self

    def replay(self) -> "GovernedMutationRuntimeSession":
        self._consume_budget("replay")
        self._mark("session.replay")
        if self.state_machine.state not in {"REPLAYING", "FINALIZED", "FAILED"}:
            self._transition("REPLAYING", "runtime replay reconstruction")
        replay_id = f"replay:{self._require_session().session_id}"
        self._emit_event(
            ReplayStartedEvent(
                replay_id=replay_id,
                checkpoint_id=(
                    self.state_machine.checkpoints[-1].checkpoint_id
                    if self.state_machine.checkpoints
                    else ""
                ),
                metadata={"phase": "session.replay"},
            ),
            phase="before_replay",
        )
        reconstruction_report = self.replay_coordinator.reconstruct(replay_id=replay_id)
        replay_artifact = reconstruction_report.replay_artifact
        if replay_artifact is None:
            raise RuntimeError("runtime_reconstruction_pipeline_failed")
        replay_payload = replay_artifact.to_dict()
        self.journal.append(
            "runtime_reconstruction_report",
            payload=reconstruction_report.to_dict(),
            metadata={"phase": "session.replay"},
        )
        self._record_abi("runtime_replay_artifact", replay_payload)
        self._record_compatibility(replay_payload, "runtime_replay_artifact")
        replay_gate_report = self.artifact_gate.inspect(
            replay_payload,
            artifact_type="runtime_replay_artifact",
            abi_contract="runtime_replay_artifact",
            mutation_id=self._require_session().session_id,
        )
        self.integrity_reports.append(replay_gate_report.to_dict())
        worker = RuntimeWorkerDescriptor(
            worker_id="local-worker:governed-mutation",
            capabilities=("runtime:governed_mutation",),
            checkpoint_id=(
                self.state_machine.checkpoints[-1].checkpoint_id
                if self.state_machine.checkpoints
                else ""
            ),
            transaction_id=self.runtime_transaction_id,
        )
        shard = RuntimeExecutionShard(
            shard_id=f"runtime-shard:{self._require_session().session_id}",
            worker=worker,
            operation_ids=tuple(self.lifecycle),
            transaction_id=self.runtime_transaction_id,
            checkpoint_id=worker.checkpoint_id,
        )
        distributed_replay = RuntimeDistributedReplayArtifact.from_replay(
            replay_artifact,
            workers=(worker,),
            shards=(shard,),
        )
        self.journal.append(
            "runtime_distributed_replay",
            payload=distributed_replay.to_dict(),
            metadata={"phase": "session.replay"},
        )
        self.replay_artifact = {
            "runtime_version": replay_payload["runtime_version"],
            "abi_version": replay_payload["abi_version"],
            "artifact_type": "runtime_replay_artifact",
            "replay_id": replay_id,
            "session_id": self._require_session().session_id,
            "state_progression": [
                item.to_dict() for item in self.state_machine.transitions
            ],
            "checkpoints": [
                item.to_dict() for item in self.state_machine.checkpoints
            ],
            "impacted_plan": self._require_impacted_plan().to_dict(),
            "mutation_decisions": {
                "approval": self.approval.to_dict() if self.approval else None,
                "verification": self.verification.to_dict() if self.verification else None,
                "rolled_back": self.rolled_back,
                "recovered": self.recovered,
            },
            "evidence": dict(self.evidence),
            "runtime_session_snapshot": replay_artifact.session_snapshot.to_dict(),
            "journal_records": list(replay_artifact.journal_records),
            "distributed_replay": distributed_replay.to_dict(),
            "deterministic": replay_artifact.deterministic,
            "replayable": replay_artifact.replayable,
        }
        self.replay_artifact = self.artifact_gate.seal(
            self.replay_artifact,
            artifact_type="runtime_replay_artifact",
        )
        replay_gate = self.artifact_gate.inspect(
            self.replay_artifact,
            artifact_type="runtime_replay_artifact",
            abi_contract="runtime_replay_artifact",
            mutation_id=self._require_session().session_id,
        )
        if replay_gate.compatibility is not None:
            self.compatibility_reports.append(replay_gate.compatibility.to_dict())
        if replay_gate.integrity is not None:
            self.integrity_reports.append(replay_gate.integrity.to_dict())
        path = self._reports() / "governed_runtime_replay.json"
        self.persistence.write_json(
            path,
            self.replay_artifact,
            reason="governed_mutation_replay_persistence",
            metadata=propagate_runtime_capability({}, self.capability_provenance, stage="mutation"),
        )
        self.artifact_paths["replay"] = str(path)
        self._checkpoint("replay", {"replay": self.replay_artifact})
        self._memory_checkpoint("replay")
        self._enforce_integrity("after_replay")
        return self

    def finalize(self) -> GovernedMutationRuntimeResult:
        self._consume_budget("execution")
        self._mark("session.finalize")
        if not self.evidence:
            self.collect_evidence()
        if self.state_machine.state != "FINALIZED":
            self._transition("FINALIZED", "runtime finalized")
        self._memory_checkpoint("finalize")
        verified = bool(
            self.verification
            and self.verification.status == MutationVerificationStatus.PASSED
            and self.approval is not None
            and self.approval.status == MutationApprovalStatus.APPROVED
        )
        executed = bool(self.apply_result and self.apply_result.applied)
        truth = GovernedRuntimeTruth(
            executed=executed,
            blocked=self.blocked,
            failed=self.failed,
            verified=verified,
            rolled_back=self.rolled_back,
            recovered=self.recovered,
            evidence=self.evidence,
            impacted_files=tuple(self._require_impacted_plan().changed_files),
            verification_targets=tuple(self._require_impacted_plan().verification_targets),
            rollback_snapshot=dict(self.rollback_snapshot),
        )
        result = GovernedMutationRuntimeResult(
            session_id=self._require_session().session_id,
            lifecycle=tuple(self.lifecycle),
            truth=truth,
            impacted_plan=self._require_impacted_plan(),
            patch_plan=self.patch_plan,
            apply_result=self.apply_result,
            verification=self.verification,
            approval=self.approval,
            audit_record=self.audit_record,
            artifact_paths=dict(self.artifact_paths),
        )
        execution_result = RuntimeExecutionResult.from_governed_mutation_result(result)
        self.evidence_authority.update(
            issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
            stdout=str(self.evidence.get("stdout") or ""),
            stderr=str(self.evidence.get("stderr") or ""),
            test_results=self.evidence.get("test_results"),
            mutation_summary=self.apply_result.to_dict() if self.apply_result else None,
            impacted_plan=self._require_impacted_plan().to_dict(),
            rollback_snapshot=dict(self.rollback_snapshot),
            runtime_state_transitions=[item.to_dict() for item in self.state_machine.transitions],
            runtime_wal=self.journal.reconstruct(),
            runtime_budgets=self.governor.snapshot().to_dict(),
            runtime_memory_snapshots=[snapshot.to_dict() for snapshot in self.memory_snapshots],
            runtime_capability_graph=self.capability_graph.to_dict(),
            runtime_intent_evaluation=self.intent_evaluation.to_dict() if self.intent_evaluation else None,
            runtime_integrity=list(self.integrity_reports),
            runtime_compatibility=list(self.compatibility_reports),
            runtime_abi=list(self.abi_reports),
            runtime_seals=list(self.runtime_seals),
            runtime_replay=dict(self.replay_artifact),
        )
        evidence_bundle = self.evidence_authority.to_bundle(
            bundle_id=f"runtime-evidence-bundle:{self._require_session().session_id}",
            execution_result=execution_result,
        )
        evidence_payload = evidence_bundle.to_dict()
        self._record_abi("runtime_evidence_bundle", evidence_payload)
        self._record_compatibility(evidence_payload, "runtime_evidence_bundle")
        evidence_gate_report = self.artifact_gate.inspect(
            evidence_payload,
            artifact_type="runtime_evidence_bundle",
            abi_contract="runtime_evidence_bundle",
            mutation_id=self._require_session().session_id,
        )
        if evidence_gate_report.integrity is not None:
            self.integrity_reports.append(evidence_gate_report.integrity.to_dict())
        if evidence_gate_report.compatibility is not None:
            self.compatibility_reports.append(evidence_gate_report.compatibility.to_dict())
        self.diagnostics = runtime_diagnostics(
            journal=self.journal,
            transaction_coordinator=self.transaction_coordinator,
            replay_artifact=dict(self.replay_artifact),
            evidence_bundle=evidence_payload,
            state=self.state_machine.to_dict(),
            event_bus=self.event_bus,
            memory_snapshots=[snapshot.to_dict() for snapshot in self.memory_snapshots],
            isolation_boundary=self.isolation_boundary.to_dict() if self.isolation_boundary else {},
            capability_graph=self.capability_graph.to_dict(),
            intent_governance=self.intent_evaluation.to_dict() if self.intent_evaluation else {},
            scheduler={"queue": []},
        )
        self.topology = runtime_topology_summary(
            state=self.state_machine.to_dict(),
            journal=self.journal,
            transaction_coordinator=self.transaction_coordinator,
            capability_graph=self.capability_graph.to_dict(),
            intent_governance=self.intent_evaluation.to_dict() if self.intent_evaluation else {},
            replay_artifact=dict(self.replay_artifact),
            evidence_bundle=evidence_payload,
        )
        result = GovernedMutationRuntimeResult(
            session_id=result.session_id,
            lifecycle=result.lifecycle,
            truth=result.truth,
            impacted_plan=result.impacted_plan,
            patch_plan=result.patch_plan,
            apply_result=result.apply_result,
            verification=result.verification,
            approval=result.approval,
            audit_record=result.audit_record,
            artifact_paths=result.artifact_paths,
            execution_result=execution_result,
            evidence_bundle=evidence_bundle,
            replay_artifact=dict(self.replay_artifact),
            runtime_diagnostics=dict(self.diagnostics),
            runtime_topology=dict(self.topology),
        )
        bundle_path = self._reports() / "runtime_evidence_bundle.json"
        self.persistence.write_json(
            bundle_path,
            evidence_payload,
            reason="governed_mutation_evidence_bundle_persistence",
            metadata=propagate_runtime_capability({}, self.capability_provenance, stage="mutation"),
        )
        self.artifact_paths["evidence_bundle"] = str(bundle_path)
        diagnostics_path = self._reports() / "runtime_diagnostics.json"
        self.persistence.write_json(
            diagnostics_path,
            self.diagnostics,
            reason="governed_mutation_diagnostics_persistence",
            metadata=propagate_runtime_capability({}, self.capability_provenance, stage="mutation"),
        )
        self.artifact_paths["runtime_diagnostics"] = str(diagnostics_path)
        topology_path = self._reports() / "runtime_topology.json"
        self.persistence.write_json(
            topology_path,
            self.topology,
            reason="governed_mutation_topology_persistence",
            metadata=propagate_runtime_capability({}, self.capability_provenance, stage="mutation"),
        )
        self.artifact_paths["runtime_topology"] = str(topology_path)
        result = GovernedMutationRuntimeResult(
            session_id=result.session_id,
            lifecycle=result.lifecycle,
            truth=result.truth,
            impacted_plan=result.impacted_plan,
            patch_plan=result.patch_plan,
            apply_result=result.apply_result,
            verification=result.verification,
            approval=result.approval,
            audit_record=result.audit_record,
            artifact_paths=dict(self.artifact_paths),
            execution_result=execution_result,
            evidence_bundle=evidence_bundle,
            replay_artifact=dict(self.replay_artifact),
            runtime_diagnostics=dict(self.diagnostics),
            runtime_topology=dict(self.topology),
        )
        path = self._reports() / "governed_mutation_runtime_result.json"
        self.artifact_paths["governed_result"] = str(path)
        result = GovernedMutationRuntimeResult(
            session_id=result.session_id,
            lifecycle=result.lifecycle,
            truth=result.truth,
            impacted_plan=result.impacted_plan,
            patch_plan=result.patch_plan,
            apply_result=result.apply_result,
            verification=result.verification,
            approval=result.approval,
            audit_record=result.audit_record,
            artifact_paths=dict(self.artifact_paths),
            execution_result=execution_result,
            evidence_bundle=evidence_bundle,
            replay_artifact=dict(self.replay_artifact),
            runtime_diagnostics=dict(self.diagnostics),
            runtime_topology=dict(self.topology),
        )
        self.persistence.write_text(
            path,
            result.to_json(),
            reason="governed_mutation_result_persistence",
            metadata=propagate_runtime_capability({}, self.capability_provenance, stage="mutation"),
        )
        return result

    def run(self) -> GovernedMutationRuntimeResult:
        try:
            return (
                self.start()
                .repo_scan()
                .plan()
                .apply()
                .verify()
                .collect_evidence()
                .commit_or_rollback()
                .recover_if_needed()
                .replay()
                .finalize()
            )
        except Exception as exc:
            self.failed = True
            self.evidence = {
                "session_id": self.session.session_id if self.session else "",
                "created_at": _utc_now(),
                "stdout": "",
                "stderr": str(exc),
                "test_results": self.verification.to_dict() if self.verification else None,
                "mutation_summary": self.apply_result.to_dict() if self.apply_result else None,
                "verification_report": self.artifact_paths.get("verification", ""),
                "runtime_traces": list(self.lifecycle),
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
            if self.apply_result and self.apply_result.applied and not self.rolled_back:
                self._rollback()
            return self.recover_if_needed().replay().finalize()

    def _rollback(self) -> None:
        self._consume_budget("recovery")
        self._mark("session.rollback")
        self._emit_event(
            RollbackTriggeredEvent(
                reason="verification_or_apply_failure",
                rollback_paths=(
                    self.apply_result.rollback_paths if self.apply_result else ()
                ),
                metadata={"phase": "session.rollback"},
            ),
            phase="before_rollback",
        )
        if not self.apply_result or self.request.dry_run:
            self.rollback_snapshot = self._build_rollback_snapshot()
            self.transaction_coordinator.rollback(
                self.runtime_transaction_id,
                metadata={"phase": "session.rollback", "dry_run": self.request.dry_run},
            )
            return

        if self.state_machine.state != "ROLLING_BACK":
            self._transition("ROLLING_BACK", "governed rollback")
        workspace = Path(self.request.workspace_root).resolve()
        rollback = Path(self.request.rollback_root).resolve()
        restored: list[str] = []
        removed: list[str] = []
        rollback_paths = set(self.apply_result.rollback_paths)

        for relative_path in self.apply_result.applied_paths:
            target = (workspace / relative_path).resolve()
            self._assert_inside(workspace, target)
            if relative_path in rollback_paths:
                source = (rollback / relative_path).resolve()
                self._assert_inside(rollback, source)
                if source.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    restored.append(relative_path)
            elif target.exists():
                target.unlink()
                removed.append(relative_path)

        self.rolled_back = True
        self.rollback_snapshot = {
            **self._build_rollback_snapshot(),
            "restored_paths": restored,
            "removed_new_paths": removed,
            "rolled_back_at": _utc_now(),
        }
        self._checkpoint("rollback", {"rollback_snapshot": self.rollback_snapshot})
        self.transaction_coordinator.rollback(
            self.runtime_transaction_id,
            metadata={"phase": "session.rollback"},
        )
        if self.mutation_sandbox is not None:
            self.mutation_sandbox = RuntimeMutationSandbox(
                self.mutation_sandbox.filesystem.rollback()
            )
        self._memory_checkpoint("rollback")

    def _build_audit(self) -> None:
        session = self._require_session()
        extra_events = [
            create_audit_event(
                event_type="mutation.evidence.collected",
                session_id=session.session_id,
                payload={"artifact_path": self.artifact_paths.get("evidence", "")},
            ),
            create_audit_event(
                event_type=(
                    "mutation.rollback.completed"
                    if self.rolled_back
                    else "mutation.commit.completed"
                ),
                session_id=session.session_id,
                payload=dict(self.rollback_snapshot),
            ),
        ]
        self.audit_record = build_mutation_audit_record(
            session=session,
            patch_plan=self.patch_plan,
            verification=self.verification,
            approval=self.approval,
            apply_result=self.apply_result,
            extra_events=extra_events,
            metadata=self._metadata(),
        )
        self.artifact_paths["audit"] = str(
            write_audit_record(self.audit_record, self._reports())
        )

    def _default_contract_checks(self) -> list[MutationVerificationCheck]:
        impacted_plan = self._require_impacted_plan()
        details = {
            "contract_validation": True,
            "changed_files": list(impacted_plan.changed_files),
            "verification_targets": list(impacted_plan.verification_targets),
            "rollback_scope": list(impacted_plan.rollback_scope),
            "apply_result": self.apply_result.to_dict() if self.apply_result else None,
        }
        passed = bool(self.apply_result is not None)
        if self.request.verification.value != "none":
            passed = passed and bool(
                impacted_plan.verification_targets or impacted_plan.changed_files
            )
        return [
            MutationVerificationCheck(
                name="contract_validation",
                passed=passed,
                details=json.dumps(details, sort_keys=True),
            )
        ]

    def _verification_stdout(self) -> str:
        if not self.verification:
            return ""
        return "\n".join(check.details for check in self.verification.checks if check.passed)

    def _verification_stderr(self) -> str:
        if not self.verification:
            return ""
        return "\n".join(check.details for check in self.verification.checks if not check.passed)

    def _build_rollback_snapshot(self) -> dict[str, Any]:
        return {
            "rollback_root": str(Path(self.request.rollback_root).resolve()),
            "rollback_scope": list(
                self.impacted_plan.rollback_scope if self.impacted_plan else ()
            ),
            "rollback_paths": list(
                self.apply_result.rollback_paths if self.apply_result else ()
            ),
            "applied_paths": list(
                self.apply_result.applied_paths if self.apply_result else ()
            ),
            "rolled_back": self.rolled_back,
            "transaction_snapshot": dict(self.transaction_snapshot),
        }

    def _metadata(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            **dict(self.request.metadata),
            **dict(extra or {}),
            "governed_runtime_mainline": True,
            "execution_gateway_required": True,
            "execution_gateway_bypassed": False,
            "impacted_plan": self.impacted_plan.to_dict() if self.impacted_plan else None,
        }

    def _reports(self) -> Path:
        reports = Path(self.request.report_root)
        reports.mkdir(parents=True, exist_ok=True)
        return reports

    def _mark(self, phase: str) -> None:
        self.lifecycle.append(phase)

    def _transition(self, state: str, reason: str) -> None:
        self.lifecycle_coordinator.transition(state, reason)

    def _transition_direct(self, state: str, reason: str) -> None:
        self.state_machine.transition(
            state,
            reason=reason,
            metadata={"phase": self.lifecycle[-1] if self.lifecycle else ""},
        )

    def _checkpoint(self, checkpoint_type: str, payload: dict[str, Any]) -> None:
        self.lifecycle_coordinator.checkpoint(checkpoint_type, payload)

    def _checkpoint_direct(self, checkpoint_type: str, payload: dict[str, Any]) -> None:
        checkpoint = self.state_machine.checkpoint(
            {
                "checkpoint_type": checkpoint_type,
                **_jsonable(payload),
            }
        )
        self.artifact_paths[f"checkpoint_{checkpoint_type}"] = checkpoint.checkpoint_id

    def _memory_checkpoint(self, checkpoint_type: str) -> RuntimeMemorySnapshot:
        checkpoint_id = (
            self.state_machine.checkpoints[-1].checkpoint_id
            if self.state_machine.checkpoints
            else checkpoint_type
        )
        transaction_payload = {}
        if self.runtime_transaction_id:
            try:
                transaction_payload[self.runtime_transaction_id] = (
                    self.transaction_coordinator.get_scope(self.runtime_transaction_id).to_metadata()
                )
            except Exception:
                transaction_payload[self.runtime_transaction_id] = {"unavailable": True}
        snapshot = build_runtime_memory_snapshot(
            checkpoint_id=checkpoint_id,
            state=self.state_machine.to_dict(),
            transactions=transaction_payload,
            replay=dict(self.replay_artifact),
            recovery=dict(self.evidence.get("recovery") or {}),
            capabilities=self.capability_graph.to_dict(),
            intent=self.intent_evaluation.to_dict() if self.intent_evaluation else {},
            scheduler={"queue": [], "checkpoint_type": checkpoint_type},
        )
        self.memory_snapshots.append(snapshot)
        self.journal.append(
            "runtime_memory_snapshot",
            payload=snapshot.to_dict(),
            metadata={"phase": f"memory:{checkpoint_type}"},
        )
        self._record_abi("runtime_memory_snapshot", snapshot.to_dict())
        return snapshot

    def _seal_current_runtime(self, label: str) -> dict[str, Any]:
        payload = {
            "label": label,
            "runtime": runtime_version_descriptor().to_dict(),
            "state": self.state_machine.to_dict(),
            "journal": self.journal.reconstruct(),
            "transactions": self.transaction_coordinator.to_dict(),
            "memory_snapshot_count": len(self.memory_snapshots),
            "capability_graph": self.capability_graph.to_dict(),
            "intent_governance": self.intent_evaluation.to_dict() if self.intent_evaluation else {},
        }
        seal = self.artifact_gate.seal(
            payload,
            artifact_type="runtime_seal_snapshot",
            metadata={"phase": self.lifecycle[-1] if self.lifecycle else label},
        ).get("runtime_seal", {})
        self.runtime_seals.append(seal)
        self.journal.append(
            "runtime_seal_snapshot",
            payload=seal,
            metadata={"phase": f"seal:{label}"},
        )
        return seal

    def _enforce_integrity(self, label: str) -> None:
        journal_report = self.journal.verify_integrity()
        self.integrity_reports.append({**journal_report.to_dict(), "phase": label})
        journal_gate = self.artifact_gate.inspect(
            self.artifact_gate.seal(self.journal.reconstruct(), artifact_type="runtime_journal"),
            artifact_type="runtime_journal",
            abi_contract=None,
            mutation_id=self.session.session_id if self.session else "runtime-mutation",
        )
        if journal_gate.integrity is not None:
            self.integrity_reports.append({**journal_gate.integrity.to_dict(), "phase": label})
        decision = self.protection.enforce_integrity(
            (journal_report,),
            mutation_id=self.session.session_id if self.session else "runtime-mutation",
        )
        if decision.blocked:
            self.blocked = True
            self.failed = True
            self.journal.append(
                "runtime_protection_event",
                payload=decision.to_dict(),
                metadata={"phase": label},
            )
            raise RuntimeError(decision.reason)

    def _record_compatibility(self, payload: dict[str, Any], artifact_type: str) -> None:
        self.compatibility_reports.append(
            check_runtime_compatibility(payload, artifact_type=artifact_type).to_dict()
        )

    def _record_abi(self, contract_name: str, payload: dict[str, Any]) -> None:
        try:
            self.abi_reports.append(validate_abi(contract_name, payload).to_dict())
        except KeyError as exc:
            self.abi_reports.append(
                {
                    "contract_name": contract_name,
                    "version": runtime_version_descriptor().abi_version,
                    "valid": False,
                    "missing_fields": [],
                    "reason": str(exc),
                }
            )

    def _stage_available_mutation_paths(
        self,
        relative_paths: tuple[str, ...],
    ) -> RuntimeMutationSandbox:
        if self.isolation_boundary is None:
            raise ValueError("runtime_isolation_boundary_missing")
        sandbox = self.isolation_boundary.mutation_sandbox()
        available = tuple(
            path
            for path in relative_paths
            if (Path(self.request.sandbox_source_root) / path).exists()
        )
        if not available:
            return sandbox
        return sandbox.stage_paths(self.request.sandbox_source_root, available)

    def _emit_event(self, event, *, phase: str) -> None:
        self.journal.append_event(event, phase=phase)
        self.event_bus.publish_event(event)

    def _consume_budget(self, budget: str) -> None:
        try:
            self.governor = self.governor.consume(budget)
        except RuntimeBudgetExceeded as exc:
            event = BudgetExhaustedEvent(
                budget=exc.budget,
                snapshot=exc.snapshot,
                metadata={"phase": self.lifecycle[-1] if self.lifecycle else ""},
            )
            self._emit_event(event, phase="budget_exhausted")
            raise

    def _request_summary(self) -> dict[str, Any]:
        return {
            "intent": self.request.intent,
            "relative_paths": list(self.request.relative_paths),
            "dry_run": self.request.dry_run,
        }

    def _capture_transaction_snapshot(
        self,
        plan: MutationPatchPlan,
    ) -> dict[str, Any]:
        workspace = Path(self.request.workspace_root).resolve()
        snapshot_root = self._reports() / "transaction_snapshot"
        snapshot_root.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, Any]] = []
        for item in plan.items:
            relative_path = str(item.relative_path).replace("\\", "/")
            target = (workspace / relative_path).resolve()
            self._assert_inside(workspace, target)
            snapshot_target = (snapshot_root / relative_path).resolve()
            self._assert_inside(snapshot_root, snapshot_target)
            record = {
                "relative_path": relative_path,
                "existed": target.exists(),
                "snapshot_path": str(snapshot_target),
            }
            if target.exists():
                snapshot_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, snapshot_target)
            files.append(record)
        return {
            "snapshot_root": str(snapshot_root),
            "files": files,
            "complete": True,
        }

    def _rollback_from_transaction_snapshot(self) -> None:
        if self.state_machine.state != "ROLLING_BACK":
            self._transition("ROLLING_BACK", "transaction snapshot rollback")
        workspace = Path(self.request.workspace_root).resolve()
        restored: list[str] = []
        removed: list[str] = []
        for record in self.transaction_snapshot.get("files", []):
            if not isinstance(record, dict):
                continue
            relative_path = str(record.get("relative_path") or "")
            target = (workspace / relative_path).resolve()
            self._assert_inside(workspace, target)
            if record.get("existed"):
                snapshot_path = Path(str(record.get("snapshot_path") or "")).resolve()
                if snapshot_path.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(snapshot_path, target)
                    restored.append(relative_path)
            elif target.exists():
                target.unlink()
                removed.append(relative_path)
        self.rolled_back = True
        self.rollback_snapshot = {
            **self._build_rollback_snapshot(),
            "restored_paths": restored,
            "removed_new_paths": removed,
            "rolled_back_at": _utc_now(),
            "rollback_source": "transaction_snapshot",
        }
        self._checkpoint("rollback", {"rollback_snapshot": self.rollback_snapshot})

    def _require_session(self) -> MutationSession:
        if self.session is None:
            raise ValueError("governed_mutation_runtime_session_not_started")
        return self.session

    def _require_impacted_plan(self) -> ImpactedPlan:
        if self.impacted_plan is None:
            raise ValueError("governed_mutation_runtime_repo_scan_missing")
        return self.impacted_plan

    def _require_patch_plan(self) -> MutationPatchPlan:
        if self.patch_plan is None:
            raise ValueError("governed_mutation_runtime_plan_missing")
        return self.patch_plan

    def _assert_inside(self, root: Path, target: Path) -> None:
        try:
            target.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"rollback_path_escapes_root:{target}") from exc


def run_governed_mutation_runtime(
    request: MutationGatewayRequest,
) -> GovernedMutationRuntimeResult:
    return GovernedMutationRuntimeSession(request).run()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> dict[str, Any]:
    return json.loads(json.dumps(value, default=str))


__all__ = [
    "GovernedMutationRuntimeResult",
    "GovernedMutationRuntimeSession",
    "GovernedRuntimeTruth",
    "run_governed_mutation_runtime",
]
