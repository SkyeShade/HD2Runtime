# EquippedWeaponEventTest

Live test for `player:equipped_weapon()` and the `weapon_equipped`, `weapon_unequipped` and `weapon_changed` events
(`docs/events.md`).

## How it works

- What your avatar holds is slot 0 of its wielder record. The game's weapon switch writes it, together with the
  inventory selection, in one call (`research/event-wielder-F5FEE03DCFDB.json`).
- The held entity's type is its weapon resource, named from the catalog. Selection 1 (primary) and 2 (secondary)
  are proven. Support, held item and unknown are inferred and marked `(inferred)`.
- Runtime checks 10 times a second and reports each change. Only the local player is read.

## How to test

1. In a mission, switch between primary and secondary. Each switch logs `unequipped ... (switched)`, `equipped ...`
   and `changed A -> B`.
2. Take out the support weapon, a grenade and a stratagem ball. Pick up and drop a carried item (for example a
   sample container or a Hellbomb).
3. Die and reinforce: `unequipped ... (emptied|avatar_changed)`, then `equipped <primary>` after the respawn.
4. Press F7 at any time: `F7: in hand: ...`.

Please report any line whose name, slot or selection is wrong, especially support weapons, grenades, stratagem balls
and carried items (their slots are inferred).
