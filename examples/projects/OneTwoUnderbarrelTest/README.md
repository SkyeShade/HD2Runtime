# OneTwoUnderbarrelTest

Live test for the AR/GL-21 One-Two's underbarrel grenade launcher. Uses the MODS tab (page **One-Two Underbarrel
Test**).

The launcher is its own weapon entity, not part of the rifle. The rifle's default underbarrel item names it, and the
game creates it as a separate weapon when the One-Two is set up (research/underbarrel-weapons-F5FEE03DCFDB.json). Its
grenade spread and grenade reserve are that entity's own records, written on
`hd2.weapon('AR/GL-21 One-Two'):underbarrel()`. The rifle is untouched.

| Option | Default | What it does |
| --- | --- | --- |
| Tight grenades | on | grenade spread 30 -> 3 (horizontal and vertical) |
| Grenade pouch | on | spare grenades 5 -> 15, resupply 5 -> 15, starting reserve 3 -> 9 |

## How to test

1. Check the log: `transaction one-two-spread APPLIED` and `one-two-grenades APPLIED`.
2. Equip the One-Two **after** APPLY (or re-equip it / call in a new loadout).
3. **Grenade pouch:** the launcher's grenade count should show far more grenades in reserve (vanilla: 3 at the start,
   5 at most). A resupply box should refill up to 15.
4. **Tight grenades:** fire grenades at a wall from mid range. They should land in a tight group where you aim
   (vanilla spreads noticeably).
5. The rifle (5.5x50mm) should behave exactly as vanilla: fire rate, spread, magazine.
6. Everything off, APPLY, re-equip: vanilla.

Report:
- whether the reserve count and the resupply changed, and what the HUD showed;
- whether the grenade spread tightened;
- whether it needed a re-equip or a new loadout;
- whether the rifle stayed vanilla.

`allow_unverified_effect` is set: these fields are mapped offline, not yet shown in game.
