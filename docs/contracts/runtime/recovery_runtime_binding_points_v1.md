# Recovery Runtime Binding Points v1

Package 201 defines an inert binding-points report for Runtime Recovery.

The report describes declared binding points as data. It must not register runtime hooks, inspect runtime modules, apply runtime bindings, or emit events.

## Contract ID

`aer.runtime.recovery.runtime_binding_points_report.v1`

## Required Binding Point

Only this binding point may appear in v1:

- `runtime_recovery_single_entry`

## Required Safety Flags

- `binding_points_declared` may be true only for valid disabled binding input
- `binding_points_registered` must be false
- `runtime_hook_registered` must be false
- `runtime_binding_applied` must be false
- `runtime_surface_touched` must be false
- `binding_enabled` must be false
- `recovery_enabled` must be false
- `event_emitted` must be false
- `executes_recovery` must be false
- `side_effects_performed` must be false
- `plain_dict_only` must be true

## Future Ownership

Future packages own controlled runtime wiring. This package owns only disabled binding point declaration.
