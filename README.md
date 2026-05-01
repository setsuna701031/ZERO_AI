# ZERO --- Event Engineering Automation

ZERO turns a simple file event into structured engineering outputs
automatically.\
No GitHub API. No commit. Fully controlled.

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
