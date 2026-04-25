# ZERO Capabilities

## Document Flow Orchestrator

File:

- `core/capabilities/document_flow_orchestrator.py`

Status:

- Capability wrapper
- Not planner
- Not AgentLoop
- Not UI demo

Provides:

- `run_summary(input_path, output_path)`
- `run_action_items(input_path, output_path)`
- `run_summary_and_action_items(input_path, summary_output_path, action_items_output_path)`

Validation:

- `python tests/run_document_flow_orchestrator_smoke.py`

Purpose:

- Provides a clean callable document-flow capability for future AgentLoop orchestration.
- Wraps the official `doc-summary` and `doc-action-items` task lifecycle.

## Smoke Policy

ZERO currently separates smoke validation into three levels.

### Mainline smoke

Mainline smoke is for core paths that must not regress during normal development.

Entry:

- `python tests/run_mainline_smoke.py`
- `python main.py smoke`

Mainline smoke should include only stable, high-value checks such as:

- tool layer smoke
- scheduler smoke
- runtime smoke
- document task smoke
- document flow showcase smoke
- document pipeline identity smoke
- requirement demo smoke
- execution demo smoke
- semantic task smoke
- implementation-proof smoke
- full-build demo smoke

### Feature smoke

Feature smoke protects a specific capability or showcase while it is still evolving.

These checks are useful, but they do not automatically belong in mainline smoke.

Current examples:

- `python tests/run_persona_agent_demo_smoke.py`
- `python tests/run_persona_runtime_entry_smoke.py`
- `python tests/run_document_flow_orchestrator_smoke.py`

### Temporary / diagnostic smoke

Temporary smoke is used during debugging or extraction work.

These files should be archived, merged, or removed once the relevant behavior is protected by a clearer mainline or feature smoke.

### Rule

Do not fold every new smoke into mainline.

A smoke should enter mainline only when the protected path is:

- stable
- part of the normal expected system behavior
- important enough that future changes should fail immediately if it breaks