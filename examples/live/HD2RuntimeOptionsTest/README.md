# HD2RuntimeOptionsTest

Live-validation mod for HD2Runtime 0.25.0 in-game options. It is not a release example and is
not part of the example-projects ZIP.

Confirmed in game with HD2Runtime 0.25.0, Mod Options Menu v1.0.1 and Bingus Shared Loader v18
(Steam build 25480438):

- the controls work;
- APPLY updates the managed value;
- disabling restores 90;
- without the menu, only this operation is disabled;
- a saved value of 230 survived a full restart and was applied at startup.

Adds an **HD2Runtime Options Test** page to the MODS tab (CowboyBingus Mod Options Menu):

- **Enabled** toggle (default on). Off restores the vanilla AR-23 Liberator damage (90) through
  the guarded path; on applies the slider value again.
- **Liberator Damage** slider, 90–300 in steps of 10, default 100.

One `hd2.ensure` (`options-test-liberator-damage`) owns the write to the AR-23 Liberator primary
projectile's `damage.player_standard_damage`, with `expect=90` and `allow_shared=true` (the row
is shared with the AR-23A Liberator Carbine and StA-52). Changes take effect on APPLY.

Mod Options Menu v1+ (Bingus Shared Loader v18+) is an optional dependency: without it the mod
logs one warning and leaves the Liberator unchanged. Saved ids are
`hd2runtime_options_test.enabled` and `hd2runtime_options_test.liberator_damage`.

Build: `python build.py` (output in `build/`).
