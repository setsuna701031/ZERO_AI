# ZERO Work Package Constitution v1

## Core Purpose
This constitution defines the baseline rules that every ZERO work package must follow.

## Package Boundary Rules
- One package only.
- Do not split work.
- Stay inside declared scope.
- Do not perform unrelated cleanup.
- Root-cause fixes only.
- Do not silently workaround problems.
- Do not expand scope to fix non-mainline issues.

## Architecture Rules
- Public Contract Rule.
- Projection Rule.
- Error Projection Rule.
- Fixed Contract Rule.
- Object Independence Rule.
- No Wrapper Rule.
- No Passthrough Rule.
- No Recursive Leak Rule.
- Public payloads must not embed previous-layer objects.
- Public payloads must not expose upstream wrapper names.
- Failure payloads must also obey projection boundaries.

## Execution Environment Rule
- Do not install Python packages.
- Do not upgrade Python packages.
- Do not uninstall Python packages.
- Do not modify virtual environments.
- Do not modify PATH.
- Do not modify pip configuration.
- Do not modify bundled runtimes.
- Do not change the execution environment.
- If validation cannot run because of missing tooling or environment limitations, report the limitation and stop.
- Environment management is outside package scope.

## Validation Rules
Each package must clearly separate:
- Required short validation.
- Optional validation.
- Local-only long validation.

Rules:
- Run only requested short validation.
- Do not invent extra long validation.
- Do not run full test suites unless explicitly requested.
- Long validation must be handed back for local execution.
- If validation cannot run, report why and stop.

## Engineering Discipline Rules
- Non-mainline Issue Reporting is mandatory.
- Never silently skip discovered problems.
- Never silently hide architectural debt.
- Never silently convert a real issue into unrelated cleanup.
- Report non-mainline issues without modifying them.
- Do not perform unrelated refactors.
- Do not change production behavior in documentation-only packages.

## Output Rules
Every package completion report must include:
- Files changed.
- Summary.
- Verification.
- Non-mainline issues.
- Git diff summary.

## Documentation Rules
If a package modifies contract, architecture, projection, constitution, or public behavior, update the relevant docs in the same package.

## Future Runtime Module Rule
Future runtime modules, including Snapshot, Replay, Journal, Persistence, Audit, and related AER runtime layers, must comply with this constitution unless a later constitution version explicitly supersedes it.

## Compliance Rule
Every future work package should state that it complies with ZERO Work Package Constitution v1 unless explicitly superseded.
