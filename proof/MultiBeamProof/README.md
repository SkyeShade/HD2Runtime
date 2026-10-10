# MultiBeamProof (EXPERIMENTAL, SOLO ONLY)

This mod live-tests the **LAS-13 Trident beam on three weapons at once**: the **AR-23 Liberator**, the **LAS-58
Talon** and the **SMG-32 Reprimand** (`research/docs/multi-beam-swap-F5FEE03DCFDB.md`). It generalises the
live-proven Liberator swap of LiberatorBeamProof 0.2.0.

It is not a Runtime feature and not part of any release. It needs the HD2Runtime build of branch `exp/multi-beam` with
`runtime/experiment_beam_swap.lua` **0.1.x**. With any other Runtime the mod logs `UNAVAILABLE` and does nothing.

- Startup line: `MultiBeamProof 0.1.0 EXPERIMENTAL BUILD`.
- Every Runtime step logs a line starting with `MULTI BEAM:`; each status prints one line per weapon,
  `MULTI BEAM: <weapon>: <state> (...)`.
- The Liberator-only path stays available: **LiberatorBeamProof 0.2.0** (Ctrl+Shift+F1..F4) runs on the same Runtime
  build. Use one proof at a time (each refuses a table the other changed, except that this one recognises
  LiberatorBeamProof's L2b Liberator as its own and can restore it).

## What it writes

| Weapon | BeamWeapon row | Membership list | Ammunition |
|---|---|---|---|
| AR-23 Liberator | 21 | ProjectileWeapon out, BeamWeapon in | magazine record 201 +156: 1 -> 0 (no chamber) |
| LAS-58 Talon | 11 | ProjectileWeapon out, BeamWeapon in | none: a heat weapon, its own heat and heat sinks |
| SMG-32 Reprimand | 25 | ProjectileWeapon out, BeamWeapon in | magazine record 139 +156: 1 -> 0 (no chamber) |

- All three rows name **one** BeamWeapon record, 23, which becomes a byte copy of the Trident's record 18 (written once,
  restored last).
- One write per key press, **all or nothing**: if any byte fails, everything written in that press is rolled back.
- Restore runs in reverse order: the Reprimand, the Talon, the Liberator, then record 23.

## Keys

| Key | What it does |
|---|---|
| Ctrl+Alt+F5 | Status, read-only: pins, record 23, per weapon state (vanilla / applied / partial / foreign) and live count, solo, Trident package, the F6 set |
| Ctrl+Alt+F8 | Choose the set F6 applies: all three (default) -> Liberator only -> Talon only -> Reprimand only -> all three. Writes nothing |
| Ctrl+Alt+F6 (twice) | Apply the chosen set |
| Ctrl+Alt+F7 (twice) | Restore every swapped weapon, then record 23 |

- A write key needs a second press within 6 s.
- These keys are used by no other proof in the repository (the Pelican proofs use Ctrl+Shift+F-keys).

## Rules (every write and the restore refuse otherwise)

- **Solo only.** Any other player in the lobby, or an unreadable lobby, refuses. Play Private/Friends-only alone.
- **Zero live instances of every weapon written.** No Liberator, Talon or Reprimand entity may exist at the apply or
  at the restore (only the weapons that press writes are counted).
  - **On the ship, equip a primary other than the Liberator and the Reprimand, a secondary other than the Talon, and
    do not open the armory**: its preview spawns one.
- **Apply needs the Trident's package** (`laser_shotgun`). The mod requests it at load. If the status says it is not
  resident, equip the LAS-13 Trident once, then switch away again.
- **Every pin and every before byte must match the research** (188 code pins, the rows, record 23, the three lists,
  the two magazine rows and bytes). Otherwise you see `REFUSED` / `UNPROVEN`, and nothing is written.
- **Restart the game after using it.** A Liberator spawned while swapped leaves a ProjectileWeapon copy (its default
  ammunition) that nothing removes until the game exits; a Reprimand with a muzzle attachment does too. The Talon
  leaves none.
- **Other HD2Runtime mods.** While a weapon is swapped, writes to its fire rate, projectile, ammunition and damage are
  refused (dormant); its other fields still apply.

## Test plan (solo, least to most risky)

1. **Status (ship).** Equip, for example, the SG-8 Punisher and the P-2 Peacemaker; leave the armory unopened. Press
   Ctrl+Alt+F5.
   - Expect `record 23 vanilla`, three `MULTI BEAM: <weapon>: vanilla (...); live 0` lines, `solo true`,
     `Trident package resident`.
   - **Abort** on any other state, a refusal, or a live count above 0.
2. **Apply all three (ship).** Press Ctrl+Alt+F6 twice (the default set is all three).
   - Expect `AR-23 Liberator APPLIED`, `LAS-58 Talon APPLIED`, `SMG-32 Reprimand APPLIED`, then `APPLIED (record 23
     Trident copy; ... applied ...)`, and three `applied` lines.
3. **Mission 1: Liberator + Talon.** Equip the Liberator and the Talon and deploy solo. Expect:
   - **Liberator** (as live-proven): Trident pulses at 300 rpm with the Trident beam and sound; one round per pulse;
     a normal reload to a full magazine; no heat bar.
   - **Talon**: Trident pulses with the Trident beam and sound; **heat** rises per pulse (from
     the Talon's own heat record: heat per shot 15, capacity 100, as the Trident uses its own) and a heat-sink swap
     ("Changing I.C.E.") works; no laser bolts.
     - Not traced offline: whether its semi-automatic trigger gives one pulse per click or pulses while held. Either
       is fine; please report which.
   - **Abort** (send the log and the crash dump) on a crash at spawn or on the first shot, an invisible beam,
     bullets/bolts still firing, or a weapon that cannot fire.
4. **Mission 2: Reprimand** (extract first; no restore needed between missions). Equip the Reprimand with **no
   muzzle attachment** (its default) and deploy solo. Expect what the Liberator does: Trident pulses, one round per
   pulse from its 25-round magazine, a normal reload.
5. **Lifecycle (either mission).** Empty and reload, resupply, drop and pick up, die and reinforce, call a Laser
   Sentry, swap between primary and secondary. Expect no crash and a normal sentry. **Abort** if another beam weapon
   or an enemy weapon misbehaves.
6. **Restore (ship).** Extract. Equip a primary and a secondary other than the three and wait until the status shows
   `live 0` for all three. Press Ctrl+Alt+F7 twice.
   - Expect `SMG-32 Reprimand RESTORED`, `LAS-58 Talon RESTORED`, `AR-23 Liberator RESTORED`, then `RESTORED (record
     23 vanilla; ... vanilla ...)`.
   - **Quit the game.** Play a vanilla mission in the next session.
   - If the live count never reaches 0, **quit without restoring**: the game reloads the entity file at start.

If something fails with all three, narrow it down: restart, choose one weapon with Ctrl+Alt+F8, apply only that one,
and repeat the mission step for it.

Cosmetic, expected:
- An **empty** Liberator or Reprimand says "Need fresh I.C.E." on the trigger (the Trident's empty-weapon line).
- The armory may show beam stats for the swapped weapons (its stat readers look the BeamWeapon record up by weapon).
- The fire-rate selector of the Liberator and the Reprimand does nothing.

For each step, report:
- the `MULTI BEAM:` lines of the log;
- what you saw per weapon: beam visible or not, rounds or heat, reload / heat sink, trigger behaviour;
- any crash.
