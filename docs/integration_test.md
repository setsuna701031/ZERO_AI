\# Integration Test



The integration test verifies the full DAG execution flow.



\---



\# Test Scenario



Tasks:



task\_a

task\_b depends\_on task\_a



Execution flow:



Tick #1:

task\_a finished

task\_b blocked



Dependency resolved



Tick #2:

task\_b queued / running



Tick #3:

task\_b finished



\---



\# Assertions



Final assertions:



task\_a status == finished

task\_b status == finished



Integration test ensures:



\* DAG dependency works

\* Scheduler queue works

\* Runtime state updates

\* Task runner executes

\* Final state correct



