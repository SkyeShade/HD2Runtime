# BeamConversionSyncProof

Development proof for the HD2Runtime beam conversion sync (`docs/beam-conversion.md`, "Multiplayer";
`research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md`). It uses only the public API:
`hd2.weapon(name):beam_conversion()` and `hd2.ensure`. The Runtime itself does the sync: it posts this machine's
conversions under the lobby key `hd2bc`, reads every other member's, and logs `BEAM CONVERSION SYNC:` lines.

## What this proof can and cannot show

**Multiplayer conversions stay refused, even with identical options on both machines.** The research proved that the
game applies another player's weapon through its network type alone. A weapon built from a converted list therefore
crashes the game when it belongs to someone else, whatever that player converted. If both of you convert the Liberator
and both carry it, **both games crash**.

This test therefore checks that:

- the sync channel works between two machines;
- every member state and decision is correct;
- the restores happen before anything can crash;
- the warnings reach the right player.

It never puts a converted weapon type in two players' hands.

## Options

MODS tab, page **Beam Conversion Sync Proof**. Everything is off by default.

| Option | Effect |
|---|---|
| Sickle: Trident pulses | converts the LAS-16 Sickle |
| Liberator: Trident pulses | converts the AR-23 Liberator at the rate below |
| Liberator rate | 600 rpm (the same on both machines) or 450 rpm (deliberately different: another digest). **Choose it before turning the Liberator on.** |

A conversion applies **only solo**, and only while no instance of that weapon exists on your machine:

1. Unequip it and keep the armory closed.
2. Turn the option on and wait for `APPLIED`.
3. Then equip it.

Restart the game after the session.

## Two-machine test plan (players A = host, B = client)

Both install the **same** HD2Runtime build and this proof. Keep `HD2Runtime.log` from both machines for every step.

**Step 1: solo, identical options, the same digest.**

1. Each player alone: turn on Sickle and Liberator (600 rpm) with both unequipped, and wait for two `APPLIED`.
2. Optionally equip each weapon and fire it at the ship's range. Each fires Trident pulses; the Liberator is faster.
3. **Unequip both again.**
4. Compare the two logs. The lines `BEAM CONVERSION SYNC: posting seq 2: AR-23 Liberator, LAS-16 Sickle (hd2bc/1;...)`
   must carry the **same** digest (the 6th `;` field) and the same entries on both machines.
5. Then B, still solo: turn the Liberator off (unequipped; wait for the restore), set the Liberator rate to 450, and
   turn it on again. B's new posting line must show a **different** Liberator record digest and a different set
   digest. Set it back to 600 the same way.

**Step 2: B joins A's lobby, nothing converted in hand.**

1. A equips weapons **other than** the Sickle and the Liberator.
2. B joins A's lobby with both converted weapons unequipped.
3. Expected on both machines, within about a second of the lobby showing two members:
   - `BEAM CONVERSION: ANOTHER PLAYER IS PRESENT (...): restored AR-23 Liberator, LAS-16 Sickle`;
   - then `BEAM CONVERSION SYNC: posting seq N: nothing converted`;
   - `member <peer>: pending` (the other machine has not posted in this lobby yet), then, 10 to 30 s after the join,
     `member <peer>: match (the same conversions (...))`, with `(host)` on B's side;
   - `decision REFUSED (PENDING)`, then `decision REFUSED (REMOTE_APPLY_UNSAFE)`.
4. The proof's ensures log `NOT_SOLO ... BEAM CONVERSION SYNC: REFUSED (...)` and keep waiting. No crash.
5. Both may now equip any weapon. Everything is vanilla again.

**Step 3: the mismatch path, one converted weapon in hand on each side.**

1. B leaves. Both players are solo; the ensures convert again.
2. Each player, solo, with weapons unequipped:
   - A turns the **Sickle off** (the Liberator stays on);
   - B turns the **Liberator off** (the Sickle stays on).
3. A equips the converted Liberator. B equips the converted Sickle.
4. B joins A's lobby. **Neither player may carry, call in or pick up the other's weapon type.**
5. Expected on both machines:
   - `member <peer>: mismatch (...)` and `decision REFUSED (MISMATCH)`;
   - the loud `WARNING: ANOTHER PLAYER IS PRESENT` (your converted weapon is in use and stays converted);
   - `BEAM CONVERSION SYNC: WARNING: member <peer> has <their weapon> converted`, plus the notice, naming the **other**
     player's weapon: AR-23 Liberator on B, LAS-16 Sickle on A.
6. No crash. Each machine builds the other's weapon from its own vanilla list.

**Step 4: a player without the Runtime joins.**

1. A keeps the converted Liberator in hand.
2. C (no HD2Runtime) joins A's lobby **without a Liberator**.
3. Expected on A:
   - the warnings;
   - `member <C>: pending`, then after 30 s `no runtime` and `decision REFUSED (NO_RUNTIME)`.
4. No crash. A C carrying a Liberator **would** crash A's game. That case is documented as unsafe; do not test it.

## What to report

For each step:

- the `BEAM CONVERSION`, `BEAM CONVERSION SYNC`, `PEER CHANNEL` and `[BeamConversionSyncProof]` lines of both logs;
- any notice shown;
- any crash, with the newest dump.

What would show the model wrong:

- a different digest for identical options (step 1);
- a `match` with different options;
- a restore that does not happen within a few seconds of the join;
- any crash in steps 2 to 4.
