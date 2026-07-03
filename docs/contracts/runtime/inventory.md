# AER Runtime Contract Inventory

## Purpose
Track runtime public surfaces, their dedicated contract specs, implementation modules, tests, and migration status.

## Status Vocabulary
- Complete: dedicated spec exists, implementation exists, focused tests exist.
- Missing Spec: implementation/tests exist but dedicated spec is missing.
- Missing Implementation: dedicated spec exists but implementation/tests are not complete.
- Not Started: no implementation/spec/test exists yet.
- Blocked: known architecture or contract issue blocks implementation.

## Inventory Table
| Runtime Surface | Contract Spec | Implementation | Tests | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| Bootstrap | bootstrap_v1.md | aer_runtime_bootstrap.py | test_aer_runtime_bootstrap.py | Missing Spec | existing layer needs dedicated spec |
| Context | context_v1.md | aer_runtime_context.py | test_aer_runtime_context.py | Missing Spec | existing layer needs dedicated spec |
| Projection | projection_v1.md | aer_runtime_projection.py | test_aer_runtime_projection.py | Missing Spec | existing layer needs dedicated spec |
| Session | session_v1.md | aer_runtime_session.py | test_aer_runtime_session.py | Missing Spec | existing layer needs dedicated spec |
| Activation | activation_v1.md | aer_runtime_activation.py | test_aer_runtime_activation.py | Missing Spec | existing layer needs dedicated spec |
| Lifecycle | lifecycle_v1.md | aer_runtime_lifecycle.py | test_aer_runtime_lifecycle.py | Missing Spec | existing layer needs dedicated spec |
| Checkpoint | checkpoint_v1.md | aer_runtime_checkpoint.py | test_aer_runtime_checkpoint.py | Missing Spec | existing layer needs dedicated spec |
| Recovery Marker | recovery_marker_v1.md | aer_runtime_recovery_marker.py | test_aer_runtime_recovery_marker.py | Missing Spec | existing layer needs dedicated spec |
| Resume Marker | resume_marker_v1.md | aer_runtime_resume_marker.py | test_aer_runtime_resume_marker.py | Missing Spec | existing layer needs dedicated spec |
| Resume Summary | resume_summary_v1.md | aer_runtime_resume_marker.py | test_aer_runtime_resume_marker.py | Complete | dedicated contract currently exists as docs/aer_runtime_resume_summary_contract.md; migration to docs/contracts/runtime/resume_summary_v1.md remains future work |
| Snapshot | docs/contracts/runtime/snapshot_v1.md | core/runtime/aer_runtime_snapshot.py | spec/adapter/validation/builder seal | Builder Implemented | pure deterministic builder/validator added; runtime mainline integration remains future work |
| Runtime Resume | docs/contracts/runtime/resume_v1.md | TBD | tests/test_aer_runtime_resume_contract.py | Missing Implementation | Package 126 contract/spec + seal only; implementation remains future work |
| Recovery | docs/contracts/runtime/recovery_v1.md | TBD | tests/test_aer_runtime_recovery_contract.py | Missing Implementation | Package 139 contract/spec + seal only; implementation remains future work |
| Runtime Recovery Execution | docs/contracts/runtime/recovery_execution_v1.md | TBD | tests/test_runtime_recovery_execution_contract.py | Missing Implementation | Package 257 contract/spec + seal only; implementation remains future work |
| Runtime Recovery Execution Plan | docs/contracts/runtime/recovery_execution_plan_v1.md | TBD | tests/test_runtime_recovery_execution_plan_contract.py | Missing Implementation | Package 258 contract/spec + seal only; implementation remains future work |
| Runtime Recovery Executor | docs/contracts/runtime/recovery_executor_v1.md | TBD | tests/test_runtime_recovery_executor_contract.py | Missing Implementation | Package 259 contract/spec + seal only; implementation remains future work |
| Runtime Recovery State Transition | docs/contracts/runtime/recovery_state_transition_v1.md | TBD | tests/test_runtime_recovery_state_transition_contract.py | Missing Implementation | Package 260 contract/spec + seal only; implementation remains future work |
| Runtime Recovery Checkpoint | docs/contracts/runtime/recovery_checkpoint_v1.md | TBD | tests/test_runtime_recovery_checkpoint_contract.py | Missing Implementation | Package 261 contract/spec + seal only; implementation remains future work |
| Runtime Recovery Rollback | docs/contracts/runtime/recovery_rollback_v1.md | TBD | tests/test_runtime_recovery_rollback_contract.py | Missing Implementation | Package 262 contract/spec + seal only; implementation remains future work |
| Runtime Recovery Retry | docs/contracts/runtime/recovery_retry_v1.md | TBD | tests/test_runtime_recovery_retry_contract.py | Missing Implementation | Package 263 contract/spec + seal only; implementation remains future work |
| Runtime Recovery Activation Request | docs/contracts/runtime/recovery_activation_request_v1.md | TBD | tests/test_recovery_runtime_activation_control_bundle.py | Missing Implementation | Package 281 contract/spec + seal only; implementation remains future work |
| Runtime Recovery Wiring Control | docs/contracts/runtime/recovery_wiring_control_v1.md | core/runtime/recovery_wiring_controller.py | tests/test_recovery_runtime_wiring_control_bundle.py | Stub Implemented | Packages 287-292 controlled wiring path remains disabled and non-mutating |
| Runtime Recovery Enablement | docs/contracts/runtime/recovery_enablement_v1.md | core/runtime/recovery_enablement_gate.py | tests/test_recovery_runtime_controlled_enablement_bundle.py | Stub Implemented | Packages 301-306 controlled enablement path remains disabled and non-mutating |
| Runtime Recovery Control Pipeline | docs/contracts/runtime/recovery_control_pipeline_v1.md | core/runtime/recovery_control_pipeline.py | tests/test_recovery_runtime_disabled_control_pipeline_bundle.py | Stub Implemented | Packages 307-312 disabled control pipeline remains data-only and non-mutating |
| Runtime Recovery Enablement Decision | docs/contracts/runtime/recovery_enablement_decision_v1.md | core/runtime/recovery_enablement_decision.py | tests/test_recovery_runtime_enablement_decision_bundle.py | Stub Implemented | Packages 313-320 enablement decision remains blocked, disabled, and non-mutating |
| Runtime Recovery Controlled Activation | docs/contracts/runtime/recovery_controlled_activation_v1.md | core/runtime/recovery_controlled_activation_gate.py | tests/test_recovery_runtime_controlled_activation_bundle.py | Stub Implemented | Packages 321-328 controlled activation skeleton remains disabled and non-mutating |
| Runtime Recovery Controlled Activation Decision | docs/contracts/runtime/recovery_controlled_activation_decision_v1.md | core/runtime/recovery_controlled_activation_decision_policy.py | tests/test_recovery_runtime_controlled_activation_decision_bundle.py | Stub Implemented | Packages 329-336 controlled activation decision remains disabled, data-only, and non-mutating |
| Runtime Recovery Controlled Activation Authorization | docs/contracts/runtime/recovery_controlled_activation_authorization_v1.md | core/runtime/recovery_controlled_activation_authorization_policy.py | tests/test_recovery_runtime_controlled_activation_authorization_bundle.py | Stub Implemented | Packages 337-344 controlled activation authorization remains disabled, data-only, and non-mutating |
| Runtime Recovery Controlled Activation Permit | docs/contracts/runtime/recovery_controlled_activation_permit_v1.md | core/runtime/recovery_controlled_activation_permit_policy.py | tests/test_recovery_runtime_controlled_activation_permit_bundle.py | Stub Implemented | Packages 345-352 controlled activation permit remains disabled, data-only, and non-mutating |
| Runtime Recovery Controlled Activation Grant | docs/contracts/runtime/recovery_controlled_activation_grant_v1.md | core/runtime/recovery_controlled_activation_grant_policy.py | tests/test_recovery_runtime_controlled_activation_grant_bundle.py | Stub Implemented | Packages 353-360 controlled activation grant remains disabled, data-only, and non-mutating |
| Runtime Recovery Controlled Activation Commit | docs/contracts/runtime/recovery_controlled_activation_commit_v1.md | core/runtime/recovery_controlled_activation_commit_policy.py | tests/test_recovery_runtime_controlled_activation_commit_bundle.py | Stub Implemented | Packages 361-368 controlled activation commit remains disabled, data-only, and non-mutating |
| Runtime Recovery Controlled Activation Apply | docs/contracts/runtime/recovery_controlled_activation_apply_v1.md | core/runtime/recovery_controlled_activation_apply_policy.py | tests/test_recovery_runtime_controlled_activation_apply_bundle.py | Stub Implemented | Packages 369-376 controlled activation apply remains disabled, data-only, and non-mutating |
| Runtime Recovery Controlled Activation Admission Preparation | docs/contracts/runtime/recovery_controlled_activation_admission_preparation_v1.md | core/runtime/recovery_controlled_activation_admission_preparation_policy.py | tests/test_recovery_runtime_controlled_activation_admission_preparation_bundle.py | Stub Implemented | Packages 385-392 admission preparation remains disabled, data-only, and non-mutating |
| Runtime Recovery Controlled Activation Admission Decision | docs/contracts/runtime/recovery_controlled_activation_admission_decision_v1.md | core/runtime/recovery_controlled_activation_admission_decision_policy.py | tests/test_recovery_runtime_controlled_activation_admission_decision_bundle.py | Stub Implemented | Packages 401-408 admission decision remains disabled, data-only, and non-mutating |
| Persistence | persistence_v1.md | TBD | TBD | Not Started | future layer |
| Replay | replay_v1.md | TBD | TBD | Not Started | future layer |
| Journal | journal_v1.md | TBD | TBD | Not Started | future layer |
| Audit | audit_v1.md | TBD | TBD | Not Started | future layer |

## Migration Priority
1. Move/normalize Resume Summary spec into docs/contracts/runtime/resume_summary_v1.md.
2. Add dedicated specs for existing completed layers from Bootstrap through Resume Marker.
3. Implement Snapshot only after Snapshot v1 spec alignment passes.
4. Add future Persistence / Replay / Journal / Audit specs before implementation.

## Inventory Rule
Inventory tracks contract governance only.
It must not define layer-specific vocabulary.
Layer-specific vocabulary belongs in dedicated contract specs.
