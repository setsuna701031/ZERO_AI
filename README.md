# ZERO AI

Local Tool-Driven Engineering Agent

ZERO AI is a local-first engineering assistant focused on tool execution, modular architecture, and privacy-preserving workflows.

It is designed to run on a local machine and evolve from a tool-routed assistant into a more complete engineering agent system.

---

## Current Milestone

This repository is currently at the first runtime milestone / checkpoint.

The project has completed an initial runtime execution skeleton and a repository structure reorganization.

### Current working runtime flow

User input  
→ TaskManager.create_task  
→ TaskRuntime.run_task  
→ step loop  
→ task status sync  
→ workspace artifacts  
→ CLI display

---

## Current Status

Current implemented foundation includes:

- Runtime task pipeline connected
- Agent loop skeleton available
- Router / planner / executor structure in place
- Tool registry and tool dispatch foundation available
- Local web search integration available
- Project structure reorganized into clearer modules

This is still an early-stage engineering checkpoint, not a finished autonomous agent.

---

## Repository Structure

Main repository structure currently includes:

- `config/` — configuration
- `core/` — runtime, routing, planning, execution, state handling
- `services/` — system boot and service-level integration
- `tools/` — tool implementations
- `memory/` — memory-related storage/components
- `tests/` — project tests
- `ui/` — interface assets

---

## Next Steps

Planned next-stage work:

- strengthen planner output structure
- improve runtime step execution loop
- improve task state persistence and observation flow
- connect verifier / response finalization more cleanly
- continue reducing root-level responsibility mixing

---

## Notes

ZERO AI is being developed as a local engineering agent platform, with emphasis on modularity, controllability, and safe incremental evolution.
