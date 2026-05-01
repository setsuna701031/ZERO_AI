# ZERO AI

**Turn real changes into safe, approved actions.**

AI that doesn't just suggest --- it safely prepares real actions.

ZERO is a **local-first AI execution system** that:

-   reads real inputs (git diff / status)
-   generates structured artifacts (commit + PR)
-   records full execution trace
-   requires human approval
-   produces a controlled execution plan

------------------------------------------------------------------------

# 🎬 Demo (MVP)

Run:

``` bash
python zero_demo.py
```

Demo video:

![demo](demos/zero_demo_mvp.mp4)

------------------------------------------------------------------------

# ⚡ What it actually does

``` text
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

------------------------------------------------------------------------

# 🔐 Safety by Design

ZERO **never mutates your repo by default**:

``` text
❌ no commit
❌ no push
❌ no GitHub API call
❌ no repo modification
```

Everything is:

``` text
generate → inspect → approve → simulate
```

------------------------------------------------------------------------

# 🧠 One-line Summary

ZERO is a **controlled AI execution pipeline** that turns real inputs
into\
**approved, traceable, and safe actions**.
