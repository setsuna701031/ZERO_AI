# Runtime Mutation Sovereignty Closure - apply package

Copy these files into the repository root, preserving paths.

Files included:

```text
core/runtime/runtime_mutation_authority.py
core/runtime/runtime_mutation_gateway.py
core/runtime/governed_mutation_runtime.py
core/runtime/mutation_runtime_pipeline.py
core/runtime/mutation_patch_apply.py
docs/runtime_mutation_sovereignty_closure.md
tests/test_runtime_mutation_authority_inventory.py
tests/test_runtime_mutation_bypass_proof.py
tests/test_runtime_mutation_gateway_sovereignty_seal.py
tests/test_runtime_mutation_sovereignty_closure.py
```

Validation used:

```powershell
pytest -q tests/test_runtime_mutation_sovereignty_closure.py tests/test_runtime_mutation_authority_inventory.py tests/test_runtime_mutation_gateway_sovereignty_seal.py tests/test_runtime_mutation_bypass_proof.py tests/test_mutation_patch_apply.py
python -m compileall core cli tests
git diff --check
```

Expected focused result:

```text
26 passed
compileall passed
```

Non-mainline note:

Evidence reference ownership remains a separate distributed metadata authority surface and is not closed by this package.
```
