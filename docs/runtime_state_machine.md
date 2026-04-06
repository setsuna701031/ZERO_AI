\# Runtime State Machine



Each task has a persistent runtime state stored in:



workspace/tasks/<task\_id>/runtime\_state.json



\---



\# Runtime State Fields



status

current\_step\_index

steps\_total

retry\_count

replan\_count

blocked\_reason

failure\_type

failure\_message

final\_answer



\---



\# State Transitions



queued → running

running → finished

running → retry

running → failed

running → replan

retry → running

replan → running



\---



\# Purpose



The runtime state machine ensures that task execution is persistent, recoverable, and resumable even after system restart.



