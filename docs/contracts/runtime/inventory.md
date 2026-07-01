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
