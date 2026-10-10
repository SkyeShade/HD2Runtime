# UserRequestsProof

Development proof for HD2Runtime 0.30.4. It live-tests the answers to three user requests:

- **Charges before cooldown.** `hd2.fields.stratagem.rearm_pool` (StratagemInfo +200) puts a stratagem into the
  Eagle Rearm pool, the game's only charge mechanism. Its `stratagem.max_uses` become charges, `stratagem.cooldown`
  is the wait between charges (shared with every Eagle), and calling Eagle Rearm refills all charges at once. See
  docs/stratagem-uses.md, "Charges before cooldown".
- **Orbital Railcannon targeting.** The strike's own OrbitalAbility record: `orbital.search_radius` (where it looks for
  a target), `orbital.movement_speed` (how fast the red targeting beam swings onto it), `orbital.fire_delay` (start to
  shot) and `orbital.duration` (how long the targeting beam stays), plus the Orbital Laser's
  `orbital.retarget_interval`. See docs/stratagem-authoring.md, "Orbital targeting".
- **Hot-Shot fire modes.** The game's fire-mode selector bound on a free input of the R/40-K Hot-Shot together with a
  second (or third) mode. See docs/fire-modes.md, "Adding the selector".

Each test is one toggle on the mod's options page (MODS tab, **User Requests Proof**). Toggles that edit the same
field must not be on together: the second is refused and logged (CONFLICT).

When each one takes effect:

- **Charges**: from the next mission. Turn the toggle on aboard the ship, then deploy.
- **Railcannon and Laser**: from the next call.
- **Fire modes**: when the weapon is next built. Re-equip it on the ship, or redeploy.

| Toggle (default) | Change | Expected |
|---|---|---|
| Orbital Laser 5 charges (on) | `max_uses` 3 -> 5, `cooldown` 300 -> 15 s, `rearm_pool` none -> eagle_rearm | You can call the Laser five times, each call 15 s after the last. After every Laser call, your Eagles wait 15 s too. Once the Laser and the Eagles are empty, Eagle Rearm starts on its own; calling it earlier also works. Either way the Laser gets all 5 charges back. Vanilla: 3 calls per mission, 300 s apart, never refilled. **Please note what the HUD shows** for the Laser: its charge count, and whether it shows the rearm. |
| Railcannon 3 charges (off) | `max_uses` unlimited -> 3, `cooldown` 180 -> 15 s, `rearm_pool` -> eagle_rearm | three Railcannon calls 15 s apart, then refilled by Eagle Rearm |
| Railcannon search radius 200 m (on) | `orbital.search_radius` 30 -> 200 | Throw the beacon away from enemies. The Railcannon still locks onto an enemy up to 200 m away (vanilla: within 30 m of the beacon, else the shot hits the beacon) |
| Railcannon search radius 3 m (off; 200 m off) | 30 -> 3 | control: it only locks an enemy standing almost on the beacon |
| Railcannon tracking x5 (on) | `orbital.movement_speed` 90 -> 450 | the red targeting beam snaps onto the target almost at once and follows a moving target tightly |
| Railcannon tracking x0.1 (off; x5 off) | 90 -> 9 | the beam drifts slowly toward the target and lags behind a moving one; the shot may miss a fast target |
| Railcannon shot after 0.5 s (off) | `orbital.fire_delay` 1.7 -> 0.5 | the shot comes about 1.2 s sooner after the beam appears |
| Railcannon targeting beam 2 -> 8 s (off) | `orbital.duration` 2 -> 8 | the red beam stays about 6 s longer; still exactly one shot, at the usual time |
| Orbital Laser re-target every 0.25 s (off) | `orbital.retarget_interval` 1 -> 0.25 | the Laser switches to a new target much faster after its target dies |
| Orbital Laser re-target every 30 s (off; 0.25 s off) | 1 -> 30 | control: after its first target dies, the Laser stays put for a long time before moving on |
| Hot-Shot single/auto selector (on) | `fire_mode.modes` {single} -> {single, automatic}, `weapon_function.left` none -> fire_mode | the Hot-Shot now has a fire-mode selector. Switch it like on the Liberator (hold reload, or your fire-mode key): single and full-auto. **Please note** whether the weapon menu and the HUD show the modes. |
| Hot-Shot single/auto/burst selector (off; single/auto off) | {single} -> {single, automatic, burst} + the binding | three modes to cycle through |
| MG-43: auto/single selector beside its rate selector (off) | MG-43 `fire_mode.modes` {automatic} -> {automatic, single}, `weapon_function.left` -> fire_mode | the MG-43 keeps its rate-of-fire selector and gains an auto/single switch |

For each toggle, please report:

- what you saw, compared with vanilla;
- the log line (APPLIED, or the error);
- anything that looked broken, or a crash.

Solo first. Then, if you can, with a friend running the same mod.

- **Charges**: the host applies use counts, so report who hosted.
- **Railcannon**: the machine that builds the strike picks the target, so report who called it.
- **Fire modes**: report who held the weapon.
