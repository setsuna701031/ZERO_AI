# ZERO --- Event Engineering Automation

ZERO turns problems into executable engineering workflows.

No GitHub API. No commit. Fully controlled.

------------------------------------------------------------------------

## Why this matters

Modern AI tools generate text.\
ZERO executes engineering workflows.

It turns problems into structured outputs with: - no uncontrolled side
effects - full traceability - reproducible execution

------------------------------------------------------------------------

## Demo

```{=html}
<video src="https://github.com/setsuna701031/ZERO_AI/raw/main/demos/zero_event_engineering_demo.mp4" controls width="800">
```
```{=html}
</video>
```

------------------------------------------------------------------------

## What it does

Event → Task → Tool → Output → Audit → Session

Input: a single text file describing a problem\
Output: structured engineering artifacts ready for Git workflow

------------------------------------------------------------------------

## Example Use Cases

-   Auto-generate PR drafts from issue descriptions
-   Analyze incoming tasks and produce structured plans
-   Convert file-based events into engineering actions
-   Safe, auditable AI-assisted development workflows

------------------------------------------------------------------------

## Example Output

    workspace/github_outbox/
    ├── commit_message.txt
    ├── pr_description.md
    ├── devlog_entry.md
    └── publish_plan.md

    workspace/events_outbox/
    └── event_results.jsonl

    workspace/execution_sessions/
    └── <session_id>.json

    workspace/audit_logs/
    └── tool_audit.jsonl

------------------------------------------------------------------------

## Key Features

-   Controlled execution (no external side effects)
-   Event-driven automation (File → Task → Tool)
-   Tool routing system (ToolRouter)
-   Standardized tool schema (ToolRequest / ToolResult)
-   Full audit log (traceable execution)
-   Execution session tracking (end-to-end visibility)

------------------------------------------------------------------------

## Run Demo

    python demos/demo_event_to_github_flow.py

------------------------------------------------------------------------

## Result

A real engineering workflow executed without human intervention.

    [OK] 4 engineering artifacts generated
    [OK] 1 execution session recorded
    [OK] audit log updated
    [OK] no external side effects (safe mode)
