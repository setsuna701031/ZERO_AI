# Scheduler Contract Preservation Investigation

Date: 2026-06-21

## Executive conclusion

None of the 16 investigated values is display-only text. All 16 participate in
scheduler behavior:

- 3 are `CONTRACT_KEYWORD` values.
- 7 are `ROUTING_TOKEN` values.
- 6 are `REGEX_PATTERN` values.
- 0 are `SAFE_TO_REPAIR` or `MANUAL_REVIEW` after historical evidence review.

Commit `5cf1104bd6ef860d2abdfab2b24b17d152a2bba0` introduced the corrupted
values. Its parent revision contains the exact pre-corruption values, so the
intended contracts can be identified without guessing. This report performs no
Python source modification.

## Evidence method

- Inspected each value's containing function and downstream branch.
- Located direct callers and task-record consumers with repository search.
- Used `git blame` and compared `5cf1104b` with its parent revision.
- Compared parallel implementations in `core/planning/task_replanner.py` and
  `core/system/llm_planner.py`.
- Compiled each current regex independently with Python's `re.compile`.
- Searched focused scheduler tests for direct coverage.

## Position-by-position classification

### 1. Verification marker at line 6850

- **file:** `core/tasks/scheduler.py`
- **line:** 6850
- **current value:** `"????"`
- **classification:** `ROUTING_TOKEN`
- **usage sites:** Member of `verify_markers`; consumed by the substring check
  at line 6857 in `_should_force_deterministic_task_planner()`.
- **referenced by:** `_plan_goal()` at line 6955. A match attempts
  `_plan_goal_via_forced_deterministic_planner()` before the normal external
  planner route.
- **behavioral risk:** False negatives prevent the intended localized verify
  request from taking the forced deterministic planner route. A literal string
  of question marks can also create an unintended match.
- **recommended action:** Restore the parent-revision token `確認` only in a
  dedicated behavior change with positive/negative route tests.

### 2. Verification marker at line 6852

- **file:** `core/tasks/scheduler.py`
- **line:** 6852
- **current value:** `"????"`
- **classification:** `ROUTING_TOKEN`
- **usage sites:** Same `verify_markers` substring check at line 6857.
- **referenced by:** `_plan_goal()` line 6955 and the forced deterministic
  planner path at lines 6956-6960.
- **behavioral risk:** The intended localized verification route is lost; the
  goal may reach a different planner or fallback.
- **recommended action:** Restore the parent-revision token `驗證` with route
  precedence tests. Do not treat it as a cosmetic string replacement.

### 3. Document action keyword at line 7455

- **file:** `core/tasks/scheduler.py`
- **line:** 7455
- **current value:** `"??雓◇??????"`
- **classification:** `CONTRACT_KEYWORD`
- **usage sites:** `action_keywords` in `_extract_document_task_payload()`;
  feeds `wants_action_items` at line 7466.
- **referenced by:** `_parse_goal_overrides()` line 7425; `_create_task_record()`
  lines 3968-3970 and 4055-4062; `_plan_goal()` document-planner path at
  lines 6945-6953.
- **behavioral risk:** A valid localized action-items request is not classified
  as document mode, so document metadata and planner context can be absent.
- **recommended action:** Restore the parent-revision contract keyword
  `行動項目` and add payload-mode tests.

### 4. Document action keyword at line 7456

- **file:** `core/tasks/scheduler.py`
- **line:** 7456
- **current value:** `"??蟡????????"`
- **classification:** `CONTRACT_KEYWORD`
- **usage sites:** Same `action_keywords` list and `wants_action_items` branch.
- **referenced by:** The goal-override, task-record, and document-planner chain
  described for line 7455.
- **behavioral risk:** The alternate localized action-items vocabulary no
  longer produces `mode="action_items"`.
- **recommended action:** Restore the parent-revision keyword `待辦事項` with
  a focused task payload assertion.

### 5. Document summary keyword at line 7463

- **file:** `core/tasks/scheduler.py`
- **line:** 7463
- **current value:** `"????"`
- **classification:** `CONTRACT_KEYWORD`
- **usage sites:** `summary_keywords`; feeds `wants_summary` at line 7467 and
  the summary payload returned at lines 7490 onward.
- **referenced by:** `_parse_goal_overrides()`, `_create_task_record()`, and the
  document planner path in `_plan_goal()`.
- **behavioral risk:** Localized summary requests can miss document
  classification unless an output filename independently contains `summary`.
- **recommended action:** Restore the parent-revision keyword `總結` together
  with direct mode/output-path tests.

### 6. Hello-world routing token at line 7577

- **file:** `core/tasks/scheduler.py`
- **line:** 7577
- **current value:** `"??此?????hello world python"`
- **classification:** `ROUTING_TOKEN`
- **usage sites:** Candidate substring in `_looks_like_hello_world_python()`;
  consumed at line 7584.
- **referenced by:** `_plan_goal()` line 7002; a match selects the
  `hello_world_python_multi_step` plan at lines 7003-7019.
- **behavioral risk:** The intended localized request misses the fixed
  write/run/verify plan and proceeds through another fallback.
- **recommended action:** Restore `寫一個 hello world python` from the parent
  revision with a plan-shape test.

### 7. Hello-world routing token at line 7578

- **file:** `core/tasks/scheduler.py`
- **line:** 7578
- **current value:** `"???? hello world python"`
- **classification:** `ROUTING_TOKEN`
- **usage sites:** Same candidate list and substring matcher at line 7584.
- **referenced by:** `_plan_goal()` line 7002 and its deterministic three-step
  hello-world branch.
- **behavioral risk:** The localized create request no longer selects the
  deterministic plan.
- **recommended action:** Restore `建立 hello world python` with route and
  generated-step assertions.

### 8. Hello-world routing token at line 7579

- **file:** `core/tasks/scheduler.py`
- **line:** 7579
- **current value:** `"?????hello world python"`
- **classification:** `ROUTING_TOKEN`
- **usage sites:** Same candidate list and substring matcher.
- **referenced by:** `_plan_goal()` line 7002.
- **behavioral risk:** The localized make request misses the specialized route.
- **recommended action:** Restore `做一個 hello world python` with a focused
  route test.

### 9. Hello-file routing token at line 7581

- **file:** `core/tasks/scheduler.py`
- **line:** 7581
- **current value:** `"??????????hello.py ?????hello world"`
- **classification:** `ROUTING_TOKEN`
- **usage sites:** Same `_looks_like_hello_world_python()` candidate matcher.
- **referenced by:** `_plan_goal()` line 7002 and the fixed `shared/hello.py`
  plan.
- **behavioral risk:** A localized explicit-file request loses deterministic
  plan selection.
- **recommended action:** Restore `建立一個 hello.py 印出 hello world` and
  verify path, content, run, and verify steps in a contract test.

### 10. Hello-file routing token at line 7582

- **file:** `core/tasks/scheduler.py`
- **line:** 7582
- **current value:** `"hello.py ?????hello world"`
- **classification:** `ROUTING_TOKEN`
- **usage sites:** Same candidate matcher at line 7584.
- **referenced by:** `_plan_goal()` line 7002.
- **behavioral risk:** The shorter localized explicit-file phrase misses the
  specialized three-step plan.
- **recommended action:** Restore `hello.py 印出 hello world` with the same
  deterministic plan contract test.

### 11. Write-content regex at line 7619

- **file:** `core/tasks/scheduler.py`
- **line:** 7619
- **current value:** `r"????????(.+)$"`
- **classification:** `REGEX_PATTERN`
- **usage sites:** First entry in `_extract_write_content()`; passed to
  `re.search()` at line 7631.
- **referenced by:** `_try_plan_write_file()` line 7602; `_plan_goal()` lines
  6984-6991.
- **behavioral risk:** `re.compile` fails with `nothing to repeat at position
  0`. Because this is the first pattern, every call to `_extract_write_content`
  raises before any valid English pattern can run.
- **recommended action:** Highest priority. Restore
  `r"內容是\s*(.+)$"` from the parent revision and add runtime regex and
  extraction tests.

### 12. Write-content regex at line 7620

- **file:** `core/tasks/scheduler.py`
- **line:** 7620
- **current value:** `r"????????(.+)$"`
- **classification:** `REGEX_PATTERN`
- **usage sites:** Second pattern in `_extract_write_content()`.
- **referenced by:** `_try_plan_write_file()` and the write fallback in
  `_plan_goal()`.
- **behavioral risk:** Independently fails `re.compile` with `nothing to repeat
  at position 0`; currently masked by the first pattern failing first.
- **recommended action:** Restore `r"內容為\s*(.+)$"` and test extraction.

### 13. Write-content regex at line 7621

- **file:** `core/tasks/scheduler.py`
- **line:** 7621
- **current value:** `r"????:\s*(.+)$"`
- **classification:** `REGEX_PATTERN`
- **usage sites:** Third pattern in `_extract_write_content()`.
- **referenced by:** `_try_plan_write_file()` and `_plan_goal()`.
- **behavioral risk:** Independently invalid at position 0 and cannot recognize
  the intended ASCII-colon content form.
- **recommended action:** Restore `r"內容:\s*(.+)$"` with punctuation-specific
  extraction coverage.

### 14. Write-content regex at line 7622

- **file:** `core/tasks/scheduler.py`
- **line:** 7622
- **current value:** `r"???????s*(.+)$"`
- **classification:** `REGEX_PATTERN`
- **usage sites:** Fourth pattern in `_extract_write_content()`.
- **referenced by:** `_try_plan_write_file()` and `_plan_goal()`.
- **behavioral risk:** Independently invalid at position 0. The corruption also
  destroyed both the full-width colon and the whitespace escape.
- **recommended action:** Restore `r"內容：\s*(.+)$"` and test full-width
  punctuation explicitly.

### 15. Write-content regex at line 7623

- **file:** `core/tasks/scheduler.py`
- **line:** 7623
- **current value:** `r"??此???拆????*(.+)$"`
- **classification:** `REGEX_PATTERN`
- **usage sites:** Fifth pattern in `_extract_write_content()`.
- **referenced by:** `_try_plan_write_file()` and `_plan_goal()`.
- **behavioral risk:** Independently invalid at position 0 and cannot extract
  the intended write payload.
- **recommended action:** Restore `r"寫入\s*(.+)$"` with extraction and quote
  normalization tests.

### 16. Write-content regex at line 7624

- **file:** `core/tasks/scheduler.py`
- **line:** 7624
- **current value:** `r"??????\s*(.+)$"`
- **classification:** `REGEX_PATTERN`
- **usage sites:** Sixth pattern in `_extract_write_content()`.
- **referenced by:** `_try_plan_write_file()` and `_plan_goal()`.
- **behavioral risk:** Independently invalid at position 0 and cannot extract
  the intended alternate insertion phrase.
- **recommended action:** Restore `r"放入\s*(.+)$"` with extraction coverage.

## Test coverage assessment

No focused test directly invokes the four affected private scheduler methods
with the localized contract values. Existing scheduler parser tests cover path
helpers and English examples, but do not protect these 16 tokens. The regex
failure is runtime-only and is not detected by `compileall`.

Recommended future tests should freeze:

- forced deterministic planner route precedence for localized verify goals;
- document payload `mode`, input path, and output path for each localized term;
- exact hello-world deterministic plan shape;
- successful compilation and extraction for every regex, plus valid English
  fallbacks after the localized patterns.

## Adjacent mainline findings (not part of the requested 16)

The same commit contains additional scheduler contract changes that the prior
four-question-mark/private-use scan did not count:

- Line 7462 is `"???"`; the parent value is `"摘要"`.
- Line 7576 is `"hello world ??python"`; the parent value is
  `"hello world 的 python"`.
- Lines 7593-7594 no longer contain the parent revision's localized write
  intent tokens (`寫`, `建立`, `新增`). This is semantic loss rather than a
  visibly corrupted literal and can prevent localized requests from reaching
  `_extract_write_content()` at all.

These require inclusion in any future scheduler contract repair scope.

## Validation

- `python -m compileall core`: PASS (exit 0)
- `python -m compileall tests`: PASS (exit 0)

## Non-Mainline Issue Report

### Parallel implementation drift

- `core/planning/task_replanner.py` lines 817-827 retains clean hello-world
  localized candidates, but only a subset of the scheduler's historical list.
- `core/system/llm_planner.py` lines 791-805 retains valid localized
  write-content regexes. Its vocabulary differs slightly (`內容放`, `寫成`)
  from the scheduler's parent contract (`寫入`, `放入`).

The duplicate parsers can drift independently. A future repair should decide
whether these are intentionally surface-specific contracts or should share a
single tested vocabulary source.

### Historical inventory snapshots

The previous repository-wide audit found stale corrupted scheduler excerpts in
generated or historical inventory files under:

- `docs/architecture/runtime_compatibility_inventory/`
- `docs/architecture/runtime_native_ownership/`

They are not executable and were not modified. If scheduler source is repaired,
these snapshots should be regenerated by their owning workflow rather than
edited by hand.

### Tests

No corrupted test literal was found for these 16 values, but there is no direct
regression coverage for the affected localized scheduler contracts. This is a
coverage issue, not a compile failure.
