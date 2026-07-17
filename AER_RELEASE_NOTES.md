# AER Core v1.0.0-rc1 Release Notes

## Status

AER Core v1 is a Release Candidate.

Engineering blockers: 0

## Validated Baseline

Fast regression:

```text
370 passed
5377 deselected
73 subtests passed
```

## Frozen Surfaces

- Scheduler.run_one_step
- Scheduler runtime bindings
- Runtime boundary
- Authority context contract
- Runtime identity contract
- Runtime session contract
- Runtime execution contract
- Runtime boundary contract

## Completed Evidence

- scheduler_mainline_inventory.txt
- scheduler_mainline_callgraph.txt
- scheduler_review_inventory.txt
- scheduler_freeze_readiness_report.txt
- taskrunner_boundary_inventory.txt
- runtime_boundary_matrix.txt
- runtime_boundary_consistency_audit.txt
- runtime_boundary_manual_review.txt
- aer_runtime_freeze_evidence_pack.txt
- aer_freeze_candidate_seal.txt
- runtime_contract_constant_dedup.txt

## Contract Layer

Runtime contracts have been established and covered by unit tests:

- authority_context_contract.py
- runtime_identity_contract.py
- runtime_session_contract.py
- runtime_execution_contract.py
- runtime_boundary_contract.py

Contract tests:

```text
tests/test_runtime_contracts.py
17 passed
```

## Known Non-Blocking Follow-up

Contract constant dedup migration is post-freeze maintenance and is not an AER Core v1 RC blocker.

## Freeze Rules

- Do not modify Scheduler.run_one_step.
- Do not collapse runtime wrappers without a dedicated behavior audit.
- Do not treat dedup candidates as freeze blockers.
- If future work finds issues outside the current scope, report them explicitly instead of silently skipping them.
