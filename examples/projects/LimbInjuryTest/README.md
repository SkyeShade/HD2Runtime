# LimbInjuryTest

Live test for `hd2.actions.injure` (`docs/event-scripting.md`, limb injuries): **every shot you fire hurts your own
right arm.** Every log line starts with `LIMB INJURY 0.1.0 BUILD`.

## How it works

- `hd2.actions.injure(player, 'r_hand', damage)` looks up the `r_hand` physics actor on your avatar's unit with the
  engine's own lookup (exe `0x799DE0`) and queues one damage request at it through the game's own damage request
  (game.dll `QueueDamage`, `0x129F910`). The template is the game's own VG-70 Variable self-damage: its third fire mode
  queues 15 Ability damage at the shooter's `r_shoulder` the same way.
- The game drains the queue later in the same frame and applies the damage like any hit on that limb: the arm_right
  zone (35 health) loses it, and main health loses 0.85 of it. An arm at 0 is injured, with the game's own effects.
- No host needed: each machine injures only the avatar it owns (the game's own self-injuries work the same way).
- This test: 2 per shot (`player_fired` is checked 10 times per second and can count several shots), at most 35 per
  request. Runtime also limits 12 requests at once and 10 per second per mod.

| Key | What it does |
| --- | --- |
| Alt+F7 | `r_hand` 35: the right arm is injured at once |
| Alt+F8 | `l_knee` 45: the left leg is injured at once |
| Alt+F9 | `head` 10: no HUD indicator; main health drops by about 15 |

## How to test

1. Load the mod. The log shows `LIMB INJURY 0.1.0 BUILD: loaded (limbs head=head:85, chest=body:60, ...)`.
2. In a mission (host or client), fire about 18 shots with any weapon. The log shows
   `LIMB INJURY 0.1.0 BUILD: 1 shot(s) requested (r_hand / arm_right -2, zone health before 35)` and so on.
3. Check that the HUD shows the right arm injured and the aim sways. Use a stim: the arm heals.
4. Press Alt+F8: the left leg is injured (you limp). Press Alt+F9: health drops.
5. Aboard the ship every request is refused with `NOT_IN_MISSION`.

Please report: whether the arm and leg injuries looked exactly like ordinary injuries (HUD, sway, limp, voice line),
whether a stim healed them, whether it worked as a client, what other players saw, and any refusal codes in the log.

## Build

`py build.py` (the SDK in `../../../sdk`).
