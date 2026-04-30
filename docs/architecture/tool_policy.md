# Tool Policy

This document records the current safe tool boundary for ZERO.

## Tool Capability Model

- `read_only`: may inspect local repository state or allowed files, but must not mutate.
- `generate_only`: may generate text or structured data, but must not write files or mutate state.
- `workspace_write`: may write only approved workspace artifacts.
- `external_write`: disabled.

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

The current pipeline may produce engineering artifacts, but it must not perform GitHub or git mutations.

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

## Trace Expectations

Tool trace records should include:

- `tool_name`
- `tool_class`
- `side_effect_level`
- `policy_decision`
- `output_path` or `output_summary`
- `origin` when the output comes from a generator

Trace is evidence. It is not approval.
