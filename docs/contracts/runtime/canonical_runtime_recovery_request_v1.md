# Canonical Runtime Recovery Request v1

Package 243 defines the first canonical request layer that flows into the Canonical Runtime Recovery Surface in future packages.

## Contract ID

`aer.runtime.recovery.canonical_request.v1`

## Scope

The request layer is disabled, plain-data, non-executing, and not wired into any runtime caller.

Package 243 does not wire requests into the Canonical Runtime Recovery Surface yet. It defines request data only. No existing runtime caller may import or call the request helper in this package.

This request layer is owned by the Canonical Surface family, but Packages 243 through 246 must not connect the request helper to the surface helper yet. Connection happens only after a future GO review.

## Relationship To Canonical Surface

The request is designed to flow into the Canonical Runtime Recovery Surface after a future GO review. It must remain compatible with the stable public Runtime Recovery surface introduced by Package 239.

The request layer does not replace, bypass, deprecate, or compete with the Canonical Runtime Recovery Surface. Future Runtime Recovery callers must remain compatible with the canonical surface.

The Canonical Runtime Recovery Request is part of the public compatibility boundary. The public request schema is append-only. Existing public fields must never be renamed or removed. Future packages may only add optional fields unless a major-version contract, such as `canonical_runtime_recovery_request_v2`, is introduced.

Exactly one canonical public request schema is allowed. Future packages must not introduce competing public Runtime Recovery request formats.

Future Runtime Recovery implementations, beginning with Package 247 and later, must consume this public request object instead of inventing additional request schemas.

The request object represents intent only. It is not an execution request.

## Required Fields

A valid canonical request must preserve:

- `schema: aer.runtime.recovery.canonical_request.v1`
- `request_id`
- `surface_id`
- `runtime_identity`
- `recovery_reason`
- `recovery_mode`
- `recovery_context`
- `disabled: true`
- `execution_allowed: false`
- `recovery_enabled: false`
- `runtime_state_mutated: false`
- `surface_wired: false`
- `owned_by_canonical_surface_family: true`
- `request_helper_connected_to_surface_helper: false`
- `surface_connection_requires_future_go_review: true`
- `canonical_surface_called: false`
- `public_compatibility_boundary: true`
- `append_only_public_schema: true`
- `existing_public_fields_renamable: false`
- `existing_public_fields_removable: false`
- `future_fields_must_be_optional: true`
- `major_version_required_for_breaking_schema_change: true`
- `exactly_one_canonical_request_schema: true`
- `competing_public_request_formats_allowed: false`
- `future_implementations_must_consume_this_request: true`
- `intent_only: true`
- `execution_request: false`
- `runtime_caller_modified: false`
- `plain_dict_only: true`

## Ownership

The canonical request layer owns only disabled request normalization and validation data. It does not own recovery policy, recovery planning, recovery scheduling, recovery execution, recovery supervision, recovery state machine, recovery persistence, recovery audit, recovery journaling, recovery hook registration, recovery binding, recovery endpoint invocation, or Canonical Runtime Recovery Surface wiring.

Those capabilities remain owned by their future dedicated packages.

## Boundary

The helper must normalize and validate request data only. It must return deterministic plain dictionaries only. It must not import runtime execution modules, decide recovery policy, schedule recovery, execute Recovery, execute recovery, invoke runtime, mutate runtime state, call the Canonical Runtime Recovery Surface, call canonical surface, call binding endpoint, call activation gate, register hooks, apply binding, invoke endpoints, persist, audit, journal, spawn subprocesses, touch filesystem mutation paths, call Scheduler, TaskRunner, Operator, Dispatcher, Supervisor, Native Runtime, Watchdog, or otherwise call Scheduler, TaskRunner, Operator, Dispatcher, Supervisor, Native Runtime, or Watchdog.

The helper must expose strict `__all__`.

The helper must expose exactly one public API: `prepare_canonical_runtime_recovery_request(...)`. Everything else must remain private. The module must not expose alternate request builders, legacy compatibility builders, convenience wrappers, or alias APIs.

Future packages must extend this API instead of creating additional public request entry points.
