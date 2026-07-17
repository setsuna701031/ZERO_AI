# Controlled Active Limited Mode Candidate v1 Contract

Package range: 1137-1144.

Status: disabled / candidate-only / preview-only.

## Purpose

This contract reserves the first limited controlled-active runtime mode candidate.

It describes what a safe limited active mode would look like without actually switching runtime mode or enabling real effects.

## Candidate capabilities in preview

- limited scheduler loop may be represented
- internal execution may be represented
- state transition may be represented

## Mandatory locked capabilities

- real file mutation remains locked
- runtime mutation remains locked
- external tool execution remains locked
- network IO remains locked
- unbounded autonomy remains locked
- self-start remains locked

## Mandatory disabled outputs

Every candidate result must keep:

- `enabled: false`
- `candidate_only: true`
- `preview_only: true`
- `controlled_active_limited_allowed: false`
- `runtime_mode_transition_performed: false`
- `controlled_active_enabled: false`
- `real_file_mutation_performed: false`
- `runtime_mutation_performed: false`
- `external_tool_invoked: false`
- `network_io_performed: false`
- `unbounded_autonomy_started: false`
- `self_start_performed: false`

## Non-mainline issue reporting rule

Any issue discovered outside this package scope must be reported explicitly and must not be silently skipped, hidden, or bypassed.
