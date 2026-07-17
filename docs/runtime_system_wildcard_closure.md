# Runtime SYSTEM wildcard closure

## Decision

`SYSTEM` remains a runtime identity for infrastructure metadata; it is no longer an authority shortcut. The ownership matrix grants only explicit read and observability operations. Mutation, execution, recovery, and rollback require live tokens bound to issuer, resource, action, scope, and lineage. Wildcard resource or action grants are rejected.

## Permission inventory

| Class | Explicit SYSTEM capability | Authority boundary |
| --- | --- | --- |
| READ | runtime state reads | ownership matrix |
| WRITE | runtime event and incident emission | ownership matrix |
| MUTATE | declared workspace file or generated-artifact write | RuntimeMutationGateway token |
| EXECUTE | declared task execution or work-package dispatch | RuntimeDispatcher token |
| ROLLBACK | declared workspace rollback for one task lineage | TaskRunner token, TaskRuntime validation |
| RECOVERY | declared task recovery for one lineage | scoped token contract |
| ADMIN | none | denied |

## Audited mainline paths

- `runtime_ownership.py`: SYSTEM policy grants are an inspectable finite set.
- `runtime_mutation_authority.py`: mutation defaults are request/target bound; wildcard grants fail validation.
- `runtime_mutation_gateway.py`: a SYSTEM mutation must present a live mutation token before policy evaluation or I/O.
- `runtime_dispatcher.py`: dispatch creates a task/package/session-bound execution token.
- `task_runner.py`: SYSTEM execution validates dispatch scope and lineage; rollback receives a separate bounded token.
- `task_runtime.py`: SYSTEM rollback validates the TaskRunner token before restoration writes.

## Non-mainline issue report

| Issue class | Finding | Closure / disposition |
| --- | --- | --- |
| hidden SYSTEM paths | SYSTEM appears as metadata identity in execution and file-service evidence paths. | Metadata identity is explicitly separated from policy authority; no grant is inferred from the string. |
| implicit elevation | Mutation capability defaults and legacy patch apply used `*` operation/target grants. | Defaults now bind to the requested operation and target; legacy callers issue per-item grants. |
| authority drift | Execution seals validated task lineage but did not model resource/action and issuer in one contract. | The scoped SYSTEM token validates all five dimensions alongside the existing live execution seal. |
| ownership drift | Runtime status projection and persistence use component owner strings outside the ownership enum. | These remain projections, not SYSTEM grants; mutating SYSTEM paths are token-gated at execution/mutation/rollback boundaries. |
| recovery bypass | Recovery planning exposes resumability metadata without a live capability. | Metadata remains non-executable; recovery execution is reserved in the explicit RECOVERY class and requires a lineage-bound token. |
| rollback bypass | TaskRuntime restoration could write from saved backup metadata without checking SYSTEM authority. | SYSTEM rollback now requires a live TaskRunner-issued token scoped to the task lineage. |

## Residual non-mainline policy

Compatibility paths may carry SYSTEM identity metadata, but they must not interpret it as approval. Any future executable recovery or administrative path must add an explicit inventory entry, an authorized issuer, and scope/lineage validation. ADMIN intentionally has no grants.
