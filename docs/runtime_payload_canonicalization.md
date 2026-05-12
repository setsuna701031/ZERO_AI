# Runtime Payload Canonicalization v1

This document defines the first canonical runtime payload contract used by scheduler-side compatibility and result extraction logic.

The goal is not to delete legacy payload support immediately.

The goal is to establish which fields are canonical, which fields are fallback-only, and which traversal paths are allowed while narrowing scheduler/runtime coupling.

## Purpose

Scheduler currently needs to interpret runtime payloads from several sources:

```text
StepExecutor
simple runner
AgentLoop runner result
forced_repo_edit
Code Chain bridge
repair/retry/replan paths
legacy execution_log / step_results payloads
```

Historically this caused broad recursive extraction across many possible keys.

This document defines a narrower target ABI so future refactors can preserve behavior without expanding implicit payload assumptions.

## Canonical Tier 1 Runtime Text Fields

These fields are the preferred runtime contract fields.

Scheduler should prefer these fields before all legacy fallbacks:

```text
final_answer
message
error.message
execution_trace
results
```

### final_answer

`final_answer` is the preferred human-facing final result for completed or failed runtime paths.

Expected usage:

```text
task final output
StepExecutor batch output
runtime persistence
scheduler result projection
repair/retry/replan summary
```

### message

`message` is the preferred short runtime status or step output text.

Expected usage:

```text
step result summary
batch result summary
error message fallback
CLI-friendly output
```

### error.message

When `error` is a dictionary, `error.message` is the preferred structured error text.

Expected shape:

```json
{
  "error": {
    "type": "unsupported_step_type",
    "message": "unsupported step type: not_real_step",
    "retryable": false
  }
}
```

### execution_trace

`execution_trace` is the canonical trace carrier for runtime execution events.

Expected usage:

```text
runtime observability
scheduler trace promotion
repair/replan diagnostics
regression assertions
```

### results

`results` is the canonical batch step result list.

Expected usage:

```text
StepExecutor.execute_steps output
task result persistence
runtime hydration
final-answer extraction fallback
```

## Canonical Batch Envelope

A successful batch runtime result should preserve:

```text
ok
summary
message
final_answer
step_count
completed_steps
failed_step
results
last_result
error
execution_trace
```

A failed batch runtime result should preserve the same outer envelope, with:

```text
ok == False
error != None
failed_step != None
results containing completed/failed step result records
execution_trace containing failure trace
```

An empty batch runtime result should preserve:

```text
ok == True
summary == all steps executed
message == 執行完成
final_answer == 執行完成
results == []
execution_trace == []
error == None
```

## Canonical Step Result Envelope

Each step result should preserve:

```text
ok
step_type
step_index
step_count
task_id
runtime_mode
step
result
message
final_answer
error
execution_trace
```

The nested `result` may contain tool-specific or step-specific fields, but scheduler should not depend on absolute local paths or environment-specific values.

## Legacy Compatibility Fields

These fields are allowed only as fallback compatibility sources.

They should not be introduced into new runtime payloads unless a boundary-specific contract explicitly requires them:

```text
text
content
response
stdout
checked_text
summary_text
output_text
payload
raw
data
previous_result
raw_result
runner_result
task
```

## Allowed Recursive Traversal

Scheduler compatibility logic may traverse these nested fields while legacy compatibility remains necessary:

```text
result
last_step_result
raw_result
runner_result
task
raw
data
payload
previous_result
```

List traversal is allowed for recent result containers:

```text
results
step_results
execution_log
```

Traversal should remain bounded.

Recommended maximum depth:

```text
8
```

## Disallowed Future Payload Growth

Future runtime payloads should not add new arbitrary text aliases unless there is a documented contract reason.

Avoid adding new fields like:

```text
human_text
assistant_text
display_text
output
answer_text
result_text
```

Instead, map new output into:

```text
final_answer
message
error.message
```

## Compatibility Rule

During transition, scheduler may still read legacy fields.

However, new code should write canonical fields first.

Preferred write order:

```text
final_answer
message
error.message
results
execution_trace
```

Preferred read order for success text:

```text
final_answer
message
content
text
response
stdout
checked_text
```

Preferred read order for error text:

```text
error.message
error
last_error
failure_message
message
final_answer
stderr
output_text
summary_text
content
text
```

## Runtime ABI Narrowing Rule

Before extracting or refactoring scheduler runtime logic, classify every touched field as one of:

```text
canonical required
canonical optional
legacy fallback
derived display
internal transient
```

Do not remove legacy fallback support until regression coverage proves the fallback is unused or intentionally deprecated.

## Current Contract Tests

Current related tests:

```text
tests/test_step_executor.py
tests/test_runtime_execution_contracts.py
tests/test_runtime_contract_integrity.py
tests/run_regression_contracts.py
```

These tests currently protect:

```text
unsupported step type envelope
execute_steps failure envelope
execute_steps empty envelope
write/read/verify success envelope
Tier 1 runtime integrity fields
execution_trace shape
```

## Next Step

After this document is committed, the next safe step is to add focused regression coverage for scheduler payload text extraction.

Candidate test target:

```text
tests/test_scheduler_runtime_payload_text.py
```

Target behavior:

```text
_extract_text_from_result_payload prefers canonical fields
_extract_error_text_deep prefers error.message
legacy fallback still works
recursive traversal remains bounded
```

Do not refactor scheduler extraction logic before this focused coverage exists.
