# Runtime Task Dispatch Commit Audit

## Audit Scope

Runtime Task Dispatch Commit audit records preserve:

- dispatch commit request id
- dispatch id
- task admission id
- runtime session id
- execution lease id
- capability grant id
- executor binding id
- executor target metadata
- commit status
- denial reason
- forbidden surface locks
- non-mainline issue reporting requirement

## Audit Rule

Audit projections are deterministic and projection-only. They must not trigger executor execution or any external effect.

## Forbidden Evidence

Audit records must not include evidence of task execution, tool invocation, subprocess execution, network access, filesystem mutation, state mutation, task completion, autonomy loop startup, or background worker startup.
