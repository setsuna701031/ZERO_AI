\# Scheduler Compatibility Surface



\## Current active endpoint



`Scheduler.run\_one\_step` is currently bound to:



```text

\_zero\_scheduler\_run\_one\_step\_v16



Active run\_one\_step chain

v16

&#x20;-> v8

&#x20;-> v5

&#x20;-> v3

&#x20;-> v7336

&#x20;-> v7335

&#x20;-> v7334

&#x20;-> v7333

&#x20;-> v7332

&#x20;-> v352

&#x20;-> v734

&#x20;-> original Scheduler.run\_one\_step

Compatibility API



These helpers are directly referenced by scheduler behavior-lock tests and must not be removed without updating tests and call sites:



\_zero\_scheduler\_base\_run\_one\_step\_v16

\_zero\_scheduler\_run\_one\_step\_v16

\_zero\_scheduler\_run\_operator\_completion\_pipeline

\_zero\_scheduler\_complete\_operator

\_zero\_scheduler\_mark\_operator\_complete\_if\_ok

\_zero\_scheduler\_mark\_failed\_step\_if\_needed

\_zero\_scheduler\_mark\_operator\_complete\_or\_failed

\_zero\_scheduler\_mark\_failed\_if\_ok\_without\_completion

\_zero\_scheduler\_run\_one\_step\_v2

\_zero\_scheduler\_run\_one\_step\_v3

\_zero\_scheduler\_run\_one\_step\_v4

\_zero\_scheduler\_run\_one\_step\_v5

\_zero\_scheduler\_base\_run\_one\_step\_v2

\_zero\_scheduler\_base\_run\_one\_step\_v3

\_zero\_scheduler\_base\_run\_one\_step\_v4

\_zero\_scheduler\_base\_run\_one\_step\_v5

Extracted implementation center



Operator completion logic is implemented in:



core/tasks/scheduler\_core/scheduler\_completion.py



scheduler.py keeps forwarding helpers for compatibility.



Consolidation rule



Do not delete scheduler forwarding helpers only because their implementation moved to scheduler\_core.



A helper can only be removed when:



no tests reference it directly,

no production code references it directly,

the active run\_one\_step chain does not depend on it,

compatibility tests are updated intentionally.

