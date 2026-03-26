# ZERO - Task Operating System

ZERO is an experimental task-oriented autonomous agent runtime.

It is not just a chatbot.
It is a system that can plan tasks, execute steps, detect failures, retry, reflect, replan, recover, and store lessons in memory.

The idea is to explore a "Task Operating System" architecture.

---

## What ZERO can do

ZERO can:

- Create tasks
- Build a task tree
- Execute steps
- Retry failed steps
- Detect permanent failures
- Trigger reflection
- Generate recovery plans
- Replan tasks
- Execute recovery steps
- Complete tasks
- Write execution history into memory
- Record lessons learned

Execution flow looks like this:

User → Planner → Task Tree → Executor → Failure → Retry → Reflection → Replan → Recovery → Success → Memory

---

## Demo

Reflection and recovery demo:

See demo document:
docs/demo.md

This demo shows:

- Step failure
- Retry logic
- Reflection
- Replanning
- Recovery execution
- Task completion
- Memory logging
- Lessons learned

---

## Project Structure

zero_ai/
core/        core runtime, planner, agent loop, task system
tools/       tools used by the agent
docs/        documentation and demos
images/      screenshots for demo and README
tests/       test scripts
app.py       main entry point

---

## Why this project

Most AI systems today are chat-based.
They answer questions but do not manage tasks.

This project explores a different direction:
AI should manage tasks, recover from errors, and learn from execution history.

Instead of a Chat AI,
this project explores a Task Operating System.

---

## Roadmap

Planned future work:

- Memory-aware planning
- Long-term memory
- Tool auto selection
- Multi-step planning
- Multi-agent workers
- Persistent task sessions
- Web interface
- One-click deployment

---

## Long-term Goal

The long-term goal of ZERO is to become a personal autonomous engineering assistant.

The user gives a goal,
and the system helps plan, execute, recover from errors, and complete the task.