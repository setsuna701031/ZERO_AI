# Scheduler Contract Restoration Report

Date: 2026-06-21

## Scope

This restoration changes only the 16 contract values classified in
`scheduler_contract_preservation_report.md`:

- 3 contract keywords
- 7 routing tokens
- 6 regex patterns

No surrounding branch, function, planner order, return shape, or parser logic
was changed.

## Source evidence

- Corruption-introducing commit:
  `5cf1104bd6ef860d2abdfab2b24b17d152a2bba0`
- Evidence revision requested by the investigation (`5cf1104b^`):
  `7d791c5cf836841fab5de220141e7fa1938f396e`
- Evidence path: `core/tasks/scheduler.py` at the parent revision.

The restored values were copied from the corresponding lists in the parent
revision. No localized token or regex was inferred or reconstructed.
An AST-based equality check compared every restored value with its exact parent
counterpart and passed for all 16 items.

## Restored contracts

| Current value before restoration | Restored value | Source commit | Evidence |
|---|---|---|---|
| `"??雓◇??????"` | `"行動項目"` | `7d791c5c` | Parent `_extract_document_task_payload.action_keywords[5]` |
| `"??蟡????????"` | `"待辦事項"` | `7d791c5c` | Parent `_extract_document_task_payload.action_keywords[6]` |
| `"????"` | `"總結"` | `7d791c5c` | Parent `_extract_document_task_payload.summary_keywords[4]` |

These values control construction of document task payloads and selection of
`action_items` or `summary` mode.

## Restored routing tokens

| Current value before restoration | Restored value | Source commit | Evidence |
|---|---|---|---|
| `"????"` | `"確認"` | `7d791c5c` | Parent `_should_force_deterministic_task_planner.verify_markers[11]` |
| `"????"` | `"驗證"` | `7d791c5c` | Parent `_should_force_deterministic_task_planner.verify_markers[13]` |
| `"??此?????hello world python"` | `"寫一個 hello world python"` | `7d791c5c` | Parent `_looks_like_hello_world_python.candidates[2]` |
| `"???? hello world python"` | `"建立 hello world python"` | `7d791c5c` | Parent `_looks_like_hello_world_python.candidates[3]` |
| `"?????hello world python"` | `"做一個 hello world python"` | `7d791c5c` | Parent `_looks_like_hello_world_python.candidates[4]` |
| `"??????????hello.py ?????hello world"` | `"建立一個 hello.py 印出 hello world"` | `7d791c5c` | Parent `_looks_like_hello_world_python.candidates[6]` |
| `"hello.py ?????hello world"` | `"hello.py 印出 hello world"` | `7d791c5c` | Parent `_looks_like_hello_world_python.candidates[7]` |

The verification tokens control forced deterministic planner selection. The
hello-world tokens control the deterministic write/run/verify plan route.

## Restored regex patterns

| Current value before restoration | Restored value | Source commit | Evidence |
|---|---|---|---|
| `r"????????(.+)$"` | `r"內容是\s*(.+)$"` | `7d791c5c` | Parent `_extract_write_content.patterns[0]` |
| `r"????????(.+)$"` | `r"內容為\s*(.+)$"` | `7d791c5c` | Parent `_extract_write_content.patterns[1]` |
| `r"????:\s*(.+)$"` | `r"內容:\s*(.+)$"` | `7d791c5c` | Parent `_extract_write_content.patterns[2]` |
| `r"???????s*(.+)$"` | `r"內容：\s*(.+)$"` | `7d791c5c` | Parent `_extract_write_content.patterns[3]` |
| `r"??此???拆????*(.+)$"` | `r"寫入\s*(.+)$"` | `7d791c5c` | Parent `_extract_write_content.patterns[4]` |
| `r"??????\s*(.+)$"` | `r"放入\s*(.+)$"` | `7d791c5c` | Parent `_extract_write_content.patterns[5]` |

All six restored patterns are byte-for-byte equivalent at the Python string
value level to the parent revision. The restoration did not manually synthesize
regex syntax.

## Validation evidence

### Parent equality validation

- Parsed the current and parent scheduler source with `ast`.
- Compared the exact selected list indices.
- Result: `parent equality validation: PASS (16)`.

### Regex compilation

- Extracted the first six `_extract_write_content.patterns` values from the
  current source with `ast.literal_eval`.
- Ran `re.compile` on each value.
- Result: `re.compile validation: PASS (6)`.

### Matcher validation

- Forced deterministic verify routing: PASS (2 restored inputs).
- Document contract matching: PASS (3 restored inputs and expected modes).
- Hello-world deterministic routing: PASS (5 restored inputs).
- Combined result: all 10 restored keyword/token matchers passed.

The validation harness used ASCII-only Python source with Unicode escapes so
PowerShell console encoding could not alter test inputs.

### Write-content parser validation

Called `Scheduler._extract_write_content()` with one input for each restored
pattern and asserted `explicit is True` plus exact extracted content:

- `內容是 alpha` -> `alpha`
- `內容為 beta` -> `beta`
- `內容: gamma` -> `gamma`
- `內容： delta` -> `delta`
- `寫入 epsilon` -> `epsilon`
- `放入 zeta` -> `zeta`

Result: `write-content parser validation: PASS (6)`.

### Compile validation

- `python -m compileall core`: PASS (exit 0)
- `python -m compileall tests`: PASS (exit 0)

## Files changed for this restoration

- `core/tasks/scheduler.py`
- `docs/architecture/scheduler_contract_restoration_report.md`

## Non-Mainline Issue Report

### Explicitly excluded adjacent scheduler values

The preservation investigation identified adjacent values that were not part of
the requested 3/7/6 restoration set. They remain unchanged:

- `summary_keywords` contains `"???"` where the same parent revision contains
  `"摘要"`.
- `candidates` contains `"hello world ??python"` where the parent contains
  `"hello world 的 python"`.
- The localized write-intent gate differs semantically from the parent revision.

These require a separately authorized scope because changing them would exceed
the enumerated 16 contracts restored here.

### Parallel parser implementations

- `core/planning/task_replanner.py` has a separate hello-world vocabulary.
- `core/system/llm_planner.py` has a separate write-content regex vocabulary.

They were not modified. Their contracts should eventually be tested for
intentional divergence or consolidated under a shared vocabulary owner.

### Historical inventory snapshots

Generated or historical inventory JSON under
`docs/architecture/runtime_compatibility_inventory/` and
`docs/architecture/runtime_native_ownership/` still contains stale corrupted
scheduler excerpts. These non-executable snapshots were not edited and should
be regenerated through their owning workflow.
