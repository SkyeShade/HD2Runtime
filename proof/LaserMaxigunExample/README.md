# LaserMaxigunExample 0.1.1

The **LAS-1000 Laser Maxigun**: a mission-scoped variant of the M-1000 Maxigun on its own type. It fires the LAS-58
Talon's laser round and can show a **Runtime-owned debug model**. Needs HD2Runtime 0.30.0-dev (r25 or later), the Mod
Options Menu, and the other test mods removed. Not live-tested yet.

- **Carrier.** The Maxigun is the only support weapon with its component set, so the Maxigun's own stratagem carries
  everything: its row presents as the Laser Maxigun and answers to DOWN UP UP DOWN DOWN LEFT. Its own pod brings the gun
  and its backpack, and its type is the variant for the mission.
- **No fallback.**
  - If anyone in the lobby brings the vanilla Maxigun, the Laser Maxigun is unavailable (its tile warns).
  - While the Laser Maxigun is selected, the vanilla Maxigun is blocked in the native picker.
- **The debug model.** `models/laser_maxigun.json` is the Maxigun's own mesh with a debug palette: each of its 8 colour
  zones is a different bright colour (red, green, blue, yellow, magenta, cyan, white, orange). The build derives it from
  your installed game and ships it as a patch of the Maxigun's package archive (`mod/b2c627b3ba7e0c0a.patch_0`),
  beside the vanilla model. The vanilla Maxigun is never changed.

| Mod Options > Laser Maxigun | Default | What it does |
|---|---|---|
| Model | Check only (vanilla model) | At mission start: `Check only` logs whether the debug model is loaded and keeps the vanilla model; `Debug model` shows it on the Laser Maxigun |

## Live test, in order

1. **Ship.** The log names the build: `LaserMaxigunExample 0.1.1 LASER MAXIGUN CODE FIX BUILD`, then
   `custom model mods/skyeshade/hd2runtime_laser_maxigun_example/models/laser_maxigun (...): derived from the M-1000
   Maxigun unit ...`.
   - Select the Laser Maxigun in the custom panel. The vanilla Maxigun card is blocked (`CARRIER BLOCKS`).
   - Deselect it: the card is released.
2. **Mission 1, Model = Check only.** Expect:
   - `MODEL READY` for the M-1000 Maxigun. If you see `MODEL NOT READY`, send the reason.
   - `APPLIED (laser_maxigun): M-1000 Maxigun is its own VARIANT for this mission` (presentation and round, no model).

   Call it in, pick up the gun with its backpack, and fire:
   - it should fire Talon laser bolts, with the Maxigun's spin-up and belt;
   - it shows the Laser Maxigun name and icon on its pickup prompt and weapon panel;
   - nothing crashes while the Maxigun package is loaded, which is the debug model's patch loading.
3. **Back on the ship.** Expect `RESTORED`: the Maxigun is its own weapon again.
4. **Mission 2, Model = Debug model.**
   - Expect `MODEL READY`, then `APPLIED ... model model 'laser_maxigun' ...`.
   - The called Maxigun shows the debug colours in first and third person; tell me which colour is on which part.
   - Its spin-up, belt and backpack link work, and it fires Talon bolts.
5. **Back on the ship again.** Expect `RESTORED`. A vanilla Maxigun in a later mission must look and fire vanilla.
6. **Multiplayer**, every player with the same Runtime and this mod, all on the same Model choice. Each machine logs its
   own `APPLIED`, and teammates see the Laser Maxigun as you do.

Send `HD2Runtime.log` after each step, and a screenshot of the debug model.
