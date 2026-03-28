\# ZERO AI Project Overview



\## Project Name



ZERO AI / zero\_ai



\## Project Positioning



ZERO is a local-first AI engineering agent project.



It is no longer just a chatbot wrapper or a simple tool collection.

The project is evolving toward a \*\*Task Operating System\*\*:

a task-oriented runtime that can plan, execute, retry, recover, and record execution state.



\## Core Direction



\- local-first execution

\- modular architecture

\- task-oriented runtime instead of conversation-oriented interaction

\- execution, retry, and recovery before product polish

\- engineering-state summaries instead of raw transcript memory

\- extensible core that can later support additional skill packs and interfaces



\## Current Stage



ZERO is currently in the \*\*Task OS prototype\*\* stage.



The current core already includes:



\- task queue

\- priority queue

\- preemptive scheduling

\- task runtime

\- step execution

\- workspace state tracking

\- pause / resume behavior

\- retry / failure closure

\- CLI-driven execution flow

\- logging and runtime state transitions



This means the project has moved beyond the early API/router skeleton stage

and is now focused on the autonomous task-execution kernel.



\## What ZERO Is Becoming



ZERO is being built toward a system where the user gives a goal,

and the runtime manages the rest through task flow control.



Target direction:



User Goal  

↓  

Planner  

↓  

Task Queue / Scheduler  

↓  

Task Runtime  

↓  

Tool Execution  

↓  

Failure Detection  

↓  

Retry / Recovery  

↓  

Reflection / Replan  

↓  

Task Completion  

↓  

Memory Summary



\## Design Principles



\- local-first before cloud dependency

\- stable, understandable architecture before aggressive feature growth

\- core / policy / adapter separation

\- avoid stuffing unrelated logic into one large file

\- treat task execution as the center of the system

\- preserve reusable general architecture before adding vertical specialization

\- record important engineering milestones into local docs



\## Short-Term Focus



Current short-term focus areas:



\- improve runtime observability

\- expose task state history and event flow

\- verify both failure-path and success-path closure

\- continue stabilizing scheduler/runtime/task-state behavior

\- keep the Task OS core clean before adding more product layers



\## Longer-Term Direction



After the execution kernel is stable, future layers may include:



\- memory-aware planning

\- long-term memory

\- tool auto-selection

\- richer replanning and reflection

\- multi-worker execution

\- web UI / dashboards

\- one-click deployment

\- vertical engineering assistant capabilities

