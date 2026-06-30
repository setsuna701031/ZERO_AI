# Changelog

## aer-core-v1.0.0-rc1

### Added

- AER freeze evidence pack.
- AER freeze candidate seal.
- Runtime contract layer:
  - Authority context contract
  - Runtime identity contract
  - Runtime session contract
  - Runtime execution contract
  - Runtime boundary contract
- Runtime contract unit tests.
- Passive contract adoption in:
  - RuntimeDispatcher
  - RuntimeSessionResume
  - RuntimeStateMachine
  - RuntimeExecutionFabric

### Changed

- Scheduler and runtime boundary work is now treated as freeze candidate scope.
- Contract dedup migration is deferred to post-freeze maintenance.

### Validated

```text
370 passed
5377 deselected
73 subtests passed
```

### Notes

This release candidate should be treated as the stable AER Core baseline. Future dedup/refactor work should happen after this RC baseline is preserved.
