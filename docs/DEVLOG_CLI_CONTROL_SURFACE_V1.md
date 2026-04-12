# ZERO Devlog — CLI Control Surface v1

## Milestone
ZERO CLI Control Surface v1

## Completed in this round
- unified model/plugin override path from CLI into system boot
- added dual-mode CLI:
  - interactive mode
  - one-shot command mode
- added runtime / health inspection commands
- added task lifecycle commands:
  - list
  - show
  - result
  - open
  - delete
  - purge
- improved task result visibility in CLI
- recorded working demo for runtime + task flow

## Verified
- `python app.py runtime`
- `python app.py chat "你好"`
- `python app.py ask "幫我建立一個 demo.txt，內容是 demo test，然後再讀出來" --model llama3.1:latest`
- `python app.py task list`
- `python app.py task result <task_id>`

## Current state
The project now has a usable CLI control surface for local task execution and runtime inspection.

## Next likely direction
- keep CLI stable
- avoid deep scheduler refactors for now
- continue building outward-facing control and inspection features
