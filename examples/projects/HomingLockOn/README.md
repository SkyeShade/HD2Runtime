# HomingLockOn (development example)

Requires the Runtime extension described in `docs/homing-lock-on.md`. The stock
0.40.0 release safely refuses these new options even though the build profile matches.
Build with `python build.py`; the separately installed SDK is found as in the other
example projects. No Runtime implementation is bundled by this example.

Use solo/host, hold a normal AR-23, acquire up to three targets for 0.3 seconds,
and then fire single shots and bursts. A shot fired before locking stays ordinary.
LOS must be clear; blocked/unknown targets are excluded. The 600 m/s² acceleration
budget produces gentler speed-dependent curves, under the 1440 deg/s cap.
The example enables `require_aim`: hip fire cannot acquire/assign new rounds;
rounds already assigned while aiming keep following after Aim release.

Compare aim press/release and menu transitions, three-target bursts, a blocked
sightline, and acceleration 300/600/1200. Check acquisition/steering and hit outcomes
separately. The HUD is aim-only and defaults to amber acquisition / green lock.
Change `hud:style(...)` from an options callback without recreating gameplay.

The earlier cb8f9a3 Runtime port has AR-23 steering logs, but this updated example's
Aim gate and optional vanilla marker path still await a separate live check.
Select `hud:style({marker_shape='vanilla'})` to prefer resident Warrant marker art,
with an explicitly reported geometric fallback. No native TargetLock is enabled.
