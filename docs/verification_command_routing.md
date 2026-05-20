# Verification Command Routing Contract

## Purpose

The verification command routing layer connects an approved engineering proposal to
a verification-only command route.

It does not execute commands by itself. It classifies which commands are eligible
for a future governed executor to run.

The intended position is:

```text
diff proposal
 -> approval envelope
 -> verification profile
 -> verification route
 -> governed runtime execution
 -> verification evidence
 -> retry/repair eligibility
```

## Boundary

Verification routes are:

- verification-only
- read-only at the planning layer
- not mutation authority
- not patch application authority
- not runtime canonical success

Required metadata:

```text
verification_only=True
mutation_allowed=False
patch_apply_allowed=False
execution_authority_owned_by_runtime=True
governed_runtime_required=True
canonical_success=False
```

## Allowed Command Shape

Initial allowed command families are intentionally narrow:

```text
python -m pytest ...
python -m compileall ...
pytest ...
```

The router blocks command shapes that imply mutation, network setup, shell control,
or repository publication, such as:

```text
git push
git commit
git reset
git clean
pip install
npm install
curl / wget
redirection
shell chaining
Remove-Item / rm / del
```

## Verification Evidence

Verification evidence records externally supplied command results and determines
whether verification passed or failed.

It does not claim runtime canonical success.

Canonical success still requires governed runtime evidence and audit lineage.

## Non-Goals

This layer does not:

- apply patches
- mutate files
- run commands directly
- bypass the governed runtime
- replace recovery or rollback logic
- approve autonomous mutation
- publish repository changes

## Future Extension

Future safe extensions may include:

- named verification profiles
- bounded retry budgets
- targeted test selection
- compile/test grouping
- route-to-runtime execution adapters
- verification evidence sealing through runtime evidence chains

Any extension must preserve L4 runtime freeze invariants.
