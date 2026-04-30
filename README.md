# ZERO AI

**Turn real changes into safe, approved actions.**

AI that doesn’t just suggest — it safely prepares real actions.

ZERO is a **local-first AI execution system** that:

- reads real inputs, such as git diff / status
- generates structured artifacts
- records full execution trace
- requires human approval
- produces a controlled execution plan

---

# 🎬 Demo (25s)

ZERO processes real git changes safely:

![demo](demos/00_git_pipeline_replay_demo.mp4)

---

# ⚡ What it actually does

```text
git diff
  ↓
analyze
  ↓
generate artifacts (commit + PR)
  ↓
replay (read-only trace)
  ↓
approval (human gate)
  ↓
execution plan (blocked by default)
```

---

# 🔐 Safety by Design

ZERO **never mutates your repo by default**:

```text
❌ no commit
❌ no push
❌ no GitHub API call
❌ no repo modification
```

Everything is:

```text
generate → inspect → approve → simulate
```

---

# 🧠 Core Idea

Most AI tools:

```text
prompt → output
```

ZERO:

```text
real state → generate → trace → approve → controlled execution
```

This is a **system**, not a chatbot.

---

## Why this matters

Most AI tools stop at generating suggestions.

ZERO goes further:

- connects to real system state
- produces structured, inspectable outputs
- enforces human approval before execution
- prevents unintended actions by default

This enables AI to move closer to real-world automation — safely.

---

# 🧩 Key Features

### 1. Replay (Audit-first)

```bash
python replay.py --task <task_id>
```

- read-only
- shows steps, artifacts, safety flags
- no execution

---

### 2. Approval Layer

```bash
python approve_outbox.py
```

- shows commit_message / PR artifacts
- displays hash + size
- requires explicit decision

Outputs:

```text
approval_record.json
rejection_record.json
```

---

### 3. Controlled Execution (Dry-Run)

```bash
python controlled_execute.py --approval workspace/github_outbox/approval_record.json
```

Output:

```text
[DRY-RUN EXECUTION PLAN]

Would execute:
- git add ...
- git commit ...
- git push ...
- create PR ...

Blocked:
- external mutation disabled
```

---

# 🚀 One-command Demo

```bash
python demo_controlled_pipeline.py
```

Flow:

```text
detect → generate → replay → approve → plan
```

Artifacts:

```text
workspace/github_outbox/commit_message.txt
workspace/github_outbox/pr_description.md
workspace/github_outbox/approval_record.json
```

---

# 📦 Project Layout

```text
core/
workspace/github_outbox/

replay.py
approve_outbox.py
controlled_execute.py
demo_controlled_pipeline.py
```

---

# 📍 Current Status

- full safe pipeline
- replayable trace
- approval audit system
- controlled execution simulation

Not yet:

```text
- real GitHub execution
- automatic commit / push
- UI layer
```

---

# 🧠 One-line Summary

ZERO is a **controlled AI execution pipeline** that turns real inputs into **approved, traceable, and safe actions**.
