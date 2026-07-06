# Runtime Read Replay Verification Contract v1

Status: read replay verification only.

Schema: `zero.runtime.read_replay_verification.v1`.

This contract verifies controlled read evidence before any future mutation path. Verification requires a read
execution id, immutable read evidence, content digest, and content metadata.

The deterministic replay verification record includes replay verification id, read execution id, original
digest, current digest, verification status, mismatch reason, and audit projection.

Supported statuses:

- verified
- mismatch
- expired
- invalid

Rules:

- matching digest produces verified
- changed digest produces mismatch
- missing evidence produces invalid
- expired evidence produces expired
- mismatch or invalid evidence blocks mutation readiness

The verifier records stale read detection, evidence ownership, replay audit, and verification timestamp. It does
not reread unauthorized resources and never writes, mutates, starts subprocesses, runs shells, uses network,
performs executor actions, starts autonomy, or starts background loops.

Final decision: runtime can prove what it saw before allowing future changes.
