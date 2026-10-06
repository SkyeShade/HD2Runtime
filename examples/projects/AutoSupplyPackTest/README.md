# AutoSupplyPackTest

Live test for the equipment reads (`player:loadout()`, `:held_weapon()`, `:backpack()`, `:ammo()`) and
`hd2.actions.resupply_from_pack` (`docs/player-equipment.md`): **an auto-consuming B-1 Supply Pack.** When the weapon
in your hands is down to one spare magazine, your own Supply Pack uses one of its supplies on you. Every log line
starts with `AUTO SUPPLY PACK 0.1.0 BUILD`.

## How it works

- Twice a second the mod reads your worn backpack (`player:backpack()`: the B-1 Supply Pack and its live supply count)
  and the ammunition of the weapon in hand (`player:ammo()`: rounds in the magazine and spare magazines).
- When the weapon has at most 1 spare magazine and the pack has a supply left, it calls
  `hd2.actions.resupply_from_pack(player)`. Runtime then makes the request the game's own input makes when you press the
  pack's key: the pack's own self-use ability (2629, from its deposit definition) starts on your avatar through the
  game's `try_start_action` (game.dll `0xA431D0`). The game plays its own animation, spends one supply and refills
  your weapons, with its own network replication.
- Runtime refuses, without calling anything, whatever the game would refuse: no Supply Pack (`NO_BACKPACK`,
  `NOT_A_SUPPLY_PACK`), an empty pack (`NO_SUPPLIES`), already acting (`BUSY`, `CANNOT_ACT`). It also asks the game's own
  query whether a weapon takes ammunition, so a supply is never spent on full weapons (`NO_AMMO_NEEDED`).
- The "auto" rule is this mod; Runtime offers only the reads and the one action. One request per 2 s per mod.

| Key | What it does |
| --- | --- |
| Alt+F10 | logs what you hold and wear: primary, secondary, support, backpack (with its supplies), throwables, the weapon in hand and its ammunition |
| Alt+F11 | asks for one use at once |

## How to test

1. Load the mod. The log shows `AUTO SUPPLY PACK 0.1.0 BUILD: loaded; ...`.
2. Aboard the ship press Alt+F10: the log names your primary, secondary and throwables (backpack `none`). Alt+F11 is
   refused with `NOT_IN_MISSION`.
3. In a mission, call in and wear a B-1 Supply Pack. Press Alt+F10: the backpack is `B-1 Supply Pack 4/4`.
4. Fire your primary until it has 1 spare magazine left (reload as you go). Within half a second the Helldiver
   should use the pack on itself. The log shows `auto: Supply Pack used (4/4 supplies before)`.
5. Check: the use animation plays as when you press the pack's key; the pack's supply counter drops by one; the
   weapon's spare magazines refill; Alt+F10 now shows `3/4`.
6. Press Alt+F11 with full weapons: refused with `NO_AMMO_NEEDED` and no supply spent.
7. Empty the pack (four uses): the next attempt is refused with `NO_SUPPLIES`.
8. Wear another backpack (for example a Guard Dog): Alt+F10 shows it with its ammunition; Alt+F11 is refused with
   `NOT_A_SUPPLY_PACK`.

Please report: whether the use looked and sounded exactly like pressing the pack's key; whether one supply was spent
per use and the right weapons were refilled (grenades and stims too?); whether it worked as a client; what other
players saw (the animation, the supply counter); any refusal codes; and whether Alt+F10 named everything correctly
(also your support weapon and throwables).

## Build

`py build.py` (the SDK in `../../../sdk`).
