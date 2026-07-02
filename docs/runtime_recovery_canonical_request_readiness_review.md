# Runtime Recovery Canonical Request Readiness Review

## Package

Package 246: Canonical Runtime Recovery Request Readiness Review

## Scope

Packages 243 through 246 define the first canonical request layer that will flow into the Canonical Runtime Recovery Surface only after a future GO review.

This layer remains disabled, plain-data, non-executing, and not wired into any runtime caller.

## Review Findings

- Canonical request schema is `aer.runtime.recovery.canonical_request.v1`.
- The helper returns deterministic plain dict request data.
- Stable request fields include `schema`, `request_id`, `surface_id`, `runtime_identity`, `recovery_reason`, `recovery_mode`, `recovery_context`, `disabled`, `execution_allowed`, `recovery_enabled`, and `runtime_state_mutated`.
- The request layer is not wired into the Canonical Runtime Recovery Surface yet.
- This request layer is owned by the Canonical Surface family.
- Packages 243 through 246 do not connect the request helper to the surface helper yet.
- Connection happens only after a future GO review.
- The Canonical Runtime Recovery Request is part of the public compatibility boundary.
- The public request schema is append-only.
- Existing public fields must never be renamed or removed.
- Future packages may only add optional fields unless a major-version contract, such as `canonical_runtime_recovery_request_v2`, is introduced.
- Exactly one canonical public request schema is allowed.
- Future packages must not introduce competing public Runtime Recovery request formats.
- Future Runtime Recovery implementations, beginning with Package 247 and later, must consume this public request object instead of inventing additional request schemas.
- The request object represents intent only.
- It is not an execution request.
- The helper normalizes and validates request data only.
- The helper exposes exactly one public API: `prepare_canonical_runtime_recovery_request(...)`.
- Strict `__all__` exposes no additional request API.
- The module exposes no alternate request builders, legacy compatibility builders, convenience wrappers, or alias APIs.
- Future packages must extend this API instead of creating additional public request entry points.
- The helper does not decide recovery policy, schedule recovery, execute recovery, invoke runtime, mutate runtime state, call canonical surface, call binding endpoint, or call activation gate.
- Existing runtime callers are not modified.
- `core/runtime/runtime_supervisor_bridge.py` is not modified.
- Recovery is not executed.
- Recovery is not enabled.
- Hooks are not registered.
- Binding is not applied.
- Endpoints are not invoked.
- Runtime state is not mutated.
- Scheduler is not changed.
- TaskRunner is not changed.
- Operator is not changed.
- Dispatcher is not changed.
- Supervisor is not changed.
- Native Runtime is not changed.
- Watchdog is not changed.
- Persistence paths are not called.
- Audit paths are not called.
- Journal paths are not called.
- Subprocess paths are not called.
- Filesystem mutation paths are not called.
- Long validation is not run by Codex.
- Focused seal tests only.

## GO / NO-GO

Final decision: GO for the disabled canonical Runtime Recovery request layer.

NO-GO for wiring into the Canonical Runtime Recovery Surface, modifying runtime callers, Recovery execution, Recovery enablement, hook registration, binding application, endpoint invocation, runtime mutation, Scheduler, TaskRunner, Operator, Dispatcher, Supervisor, Native Runtime, Watchdog, persistence, audit, journal, subprocess, or filesystem mutation.

Next package: Package 247 may extend or verify the canonical request layer only if it preserves the Canonical Runtime Recovery Surface as the only public Runtime Recovery entry surface.

## Non-mainline Issues Found

- Existing historical Runtime Recovery modules include bridge, executor, scheduler adapter, operator adapter, supervisor adapter, native adapter, and integration filenames from earlier packages. Package 243 through 246 preserve those files and do not wire the new canonical request layer into them.
- Existing `docs/runtime_recovery_binding_endpoint_readiness_review.md` and `tests/test_runtime_recovery_binding_endpoint_readiness_review.py` use Package 210 wording while the main package sequence identifies that readiness review as Package 222. This package preserves that unrelated numbering drift and does not modify those files.
