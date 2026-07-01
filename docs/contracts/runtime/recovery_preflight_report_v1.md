# Recovery Preflight Report v1

Package 185 defines the passive Recovery preflight report surface.

The report consumes a Package 184 preflight eligibility report and projects it
into a stable report shape. The report remains non-executing, single-entry,
observe-only, dry-run, and Recovery-disabled.

Required safety fields:
- `preflight_report_only: True`
- `eligible` derived from valid preflight eligibility
- `runtime_binding_allowed: False`
- `runtime_mainline_wiring_allowed: False`
- `event_emitted: False`
- `recovery_enabled: False`
- `executes_recovery: False`
- `side_effects_performed: False`
- `plain_dict_only: True`

GO / NO-GO: GO when the report tests pass.
