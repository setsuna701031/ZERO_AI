# Runtime SYSTEM Authority Enforcement Seal - apply package

Copy these files into the repository root, preserving paths.

Files included:

- `core/runtime/runtime_ownership.py`
- `docs/runtime_system_authority_audit.md`
- `docs/runtime_system_authority_enforcement.md`
- `tests/runtime_system_authority_audit.md`
- `tests/test_runtime_boundary_contract.py`
- `tests/test_runtime_mutation_bypass_proof.py`
- `tests/test_runtime_mutation_guard_contract.py`
- `tests/test_runtime_ownership_contract.py`
- `tests/test_runtime_system_authority_audit.py`
- `tests/test_runtime_system_authority_enforcement_seal.py`

Validation used:

```powershell
pytest -q tests/test_runtime_system_authority_enforcement_seal.py tests/test_runtime_system_authority_audit.py tests/test_runtime_mutation_gateway_sovereignty_seal.py tests/test_runtime_mutation_bypass_proof.py tests/test_runtime_ownership_contract.py tests/test_runtime_mutation_guard_contract.py tests/test_runtime_boundary_contract.py
python -m compileall core cli tests
git diff --check
```

Expected focused result:

```text
60 passed, 23 subtests passed
```

Non-mainline note:

The historical audit document remains at `tests/runtime_system_authority_audit.md` because it was already committed there. This package also adds the canonical docs copy at `docs/runtime_system_authority_audit.md` and the enforcement document at `docs/runtime_system_authority_enforcement.md`.
