# First guarded patch: JAR-5 AP4

> **Historical document.** This describes the original fixed-resource JAR-5 `armor_penetration` patch from HD2Runtime 0.3.0. The runtime still accepts it so old mods keep working, but it is not how new mods are written. For the current typed API see `getting-started.md` (ownership, patch/transaction/plan) and the `Jar5AP4` example project.

The typed equivalent writes the same bytes: `hd2.weapon('JAR-5 Dominator'):attack('primary'):projectile()` with `hd2.fields.damage.ap_direct`, `ap_slight` and `ap_large` from 3 to 4, as one transaction with `allow_shared=true`.

Version 0.3.0 adds one reviewed write: JAR-5 Dominator logical armor penetration
from 3 to 4. The retained source entrypoint is `proof/jar5.lua`; its entire gameplay
declaration is:

```lua
local hd2 = require('mods/skyeshade/hd2runtime')
hd2.patch({
    id = 'jar5-ap4',
    target = hd2.weapon('JAR-5 Dominator'):projectile():damage(),
    field = 'armor_penetration',
    expect = 3,
    value = 4,
})
```

`patch` returns a scheduled handle. After three update seconds it performs fresh,
bounded discovery and applies once. Inspect `handle.status` (`waiting`,
`resolving`, `complete`, `rejected`, `cancelled`) and `handle.result.status`
(`APPLIED`, `ALREADY_DESIRED`, `REJECTED`). `cancel()` stops pending discovery;
it does not undo an applied patch. Discovery stops after 180 update seconds or
10,000 steps. Unavailable targets reject this one-shot request; it never falls
back to an old address or fixture. Invalid declarations raise before scheduling.

`diagnostic = true` adds identity, schema type, record, discovery, write and
protection counters. Normal success logging is:

```text
[HD2Runtime] patch jar5-ap4 target resolved
[HD2Runtime] armor_penetration 3 -> 4
[HD2Runtime] non_target_bytes_unchanged=true
[HD2Runtime] protection_restored=true
[HD2Runtime] patch jar5-ap4 APPLIED
```

An already-desired record logs `ALREADY_DESIRED` and causes no writes or protection
changes. A third-party or mixed lane value logs `REJECTED code=CONFLICT`.
Runtime failure reports include the reason, rollback outcome and protection
restoration result. A failed verification is never logged as `APPLIED`.

## Reviewed mapping and evidence

| Identity/field | Mapping |
| --- | --- |
| Resource | `0x80F1A156D9FA1E36` |
| ProjectileWeaponComponentData | index 321, owned record 211; projectile type 177 |
| ProjectileSettings | group 0, row 262, type 177; damage type 153 |
| DamageSettings / DamageInfo | group 1, row 158, type 153; 76-byte record |
| Logical `armor_penetration` | three contiguous UINT32 lanes at record offsets 12, 16, 20 |
| Expected -> desired bytes | `3,3,3` -> `4,4,4`; exactly 12 bytes |
| Fourth AP lane | offset 24, must remain 0 |
| Standard/durable damage | offsets 4/8, must remain 275/90 |

This follows `Jar-5_buff/src/gameplay/validate.lua` and `transaction.lua`, with the
native wrapper pattern from `src/infra/windows_write.lua`. Their hashes are in
`provenance.json`. The complete 272-byte projectile record and non-target bytes
of the 76-byte damage record are compared with retained reviewed originals in
`domains/patches.lua`. Regression tests cross-check those constants against the
existing captured settings fixtures. Baseline constants authorize comparisons;
they never substitute for runtime reads.

The API currently accepts only this target, logical field, expected value 3 and
desired value 4. Raw lane writes and all other weapon fields are rejected.
Version 0.4.0 also allows this descriptor to be wrapped by `ensure`; Shield Relay
provides the first multi-field `transaction`. No new resource mapping is added.
Read APIs continue exposing the individual lane values; the write mapping is an
explicit domain-level logical field, distinct from the scalar read width.

The user reported read-only live validation passing all six resources at
`9e7a9e6e2ab94195ef8c06d22ec4df8388069b08`. That establishes prior read validation,
not live gameplay confirmation for this new package. Structural and schema
evidence remain separate from gameplay and native-consumer evidence. This
milestone does not claim a new native-consumer proof or exhaustive sharing audit
outside the reviewed projectile consumer table.

## Guard sequence

1. Validate the declaration and copy identity/value scalars. The descriptor
   cannot contain an address. Fresh application-time discovery uses the same
   resource/component/settings resolver as public reads.
2. Validate EXE/game.dll fingerprints, unique allocations, entity membership,
   component indices, grouped settings schema, projectile/damage links, and the
   single reviewed projectile consumer. Validate original or desired AP bytes,
   full projectile bytes and every non-target damage-record byte.
3. Finish paced snapshot verification and revalidate fingerprints. The commit
   section has no coroutine yields, log callbacks or user callbacks. Reread all
   captured ownership and data contexts before opening the target page and again
   directly before the write. The shared transaction engine caps the synchronous
   section at 128 contexts / 2 MiB of snapshot data and 16,384 read queries. Its
   reread allowance is derived from the plan and bounded by a 64 MiB ceiling
   (`docs/transaction-ensure.md`, read budget).
4. Allow only private committed data pages with original protection READONLY or
   READWRITE. Require an aligned 12-byte field wholly inside one 4 KiB page.
   Open that page only when necessary, verify writable protection, and reread
   the target immediately before the exact-width native write.
5. Verify the transferred count, reread the target, compare every captured byte
   with the expected result, restore original protection, verify it by query,
   and verify the full contexts again. Checks include the complete generated
   damage and projectile buffers and the captured entity ownership chain.
6. On failure, roll back only the original value or the exact transferred prefix
   reported by the attempted write. Unknown bytes, changed ownership, or changed
   non-target context refuse rollback. Never overwrite an unexplained value.
   Restore protection on every failure path; make two bounded attempts. A failed
   rollback or restoration is terminal and explicitly reported.

`writes` counts native write attempts, including rollback. `bytes_written` is the
reported forward transfer count. `protection_changes` counts native protection
attempts. No automatic retry follows a transaction failure. If the OS refuses
restoration, the runtime reports `protection_restored=false`; it cannot promise
that an unsuccessful OS operation restored a page.

Sequential rereads reduce races but cannot lock a running game's memory or make
a 12-byte write CPU-atomic. The transaction runs without cooperative yields and
verifies the result; unknown interference fails closed. Failure can leave a
partial patch when ownership/interference prevents safe rollback, which is
reported rather than concealed.

## Reading a rejection (Proton and Wine reports)

`non_target_bytes_unchanged=true` is set only after every captured context
matched. On a rejection the log adds `non_target_check`, which says how far the
comparison got:

- `not_reached`: validation stopped before any comparison completed.
  `non_target_bytes_unchanged=false` then says nothing about the bytes; nothing
  was read as changed, opened or written.
- `checked`: the contexts matched before the failure.
- `mismatch`: bytes around a target changed.

A refused region query (`allocation ownership/protection changed`) also logs one
`guard_failure` line. The guard itself is unchanged; the line only names the
reason and what the memory looked like:

```text
[HD2Runtime] non_target_bytes_unchanged=false non_target_check=not_reached
[HD2Runtime] guard_failure address=0x... failed=protection region=0x...+0x1000 state=0x1000 type=0x20000 protect=0x40 allocation_base=0x... allocation_protect=0x40 expected_allocation_base=0x... expected_size=0x... expected_type=0x20000 expected_protect=0x4 module=none expected_bytes=match (1 match, 0 differ, 0 unreadable)
```

- `failed` lists every condition that did not hold: `query_failed`, `extent`,
  `address_outside_region`, `state` (not committed), `allocation_base` (another
  allocation), `type` (not the captured private/image type) or `protection`
  (not READONLY or READWRITE).
- `region`, `state`, `type`, `protect`, `allocation_base` and
  `allocation_protect` are the query's answer. The `expected_*` values are what
  resolution captured.
- `module` names the loaded module that contains the address, if any.
- `expected_bytes` compares every target with the bytes the plan expected. It
  uses a fault-safe read and reads only the plan's own targets, following no
  pointer.

The first refused query is the one reported. It can be a target page (the
rejection happens before any page is opened) or a captured context, read again
inside the guarded section. A protection restore that fails after its retries
logs `protection_restore_failure page=... original=... reason=...`.

Runtime does not accept other protections or allocation layouts on Wine or
Proton (for example PAGE_EXECUTE_READWRITE heap pages). Nothing proves offline
that such a page behaves like the Windows one it replaces. A `guard_failure`
line from an affected system is the evidence needed to decide that.
`tests/test_transaction.py` covers these cases with a fault-injecting memory:
an unchanged region, a benign subdivision into one-page regions of the same
allocation (accepted), a changed protection, a changed allocation base, a true
replacement (other allocation, other type, other bytes), a failed query and a
failed restore.

## Package and tests

From a clean commit:

```powershell
py -3.14 -B scripts/build_gameplay_proof.py
```

The standalone ZIP includes the library, native writer, minimal proof entrypoint,
manifest, archive sidecars, provenance, test log and commit-identified build
report. It requires Bingus Shared Loader v15+ / API 1. Use one HD2Runtime package
at a time; it replaces the read-only report package under the same mod GUID.
Building does not deploy, launch HD2 or perform gameplay writes.

The separate read-only report and live-validation builders still exclude every
write module. `fixture_fallback=disabled` applies to both package types. Tests use
injected memory and a separately allocated test-process page for native ABI
verification; no tests write to HD2.
