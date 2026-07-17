# Runtime Execution Tick Audit

Runtime execution tick audit records are deterministic projections of tick validation and tick records.

Audit must include:

- execution tick id
- executor invocation id
- dispatch commit id
- dispatch id
- task admission id
- executor binding id
- tick status
- denial reason
- tick decision
- forbidden-surface locks

Audit confirms that tick records are record-only and single-cycle only.
