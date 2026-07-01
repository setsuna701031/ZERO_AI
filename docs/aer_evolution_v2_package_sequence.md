# AER Evolution v2 Package Sequence

## Purpose

This document defines the implementation order for AER Evolution v2 after the mainline design is locked.

The sequence protects RC1 behavior by building v2 foundation surfaces on the separate evolution branch before scheduler or runtime integration begins.

## Foundation Order

1. Package 78 - Mainline Design
2. Package 79 - Operator Lifecycle
3. Package 80 - Checkpoint Model
4. Package 81 - Operator State Machine
5. Package 82 - Operator Execution Context
6. Package 83 - Checkpoint Store
7. Package 84 - Resume Engine
8. Package 85 - Foundation Architecture Review
9. Package 86 - Operator Event Log
10. Package 87 - Audit Reader
11. Package 88 - Checkpoint Store Read Index
12. Package 89 - Audit Snapshot Composition
13. Package 90 - Human Approval Boundary
14. Package 91 - Issue Reporter
15. Package 92 - Stop Condition Contract
16. Package 93 - Operator Decision Contract
17. Package 94 - Operator Decision Flow
18. Package 95 - Operator Plan Flow
19. Package 96 - Decision + Plan Composition
20. Package 97 - Operator State Composition
21. Package 98 - Operator Handoff Contract
22. Package 99 - Runtime Intake Contract
23. Package 100 - Public Surface Export Seal
24. Package 101 - Runtime Bootstrap Contract
25. Package 102 - Runtime Context Contract
26. Package 103 - Runtime Projection Contract
27. Package 104 - Runtime Session Contract
28. Package 105 - Runtime Activation Contract
29. Package 106 - Runtime Lifecycle Contract
30. Package 107+ - Long-running Operator Loop / Scheduler / Runtime integration

## Package Boundaries

Packages 78 through 98 define v2 foundation surfaces without changing RC1 scheduler, task runner, or operator runtime behavior.

Scheduler and runtime integration begins only after the passive Runtime Intake contract is complete.

## Package 90

Package 90 adds the Human Approval Boundary contract for AER v2 without persistence, event emission, UI, operator loop behavior, scheduler integration, or runtime execution.

All future v2 modules that need persistence must access persistence through repository/store modules. Resume, Loop, Scheduler, Issue Reporter, Approval, and runtime business modules must not directly open, read, write, or delete checkpoint files.

Package 90 owns:

- approval request contract shape
- approval id, operator session id, package id, requested action, request reason, status, and metadata
- pending, approved, rejected, and expired approval statuses
- pure dict helpers for creating, approving, rejecting, and validating approval payloads

Package 90 must not:

- implement operator loop behavior
- call scheduler
- call task_runner
- call resume
- call replay
- write checkpoints
- mutate checkpoints
- own checkpoints
- own resume behavior
- own runtime state
- own operator state machine behavior
- own event ledger behavior
- own audit reader behavior
- persist approvals
- append events
- implement approval UI
- implement retry logic
- implement timers
- implement a transition engine
- change checkpoint persistence
- change checkpoint schema
- parse checkpoint files
- scan checkpoint directories
- discover checkpoints from event payloads
- treat Event Log as a Checkpoint Store index
- scan Event Ledger
- import Event Log
- delete events
- update events
- append events
- classify event severity
- perform issue analysis
- implement approval workflow
- decide operator actions
- filter business events
- trigger scheduler behavior
- trigger runtime behavior
- sort events during load
- infer missing sequence numbers
- reconstruct history
- repair history
- interpret history
- infer missing expected events
- validate lifecycle progression
- require approval events
- require checkpoint events
- require resume events
- require issue report events
- decide what should have existed
- duplicate lifecycle definitions
- duplicate transition rules
- duplicate repository responsibilities
- implement approval
- implement issue reporter
- introduce SQLite, Redis, memory caches, or multi-backend abstractions
- change broad runtime behavior
- change RC1 behavior

## Non-mainline Issues Found

- None for Package 90.

## Package 91

Package 91 adds the Issue Reporter contract for AER v2 without persistence, issue workflow, routing, event emission, operator loop behavior, scheduler integration, runtime execution, approval workflow, checkpoint mutation, resume, retry, or repair.

Package 91 owns:

- issue reporter contract shape
- issue id, operator session id, package id, severity, status, title, description, and metadata
- open, resolved, and dismissed issue statuses
- info, warning, error, and critical issue severities
- pure dict helpers for creating, closing, validating, and summarizing issue payloads

Package 91 must not:

- implement scheduler integration
- implement operator loop behavior
- execute runtime work
- emit events
- implement approval workflow
- mutate checkpoints
- own checkpoint state
- own resume behavior
- implement retry logic
- implement repair logic
- persist issues
- route issues
- implement issue workflow
- import scheduler, task_runner, resume, checkpoint_store, event_log, audit_reader, approval, operator_loop, runtime_execution, or repair modules

Future packages own:

- issue persistence
- issue workflow
- issue routing
- issue event emission

## Non-mainline Issues Found

- None for Package 91.

## Package 92

Package 92 adds the Stop Condition contract for AER v2 without operator loop behavior, scheduler integration, runtime execution, retry, repair, resume behavior, approval workflow, issue workflow, event emission, persistence, or checkpoint mutation.

Package 92 owns:

- stop condition contract shape
- stop condition id, operator session id, package id, reason, status, message, and metadata
- completed, failed, blocked, waiting_for_approval, validation_failed, unsafe_to_continue, checkpoint_missing, checkpoint_invalid, resume_identity_mismatch, and non_mainline_issue_detected stop reasons
- active and resolved stop condition statuses
- pure dict helpers for creating, resolving, validating, and summarizing stop condition payloads

Package 92 must not:

- implement operator loop behavior
- implement scheduler integration
- execute runtime work
- implement retry logic
- implement repair behavior
- own resume behavior
- implement approval workflow
- implement issue workflow
- emit events
- persist stop conditions
- mutate checkpoints
- own checkpoint state
- own state machine behavior
- interpret lifecycle transitions
- import scheduler, task_runner, resume, checkpoint_store, event_log, audit_reader, approval, issue_reporter, operator_loop, runtime_execution, repair, or state_machine modules

Future packages own:

- loop integration
- event emission
- runtime interpretation
- retry and repair behavior

## Non-mainline Issues Found

- None for Package 92.

## Package 93

Package 93 adds the Operator Decision contract for AER v2 without runtime integration, scheduler integration, operator loop behavior, event emission, checkpoint mutation, resume behavior, approval workflow, issue workflow, retry, repair, persistence, or execution dispatch.

Package 93 owns:

- operator decision contract shape
- decision id, operator session id, package id, decision type, decision reason, status, metadata, and created_at
- continue, stop, request_approval, report_issue, checkpoint, and resume decision types
- proposed, accepted, and rejected decision statuses
- pure dict helpers for creating, accepting, validating, and summarizing decision payloads

Package 93 must not:

- integrate with runtime execution
- implement scheduler integration
- implement operator loop behavior
- emit events
- mutate checkpoints
- own resume behavior
- implement approval workflow
- implement issue workflow
- implement retry logic
- implement repair behavior
- persist decisions
- dispatch execution
- interpret decisions at runtime
- implement decision flow
- import scheduler, task_runner, resume, checkpoint_store, event_log, audit_reader, approval, issue_reporter, stop_condition, operator_loop, runtime_execution, repair, or state_machine modules

Future packages own:

- decision flow
- event emission
- loop integration
- runtime interpretation
- retry and repair behavior

## Non-mainline Issues Found

- None for Package 93.

## Package 94

Package 94 adds the Operator Decision Flow for AER v2 as a pure composition layer over completed contracts only. The flow validates an operator decision contract and returns exactly one outcome: continue, approval_required, issue_reported, or stopped.

Package 94 owns:

- decision flow composition over the decision contract
- allowed outcome mapping for continue, request_approval, report_issue, and stop decisions
- invalid decision handling as issue_reported
- summary projection containing only outcome, decision_id, decision_type, and status

Package 94 must not:

- execute runtime work
- call Scheduler
- call TaskRunner
- emit events
- write checkpoints
- resume execution
- persist state
- start loops
- perform retries
- repair code
- implement runtime integration
- implement scheduler integration
- implement operator loop behavior
- import scheduler, task_runner, operator_loop, event_log, checkpoint_store, resume, or audit_reader modules

Future packages own:

- runtime execution
- scheduler integration
- operator loop integration
- event emission
- checkpoint mutation
- resume execution
- retry and repair behavior

## Non-mainline Issues Found

- None for Package 94.

## Package 95

Package 95 adds the Operator Plan Flow for AER v2 as a pure composition layer over the operator plan contract only. The flow validates an operator plan contract and returns exactly one outcome: continue, approval_required, issue_reported, or stopped.

Package 95 owns:

- plan flow composition over the plan contract
- allowed outcome mapping for continue, request_approval, report_issue, and stop plans
- invalid plan handling as issue_reported
- valid-but-not-flow-owned plan handling as issue_reported
- summary projection containing only outcome, plan_id, plan_type, and status

Package 95 must not:

- execute runtime work
- call Scheduler
- call TaskRunner
- emit events
- write checkpoints
- resume execution
- persist state
- start loops
- perform retries
- repair code
- implement runtime integration
- implement scheduler integration
- implement operator loop behavior
- import scheduler, task_runner, operator_loop, event_log, checkpoint_store, resume, or audit_reader modules

Future packages own:

- runtime execution
- scheduler integration
- operator loop integration
- event emission
- checkpoint mutation
- resume execution
- retry and repair behavior

## Non-mainline Issues Found

- Existing operator plan contract files were not present in the working tree before Package 95 implementation; Package 95 added the minimal contract-only surface needed for the requested composition flow.

## Package 96

Package 96 adds the Decision + Plan Composition flow for AER v2 as a pure composition layer over completed Decision Flow and Plan Flow surfaces. The composition flow evaluates both lower-level flows and returns a fresh combined summary without executing runtime, scheduler, or operator loop behavior.

Package 96 owns:

- composition over Decision Flow and Plan Flow outputs
- combined outcome mapping for continue, approval_required, issue_reported, and stopped
- invalid decision or invalid plan handling through lower-level flow issue outcomes
- issue_reported precedence when either lower-level flow reports an issue
- summary projection containing only outcome, decision summary, and plan summary

Package 96 must not:

- execute runtime work
- call Scheduler
- call TaskRunner
- emit events
- write checkpoints
- resume execution
- persist state
- start loops
- perform retries
- repair code
- implement runtime integration
- implement scheduler integration
- implement operator loop behavior
- import scheduler, task_runner, persistent_operator, operator_loop, event_log, checkpoint_store, resume, or audit_reader modules

Future packages own:

- runtime execution
- scheduler integration
- operator loop integration
- event emission
- checkpoint mutation
- resume execution
- retry and repair behavior

## Non-mainline Issues Found

- Existing Package 94 and Package 95 files were still untracked in the working tree when Package 96 was implemented; Package 96 composed those local surfaces without modifying them.

## Package 97

Package 97 adds the Operator State Composition layer for AER v2 as a pure state wrapper over the completed Decision + Plan Composition summary. The operator state is a fresh dict projection of the composition summary and does not execute, schedule, persist, resume, or interpret runtime behavior.

Package 97 owns:

- operator state contract shape
- immutable state creation from a composition summary
- validation of the state wrapper and nested composition summary projection
- summary projection containing only outcome and composition summary

Package 97 must not:

- execute runtime work
- call Scheduler
- call TaskRunner
- emit events
- write checkpoints
- resume execution
- persist state
- start loops
- perform retries
- repair code
- implement runtime integration
- implement scheduler integration
- implement operator loop behavior
- import scheduler, task_runner, persistent_operator, operator_loop, event_log, checkpoint_store, resume, or audit_reader modules

Future packages own:

- runtime execution
- scheduler integration
- operator loop integration
- event emission
- checkpoint mutation
- resume execution
- retry and repair behavior

## Non-mainline Issues Found

- Package 94 through Package 96 implementation files were still untracked in the working tree when Package 97 was implemented; Package 97 composed those local surfaces without modifying them.

## Package 98

Package 98 adds the Operator Handoff Contract for AER v2 as a passive data wrapper over Operator State. The handoff is a fresh dict prepared for future runtime integration, but it does not execute, dispatch, schedule, allocate identities, persist, transition lifecycle, checkpoint, resume, retry, or call any runtime loop.

Package 98 owns:

- operator handoff contract shape
- immutable handoff creation from an operator state dict
- invalid operator state handling as an invalid handoff or issue_reported outcome
- validation of the handoff wrapper and nested operator state summary projection
- summary projection containing only outcome, operator state summary, and state validity

Package 98 must not:

- execute runtime work
- dispatch runtime work
- call Scheduler
- call TaskRunner
- emit events
- write checkpoints
- resume execution
- persist state
- start loops
- perform retries
- repair code
- generate session ids
- allocate runtime identity
- introduce ownership
- introduce authority
- introduce leases
- introduce locks
- introduce reservations
- introduce execution permissions
- introduce recovery metadata
- introduce watchdog metadata
- reference runtime sessions
- implement state transitions
- implement lifecycle behavior
- implement runtime integration
- implement scheduler integration
- implement operator loop behavior
- import scheduler, task_runner, persistent_operator, operator_loop, event_log, checkpoint_store, resume, or audit_reader modules

Future packages own:

- runtime execution
- scheduler integration
- operator loop integration
- event emission
- checkpoint mutation
- resume execution
- retry and repair behavior
- runtime identity allocation

## Non-mainline Issues Found

- Package 94 through Package 97 implementation files were still untracked in the working tree when Package 98 was implemented; Package 98 composed those local surfaces without modifying them.

## Package 99

Package 99 adds the Runtime Intake Contract for AER v2 as a passive data wrapper over Operator Handoff. The intake is a fresh dict prepared for future runtime consumption, but it does not execute, dispatch, schedule, allocate runtime sessions, persist, transition lifecycle, checkpoint, resume, retry, or call any runtime loop.

Package 99 owns:

- runtime intake contract shape
- immutable intake creation from an operator handoff dict
- valid operator handoff issue outcomes carried as valid issue_reported intake
- invalid operator handoff payload handling as invalid runtime intake
- validation of the intake wrapper and nested operator handoff summary projection
- summary projection containing only outcome, operator handoff summary, and intake structural validity
- separation of intake structural validity from business outcome

Package 99 must not:

- execute runtime work
- dispatch runtime work
- call Scheduler
- call TaskRunner
- emit events
- write checkpoints
- resume execution
- persist state
- start loops
- perform retries
- repair code
- generate session ids
- allocate runtime identity
- introduce ownership
- introduce authority
- introduce leases
- introduce locks
- introduce reservations
- introduce execution permissions
- introduce recovery metadata
- introduce watchdog metadata
- reference runtime sessions
- implement state transitions
- implement lifecycle behavior
- implement runtime integration
- implement scheduler integration
- implement operator loop behavior
- import scheduler, task_runner, persistent_operator, operator_loop, event_log, checkpoint_store, resume, or audit_reader modules
- automatically pass through unknown operator handoff fields

Future packages own:

- runtime execution
- scheduler integration
- operator loop integration
- event emission
- checkpoint mutation
- resume execution
- retry and repair behavior
- runtime identity allocation

## Non-mainline Issues Found

- Package 94 through Package 98 implementation files were still untracked in the working tree when Package 99 was implemented; Package 99 composed those local surfaces without modifying them.

## Package 100

Package 100 adds the AER v2 Public Surface Export Seal before any Runtime Integration begins. The seal is a focused test layer over the current supported AER v2 contract surface and does not add runtime behavior or require implementation changes.

Package 100 owns:

- focused public surface seal tests for AER v2 modules
- current supported __all__ verification where modules already declare __all__
- inventory handling for modules that do not yet declare __all__
- forbidden export checks for execute, dispatch, retry, checkpoint, resume, lifecycle, transition, session, and runtime identity API names
- forbidden import checks for scheduler, task_runner, persistent_operator, runtime loop, and operator loop surfaces
- fixed key set checks for summary, handoff, and runtime intake projections
- unknown key non-passthrough checks for handoff and runtime intake
- runtime intake valid/outcome semantic separation checks

Package 100 must not:

- modify AER v2 implementation files
- add runtime behavior
- dispatch runtime work
- call Scheduler
- call TaskRunner
- emit events
- write checkpoints
- resume execution
- persist state
- start loops
- perform retries
- generate runtime sessions or identities
- introduce lifecycle or transition behavior
- create red tests for future public API work

Future packages own:

- adding explicit __all__ declarations to modules that do not currently expose them, if desired
- runtime execution
- scheduler integration
- operator loop integration
- event emission
- checkpoint mutation
- resume execution
- retry and repair behavior
- runtime identity allocation

## Non-mainline Issues Found

- Package 100 inventory found that core/runtime/aer_operator_decision.py and core/runtime/aer_operator_plan.py do not currently declare __all__; the seal treats this as inventory, not a failing future-work expectation.
- Package 94 through Package 99 implementation files were still untracked in the working tree when Package 100 was implemented; Package 100 tested those local surfaces without modifying them.

## Package 101

Package 101 adds the Runtime Bootstrap Contract for AER v2 as a passive transport and preparation data wrapper over Runtime Intake. The bootstrap payload describes what a future Runtime would need, but it does not create, resolve, bind, initialize, execute, dispatch, schedule, allocate runtime sessions, persist, checkpoint, resume, or call any runtime loop.

Package 101 owns:

- runtime bootstrap contract shape
- immutable bootstrap creation from a runtime intake dict
- valid runtime intake issue outcomes carried as valid issue_reported bootstrap
- malformed runtime intake payload handling as invalid runtime bootstrap
- validation of the bootstrap wrapper and nested runtime intake summary projection
- summary projection containing only outcome, runtime intake summary, and bootstrap structural validity
- separation of bootstrap structural validity from business outcome

Package 101 must not:

- execute runtime work
- dispatch runtime work
- call Scheduler
- call TaskRunner
- emit events
- write checkpoints
- resume execution
- persist state
- start loops
- perform retries
- repair code
- generate session ids
- allocate runtime identity
- create runtime objects
- construct runtime instances
- perform dependency injection
- resolve services
- bind workspaces
- bind filesystems
- bind repositories
- load configuration
- load environment state
- load plugins
- run runtime initialization callbacks
- describe execution mode
- describe execution policy
- describe retry policy
- describe timeout behavior
- describe priority
- select schedules
- select queues
- select workers
- select executors
- classify runtime resources
- introduce concurrency
- introduce parallelism
- advertise supported features
- advertise supported capabilities
- introduce capability flags
- describe runtime capabilities
- negotiate features
- define compatibility matrices
- introduce ownership
- introduce authority
- introduce leases
- introduce locks
- introduce reservations
- introduce execution permissions
- introduce recovery metadata
- introduce watchdog metadata
- reference runtime sessions
- implement state transitions
- implement lifecycle behavior
- implement runtime integration
- implement scheduler integration
- implement operator loop behavior
- import scheduler, task_runner, persistent_operator, operator_loop, event_log, checkpoint_store, resume, or audit_reader modules
- automatically pass through unknown runtime intake fields

Future packages own:

- runtime object creation, if any
- runtime instance construction, if any
- dependency injection and service resolution, if any
- workspace, filesystem, repository, configuration, environment, and plugin binding, if any
- runtime initialization callbacks, if any
- execution strategy, including mode, policy, retry policy, timeout, priority, scheduling, queues, workers, executors, resource classes, concurrency, and parallelism
- capability discovery, feature negotiation, and compatibility matrices
- runtime execution
- scheduler integration
- operator loop integration
- event emission
- checkpoint mutation
- resume execution
- retry and repair behavior
- runtime identity allocation

## Non-mainline Issues Found

- Package 94 through Package 100 implementation and test files were still untracked in the working tree when Package 101 was implemented; Package 101 composed those local surfaces without modifying unrelated implementation files.

## Package 102

Package 102 adds the Runtime Context Contract for AER v2 as a passive data contract produced from Runtime Bootstrap. The context payload is a future Runtime-readable dict, but it does not create a Runtime, allocate a session, bind a workspace, resolve configuration, negotiate capabilities, choose an execution strategy, dispatch work, or interact with scheduler/runtime/operator loops.

Package 102 owns:

- runtime context contract shape
- immutable context creation from a runtime bootstrap dict
- valid runtime bootstrap issue outcomes carried as valid issue_reported context
- malformed runtime bootstrap payload handling as invalid runtime context
- validation of the context wrapper and operator handoff projection derived from bootstrap
- summary projection containing only outcome, operator handoff projection, and context structural validity
- separation of context structural validity from business outcome
- documented context field purposes: contract identifies the schema, outcome exposes the upstream result to a future Runtime, operator_handoff carries minimal upstream operator intent, valid records context structural validity, and errors records structural validation failures

Package 102 must not:

- create runtime objects
- allocate runtime sessions
- allocate runtime identity
- bind workspaces
- bind repositories
- bind filesystems
- load configuration
- load environment state
- load plugins
- introduce ownership
- introduce authority
- introduce leases
- introduce locks
- introduce reservations
- introduce execution permissions
- execute runtime work
- dispatch runtime work
- perform retries
- write checkpoints
- resume execution
- select execution strategy
- select schedules
- select queues
- select workers
- select executors
- describe priority
- negotiate capabilities
- advertise supported features
- pass through unknown runtime bootstrap fields
- call Scheduler
- call TaskRunner
- call persistent operator surfaces
- call runtime loop, scheduler loop, or operator loop files

Future packages own:

- runtime object creation, if any
- runtime session and identity allocation, if any
- workspace, repository, filesystem, configuration, environment, and plugin binding, if any
- authority, lease, lock, reservation, and permission models
- execution strategy, queues, workers, executors, scheduling, priority, retry, checkpoint, and resume behavior
- capability discovery, feature negotiation, and supported feature surfaces
- scheduler, runtime loop, and operator loop integration

## Non-mainline Issues Found

- Existing Package 100 inventory remains: core/runtime/aer_operator_decision.py and core/runtime/aer_operator_plan.py do not currently declare __all__; Package 102 did not modify them.

## Package 103

Package 103 adds the Runtime Projection Contract for AER v2 as a passive data contract over Runtime Context. The projection payload is the direct future Runtime consumption surface. It intentionally consumes Runtime Context only and does not expose runtime bootstrap, runtime intake, or any upstream wrapper shape.

Package 103 owns:

- runtime projection contract shape
- immutable projection creation from a runtime context dict
- valid runtime context issue outcomes carried as valid issue_reported projection
- malformed runtime context payload handling as invalid runtime projection
- validation of the projection wrapper and operator handoff projection derived from context
- summary projection containing only outcome, operator handoff projection, and projection structural validity
- separation of projection structural validity from business outcome
- documented projection field purposes: contract identifies the schema, outcome exposes the context result to a future Runtime, operator_handoff carries minimal upstream operator intent, valid records projection structural validity, and errors records structural validation failures

Package 103 must not:

- import runtime bootstrap helpers
- import runtime intake helpers
- expose runtime bootstrap fields
- expose runtime intake fields
- preserve upstream wrapper shape
- create runtime objects
- allocate runtime sessions
- allocate runtime identity
- bind workspaces
- bind repositories
- bind filesystems
- load configuration
- load environment state
- load plugins
- introduce ownership
- introduce authority
- introduce leases
- introduce locks
- introduce reservations
- introduce execution permissions
- execute runtime work
- dispatch runtime work
- perform retries
- write checkpoints
- resume execution
- select execution strategy
- select schedules
- select queues
- select workers
- select executors
- describe priority
- negotiate capabilities
- advertise supported features
- pass through unknown runtime context fields
- call Scheduler
- call TaskRunner
- call persistent operator surfaces
- call runtime loop, scheduler loop, or operator loop files

Future packages own:

- runtime object creation, if any
- runtime session and identity allocation, if any
- workspace, repository, filesystem, configuration, environment, and plugin binding, if any
- authority, lease, lock, reservation, and permission models
- execution strategy, queues, workers, executors, scheduling, priority, retry, checkpoint, and resume behavior
- capability discovery, feature negotiation, and supported feature surfaces
- scheduler, runtime loop, and operator loop integration

## Non-mainline Issues Found

- Existing Package 100 inventory remains: core/runtime/aer_operator_decision.py and core/runtime/aer_operator_plan.py do not currently declare __all__; Package 103 does not modify them.


## Package 104

Package 104 adds the Runtime Session Contract for AER v2 as a passive data contract over Runtime Projection. The session payload is the first Runtime-named public contract, but it does not allocate a session id, create a Runtime object, bind resources, dispatch work, schedule work, checkpoint, resume, retry, or call any runtime loop.

Package 104 owns:

- runtime session contract shape
- immutable runtime session creation from a runtime projection dict
- valid runtime projection issue outcomes carried as valid issue_reported runtime session
- malformed runtime projection payload handling as invalid runtime session
- validation of the runtime session wrapper and operator handoff projection derived from projection
- summary projection containing only outcome, runtime session summary, and session structural validity
- separation of runtime session structural validity from business outcome
- documented runtime session field purposes: contract identifies the schema, outcome exposes the projection result to a future Runtime, runtime_session carries minimal Runtime-facing session intent, valid records session contract structural validity, and errors records structural validation failures

Package 104 must not:

- allocate session ids
- allocate runtime identity
- create runtime objects
- construct runtime instances
- perform dependency injection
- resolve services
- bind workspaces
- bind repositories
- bind filesystems
- load configuration
- load environment state
- load plugins
- run runtime initialization callbacks
- introduce ownership
- introduce authority
- introduce leases
- introduce locks
- introduce reservations
- introduce execution permissions
- execute runtime work
- dispatch runtime work
- perform retries
- write checkpoints
- resume execution
- select execution strategy
- select schedules
- select queues
- select workers
- select executors
- describe priority
- negotiate capabilities
- advertise supported features
- import runtime context helpers
- import runtime bootstrap helpers
- import runtime intake helpers
- expose runtime projection fields
- expose runtime context fields
- expose runtime bootstrap fields
- expose runtime intake fields
- preserve upstream wrapper shape
- pass through unknown runtime projection fields
- call Scheduler
- call TaskRunner
- call persistent operator surfaces
- call runtime loop, scheduler loop, or operator loop files

Future packages own:

- runtime object creation, if any
- real runtime session id allocation, if any
- runtime identity allocation, if any
- workspace, repository, filesystem, configuration, environment, and plugin binding, if any
- authority, lease, lock, reservation, and permission models
- execution strategy, queues, workers, executors, scheduling, priority, retry, checkpoint, and resume behavior
- capability discovery, feature negotiation, and supported feature surfaces
- scheduler, runtime loop, and operator loop integration

## Non-mainline Issues Found

- Existing Package 100 inventory remains: core/runtime/aer_operator_decision.py and core/runtime/aer_operator_plan.py do not currently declare __all__; Package 104 does not modify them.




## Package 105

Package 105 adds the Runtime Activation Contract for AER v2 as a passive data contract over Runtime Session. The activation payload describes a minimal activation intent for a future Runtime, but it does not activate, initialize, allocate, bind, dispatch, execute, schedule, checkpoint, resume, retry, or call any runtime loop.

Package 105 owns:

- runtime activation contract shape
- immutable runtime activation creation from a runtime session dict
- valid runtime session issue outcomes carried as valid issue_reported runtime activation
- malformed runtime session payload handling as invalid runtime activation
- validation of the runtime activation wrapper and runtime session projection derived from session
- summary projection containing only outcome, runtime activation summary, and activation structural validity
- separation of runtime activation structural validity from business outcome
- documented runtime activation field purposes: contract identifies the schema, outcome exposes the session result to a future Runtime, runtime_activation carries minimal Runtime-facing activation intent, valid records activation contract structural validity, and errors records structural validation failures

Package 105 must not:

- activate runtime work
- initialize runtime work
- allocate session ids
- allocate runtime identity
- create runtime objects
- construct runtime instances
- perform dependency injection
- resolve services
- bind workspaces
- bind repositories
- bind filesystems
- load configuration
- load environment state
- load plugins
- run runtime initialization callbacks
- introduce ownership
- introduce authority
- introduce leases
- introduce locks
- introduce reservations
- introduce execution permissions
- execute runtime work
- dispatch runtime work
- perform retries
- write checkpoints
- resume execution
- select execution strategy
- select schedules
- select queues
- select workers
- select executors
- describe priority
- negotiate capabilities
- advertise supported features
- import runtime projection helpers
- import runtime context helpers
- import runtime bootstrap helpers
- import runtime intake helpers
- expose runtime projection fields
- expose runtime context fields
- expose runtime bootstrap fields
- expose runtime intake fields
- preserve upstream wrapper shape
- pass through unknown runtime session fields
- call Scheduler
- call TaskRunner
- call persistent operator surfaces
- call runtime loop, scheduler loop, or operator loop files

Future packages own:

- real runtime activation behavior, if any
- runtime object creation, if any
- real runtime session id allocation, if any
- runtime identity allocation, if any
- workspace, repository, filesystem, configuration, environment, and plugin binding, if any
- authority, lease, lock, reservation, and permission models
- execution strategy, queues, workers, executors, scheduling, priority, retry, checkpoint, and resume behavior
- capability discovery, feature negotiation, and supported feature surfaces
- scheduler, runtime loop, and operator loop integration

## Non-mainline Issues Found

- Existing Package 100 inventory remains: core/runtime/aer_operator_decision.py and core/runtime/aer_operator_plan.py do not currently declare __all__; Package 105 does not modify them.



## Package 106

Package 106 adds the Runtime Lifecycle Contract for AER v2 as a passive data contract over Runtime Activation. The lifecycle payload describes minimal lifecycle intent for a future Runtime, but it does not activate, initialize, transition, allocate, bind, dispatch, execute, schedule, checkpoint, resume, retry, recover, repair, or call any runtime loop.

Package 106 owns:

- runtime lifecycle contract shape
- immutable runtime lifecycle creation from a runtime activation dict
- valid runtime activation issue outcomes carried as valid issue_reported runtime lifecycle
- malformed runtime activation payload handling as invalid runtime lifecycle
- validation of the runtime lifecycle wrapper and runtime activation projection derived from activation
- summary projection containing only outcome, runtime lifecycle summary, and lifecycle structural validity
- separation of runtime lifecycle structural validity from business outcome
- documented runtime lifecycle field purposes: contract identifies the schema, outcome exposes the activation result to a future Runtime, runtime_lifecycle carries minimal Runtime-facing lifecycle intent, valid records lifecycle contract structural validity, and errors records structural validation failures

Package 106 must not:

- activate runtime work
- initialize runtime work
- implement lifecycle transitions
- allocate session ids
- allocate runtime identity
- create runtime objects
- construct runtime instances
- perform dependency injection
- resolve services
- bind workspaces
- bind repositories
- bind filesystems
- load configuration
- load environment state
- load plugins
- run runtime initialization callbacks
- introduce ownership
- introduce authority
- introduce leases
- introduce locks
- introduce reservations
- introduce execution permissions
- execute runtime work
- dispatch runtime work
- perform retries
- write checkpoints
- resume execution
- perform recovery
- repair code
- select execution strategy
- select schedules
- select queues
- select workers
- select executors
- describe priority
- negotiate capabilities
- advertise supported features
- import runtime session helpers
- import runtime projection helpers
- import runtime context helpers
- import runtime bootstrap helpers
- import runtime intake helpers
- expose runtime session fields
- expose runtime projection fields
- expose runtime context fields
- expose runtime bootstrap fields
- expose runtime intake fields
- preserve upstream wrapper shape
- pass through unknown runtime activation fields
- call Scheduler
- call TaskRunner
- call persistent operator surfaces
- call runtime loop, scheduler loop, or operator loop files

Future packages own:

- real runtime lifecycle transitions, if any
- real runtime activation behavior, if any
- runtime object creation, if any
- real runtime session id allocation, if any
- runtime identity allocation, if any
- workspace, repository, filesystem, configuration, environment, and plugin binding, if any
- authority, lease, lock, reservation, and permission models
- execution strategy, queues, workers, executors, scheduling, priority, retry, checkpoint, resume, recovery, and repair behavior
- capability discovery, feature negotiation, and supported feature surfaces
- scheduler, runtime loop, and operator loop integration

## Non-mainline Issues Found

- Existing Package 100 inventory remains: core/runtime/aer_operator_decision.py and core/runtime/aer_operator_plan.py do not currently declare __all__; Package 106 does not modify them.



## Future Foundation Work

- Shared cross-module identity validation is deferred until Lifecycle, State Machine, Context, and Checkpoint have stabilized.
- Future modules must compose the foundation modules instead of reimplementing lifecycle phases, transition rules, context data, or checkpoint serialization.
- Future long-running state retention belongs to the Operator Loop, not Resume.
- Issue Reporter decides when to emit issue events.
- Future Approval integration decides when to emit approval events and how approval decisions are consumed.
- Resume may emit resume events in a future package, but Package 86 does not integrate Resume and Event Log.
- Operator Loop decides when events are emitted during execution.
- Future Audit Reader extensions must continue composing published repository read APIs instead of deriving persistence state from Event Ledger payloads.
