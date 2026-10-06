# BeaconTimingProof 0.1.0 (development only): the beacon timing API

The live proof of `runtime/beacons.lua`, the development beacon API (not public yet). It sets a single beacon's
timing semantically:

| API value | Meaning |
| --- | --- |
| `call_in_time` | countdown - activation threshold: the time to the activation, counted once the beacon has landed |
| `lifetime_after_activation` | the activation threshold: how long the beacon remains after its activation (its beam) |

Setting one keeps the other. The raw countdown and activation threshold are also readable, and settable explicitly.

Solo host; no multiplayer change; not part of the Gas Barrage.

## What is written

Each change is **one guarded transaction on that beacon's element only**: its countdown, its threshold and, in the
option, its type. It is refused, with nothing written, unless:
- the pins prove, in a mission, as solo host;
- the beacon is present with the expected type, not activated and not a remote copy;
- its current timers are sane (threshold > 0, countdown >= threshold) and exactly as observed;
- a new delivery's call-in package is resident;
- the resulting timers are sane (threshold > 0, countdown >= threshold, at most 120 s).

Afterwards every written member is read back, the others are compared, the non-target bytes checked and the
protection restored. **Never written:** any StratagemInfo, component, projectile or bombardment record, the mission
record, the save, the account.

## Modes (Mod Options > Beacon Timing Proof)

| Mode | AC-8 Autocannon beacon |
| --- | --- |
| **Default** | in its first update: call-in **6.0 s**, lifetime kept (1 write); 2 s later, before its activation: lifetime after activation **15.0 s**, the remaining call-in kept (2 writes); after its activation: one more change is attempted and must be **refused** (ACTIVATED). The delivery stays the native AC-8 |
| "120mm delivery with a native 120mm's timing" | in its first update, in one transaction: the delivery Orbital 120mm HE Barrage, call-in **4.0 s**, lifetime after activation **22.4 s** (3 writes). The barrage's counters are logged, as read at its creation |

## Live test

1. Install `HD2Runtime-0.28.0-runtime.zip` (this build) and `BeaconTimingProof-0.1.0.zip`. Remove or disable
   BeaconRedirectProof. The first proof line is `BeaconTimingProof 0.1.0 BEACON TIMING API BUILD`.
2. Put **AC-8 Autocannon** in your loadout. Start a **solo** mission. Wait for `BEACON TIMING READY`.
3. **Default mode:** throw the AC-8 once, preferably at your feet (so it lands at once). Expect:
   - `BEACON TIMING APPLIED (first update): … -> call-in 6.000 s …; verified true`;
   - `BEACON TIMING APPLIED (2.x s later, before its activation): … lifetime after activation 15.000 s …; verified
     true`;
   - **the pod about 6 s after the beacon landed** (natively about 0 to 2.4 s);
   - `BEACON TIMING GUARD: a change after the activation: refused ACTIVATED`;
   - **the beam remaining about 15 s after the pod was dispatched**;
   - `TIMING RESULT: …`.
4. **Option** (a new solo mission; the 120mm need not be in the loadout): throw the AC-8 once. Expect:
   - `BEACON TIMING APPLIED (first update): …, delivery AC-8 Autocannon -> Orbital 120mm HE Barrage; … call-in 4.000 s,
     lifetime after activation 22.400 s …; verified true …, 3 writes`;
   - the 120mm barrage about 4 s after landing;
   - `BARRAGE: … counters at creation …`, then `BARRAGE: … removed … shells fired N (counter a -> b) …`.
5. **Send** every line starting with `BEACON TIMING`, `TIMING RESULT`, `BARRAGE` or `MISSION START`, plus what you
   saw: when the pod or shells came, and how long the beam stayed.
6. **On a crash:** keep the newest dump and the Runtime log.
