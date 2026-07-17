# Canonical Runtime Recovery Surface v1

Package 239 defines the first disabled Runtime implementation surface for Runtime Recovery.

## Contract ID

`aer.runtime.recovery.canonical_surface.v1`

## Canonical Surface

The exactly one canonical Runtime Recovery surface is `runtime_recovery_canonical_surface`.

Package 239 must not create multiple Runtime Recovery entry points. All future Runtime Recovery execution, when eventually enabled by later packages, must flow through this single canonical surface. Future packages may extend or verify this surface, but must not introduce competing Runtime entry paths.

The Canonical Runtime Recovery Surface introduced in Package 239 is the ONLY public Runtime Recovery entry surface. All future Runtime Recovery implementations, beginning with Packages 243 and later, must enter through this surface. No future package may expose another public Runtime Recovery entry API.

Bridge modules, adapters, supervisors, schedulers, operators, dispatchers, watchdogs, and native runtime components may only connect to this canonical surface in future packages after the required GO reviews.

## Ownership

This package owns only the public Runtime Recovery interface as a disabled plain-data Runtime implementation surface. It does not wire the surface into existing runtime flow, and no existing runtime module may import or call it in this package.

Package 239 does not own Runtime hook registration, Runtime binding application, endpoint invocation, scheduler behavior, task runner behavior, operator behavior, dispatcher behavior, supervisor behavior, native runtime behavior, watchdog behavior, event emission, persistence, replay, audit, journal, subprocess, filesystem mutation, or Recovery execution.

The Canonical Runtime Recovery Surface does NOT own:

- recovery policy
- recovery planning
- recovery scheduling
- recovery execution
- recovery supervision
- recovery state machine
- recovery persistence
- recovery audit
- recovery journaling
- recovery hook registration
- recovery binding
- recovery endpoint invocation

Those capabilities remain owned by their future dedicated packages.

The canonical surface may only validate, normalize, and forward canonical Runtime Recovery requests after future GO approval.

The Canonical Runtime Recovery Surface is a stable compatibility boundary. Future packages may extend its internal implementation, but must preserve its public API and ownership boundary. Backward compatibility of the public Runtime Recovery surface must be maintained unless an explicit major-version contract, such as `canonical_runtime_recovery_surface_v2`, is introduced.

No future package may silently replace, bypass, or deprecate this canonical surface. All Runtime Recovery callers must remain compatible with it.

## Required Safety Fields

A valid canonical surface report must preserve:

- `surface_name: runtime_recovery_canonical_surface`
- `canonical_surface: true`
- `single_canonical_surface: true`
- `only_public_runtime_recovery_entry_surface: true`
- `public_entry_api: prepare_canonical_runtime_recovery_surface`
- `competing_public_runtime_recovery_surfaces: []`
- `competing_entry_points_allowed: false`
- `future_recovery_entry_must_flow_through_surface: true`
- `future_packages_must_enter_through_surface: true`
- `future_public_entry_api_allowed: false`
- `future_connectors_require_go_review: true`
- `owns_public_runtime_recovery_interface_only: true`
- `owns_recovery_policy: false`
- `owns_recovery_planning: false`
- `owns_recovery_scheduling: false`
- `owns_recovery_execution: false`
- `owns_recovery_supervision: false`
- `owns_recovery_state_machine: false`
- `owns_recovery_persistence: false`
- `owns_recovery_audit: false`
- `owns_recovery_journaling: false`
- `owns_recovery_hook_registration: false`
- `owns_recovery_binding: false`
- `owns_recovery_endpoint_invocation: false`
- `may_validate_normalize_forward_after_go: true`
- `stable_compatibility_boundary: true`
- `public_api_stable: true`
- `ownership_boundary_stable: true`
- `requires_major_version_for_breaking_public_api: true`
- `silent_replacement_allowed: false`
- `bypass_allowed: false`
- `silent_deprecation_allowed: false`
- `all_callers_must_remain_compatible: true`
- `surface_enabled: false`
- `runtime_wiring_enabled: false`
- `runtime_hook_registered: false`
- `runtime_binding_applied: false`
- `endpoint_invoked: false`
- `event_emitted: false`
- `recovery_enabled: false`
- `executes_recovery: false`
- `runtime_state_mutated: false`
- `side_effects_performed: false`
- `plain_dict_only: true`

## Statuses

Allowed statuses are `prepared`, `blocked`, and `denied`.

`prepared` means the canonical surface is described as disabled plain data only. It does not mean Recovery can run.

`blocked` means the requested canonical surface name or requested status is incompatible.

`denied` means an activation, execution, hook registration, binding application, endpoint invocation, event emission, runtime mutation, persistence, audit, journal, subprocess, or filesystem mutation attempt was requested and denied as data only.

## Boundary

The helper must return deterministic plain dictionaries only. It must not register hooks, apply runtime binding, invoke endpoints, emit events, mutate runtime state, persist, audit, journal, spawn subprocesses, touch filesystem mutation paths, call Scheduler, TaskRunner, Operator, Dispatcher, Supervisor, Native Runtime, Watchdog, or execute Recovery.

The helper must expose strict `__all__`.

The helper must expose exactly one public entry API: `prepare_canonical_runtime_recovery_surface`.
