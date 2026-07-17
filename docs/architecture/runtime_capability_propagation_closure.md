# Runtime capability propagation closure

## Canonical flow

`Authority Decision -> Capability -> Dispatcher -> Runtime -> Mutation -> Evidence -> Persistence`

The canonical identity is `RuntimeCapabilityProvenance`. It is created exactly once from an allowed `RuntimeExecutionAuthorityDecision`. Every downstream layer carries the same `capability_id`, `authority_decision_id`, scope, lineage, and fingerprint. Serialization may rehydrate the sealed envelope, but it must not create a new identity.

## Sealed rules

1. Single Capability Source: `capability_from_authority_decision` is the mainline source.
2. No Capability Re-Issue: one authority decision maps to one deterministic capability identity; the canonical zone-token method rejects a second issue for the same decision.
3. No Capability Upgrade: resource, action, scope, and lineage are immutable; wildcard scope is rejected.
4. No Capability Override: `propagate_runtime_capability` rejects a different capability or authority-decision ID already present at a handoff.
5. Dispatcher preservation: RuntimeDispatcher creates the provenance once and carries it with the live execution seal.
6. Runtime preservation: TaskRunner validates consistency and propagates the same provenance; TaskRuntime stores the same ID.
7. Mutation preservation: RuntimeMutationGateway no longer creates replacement mutation capabilities. It validates and advances the incoming provenance.
8. Capability Evidence Consistency: RuntimeEvidenceAuthority embeds the same capability and rejects conflicting capability-bearing updates.
9. Capability Persistence Consistency: RuntimePersistenceService carries the same capability through governed persistence and reports the same ID in its result.

## Scoped audit

| File | Result |
| --- | --- |
| `core/runtime/runtime_dispatcher.py` | authority-decision-rooted provenance issued once; resume validates persisted provenance |
| `core/runtime/task_runner.py` | active late-bound builder preserves provenance; pre-execution checks identity consistency |
| `core/runtime/task_runtime.py` | runtime state persists capability provenance and ID |
| `core/runtime/runtime_mutation_gateway.py` | gateway re-issuance removed; incoming provenance preserved |
| `core/runtime/governed_mutation_runtime.py` | mutation, evidence, replay, result, diagnostics, topology, and bundle persistence share one provenance |
| `core/runtime/runtime_evidence_authority.py` | evidence carries and validates capability identity |
| `core/runtime/runtime_evidence_registry.py` | registry snapshot indexes capability and authority-decision IDs |
| `core/runtime/runtime_persistence_service.py` | persistence checks ID consistency and returns the persisted capability ID |
| `core/runtime/runtime_execution_authority.py` | canonical immutable propagation contract |
| `core/runtime/runtime_capability_tokens.py` | canonical decision-rooted issue method added; exact capability/zone checks prevent upgrade |

## Non-mainline issue reporting

These findings are mandatory reports even where they are outside this package’s safe compatibility scope:

| Required issue | Finding | Disposition |
| --- | --- | --- |
| second capability system | `RuntimeCapabilityTokenManager.issue_token` remains a legacy zone bearer-token API alongside live execution seals and SYSTEM tokens. | Non-mainline compatibility surface; new mainline code must use decision-rooted provenance or `issue_from_authority_decision`. |
| wildcard capability | Legacy `RuntimeCapabilityScope` and file-service compatibility scopes still contain `*` path patterns. | Reported; not accepted by canonical provenance. Requires a separate path-scope migration. |
| capability fallback | Legacy tasks without provenance can still use older live execution seals; controlled-document compatibility also synthesizes descriptive authority metadata. | Reported; metadata is not authority and new dispatcher work always carries provenance. |
| authority/capability mixed responsibility | Runtime execution seals, SYSTEM capabilities, mutation scopes, and zone tokens model different domains. | Reported; the provenance record binds them to one authority decision without silently merging domain semantics. |
| capability/evidence drift | Older evidence bundles may contain only a capability graph and no root capability ID. | Reported; new evidence embeds the root ID and conflicting updates fail. |
| capability/persistence drift | Older persistence calls may omit capability provenance. | Reported; new TaskRuntime and governed-mutation mainlines propagate it, while legacy omissions remain visible rather than reconstructed. |

Report, do not silently skip. Do not suppress these findings because an unrelated compatibility test depends on the legacy surface.
