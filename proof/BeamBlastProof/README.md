# BeamBlastProof

Development proof for HD2Runtime 0.30.4: the wind-up (firing charge) of heat weapons and the LAS-13 Trident's pulsed
beam on other beam weapons (docs/player-weapon-authoring.md, "Wind-up and Trident-like beam blasts"). Each test is
one toggle in the mod's options page (MODS tab); re-equip the weapon (or call a new one in) after a change: the values
are copied into a weapon when it is built.

| Toggle (default) | Change | Expected |
|---|---|---|
| Trident-like Scythe (on) | LAS-5 Scythe: beam mode 4 -> 6, 60 -> 300 rpm, 1 -> 2 beams per pulse, 0 -> 0.15 s | the Scythe fires short pulsed blasts like the Trident instead of a continuous beam |
| Instant Sickle (on) | LAS-16 Sickle firing charge 100 -> 0 | the Sickle fires the moment the trigger is pulled (no 0.5 s wind-up) |
| Slow Double-Edge (on) | LAS-17 Double-Edge Sickle charge gain 200 -> 50 per second | about 2 s of wind-up before it fires |
| Trident long pulse (off) | LAS-13 Trident pulse 0.15 -> 1.0 s | each blast lasts visibly longer |
| Trident 6 beams (off) | LAS-13 Trident beams per pulse 2 -> 6 | more beams (or more damage ticks) per pulse |

Report each: what you saw, and whether anything looked broken. Solo first; then, if you can, a friend in the lobby
with and without the mod (the beam blasts must look the same on their screen).

Credit: the laser research these tests check started from [Bans](https://ayakamods.com/members/bans.388863/)'s [True Lasgun Beam Overhaul](https://ayakamods.com/mods/true-lasgun-beam-overhaul.4681/).
