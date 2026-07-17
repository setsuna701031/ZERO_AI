# Runtime Recovery Preflight Eligibility v1

## Package

Package 183: Runtime Recovery Preflight Eligibility Contract

## Contract ID

`zero.runtime.recovery.preflight_eligibility.v1`

## Purpose

This contract defines the non-executing preflight eligibility boundary that follows the observe-only Recovery layer. It answers whether the existing observation data is structurally ready for a later controlled non-executing binding phase. It does not allow Runtime binding, Recovery execution, event emission, state mutation, or mainline activation.

## Required Upstream Surface

The preflight eligibility layer consumes only the Package 177 observation report shape:

- `aer.runtime.recovery.observation_report.v1`
- prepared status only
- `runtime_recovery_single_entry` only
- canonical Recovery event preserved
- `event_emitted` remains `False`
- `recovery_enabled` remains `False`
- `executes_recovery` remains `False`
- `side_effects_performed` remains `False`

## Public Output Shape

A preflight eligibility report must expose a plain dict with these public meanings:

- `contract`: `aer.runtime.recovery.preflight_eligibility_report.v1`
- `prepared`, `blocked`, `denied`, `status`: passive three-state result
- `preflight_only`: always `True`
- `eligibility_checked`: true only for a valid prepared upstream observation
- `eligibility_level`: `non_executing_preflight`
- `single_entry_only`: always `True`
- `preflight_entry`: `runtime_recovery_single_entry` when valid
- `eligible_for_next_non_executing_phase`: true only for valid prepared preflight
- `eligible_for_runtime_binding`: always `False`
- `eligible_for_recovery_execution`: always `False`
- `runtime_binding_allowed`: always `False`
- `recovery_execution_allowed`: always `False`
- `event_emitted`: always `False`
- `recovery_enabled`: always `False`
- `runtime_surface_touched`: always `False`
- `canonical_event`: the Package 169 canonical event, preserved by value
- `observation_reference`: the validated upstream observation report, preserved by value
- `preflight_requirements`: explicit boolean checklist for non-executing readiness
- `denied_capabilities`: fixed denied capability list
- `reason`: passive block/deny reason
- `metadata`: caller metadata copied as plain data
- `preflight_report_only`: always `True`
- `executes_recovery`: always `False`
- `side_effects_performed`: always `False`
- `plain_dict_only`: always `True`

## Denied Capabilities

The preflight eligibility layer must deny:

- Recovery execution
- Recovery enablement
- Runtime mainline wiring
- Runtime binding
- Route activation
- Event emission
- Scheduler, Operator, Dispatcher, Supervisor, and Native Runtime calls
- Runtime mutation
- Persistence, replay, audit, journal, subprocess, and file IO

## Boundary Rules

This contract must not:

- execute Recovery
- enable Recovery by default
- perform Recovery actions
- bind Runtime
- emit Runtime events
- mutate Runtime state
- persist, replay, audit, journal, subprocess, or perform file IO
- call scheduler, operator, dispatcher, supervisor, or native runtime behavior
- create or call a Recovery executor
- inspect Runtime modules
- scan source files
- run broad validation

## Future Ownership

Future packages own any later controlled non-executing binding attempt. Runtime binding and Recovery execution remain explicitly out of scope for this package.
