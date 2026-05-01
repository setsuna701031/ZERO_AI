# ZERO

ZERO is a local AI runtime that turns a task into an executable, traceable workflow.

It is not just a chatbot, and it is not a loose script runner.

ZERO does not just generate answers.

It executes real steps, produces real outputs, and shows exactly how the result was created.

ZERO breaks a request into steps, runs tools such as `file_read`, `file_write`, `web_search`, and `github_commit`, then records the full execution trace so the UI can show what actually happened.

The point is simple: make AI work observable.

Users can see:

- what the system planned
- which tools ran
- what arguments were used
- whether each step succeeded or was blocked
- the final result
- the trace that can be replayed later

## Demo

Main demo video (Search → Execution → Commit):

`demos/00_zero_hybrid_search_to_commit.mp4`

This demo shows ZERO taking external information and turning it into real system output.

1. search external data
2. generate a summary
3. write the result to a file
4. commit the result locally
5. display the full execution trace in the UI

## What The Demo Shows

The standard demo shows ZERO doing real work from start to finish:

1. Receive a task
2. Plan the workflow
3. Execute tools
4. Generate a result
5. Commit the result locally
6. Display the full timeline in the Persona UI

The focus is not the final file. The focus is that the process is visible.

## Standard Demo Flow

The Persona UI demo runs a fixed workflow:

1. `web_search` searches for external information
2. `file_write` creates `workspace/shared/search_summary.txt`
3. `github_commit` commits the summary into a local demo repo

This demo does not push, open a pull request, or call the GitHub API. The GitHub tool currently uses local Git only.

## Timeline View

The UI displays the task as a timeline:

1. `Step 1: web_search`
2. `Step 2: file_write`
3. `Step 3: github_commit`
4. `Result`

Each tool call is shown in order with:

- tool name
- simplified args summary
- status, such as `success` or `blocked`
- timestamp

These states come from ZERO runtime data: `execution_trace` and `execution_log`. They are not fake UI states.

## Trace And Replay

ZERO records what happened during execution.

The Persona runtime bridge turns that trace into a UI-friendly timeline and result summary.

`runtime-replay` shows the previous task trace again without running the tools again. It does not rewrite files and does not create another commit.

Replay is for answering one question:

> What did the AI actually do?

## Run The Demo

In the Persona UI, press `Demo`, or type:

```text
run hybrid-demo
```

Show the latest runtime state:

```text
runtime-status
```

Replay the previous task trace:

```text
runtime-replay
```

Run the smoke tests:

```bash
python tests/run_hybrid_demo_smoke.py
python tests/run_persona_runtime_bridge_smoke.py
```

## Current Scope

ZERO currently focuses on local, inspectable engineering workflows:

- tool call execution
- web search adapter
- trace and execution logs
- Persona UI task visualization
- local Git commit demo
- replayable task history

Not included:

- voice
- TTS
- 3D avatar
- Live2D
- push
- pull requests
- GitHub API calls
- browser automation

## Why This Matters

Most AI tools hide the execution path.

ZERO exposes it.

That makes the system easier to debug, easier to trust, and easier to demonstrate.
