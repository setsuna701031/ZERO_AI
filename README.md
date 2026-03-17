ZERO AI

Autonomous Engineering Agent (Local AI System)

ZERO is a local-first autonomous engineering assistant designed to help users complete engineering tasks such as coding, file operations, and tool execution using local large language models.

The system focuses on local privacy, tool execution, and modular AI architecture, allowing an AI agent to plan tasks and interact with real system tools.

Core Philosophy

ZERO is designed around three principles:

Local First – Runs entirely on local LLMs (Ollama)

Engineering Workflow – AI assists real engineering tasks

Tool-Driven Execution – AI interacts with system tools instead of only chatting

Current System Architecture
User
  ↓
Router
  ↓
Tool Router
  ↓
Tool Execution
  ↓
Workspace (Sandbox)
Components

Router

Determines how user input should be processed.

Example routes:

help

tools

memory

tool execution

normal chat

Tool Router

Maps commands to actual system tools.

Example:

echo hello
list files
read file example.txt
run python script.py

Tools

Tools are executable system capabilities.

Examples:

read_file
write_file
list_files
run_python

Each tool is implemented as a Python module.

Workspace

All file operations are restricted to:

zero_workspace/

This acts as a sandbox environment for the AI system.

Project Structure
zero_ai/

core/
    router.py
    tool_router.py
    executor.py

tools/
    read_file.py
    write_file.py
    list_files.py
    run_python.py

workspace/
    zero_workspace/

app.py
Installation

Clone the repository

git clone https://github.com/yourname/zero-ai
cd zero-ai

Install Python dependencies

pip install -r requirements.txt

Install local model (Ollama)

ollama pull qwen2.5
Run the system

Start the API server

python app.py

Then send requests to:

http://127.0.0.1:5000
Example Commands

Example interaction:

User input

echo hello world

System response

hello world

Another example:

list files

Returns file list from the workspace.

Roadmap

Planned system evolution:

Phase 1 (Current)

Router
Tool system
Execution engine
Sandbox workspace

Phase 2

Agent Loop

plan → tool → execute → observe → repeat

The AI will be able to plan multi-step engineering tasks.

Phase 3

Memory system
Web crawler tools
Self-repair capability

Phase 4

Vision system
Hardware control
Autonomous engineering workflows

Long Term Vision

ZERO aims to become a personal engineering AI assistant capable of helping with:

software development

hardware prototyping

automation workflows

engineering research

while remaining fully local and privacy-preserving.

License

MIT License
