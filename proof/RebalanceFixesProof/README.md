# RebalanceFixesProof

Development proof for HD2Runtime 0.30.4. It live-tests the answers to three rebalance reports:

- **Hover Pack height.** There is no height member. The pack climbs only when its lift
  (`hover.vertical_acceleration_low_speed`) is above gravity (9.82). The vanilla lift is 9.8, so the pack only
  holds the height it was activated at. `hover.duration` is the climb window, counted in seconds of air time; it is
  not the hover time. `hover.max_vertical_speed` is only a cap. See docs/backpack-authoring.md, "How high the Hover
  Pack flies".
- **Wind-up.** The laser weapons' wind-up is their firing charge: `heat.firing_charge` / `heat.charge_gain_per_second`
  seconds. The Maxigun, the Patriot minigun and the Gatling Sentry use their spin-up, `windup.wind_up_seconds`.
  `windup.wind_down_seconds` is only a switch: 0 stops the barrels at once; any other value spins down over the
  wind-up time. See docs/player-weapon-authoring.md, "Wind-up".
- **The CQC-20 Breaching Hammer's blast** (2200 damage, Anti-Tank II) through
  `hd2.support_weapon('CQC-20 Breaching Hammer'):attack('ability'):explosion()`. See docs/support-weapon-api.md.

Each test is one toggle on the mod's options page (MODS tab, **Rebalance Fixes Proof**). Every value is read live,
so a toggle takes effect at once, also on gear you already hold. Toggles that edit the same field must not be on
together: the second is refused and logged (CONFLICT).

| Toggle (default) | Change | Expected |
|---|---|---|
| Hover: climb higher (on) | lift 9.8 -> 15 | after activation the pack climbs steadily, about 2.8 m/s, for about 6 s of air time (about 15 m above where the hover started), then holds that height until the fuel runs out. Vanilla: no climb after activation. |
| Hover: climb window 6 -> 10 s (off) | `hover.duration` 6 -> 10 | together with climb higher: it climbs for about 10 s of air time (about 27 m). Alone: no visible change. |
| Hover control: climb cap 10 -> 30 only (off; climb higher off) | `hover.max_vertical_speed` 10 -> 30 | **no change** from vanilla. This was the reporter's edit. |
| Sickle: no wind-up (on) | `heat.firing_charge` 100 -> 0 | the LAS-16 Sickle fires the moment you pull the trigger (vanilla 0.5 s delay) |
| Sickle: 2 s wind-up (off; no wind-up off) | `heat.charge_gain_per_second` 200 -> 50 | the first shot comes about 2 s after you pull the trigger |
| Quasar: 1 s charge (off) | `heat.charge_gain_per_second` 33 -> 100 | the LAS-99 Quasar fires after about 1 s of charging (vanilla 3 s) |
| Maxigun: instant spin-up (on) | `windup.wind_up_seconds` 0.5 -> 0 | the M-1000 Maxigun fires at once, with no spin-up |
| Maxigun: slow spin-up (off; instant off) | `windup.wind_up_seconds` 0.5 -> 3 | about 3 s of spinning before the first round |
| Maxigun: barrels stop at once (off) | `windup.wind_down_seconds` 0.5 -> 0 | when you let go, the barrels stop at once; the next burst needs the full spin-up again |
| Patriot minigun: instant spin-up (off) | `windup.wind_up_seconds` 1 -> 0 | the EXO-45 Patriot's minigun fires at once |
| Rover drone: no wind-up (off) | `heat.firing_charge` 100 -> 0 | the AX/LAS-5 Rover's laser fires with no delay |
| Laser Sentry: 2 s wind-up (off) | `heat.charge_gain_per_second` 200 -> 50 | the A/LAS-98 Laser Sentry waits about 2 s before each beam starts (vanilla 0.5 s) |
| Hammer: big blast (on) | blast damage 2200 -> 5000, outer radius 3 -> 6 m | the Breaching Hammer's charged hit kills heavier enemies outright and staggers enemies about twice as far out |
| Hammer: gentle blast (off; big blast off) | blast damage 2200 -> 50 | the charged hit barely hurts anything; the normal swing (300) is unchanged |

For each toggle, please report:

- what you saw, compared with vanilla;
- the log line (APPLIED, or the error);
- anything that looked broken, or a crash.

Solo first. Then, if you can, with a friend running the same mod. The values belong to the machine that simulates
the weapon or the avatar, so report who held the weapon or wore the pack.
