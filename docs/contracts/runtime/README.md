# AER Runtime Contract Specifications

## Purpose
This directory is the authoritative home for AER Runtime public contract specifications.

## Authority Order
Public contract questions must be resolved in this order:
1. Dedicated contract specification in docs/contracts/runtime/
2. Runtime implementation
3. Contract tests
4. Package sequence notes
5. Architecture constitution

## Required Contract Spec Sections
Every runtime contract spec should include:
- Purpose
- Inputs
- Outputs
- Fixed public keys
- Vocabulary
- Projection rules
- Error projection rules
- Forbidden leaks
- Object independence
- Compatibility
- Migration history

## Constitution Boundary
Architecture constitutions define cross-layer rules only.
They must not become API reference documents.
Layer-specific vocabulary belongs in dedicated contract specs.

## Future Runtime Contracts
Future runtime public contracts, including:
- bootstrap
- context
- projection
- session
- activation
- lifecycle
- checkpoint
- recovery marker
- resume marker
- resume summary
- snapshot
- persistence
- replay
- journal
- audit

must have dedicated contract specs before or alongside implementation.

## Contract File Naming
Use stable names such as:
- bootstrap_v1.md
- context_v1.md
- projection_v1.md
- session_v1.md
- activation_v1.md
- lifecycle_v1.md
- checkpoint_v1.md
- recovery_marker_v1.md
- resume_marker_v1.md
- resume_summary_v1.md
- snapshot_v1.md

## Compliance Rule
A runtime contract implementation and its tests must align with the dedicated contract spec.
If no dedicated contract spec exists, do not infer vocabulary from tests or implementation unless the package explicitly creates the missing spec.
