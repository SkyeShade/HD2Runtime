# ResupplyTest

Live test for the Resupply stratagem as an `hd2.stratagem` target. Two options on the MODS tab (Mod Options Menu)
change its cooldown and what its drop pod holds.

| Option | Choices | Default |
| --- | --- | --- |
| Resupply cooldown | Vanilla (180 s) / 5 s | 5 s |
| Resupply payload | Vanilla supply boxes / Grenade boxes | Grenade boxes |

Without Mod Options Menu the defaults apply (5 s, grenade boxes).

## How it works

- **Identity.** `hd2.stratagem('Resupply')` is the only StratagemInfo row of native type AmmoRack (33), the type whose
  UI icon is `StratagemRessuply`. Its id, group, row, package and payloads are identical in all seven retained
  snapshots (`research/resupply-F5FEE03DCFDB.json`). Runtime re-proves that row before every write.
- **Cooldown.** StratagemInfo `+104` (180 s in this build). The same member is live-proven on the Orbital Precision
  Strike, but not yet on Resupply.
- **Payload.** The row's payloads are three (Resupply rack, hellpod) pairs. The rack (`hellpod/ammo_rack/ammo_rack`)
  spawns its first four slots, each a Supply Box. `hd2.stratagem('Resupply'):delivery():rack()` is that rack. The
  test writes the four slots with the Grenade Box, a pickup whose own package Runtime loads first. The Grenade Box is
  live-proven in an MG-43 pod slot, not yet in this pod (`allow_unverified_reference`).
- **Shared rack.** The Resupply reward variant (AmmoRack_PresidentReward) uses the same rack, so its pods change too
  (`allow_shared`).
- **Medal payload.** Not offered. No medal pickup entity exists, and the one exploration-reward entity interacts
  through an unproven interaction type and grants account progression decided by the game servers.
- **Switching back.** Changing an option applies at once. Vanilla restores exactly the supply boxes and the 180 s
  cooldown. The slot write treats the value this mod applied itself as its own (an owned transition), never as a
  conflict.

## How to test

1. Install HD2Runtime 0.28.0, Mod Options Menu and this
   mod. Start a mission.
2. The log shows `assets for resupply-payload requested`, then `resident`, then `patch resupply-cooldown APPLIED` and
   `plan resupply-payload APPLIED`.
3. Call Resupply. The log shows `Resupply pod landed (entity ...)`. The pod opens with **four grenade boxes**; pick one
   up (it should refill grenades).
4. Call Resupply again: it should be ready again **5 s** after the first call.
5. In the MODS tab, set the payload to Vanilla and press APPLY; the next pod has four supply boxes. Set the cooldown
   to Vanilla; the next cooldown is 180 s.

Please report:

- the cooldown you saw;
- whether the pod landed normally;
- whether the grenade boxes appeared with their model (not a question mark) and could be picked up;
- whether picking one up refilled grenades;
- whether switching back to Vanilla worked without a restart.
