# Runtime Cursor Advance Authority Review

## Package
1521-1528

## Review Decision
GO for Cursor Advance Authority only.

## Ownership Boundary
Runtime Cursor Advance Authority owns cursor-position authorization after a valid progress apply record. It does not own completion validation, progress application, scheduler admission, or execution.

## Why Separate From Progress Apply
Progress Apply decides whether a completed commit may become progress state. Cursor Advance decides only whether a next cursor position is authorized from that accepted progress signal. Keeping these separate prevents completion validation from silently becoming runtime navigation.

## Why Cursor Movement Cannot Trigger Execution
Cursor movement is not execution admission. A cursor advance record may identify the next position, but it must not request a next tick, call a scheduler, call an executor, continue a loop, or run a task.

## Forbidden Surfaces
- no scheduler import or call
- no executor import or call
- no task runner import or call
- no agent loop import or call
- no progress memory writer import or call
- no runtime queue mutation
- no next tick request

## Remaining Gap
Scheduler admission must consume cursor authority in a later package before any next tick can be requested.
