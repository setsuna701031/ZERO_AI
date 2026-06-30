\# AER Evolution v2 Contract Inventory



\## Purpose



This document records the contract surfaces required before AER Evolution v2 implementation begins.



This package is documentation-only.



\## Contract Surface 1: Operator Loop Contract



Future contract name:



`aer.operator\_loop.v2`



Required fields:



\- operator\_session\_id

\- package\_id

\- package\_version

\- loop\_state

\- current\_phase

\- previous\_phase

\- iteration\_index

\- checkpoint\_id

\- stop\_condition

\- approval\_state

\- issue\_report\_id



Required states:



\- initialized

\- running

\- checkpointed

\- waiting\_for\_approval

\- blocked

\- failed

\- completed

\- resumed



Core invariant:



The operator loop must never advance without either a completed phase result, a checkpoint, or an explicit stop condition.



\## Contract Surface 2: Checkpoint Contract



Future contract name:



`aer.operator\_checkpoint.v2`



Required fields:



\- checkpoint\_id

\- operator\_session\_id

\- package\_id

\- runtime\_session\_id

\- current\_phase

\- completed\_phases

\- pending\_phases

\- failed\_phase

\- created\_at

\- resume\_token

\- integrity\_hash



Core invariant:



A checkpoint must be sufficient to resume without guessing prior state.



\## Contract Surface 3: Resume Contract



Future contract name:



`aer.operator\_resume.v2`



Required fields:



\- resume\_token

\- checkpoint\_id

\- operator\_session\_id

\- package\_id

\- requested\_by

\- resume\_mode

\- resume\_result

\- identity\_match

\- lineage\_match



Allowed resume modes:



\- continue

\- retry\_failed\_phase

\- restart\_with\_new\_identity



Core invariant:



Default resume mode must preserve identity and lineage.



\## Contract Surface 4: Issue Reporter Contract



Future contract name:



`aer.operator\_issue\_report.v2`



Required fields:



\- issue\_report\_id

\- operator\_session\_id

\- package\_id

\- discovered\_at\_phase

\- issue\_type

\- severity

\- scope\_relation

\- description

\- recommended\_action

\- fixed\_in\_current\_package



Allowed scope relation:



\- mainline

\- non\_mainline

\- unknown



Core invariant:



A non-mainline issue must be reported, not silently skipped.



\## Contract Surface 5: Stop Condition Contract



Future contract name:



`aer.operator\_stop\_condition.v2`



Required fields:



\- stop\_condition\_id

\- operator\_session\_id

\- package\_id

\- phase

\- reason

\- severity

\- can\_resume

\- requires\_human\_approval

\- validation\_required\_before\_resume



Allowed stop reasons:



\- completed

\- failed

\- blocked

\- validation\_failed

\- waiting\_for\_human\_approval

\- unsafe\_to\_continue

\- checkpoint\_missing

\- checkpoint\_invalid

\- resume\_identity\_mismatch

\- non\_mainline\_issue\_detected



Core invariant:



Every stop must have a typed reason.



\## Contract Surface 6: Human Approval Boundary Contract



Future contract name:



`aer.operator\_human\_approval.v2`



Required fields:



\- approval\_id

\- operator\_session\_id

\- package\_id

\- phase

\- requested\_action

\- risk\_reason

\- approval\_status

\- approved\_by

\- approved\_at



Allowed approval status:



\- not\_required

\- required

\- approved

\- rejected

\- expired



Core invariant:



Approval-required actions must not continue automatically.



\## Non-mainline Issues Found



None in this documentation-only package.

