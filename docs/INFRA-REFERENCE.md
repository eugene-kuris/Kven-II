# Synthetic INFRA reference slice

`src/kven_public/infra_reference.py` is a deliberately simplified, standalone
**reference implementation**, not the private deployed collector, INFRA schema,
archive reader, authorization mechanism, or a deployable infrastructure tool.
It uses only Python's standard library and caller-supplied tuple-backed
snapshots, and makes **no** network or system calls. Nested values are
canonically captured at construction; record fields cannot be reassigned.
Snapshot metadata and reference timestamps must be exact strings, not subclasses
with caller-defined comparison or parsing behavior. This example is not a
general security boundary for untrusted Python code.

A snapshot declares a source, stable source-native typed identities, an exact
collection scope, its coverage (`COMPLETE`, `PARTIAL`, `FAILED`), a timestamp,
and synthetic evidence digests/references. `replay` deterministically derives
historical facts and current candidates from those inputs. Changes retain
superseded evidence; contradictory observations produce an unresolved conflict,
not a chosen truth. Identical observations at a later timestamp are recorded
as re-verification without semantic drift. Only an item actually re-observed
updates its own `last_verified_at`.

An item absent from an exactly matching `COMPLETE` snapshot can be removed
from that source/scope's derived view. Absence under `PARTIAL` or `FAILED`
remains unknown, including unresolved competing evidence for a property that
was only partially re-observed. A single partial re-observation cannot silently
resolve an earlier conflict; failed collection cannot certify any retained historical fact
as current. `current_state_proof` is deliberately strict: it only means that
an unconflicted fact was verified at the caller's explicit `as_of` instant.
It is **not** a credential, a live-state guarantee, or an authorization grant.

For a standalone example, see `tests/test_infra_reference.py`. All entities,
evidence pointers and timestamps in these tests are invented. Production persistence, source authorization, collector adapters, and other
operational behaviors are **outside the scope** of this reference example.
