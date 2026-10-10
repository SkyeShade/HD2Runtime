# MultiBeamProof (EXPERIMENTAL, SOLO ONLY)

This mod live-tests the **LAS-13 Trident beam on three weapons at once**: the **AR-23 Liberator**, the **LAS-58
Talon** and the **SMG-32 Reprimand** (`research/docs/multi-beam-swap-F5FEE03DCFDB.md`). It generalises the
live-proven Liberator swap of LiberatorBeamProof 0.2.0.

- 0.2.0 added **each swapped weapon's own beam damage and armour penetration**
  (`research/docs/beam-damage-per-weapon-F5FEE03DCFDB.md`): the Runtime writes each weapon's own shots, never a row.
- **New in 0.3.0: each weapon's own BeamWeapon record, so its own rate of fire and pulse**
  (`research/docs/beam-table-relocation-F5FEE03DCFDB.md`). The Runtime builds a private copy of the game's BeamWeapon
  table with three records of its own (Liberator 24, Talon 25, Reprimand 26, each a copy of the Trident's record) and
  switches the game to read that copy: **one 8-byte pointer write**. The game's own table is never written. This is
  the **owned table** path; the status line says which path is active.
- If the owned table is not available (a pin differs, the Runtime cannot allocate it), the swap falls back to the
  0.1.0 **shared record** path: all three share record 23 (one rate for all three).

It is not a Runtime feature and not part of any release. It needs the HD2Runtime build of branch `exp/multi-beam` with
`runtime/experiment_beam_swap.lua` **0.3.x**, `runtime/experiment_beam_table.lua` **0.1.x** and
`runtime/experiment_beam_damage.lua` **0.1.x**. With any other Runtime the mod logs `UNAVAILABLE` and does nothing.

- Startup line: `MultiBeamProof 0.3.0 EXPERIMENTAL BUILD`.
- Every Runtime step logs a line starting with `MULTI BEAM:` (and `BEAM TABLE:` for the copy); each status prints
  one line per weapon, `MULTI BEAM: <weapon>: <state> [<path>] (...)`, with its rate.
- Every damage step logs a line starting with `MULTI BEAM DAMAGE:`.
- The Liberator-only path stays available: **LiberatorBeamProof 0.2.0** (Ctrl+Shift+F1..F4) runs on the same Runtime
  build. Use one proof at a time: it refuses while the owned table is live ("restore it with MultiBeamProof first").

## What it writes

Owned table (default):

| Step | Where | What |
|---|---|---|
| copy | a new private page (never freed) | the table's header, its 46 rows plus the weapons' rows, records 0..23 as the game's, records 24 / 25 / 26 = the Trident's record with each weapon's rate and pulse |
| switch | the game's BeamWeapon table pointer | the game's own table -> the copy (one 8-byte write) |
| per weapon | its membership list | ProjectileWeapon out, BeamWeapon in |
| Liberator, Reprimand | magazine record 201 / 139 +156 | 1 -> 0 (no chamber) |

- Applying more weapons later adds their rows to the live copy. Restoring some weapons removes their rows; restoring
  the **last** one puts the pointer back to the game's own table (the copy stays allocated and unused).
- **Rate and pulse (Ctrl+Alt+F10)** are written into each weapon's own record in the copy, at once; the next shots use
  them. Ranges, as the 0.30.4 beam fields: rate 1..6000 rpm, beams per pulse 1..8, pulse 0..10 s.
- Shared record (fallback): rows 21 / 11 / 25 in the game's table name record 23, which becomes the Trident's copy
  (written first, restored last). One rate for all three: Ctrl+Alt+F10 is refused on this path.
- One write per key press, **all or nothing**: if any byte fails, everything written in that press is rolled back.

## Keys

| Key | What it does |
|---|---|
| Ctrl+Alt+F5 | Status, read-only: the path (`owned table` / `shared record` / `none`), whether the game reads the copy, per weapon state (vanilla / applied / partial / orphaned / foreign), rate and live count, solo, Trident package, the F6 set |
| Ctrl+Alt+F8 | Choose the set F6 applies: all three (default) -> Liberator only -> Talon only -> Reprimand only -> all three. Writes nothing |
| Ctrl+Alt+F6 (twice) | Apply the chosen set |
| Ctrl+Alt+F7 (twice) | Restore every swapped weapon, then the table (owned: the pointer; shared: record 23) |
| Ctrl+Alt+F9 | Choose the damage profile: off (default) -> A -> B -> off. Applies at once to the swapped weapons' next shots |
| Ctrl+Alt+F10 | Choose the rate / pulse profile: Trident (default) -> R -> P -> Trident. Owned table: written at once; otherwise kept for the next apply |

- A write key needs a second press within 6 s. F9 writes nothing by itself. F10 writes only the weapons' own records
  in the copy (never the game's table; no live-instance rule: records are read per shot).
- These keys are used by no other proof in the repository (the Pelican proofs use Ctrl+Shift+F-keys).

## Rate / pulse profiles (Ctrl+Alt+F10)

The Trident: **300 rpm, 2 beams per pulse, 0.15 s** (BeamWeapon +104, +108, +112).

| Profile | AR-23 Liberator | LAS-58 Talon | SMG-32 Reprimand |
|---|---|---|---|
| Trident (default) | 300 rpm | 300 rpm | 300 rpm |
| R (rates) | **600 rpm** | **150 rpm** | **900 rpm** |
| P (pulse) | 600 rpm, **1 beam per pulse** | 150 rpm, **6 beams per pulse** | 900 rpm, **1.0 s pulse** |

- `beams per pulse` and `pulse seconds` are **names from leads** (the 0.30.4 docs): profile P is how we learn what
  they do. The rate (+104) is read per shot (proven in code).

## Damage profiles (Ctrl+Alt+F9)

The Trident pulse does **60 damage / 6 durable, armour penetration 2/2/2/0** (DamageInfo 508).

| Profile | AR-23 Liberator | LAS-58 Talon | SMG-32 Reprimand |
|---|---|---|---|
| off (default) | Trident: 60 / 6, AP 2 | Trident: 60 / 6, AP 2 | Trident: 60 / 6, AP 2 |
| A | **10x damage: 600 / 60**, AP 2 | **0.1x damage: 6 / 0.6**, AP 2 | 60 / 6, **AP 6** |
| B | **the LAS-5 Scythe's damage row: 350 / 70, AP 2**, demolition 10, no stagger or push, the Scythe's status | **150 / 15, AP 3** | unchanged (the control): 60 / 6, AP 2 |

- Profile B requests the LAS-5 Scythe's package (`laser_rifle`); the Liberator's setting waits until it is resident.
- Each weapon's **first** modified shot logs `MULTI BEAM DAMAGE: <weapon>: first shot written ...`. `MISSED` means a
  shot had already hit when the Runtime saw it: please report any.

## Rules (every write and the restore refuse otherwise)

- **Solo only.** Any other player in the lobby, or an unreadable lobby, refuses. Play Private/Friends-only alone.
- **Zero live instances of every weapon written.** No Liberator, Talon or Reprimand entity may exist at the apply or
  at the restore (only the weapons that press writes are counted).
  - **On the ship, equip a primary other than the Liberator and the Reprimand, a secondary other than the Talon, and
    do not open the armory**: its preview spawns one.
- **Apply needs the Trident's package** (`laser_shotgun`). The mod requests it at load.
- **Every pin and every before byte must match the research** (the 188 swap pins, the 28 table pins, the rows, the
  lists, the magazine bytes). Otherwise you see `REFUSED` / `UNPROVEN`, and nothing is written.
- **Another mod that moved the BeamWeapon table** (True Lasgun Beam Overhaul does): both paths refuse
  (`never chains onto a foreign copy`). Disable that mod for this test.
- **Restart the game after using it** (stale ProjectileWeapon copies of swapped weapons; and every owned copy stays
  allocated until the game exits).
- **Other HD2Runtime mods.** While a weapon is swapped, writes to its fire rate, projectile, ammunition and damage are
  refused (dormant), and so are typed writes to its beam record (use F10). Writes to other beam weapons (e.g. the
  real Trident's `beam.fire_rate`) go to the copy while it is live; the **final restore refuses** until such a write is
  undone (turn that mod's option off), so the game never loses it silently.

## Test plan (solo, least to most risky)

1. **Status (ship).** Equip, for example, the SG-8 Punisher and the P-2 Peacemaker; leave the armory unopened. Press
   Ctrl+Alt+F5.
   - Expect `path none (the game reads the file's own table); owned table available`, three
     `MULTI BEAM: <weapon>: vanilla (...); live 0` lines, `solo true`, `Trident package resident`.
   - **Abort** on any other state, `owned table UNAVAILABLE`, a refusal, or a live count above 0.
2. **Rates first (ship).** Press Ctrl+Alt+F10 once: profile R; three `beam profile R: ... kept for the next owned-table
   apply` lines.
3. **Apply all three (ship).** Press Ctrl+Alt+F6 twice.
   - Expect `BEAM TABLE: copy 1 built ...`, then `AR-23 Liberator APPLIED [owned table]: row 21 -> record 24 ... at
     600 rpm`, `LAS-58 Talon APPLIED [owned table] ... record 25 ... 150 rpm`, `SMG-32 Reprimand APPLIED [owned table]
     ... record 26 ... 900 rpm`, and `APPLY ...: OK, ... path owned table`.
   - F5: `path owned table (the game reads HD2Runtime's copy)`, `rates liberator 600 rpm, talon 150 rpm, reprimand
     900 rpm`.
   - **Abort** (quit the game, send the log) on `REFUSED` or a crash.
4. **Mission 1: Liberator + Talon.** Deploy solo. Expect, as in 0.2.0 (Trident pulses, beam and sound; Liberator one
   round per pulse and a normal reload; Talon heat per pulse and heat sinks), **and**:
   - the **Liberator fires about twice as fast as a Trident** (600 rpm), the **Talon about half as fast** (150 rpm).
   - A vanilla LAS-13 Trident (if you bring one in another mission) still fires at 300 rpm.
   - **Abort** (send the log and the crash dump) on a crash at spawn or on the first shot, an invisible beam,
     bullets/bolts still firing, or a weapon that cannot fire.
5. **Mission 2: Reprimand** (no muzzle attachment). Expect Trident pulses at **900 rpm** (three times the Trident),
   one round per pulse from its 25-round magazine, a normal reload.
6. **Pulse profile (in a mission).** Press Ctrl+Alt+F10 again: profile P. The lines say `1 write`, `2 writes`... (no
   restore needed). Keep firing:
   - Liberator: 1 beam per pulse (vs 2); Talon: 6 beams per pulse; Reprimand: a 1.0 s pulse. Report what you see
     (these names are leads: anything that changes, or nothing, is a result).
   - F10 again: back to `Trident` (300 rpm, 2, 0.15 s) for every weapon, at once.
7. **Lifecycle (either mission).** Empty and reload, resupply, drop and pick up, die and reinforce, call a Laser
   Sentry, swap weapons. Expect no crash; the Laser Sentry and enemy beams behave as always (they read their own
   records, byte-identical in the copy).
8. **Restore (ship).** Extract. Equip other weapons and wait until F5 shows `live 0` for all three. Press Ctrl+Alt+F7
   twice.
   - Expect `... RESTORED` for the three, then `RESTORED (path none; table the file's own; ...)`.
   - **Quit the game.** If the live count never reaches 0, **quit without restoring**: the game loads its own table
     at start.

If something fails with all three, narrow it down: restart, choose one weapon with Ctrl+Alt+F8, apply only that one,
and repeat the mission step for it. Damage profiles (Ctrl+Alt+F9) work on either path, as in 0.2.0: see its plan
(profile A: Liberator one-pulse kills, Talon very weak, Reprimand damages armour a Trident pulse bounces off).

Cosmetic, expected:
- An **empty** Liberator or Reprimand says "Need fresh I.C.E." on the trigger (the Trident's empty-weapon line).
- The armory may show beam stats for the swapped weapons (its stat readers look the BeamWeapon record up by weapon).
- The fire-rate selector of the Liberator and the Reprimand does nothing.

For each step, report:
- the `MULTI BEAM:` and `BEAM TABLE:` lines of the log;
- what you saw per weapon: beam visible or not, rate, rounds or heat, reload / heat sink, trigger behaviour;
- any crash.
