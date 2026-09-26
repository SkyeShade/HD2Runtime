# HD2Runtime live read-only validation

This package is a standalone HD2Runtime addon plus a one-shot validation client
for Bingus Shared Loader v15+ / API 1. It contains the generic runtime, pinned
schemas and comparison expectations. No sibling project, test fixture, external
Python script or old developer-report addon is needed at runtime. Bingus remains
a separate dependency. Use this package instead of the previous HD2Runtime report
package; it shares the runtime's manager GUID and resource namespace.

The build does not deploy or launch HD2. No new live result is claimed by creating
the ZIP. Actual successful live resources are **none yet confirmed in this task**.
The package's `build-report.json` records this distinction and its source commit.

## What happens on load

After three update seconds, validation resolves JAR-5, AMR, Bastion, Orbital Laser,
Shield Relay and Jump Pack sequentially. Each resource uses the public `describe`
and `observe` APIs. A failed resource is logged and the next resource is attempted.
There is no fallback to stored values. All values come from a successful runtime
read; expectation numbers are only comparison operands.

Each observation revalidates the EXE/DLL fingerprints, bounded unique allocation
discovery, membership/record ownership, settings joins and stable rereads. The
Win32 adapter declares no memory-write or protection-changing function. `patch`,
`ensure` and `transaction` still reject calls.

Discovery permits at most 64 guarded read/query operations and 64 KiB requested
memory reads per coroutine step. Each attempt has limits of 100,000 queries and
16 MiB memory reads. Missing modules/roots retry at five-update-second intervals
up to six attempts. Each resource has a 180-update-second / 10,000-step observation
limit. Fingerprinting reads the two module files synchronously, outside the memory
discovery loop. After all resources terminate, the validation callback detaches
when it still owns `update`; later wrappers continue to work.

Logs go to the console and Bingus's `HD2Runtime.log`, normally under
`%LOCALAPPDATA%/CowboyBingus/Helldivers2/Logs/`. File logging failures are reported
on the console. Initialization failure also reports on the console if the generic
logging capability cannot be initialized.

## Current expectations and exact identities

| Resource | Hex identity | Reviewed ownership and values |
| --- | --- | --- |
| JAR-5 Dominator | `0x80F1A156D9FA1E36` | ProjectileWeaponComponentData index 321 / record 211; projectile 177 at group 0 / row 262; DamageSettings type 153 at group 1 / row 158; standard 275, durable 90, penetration lanes `[3,3,3,0]` |
| AMR | `0x89C5493E08CA4207` | WeaponDataComponentData index 236 / record 354; crosshair_type 3 |
| Bastion | `0x16474112801385B6` | HealthComponentData index 224 / record 104; main HP 8000; default AP4; zones 0–5 and 12–30 AP4; zones 6–11 AP2; unused zones 31–37 AP0; zone 3/4 AffectsMainHealth 1.0 |
| Orbital Laser | `0xEC3575E7A93793BB` | OrbitalAbilityComponentData index 308 / record 0; linked DamageSettings type 513 / group 1 / row 504; standard 60, durable 60, interval approximately 0.1 |
| Shield Relay | `0xED13DDC480EC6910` | ShieldComponentData index 94 / record 12; radius 15, durability 4000; HellpodPayloadComponentData index 164 / record 3, lifetime 40; StratagemSettings type 22 / group 3 / row 1, cooldown 90 |
| Jump Pack | `0x59C5CA839449B379` | RechargeComponentData index 99 / record 1, recharge 15; JumppackComponentData index 264 / record 1, vertical_launch_velocity 40; reviewed scalar +0x04 = 20 and +0x24 = 60 |

The two additional Jump Pack scalars remain structural candidates. Their public
aliases `movement_scalar_04` and `movement_scalar_24` do not assert horizontal
speed or another unproven behavior. AP's scalar alias is lane 0; three additional
lane reads expose the full `[3,3,3,0]` array. The report covers **62 fields**.

## Expected log format

Illustrative lines from a successful live AMR validation (not a captured result):

```text
[HD2Runtime] LIVE_VALIDATION resource=amr id=0x89C5493E08CA4207 label="AMR" mode=live stable_snapshot=true
[HD2Runtime] LIVE_VALIDATION resource=amr id=0x89C5493E08CA4207 ownership component=WeaponDataComponentData type=0x88E4DBB1 record_type=WeaponDataComponent record_index=354 unique_owner=true component_index=236 ...
[HD2Runtime] LIVE_VALIDATION resource=amr id=0x89C5493E08CA4207 field=crosshair_type observed=3 expected=3 status=MATCH ownership=VERIFIED component=WeaponDataComponentData record_index=354
[HD2Runtime] LIVE_VALIDATION resource=amr id=0x89C5493E08CA4207 field=crosshair_type provenance=ReticleAmr/research/gameplay-confirmation-0.1.0.json structural_candidate=true schema_labelled=true current_live_ownership_proven=true gameplay_proven=true native_consumer_proven=false
[HD2Runtime] LIVE_VALIDATION resource=amr id=0x89C5493E08CA4207 status=LIVE_PASS queries=... bytes_read=... writes=0 protection_changes=0 fixture_fallback=disabled
```

Every field reports observed and expected values independently. A value of 4
prints `observed=4 expected=3 status=MISMATCH`; it is never replaced with 3 in
the report or in memory. A failed read prints `status=ERROR adapter=<exact stage>
code=<failure category> reason=<guard failure> observed=unavailable`. Expected
values alone cannot produce a pass. Float output uses nine significant digits;
the FP32 value for interval may print `0.100000001`, with an explicit 1e-8
comparison tolerance. All other baseline comparisons are exact numeric values.

Per-resource terminal statuses are `LIVE_PASS`, `VALUE_MISMATCH`,
`OWNERSHIP_MISMATCH`, `NOT_LIVE`, or `ERROR`. `NOT_LIVE` rejects fixture-mode
results even when all their values match. The summary distinguishes
`live_resolved` (valid live ownership, possibly different values) from `passed`
(valid live ownership and all baseline expectations matched):

```text
[HD2Runtime] LIVE_VALIDATION_SUMMARY completed=6/6 live_resolved=6 passed=6 commit=<40-character source commit> writes=0 protection_changes=0 fixture_fallback=disabled
```

Ownership scope is the named resource/component or a checked settings linkage.
A unique typed damage row is not a certificate of exclusive native consumers.
Gameplay/native-consumer evidence retains its prior meaning and is not promoted
by a successful memory read. Source file hashes are included in `provenance.json`.

## Adapter audit and remaining live evidence

| Adapter | Runtime implementation | Validation limit |
| --- | --- | --- |
| `runtime/windows_readonly.lua` | Native module hashes, memory metadata and guarded memory reads | Exercised on the offline process's own buffer; HD2 process execution remains untested here |
| `runtime/discover.lua` + `core/entity.lua` | Live allocation enumeration and resource/member/index joins | Regressed on retained sparse bytes, relative/relocated pointers and failure mutations |
| `core/settings.lua` | Live generated projectile/damage allocations with typed records | Regressed on retained complete settings buffers, including relocated pointers |
| `core/stratagem.lua` | Checked game.dll-relative root, PE bounds, current runtime table, package/payload join | Only the relay record is a saved live capture; surrounding grouped tables in tests are synthetic. Full live integration remains unconfirmed |

**No runtime adapter is implemented only as a fixture lookup.** No fixture file
is shipped, and no runtime fallback exists. The fixture backend in `tests/memory.lua`
is intentionally test-only. The stratagem adapter has the most limited captured
coverage; this is a live-validation gap, not evidence that it successfully works
in the current game process. Any failure reports its exact stage so that a
returned log can identify an incomplete adapter without weakening its guards.

## Building and regression coverage

```powershell
py -3.14 -B -m unittest discover -s tests -v
py -3.14 -B scripts/build_live_validation.py
```

The builder requires a clean local source commit, verifies all seven installed
file fingerprints in `schemas/build_files.json`, runs tests and packages only
HD2Runtime modules. `HD2_GAME_ROOT` can select the owned installation. Tests use
its standalone `lua51.dll`, never `game.dll` or the game executable.

Coverage includes all baseline fields, linked record identities, incremental
discovery, wrong builds, pointer/ownership/schema/reread failures, value mismatch
reporting, fixture rejection, continuation after a failed resource, callback
cleanup, archive inventory and absence of write capability. The ZIP contains
`tests.txt`, its source commit and build fingerprint report. Offline fixture
output remains labelled `mode=fixture` / `NOT_LIVE`.
