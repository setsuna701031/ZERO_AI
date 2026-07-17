# Runtime Session Birth Contract v1

Status: disabled / limited runtime session birth path.

Schema: `zero.runtime.session_birth.v1`.

This contract reserves the first limited runtime session birth path after the limited active runtime opening
gate. The opening gate remains NO-GO by default. A deterministic `runtime_session_id` may be produced only
when explicit test-controlled opening input is GO.

The born session is inert:

- limited
- non-executing
- non-mutating
- no execution lease
- no committed capabilities
- no executor start
- no tool call
- no file mutation
- no IO
- no autonomy or self-start
- no background loop

Heartbeat/status projection is data-only and never live.

Non-mainline issue reporting remains required. Any detected non-mainline issue must be represented in output,
not silently skipped.

Final decision: runtime session birth is structurally possible only under explicit test-controlled GO input,
and the born session remains inert.
