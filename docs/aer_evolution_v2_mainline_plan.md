\# AER Evolution v2 Mainline Plan



\## Purpose



AER Evolution v2 is the long-running operator mainline.



This package does not implement runtime behavior. It locks the design boundary for later implementation packages.



\## Mainline Scope



The v2 mainline is defined by six surfaces:



1\. Operator loop

2\. Checkpoint

3\. Resume

4\. Issue reporter

5\. Stop condition

6\. Human approval boundary



\## Non-goals



This package must not:



\- rewrite scheduler behavior

\- rewrite task runner behavior

\- change operator runtime execution

\- add v2 runtime behavior

\- mutate RC1 contract behavior

\- introduce hidden fallback routes



\## Operator Loop



The operator loop is the outer execution controller for long-running work.



It must eventually own:



\- package admission

\- loop iteration state

\- checkpoint boundary

\- stop-condition evaluation

\- issue reporting

\- human approval pauses

\- resume handoff



The loop must not directly bypass existing governed execution surfaces.



\## Checkpoint



A checkpoint records enough state to resume safely.



A checkpoint must eventually include:



\- operator session identity

\- package identity

\- current phase

\- completed phase markers

\- pending phase markers

\- last known runtime status

\- stop reason, if any

\- approval wait state, if any

\- issue reporter output, if any



Checkpoint writes must be explicit and auditable.



\## Resume



Resume must continue from checkpoint state.



Resume must not:



\- duplicate completed phases

\- silently restart a finished package

\- skip approval waits

\- hide prior issue reports

\- create a new identity unless explicitly requested



Resume must preserve operator lineage.



\## Issue Reporter



The issue reporter records discovered problems that are outside the current executable scope.



It must support the rule:



If the operator discovers a non-mainline issue, it reports it explicitly instead of silently skipping it.



Issue reporter output must be kept separate from execution result status.



\## Stop Condition



Stop conditions define when the operator must pause or terminate.



Initial stop-condition categories:



\- completed

\- failed

\- blocked

\- waiting\_for\_human\_approval

\- unsafe\_to\_continue

\- missing\_checkpoint

\- resume\_identity\_mismatch

\- non\_mainline\_issue\_detected

\- validation\_failed



Stop conditions must be explicit.



\## Human Approval Boundary



Human approval is required when the next action would cross a policy or authority boundary.



Human approval must eventually be required for:



\- destructive repository mutation

\- broad runtime rewrites

\- contract weakening

\- deletion of evidence or checkpoint files

\- automatic continuation after serious validation failure

\- scope expansion beyond approved package



\## Invariants



\- RC1 behavior remains protected.

\- v2 starts as a separate evolution branch.

\- Long validations are not delegated to Codex.

\- Short validation only for this package.

\- No implementation code in this package.

\- All non-mainline issues must be reported.

