# MultiBeamProof (EXPERIMENTAL, SOLO ONLY)

**Superseded by `proof/BeamConversionProof` and the beam conversion API (`docs/beam-conversion.md`).** Kept as the
live-proven experiment fallback. It needs a development build that ships its experiment module
(runtime/experiment_*.lua; the 0.31.0 release runtime does not), and the Runtime refuses to mix the two (an experiment copy
of the BeamWeapon table refuses every conversion, and the other way round).

This mod live-tests the **LAS-13 Trident beam on three weapons at once**: the **AR-23 Liberator**, the **LAS-58
Talon** and the **SMG-32 Reprimand** (`research/docs/multi-beam-swap-F5FEE03DCFDB.md`). It generalises the
live-proven Liberator swap of LiberatorBeamProof 0.2.0.

- 0.2.0 added **each swapped weapon's own beam damage and armour penetration**
  (`research/docs/beam-damage-per-weapon-F5FEE03DCFDB.md`): the Runtime writes each weapon's own shots, never a row.
- 0.3.0 added **each weapon's own BeamWeapon record, so its own rate of fire and pulse**
  (`research/docs/beam-table-relocation-F5FEE03DCFDB.md`). The Runtime builds a private copy of the game's BeamWeapon
  table with three records of its own (Liberator 24, Talon 25, Reprimand 26, each a copy of the Trident's record) and
  switches the game to read that copy: **one 8-byte pointer write**. The game's own table is never written. This is
  the **owned table** path; the status line says which path is active.
- If the owned table is not available (a pin differs, the Runtime cannot allocate it), the swap falls back to the
  0.1.0 **shared record** path: all three share record 23 (one rate for all three).
- **New in 0.3.1: fast rates are reached** (`research/docs/beam-pulse-rate-F5FEE03DCFDB.md`). The 0.3.0 live test
  (solo, 2026-10-10) worked, with per-weapon rates, but 600 and 900 rpm were capped. The cause is in the game's beam
  update: a new pulse starts only in the update **after** the previous pulse has ended, so with the Trident's 0.15 s
  pulse no weapon fires faster than about **330-360 rpm at 60 fps**. Now a rate set without its own pulse length gets
  a **pulse that fits its shot interval** (the log line says `pulse fitted to the rate`). A pulse length you set
  yourself is kept, with a `WARNING ... caps` line when it limits the rate.

It is not a Runtime feature and not part of any release. It needs the HD2Runtime build of branch `exp/multi-beam` with
`runtime/experiment_beam_swap.lua` **0.3.1 or later**, `runtime/experiment_beam_table.lua` **0.1.x** and
`runtime/experiment_beam_damage.lua` **0.1.x**. With any other Runtime the mod logs `UNAVAILABLE` and does nothing.

- Startup line: `MultiBeamProof 0.3.1 EXPERIMENTAL BUILD`.
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
| Ctrl+Alt+F10 | Choose the rate / pulse profile: Trident (default) -> R -> F -> C -> P -> Trident. Owned table: written at once; otherwise kept for the next apply |

- A write key needs a second press within 6 s. F9 writes nothing by itself. F10 writes only the weapons' own records
  in the copy (never the game's table; no live-instance rule: records are read per shot).
- These keys are used by no other proof in the repository (the Pelican proofs use Ctrl+Shift+F-keys).

## Rate / pulse profiles (Ctrl+Alt+F10)

The Trident: **300 rpm, 2 beams per pulse, 0.15 s** (BeamWeapon +104, +108, +112).

| Profile | AR-23 Liberator | LAS-58 Talon | SMG-32 Reprimand |
|---|---|---|---|
| Trident (default) | 300 rpm, 0.15 s | 300 rpm, 0.15 s | 300 rpm, 0.15 s |
| R (rates, fitted) | **600 rpm**, 0.067 s (fitted) | **150 rpm**, 0.15 s | **900 rpm**, 0.033 s (fitted) |
| F (fast, fitted) | 600 rpm, 0.067 s (fitted) | 150 rpm, 0.15 s | **1200 rpm**, 0.025 s (fitted) |
| C (capped control) | 600 rpm, 0.067 s (fitted) | 150 rpm, 0.15 s | 900 rpm, **0.15 s (set)**: capped, about 330-360 rpm |
| P (pulse) | 600 rpm, **1 beam per pulse**, 0.067 s (fitted) | 150 rpm, **6 beams per pulse** | 900 rpm, **1.0 s pulse (set)**: capped, about 57 rpm |

- **Why the pulse length limits the rate** (proven in the game's code, `research/docs/beam-pulse-rate-F5FEE03DCFDB.md`):
  the game counts in updates (frames). A pulse runs for `pulse seconds`; the update after it ends, a new pulse may
  start if `60 / rpm` seconds have passed since the last start. So the time between pulses is the longer of the two,
  rounded up to whole frames.
- **The fitted pulse** is the longer of half the interval and the interval minus 1/30 s, never longer than the
  Trident's 0.15 s: 600 rpm -> 0.067 s, 900 rpm -> 0.033 s, 1200 rpm -> 0.025 s. 150 and 300 rpm keep 0.15 s.
- **Limits that remain** (the game's, not fixable by data):
  - A pulse **shorter than one frame deals no damage**: the game ends it before its first hit. 1200 rpm (0.025 s)
    hits only above **40 fps**; 900 rpm (0.033 s) above 30 fps.
  - At most **one pulse every 3 frames** for a pulse that hits: 1200 rpm at 60 fps, 2400 at 120 fps.
  - **Each interval rounds up to whole frames**: with a varying frame rate expect a little less than the setting,
    about 550 for 600 rpm, 800 for 900 and 1000-1100 for 1200 at around 60 fps (closer at higher frame rates).
- `beams per pulse` stays a **name from leads** (profile P): all beams of a pulse fire in the same frame, so it does
  not change the rate. The rate (+104) and the pulse (+112) are read at every pulse start (proven in code).

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
6. **Fast rates, then the control (in a mission, 0.3.1).** Note your frame rate (the game's FPS counter or any
   overlay). Each F10 press writes at once (no restore needed); the `beam profile` lines say `pulse FITTED`,
   `pulse fits` or `pulse CAPS the rate`, and the `MULTI BEAM:` lines say what was fitted or warned.
   - Profile R (already set): the **Liberator now really fires about twice as fast as a Trident** (600 rpm, about 10
     pulses per second), the **Reprimand three times as fast** (900 rpm, 15 per second). In 0.3.0 both stopped at
     about 6 per second. Count rounds: a full Liberator magazine (45) should empty in about 5 s, a Reprimand (25) in
     under 2 s.
   - F10 -> **F**: the Reprimand at **1200 rpm** (20 per second; 25 rounds in about 1.3 s). Check it still damages
     enemies (its pulse is 0.025 s: below 40 fps it would deal no damage). Report your frame rate.
   - F10 -> **C** (control): the Reprimand back to 900 rpm with the Trident's 0.15 s pulse. Expect the 0.3.0 cap
     (about 6 per second) and a `WARNING: pulse 0.15 s caps 900 rpm` line. If C fires as fast as R, the model is wrong.
   - F10 -> **P**: Liberator 1 beam per pulse (vs 2); Talon 6 beams per pulse; Reprimand a 1.0 s pulse (capped: about
     one pulse per second). Report what you see (beams per pulse is a lead: anything that changes, or nothing, is a
     result).
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
- what you saw per weapon: beam visible or not, rate (seconds to empty a magazine), rounds or heat, reload / heat
  sink, trigger behaviour, and for profile F whether the 1200 rpm Reprimand still damages enemies;
- your frame rate during the fast-rate steps;
- any crash.
