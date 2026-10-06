# VehicleTuningTest

Live test for the vehicle tuning fields. It uses one page on the MODS tab (**Vehicle Tuning Test**), and every log line
starts with `VEHICLE TUNING 0.1.0 BUILD`. The fields:

- **Turret motion** on mounted weapons (`hd2.vehicle(name):weapon(mount)`):
  - `hd2.fields.turret.yaw_speed` and `turret.pitch_speed` in degrees per second;
  - `turret.yaw_min/yaw_max` and `turret.pitch_min/pitch_max` in degrees.

  These are the same ids as the sentry turret fields.
- **Exosuit body rotation** on `hd2.vehicle(name)`:
  - `hd2.fields.rotation.turn_speed` in degrees per second;
  - `rotation.acceleration` and `rotation.deceleration` in degrees per second².
- **Steering response** on `hd2.vehicle(name)`: `hd2.fields.vehicle.steering_response_speed`, in input units per
  second.

Every field needs `allow_unverified_effect` until this test passes. The sentry live evidence for the same turret ids does
not apply to vehicles. Research: `docs/research/vehicle-mech-components-F5FEE03DCFDB.md`.

## When each value takes effect

| Field | Read by the game | What you must do after APPLY |
| --- | --- | --- |
| `turret.yaw_speed`, `turret.pitch_speed` | copied into the turret when the vehicle is created | call in a **new** vehicle |
| `turret.yaw_min/yaw_max`, `turret.pitch_min/pitch_max` | every turret update | nothing: a deployed vehicle follows at once |
| `rotation.turn_speed`, `rotation.acceleration` | copied into the Exosuit when it spawns | call in a **new** Exosuit |
| `vehicle.steering_response_speed` | every frame, from the vehicle type | nothing: every live FRV of that type follows at once |

## Options

| Option | Choices | Default |
| --- | --- | --- |
| M-103 gun traverse (deg/s) | 130 (vanilla) / 30 | 30 |
| Bastion cannon traverse (deg/s) | 35 (vanilla) / 8 | 8 |
| Bastion cannon left limit (deg) | -20 (vanilla) / -5 | -5 |
| Bastion cannon right limit (deg) | 20 (vanilla) / 5 | 5 |
| Bastion cannon highest aim (deg) | 25 (vanilla) / 45 | 45 |
| Patriot body turn speed (deg/s) | 65 (vanilla) / 20 | 20 |
| Patriot turn acceleration (deg/s²) | 0 (vanilla, instant) / 30 | 0 |
| M-102 FRV steering response (per s) | 3.1 (vanilla) / 0.5 | 0.5 |

**Without Mod Options Menu**, the defaults apply. The Bastion's three cannon limits are written in one transaction, so
the left limit always stays below the right one.

## Checklist

1. Install HD2Runtime 0.30.0-dev (built from this tree), Mod Options Menu and this mod.
2. Check the log:
   - `VEHICLE TUNING 0.1.0 BUILD: loaded; M-103 traverse 30; Bastion traverse 8, limits -5/5, highest aim 45; ...`;
   - one `APPLIED` line each for `m103-traverse`, `bastion-traverse`, `bastion-cannon-limits`, `patriot-rotation` and
     `frv-steering`.
3. **Pre-write control (creation copy).** If you can, call in a vehicle **before** the mod applies, for example with
   every option on vanilla, then switch to the test values. That vehicle must keep its vanilla traverse and turn rate.
   Only vehicles called in afterwards change.
4. **M-103 Supply FRV gun traverse 130 → 30.** Call in a new M-103 and turn the gun 180°.
   - Vanilla takes about 1.4 s; 30 takes about 6 s.
   - If the M-103 is not available, use the **Bastion cannon traverse 35 → 8** instead: a new Bastion's cannon sweeps
     its ±20° arc in about 5 s instead of about 1.1 s.
5. **Bastion cannon limits (immediate).** On a Bastion that is **already deployed**, aim the cannon fully left, right and
   up.
   - With -5/5 the cannon stops about 5° either side, and with 45 it elevates to about 45°.
   - Switch the left limit back to -20 and press APPLY. The arc opens again **without** a new Bastion.
   - Note whether the ±20° arc limits the cannon inside its turret or the turret itself.
6. **EXO-45 Patriot body turn 65 → 20.** Call in a new Patriot and turn on the spot by 180°.
   - Vanilla takes about 2.8 s; 20 takes about 9 s.
   - Then set **Patriot turn acceleration 30**, press APPLY and call in another Patriot. Its turn now ramps up over
     about a second instead of starting at full rate.
7. **M-102 Gunner FRV steering 3.1 → 0.5 (immediate).** In a live M-102, steer from straight ahead to full lock.
   - Vanilla takes about 0.3 s; 0.5 takes about 2 s.
   - Switch back to 3.1 and press APPLY **while driving**. The response returns at once, with no new FRV.
8. **Revert.** Set every option to vanilla and press APPLY. The log shows the writes restoring the vanilla values.

## What to report

- For each step: the observed time or angle, and whether a vehicle already in the world followed the change.
- Which arc the Bastion ±20° limit governs (cannon in turret, or turret).
- Whether a client gunner sees the changed M-103 traverse when only the host runs this mod. The rate is a host-written
  network creation field.
- Any `REJECTED` or `CONFLICT` line from the log.
