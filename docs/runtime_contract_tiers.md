\# Runtime Contract Tiers



\## Tier 1 — Hard Runtime Contracts



\- execution\_trace

\- results

\- final\_answer

\- error



Reason:

Used by repair/retry/replan/runtime persistence.



Breaking risk:

Critical.



\---



\## Tier 2 — Runtime State Synchronization



\- last\_error

\- failure\_message

\- failure\_type

\- status

\- state\_detail



Reason:

Scheduler state machine synchronization.



Breaking risk:

High.



\---



\## Tier 3 — Runtime Snapshot / Hydration



\- step\_results

\- last\_step\_result

\- execution\_log



Reason:

Runtime persistence + hydration replay.



Breaking risk:

Medium-High.



\---



\## Tier 4 — Legacy Compatibility Fields



\- message

\- summary

\- text

\- content

\- stdout

\- response



Reason:

Legacy payload normalization compatibility.



Breaking risk:

Low individually, High collectively.

