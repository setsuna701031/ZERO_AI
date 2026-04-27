# ZERO AI

A local-first AI engineering agent that turns requirements into executable results.

**Requirement → Planning → Code → Execution → Verification**

ZERO is not a chatbot.  
It is a system that builds and runs solutions.

---

## ✅ Current Engineering Checkpoint

ZERO's current mainline has a runtime-safe multi-task execution baseline.

Validated mainline capabilities now include:

- normalized handler results
- observable local traces with `step_start`, `step_result`, and `task_finished`
- task-local trace ticks for cleaner inspection
- queue readiness rules that prevent `created` tasks from running before submit
- multi-task queue progression without failed/replanning tasks blocking normal tasks
- runtime artifact safety guards to prevent oversized `runtime_state.json` / `result.json` growth
- command safety guard against self-invoking task commands such as `python app.py task run ...`

Latest regression proof:

```bash
python app.py task create "write MAIN_SAFE_OK to main_safe_ok.txt, then verify main_safe_ok.txt contains MAIN_SAFE_OK"
python app.py task submit <task_id>
python app.py task run 1
python app.py task run 1
python app.py task run 1
python app.py task show <task_id>
```

Confirmed result:

- task reached `finished`
- step progress reached `3/3`
- final answer: `MAIN_SAFE_OK`

---

## 🔧 Core Showcase

### 🚀 Mini Build Agent (Primary Demo)

```bash
python main.py mini-build-demo
```

This demo shows a complete engineering loop:

- read a requirement document  
- generate planning outputs  
- generate Python code  
- execute the generated script  
- write result artifacts  
- verify the final output  

### 📦 Output Artifacts

- workspace/shared/project_summary.txt  
- workspace/shared/implementation_plan.txt  
- workspace/shared/acceptance_checklist.txt  
- workspace/shared/number_stats.py  
- workspace/shared/stats_result.txt  

### ✅ What this proves

- not just text generation  
- real file outputs  
- code generation + execution  
- result verification  

📂 Demo assets:  
demos/08_mini_build_demo/

---

## 📦 Additional Demo

### Requirement Demo

```bash
python main.py requirement-demo
```

Demonstrates:

- requirement input  
- planning output  
- multi-artifact generation  
- result inspection  

### Output Artifacts

- workspace/shared/project_summary.txt  
- workspace/shared/implementation_plan.txt  
- workspace/shared/acceptance_checklist.txt  

📂 Demo assets:  
demos/07_requirement_demo/


---

## 🖥️ Persona Runtime Window

ZERO also includes a local Persona Runtime window for showing runtime state through a visual UI.

This window is not only a character display. It shows:

- current runtime state
- command/chat interaction
- execution-demo result
- task artifact paths
- runtime summary and output hints

### Visual Ready

![Persona Runtime visual ready](docs/demo_assets/persona_runtime/persona_runtime_v1_visual_ready.png)

### Execution Demo Success

![Persona Runtime execution demo success](docs/demo_assets/persona_runtime/persona_runtime_v2_execution_demo_success.png)

### What this proves

- the UI is connected to runtime state
- execution-demo can update the persona status to SUCCESS
- output artifacts such as `workspace/shared/hello.py` are surfaced in the UI
- task IDs and execution traces are visible for inspection

---

## ⚙️ Capabilities

- Requirement understanding  
- Planning system (planning pack)  
- Code generation  
- Tool execution  
- Output verification  
- Task lifecycle control  
- Controlled AgentLoop observe-decide-act loop  
- Safe loop execution through `task loop <task_id> [max_cycles]`  
- Artifact visibility  

---

## 🧠 What makes this different

This is not an LLM wrapper.

ZERO:

- executes tasks, not just responds  
- produces real artifacts (code, files)  
- exposes runtime state  
- verifies outputs through execution  

It demonstrates a **complete engineering agent loop**.

---

## 🚀 Quick Start

### Show help
```bash
python main.py help
```

### Check runtime
```bash
python main.py runtime
```

### Run validation
```bash
python main.py smoke
```

### Run demos
```bash
python main.py doc-demo
python main.py requirement-demo
python main.py execution-demo
python main.py mini-build-demo
```

---

## 🧱 Core CLI

```bash
python app.py runtime
python app.py health
python app.py task list
python app.py task show <task_id>
python app.py task result <task_id>
python app.py task loop <task_id> [max_cycles]
```

### Document tasks

```bash
python app.py task doc-summary input.txt summary.txt
python app.py task doc-action-items input.txt action_items.txt
```

---

## 🔁 Controlled AgentLoop Loop

ZERO now includes a controlled minimal AgentLoop path:

```bash
python app.py task loop <task_id> [max_cycles]
```

This path is intentionally explicit. It does not replace the default scheduler or `task run` behavior.

It supports a safe observe-decide-act cycle:

- observe current task/runtime result
- decide whether to finish, continue, replan, fail, or stop on guard/block conditions
- run the next tick only when the decision is `continue`
- stop safely on `finish`, `replan`, `fail`, `blocked`, or `max_cycles_reached`

### What this proves

- AgentLoop can now record observe/decide metadata
- task loop execution can run until terminal state under a max-cycle guard
- CLI access is controlled through an explicit command
- default task execution remains unchanged

---

---

## 🔁 Multi-task Demo

ZERO now includes a repeatable multi-task demo scenario:

```bash
python tests/run_multi_task_demo_smoke.py
```

This demo creates three tasks:

- one normal task that writes and verifies `MULTI_DEMO_A`
- one normal task that writes and verifies `MULTI_DEMO_B`
- one intentionally failing verification task

The expected result is that the two normal tasks finish successfully while the intentional failure moves into a safe repair state without blocking the queue.

![Multi-task demo smoke all pass](docs/images/checkpoints/checkpoint_multi_task_demo_smoke_all_pass.png)

### What this proves

- multiple tasks can be queued and advanced together
- normal tasks can finish even when another task fails or replans
- each task has observable trace evidence
- the demo is repeatable through smoke validation

Engineering proof for the queue policy is also kept here:

![Queue policy failure does not block](docs/images/checkpoints/checkpoint_queue_policy_failure_does_not_block.png)

## 🏗️ System Structure

- main.py → unified entrypoint  
- app.py → core CLI  
- core/planning/ → planner  
- core/runtime/ → execution layer  
- core/tasks/ → scheduler + lifecycle  
- tests/ → validation  
- demos/ → showcase assets  
- docs/ → devlog + checkpoints  

---

## 📊 Current Position

ZERO is:

- local-first  
- execution-oriented  
- artifact-producing  
- inspectable  
- reproducible  

Not optimized yet for:

- polished UI  
- one-click install  
- mass users  

---

## 📌 One-line Summary

ZERO is a local-first engineering agent that can turn requirements into executable, verifiable results through a controllable task system.
