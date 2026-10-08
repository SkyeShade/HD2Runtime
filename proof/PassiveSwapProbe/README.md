# PassiveSwapProbe 0.2.0

The live test of armor passive overrides (`hd2.player_passives.set`, docs/armor-passives.md), round two. The local
player's armor passive is replaced on their own customization record, and a second passive can be added in the empty
helmet slot. Every other player, the shared passive table and the kits stay vanilla. Development only, solo. Requires
HD2Runtime 0.30.0-dev with the armor kits and effect packages build.

0.1.0 proved the armor-slot swap to SERVO-ASSISTED, ENGINEERING KIT and SCOUT. 0.2.0 tests more passives in the
armor slot whose effect is easy to see, the first passive with an effect package (INTEGRATED EXPLOSIVES), and one
control that must not change (EXTRA PADDING).

## How to test

1. Start a **solo** mission in any armor (note its passive; the log line `PASSIVES (mission start)` names the kits
   and the passive). Bring incendiary grenades (or any grenade) and, if you can, a Tesla Tower.
2. In `VANILLA` first, note your reference values: the health you lose from your own grenade at a fixed distance
   (just outside its kill radius), your grenade and stim counts after a resupply, how long a stim lasts.
3. **F8** cycles the armor passive. For each mode, what to observe:

| Mode | Observe | Follows a swap (research) |
| --- | --- | --- |
| `VANILLA` | The kit's own passive: your reference values. | - |
| `INTEGRATED EXPLOSIVES` | Die (your own grenade, a fall). About **1.5 s later your body explodes** where you died: a visible blast and its sound. The log must show the effect package loading first: `handle waiting_for_assets`, `effect package resident`, then `HANDLE waiting_for_assets -> active`. Also +2 grenades (maybe only after a resupply). | full (needs its package) |
| `MED-KIT` | **+2 stims** after a resupply or reinforcement (the timing is unproven), and the stim effect lasts **about 2 s longer**. | full |
| `FORTIFIED` | Your own grenade at the same distance: **about half** the health loss. Less recoil crouched or prone. | full |
| `DEMOCRACY PROTECTS` | Take a lethal hit several times: **about half the time you survive** with low health (the game text: 50%). A chest bleed does no damage. | full |
| `ELECTRICAL CONDUIT` | Stand by your own Tesla Tower or take an Arc Thrower blast: **almost no damage** (x0.05). | full |
| `INFLAMMABLE` | Stand in your own incendiary fire: the health drains **about four times slower** (x0.25). | full |
| `EXTRA PADDING` | **Control: nothing may change.** Its only effect is the armor rating, which follows the worn armor kit, never the slot. The same hit must do the same damage as in VANILLA. A difference is a finding: report it. | NO (armor rating) |
| `SERVO-ASSISTED` | Live-proven in 0.1.0: throw range x1.3. | full |
| `ENGINEERING KIT` | Live-proven in 0.1.0: +2 grenades. | full |
| `SCOUT` | Live-proven in 0.1.0: enemies detect you later; markers make radar scans. | full |

4. **Ctrl+F8** adds or removes a second passive, `MED-KIT` (+2 stims, +2 s stim duration), in the helmet slot. It is
   left out while the armor mode is MED-KIT itself.
5. Back on the ship with an override active, change your armor in the armory. The log must show
   `RE-APPLIED after the kit changed`, and **Shift+F8** (logs the passives now, changes nothing) still shows the
   override.
6. **Ctrl+Shift+F8** restores the kit's own passives.

Please report per mode: what you saw, and whether it matched the table. For INTEGRATED EXPLOSIVES also report whether
the explosion appeared on the first death after the mode was set.

## What the log shows

- `PASSIVES (...)`: the armor and helmet kits (id, game name, weight), the two slots, the kit-derived values and the
  rows the game reads (key name, type, value, which slot).
- `MODE ... handle active` (or `waiting_for_assets` for INTEGRATED EXPLOSIVES): the override is in place or loading.
  `refused` with a code says why: `NOT_SOLO`, `ASSET_UNAVAILABLE`, `UNKNOWN_PASSIVE`, and others.
- `FOLLOWS (...)`: per modifier row, its reader status from the research (direct, data-driven, description-only,
  armor rating) and whether it follows a swap; the effect package, if any.
- `HANDLE a -> b`: a status change of the handle (for example the package becoming resident).
- `OBSERVE:` what should change in game.
- `[HD2Runtime] passives (...)`: the Runtime's own lines: `waiting_for_assets`, `effect package resident`, `APPLIED`,
  `RE-APPLIED`, `SUSPENDED`, `stopped ... restored`.

## Known limits

- **Not stacked.** A key both passives carry keeps the armor's value.
- **Armor-slot-only readers.** Flinch, one chest-bleed site and the Integrated Explosives death explosion read the
  armor slot only, so a second passive never reaches them. The Runtime refuses INTEGRATED EXPLOSIVES as the second
  passive (`ARMOR_SLOT_ONLY`).
- **Armor rating, reload, ammo and sidearm stats** follow the kit worn (at spawn), never the slot. EXTRA PADDING is the
  control for this.
- **Capacities.** Grenade and stim capacity may only change at the next resupply or spawn. This is unproven, and part
  of what this test checks.
- **Effect package.** INTEGRATED EXPLOSIVES' package is loaded through the Runtime's asset loader first (and kept for
  the session). What the game does if the explosion fires without it is unknown; the probe never lets that happen.
