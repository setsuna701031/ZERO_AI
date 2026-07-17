# Recovery Binding Validator v1

Package 192 defines passive validation for Runtime Recovery binding candidates.

## Scope

The validator checks that a candidate preserves the single-entry, policy, preflight, registry, framework, and no-side-effect boundaries. It produces a deterministic report only.

## Public Contract

- contract: `aer.runtime.recovery.binding_validator_report.v1`
- candidate_valid: `True` only for compatible prepared candidates
- policy_validated: `True` only for compatible prepared candidates
- preflight_validated: `True` only for compatible prepared candidates
- registry_validated: `True` only for compatible prepared candidates
- framework_validated: `True` only for compatible prepared candidates
- binding_application_allowed: `False`
- binding_registered: `False`
- runtime_bound: `False`
- runtime_mainline_wiring_enabled: `False`
- event_emitted: `False`
- recovery_enabled: `False`

## Boundary Rules

Validation must not bind runtime, execute Recovery, emit events, mutate state, persist, replay, audit, journal, spawn subprocesses, perform file IO, or call runtime behavior.
