# Runtime Recovery Controlled Activation Authorization Contract v1

## Purpose

Package 337 defines the Recovery Controlled Activation Authorization v1 contract.

Contract/specification only.

Schema name: `aer.runtime.recovery.controlled_activation_authorization.v1`.

This contract defines a disabled-by-default authorization shape and a deterministic default result for future controlled activation packages. Authorization is not activation, execution, scheduling, dispatch, gateway mutation, recovery execution, or runtime mutation.

## Required Authorization Fields

- `enabled`
- `authorization_status`
- `authorization_version`
- `authorization_allowed`
- `activation_allowed`
- `execution_allowed`
- `recovery_enabled`
- `runtime_state_mutated`
- `reason`
- `metadata`

## Default Authorization Values

- `enabled: false`
- `authorization_status: reserved`
- `authorization_version: v1_reserved`
- `authorization_allowed: false`
- `activation_allowed: false`
- `execution_allowed: false`
- `recovery_enabled: false`
- `runtime_state_mutated: false`
- `reason: future_package`
- `metadata: {}`

## Compatibility

The contract is compatible with Packages 329-336 decision outputs without importing or calling their runtime modules.

Future compatible changes may add optional fields only.

Breaking changes require a new contract version.

## Boundary

Authorization is not activation.

Authorization is not execution.

Authorization is not scheduling.

Authorization is not dispatch.

Authorization is not gateway mutation.

Authorization is not recovery execution.

Authorization is not runtime mutation.

Final decision: GO for contract-only disabled authorization surface. Next package: Package 338.
