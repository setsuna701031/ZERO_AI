# AER Runtime Projection Constitution

## Core Principle

Every runtime layer owns its own public contract.

A runtime layer may consume the previous layer's public summary through the previous layer's validator and summary helper.

A runtime layer must not embed, expose, copy, or rename the previous layer's public object. The downstream public payload is not a wrapper, alias, view, or renamed carrier for the upstream object.

## Success Projection Rule

Success payloads must be projected into this layer's own vocabulary.

No previous-layer wrapper key may appear in downstream public payloads.

No previous-layer object graph may appear downstream.

No passthrough of previous public objects is allowed.

The downstream layer may map the upstream result into generic fields such as `source_valid` and `source_outcome`, but it must not carry the previous public object itself.

## Error Projection Rule

Failure payloads are also public contract.

Downstream layers must not copy upstream error text.

Upstream-specific names such as `runtime_checkpoint` and `runtime_recovery_marker` must not leak through downstream error payloads.

Downstream layers may report only generic source invalidity, for example `invalid upstream contract`.

Error projection must follow the same leak seal as success projection: no previous-layer wrapper key, object name, view name, or source-specific diagnostic vocabulary may become downstream public payload.

## Fixed Contract Rule

Public payload keys must be fixed per layer.

Extra fields added upstream must not appear downstream.

Downstream public contracts must remain stable when upstream internals evolve.

Downstream layers must validate their own fixed key set and reject unknown keys in their own payloads without using upstream payloads as passthrough dictionaries.

## Object Independence Rule

Downstream public payload must not share object references with upstream payload.

Mutating upstream objects after projection must not change downstream objects.

Mutating downstream objects or downstream summaries must not change upstream objects.

The projection boundary must be a value boundary, not a reference boundary.

## Allowed vs Forbidden

Allowed:

- importing upstream validators/helpers
- consuming upstream public summary
- mapping upstream result into generic `source_valid` and `source_outcome`
- reporting generic source invalidity such as `invalid upstream contract`

Forbidden:

- embedding `runtime_checkpoint` / `runtime_recovery_marker` objects in downstream public marker payloads
- recursive wrapper leaks
- renamed wrapper leaks
- copied upstream errors
- passthrough references
- downstream dependence on upstream internal keys
- no passthrough violations disguised as projection
- no recursive wrapper leak hidden inside nested public payloads

## Future Layer Requirement

All future AER Runtime public contracts must include tests for:

- no wrapper leak
- no recursive leak
- no error leak
- fixed keys
- no passthrough
- no shared object reference
- upstream extra-field independence
- deep mutation independence

This requirement applies to future Snapshot, Replay, Journal, Persistence, and Audit public contracts. Those layers may consume the immediately preceding public summary, but their public payloads must be projected into their own vocabulary and must not embed previous wrapper, view, object, or diagnostic surfaces.
