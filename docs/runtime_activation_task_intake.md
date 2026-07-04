# Runtime Activation Task Intent Intake

This document records the first task-facing activation layer.

## Purpose

The task intent intake layer accepts task-like input, normalizes intent metadata, attaches activation preflight evidence, and forwards only to the executor noop admission path.

## Guardrails

- minimal implementation only
- no task execution
- no task creation
- no queue write
- no scheduler execution
- no scheduler call
- no executor execution
- no executor call
- no tool execution
- no mutation
- no repo or file mutation
- no runtime state mutation

## Allowed Flow

task-like intent
  -> task intake preflight
  -> executor noop admission path
  -> deterministic blocked result

## Forbidden Flow

task intake preflight
  -> task creation forbidden
  -> queue write forbidden
  -> scheduler execution forbidden
  -> executor execution forbidden
  -> mutation forbidden

## Final State

ZERO can receive task intent safely, but scheduling, execution, tools, and mutation remain disabled.
