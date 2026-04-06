\# ZERO Task OS



Local DAG Task Orchestration Runtime with Persistent Runtime State Machine.



This project implements a local task orchestration system that supports:



\* Task repository

\* DAG dependency scheduling

\* Scheduler queue

\* Runtime state machine

\* Task runner

\* Persistent runtime state

\* Integration testing



\---



\# System Components



\## 1. Task Repository



Stores all tasks, status, dependencies, history, and workspace paths.



\## 2. DAG Scheduler



Determines which tasks are ready based on dependency completion.



\## 3. Scheduler Queue



Ready tasks are pushed into a runnable queue.



\## 4. Runtime State Machine



Tracks task runtime execution state:



\* current step

\* retry count

\* replan count

\* failure type

\* final answer



\## 5. Task Runner



Executes task steps and updates runtime state.



\## 6. Integration Test



End-to-end test verifying DAG execution flow.



\---



\# DAG Execution Flow



\## Tick #1 – Dependency Blocking



docs/images/dag\_runtime\_tick1\_blocked.png



Task A finished, Task B blocked by dependency.



\## Scheduler – Dependency Unlocked → Queue



docs/images/scheduler\_queue\_after\_unblock.png



Task B moved into scheduler queue after dependency resolved.



\## Tick #2 – Upstream Finished



docs/images/dag\_repo\_tick2\_finished.png



Repository shows upstream task finished.



\## Tick #3 – All Tasks Finished



docs/images/dag\_repo\_tick3\_runtime\_finished.png



All tasks completed and runtime state finalized.



\## Integration Tests Passed



docs/images/task\_os\_integration\_tests\_passed.png



End-to-end orchestration test passed.



\---



\# Project Structure



core/

tasks/

runtime/

services/

docs/

workspace/

tests/



\---



\# Summary



This project demonstrates a local task orchestration runtime similar in architecture to workflow orchestration systems such as Airflow, Prefect, or Temporal, but implemented as a lightweight local task operating system.



