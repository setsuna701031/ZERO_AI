# ZERO Redemo Notes

Current priority: keep the safe engineering-output path documented before adding more generators or tools.

## Tool Capability Model

- `read_only`
- `generate_only`
- `workspace_write`
- `external_write` disabled

## Core Rules

Generated artifacts are not actions.

Only approved executor steps can create side effects.

## Current Safe Pipeline

```text
real git_diff/status
-> analyze
-> commit_message_generator
-> github_outbox.write
-> trace
```

## Allowed Outbox Files

```text
workspace/github_outbox/commit_message.txt
workspace/github_outbox/pr_description.md
workspace/github_outbox/devlog.md
workspace/github_outbox/review_report.md
```

## Forbidden

```text
git commit
git push
create PR
external_write
```

## Current Direction

Do not add another generator or tool before this boundary stays documented and validated.
