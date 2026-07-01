# AER Runtime Snapshot Contract v1

## Purpose
Define `aer.runtime.snapshot.v1` as the public contract boundary after Resume Summary and before future Persistence, Replay, Journal, and Audit layers.

Snapshot is a contract boundary, not persistence. Snapshot does not perform IO, storage, replay, recovery, scheduling, runtime execution, or operator loop behavior.

Snapshot consumes the Resume Summary public contract and outputs only its own Snapshot v1 public contract.

## Inputs
Snapshot v1 consumes Resume Summary public fields only:

- `valid`
- `outcome`
- `status`
- `reason`
- `contract`

The Snapshot contract may map those fields into generic `source_*` fields. It must not consume Resume Marker implementation details or any wrapper object.

## Outputs
Snapshot v1 outputs a single public payload with fixed keys.

The output contract name is:

`aer.runtime.snapshot.v1`

## Fixed public keys
Snapshot v1 public payloads contain exactly these keys:

- `contract`
- `snapshot_id`
- `source_valid`
- `source_outcome`
- `source_status`
- `valid`
- `status`
- `outcome`
- `reason`
- `metadata`

## Vocabulary
- `contract`: always `aer.runtime.snapshot.v1`.
- `snapshot_id`: stable Snapshot identifier assigned by the Snapshot contract layer.
- `source_valid`: projected Resume Summary validity.
- `source_outcome`: projected Resume Summary outcome.
- `source_status`: projected Resume Summary status.
- `valid`: Snapshot structural validity.
- `status`: Snapshot structural status, such as `valid` or `invalid`.
- `outcome`: Snapshot runtime-visible result.
- `reason`: generic Snapshot reason, or `None` for valid snapshots.
- `metadata`: Snapshot-owned metadata only.

The `source_*` fields may only come from Resume Summary projected public fields. They must not expose upstream implementation objects, wrapper keys, or internal diagnostics.

## Valid snapshot example
```json
{
  "contract": "aer.runtime.snapshot.v1",
  "snapshot_id": "snapshot-001",
  "source_valid": true,
  "source_outcome": "continue",
  "source_status": "valid",
  "valid": true,
  "status": "valid",
  "outcome": "continue",
  "reason": null,
  "metadata": {}
}
```

## Invalid upstream example
```json
{
  "contract": "aer.runtime.snapshot.v1",
  "snapshot_id": "snapshot-001",
  "source_valid": false,
  "source_outcome": "continue",
  "source_status": "invalid",
  "valid": false,
  "status": "invalid",
  "outcome": "continue",
  "reason": "invalid upstream contract",
  "metadata": {}
}
```

## Error projection rule
Invalid upstream Resume Summary payloads must be reported with generic Snapshot-owned error vocabulary.

Snapshot v1 uses the generic reason:

`invalid upstream contract`

Snapshot v1 must not copy upstream error text, internal reason strings, wrapper names, or implementation diagnostics.

## Resume Summary Adapter Contract
The Resume Summary Adapter Contract defines the contract boundary for mapping Resume Summary public fields into the Snapshot v1 public schema.

This is a contract-only adapter boundary. It does not define or imply a runtime Snapshot implementation.

Input schema name:

`aer.runtime.resume_summary.v1`

Output schema name:

`aer.runtime.snapshot.v1`

Allowed input fields:

- `contract`
- `valid`
- `outcome`
- `status`
- `reason`

Field-level mapping table:

| Resume Summary field | Snapshot field | Required / Optional | Classification | Mapping rule | Default behavior | Invalid-input behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `contract` | `contract` | Required | constant | Output contract is always `aer.runtime.snapshot.v1`; input contract must identify `aer.runtime.resume_summary.v1`. | `aer.runtime.snapshot.v1` | Output remains `aer.runtime.snapshot.v1`; mark Snapshot invalid. |
| `contract`, `valid`, `outcome`, `status`, `reason` | `snapshot_id` | Required | derived | Snapshot-owned identity derived deterministically from the canonical allowed input field projection. | Deterministic Snapshot-owned identity for the canonical input projection. | Deterministic Snapshot-owned identity for the canonical invalid-input projection. |
| `valid` | `source_valid` | Required | copied directly | Copy the Resume Summary `valid` value as source lineage. | No default for valid input; missing field is invalid input. | Use generic invalid upstream projection; do not copy unknown diagnostics. |
| `outcome` | `source_outcome` | Required | copied directly | Copy the Resume Summary `outcome` value as source lineage. | No default for valid input; missing field is invalid input. | Use generic invalid upstream projection; do not copy unknown diagnostics. |
| `status` | `source_status` | Required | copied directly | Copy the Resume Summary `status` value as source lineage. | No default for valid input; missing field is invalid input. | Use generic invalid upstream projection; do not copy unknown diagnostics. |
| `valid`, `contract`, `outcome`, `status`, `reason` | `valid` | Required | derived | Snapshot structural validity is true only when the allowed Resume Summary input is complete and valid. | `true` for valid input. | `false`. |
| `valid`, `contract`, `outcome`, `status`, `reason` | `status` | Required | derived | Snapshot structural status is `valid` for valid input and `invalid` for missing-field or invalid input. | `valid` for valid input. | `invalid`. |
| `outcome` | `outcome` | Required | copied directly | Copy the Resume Summary runtime-visible `outcome` for valid input. | No default for valid input; missing field is invalid input. | Use generic invalid upstream projection; do not copy unknown diagnostics. |
| `reason`, structural validation result | `reason` | Required | derived | Use `None` for valid input; use generic Snapshot-owned reason for invalid upstream input. | `None`. | `invalid upstream contract`. |
| none | `metadata` | Required | constant | Snapshot-owned metadata only; adapter contract default is an empty object. | `{}` | `{}`; must not hold upstream references. |
| any unlisted input field | any unlisted Snapshot field | Prohibited | prohibited | Unknown input fields must not be mapped, renamed, embedded, or passed through. | Not emitted. | Not emitted. |

Every Snapshot v1 field is defined by this table. There are no undefined Snapshot fields.

Future implementations of this adapter are required to be fully deterministic: the same Resume Summary input shall always produce the identical Snapshot payload.

Required identity fields:

- input `contract` must be `aer.runtime.resume_summary.v1`
- output `contract` must be `aer.runtime.snapshot.v1`
- output `snapshot_id` must be Snapshot-owned identity

Required lineage fields:

- output `source_valid` maps from input `valid`
- output `source_outcome` maps from input `outcome`
- output `source_status` maps from input `status`

Status vocabulary mapping rules:

- input `status` is treated as Resume Summary structural status only
- output `source_status` preserves the allowed input `status` value as lineage
- output `status` is Snapshot structural status only
- valid input maps to output `status` value `valid`
- missing required fields or invalid input maps to output `status` value `invalid`
- invalid upstream input maps to generic Snapshot-owned reason `invalid upstream contract`
- Snapshot must not copy upstream error text from input `reason`

Forbidden fields:

- `runtime_resume_marker`
- `resume_marker`
- `runtime_snapshot`
- `snapshot`
- `checkpoint`
- `persistence`
- `storage`
- `io`
- `replay`
- `recovery`
- `journal`
- `audit`
- `scheduler`
- `operator`
- `runtime_execution`
- any upstream wrapper object
- any unknown input field passed through into output

Missing-field behavior:

- missing input `contract`, `valid`, `outcome`, `status`, or `reason` is invalid input
- missing-field failures must produce a Snapshot-owned invalid result
- missing-field failures must use generic reason `invalid upstream contract`
- missing-field failures must not name missing upstream internals or leak diagnostics

Invalid-input behavior:

- non-dict input is invalid input
- input with a `contract` value other than `aer.runtime.resume_summary.v1` is invalid input
- invalid input must produce a Snapshot-owned invalid result
- invalid input must use generic reason `invalid upstream contract`
- invalid input must not copy upstream error text, wrapper names, diagnostics, or unknown fields

No side effects rule:

- the adapter contract is pure projection only
- the adapter must not perform IO, storage, replay, recovery, persistence, journal, audit, scheduling, operator loop behavior, or runtime execution
- the adapter must not read files, write files, open network connections, mutate external state, or persist Snapshot payloads

## Snapshot Validation Contract
The Snapshot Validation Contract defines what makes an `aer.runtime.snapshot.v1` payload valid or invalid before any Snapshot implementation exists.

This is a documentation-only validation contract. It does not define or imply a Snapshot builder, validator implementation, persistence layer, replay layer, recovery layer, audit layer, journal layer, scheduler integration, operator loop, or runtime execution behavior.

Structural validation:

- a Snapshot payload must be a single mapping object
- the payload must contain exactly the fixed public keys defined by Snapshot v1
- validation must inspect public fields only
- validation must not inspect Resume Summary objects, upstream wrappers, runtime internals, files, stores, journals, replay logs, audit logs, or scheduler state

Required fields:

- `contract`
- `snapshot_id`
- `source_valid`
- `source_outcome`
- `source_status`
- `valid`
- `status`
- `outcome`
- `reason`
- `metadata`

Allowed / unknown field policy:

- the required fields are the only allowed fields
- unknown fields are prohibited
- unknown fields make the Snapshot payload invalid
- unknown fields must not be ignored, renamed, embedded in `metadata`, or passed through to future layers

Schema version rule:

- `contract` is the schema version discriminator
- for Snapshot v1, `contract` must be exactly `aer.runtime.snapshot.v1`
- missing, null, non-string, or different `contract` values are invalid
- Snapshot v1 validators must not silently accept future schema versions

Identity validation:

- `snapshot_id` is required
- `snapshot_id` must be Snapshot-owned identity
- `snapshot_id` must be deterministic for an equivalent canonical Snapshot payload
- `snapshot_id` must not be copied from Resume Summary identity, wrapper identity, runtime identity, scheduler identity, operator identity, persistence identity, replay identity, recovery identity, audit identity, or journal identity

Lineage validation:

- `source_valid`, `source_outcome`, and `source_status` are required lineage fields
- lineage fields must represent Resume Summary public field projection only
- lineage fields must not expose Resume Marker objects, wrapper keys, upstream diagnostics, private fields, or unknown input fields

Status vocabulary validation:

- `status` is Snapshot structural status only
- allowed Snapshot `status` values are `valid` and `invalid`
- `source_status` is Resume Summary lineage status only
- `source_status` must not be treated as Snapshot structural status
- invalid Snapshot payloads must use Snapshot-owned status vocabulary rather than upstream status diagnostics

Consistency validation:

- when `valid` is `true`, `status` must be `valid`
- when `valid` is `true`, `reason` must be `None`
- when `valid` is `false`, `status` must be `invalid`
- when `valid` is `false`, `reason` must be a generic Snapshot-owned reason
- `metadata` must be a Snapshot-owned mapping and must not contain upstream object references
- `outcome` must be the Snapshot runtime-visible result and must not be an upstream wrapper object

Deterministic validation rule:

- validation rules are fully deterministic
- the same Snapshot payload must always produce the same valid or invalid validation result
- validation must not depend on wall-clock time, randomness, filesystem state, environment state, network state, scheduler state, operator state, replay state, recovery state, audit state, journal state, or persistence state

Canonical validation error taxonomy:

Each validation failure must belong to exactly one category. If more than one rule could apply, future implementations must use a deterministic precedence order defined by their implementation contract without changing these category meanings.

| Category | Trigger condition | Contract consequence | Snapshot rejected | Future auto-repair allowed |
| --- | --- | --- | --- | --- |
| Schema Error | Payload is not a single mapping object or cannot be evaluated as a Snapshot public payload. | Treat as invalid Snapshot input outside the v1 public shape. | Yes | No |
| Required Field Error | One or more required Snapshot v1 fields are missing. | Treat as invalid Snapshot input with incomplete public shape. | Yes | No |
| Unknown Field Error | Payload contains any field outside the fixed Snapshot v1 public key set. | Treat as invalid Snapshot input with prohibited extra surface. | Yes | No |
| Type Error | A required field has a type incompatible with its Snapshot v1 public meaning. | Treat as invalid Snapshot input with invalid public value shape. | Yes | No |
| Identity Error | `snapshot_id` is missing, non-Snapshot-owned, non-deterministic, or copied from a prohibited upstream/runtime identity source. | Treat as invalid Snapshot identity. | Yes | No |
| Lineage Error | `source_valid`, `source_outcome`, or `source_status` is missing, malformed, or exposes prohibited upstream object, wrapper, diagnostic, private, or unknown-field data. | Treat as invalid Snapshot lineage. | Yes | No |
| Status Error | `status` is outside Snapshot status vocabulary or `source_status` is incorrectly treated as Snapshot structural status. | Treat as invalid Snapshot status vocabulary. | Yes | No |
| Consistency Error | Public fields contradict each other, including `valid`/`status`/`reason` mismatches or metadata holding upstream object references. | Treat as invalid Snapshot consistency. | Yes | No |
| Version Error | `contract` is missing, null, non-string, not `aer.runtime.snapshot.v1`, or attempts to use an unsupported future version. | Treat as invalid Snapshot schema version. | Yes | No |
| Determinism Error | Validation outcome depends on time, randomness, IO, environment, external state, scheduler/operator state, replay/recovery/audit/journal/persistence state, or equivalent payloads produce different results. | Treat as invalid validation behavior for Snapshot v1. | Yes | No |

Validation reports are descriptive only. They must not perform mutation, repair, replay, persistence, recovery, scheduling, operator loop behavior, or runtime execution.

Invalid snapshot behavior:

- invalid Snapshot payloads must be rejected by the contract boundary
- invalid Snapshot payloads must not be repaired, normalized, persisted, replayed, recovered, scheduled, audited, journaled, or executed by this contract
- invalid Snapshot behavior must be reported with Snapshot-owned generic validation vocabulary
- invalid Snapshot handling must not copy upstream error text, wrapper names, internal diagnostics, or unknown fields

Compatibility boundary for future v2 migration:

- Snapshot v1 validators validate only `aer.runtime.snapshot.v1`
- future Snapshot v2 payloads must use a distinct contract value
- v2 migration must define a dedicated v2 contract before implementation
- Snapshot v1 validation must not infer, upgrade, downgrade, coerce, or silently accept v2 fields
- compatibility with future v2 is limited to explicit migration contracts outside Snapshot v1

No side effects rule:

- validation is pure contract evaluation only
- validation must not perform IO, storage, replay, recovery, persistence, journal, audit, scheduling, operator loop behavior, or runtime execution
- validation must not read files, write files, open network connections, mutate external state, persist Snapshot payloads, enqueue work, or dispatch runtime work

## Forbidden leaks
Snapshot v1 must not:

- expose `runtime_resume_marker`
- expose a resume marker object
- passthrough a Resume Summary object
- copy upstream error text
- embed upstream wrapper keys
- recursively leak upstream public or private objects
- rename upstream wrapper fields as Snapshot fields
- perform IO, storage, replay, recovery, persistence, scheduling, or runtime execution

## Object independence
Snapshot v1 output must be a Snapshot-owned value.

Mutating the Resume Summary input after Snapshot creation must not mutate the Snapshot payload. Mutating the Snapshot payload must not mutate the Resume Summary input.

Snapshot metadata must be Snapshot-owned metadata and must not hold references to upstream objects.

## Compatibility
Snapshot v1 is compatible with Resume Summary v1 public fields only. Future Resume Summary implementation changes are compatible when they preserve the Resume Summary public contract.

Future Persistence, Replay, Journal, and Audit layers may consume Snapshot v1 public payloads, but they must define their own dedicated public contract specs before implementation.

## Migration history
- Package 117: Defines Snapshot v1 architecture and public contract specification only.
- Package 117 does not add `core/runtime/aer_runtime_snapshot.py`.
- Package 117 does not implement Snapshot behavior.
