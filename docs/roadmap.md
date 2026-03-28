\# ZERO Roadmap



This document describes the development roadmap of the ZERO Task Operating System.



\---



\## Stage 1 – Basic Task Execution

Status: Completed



\- task creation

\- task tree

\- step execution

\- tool calling

\- step result recording

\- task completion



\---



\## Stage 2 – Retry System

Status: Completed



\- step retry

\- retry limit

\- retry counter

\- failure detection

\- permanent failure detection

\- final failure convergence



\---



\## Stage 3 – Scheduler / Task OS Foundations

Status: In Progress



\- task queue

\- priority queue

\- preemptive scheduling

\- task runtime

\- workspace state

\- pause / resume behavior

\- CLI-driven execution control



\### Current Note



This stage has already reached a meaningful prototype level.

The retry/failure closure and scheduler flow are now working milestone pieces,

but runtime observability and cleaner state history exposure are still being improved.



\---



\## Stage 4 – Reflection and Replanning

Status: Partial / In Progress



\- reflection triggered after terminal failure conditions

\- reflection generates recovery direction

\- replanner inserts recovery steps

\- recovery execution continues task flow



\### Current Note



Reflection/replan direction exists in project design

and parts of the architecture have already been shaped around it,

but this path still needs cleaner structured validation as the scheduler/runtime core stabilizes.



\---



\## Stage 5 – Memory Logging

Status: In Progress



\- task summary

\- failed-step summary

\- recovered-step summary

\- retry statistics

\- reflection statistics

\- lessons learned



\### Current Note



Memory remains part of the architecture direction,

but the current engineering priority is still execution-core stability.



\---



\## Stage 6 – Runtime Observability

Status: Immediate Next Focus



\- task event history

\- queue/runtime transition visibility

\- success-path closure verification

\- failure-path timeline visibility

\- inspectable task execution traces



\---



\## Stage 7 – Memory-Aware Planning

Status: Planned



\- planner reads memory before planning

\- avoid repeating previous failures

\- use past successful recovery strategies

\- improve planning based on history



\---



\## Stage 8 – Long-Term Memory

Status: Planned



\- store memory to database

\- memory retrieval

\- task history search

\- lessons database



\---



\## Stage 9 – Tool Auto Selection

Status: Planned



\- automatically choose tools

\- tool capability description

\- tool selection logic

\- multi-tool workflow



\---



\## Stage 10 – Multi-Step Planning

Status: Planned



\- planner generates multi-step plans

\- dependency between steps

\- conditional execution

\- loop tasks



\---



\## Stage 11 – Multi-Agent Workers

Status: Planned



\- worker agents

\- task delegation

\- parallel execution

\- result aggregation



\---



\## Stage 12 – Web Interface

Status: Planned



\- web UI

\- task dashboard

\- task tree visualization

\- memory viewer



\---



\## Stage 13 – One-Click Deployment

Status: Planned



\- install script

\- start script

\- Docker deployment

\- server deployment



\---



\## Long-Term Vision



ZERO is designed to become a Task Operating System.



Instead of interacting with AI through conversation,

users interact with AI through tasks.



The system should:



\- plan tasks

\- queue and schedule work

\- execute steps

\- recover from failures

\- learn from execution history

\- improve over time

