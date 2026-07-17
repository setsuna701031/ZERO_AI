# Runtime Scheduler Dispatch Admission v1

## Purpose

Runtime Scheduler Dispatch Admission is the data-only authority layer that consumes a `RuntimeSchedulerWakeBridgeRecord` and decides whether scheduler dispatch may be admitted.

It does not choose runnable work. It does not call scheduler APIs. It does not execute tasks.

## Input

`RuntimeSchedulerWakeBridgeRecord`

Required input semantics:

- `scheduler_wake_bridge_authorized` must be true.
- `source_wake_admission_id` or `source_wake_bridge_id` must identify the upstream wake bridge source.
- `admitted_cursor` must identify the cursor admitted for downstream dispatch consideration.

## Output

`RuntimeSchedulerDispatchAdmissionRecord`

Required fields:

- `scheduler_dispatch_admitted`
- `source_wake_bridge_id`
- `admitted_cursor`
- `dispatch_reason`
- `denial_reason`
- `scheduler_dispatch_started`
- `executor_invoked`
- `runtime_state_mutated`

## Rules

- Valid wake bridge records may admit scheduler dispatch.
- Missing wake bridge records must deny deterministically.
- Rejected wake bridge records must deny deterministically.
- Missing source wake bridge identity must deny deterministically.
- Missing admitted cursor must deny deterministically.
- `scheduler_dispatch_started` must remain false.
- `executor_invoked` must remain false.
- `runtime_state_mutated` must remain false.

## Ownership

- Scheduler Wake Bridge carries admitted wake data.
- Scheduler Dispatch Admission authorizes dispatch eligibility.
- Scheduler Dispatch still owns choosing runnable work.
- Executor still owns execution.
