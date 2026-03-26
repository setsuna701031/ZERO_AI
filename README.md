# ZERO — Local Tool-Driven Engineering Agent

ZERO is a local-first engineering agent designed to execute tasks, call tools,
recover from failures, and learn from execution history.

It is not just a chatbot.
ZERO is an agent execution system focused on tool usage, task execution,
retry, reflection, replanning, and memory-driven summaries.

The goal of this project is to evolve ZERO from a simple tool-routed assistant
into a local autonomous engineering agent.


------------------------------------------------------------
Features
------------------------------------------------------------

Current capabilities:

- Local-first architecture
- Tool routing system
- Agent execution loop
- Task tree execution
- Retry mechanism
- Reflection after repeated failures
- Replanning and recovery steps
- Memory summaries and lessons
- Local web search (SearxNG)
- Flask API interface

ZERO already behaves like a basic autonomous agent kernel,
not just a script runner or chatbot.


------------------------------------------------------------
Architecture Overview
------------------------------------------------------------

High-level execution flow:

User Request
    ↓
Flask API (app.py)
    ↓
Agent Loop
    ↓
Router
    ↓
Tool Registry
    ↓
Tools / Services
    ↓
Task Execution
    ↓
Retry / Reflection / Replan
    ↓
Memory Summary


Core execution idea:

Plan → Execute → Fail → Retry → Reflect → Replan → Continue → Summarize → Learn

This loop is the core of ZERO.


------------------------------------------------------------
Core Modules
------------------------------------------------------------

app.py
    Flask API entry point.

agent_loop.py
    Main agent execution loop.

router.py
    Determines whether a request should go to chat or tools.

tool_registry.py
    Registers tools and executes them.

tools/
    Callable tools such as web search, file tools, terminal tools.

services/
    Lower-level service implementations such as SearxNG web search.

core/
    Agent kernel modules:
    - task manager
    - task runtime
    - planner
    - reflection engine
    - replanner
    - memory manager
    - step executor

memory/
    Stores task summaries, lessons, and execution history.


------------------------------------------------------------
Quick Start
------------------------------------------------------------

Start the server:

python app.py

Health check:

http://127.0.0.1:5000/health

Chat endpoint example:

POST /chat
{
  "message": "search latest AI news"
}


------------------------------------------------------------
Demo
------------------------------------------------------------

See:

docs/demo.md

Recommended demo order:

1. Basic Task Execution
2. Retry Recovery
3. Reflection + Replan Recovery


------------------------------------------------------------
Project Structure
------------------------------------------------------------

zero_ai/
├─ app.py
├─ agent_loop.py
├─ router.py
├─ tool_registry.py
├─ requirements.txt
├─ README.md
├─ LICENSE
├─ core/
├─ tools/
├─ services/
├─ memory/
├─ schemas/
├─ utils/
├─ ui/
├─ docs/
├─ data/
├─ workspace/
└─ logs/


------------------------------------------------------------
Current Status
------------------------------------------------------------

Current version includes:

- Flask API
- Agent loop
- Router
- Tool registry
- Local web search
- Task execution system
- Retry mechanism
- Reflection system
- Replanning system
- Memory summaries

ZERO is currently in early prototype stage,
focused on building the agent execution core.


------------------------------------------------------------
Roadmap
------------------------------------------------------------

Planned future directions:

- Memory-aware planning
- Lesson-guided task decomposition
- Multi-task scheduling
- Multi-agent cooperation
- Tool auto-discovery
- Local model integration
- UI workflow interface
- One-click deployment
- Distributed execution


------------------------------------------------------------
Design Philosophy
------------------------------------------------------------

ZERO follows these principles:

- Local-first
- Tool-driven
- Modular architecture
- Recoverable execution
- Memory-driven improvement
- Engineering-oriented agent
- Not cloud-dependent
- Not chatbot-first

ZERO is designed as an engineering agent,
not a conversational assistant.


------------------------------------------------------------
License
------------------------------------------------------------

This project is licensed under the MIT License.