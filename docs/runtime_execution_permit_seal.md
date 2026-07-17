# Runtime Execution Permit Seal

## Package
2113-2144

## Final Decision
GO_FOR_RUNTIME_EXECUTION_PERMIT_LAYER_ONLY

## Sealed Contract
Runtime Execution Permit v1 converts one admitted execution admission record into one deterministic execution permit metadata record.

## Sealed Lineage
- goal_id
- session_id
- queue_id
- worker_id
- cycle_id
- execution_request_id
- tick_id
- decision_id
- proposal_id
- authorization_id
- commit_id
- execution_admission_id

## Sealed Statuses
- permit_granted
- permit_denied

## Locked Default
execution_permitted=false

## Locked Meaning
permit_granted metadata does not execute.

## Locked Surfaces
- executor call
- scheduler dispatch
- subprocess
- filesystem mutation
- repo mutation
- cursor advance
- progress mutation

## Remaining Gap
A later package must provide a separately reviewed activation path before any permit metadata can become executable work.
