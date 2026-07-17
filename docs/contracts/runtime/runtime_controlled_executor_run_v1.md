# Runtime Controlled Executor Run Bundle v1

## Purpose

Defines the controlled path from executor activation readiness into a run-handler result record.

## Inputs

- Runtime Executor Activation record
- Optional injected run handler

## Outputs

- RuntimeControlledRunAdmissionRecord
- RuntimeControlledRunBridgeRecord
- RuntimeControlledRunResultIntakeRecord

## Rules

- Admission requires authorized upstream activation.
- Bridge may call only an injected run handler.
- Handler payload is data-only.
- Result intake accepts result data only.
- No scheduler loop is started here.
- No progress memory, cursor, or runtime state mutation occurs here.

## Ownership

Controlled run admission authorizes readiness to call the injected run handler.
Controlled run bridge carries the request and receives result data.
Result intake validates that a result exists and remains data-only.
