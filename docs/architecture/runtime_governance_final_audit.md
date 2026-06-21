# Runtime Governance Final Audit

Schema: `zero.runtime_governance_final_audit.v1`

## Purpose

This final audit stops the runtime governance work from becoming an endless list
of independent closure names.  It treats the existing closure packages as one
runtime governance layer and verifies that every sealed piece is represented in a
single coverage matrix.

This audit is passive.  It does not grant authority, issue capability, mint
identity, assign ownership, mutate state, write evidence, persist data, resume
sessions, or repair records.

## Governance stack under audit

```text
Execution Capability Unification
  -> Authority Source Closure
  -> Capability Propagation Closure
  -> Identity Closure
  -> Ownership Closure
  -> Mutation Closure
  -> Evidence Closure
  -> Persistence Closure
  -> Governance Graph Closure
```

## Coverage matrix

| Closure target | Required document | Required test |
|---|---|---|
| Execution Capability Unification | `docs/architecture/runtime_execution_capability_unification.md` | `tests/test_runtime_execution_capability_unification_audit.py` |
| Authority Source Closure | `docs/architecture/runtime_authority_source_closure.md` | `tests/test_runtime_authority_source_closure.py` |
| Capability Propagation Closure | `docs/architecture/runtime_capability_propagation_closure.md` | `tests/test_runtime_capability_propagation_closure.py` |
| Identity Closure | `docs/architecture/runtime_identity_closure.md` | `tests/test_runtime_identity_closure.py` |
| Ownership Closure | `docs/architecture/runtime_ownership_closure.md` | `tests/test_runtime_ownership_closure.py` |
| Mutation Closure | `docs/architecture/runtime_mutation_closure.md` | `tests/test_runtime_mutation_closure.py` |
| Evidence Closure | `docs/architecture/runtime_evidence_closure.md` | `tests/test_runtime_evidence_closure.py` |
| Persistence Closure | `docs/architecture/runtime_persistence_closure.md` | `tests/test_runtime_persistence_closure.py` |
| Governance Graph Closure | `docs/architecture/runtime_governance_graph_closure.md` | `tests/test_runtime_governance_graph_closure.py` |

## Final audit invariants

1. Every closure in the governance stack has both documentation and a validation test.
2. Regression commands include every sealed closure test.
3. The coverage matrix has no duplicate target names.
4. The governance stack is evaluated as a single graph rather than as isolated green tests.
5. Missing non-mainline reporting sections are surfaced as findings.
6. Hidden bypass, fallback, wildcard, legacy, or parallel governance surfaces remain visible.
7. Final audit findings are reported without silently rewriting runtime behavior.

## Non-mainline findings

Mandatory reporting remains active.  The final audit must continue to surface:

- parallel governance graph
- hidden governance source
- legacy governance path
- cross-layer drift
- resume drift
- continuation drift
- replan drift
- authority bypass
- capability bypass
- identity bypass
- ownership bypass
- mutation bypass
- evidence bypass
- persistence bypass

Known watch item: `runtime_execution_capability_unification.md` predates the
later closure packages and may not carry the same explicit non-mainline section
style.  This should remain visible as an audit finding unless the document is
later normalized.  It is not a reason to treat the execution capability seal as
invalid.

No finding should be omitted just because the closure tests pass.

## Validation

```powershell
pytest -q tests/test_runtime_governance_final_audit.py
pytest -q tests/test_runtime_governance_graph_closure.py tests/test_runtime_mutation_closure.py tests/test_runtime_ownership_closure.py tests/test_runtime_persistence_closure.py tests/test_runtime_evidence_closure.py tests/test_runtime_identity_closure.py tests/test_runtime_capability_propagation_closure.py tests/test_runtime_authority_source_closure.py tests/test_runtime_execution_capability_unification_audit.py
python -m compileall core/runtime core/evidence core/goals core/tasks core/session core/adaptive tests
git diff --check
```
