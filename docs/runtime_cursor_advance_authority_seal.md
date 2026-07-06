# Runtime Cursor Advance Authority Seal

## Package
1521-1528

## Final Decision
GO for Cursor Advance Authority only.

## Sealed Boundary
Progress Apply:
    decides completion validity

Cursor Advance:
    decides next position

Scheduler:
    decides execution admission

## Sealed Outcomes
- valid progress apply can authorize cursor advance
- missing progress apply is denied
- rejected progress apply is denied
- denied records are deterministic
- runtime_state_mutated remains false

## Locked Surfaces
- scheduler connection
- executor connection
- loop start or continuation
- task execution
- runtime queue mutation
- progress memory mutation
- automatic next tick

## Remaining Gap
The runtime still needs a separate scheduler admission layer that consumes cursor authority without bypassing bounded execution controls.
