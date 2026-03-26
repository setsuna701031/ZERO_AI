\# ZERO Architecture



ZERO is a task-oriented autonomous agent runtime.

It is designed as a "Task Operating System" rather than a chatbot.



The system focuses on task execution, failure recovery, reflection, and memory.



\---



\## High Level Architecture



User

&#x20; ↓

Planner

&#x20; ↓

Task Manager

&#x20; ↓

Task Tree

&#x20; ↓

Executor

&#x20; ↓

Failure Detection

&#x20; ↓

Retry

&#x20; ↓

Reflection

&#x20; ↓

Replan

&#x20; ↓

Recovery Execution

&#x20; ↓

Task Complete

&#x20; ↓

Memory Log

&#x20; ↓

Lessons Learned



\---



\## Core Components



\### 1. Planner

The planner converts a user goal into task steps.



Example:

Goal: Create a folder and verify it exists

Steps:

1\. Create folder

2\. Verify folder exists



\---



\### 2. Task Manager

The task manager manages:

\- Task tree

\- Task status

\- Retry count

\- Reflection count

\- Parent/child tasks

\- Replanned tasks

\- Execution history



\---



\### 3. Executor

The executor runs steps using tools.



Example tools:

\- workspace tool

\- file tool

\- command tool

\- web tool

\- memory tool



\---



\### 4. Failure Handling

If a step fails:

1\. Retry step

2\. If retry exceeds limit → mark permanent failure

3\. Trigger reflection



\---



\### 5. Reflection Engine

Reflection analyzes why the step failed and generates a recovery plan.



Example:

Original step failed → create alternative steps → continue execution



\---



\### 6. Replanner

The replanner inserts new steps into the task tree based on reflection results.



This allows the system to recover from failures automatically.



\---



\### 7. Memory System

After task execution, the system writes logs into memory:



\- Task summary

\- Failed steps

\- Recovered steps

\- Retry count

\- Reflection count

\- Lessons learned



This memory can be used for future planning.



\---



\## Execution Flow



Full execution flow:



User Goal

&#x20; ↓

Planner

&#x20; ↓

Task Tree Created

&#x20; ↓

Execute Step

&#x20; ↓

Success → Next Step

&#x20; ↓

Fail → Retry

&#x20; ↓

Retry Fail → Reflection

&#x20; ↓

Reflection → Replan

&#x20; ↓

Insert Recovery Steps

&#x20; ↓

Execute Recovery Steps

&#x20; ↓

Task Completed

&#x20; ↓

Write Memory

&#x20; ↓

Lessons Learned



\---



\## Design Philosophy



ZERO is not designed to be a chatbot.

ZERO is designed to be a task execution system.



Key ideas:



\- Tasks instead of conversations

\- Steps instead of responses

\- Execution instead of chatting

\- Failure recovery instead of stopping

\- Reflection instead of giving up

\- Memory instead of forgetting

\- Lessons instead of logs



This project explores the concept of a Task Operating System.

