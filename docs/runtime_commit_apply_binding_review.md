# Runtime Commit Apply Binding Review

Package 2861-2940 binds controlled mutation success to a governed commit/apply record.

`commit_allowed` is not the same as `commit_applied`. `commit_allowed=True` means controlled mutation passed validation and may be committed. `commit_applied=True` and `commit_recorded=True` require a governed commit adapter to record the apply result.

Commit/apply belongs to the governed adapter boundary. The executor cannot commit directly, and the binding consumes only the controlled mutation result after `mutation_allowed=True`, `validation_passed=True`, `commit_allowed=True`, and `rollback_required=False`.

The CLI does not call git directly. `zero_operator_console` only reports commit/apply fields returned by `RuntimeOperatorService`.

If no governed commit adapter is present, the binding returns deterministic `blocked_no_governed_commit_adapter` with `commit_applied=False`, `commit_recorded=False`, and `git_diff_recorded=False`.

The next optional layer is Runtime Launch Script / Web UI.
