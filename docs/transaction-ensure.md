# Guarded transactions and ensure

> **Historical document.** This describes the original fixed-resource Shield Relay transaction from HD2Runtime 0.4.0. The runtime still accepts it so old mods keep working, but it is not how new mods are written. For the current typed API see `getting-started.md` (ownership, patch/transaction/plan) and the `ShieldRelayRecreation` example project.

The typed equivalent targets `hd2.stratagem('FX-12 Shield Generator Relay'):deployed_entity():shield()` and the relay's other owners separately, one transaction or plan operation per owning object.

Version 0.4.0 adds `hd2.transaction()` and `hd2.ensure()` on top of the same
fresh resolver and guarded write engine used by `hd2.patch()`.

The Shield Relay proof declaration is the complete mod entrypoint behavior:

```lua
local hd2=require('mods/skyeshade/hd2runtime')
return hd2.ensure({
    transaction={
        id='shield-relay-proof',
        target=hd2.stratagem('Shield Relay'),
        changes={
            {field='radius',expect=15,value=8},
            {field='durability',expect=4000,value=40000},
            {field='lifetime',expect=40,value=90},
            {field='cooldown',expect=90,value=180},
        },
    },
})
```

The entrypoint has no update hook, timer, memory reader, scanner, native call,
address, offset or protection logic. HD2Runtime owns the shared update scheduler.

## Exact mapping

| Logical field | Owned record | Record offset | Encoding | Change |
| --- | --- | ---: | --- | ---: |
| `radius` | ShieldComponentData record 12 | 0 | FP32, 4 bytes | 15 -> 8 |
| `durability` | ShieldComponentData record 12 | 76 | FP32, 4 bytes | 4000 -> 40000 |
| `lifetime` | HellpodPayloadComponentData record 3 | 4 | FP32, 4 bytes | 40 -> 90 |
| `cooldown` | StratagemInfo type 22, group 3 row 1 | 104 | FP32, 4 bytes | 90 -> 180 |

The resource is `0xED13DDC480EC6910`. Cooldown ownership additionally requires
ID `0x880384FF`, package `0xFE0DB34AC2B9AC61`, the two-entry payload list, current
runtime type table, and zero adjacent spawn/failure cooldown fields at offsets
84 and 108. Radius and durability share one page in the reviewed fixture;
lifetime and cooldown use separate pages. Page grouping is derived from freshly
resolved runtime addresses and is never part of the public identity.

Only these four expected/value pairs are enabled. Other targets, fields, values,
duplicate fields, overlapping writes and address-bearing target tables reject
before memory discovery or protection changes.

## Transaction behavior

Every transaction performs fresh build fingerprint validation, bounded allocation
discovery, resource/component ownership validation, grouped-record schema checks,
stable snapshot rereads and an application-time fingerprint reread. It then:

1. Classifies every field from exact encoded bytes. Desired values are retained,
   expected values are planned, and any other value rejects the whole transaction.
2. Captures every ownership/data context and verifies that each target belongs to
   exactly one captured record. All changes validate before the first page opens.
3. Deduplicates touched 4 KiB pages. Each page must be committed private memory,
   owned by the resolved allocation, and READONLY or READWRITE. Already-writable
   pages are not changed.
4. Opens all required read-only pages, rereads every context, and rereads each
   field directly before its exact four-byte write. Writes follow declaration
   order. After every write, the target and all captured non-target bytes are
   verified against the deterministic intermediate state.
5. Restores every touched page in reverse order and verifies its original
   protection. The complete desired state and non-target contexts are reread once
   more before `APPLIED` is returned.

If any write or verification fails, the engine accepts rollback only from the
known pre-transaction value, the desired value, or the exact transferred prefix
reported by the failed native write. It validates all contexts, reverses attempted
fields in reverse order, verifies the original mixed state, and restores all
pages. Unknown third-party bytes or changed ownership refuse rollback rather than
overwrite unexplained state. A failed rollback or protection restoration is
terminal and reported explicitly; the result never claims atomic success.

This provides all-or-nothing behavior when guarded rollback succeeds. Windows
does not make four separate writes CPU-atomic. Interference can make safe rollback
impossible, in which case the result reports possible partial state.

Normal success logs are concise:

```text
[HD2Runtime] transaction shield-relay-proof targets resolved
[HD2Runtime] radius 15 -> 8
[HD2Runtime] durability 4000 -> 40000
[HD2Runtime] lifetime 40 -> 90
[HD2Runtime] cooldown 90 -> 180
[HD2Runtime] non_target_bytes_unchanged=true
[HD2Runtime] protection_restored=true
[HD2Runtime] transaction shield-relay-proof APPLIED
```

Already-desired fields log `field already value`. `diagnostic=true` on the inner
transaction adds component/settings identity, discovery, write, protection,
rollback and guard counters.

## Ensure behavior

`ensure` accepts exactly one `patch` or one `transaction` plus optional
`interval` and `startup_delay`. The default interval is 60 update seconds and the
default startup delay is three update seconds. Update time pauses when game
updates pause; it is not wall-clock time.

Each cycle creates a new one-shot operation, resolves every target again, and
uses no address from an earlier cycle. `APPLIED` and `ALREADY_DESIRED` schedule
the next cycle. An expected value can therefore be safely reapplied later. Any
conflict, build/schema/ownership mismatch, read failure, write failure, rollback
failure or protection failure puts the ensure handle in terminal `rejected`
state. It never repeatedly attacks an unexpected value. `cancel()` prevents all
future cycles but does not restore vanilla values.

The handle exposes `status`, `runs`, `result`, `error`, `kind`, `id`, `interval`
and `cancel()`. Results expose logical identities, field states and counters;
they contain no runtime address.

## Package and validation boundary

Build the standalone proof from a clean commit:

```powershell
py -3.14 -B scripts/build_transaction_proof.py
```

The builder verifies current installed file hashes, runs the complete regression
suite, embeds the source commit and test log, and sets `fixture_fallback=disabled`.
The proof includes the write adapter; read-only and live-validation packages
continue excluding all write modules.

Tests use retained fixtures and test-process memory only. They cover validation
failure before writes, fields sharing a page, multiple pages, expected/desired
mixtures, conflict, short writes, reverse rollback, rollback failure, page
restoration, non-target mutation, packaged loading, 60-second reapplication,
terminal ensure conflict and cancellation. No test deploys, launches HD2 or
writes to its process. The user subsequently confirmed the 0.4.0 proof successful
in live gameplay at `b3ee7326ce53448590a830b924c99e2df6eec179`. The 0.5.0 SDK and
separate runtime packaging have offline verification only.
