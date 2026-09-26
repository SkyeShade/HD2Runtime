# Architecture and milestone boundary

| Directory | Responsibility |
| --- | --- |
| `core/` | Bounds-checked scalar decoding, ownership/membership resolution, grouped settings and stratagem joins |
| `runtime/` | Read-only Windows adapter, bounded/paced discovery, snapshot rereads, logging, shared update scheduling |
| `schemas/` | Pinned component layout and lookup profile; implementation offsets, never public process identities |
| `domains/` | Human-readable field aliases, storage, vanilla baselines, evidence sources |
| `api/` | `read`, `describe`, `format`, `observe`; explicit rejection of all write primitives |
| `tests/` | Sparse sibling-derived regression bytes and mutation/failure tests |
| `docs/` | Audit, provenance, evidence limits, guarded-writer contract |

Each read validates the EXE/DLL file fingerprints, discovers a unique eligible
entity allocation, validates the complete target membership and component index
map, resolves the owned record, and follows only reviewed typed settings links.
The reader takes and rereads every used ownership/data snapshot before exposing
results. It rejects missing/ambiguous roots, unrecognized framing, unsafe
pointers, allocation/protection changes, out-of-bounds rows and unstable bytes.
Reads are split at region boundaries and paced by operation and byte budgets.
No addresses survive in the public result or get reused for the next observation.

Current schemas are build-pinned structural profiles, extracted from a hashed
retained type library. The runtime checks framing, sizes, counts and indices; it
does not claim a fresh live type-library capture. Reads intentionally report
finite changed field values with `expected_match=false`. They are diagnostics,
not authorization to patch those values. Membership and linkage changes reject.

The 60-second observation clock uses game update `dt`, matching the siblings;
it is paused when updates stop. This is not a wall-clock service. A read is a
stable sequential capture, not an atomic snapshot of a running game. A duplicate
allocation is rejected even if both copies contain identical bytes.

## First guarded patch

The smallest next target is AMR `crosshair_type`, a four-byte enum with an isolated
gameplay proof. Reuse its page/record comparison and protection-restoration
pattern, the JAR-5 rollback rule that rejects unknown partial target bytes, and
Bastion's multi-page/multi-field transaction bookkeeping. The current resolver,
fingerprint checks, exact field widths, ownership snapshots, bounded memory
capability and logging are reusable. They are not a complete writer.

Do not merely wrap the old mod entrypoints. The generic writer must enforce this
single shared sequence for every patch, transaction and ensure operation:

1. Validate the current build, schema, resource ownership and applicable consumer
   sharing constraints. Resolve a fresh internal target; validate the expected
   original value and exact-width desired encoding.
2. Reject overlapping fields, conflicting desired values, unsupported widths and
   unreviewed semantic aliases before making pages writable. Capture rollback
   data, complete records and available non-target bytes.
3. Reread ownership and target/context bytes immediately before writing; there
   must be no scheduler yield between the final guard and the write. This
   narrows a race but cannot provide lock-free atomicity against game writers.
4. Change only necessary target pages; retain original protection independently
   for every page. Avoid code pages and preserve already-writable page state.
5. Write exact widths; verify transferred byte counts and reread each result.
   Verify all captured non-target bytes against the planned result.
6. On partial failure, reverse only bytes demonstrably written by this
   transaction. Recheck ownership and known intermediate states. An unexpected
   third-party value must never be overwritten by rollback.
7. Always attempt restoration and verification of original page protections,
   including failure paths. A failed rollback or restoration is a terminal
   failure with explicit logs, never reported as success.

`transaction` is failure-atomic where verified rollback succeeds, not an atomic
CPU transaction. Its result must separately report apply, rollback and page
restoration outcomes. Fault injection must cover every write and restoration
boundary, including short/partial writes, callback cancellation, ownership
changes and third-party interference. The present fixture reader has **no**
`write` or protection-changing capability.

## First-class ensure contract (next milestone)

This is the proposed declarative shape; it currently returns
`READ_ONLY_MILESTONE` and does not schedule anything:

```lua
hd2.ensure {
    resource = 'amr',
    component = 'WeaponDataComponentData',
    record = 'owned',
    fields = { crosshair_type = { expected = 3, value = 4 } },
    interval = 60, -- default
}
```

`patch` will use this descriptor once. `transaction` will accept an ordered list
of these declarative changes. `ensure` will own a persistent logical identity
and use the same guarded transaction engine on each check; it is not a loop over
a cached address or an unconditional patch call.

After startup, attempt fresh resolution and guarded apply. Every 60 update
seconds, revalidate build, ownership, schema and stable reads before classifying
each field using exact encoded values:

| Current value | Action |
| --- | --- |
| Desired value | No-op, including no protection changes |
| Declared expected original | Apply through the complete guarded transaction |
| Neither expected nor desired | Conflict; terminal fail-closed state, no overwrite |
| Target unavailable | Bounded startup retry / explicit waiting state, never a cached-address write |
| Changed build, structure or ambiguous owner | Terminal rejection |

For a multi-field ensure, inspect every field first. A mixed original/desired
state may plan writes only to original-valued fields after all guards pass;
any third-party field value blocks the entire transaction. Rollback restores
the pre-attempt state, including fields already desired before the attempt.
Cancellation stops subsequent checks; it does not imply restoring vanilla.
Protection/rollback failure disables further automatic attempts. Diagnostic
observation scheduling already distinguishes missing modules/allocations from
validation failure and permits six attempts five update seconds apart. That
bounded readiness policy can be reused for ensure alongside new conflict states.

Before extending damage patches, capture the required consumer tables and
validate their sharing scope. The current read join proves the named linkage;
it does not provide an exhaustive current-live consumer exclusivity certificate.

## Validation boundary

Offline tests and package loading can validate the implementation against the
fixtures. The next authorized live step is loading the read-only report on the
pinned build and collecting its logs, with no gameplay writer present. This task
does not deploy, launch HD2 or claim that live smoke test has occurred.
