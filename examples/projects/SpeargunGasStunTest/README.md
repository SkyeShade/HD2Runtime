# SpeargunGasStunTest

Live test: an S-11 Speargun with two player-selectable modes, **Gas** (its own spear) and **Stun**, an EMS field
where the shot lands. Uses the MODS tab (Mod Options Menu, page **Speargun Gas Stun**). Needs HD2Runtime
0.28.0.

The previous run (GL-52 donor) proved the selector works, but the GL-52 arc grenade does heavy electric damage
rather than stunning an area. The research (`docs/weapon-feeds.md`, stun-field donors) found what a stun field is
natively. The Speargun's gas cloud is a *status volume* that its spear's explosion leaves where it lands (Gas, 10 s).
The EMS field is the same mechanism with the StaticField template: Stun Medium, no damage. The **A/M-23 EMS Mortar
Sentry shell** leaves one for 7 s with a 10 m radius, and it is now the stun mode. Runtime loads the EMS Mortar
turret's package before writing it (like the GL-52's before).

| Option | Default | What it does |
| --- | --- | --- |
| Enabled | on | binds ProgrammableAmmo to the left input and sets the function projectile to the EMS Mortar shell |
| Mode labels | on | names the modes **GAS** (generic ammunition icon) and **STUN** (the game's stun icon) in the weapon-function menu |

The labels are the game's own: a weapon-function menu shows each mode's projectile label and icon (the AC-8 shows
APHET / FLAK, the Halt FLECHETTES / STUN). The spear and the EMS shell have none, so without the labels the menu
shows a blank entry with no usable icon. GAS and STUN are native strings; the stun icon is the Halt's. The game has no
gas mode icon, so GAS uses `mode_icon = "auto"`, which picks the generic ammunition icon (a plain round, the one
native weapon-function icon that implies no effect).

## How to test

1. Check the log: the EMS package loads (`assets for speargun-gas-stun requested` / `resident`), then
   `transaction speargun-gas-stun APPLIED`, `transaction speargun-gas-label APPLIED`
   (`presentation.mode_icon default -> ammo_slug`) and `transaction speargun-stun-label APPLIED`.
2. Call in a **fresh** Speargun (the binding is copied into the weapon when it is built).
3. Fire normally: gas spears and the gas cloud, as vanilla.
4. Open the weapon-function menu: is there a programmable-ammunition entry, and does it read **GAS** (a plain
   round icon) / **STUN** (stun icon)? Switch to STUN and fire at a group of enemies **at least 15 m away** (an EMS field can stun
   Helldivers too): the shell should land and leave an EMS field that holds enemies stunned for about 7 s.
   Switch back: gas again.
5. Turn **Mode labels** off, APPLY, reopen the menu: the labels and icons should return to the game defaults (no
   label, no usable icon). Report whether reopening the menu was enough or a fresh Speargun was needed.
6. Check magazine, reload and handling in both modes, and that ammunition is used in both.
7. Turn **Enabled** off, APPLY, fresh Speargun: gas only, no extra menu entry.

Report what the menu shows (labels, icons), what the stun mode does on impact (does the field appear, how long
enemies stay stunned, its size), how the shell flies (it keeps the mortar shell's speed and drop), and anything
unexpected. `allow_unverified_effect` and `allow_unverified_reference` are set: the function-projectile mechanism is
live-proven (previous run), but the EMS donor and the mode labels are new.
