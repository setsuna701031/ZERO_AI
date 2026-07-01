# Recovery Binding Registry v1

## Package 188

Package 188 defines the passive Recovery binding registry report. The registry declares the one future binding entry but does not register anything with runtime.

## Contract ID

`aer.runtime.recovery.binding_registry.v1`

## Public Helper

`prepare_recovery_binding_registry_report(...)`

## Required Output Semantics

- `binding_registry_only` is `True`.
- `registry_entry` is `runtime_recovery_single_entry` for valid prepared reports.
- `runtime_binding_registered` is `False`.
- `runtime_binding_active` is `False`.
- `runtime_mainline_wiring_allowed` is `False`.
- `event_emitted` is `False`.
- `recovery_enabled` is `False`.
- `executes_recovery` is `False`.
- `side_effects_performed` is `False`.
- `plain_dict_only` is `True`.

## Forbidden Behavior

The helper must not call scheduler, operator, dispatcher, supervisor, native runtime, persistence, replay, audit, journal, subprocess, or filesystem surfaces.
