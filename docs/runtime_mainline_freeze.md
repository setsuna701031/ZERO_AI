# Runtime Mainline Freeze / L4 Seal

Date: 2026-05-20

This note records the current runtime mainline freeze boundary. It is a contract note, not an architecture rewrite: scheduler slimming, boot cleanup, public facade redesign, and UI/demo work remain outside this seal.

## Sealed Runtime Boundaries

- Canonical execution authority is owned by `core.runtime.executor`.
- Governed execution must produce a sealed runtime evidence record and canonical audit metadata.
- Side-effect records must preserve runtime evidence and audit metadata.
- Mutation and repair results must preserve evidence id, audit id, mutation transaction id, and mutation request lineage.
- Recovery verification must reject missing governed evidence, audit, authority, execution session, replay session, mutation, repair, or raw-execution guard lineage.
- Replay, continuation, and cross-session handoff must preserve source session and replay session lineage.
- Facade execution paths must return governed metadata instead of flattening or dropping it.
- Scheduler remains a compatibility and dispatch surface, not a new execution authority owner.
- `system_boot.py` remains bootstrap wiring for component construction and evidence adapter setup, not a runtime governance execution owner.

## Stable Surfaces

- `Executor.execute_request` as canonical governed command/subprocess execution.
- `safe_subprocess_run` as the compatibility facade that delegates to the canonical executor.
- Runtime evidence and audit records as required metadata on governed execution, repair, mutation, and recovery outputs.
- Governed execution, replay, continuation, and handoff session contracts.
- Repair transaction execution through governed mutation topology.
- Recovery coordinator verification only when governed lineage is present.

## Allowed Future Extension Surfaces

- Additive contract tests and documentation that clarify sealed behavior.
- New capability packs that call existing governed facades rather than bypassing them.
- New public wrappers that delegate to sealed runtime owners and preserve metadata.
- Read-only reporting over evidence, audit, replay, timeline, and handoff records.
- Scheduler compatibility adapters that route into existing governed execution surfaces.

## Deferred Work

- Scheduler slimming and private helper consolidation.
- `system_boot.py` cleanup or facade extraction.
- Capability pack packaging and external extension ergonomics.
- UI, demo, and presentation layers.
- Public recovery, rollback, and evidence service API shape beyond the sealed internal contracts.

## Forbidden Future Regressions

- Raw subprocess or shell execution outside the canonical runtime executor.
- Orphan evidence, missing evidence id, or audit metadata that cannot be tied back to runtime evidence.
- Mutation or repair results that drop evidence or audit lineage.
- Recovery verify without governed lineage.
- Replay, continuation, or handoff records without session lineage.
- Facade results that drop governed metadata.
- scheduler owning execution authority or directly claiming evidence, recovery, mutation, or governed action ownership.
- system_boot.py remains bootstrap wiring; it must not accumulate runtime governance execution logic.
