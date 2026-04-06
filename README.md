\# ZERO AI



Local-first Task OS / DAG Task Orchestration Runtime / Agent Execution Engine



ZERO is an experimental local task operating system that executes AI tasks as structured workflows with persistent runtime state, dependency scheduling, and workspace-based execution.



This project explores how a local AI system can manage tasks, plans, execution steps, runtime state, retries, replanning, and dependency graphs.



\---



\# Current Milestone



\*\*DAG dependency scheduling end-to-end integration passed\*\*



The system now supports:



\* Task repository

\* Dependency (DAG) scheduling

\* Scheduler queue

\* Runtime state machine

\* Task runner

\* Persistent runtime state

\* End-to-end integration test



\---



\# System Architecture Overview



Core components:



1\. Task Repository

2\. DAG Scheduler

3\. Scheduler Queue

4\. Task Runner

5\. Runtime State Machine

6\. Workspace / Runtime State Persistence

7\. Integration Test



Execution flow:



```

Task Submit

&#x20;   ↓

Task Repository

&#x20;   ↓

DAG Scheduler

&#x20;   ↓

Scheduler Queue

&#x20;   ↓

Task Runner

&#x20;   ↓

Runtime State Machine

&#x20;   ↓

Finished / Retry / Failed / Replan

```



\---



\# DAG Execution Flow (Integration Test)



\## Tick #1 – Dependency Blocking



Task A finished, Task B blocked by dependency.



docs/images/dag\_runtime\_tick1\_blocked.png



\---



\## Scheduler – Dependency Unlocked → Queue



Task B moved into scheduler queue after dependency resolved.



docs/images/scheduler\_queue\_after\_unblock.png



\---



\## Tick #2 – Upstream Finished



Repository shows upstream task finished.



docs/images/dag\_repo\_tick2\_finished.png



\---



\## Tick #3 – All Tasks Finished



All tasks completed and runtime state finalized.



docs/images/dag\_repo\_tick3\_runtime\_finished.png



\---



\## Integration Tests Passed



End-to-end orchestration test passed.



docs/images/task\_os\_integration\_tests\_passed.png



\---



\# Project Structure



```

core/

&#x20;   tasks/

&#x20;       task\_repository.py

&#x20;       scheduler.py

&#x20;       task\_models.py

&#x20;       task\_workspace.py



&#x20;   runtime/

&#x20;       task\_runner.py

&#x20;       task\_runtime.py

&#x20;       runtime\_state\_machine.py

&#x20;       step\_handlers.py



services/

&#x20;   system\_boot.py



workspace/

&#x20;   tasks/<task\_id>/

&#x20;       runtime\_state.json



docs/

&#x20;   architecture.md

&#x20;   dag\_scheduler.md

&#x20;   runtime\_state\_machine.md

&#x20;   integration\_test.md

&#x20;   images/



tests/

&#x20;   test\_repo\_dag.py

&#x20;   test\_dag\_flow.py

&#x20;   test\_task\_os\_integration.py

```



\---



\# Documentation Guide



Start here:



\* docs/project\_overview.md

\* docs/architecture.md



System components:



\* docs/dag\_scheduler.md

\* docs/runtime\_state\_machine.md



Execution proof:



\* docs/integration\_test.md



Project status:



\* docs/current\_status.md

\* docs/roadmap.md



\---



\# What This Project Is



This project is NOT just a script runner.



It is an experiment toward building a \*\*local AI task operating system\*\*, where:



\* Tasks have workspace directories

\* Tasks have runtime state

\* Tasks execute multi-step plans

\* Tasks can retry or replan

\* Tasks can depend on other tasks (DAG)

\* Scheduler decides execution order

\* Runtime state persists across runs

\* Integration tests verify orchestration flow



This architecture is conceptually similar to:



\* Airflow

\* Prefect

\* Luigi

\* Temporal

\* Agent workflow runtimes



But implemented as a \*\*local-first lightweight system\*\*.



\---



\# Roadmap (High Level)



Planned next steps:



\* Planner / Step generator

\* Retry \& failure policies

\* Replan logic

\* Worker loop / scheduler loop

\* Multi-task execution

\* Event log

\* CLI interface

\* Local agent runtime

\* Tool execution framework

\* Memory / context storage



\---



\# Summary



ZERO is an experimental local task orchestration runtime that explores how AI agents, task execution, runtime state machines, and workflow scheduling can be implemented as a local-first system.



