# LaserCannonTest

Live test for the LAS-98 Laser Cannon beam fire rate. Uses the MODS tab (page **Laser Cannon Test**).

Seven weapons publish a "Beam Fire Rate": LAS-98 60, LAS-13 Trident 300 and 40-K Meltagun 50 per minute, among
others. All of them sit at one typed BeamWeapon member, which sets how often the beam applies its damage. The rest
of the LAS-98 is already authored: beam length and radius, damage and armor penetration, heat and cooling,
heatsinks, reload, handling and its Fire status.

| Option | Default | What it does |
| --- | --- | --- |
| Fast beam | on | beam fire rate 60 -> 240 per minute |

## How to test

1. Check the log: `patch laser-cannon-beam-rate APPLIED`.
2. Call in a **fresh** LAS-98 after APPLY.
3. Hold the beam on one medium enemy (a Hive Guard, a Devastator) and count the seconds to the kill. Then turn the
   option off, APPLY, fresh LAS-98, same enemy type. The fast beam should kill several times faster.
4. Note whether the heat builds faster (heat is per second, so it should not).

Report both times and anything unexpected. `allow_unverified_effect` is set: mapped offline, not yet shown in game.
