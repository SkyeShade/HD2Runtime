# SurplusEatPodSwap

A live test for drop-pod payload authoring. The Surplus EAT Allocation booster's pod opens with two Resupply
**Supply Boxes** instead of two EAT-17s, which is easy to spot in game.

## How it works
- **Rack:** the booster's granted stratagem delivers the `weapon_rack_lat_oneshot` hellpod rack. Its
  `HellpodRackComponent` has eight 64-byte `RackAttach` slots, and the first `spawn_payload_size` (2) of them
  spawn.
- **Edit:** the patch rewrites the item reference in slots 1 and 2.
- **Replacement:** the replacement comes from the typed pickup catalog (`hd2.pickup('Supply Box')`), never a
  raw identifier.

## Scope and acknowledgements
- **Shared rack:** the ordinary EAT-17 Expendable Anti-Tank call-in uses the same rack entity, so its pods
  change too. That is why `allow_shared=true` is required.
- **Unverified reference:** spawning a Supply Box from this pod has not been tried in game, so
  `allow_unverified_reference=true` is required.

## Why the Supply Box
The Supply Box is spawned from a hellpod rack in vanilla (the Resupply pod). Resupply is available in every
mission, so the Supply Box's assets are always loaded. Other pickups carry a package risk: health packs, world
ammo, grenade boxes and other support weapons are only resident when their own package is loaded.

## Live test checklist
Check each of these in game:
1. The Surplus EAT pod opens with two supply boxes, and each one can be picked up.
2. An EAT-17 call-in also opens with supply boxes.
3. After the mod is removed or the game restarts, both pods drop EATs again.

This was built only, not deployed or launched.
