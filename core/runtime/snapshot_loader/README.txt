Runtime Snapshot Awareness Layer

Purpose:
- Load runtime governance snapshots
- Load runtime stage snapshots
- Load mutation governance snapshots
- Provide runtime self-awareness bootstrap
- Avoid architecture drift between runtime and governance state

Current snapshot sources:
- workspace/runtime_snapshot/runtime_state_snapshot.json
- workspace/runtime_snapshot/mutation_runtime_transition.json
- workspace/runtime_snapshot/mutation_proposal_contract.json

This layer is awareness/bootstrap only.

Not enabled:
- memory persistence
- autonomous mutation
- runtime self-edit
- recursive mutation
- auto commit
- network install