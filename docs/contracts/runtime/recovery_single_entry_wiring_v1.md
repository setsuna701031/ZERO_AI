# Runtime Recovery Single Entry Wiring Contract v1

## Purpose

Package 167 defines the declarative single-entry wiring contract for future Runtime Recovery.

This contract is planning-only. It does not execute Recovery, enable Recovery by default, perform recovery actions, mutate runtime state, persist, replay, audit, journal, call subprocess, perform file IO, or call Scheduler, Operator, Dispatcher, Runtime Supervisor, or Native Runtime behavior.

## Single Entry Rule

Runtime Recovery may prepare only one future entry surface:

- `runtime_recovery_single_entry`

No package in this scope may wire multiple runtime surfaces.

## Required Upstream Boundary

Single-entry wiring may consume only `aer.runtime.recovery.controlled_activation_report.v1`.

The controlled activation report must preserve:

- activation gate OFF
- activation not allowed
- runtime mainline wiring not allowed
- preparation-only semantics
- no Recovery execution
- no side effects
- Scheduler, Operator, Runtime Supervisor, and Native Runtime passive adapter references

## Declarative Wiring Plan

Single-entry wiring may:

- describe the future single entry
- validate controlled activation preparation data
- require a kill switch before route preparation
- require canonical event schema before future route consumers
- report prepared, blocked, or denied readiness

Single-entry wiring must not:

- execute Recovery
- enable Recovery by default
- perform recovery actions
- create runtime work
- call runtime owners
- mutate runtime state
- persist, replay, audit, journal, call subprocess, or perform file IO

## Preserved Package Boundaries

Packages 155 through 166 remain passive and preparatory.

Package 163 through Package 166 gate OFF semantics remain intact.

Prepared controlled activation data is not permission to activate Recovery.

## Canonical Event Requirement

Future event route preparation must normalize route data into one canonical event schema before any later consumer sees it.

The canonical event must preserve:

- `source_surface`
- `entry_id`
- `route_id`
- `gate_state`

Different future sources must not invent separate event shapes.

## GO / NO-GO

Final decision: GO.

Runtime Recovery Single Entry Wiring Contract v1 is complete as a contract-only package.

## Next Package

Next package: Package 168.
