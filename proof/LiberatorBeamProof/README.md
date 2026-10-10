# LiberatorBeamProof (EXPERIMENTAL, SOLO ONLY)

**Superseded by `proof/BeamConversionProof` and the beam conversion API (`docs/beam-conversion.md`).** Kept as the
live-proven experiment fallback; it still works on its own, and the Runtime refuses to mix the two (an experiment copy
of the BeamWeapon table refuses every conversion, and the other way round).

This mod live-tests the in-place component swap that makes the **AR-23 Liberator fire LAS-13 Trident pulses**
(`research/docs/component-swap-liberator-beam.md`, `component-swap-liberator-beam-chamber.md`).

It is not a Runtime feature and not part of any release. It needs the HD2Runtime build of branch `exp/liberator-beam`
with `runtime/experiment_liberator_beam.lua` **0.2.x**. With any other Runtime the mod logs `UNAVAILABLE` and does
nothing.

- Startup line: `LiberatorBeamProof 0.2.0 EXPERIMENTAL BUILD`.
- Every Runtime step logs a line starting with `LIBERATOR BEAM:`.

## What changed since 0.1.0

The first live test (0.1.0, L2) applied and restored cleanly, but the Liberator **could not fire**: "Need fresh
I.C.E.", no usable reload.

**The cause.**
- The Liberator's magazine has a chamber (magazine record 201, +156 = 1).
- The game fills the chambered round only from a ProjectileWeapon component, which L2 removes.
- So the weapon never had a round to fire.

**The fix.**
- 0.2.0 adds **L2b**: that one byte becomes 0.
- This is what the 40-K Meltagun has, the one vanilla beam weapon with a magazine: no chamber, it fires while rounds
  remain, and a reload refills the magazine.

**Not a crash.** The two crash dumps from that day are the game's usual exit crash (helldivers2.exe), not the swap.

## Keys

| Key | Step | What it does |
|---|---|---|
| Ctrl+Shift+F1 | L0 | Status, read-only: pins proven, state (vanilla / L1 / L2 / L2b), live Liberators, solo, Trident package |
| Ctrl+Shift+F2 (twice) | L1 | BeamWeapon record 23 := the Trident's record 18, then row 21 := Liberator -> record 23 |
| Ctrl+Shift+F3 (twice) | L2b | L1 if needed, then the Liberator's membership list (ProjectileWeapon 321 out, BeamWeapon 270 in), then its magazine chamber byte (record 201 +156: 1 -> 0) |
| Ctrl+Shift+F4 (twice) | L4 | Restore: the chamber byte, the list, row 21, then record 23 |

- A write key needs a second press within 6 s.
- Do not install this mod together with the Pelican proofs: they use Ctrl+Shift+F1/F2/F4 too.

## Rules (every write and the restore refuse otherwise)

- **Solo only.** Any other player in the lobby, or an unreadable lobby, refuses. Play Private/Friends-only alone.
- **Zero live Liberators.** No AR-23 Liberator entity may exist at a write or at the restore.
  - **Equip another primary and do not open the armory**: its preview spawns one.
  - In a mission, no Liberator may exist anywhere.
- **L2b needs the Trident's package** (`laser_shotgun`). The mod requests it at load. If L0 says it is not resident,
  equip the LAS-13 Trident once, then switch back to another primary.
- **Every pin and every before byte must match the research.**
  - That is 160 code pins, plus the BeamWeapon row and record, the list, and the magazine row and byte.
  - Otherwise you see `REFUSED` / `UNPROVEN`, and nothing is written.
- **Restart the game after using L2b.** Each Liberator spawned with the swap leaves a ProjectileWeapon copy that
  nothing removes until the game exits.
- **Other HD2Runtime mods.** While the swap is applied:
  - writes to the Liberator's fire rate, projectile, ammunition and damage are refused (dormant);
  - its WeaponData fields (spread, recoil, ergonomics...) still apply.

## Test plan (solo, least to most risky)

1. **L0, read-only (ship).** Equip another primary and leave the armory unopened. Press Ctrl+Shift+F1.
   - Expect: `pins proven; state vanilla (row 21 vanilla, record 23 vanilla, list vanilla, magazine chamber 1
     (vanilla)); live Liberators 0; solo true; Trident package resident`.
   - **Abort** on any other state, a refusal, or live Liberators > 0.
2. **L2b, full swap (ship).** With L0 showing live Liberators 0 and the Trident package resident, press Ctrl+Shift+F3
   twice.
   - Expect `L1 APPLIED`, `L2 APPLIED` and `L2b APPLIED`.
   - L0 now shows `state L2b (... magazine chamber 0 (L2b))`.
3. **The mission.** Equip the Liberator and deploy solo. Expect:
   - Trident pulses at 300 rpm, with the Trident beam and sound;
   - the HUD showing a full magazine;
   - one round per pulse;
   - when the magazine is empty, a normal Liberator reload back to a full magazine;
   - no heat bar and no overheat;
   - the fire-rate selector doing nothing.

   An **empty** magazine still says "Need fresh I.C.E." on the trigger. This is cosmetic: it is the Trident's
   empty-weapon line.

   **Abort** on any of these, and send the log and the crash dump:
   - a crash at spawn or on the first shot;
   - an invisible beam;
   - bullets still firing;
   - a weapon that still cannot fire with rounds in it.
4. **L3, lifecycle (same mission).** Do each of these:
   - empty the magazine and reload;
   - resupply;
   - drop and pick up the weapon;
   - die and reinforce;
   - call a Laser Sentry.

   Expect no crash and a normal sentry. **Abort** if another beam weapon or an enemy weapon misbehaves.
5. **L4, teardown.** Extract. On the ship, switch the primary away from the Liberator and wait until L0 shows live
   Liberators 0.
   - Press Ctrl+Shift+F4 twice. Expect `L2b RESTORED`, `L2 RESTORED`, then `RESTORED: every byte is vanilla again`.
   - **Quit the game.** Play a vanilla mission in the next session.
   - If L0 never reaches 0 live Liberators, **quit without restoring**: the game reloads the entity file at start.

For each step, report:
- the `LIBERATOR BEAM:` lines of the log;
- what you saw: rounds on the HUD, beam visible or not, reload;
- any crash.
