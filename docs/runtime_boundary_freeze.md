\# Runtime Boundary Freeze



Status: candidate freeze



Verified:

\- boundary/contract/ownership tests: 1249 passed, 154 subtests passed

\- evidence/seal/audit tests: 254 passed

\- recovery/replay/mutation/governed execution tests: 250 passed

\- combined runtime mainline tests: 490 passed



Freeze rule:

\- No new capability should be added directly into scheduler.py, agent\_loop.py, task\_runtime.py, step\_executor.py, or task\_runner.py.

\- New behavior must enter through adapter, boundary, policy, evidence, or contract modules.

\- Runtime core changes require regression across boundary, evidence, recovery, replay, mutation, and governed execution tests.



High-risk files:

\- core/tasks/scheduler.py

\- core/agent/agent\_loop.py

\- core/runtime/task\_runtime.py

\- core/runtime/step\_executor.py

\- core/runtime/task\_runner.py

\- core/tasks/runtime\_repair\_apply\_transaction.py



Next allowed work:

\- Extract only after green baseline.

\- No behavioral rewrite during freeze.

\- Add tests before moving responsibility.

