# AvatarActionsTest

Live test for `hd2.actions.heal_limb`, `hd2.actions.heal_limbs` and `hd2.actions.add_velocity`
(`docs/event-scripting.md`; `research/docs/player-avatar-actions-F5FEE03DCFDB.md`). Every log line starts with
`AVATAR ACTIONS 0.1.0 BUILD`. Everything acts on your own avatar only; no host needed.

## How it works

- **Limb heal:** the game's own zone restore (game.dll `RestoreZone`, `0x65B2D0`) returns one limb's damage zone to
  full health and clears its injured state, committed the way the game's own heal commits it. Main health is not
  touched. The game has no partial limb heal, so this test always heals in full.
- **Velocity:** the game's own movement velocity setter (game.dll `SetVelocity`, `0x4A7550`), the velocity the jump
  pack pushes and the game's own avatar launch sets: your current velocity plus the kick. At most 25 m/s per kick.

| Keys | What it does |
| --- | --- |
| Ctrl+Alt+F1 .. F6 | Heal head, chest, left arm (`l_hand`), right arm (`r_hand`), left leg (`l_knee`), right leg (`r_knee`) |
| Ctrl+Alt+F7 | Heal all six limbs |
| Ctrl+Alt+F8 | Upward kick, +8 m/s |
| Ctrl+Alt+F9 | Forward kick: +6 m/s along the way you were last moving, +4 m/s up |

## Checklist

1. Load the mod (with LimbInjuryTest to injure limbs on demand). The log shows `AVATAR ACTIONS 0.1.0 BUILD: loaded`.
2. In a mission, injure the right arm (LimbInjuryTest Alt+F7). Press Ctrl+Alt+F4. The log shows
   `heal r_hand requested (r_hand / arm_right, zone health before 0, was injured)`.
   - [ ] the HUD no longer shows the arm injured and the aim stops swaying
   - [ ] main health did not change
3. Injure the left leg (LimbInjuryTest Alt+F8), press Ctrl+Alt+F5:
   - [ ] the limp stops
4. Injure an arm and a leg, press Ctrl+Alt+F7:
   - [ ] both heal; the log lists all six limbs
5. Standing still, press Ctrl+Alt+F8:
   - [ ] you are lifted about 3 m (8 m/s up), or nothing happens (report which)
6. Running, press Ctrl+Alt+F9; then try it in the air (after F8, or while jump-packing):
   - [ ] grounded: pushed forward, or cancelled at once (report which)
   - [ ] airborne: pushed forward
7. As a client in a multiplayer mission, repeat 2 and 5:
   - [ ] it works without the host; what did the other players see?
8. Aboard the ship every key is refused with `NOT_IN_MISSION`.

Please report the checklist results and any refusal codes in the log.

## Build

`py build.py` (the SDK in `../../../sdk`).
