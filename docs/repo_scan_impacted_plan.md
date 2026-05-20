# Repo Scan / Impacted File Plan

Date: 2026-05-20

This document defines the first production-facing interactive engineering workflow surface: a read-only repository scan and impacted file plan contract.

## Purpose

The repo scan / impacted file plan layer gives the engineering workflow a safe first step:

```text
user task
 -> repo scan
 -> impacted file analysis
```

It helps identify candidate files for later review, diff planning, and verification planning. It does not apply patches, write files, run commands, approve mutations, or execute autonomous self-edit.

## Read-Only Guarantee

`core.engineering.repo_scan` is read-only by contract.

It may:

- scan a repository root;
- skip ignored directories such as `.git`, `__pycache__`, `.venv`, `venv`, `node_modules`, `build`, `dist`, and cache artifacts;
- list candidate files;
- classify files as `source`, `test`, `docs`, `config`, or `other`;
- build a conservative impacted file plan from task/path keywords;
- emit stable ids and planning metadata.

It must always mark scan and plan metadata with:

- `read_only=True`;
- `mutation_allowed=False`;
- `execution_allowed=False`;
- `patch_apply_allowed=False`;
- `autonomous_execution_allowed=False`.

## Connection To The Interactive Engineering Loop

The impacted file plan is a planning artifact for the interactive engineering loop.

It can feed:

- execution plan drafting;
- diff proposal preparation;
- approval review;
- verification profile selection;
- operator-facing summaries.

It cannot count as engineering loop success. Canonical engineering loop success still requires approval lineage, governed mutation lineage, runtime evidence, audit metadata, verification, rollback/recovery eligibility, and a final execution summary.

## Non-Goals

This layer does not:

- enable patch apply;
- modify files;
- call the mutation runtime pipeline;
- create repair transactions;
- run shell commands;
- call scheduler internals;
- modify `system_boot.py`;
- emit runtime evidence;
- claim approval or execution authority;
- implement autonomous editing.

## Future Extension Path Toward Diff Planning

Future work may add:

- richer content-aware read-only scanning;
- ownership and risk tagging;
- verification command suggestions;
- stable diff proposal records;
- approval request records;
- a wrapper that converts an approved diff into a governed repair transaction.

Any future diff or mutation step must continue through the governed repair / mutation / runtime spine and must preserve the existing freeze, topology, self-edit, patch/diff, and interactive loop contracts.
