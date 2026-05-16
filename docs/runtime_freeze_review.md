\# Runtime Freeze Review



\## Current Freeze Status



ZERO has reached a runtime stabilization checkpoint.



Confirmed stable:



\- Scheduler smoke passes.

\- Mainline smoke passes.

\- Targeted scheduler/runtime pytest bundle passes.

\- Scheduler compatibility methods have been restored through adapter assignments.

\- Windows smoke runner can complete and report pass/fail reliably.

\- CLI JSON output no longer fails on circular runtime payloads.

\- Local LLM client dependency loading no longer fails when `requests` is unavailable.

\- Runtime artifact hygiene boundary has been added to `.gitignore`.



\## Stabilized Boundaries



\### Scheduler Boundary



`scheduler.py` is currently treated as a compatibility facade plus orchestration entrypoint.



Completed extractions:



\- Command planning

\- Path parsing

\- Queue row / snapshot formatting

\- Public task record normalization

\- Trace serialization



Do not add new feature logic directly into `scheduler.py`.



\### Compatibility Boundary



Restored compatibility hooks:



\- `\_handle\_dispatch\_result`

\- `\_resolve\_guard\_target\_path`

\- `\_resolve\_step\_path`

\- `\_resolve\_read\_path\_with\_fallback`

\- `\_needs\_scheduler\_path\_resolution`

\- `\_normalize\_step\_scope`



These are compatibility adapters, not long-term ownership targets.



\### Smoke Boundary



Current baseline:



\- `python tests/run\_mainline\_smoke.py`

\- `python tests/run\_scheduler\_smoke.py`

\- targeted scheduler/runtime pytest bundle



These should remain the minimum regression gate before deeper runtime changes.



\### Serialization Boundary



CLI JSON output must use safe serialization.



Circular references should be represented with readable placeholders, not crash the CLI.



\### Dependency Boundary



LLM client loading must not fail at module import time because of optional HTTP dependencies.



Provider/runtime dependency failures must remain visible and diagnosable.



\### Repository Hygiene Boundary



Runtime-generated artifacts should not continue polluting the repository.



Ignored categories include:



\- Python cache files

\- virtual environments

\- runtime logs

\- traces

\- backups

\- memory state

\- mutation preview/state/audit artifacts

\- local clone/test repositories



\## Remaining Scheduler Responsibilities



Still high-risk and should not be extracted casually:



\- `tick()`

\- dispatch orchestration

\- runtime queue transition

\- repair/resume orchestration

\- task lifecycle ownership

\- execution result finalization



These require separate ownership migration planning.



\## Temporary Adapters



The restored scheduler compatibility hooks are acceptable for now.



Do not remove them until:



1\. all call sites are identified,

2\. direct ownership target modules are stable,

3\. contract tests exist,

4\. smoke passes before and after migration.



\## Phase 2 Extraction Rules



Allowed:



\- Small bounded extraction

\- Clear ownership target

\- Tests first or same commit

\- No public API break

\- No runtime topology change without explicit review



Forbidden:



\- broad scheduler cleanup

\- touching `tick()` together with unrelated cleanup

\- mixing extraction with feature work

\- silently changing queue or dispatch behavior

\- removing compatibility wrappers without call-site migration



\## Current Recommendation



Freeze this checkpoint.



Next major phase should be:



1\. review remaining scheduler responsibilities,

2\. classify high-risk ownership zones,

3\. plan phase 2 extraction,

4\. only then touch dispatch / queue / repair / resume internals.

