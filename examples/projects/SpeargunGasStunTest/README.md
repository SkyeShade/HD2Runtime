# SpeargunGasStunTest

Live test: an S-11 Speargun with two player-selectable ammunition types, **Gas** (its own spear) and **Stun**. Uses
the MODS tab (Mod Options Menu, page **Speargun Gas Stun**). Needs this HD2Runtime test build (not the published
0.27.0).

The Speargun has no second magazine and Runtime never changes a weapon's component layout. The game has another
native two-projectile mechanism: the **ProgrammableAmmo** weapon function. While it is switched on, every shot fires
the weapon's function projectile instead of its normal one; the AC-8 Autocannon (flak), GR-8 Recoilless Rifle and
RL-77 use it. The Speargun has that member (empty) and a free left weapon-function input. One transaction binds the
function to that input and sets the function projectile to the chosen stun ammunition, whose package loads first.

| Stun ammunition (option) | What it is |
| --- | --- |
| GL-52 Arc grenade (default) | the De-Escalator arc grenade: arc on impact, stuns (a live-proven donor) |
| AR-32 Pacifier round | the Pacifier's stun bullet |
| SMG-72 Pummeler round | the Pummeler's stun bullet |

## How to test

1. Check the log: the donor package loads (`assets for speargun-gas-stun requested` / `resident`), then
   `transaction speargun-gas-stun APPLIED` with `weapon_function.left none -> programmable_ammo`.
2. Call in a **fresh** Speargun (the binding is copied into the weapon when it is built).
3. Fire normally: gas spears, as vanilla.
4. Open the weapon-function menu: is there a new entry (the game's programmable-ammunition function)? Switch it on
   and fire: the Speargun should fire the stun ammunition. Switch it off: gas again.
5. Change the stun option, APPLY, call in a fresh Speargun and repeat.
6. Check magazine, reload and handling are unchanged in both modes, and that ammunition is used in both.
7. Turn **Enabled** off, APPLY, fresh Speargun: gas only, no extra menu entry.

Report the menu entry (label), what each mode fired, and whether switching worked mid-magazine. The fire-path
override is proven natively (see `docs/weapon-feeds.md`); this is the first live test of adding it to a weapon
(`allow_unverified_effect`, `allow_unverified_reference`).
