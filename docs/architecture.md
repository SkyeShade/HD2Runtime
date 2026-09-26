# Architecture and milestone boundary

| Directory | Responsibility |
| --- | --- |
| `core/` | Bounds-checked scalar decoding, ownership/membership resolution, grouped settings and stratagem joins |
| `runtime/` | Separate read-only/write Windows adapters, bounded discovery, snapshot rereads, logging, shared update scheduling |
| `schemas/` | Pinned component layout and lookup profile; implementation offsets, never public process identities |
| `domains/` | Human-readable field aliases, storage, vanilla baselines, evidence sources |
| `api/` | `read`, `describe`, `format`, `observe`, identity builders and guarded `patch`; ensure/transaction deferred |
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

The first enabled target is JAR-5 logical `armor_penetration`: three contiguous
UINT32 lanes, 3/3/3 to 4/4/4, preserving the fourth lane. See the complete
[guarded-patch contract](guarded-patch.md), including exact mapping and failure
semantics. `core/resolution.lua` is shared by read and patch operations;
`core/guarded_write.lua` owns bounded, synchronous guard/write/rollback/restore.
`domains/patches.lua` defines the reviewed logical field and baseline guards.
No sibling runtime code is imported. Every patch discovers from identity when
it runs. No public read result or declaration contains a cached process address.

The native writer and patch implementation are excluded from read-only builds.
Normal mods use the public builder and one patch declaration. The proof has no
memory access, scans, offsets or Win32 code. The only enabled patch is JAR-5 AP4;
ensure and multi-patch transactions are future milestones.

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

`patch` currently uses the identity-builder descriptor documented above.
`transaction` will accept an ordered list of declarative changes. `ensure` will own a persistent logical identity
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

The user confirmed read-only live validation passing all six resources at
`9e7a9e6e2ab94195ef8c06d22ec4df8388069b08`. Guarded-write tests use retained fixtures,
fault injection and test-owned native memory. The new gameplay proof is built
without deployment or HD2 launch; it has no new live gameplay confirmation.
