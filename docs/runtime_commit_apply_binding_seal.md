# Runtime Commit Apply Binding Seal

The runtime commit/apply binding is sealed as a post-validation record boundary.

`commit_allowed` is not `commit_applied`. Validation and commit allowance are prerequisites; actual apply recording requires a governed commit adapter.

Commit/apply belongs to the governed adapter. The executor cannot commit directly, `RuntimeOperatorService` remains the owner, and the CLI does not call git directly.

The blocked path is deterministic when no governed commit adapter exists: `commit_applied=False`, `commit_recorded=False`, `git_diff_recorded=False`, and `apply_status=blocked_no_governed_commit_adapter`.

The success path records `commit_applied=True`, `commit_recorded=True`, `git_diff_recorded=True`, a deterministic adapter-provided `commit_id`, and `apply_status=commit_apply_recorded`.

The next optional layer is Runtime Launch Script / Web UI.
