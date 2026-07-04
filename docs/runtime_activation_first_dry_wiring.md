# Runtime Activation First Dry Wiring

This document records the first dry runtime activation preflight wiring.

This is first dry wiring only. It is deterministic, data-only, and blocked by default.

## Guardrails

- first dry wiring only
- no real activation
- no scheduler dispatch
- no executor call
- no mutation
- dry wiring is blocked by default
- activation remains disabled
- no runtime state mutation
- no repo or file mutation
- no execution path

## Allowed Flow

runtime activation dry request
  -> adapter contract check
  -> adapter admission check
  -> adapter authorization check
  -> adapter lifecycle check
  -> adapter dry-run result

## Forbidden Flow

dry-run result
  -> scheduler dispatch forbidden
  -> executor forbidden
  -> mutation forbidden

## Implementation Boundary

The dry wiring entrypoint returns a plain dict. It accepts None, dict, and malformed non-dict requests safely. It never raises for malformed requests, never performs IO, never calls scheduler, never calls executor, never writes state, and never mutates the input request.

The result is blocked because activation remains disabled.

## Final State

ZERO has first dry runtime activation preflight wiring, but activation, scheduler dispatch, executor execution, and mutation remain disabled.
