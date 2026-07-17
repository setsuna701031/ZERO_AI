# Runtime Execution Capability Unification Audit

Canonical runtime side-effect flow:

```text
Execution Authority -> Capability Token -> Runtime Action
```

The three layers must not collapse into each other.

- **Execution Authority** decides whether a side-effecting runtime request may be attempted.
- **Capability Token** proves scoped, live, lineage-bound permission for the decided request.
- **Runtime Action** performs the concrete side effect only after the authority and token layers pass.

`execution_authority`, `runtime_system_capability`, and `runtime_capability_tokens` are therefore not competing authority systems. They are separate layers in one chain. A system capability or generic capability token can never become execution authority by itself, and a runtime action cannot authorize itself.

This seal is policy-only. It must not run commands, mutate files, schedule work, recover state, or issue live runtime permissions.
