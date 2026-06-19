# Runtime Mutation Sovereignty Audit

Status: read-only audit completed. No repository files were modified.

Validation run in the uploaded repo snapshot:

```text
pytest -q tests/test_runtime_mutation_governance_contract.py tests/test_runtime_mutation_guard_contract.py tests/test_runtime_ownership_contract.py
35 passed, 71 subtests passed
```

## 1. Authority graph

Current canonical mutation path is present but not sovereign:

```text
StepExecutor / RuntimeFileService
  -> governed_runtime_write_text / governed_runtime_write_bytes
  -> RuntimeMutationGateway.mutate
  -> RuntimeMutationPolicy + RuntimeAuthorityEvaluator + RuntimeCapabilityScopeEvaluator + RuntimeKernelProtection
  -> RuntimeMutationTransaction
  -> target write
```

Parallel mutation/file write surfaces still exist:

```text
GovernedMutationRuntime
mutation_runtime_pipeline
mutation_patch_apply
controlled_mutation_bridge
runtime_native_code_mutation_loop
runtime_native_git_patch_pipeline
runtime_isolation_boundary
runtime plan / health / incident / evidence registries
legacy task/tool file helpers
```

## 2. Canonical owner candidates

Recommended canonical owner split:

| Surface | Canonical owner | Current state |
|---|---|---|
| Runtime source/file mutation | RuntimeMutationGateway | Present, not sovereign |
| Compatibility file write facade | RuntimeFileService | Present, delegates to gateway |
| Mutation planning / approval / verification | GovernedMutationRuntime | Should become client, not writer |
| Patch apply / rollback copy | mutation_patch_apply | Direct writer; should become gateway client |
| Controlled source mutation | controlled_mutation_bridge | Direct writer; should become gateway client |
| Runtime state/status | TaskRuntime | Recently sealed |
| Evidence records | EvidenceAuthority / EvidenceRepository | Mostly sealed; some projection refs remain distributed |

## 3. Guarded paths already present

The following are positive signs:

- `RuntimeMutationGateway` already performs identity, authority, capability, kernel protection, policy, snapshot, side-effect registry, transaction, and lifecycle checks before committing mutation.
- `RuntimeFileService` is already a compatibility facade and delegates writes to `governed_runtime_write_text` / `governed_runtime_write_bytes`.
- `StepExecutor` has governed write helpers and routes file writes through `RuntimeFileService` in several paths.
- Existing mutation tests are green: `test_runtime_mutation_governance_contract.py`, `test_runtime_mutation_guard_contract.py`, and `test_runtime_ownership_contract.py`.

## 4. Bypass paths still present

High-risk direct writers found during audit:

| File | Direct mutation pattern |
|---|---|
| `core/runtime/governed_mutation_runtime.py` | `write_text`, `shutil.copy2` for evidence, bundles, snapshots, rollback/restore |
| `core/runtime/mutation_patch_apply.py` | `write_text`, `shutil.copy2` for plan/source/rollback/report/target writes |
| `core/runtime/controlled_mutation_bridge.py` | `write_text` for snapshots, metadata, direct restore |
| `core/runtime/mutation_runtime_pipeline.py` | direct `write_text` for result artifacts |
| `core/runtime/runtime_native_code_mutation_loop.py` | direct `target.write_text(action.content)` |
| `core/runtime/runtime_native_git_patch_pipeline.py` | direct snapshot restore `path.write_text(snapshot.content)` |
| `core/runtime/runtime_isolation_boundary.py` | direct `shutil.copy2`, direct boundary write |
| `core/runtime/runtime_mutation_gateway.py` | canonical final `target_path.write_bytes(content)`; this one should remain allowed |

Large legacy/file surfaces also still contain direct write APIs, especially `step_executor.py`, `executor.py`, `scheduler.py`, `agent_loop.py`, tool helpers, and registry/evidence emitters. Not all are source mutation, but they must be classified before enforcement becomes global.

## 5. SYSTEM wildcard authority

`core/runtime/runtime_ownership.py` still grants unrestricted access when owner is `RuntimeOwner.SYSTEM`:

```text
if runtime_owner is RuntimeOwner.SYSTEM:
    return True
```

This is the highest-risk remaining authority bypass because it is not scoped by a live issuer token, target path, capability, lifecycle, or mutation request. It should not be removed blindly; it should be replaced by a narrow bootstrap/system-maintenance path with explicit scope.

## 6. Recommended next seal

Next seal: **Runtime Mutation Gateway Sovereignty Seal**.

Dependency order:

1. Add a read-only enforcement scanner that classifies source/file mutation writers into allowed gateway/facade/legacy categories.
2. Make `RuntimeMutationGateway` the only allowed final source/file mutation committer.
3. Keep `RuntimeFileService` as the only compatibility facade; it must delegate to gateway helpers.
4. Convert `mutation_patch_apply.py` and `controlled_mutation_bridge.py` from direct writers into gateway clients first.
5. Convert `GovernedMutationRuntime` snapshot/rollback/restore writes to gateway/facade calls or explicitly mark them as non-source internal evidence writes.
6. Scope or remove `RuntimeOwner.SYSTEM` wildcard after the direct source mutation paths are under gateway control.
7. Only after that, seal task-level evidence-reference mutation ownership.

## 7. Non-mainline issues found

No unrelated functional defect was proven. Existing structural risks found:

- Several direct write surfaces are not yet under one universal mutation sovereignty contract.
- `SYSTEM` remains a wildcard authority.
- Existing ownership policy scans are useful but not yet universal enforcement for all file/source mutation paths.
