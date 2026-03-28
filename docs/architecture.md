\# ZERO Architecture



ZERO is a local-first autonomous task runtime.



It is designed as a \*\*Task Operating System\*\* rather than a chatbot.



The system focuses on:



\- task execution

\- scheduling

\- runtime control

\- failure recovery

\- retry convergence

\- reflection and replanning

\- memory summaries



\---



\## High-Level Architecture



User  

↓  

Planner  

↓  

Task Manager  

↓  

Task Queue  

↓  

Priority Queue  

↓  

Preemptive Scheduler  

↓  

Task Runtime  

↓  

Step Executor  

↓  

Workspace State  

↓  

Success / Retry / Pause / Failure  

↓  

Reflection / Replan  

↓  

Recovery Execution  

↓  

Task Complete  

↓  

Memory Summary  

↓  

Lessons Learned



\---



\## Core Components



\## 1. Planner



The planner converts a user goal into executable task steps.



Example:



Goal: Create a folder and verify it exists



Steps:

1\. Create folder

2\. Verify folder exists



The planner is responsible for turning intent into structured execution targets.



\---



\## 2. Task Manager



The task manager manages the execution graph and task state.



It is responsible for:



\- task tree

\- task metadata

\- task status

\- retry count

\- reflection count

\- parent/child relationships

\- replanned tasks

\- execution history

\- scheduler-facing task state



\---



\## 3. Task Queue



The task queue holds runnable work items.



It provides the execution system with a controlled place to pull the next task from,

instead of treating all task steps as immediate one-shot commands.



This is one of the key shifts from "assistant" architecture to "Task OS" architecture.



\---



\## 4. Priority Queue



The priority queue determines task ordering.



This allows the system to:



\- sort urgent work ahead of lower-priority work

\- support future policy-based scheduling

\- act more like a workflow engine instead of a simple sequential runner



\---



\## 5. Preemptive Scheduler



The preemptive scheduler manages which task should run now

and when current work should pause, resume, or yield.



This layer is important because it moves ZERO toward:



\- runtime control

\- task arbitration

\- execution flow management



instead of just "run the next step in order."



\---



\## 6. Task Runtime



The runtime is the execution control layer.



It is responsible for:



\- executing steps

\- recording runtime state

\- determining success/failure

\- triggering retry logic

\- forwarding terminal results back to scheduler/task manager

\- preserving execution error information



The runtime is one of the most important parts of the current prototype.



\---



\## 7. Step Executor



The step executor actually runs task steps through tools and adapters.



Example tool families:



\- workspace tool

\- file tool

\- command tool

\- web tool

\- memory tool



Execution should remain modular so the core runtime does not become tool-specific.



\---



\## 8. Workspace State



Workspace state tracks what is currently happening around task execution.



This includes operational state such as:



\- current task execution context

\- running / paused / resumed flow

\- execution control transitions



This makes task execution more stateful and inspectable.



\---



\## 9. Failure Handling



If a step fails:



1\. Runtime marks the step failure

2\. Scheduler increments retry count

3\. If retry remains available → requeue task

4\. If retry exceeds limit → converge to permanent failure

5\. Preserve `last\_error`

6\. Prevent false success state



This retry/failure closure is a key current milestone.



\---



\## 10. Reflection Engine



Reflection analyzes why a task failed

and can generate a recovery direction.



Example:



Original step failed  

→ analyze why  

→ generate alternative steps  

→ continue execution



\---



\## 11. Replanner



The replanner inserts new recovery steps into the task tree

based on reflection results.



This allows ZERO to recover dynamically instead of stopping permanently.



\---



\## 12. Memory System



After execution, the system writes engineering-style memory summaries, such as:



\- task summary

\- failed steps

\- recovered steps

\- retry count

\- reflection count

\- lessons learned

\- next useful engineering state



This memory is intended to support future planning and system improvement.



\---



\## Execution Flow



Full execution flow:



User Goal  

↓  

Planner  

↓  

Task Tree Created  

↓  

Task Queue  

↓  

Priority Queue  

↓  

Preemptive Scheduler  

↓  

Execute Step  

↓  

Success → Next Step  

↓  

Fail → Retry  

↓  

Retry Exhausted → Permanent Failure  

↓  

Reflection  

↓  

Replan  

↓  

Insert Recovery Steps  

↓  

Execute Recovery Steps  

↓  

Task Completed  

↓  

Write Memory  

↓  

Lessons Learned



\---



\## Current Architectural Reality



At the current stage, ZERO already includes meaningful progress in:



\- task queueing

\- priority handling

\- preemptive scheduling

\- runtime control

\- retry/failure convergence

\- pause/resume behavior

\- execution-state handling



So the project is no longer accurately described as only a tool-routed assistant shell.



It is now much closer to an early workflow-engine / task-OS kernel.



\---



\## Design Philosophy



ZERO is not designed to be a chatbot.



ZERO is designed to be a task execution system.



Key ideas:



\- tasks instead of conversations

\- steps instead of responses

\- execution instead of chatting

\- scheduling instead of direct one-shot dispatch

\- recovery instead of stopping

\- reflection instead of giving up

\- memory instead of forgetting

\- lessons instead of raw logs



This project explores the concept of a reusable local-first Task Operating System core.

