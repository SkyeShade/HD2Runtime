# PassiveSwapProbe 0.1.0

The live test of armor passive overrides (`hd2.player_passives.set`, docs/armor-passives.md). The local player's
armor passive is replaced on their own customization record, and a second passive can be added in the empty helmet
slot. Every other player, the shared passive table and the kits stay vanilla. Development only, solo. Requires
HD2Runtime 0.30.0-dev with the armor passives build.

## How to test

1. Start a **solo** mission in any armor (note its passive; the log line `PASSIVES (mission start)` names it).
2. Pick a fixed spot and throw a grenade at the same angle for each mode below; note where it lands.
3. **F8** cycles the armor passive:
   - `VANILLA`: the kit's own passive.
   - `SERVO-ASSISTED`: throw range x1.3 (the grenade lands clearly farther), limb health x1.5.
   - `ENGINEERING KIT`: +2 grenades (may only show after the next resupply or reinforcement), crouch / prone recoil
     x0.7.
   - `SCOUT`: enemies detect you at x0.7 range; a map marker makes a radar scan every 2 s.
4. **Ctrl+F8** adds or removes a second passive, `MED-KIT`: +2 stims (after a resupply or reinforcement) and +2 s stim
   duration.
5. Back on the ship with an override active, change your armor in the armory. The log must show
   `RE-APPLIED after the kit changed`, and **Shift+F8** (logs the passives now, changes nothing) still shows the
   override.
6. **Ctrl+Shift+F8** restores the kit's own passives.

## What the log shows

- `PASSIVES (...)`: the armor and helmet kits, the two slots, the kit-derived values and the rows the game reads
  (key name, type, value, which slot).
- `MODE ... handle active`: the override is in place. `refused` with a code says why: `NOT_SOLO`, `UNKNOWN_PASSIVE`,
  `PACKAGE_NOT_RESIDENT`, and others.
- `OBSERVE:` what should change in game.
- `[HD2Runtime] passives (...)`: the Runtime's own lines: `APPLIED`, `RE-APPLIED`, `SUSPENDED`, `stopped ... restored`.

## Known limits

- **Not stacked.** A key both passives carry keeps the armor's value.
- **Armor-slot-only readers.** Flinch, one chest-bleed site and the Integrated Explosives death explosion read the
  armor slot only, so a second passive never reaches them.
- **Armor rating.** It follows the armor kit, not the passive.
- **Capacities.** Grenade and stim capacity may only change at the next resupply or spawn. This is unproven, and part
  of what this test checks.
