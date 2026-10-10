# BeamConversionSyncProof

Development proof for the HD2Runtime beam conversion sync (`docs/beam-conversion.md`, "Multiplayer";
`research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md`, `research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md`).
It uses only the public API: `hd2.weapon(name):beam_conversion()` and `hd2.ensure`. The Runtime itself does the sync:
it posts this machine's conversions under the lobby key `hd2bc` (`hd2bc/2`), reads every other member's, and logs
`BEAM CONVERSION SYNC:` lines.

## What changed in 0.2.0

The **add layout** keeps ProjectileWeapon and adds BeamWeapon, so every machine has the instance the game's network
apply looks up. The swap layout crashed the game when another player's weapon of a converted type spawned; the add
layout has no such path. The research's verdict:

- **Identical conversions on every machine: allowed.** Both players may carry the converted weapon. Every machine draws
  every player's beam from the replicated trigger. Health damage is applied once, by the shooter's machine.
- **Different conversions, or a player without the Runtime: refused.** No crash, but one machine draws beams where the
  other draws bullets. Zone health and shields follow each machine's own simulation, so they would drift.
- **The swap layout stays solo only.** That is the Liberator here.

Not live-tested yet. This proof is that test.

## Options

MODS tab, page **Beam Conversion Sync Proof**. Everything is off by default.

| Option | Layout | Effect |
|---|---|---|
| Sickle: Trident pulses | add | converts the LAS-16 Sickle at the rate below |
| Sickle rate | | 600 rpm (the same on both machines) or 450 rpm (deliberately different: another digest). **Choose it before turning the Sickle on.** |
| Talon: Trident pulses | add | converts the LAS-58 Talon |
| Liberator: Trident pulses | swap | converts the AR-23 Liberator (solo only) |

A conversion is written only while no instance of that weapon exists on your machine, other players' included:

1. Unequip it and keep the armory closed.
2. Turn the option on and wait for `APPLIED`.
3. Then equip it.

## Two-machine test plan (players A = host, B = client)

Both install the **same** HD2Runtime build and this proof. Keep `HD2Runtime.log` from both machines for every step.

**Step 1: solo, identical options, the same digest.**

1. Each player alone, with the weapons unequipped: Sickle rate 600, Sickle on, Talon on. Wait for two `APPLIED`, each
   logged as `CONVERTED [add layout, ...]`.
2. Compare the two logs. The lines `BEAM CONVERSION SYNC: posting seq 2: LAS-16 Sickle, LAS-58 Talon (hd2bc/2;...)`
   must carry the **same** digest (the 6th `;` field) and the same entries (`....a.o.....`) on both machines.

**Step 2: B joins A's lobby, identical conversions, nothing in hand.**

1. Both keep the Sickle and the Talon unequipped. B joins A's lobby.
2. Expected on both machines:
   - `member <peer>: pending`, then 10 to 30 s after the join `member <peer>: match (the same conversions (...))`;
   - then `decision ALLOWED (ALL_MATCH)`;
   - **no** `restored` line: add conversions are kept while the other player is pending or matching;
   - with nothing in hand, the Runtime may log `another player is present (...): add-layout conversions kept: ...`.
3. No crash.

**Step 3: both carry the converted Sickle (the case the swap layout could never allow).**

1. Both equip the converted Sickle and deploy together on an easy mission.
2. Each player fires at enemies. On **both** screens:
   - each player's Sickle fires Trident pulses, never bullets;
   - the other player's pulses are drawn too.
3. Damage: shoot the same enemies. They should die as fast as with one shooter's pulses per hit. No double damage,
   and no enemy that dies on one screen but not the other.
4. Lifecycle:
   - one player drops their Sickle and the other picks it up;
   - die and reinforce;
   - call a resupply.

   No crash at any of these steps.
5. Heat: each Sickle overheats and changes heat sinks as solo.
6. Extract.

**Step 4: a converging Runtime (the Talon converts in the lobby).**

1. Back on the ship, B leaves. B, solo, with the Talon unequipped, turns the **Talon off** and waits for the restore.
   A keeps the Talon converted, also unequipped.
2. B joins A's lobby with the Talon still off. Expected on A: `another player is present (...): add-layout
   conversions kept: LAS-58 Talon (CONVERGING: ...)`. B is a Runtime whose set is still changing, so A waits 30 s.
3. Within those 30 s, B turns the Talon on, still unequipped. Expected:
   - B: `APPLIED` without leaving the lobby. A already holds the identical Talon, so the lobby agrees.
   - A: `member B: match`. A **never** logs `restored LAS-58 Talon`.
4. If B is too late, A restores the idle Talon after the grace. Then both ensures wait `NOT_AGREED`: **a weapon converts
   in a lobby only when every other player already holds it.** Leave, convert solo, join again.

**Step 5: the mismatch path.**

1. B leaves. B, solo, with the Sickle unequipped: Sickle off, wait for the restore, Sickle rate 450, Sickle on. B's
   posting line must show a **different** Sickle record digest.
2. Both keep the Sickle unequipped. B joins.
3. Expected on both machines:
   - `member <peer>: mismatch`;
   - `has LAS-16 Sickle converted (add layout) differently from this machine`;
   - after the 30 s grace, `restored LAS-16 Sickle (MISMATCH: ...)`.
   - The proof's Sickle ensure then waits `NOT_AGREED (MISMATCH ...)`. No crash.

**Step 6: the swap layout stays solo.**

1. Both players solo. A turns the Liberator on, with it unequipped. `APPLIED`, logged `CONVERTED [swap layout, ...]`.
2. B joins A's lobby. Expected on A:
   - `restored AR-23 Liberator (swap layout: solo only)` within about a second;
   - the Liberator ensure waits `NOT_SOLO`.
3. **Neither player may carry the Liberator until A's restore line is logged.**

**Step 7 (optional): a player without the Runtime.**

1. A keeps the Sickle converted and in hand. C (no HD2Runtime) joins A's lobby.
2. Expected on A:
   - `member <C>: pending`, then after 30 s `no runtime` and `decision REFUSED (NO_RUNTIME)`;
   - the warning that the Sickle cannot be restored while it is in use.
3. If C carries a Sickle, there is still no crash on either side. A draws pulses for C's Sickle and C draws bullets for
   A's. Report what each player sees.

## What to report

For each step:

- the `BEAM CONVERSION`, `BEAM CONVERSION SYNC`, `PEER CHANNEL` and `[BeamConversionSyncProof]` lines of both logs;
- what each player saw of the other's weapon;
- any notice shown;
- any crash, with the newest dump from both machines.

What would show the model wrong:

- any crash in steps 2 to 7;
- a bullet from a converted Sickle on either screen in step 3;
- double damage, or enemies dying on one screen only (step 3);
- a different digest for identical options (step 1), or a `match` with different options (step 5);
- an add conversion restored while the other player matches (step 2).
