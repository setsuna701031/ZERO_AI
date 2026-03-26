\# ZERO Demo Guide



This document describes the current demo flows for ZERO.



The purpose of these demos is to demonstrate that ZERO is not just a chatbot,

but a task execution system with retry, reflection, replanning, and memory summaries.



\---



\## Demo 1 — Basic Task Execution



This demonstrates the normal task-tree execution flow.



\### Command



&#x20;   task new build a simple homepage

&#x20;   task run

&#x20;   task tree

&#x20;   memory task



\### Expected Flow



1\. A root task is created

2\. The planner generates subtasks

3\. The agent executes leaf tasks in sequence

4\. Runtime events are recorded

5\. A task summary is written to memory



\### What This Shows



\- Task creation

\- Task tree execution

\- Runtime event tracking

\- Task memory summary



\---



\## Demo 2 — Retry Recovery



This demonstrates retry behavior after a step fails once.



\### Command



&#x20;   task new fail\_first retry test

&#x20;   task run

&#x20;   runtime events

&#x20;   task tree

&#x20;   memory task



\### Expected Flow



1\. A step fails on the first attempt

2\. The retry mechanism is triggered

3\. The step succeeds on retry

4\. The task continues normally

5\. Memory records the retry history



\### What This Shows



\- Step failure detection

\- Automatic retry

\- Retry event logging

\- Memory summary including retries



\---



\## Demo 3 — Reflection + Replan Recovery



This demonstrates the full recovery loop:



retry → reflection → replan → recovery → continue



\### Command



&#x20;   task new always\_fail reflection test

&#x20;   task run

&#x20;   runtime events

&#x20;   task tree

&#x20;   memory task



\### Expected Flow



1\. A task fails repeatedly

2\. Retry attempts are exhausted

3\. Reflection is triggered

4\. Reflection generates recovery subtasks

5\. New subtasks are inserted into the task tree

6\. The recovery subtasks are executed

7\. The root task completes successfully

8\. Memory summary records retry, reflection, replanning, and lessons



\### What This Shows



\- Retry exhaustion

\- Reflection engine activation

\- Dynamic replanning

\- Task tree modification during execution

\- Recovery execution

\- Lessons recorded into memory



\---



\## What These Demos Prove



The current ZERO prototype already supports:



\- Task-tree execution

\- Runtime event logging

\- Retry mechanism

\- Reflection after repeated failures

\- Dynamic replanning

\- Recovery-step insertion

\- Memory summary with lessons



This means ZERO already behaves like a basic autonomous agent kernel,

not just a script runner.



\---



\## Current Limitations



This project is still an early-stage prototype.



Current focus:



\- Local-first agent execution

\- Task runtime behavior

\- Reflection and replanning loop

\- Memory-aware summaries

\- Agent loop architecture



Not implemented yet:



\- Long-term learning planner

\- Multi-agent cooperation

\- Distributed execution

\- Tool auto-discovery

\- UI workflow system

\- Deployment system



\---



\## Recommended Demo Order (for GitHub / Presentation)



If you want to demonstrate ZERO to others, run demos in this order:



1\. Basic Task Execution

2\. Retry Recovery

3\. Reflection + Replan Recovery



This order shows the progression from:

task runner → resilient executor → self-recovering agent



\---



\## Summary



ZERO is currently positioned as:



A local-first agent execution kernel with retry, reflection, replanning,

and memory-based task summaries.



This repository focuses on the agent execution core first,

and product / UI / deployment layers later.

