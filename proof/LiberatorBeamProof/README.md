# LiberatorBeamProof (EXPERIMENTAL, SOLO ONLY)

Live test of the in-place component swap that makes the **AR-23 Liberator fire LAS-13 Trident pulses**
(research/docs/component-swap-liberator-beam.md). Not a Runtime feature and not part of any release: it needs the
HD2Runtime build of branch `exp/liberator-beam` (`runtime/experiment_liberator_beam.lua`). With any other Runtime the
mod logs `UNAVAILABLE` and does nothing.

Startup line: `LiberatorBeamProof 0.1.0 EXPERIMENTAL BUILD`. Every Runtime step logs a line starting with
`LIBERATOR BEAM:`.

| Key | Step | What it does |
|---|---|---|
| Ctrl+Shift+F1 | L0 | Status, read-only: pins proven, state (vanilla / L1 / L2), live Liberators, solo, Trident package |
| Ctrl+Shift+F2 (twice) | L1 | BeamWeapon record 23 := the Trident's record 18, then row 21 := Liberator -> record 23 |
| Ctrl+Shift+F3 (twice) | L2 | The Liberator's membership list: ProjectileWeapon (321) out, BeamWeapon (270) in |
| Ctrl+Shift+F4 (twice) | L4 | Restore: the list, then row 21, then record 23 |

Write keys need a second press within 6 s. Do not install this mod together with the Pelican proofs (they use
Ctrl+Shift+F1/F2/F4 too).

## Rules (every write and the restore refuse otherwise)

- **Solo only.** Any other player in the lobby (or an unreadable lobby) refuses. Play Private/Friends-only alone.
- **Zero live Liberators.** No AR-23 Liberator entity may exist at the write or at the restore. **Equip another
  primary and do not open the armory** (its preview spawns one); in a mission, no Liberator anywhere.
- **L2 needs the Trident's package** (`laser_shotgun`). The mod requests it at load; if L0 says it is not resident,
  equip the LAS-13 Trident once, then switch back to another primary.
- **Every pin and every before byte must match the research**, else `REFUSED` / `UNPROVEN` and nothing is written.
- **Restart the game after using L2.** Each Liberator spawned with the swap leaves a ProjectileWeapon copy that
  nothing removes until the game exits.
- Other HD2Runtime mods: while the swap is applied, writes to the Liberator's fire rate, projectile, ammunition and
  damage are refused (dormant); its WeaponData fields (spread, recoil, ergonomics...) still apply.

## Test plan (solo, least to most risky)

1. **L0, read-only (ship).** Another primary equipped, armory unopened. Press Ctrl+Shift+F1. Expect: `pins proven;
   state vanilla (row 21 vanilla, record 23 vanilla, list vanilla); live Liberators 0; solo true; Trident package
   resident`. **Abort** on any other state, a refusal, or live Liberators > 0.
2. **L1, row and record only.** Press Ctrl+Shift+F2 twice: `L1 APPLIED`. Then equip the Liberator and play a solo
   mission. **Expect no change**: bullets, normal sound, no beam. Laser Sentry / Scythe beams unchanged.
   **Abort** on any difference: extract, equip another primary, restore with Ctrl+Shift+F4 (twice).
3. **L2, full swap (ship).** Equip another primary again (L0 must show live Liberators 0 and the Trident package
   resident), press Ctrl+Shift+F3 twice: `L2 APPLIED`. Then equip the Liberator and deploy solo. Expect:
   - Trident pulses at 300 rpm, the Trident beam and sound;
   - one round per pulse from the 45-round magazine, the normal Liberator reload;
   - no heat bar, no overheat; the fire-rate selector does nothing.
   **Abort** on a crash at spawn or on the first shot, an invisible beam, or bullets still firing (send the log and
   the crash dump).
4. **L3, lifecycle (same mission).** Empty the magazine and reload; resupply; drop and pick up the weapon; die and
   reinforce; call a Laser Sentry. Expect no crash and a normal sentry. **Abort** if another beam weapon or an enemy
   weapon misbehaves.
5. **L4, teardown.** Extract. On the ship switch the primary away from the Liberator and wait until L0 shows live
   Liberators 0. Press Ctrl+Shift+F4 twice: `RESTORED: every byte is vanilla again`. **Quit the game.** Play a
   vanilla mission in the next session. If L0 never reaches 0 live Liberators, **quit without restoring** (the game
   reloads the entity file at start).

Report for each step: the `LIBERATOR BEAM:` lines of the log, what you saw, and any crash.
