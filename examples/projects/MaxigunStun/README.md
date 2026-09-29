# MaxigunStun

Live test: M-1000 Maxigun bullets apply Stun Medium on hit (strength 2, the AR-32 Pacifier / SMG-72 Pummeler value).
Damage, projectile, fire rate and ammunition are unchanged.

**Result: live-proven (2026-09-29).** Maxigun bullets stun enemies. Status references on player and support weapon
projectile (direct-hit) rows no longer need `allow_unverified_effect`.

Observation kept as reported: the stun held targets for about 1-2 seconds, not the 3 seconds Stun Medium's definition
stores. The cause is not established. Enemies carry per-class status susceptibility tables
(`research/status-susceptibility-F5FEE03DCFDB.json`), so target-side processing may shorten it; status duration
semantics are unchanged.

What to verify: fire short bursts at a Hunter, a Berserker or a Devastator and watch for the stun pose and the blue
electric effect.
