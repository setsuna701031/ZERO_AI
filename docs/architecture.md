# System Architecture

The system is composed of five main layers:

1. Task Repository
2. DAG Scheduler
3. Scheduler Queue
4. Runtime State Machine
5. Task Runner

---

# Architecture Flow

Task Submit
↓
Task Repository
↓
DAG Scheduler
↓
Scheduler Queue
↓
Task Runner
↓
Runtime State Machine
↓
Task Finished / Failed / Retry / Replan

---

# Components

## Task Repository

Stores:

* task_id
* status
* depends_on
* history
* workspace_dir
* task_dir

## DAG Scheduler

Determines if a task is ready:

* All dependencies finished → queued
* Otherwise → blocked

## Scheduler Queue

Runnable task queue.

## Runtime State Machine

Tracks execution state and transitions:

* queued → running → finished
* running → retry
* running → failed
* running → replan

## Task Runner

Executes steps and updates runtime state.

---

# Goal Lineage Coordination Architecture

The runtime identity model now includes a canonical goal-lineage contract above
session identity and below evidence / authority / completion.

## Canonical Goal Scope

```text
root_goal_id
+ goal_lineage_id
+ session_id
+ runtime_session_id
```

This scope defines the goal lineage that queue, scheduler, resume, evidence,
authority, and completion must preserve.

## Canonical Child Identity

```text
goal_lineage_id
+ session_id
+ runtime_session_id
+ branch_type
+ branch_id
```

This identity is used for continuation / replan / child work-item isolation.
Only a fully matching child identity is duplicate-idempotent.

## Legacy Metadata

The following fields may still be preserved as metadata, but they are not enough
to prove runtime identity by themselves:

```text
task_id
package_id
goal_id
source_goal_id
continuation_id
replan_request_id
```

## Updated Coordination Flow

```text
Root Goal
↓
Goal Lineage Contract
↓
Continuation / Replan Coordinator
↓
Persistent Queue Contract
↓
Scheduler Queue
↓
Persistent Runtime Orchestrator
↓
Runtime Session Resume
↓
Decision Evidence
↓
Evidence Repository / Evidence Authority
↓
Goal Completion Authority
↓
Goal Finished / Failed / Retry / Replan / Resume
```

## Isolation Rules

```text
A resume cannot restore another root/session/lineage snapshot.
A retry cannot modify another branch identity.
A fail/finish transition is scoped to its canonical child identity.
A child finish cannot complete the wrong root goal.
Evidence must match the target goal lineage before completion authority accepts it.
Scheduler duplicate detection must use lineage-aware branch identity, not task_id alone.
```

## Ownership Boundaries

```text
Scheduler remains orchestration only.
Queue stores and deduplicates lineage-aware work items.
Resume restores lineage-matching snapshots only.
EvidenceRepository indexes and filters by lineage scope.
EvidenceAuthority validates lineage-scoped evidence chains.
GoalCompletionAuthority owns completion acceptance and rejects lineage mismatch.
```

## Validated Seal

```text
tests/test_goal_lineage_coordination_seal.py -> 6 passed
tests/test_multi_session_coordination_seal.py -> 8 passed
tests/test_persistent_queue_multi_session.py -> 2 passed
tests/test_persistent_queue_contract_seal.py -> 8 passed
python -m compileall core cli tests -> passed
git diff --check -> passed
```

Engineering verdict:

```text
Goal Lineage Coordination Seal: SEALED
```

---

## ZERO Engineering Runtime v3.3 - Governed Multi-Cycle Runtime Coordination

Implementation baseline: `b098fcd feat(engineering): add governed multi-cycle runtime coordination`.

Runtime v3.3 adds a governed orchestration layer, not a replacement artifact family. The model is:

```text
Engineering Runtime Session
├── Runtime Cycle 1: Proposal → Approval → Authorization → Execution → Verification → Feedback → Closure
├── Runtime Cycle 2: New Proposal → New Approval → New Authorization → Execution → Verification → Feedback → Closure
└── Runtime Cycle 3: New Proposal → New Approval → New Authorization → Execution → Verification → Completed/Closed
```

Architecture boundaries:

- Session identity and fingerprints are deterministic canonical JSON / SHA-256 seals.
- Cycle identity and fingerprints are deterministic canonical JSON / SHA-256 seals.
- Cycle 1 has no previous-cycle link; later cycles must reference the exact previous cycle identity and fingerprint.
- Cycle numbers cannot skip, repeat, or cross sessions.
- Each cycle must carry fresh Approval and Authorization references; prior-cycle Approval or Authorization references are rejected.
- Feedback can only create a Proposal Candidate marked candidate-only, not approved, not authorized, and not executable.
- Resume validates persisted session/cycle/checkpoint evidence and returns the next governed action; it never approves, authorizes, invokes adapters, runs shell commands, or executes mutations.
- Inspect is a read-only projection over existing session, cycle, journal, and checkpoint artifacts.
- Journal replay is deterministic because each entry has a strict sequence and previous-entry fingerprint chain.
- Checkpoints seal durable session state, current cycle references, journal head, verified artifact references, and resume metadata.

Therefore v3.3 remains governed coordination rather than a fully autonomous engineering loop. Actual repository mutation authority remains outside the Session coordinator and must continue through existing governed execution paths.

## Engineering Runtime v3.4 Objective and Completion Coordination

Runtime v3.4 is an additive governance layer over the v3.3 Engineering Runtime Session. The existing v3.3 Session/Cycle/Journal/Checkpoint/Resume/Inspect contracts remain frozen for required fields and fingerprint semantics; v3.4 persists additional artifacts in bounded session subdirectories.

The v3.4 artifact flow is: Session Objective → Cycle Objective Assignment → governed Proposal/Approval/Authorization/Execution/Verification/Feedback → Objective Progress Evaluation → Completion Readiness → Iteration Health → Iteration Decision. When readiness is sufficient, the runtime may create a Completion Review Request with `authority_state=not_granted`. A Human Completion Decision is separate from proposal approval and authorization; only `approved_complete` permits the existing completed-session transition.

Completion readiness fails closed when required acceptance criteria lack evidence, evidence references are invalid, lineage is invalid, scope deviates, a failed cycle remains open, unresolved feedback exists, or required objectives remain unsatisfied. Testing or verification success is treated as evidence only, not as automatic objective completion.

Iteration health uses deterministic progression deltas: newly satisfied criteria indicate progressing; new evidence without satisfaction indicates slow progress; three consecutive no-progress cycles indicate stalled; repeated verification failure identities indicate repeating failure. Stalled or repeating-failure health requires human reassessment and blocks unbounded next-candidate generation.

Next Iteration Objective Candidates are bounded by remaining approved objectives and criteria. They are explicitly candidate-only, not proposals, not approved, not authorized, and not executable.

## Engineering Work Entry v3.5 Architecture

The v3.5 work entry architecture provides a single coordination surface from `zero.engineering.work_request.v1` through `zero.engineering.work_intake.v1` into `zero.engineering.work_coordination.v1`. Coordination references the existing Engineering Runtime Session rather than creating a second runtime. Stage transitions are validated by artifact evidence: repository admission, repository analysis closure, objective, planning closure, proposal, proposal review closure, approval closure, authorization closure, execution preparation closure, execution result, verification closure, progress evaluation, completion review, or next-iteration handoff.

Inspection is read-only and reports stage timeline, missing artifacts, next governed action, authority state, runtime linkage, completion readiness, iteration health, and resumability. Resume revalidates the coordination artifact and returns a decision without planning automatic approval, authorization, execution, completion, or proposal creation. Persistence is under the session store `work-entry/` namespace using canonical UTF-8 JSON and read-back validation.

v3.5 is not a fully autonomous engineering loop. It is the governed entry and coordination layer that safely connects existing analysis, planning, proposal, review, approval, authorization, execution, verification, and v3.4 completion capabilities while preserving human governance gates.

## v3.6 Governed Read-Only Engineering Preparation Pipeline

The v3.6 pipeline is an additive coordination layer. It reuses v3.5 Work Request, Work Intake, and Work Coordination as the entry point; v3.3 Runtime Session, Journal, Checkpoint, Resume, and Inspect boundaries; v3.4 Runtime Session Objectives and completion limits; and existing Repository Analysis, Planning, Proposal, and Proposal Review builders/validators as frozen contracts.

Pipeline flow:

1. Work Request / Work Intake / Work Coordination.
2. Repository Admission validates the repository root and read-only authority.
3. Repository Analysis creates the existing root admission, snapshot, topology, discovery, dependency analysis, engineering inventory, analysis evidence, analysis report, and analysis closure artifacts.
4. Session Objective Definition creates `zero.engineering.runtime_session_objective.v1` only when bounded acceptance criteria are present.
5. Engineering Planning creates the existing planning context, goals, work breakdown, dependency ordering, validation strategy, risk assessment, plan, verification, and planning closure.
6. Proposal Preparation creates existing proposal intake, scope, proposed change set, dependency mapping, validation plan, risk review, engineering proposal, verification, and proposal closure.
7. Proposal Review creates a proposal review closure that may be ready for human approval but is never approval.
8. Human Gate Handoff records pending approval with authority, authorization, and execution states still not granted/not started.

The pipeline status enum is `created`, `running`, `awaiting_input`, `awaiting_human_approval`, `completed_read_only_preparation`, `blocked`, `failed`, and `invalid`. Stage results use `completed`, `awaiting_input`, `blocked`, `failed`, and `invalid`. `completed_read_only_preparation` means the requested pre-approval read-only mode ended; it does not mean the engineering task or runtime session is complete. Legacy v3.5 work entries without a v3.6 artifact inspect as `not_initialized`.

## v3.7 Governed Approval-to-Execution Activation Architecture

The v3.7 activation module is an additive layer after Read-Only Preparation and Proposal Review. It reuses the existing work coordination references, read-only pipeline references, runtime session identity, runtime adapter admission contract validators, runtime adapter controlled invocation artifacts, runtime verification boundary, and v3.4 progress/completion vocabulary while treating existing Approval, Authorization, execution token, adapter admission fingerprint, and frozen contract semantics as immutable.

Artifacts are canonical JSON with deterministic SHA-256 fingerprints that exclude their own fingerprint fields. Activation identity binds one Work Request, Coordination, Runtime Session, Read-Only Pipeline, Proposal, Proposal Review Closure, Workspace, and exact ordered operation package. The Authorization Handoff requests human authorization with `authority_state = not_granted` and never embeds an execution token.

State transitions are artifact-gated: awaiting approval, awaiting authorization, preparing execution, ready for explicit execution, awaiting verification, verification completed, awaiting completion review, next iteration candidate, blocked, failed, invalid, completed, or closed. Inspect is read-only and Resume only returns decisions such as requiring human authorization, execution preparation, adapter admission, explicit execution activation, verification, progress evaluation, completion review, next iteration proposal, or reassessment.

Controlled execution is limited to one sealed package, one workspace, one authorization, and one invocation. Evidence records before/after state, changed and unchanged paths, operation observations, adapter references, commit markers, rollback markers, and authorization consumption. Verification must succeed before objective progress is evaluated; completion readiness still requires human completion review.

## ZERO Engineering Runtime v3.8 Operator Flow Architecture

The v3.8 operator flow is a presentation and coordination layer. It reuses `engineering_work_entry`, `engineering_read_only_pipeline`, `engineering_approval_execution_activation`, the Runtime Session Store, existing inspect/resume semantics, and canonical JSON/fingerprint utilities. It persists only deterministic operator linkage when needed and keeps human-readable summaries outside the source of truth.

The canonical `zero.engineering.operator_flow.v1` artifact includes schema, operator flow identity and fingerprint, work request, coordination, runtime session, read-only pipeline, approval/execution activation references, current phase, overall status, next operator action, human action requirement, available commands, blocked reasons, and latest summary references. Phases are derived from underlying artifacts and include not started, intake, read-only preparation, awaiting approval, awaiting authorization, execution preparation, ready for execution, execution, verification, progress evaluation, awaiting completion review, next iteration candidate, blocked, failed, completed, closed, and invalid.

The active work resolver supports explicit session, coordination, and work request IDs. With exactly one active work it resolves that work; with multiple active works it returns `ambiguous_active_work`; with none it returns `no_active_work`. Completed, closed, and invalid work is excluded from default active resolution.

Preview remains read-only and reports workspace, adapter, ordered operations, target paths, before-state hashes, expected paths, validation/recovery information, authorization actor, consumption state, readiness, and blocking conditions. Execute requires explicit confirmation and delegates to the governed v3.7 controlled execution API, which rechecks workspace state, operation package identity, and unconsumed authorization before mutation. Verify delegates to the v3.7 verification API and does not mark the engineering task completed.

## v3.9 Architecture — Governed Natural-Language Intake Layer

The v3.9 layer sits before v3.5 Work Entry. The governed flow is: Natural-Language Task → Normalized Task Intent → Repository-Grounded Evidence → Work Specification Candidate → Clarification Assessment → Human Specification Confirmation → Formal Engineering Work Request → v3.5 Work Entry → v3.6 Read-Only Pipeline.

Artifacts use canonical JSON and SHA-256 fingerprints, persisted through the existing runtime session store allowlist under bounded `work-entry/` paths. Candidate and clarification response lineage is append-only: a response creates a new candidate version linked to the previous candidate, while confirmations bind to an exact candidate fingerprint. Legacy v3.8 work without intake reports `natural_language_intake_status = not_initialized`, not corruption.

Repository evidence is bounded and read-only. It admits explicit paths and exact filenames, records unresolved references without substituting similar paths, notes observed tests/configuration, and declares limitations such as no project test execution and no arbitrary command execution. The evidence layer does not create a second repository analyzer or session registry.

Confirmation formalization reuses the existing v3.5 Work Request builder and v3.6 pipeline constructor. It does not prepare, approve, authorize, execute, or complete work. Confirmation only establishes that a human accepted the specification; approval and authorization remain frozen downstream contracts.

The model boundary remains optional and conservative. Core v3.9 behavior is deterministic and model-agnostic. Model suggestions may only be validated candidate suggestions and cannot become confirmed requirements or grant authority.

## v4.0 Governed Practical Repository Task Runner Architecture

The practical runner adds canonical artifacts under the engineering session store: `work-entry/governed-change-package.json`, `execution/bounded-test-policy.json`, `execution/practical-execution-evidence.json`, `execution/test-results.json`, and `verification/practical-verification.json`. These paths are bounded and written with the existing atomic canonical session-store helper.

The execution pipeline is: Confirmed Specification → Work Request → Read-Only Analysis → Proposal → Governed Change Package → Human Approval → Human Authorization → Execution Preparation → Adapter Admission → Explicit Execution → Evidence → Verification → Progress → Completion Review Candidate. v4.0 treats existing Approval, Authorization, Execution Activation, Adapter Admission/Invocation, workspace drift protection, replay protection, canonical JSON/SHA-256 fingerprints, and session-store semantics as frozen governance contracts. The practical runner is additive and does not create a parallel authorization token, adapter registry, shell runner, or Git mutation path.

Bounded test execution is limited to tokenized `python -m pytest <tests path> -q` or a single pytest node under configured test roots. Output is size-bounded, timeout-bounded, and executed with `shell=False`. Git diff evidence uses read-only tokenized Git inspection only. Unexpected changed paths fail verification and prevent completion candidacy.

## v4.1 Governed Multi-File Coding Workflow

The v4.1 architecture extends the governed engineering sequence to: Confirmed Specification → Work Request → Read-Only Repository Analysis → Multi-File Change Plan Candidate → Human Plan Confirmation → Proposal → Human Approval → Human Authorization → existing v4.0 Governed Change Package → Adapter Admission → Explicit Execution → Bounded Test Set → Verification → Failure Evidence Analysis → Repair Proposal Candidate → Human Review. Plan Candidate is not a confirmed plan; Confirmation is not Approval; Approval is not Authorization; Execution is not Verification; Test Failure Evidence is not Repair Authorization; Repair Proposal Candidate is not executable; and Completion still requires a separate human completion decision.

Artifacts are persisted through the existing Runtime Session Store under bounded paths for planning, testing, feedback, and iteration lineage. The plan records file roles, change kinds, repository evidence, acceptance mappings, dependency order, risk, uncertainties, and a test strategy with `prohibited_full_suite = true`. The test set runs ordered targets only through the existing bounded pytest operation. Failure parsing keeps bounded assertion summaries and repository-relative traceback frames without claiming root cause. Repair candidates classify suspected paths as within scope or requiring scope expansion, and accepted repair review only permits the next read-only planning state. Old authorization cannot be reused for the next iteration.

## v4.2 Governed Work Request Integrity Closure

The governed read-only chain is: Natural-Language Intake → Clarification → human Specification Confirmation → existing Formal Work Request → Repository Analysis/Evidence → Multi-File Plan Candidate → linkage validation → Human Plan Confirmation. The Formal Work Request is a required governance ancestor, not an Approval or execution grant. Plan validation binds the Work Request fingerprint, confirmed Specification reference, repository-analysis reference, repository identity, confirmed scope, and session identity. Missing, stale, mismatched, or silently expanded lineage fails closed with bounded reason codes. Legacy sessions without v4.2 linkage are reported as not initialized or incomplete and are not automatically migrated.

This closure adds no second schema, session store, or CLI and deliberately does not change the Perform/perf intent-classifier behavior.

## v4.3 Intent Classification Boundary Hardening

The existing natural-language Intake classifier now uses a single deterministic vocabulary policy whose entries explicitly select `short_ascii_alias`, `full_ascii_word`, `multiword_phrase`, `identifier_token`, or `non_ascii_phrase`. NFKC normalization and lowercase comparison happen before matching. ASCII terms require bounded locations, with identifier and slash-prefix handling preserving snake-case, kebab-case, and repository-path use; non-ASCII phrases retain contiguous matching because Chinese text does not require spaces.

Classification evidence remains backward compatible through `matched_terms` and additionally exposes each match kind, bounded span, and normalization basis. Ambiguous short substrings fail safe by producing no match. The v4.2 Formal Work Request and Multi-File Plan linkage chain is unchanged, and classification grants no Approval, Authorization, Execution, or mutation authority.

## v4.4 Persisted Intake Lineage Integrity Closure

The governed lineage is now: Natural-Language Intake -> Clarification -> Specification Candidate -> human Specification Confirmation -> canonical Finalized Intake -> Formal Work Request -> Repository Evidence -> Multi-File Plan Candidate -> lineage validation -> Human Plan Confirmation. Finalized Intake identity and fingerprint are derived only from canonical content; timestamps and random values are excluded. The artifact is atomically persisted and read back from the originating session before formalization.

Plan validation resolves the Work Request's finalized-Intake reference from the same bounded Session Store and verifies identity, fingerprint, session, finalization state, and Specification Confirmation linkage. Missing or inconsistent lineage fails closed with bounded reason codes. Inspect and resume expose the defect and recommend reconfirmation without silently migrating legacy artifacts or starting Approval, Authorization, Execution, mutation, repair, retry, or completion.

## v4.5 Governed Bug Reproduction & Evidence Collection

The post-plan evidence chain is: Human Plan Confirmation -> Reproduction Request Candidate -> Human Reproduction Confirmation -> single-use Bounded Test Admission -> bounded pytest execution -> Reproduction Result -> Test Failure Evidence -> Repair Proposal Candidate -> Human Repair Review. Every artifact is canonical, fingerprinted, persisted through the existing bounded Session Store, and bound to the same session.

Admission accepts only explicit `tests/` pytest files and bounded node IDs. It rejects expressions, traversal, absolute paths, scope expansion, invalid timeouts, repository or session mismatch, workspace drift, stale confirmation, and replay. The runner receives a fixed argument vector and cannot invoke a shell, install packages, use the network, mutate Git, or alter production files. A reproduced failure is evidence of observed behavior only: root cause remains unconfirmed, and the repair candidate contains investigation intent rather than executable operations or authority.

## v5.0 Governed Repair Planning & Patch Candidate

The repair-planning chain is: accepted Human Repair Review -> Repair Planning Intake -> Root-Cause Hypothesis Candidate -> Impact Analysis -> Repair Strategy Candidate -> Patch Candidate -> Patch Validation -> Human Patch Review. Each artifact is canonical, same-session persisted, and linked to the Work Request, confirmed Specification, Plan Confirmation, Reproduction Result, Failure Evidence, Repair Proposal Candidate, repository identity, confirmed scope, and iteration.

Root-Cause Hypothesis records supporting and contradicting evidence, alternatives, confidence, and limitations while keeping `confirmed_root_cause` false. Impact Analysis separates direct and possible paths; possible out-of-scope impact requires human scope review and prevents Patch Candidate construction. Patch items are descriptive metadata with `requires_human_definition`, never code or executable operations. Validation rejects stale or unresolved evidence, session/repository/iteration mismatch, silent scope expansion, unknown paths, dependency cycles, missing acceptance mappings, unbounded tests, executable payloads, and authority. Human Patch Review remains distinct from Approval, Authorization, execution, retry, and completion.

## v5.1 Governed Patch Authoring Candidate

The candidate-only authoring chain is: confirmed Human Patch Review -> Patch Authoring Intake -> bounded Source Snapshot -> human-supplied File/Test Edit Candidates -> deterministic Candidate Diff -> Authoring Validation -> Human Authored Patch Review. Snapshots contain only confirmed repository-relative UTF-8 text within strict file and byte limits, plus hashes and newline metadata. Validation re-snapshots sources to detect drift before accepting a candidate.

Edit candidates support exact replacement, full text replacement, append, exact removal, and text creation as data only. Exact edits must have one source match; test edits must remain within confirmed pytest targets. Unified diffs are generated in memory with stable `a/` and `b/` paths and no timestamps, Git, shell, or external patch utility. Neither candidate content nor diff is written to target files. Human Authored Patch Review is not Approval, Authorization, execution permission, Change Package admission, retry, or completion.

## v5.2 Governed Patch Authorization & Change Package Preparation

The authorization chain is: confirmed Human Authored Patch Review -> Change Package Preparation Intake -> Change Package Candidate -> validation -> Human Change Package Approval -> Patch Authorization Request -> Human Patch Authorization -> Authorized Change Package -> execution-readiness verification. Every transition uses canonical fingerprints and exact references to prevent operation, path, test-target, repository, session, iteration, or workspace substitution.

Change Package operations are ordered candidate data tied to reviewed edit artifacts and source/result hashes. Validation permits only bounded text-edit operation kinds, checks dependency acyclicity, acceptance mappings, confirmed scope, bounded test targets, rollback coverage, and zero embedded authority. Approval does not authorize, authorization does not execute, and readiness does not invoke an executor. Single-use and replay state are represented for a future separately governed apply runtime; this release stops at `awaiting_explicit_apply`.

## v5.3 Governed Explicit Patch Apply

The apply chain is: ready Authorized Change Package -> Explicit Human Apply Request -> Apply Admission -> authorization reservation -> transactional apply -> operation and mutation evidence -> focused verification -> Completion Review Candidate -> Human Completion Review. Admission is read-only and repeats all exact lineage, drift, scope, operation, path, target, and replay checks immediately before mutation. Authorization becomes reserved for one execution attempt and consumed whether the transaction commits or rolls back; a failed attempt requires new human authorization.

The executor accepts only exact replacement, full-file text replacement, append text, exact removal, and text-file creation. Paths remain repository-relative, symlinks and binary or structural changes are rejected, pre- and post-hashes are mandatory, and an in-memory backup set supports all-or-nothing rollback. Focused verification invokes the existing argument-vector bounded pytest runner only for authorized files or node IDs. Verification never retries or completes automatically, and Human Completion Review provides no Git authority.

## v5.4 Governed Commit Preparation & Explicit Commit

The local-commit chain is: completed Human Completion Review -> Commit Preparation Intake -> Commit Candidate -> Commit Diff Verification -> Commit Admission -> Explicit Human Commit Request -> governed local commit -> Commit Evidence -> Commit Verification -> Awaiting Explicit Push Review. Preparation requires applied mutation evidence, passing and completion-eligible verification, consumed apply authorization, and exact agreement between changed and authorized paths.

Git inspection uses fixed argument vectors and records repository root, branch, HEAD, porcelain status, path sets, diff checks, and a deterministic diff fingerprint. Admission and execution fail closed on stale lineage, replay, HEAD or workspace drift, untracked or pre-staged content, path or message substitution, and session artifacts. Execution stages only the exact confirmed paths and never exposes amend, broad staging, push, PR, merge, tag, release, or automatic actions. Post-commit verification requires the expected parent, message, paths, fingerprint, and clean tree before reporting `awaiting_explicit_push_review`.

## v5.5 Governed Explicit Push Review

The remote-mutation chain is: Commit -> Commit Verification -> Verified Commit Closure -> Push Preparation -> read-only Remote Verification -> Human Push Review -> Explicit Push Authorization -> exact-SHA Push Execution -> append-only Push Evidence -> post-push Remote Verification -> Push Closure. Verified Commit Closure is a canonical sealed gate of its own: it is `verified` only when the canonical Commit Verification status is `verified`, canonical Commit Evidence is complete, and both name the same commit. Its `commit_verification_closure_id` is carried unchanged by every downstream artifact and checked at every transition. Push Preparation and the immediate pre-push validation require the exact same immutable closure reference; matching a SHA alone never admits a push. No stage discovers a latest closure, falls back to another verification artifact, or replaces the reviewed ID. Review is not authorization, and authorization is single-use.

Remote inspection uses `git ls-remote --heads` without fetching or modifying local refs. Preflight requires the remote branch to exist at the verified commit's parent, proves ancestry, and counts exactly one pending commit. Execution accepts structured remote, commit, and branch values only, revalidates the frozen local and remote state plus the original Commit Verification closure, and constructs a single fixed-form refspec using a full SHA and `refs/heads/` destination. No free-form Git arguments or other network mutation surfaces exist. Closure requires consumed authorization, successful execution evidence, and a second read-only observation proving the remote head equals the pushed commit.
