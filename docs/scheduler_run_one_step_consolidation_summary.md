\# Scheduler run\_one\_step Consolidation Summary



\## Current active wrapper



\- Active: `\_zero\_scheduler\_run\_one\_step\_v16`

\- Sealed by: `tests/test\_scheduler\_run\_one\_step\_active\_chain\_seal.py`



\## Confirmed protected behavior



\- v15/v16 operator failed/completion behavior is sealed by:

&#x20; - `tests/test\_scheduler\_operator\_failed\_chain\_seal.py`



\## First consolidation target



\### Runtime gate fallback group



Candidate wrappers:



\- v1

\- v2

\- v3

\- v4

\- v5



Observed behavior:



\- Detect soft gate failures.

\- Select current step.

\- Re-enter execution through `\_run\_step\_via\_task\_runner`.

\- Attach canonical fallback result.

\- Gradually add authority/capability checks.



Plan:



1\. Do not remove any wrapper yet.

2\. Add tests for v1-v5 shared fallback behavior.

3\. Extract common helper only after tests exist.

4\. Collapse v1-v5 into one runtime gate fallback layer.

5\. Keep active-chain seal updated only after behavior-level tests pass.



\## Non-mainline issue



ZERO work package execution currently does not enforce forbidden write paths strongly enough. Do not use ZERO to execute report-only packages that mention protected source files until forbidden-write boundary is sealed.

