# ZERO Redemo Notes

## Purpose

This note preserves the current safe engineering-output boundary for ZERO before adding more generators, tools, or GitHub-side automation.

The current priority is simple:

```text
Keep the git pipeline safe, traceable, replayable, and outbox-only.
```

---

## Current Core Demo

### Git Pipeline Replay

```text
real git_diff/status
-> analyze
-> generate commit message
-> generate PR description
-> write github_outbox artifacts
-> replay trace
```

This path demonstrates that ZERO can inspect real local repository changes and generate review artifacts without performing repository or GitHub mutations.

Core demo video:

```text
demos/00_git_pipeline_replay_demo.mp4
```

---

## Tool Capability Model

Allowed capability classes:

```text
read_only
generate_only
workspace_write
```

Disabled capability class:

```text
external_write
```

---

## Core Rules

Generated artifacts are not actions.

Only approved executor steps can create side effects.

A generated commit message is not a commit.

A generated PR description is not a pull request.

A generated outbox artifact must remain reviewable before any external mutation is allowed.

---

## Current Safe Pipeline

```text
real git_diff/status
-> analyze
-> commit_message_generator
-> pr_description_generator
-> github_outbox.write
-> trace
-> read-only replay
```

---

## Allowed Outbox Files

```text
workspace/github_outbox/commit_message.txt
workspace/github_outbox/pr_description.md
workspace/github_outbox/devlog.md
workspace/github_outbox/review_report.md
```

---

## Forbidden Actions

```text
git commit
git push
create PR
external_write
```

The current pipeline must not perform these actions.

If any future workflow needs these actions, it must go through an explicit approval layer first.

---

## Trace Replay Contract

Replay is read-only.

Replay may read existing trace files, runtime state, result files, and outbox artifacts.

Replay must not:

```text
execute a task again
call ToolRegistry
call tools
modify repository files
write external systems
commit
push
create PR
```

Expected replay proof fields:

```text
step
mode
origin
artifact size
artifact hash
mutation_attempt
summary
safety flags
```

---

## Current Validation Targets

Current smoke coverage should include:

```text
run_readonly_tools_smoke.py
run_commit_message_generator_smoke.py
run_pr_description_generator_smoke.py
run_github_outbox_smoke.py
run_github_outbox_pipeline_smoke.py
run_git_pipeline_planner_smoke.py
run_tool_policy_smoke.py
run_trace_replay_smoke.py
```

Expected result:

```text
ALL PASS
```

---

## Current Direction

Do not add another generator, tool, GitHub API action, or approval mutation path before this boundary stays documented and validated.

Recommended order:

```text
1. Keep git pipeline stable
2. Keep replay read-only
3. Keep demo video and README current
4. Add dry-run approval record only
5. Add real GitHub mutation later, behind explicit approval
```

---

## Approval Layer Boundary

The next approval layer should start as dry-run only.

Allowed first version:

```text
show outbox files
ask yes/no
write approval_record.json
```

Not allowed yet:

```text
git commit
git push
create PR
merge PR
delete branch
force push
change repo settings
```

---

## Summary

ZERO's safe engineering-output path is valuable because it separates generation from mutation.

The current system should remain:

```text
traceable
replayable
outbox-only
policy-guarded
human-reviewable
```

This boundary is the foundation for later controlled GitHub automation.
