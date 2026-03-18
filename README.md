\# ZERO AI



Local Tool-Driven Engineering Agent



ZERO AI is a local-first engineering assistant focused on tool execution, modular architecture, and privacy-preserving workflows.  

It is designed to run on a local machine and evolve from a simple tool-routed assistant into a more complete engineering agent system.



\---



\## Current Status



Current working version:



\- Flask API running

\- Agent Loop running

\- Router working

\- Tool Registry working

\- Local web search tool callable

\- Local SearxNG integrated

\- `/chat` can perform real search requests



This means ZERO has moved beyond a static tool skeleton and is now functioning as a real local tool-based Agent v1.



\---



\## Current Active Architecture



Current main execution path:



```text

app.py

→ agent\_loop.py

→ router.py

→ tool\_registry.py

→ tools/

→ services/



\## Main Components



\### `app.py`

Current API entry point.



Runs the Flask server and exposes routes such as:



\- `/`

\- `/health`

\- `/chat`

\- `/route`

\- `/tools`

\- `/tools/<tool\_name>`



\### `agent\_loop.py`

Current main agent execution loop.



Responsibilities:



\- receive user input

\- call router

\- dispatch tool execution

\- handle normal chat fallback

\- format final result output



\### `router.py`

Determines whether a request should go to:



\- normal chat

\- tool execution



\### `tool\_registry.py`

Registers tools and executes them by name.



\### `tools/`

Contains callable tools.



Current and planned examples include:



\- web search

\- file tools

\- terminal tools

\- project tools

\- code search tools



\### `services/`

Contains lower-level service implementations.



For example:



\- SearxNG-backed web search service



\### `config.py`

Stores project configuration.



\### `llm\_client.py`

Reserved for local LLM integration and future chat generation improvements.



\---



\## Current API Routes



\### `GET /`

Basic service info and available routes.



\### `GET /health`

Health check endpoint.



\### `POST /chat`

Main user interaction route.



Example request body:



```json

{

&#x20; "message": "查一下台北今天天氣"

}



\---



\## Project Structure



```text

zero\_ai/

├─ app.py

├─ agent\_loop.py

├─ router.py

├─ tool\_registry.py

├─ planner.py

├─ llm\_client.py

├─ config.py

├─ main.py

├─ zero.py

├─ zero\_v8.py

├─ requirements.txt

├─ README.md

├─ tools/

├─ services/

├─ core/

├─ brain/

├─ memory/

├─ schemas/

├─ utils/

├─ ui/

├─ docs/

├─ data/

└─ config/



\---



\## Example Usage



\### Health check



```bash

curl http://127.0.0.1:5000/health

