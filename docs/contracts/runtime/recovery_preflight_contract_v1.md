# Recovery Preflight Eligibility v1

Package 183 defines passive Recovery preflight eligibility.

The preflight layer consumes an observe-only Package 177 observation report and
returns eligibility data only. It does not bind runtime, emit an event, mutate
state, or execute Recovery.

Required safety fields:
- `preflight_only: True`
- `eligible` derived from valid observe-only upstream data
- `runtime_binding_allowed: False`
- `runtime_mainline_wiring_allowed: False`
- `event_emitted: False`
- `recovery_enabled: False`
- `executes_recovery: False`
- `side_effects_performed: False`
- `plain_dict_only: True`

GO / NO-GO: GO when the contract and helper tests pass.
