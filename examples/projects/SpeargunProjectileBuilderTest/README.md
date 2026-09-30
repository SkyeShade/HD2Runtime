# SpeargunProjectileBuilderTest

Live test for the projectile builder (`weapon:programmable_ammo()`). Uses the MODS tab (page **Speargun Projectile
Builder**). Supersedes the second mode of SpeargunGasStunTest, which fired the EMS Mortar's shell: here the stun
mode keeps the Speargun's own spear.

| Option | Default | What it does |
| --- | --- | --- |
| Stun spear mode | on | adds mode B: the spear, leaving an EMS stun field instead of gas |
| GAS label | on | names the normal mode GAS (plain round icon) |

Where the Speargun's gas comes from (research/projectile-builder-F5FEE03DCFDB.json):

- **Direct hit**: the spear's damage row applies gas and gas confusion to what it hits.
- **Impact explosion**: none.
- **Expiry explosion**: when the spear expires (stuck in the ground or a target) its expiry explosion leaves the gas
  cloud, a Gas status volume (10 s, radius 5).

Mode B is built from native pieces only:

- **Base**: the Speargun's *spare twin*, a native projectile row that no typed data member references and that is
  byte-identical to the spear except its references (same velocity, mass, model, trail and sound). Nothing else fires
  it, so no other weapon changes. Runtime re-proves the twin match live before every write. It is a borrowed vanilla
  row, an interim until Runtime owns projectile ids of its own.
- **Expiry explosion**: pointed at the A/M-23 EMS Mortar shell's expiry explosion, which leaves a StaticField (Stun
  Medium, no damage) instead of gas. Runtime loads the EMS turret's package first.
- **Direct hit**: unchanged (the spear's own gas damage row). A stunned target hit directly still takes gas.
- **Label and icon**: STUN with the game's stun icon.

## How to test

1. Check the log: `transaction spear-stun-mode APPLIED`, `spear-stun-slots APPLIED`, `spear-stun-label APPLIED`,
   `spear-gas-primary-label APPLIED`.
2. Call in a **fresh** Speargun after APPLY.
3. Open the weapon-function menu: two modes, **GAS** (plain round icon) and **STUN** (stun icon).
4. GAS: fire into a group; the spear flies and sticks as normal and leaves a green gas cloud.
5. STUN: the same spear flight and model; where it expires, an EMS field (blue) stuns enemies instead of gas.
6. Everything off, APPLY, fresh Speargun: vanilla (one mode, gas).

Report whether mode B's spear looked and flew like the normal spear, whether its field stunned (and for how long),
and whether any other weapon changed. `allow_unverified_effect` / `allow_unverified_reference` are set: the spare
twin and the slot write are mapped offline, not yet shown in game.
