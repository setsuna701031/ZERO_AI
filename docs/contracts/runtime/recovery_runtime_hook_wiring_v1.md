# Runtime Recovery Hook Wiring Contract v1

## Purpose

Package 163 defines declarative Runtime Recovery hook wiring requirements for future Scheduler, Operator, Runtime Supervisor, and Native Runtime integration.

This contract is preparatory only. It does not activate Recovery, wire Recovery into runtime mainline, call Scheduler, call Operator, call Dispatcher, call Runtime Supervisor, call Native Runtime, mutate state, persist, replay, audit, journal, call subprocess, or perform file IO.

## Wiring Surfaces

Future wiring may consume only passive adapter reports:

| Surface | Required Contract | Runtime Permission |
| --- | --- | --- |
| Scheduler | `aer.runtime.recovery.scheduler_adapter_report.v1` | None |
| Operator | `aer.runtime.recovery.operator_adapter_report.v1` | None |
| Runtime Supervisor | `aer.runtime.recovery.supervisor_adapter_report.v1` | None |
| Native Runtime | `aer.runtime.recovery.native_adapter_report.v1` | None |

## Required References

Every future wiring contract must preserve:

- activation reference
- authority reference
- intent reference
- bridge reference
- executor report reference
- Scheduler passive adapter reference
- Operator passive adapter reference
- Runtime Supervisor passive adapter reference
- Native Runtime passive adapter reference

## Declarative Wiring Rules

Runtime hook wiring remains declarative until a future package explicitly changes the boundary.

Declarative wiring may:

- describe required adapter report inputs
- validate adapter report contracts
- validate preserved references
- report prepared, blocked, or denied readiness
- keep activation gate OFF by default

Declarative wiring must not:

- activate Recovery
- create Scheduler admissions
- request Operator actions
- dispatch commands
- supervise runtime sessions
- call Native Runtime execution
- mutate runtime state
- persist, replay, audit, journal, call subprocess, or perform file IO

## Package 159-162 Boundary Preservation

Package 159 Scheduler Passive Adapter remains adapter-only.

Package 160 Operator Passive Adapter remains adapter-only.

Package 161 Runtime Supervisor Passive Adapter remains adapter-only.

Package 162 Native Runtime Passive Adapter remains adapter-only.

No hook wiring contract may reinterpret a prepared adapter report as runtime execution permission.

## Gate Requirement

Future wiring must pass through a Recovery Wiring Gate before any controlled activation preparation can be considered.

The gate must be OFF by default.

A gate report may describe readiness, but it must not enable runtime behavior.

## Prohibited Runtime Hooks

Runtime Hook Wiring Contract v1 prohibits direct hooks to:

- Scheduler scheduling paths
- Operator runtime paths
- Dispatcher command paths
- Runtime Supervisor paths
- Native Runtime paths
- runtime mutation paths
- persistence write paths
- replay paths
- audit paths
- journal paths
- subprocess paths
- file IO paths

## Compatibility Policy

Runtime Hook Wiring Contract v1 is compatible only with passive Package 159 through Package 162 adapter reports that preserve `adapter_only: true`, `executes_recovery: false`, `side_effects_performed: false`, and `plain_dict_only: true`.

Breaking changes require a new contract version.

## GO / NO-GO

Final decision: GO.

Runtime Hook Wiring Contract v1 is complete as a contract-only package.

## Next Package

Next package: Package 164.
