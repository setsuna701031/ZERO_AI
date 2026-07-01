# AER Documentation Architecture

## Purpose
Define the documentation governance model for AER Runtime and ZERO work packages.

## Documentation Layers
Define these layers and responsibilities:

### Constitution
Owns cross-cutting architecture and engineering rules.
Must not define layer-specific API vocabulary.

### Contract Specification
Owns one public contract surface.
Defines fixed keys, vocabulary, examples, error projection, compatibility, and migration notes.

### Inventory
Tracks current status of contract specs, implementations, tests, and gaps.
Must not define vocabulary or roadmap.

### Package Sequence
Records historical package evolution and decisions.
Must not be the primary authority for contract vocabulary.

### Template
Defines reusable work package structure.
Must not define runtime contract vocabulary.

### Roadmap
Defines future planning and priority.
Must not define current contract authority.

## Authority Flow
Public contract questions must be resolved by:
1. Dedicated contract specification
2. Runtime implementation
3. Contract tests
4. Package sequence
5. Constitution

Architecture rule questions must be resolved by:
1. Runtime architecture constitution
2. ZERO work package constitution
3. Documentation architecture
4. Package sequence

## Lifecycle
A new runtime public surface should evolve in this order:
1. Architecture rule check
2. Contract specification
3. Contract test
4. Runtime implementation
5. Integration consumers
6. Inventory update
7. Package sequence record

## Single Responsibility Rule
Each documentation artifact must have one primary responsibility.
Do not use Constitution as API reference.
Do not use Inventory as roadmap.
Do not use Package Sequence as contract specification.
Do not use Template as architecture authority.

## Runtime Contract Governance
Runtime public surfaces must have dedicated contract specs before or alongside implementation.
If no spec exists, the package must either create the missing spec or stop and report ambiguity.

## Migration Rule
Existing runtime surfaces may be marked Missing Spec in inventory.
Migration packages should add dedicated specs without changing runtime behavior unless explicitly scoped.

## Completion Criteria
A documentation architecture package is complete only when:
- architecture document exists
- seal test exists
- package sequence records the architecture package
- no runtime behavior changes were made
