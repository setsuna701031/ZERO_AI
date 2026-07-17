# Runtime Scheduler Dispatch Admission Seal

## Sealed Boundary

Runtime Scheduler Dispatch Admission is sealed as a data-only authority layer.

## Ownership Matrix

| Layer | Owns |
| --- | --- |
| Progress Apply Gate | Validates completion apply |
| Cursor Advance Authority | Decides next cursor position |
| Tick Request Gate | Decides whether next tick may be requested |
| Scheduler Wake Admission | Decides whether scheduler wake may be admitted |
| Scheduler Wake Bridge | Carries admitted wake request to an injected handler |
| Scheduler Dispatch Admission | Authorizes dispatch eligibility |
| Scheduler Dispatch | Chooses runnable work |
| Executor | Executes work |

## Forbidden Actions

This layer must not:

- call scheduler
- run scheduler dispatch
- call `run_one_step`
- execute task
- mutate runtime state
- modify progress memory
- advance cursor
- create loop behavior

## Final Seal

Scheduler Dispatch Admission may only produce deterministic admission or denial records. Any actual scheduler dispatch remains downstream.
