# Evidence Authority Matrix v1

## Purpose

This audit seals the Evidence authority boundary for AER foundation work.
It verifies that evidence collection, validation, persistence, aggregation,
decision-evidence projection, and goal-completion checks remain separated.

## Authority owners

| Concern | Owner | Allowed | Forbidden |
|---|---|---|---|
| Collect pending evidence | `EvidenceCollector` | Build pending `EvidenceRecord` from `EvidenceContract` | Validate, persist, complete goals, mutate runtime |
| Validate evidence | `EvidenceValidator` | Return validated/rejected `EvidenceRecord` | Persist, complete goals, mutate runtime |
| Persist evidence | `EvidenceRepository` | Append/query JSONL evidence records, build read-only chains | Validate, decide completion, mutate goals |
| Aggregate evidence | `EvidenceAuthority` | Register evidence through repository, expose evidence chains/summaries | Execute runtime, decide goals, write memory |
| Decision evidence | `DecisionEvidenceRepository` | Compatibility projection through `EvidenceAuthority` | Independent persistence authority |
| Evidence chain | `EvidenceChain` | Read-only summary/counts | Persist, validate, complete goals |

## Completion rule

Goal completion must depend on validated evidence. No evidence component should
silently mutate goal state or bypass `EvidenceValidator` / `EvidenceAuthority`.

## Non-mainline note

Runtime evidence and historical decision-evidence paths should remain under audit
for bypasses. Compatibility shims are allowed only when writes route through
`EvidenceAuthority` into `EvidenceRepository`.
