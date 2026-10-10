# Vehicle weapons

Mounted weapons on vehicles, Exosuits, the GATER oil rig and the Guard Dog drones are ordinary weapon entities.
The runtime reaches each one through its carrier's mount slot, and edits it the same way as a support weapon.

```lua
-- Emancipator: each autocannon arm 100 -> 150 rounds (see examples/projects/EmancipatorAmmo)
local emancipator=hd2.vehicle('EXO-49 Emancipator Exosuit')
hd2.ensure({plan={id='emancipator-ammo',operations={
    {id='left',target=emancipator:weapon('left_gun'),field=hd2.fields.weapon.capacity,expect=100,value=150},
    {id='right',target=emancipator:weapon('right_gun'),field=hd2.fields.weapon.capacity,expect=100,value=150}}}})
```

## Ownership chain

| Step | Native object | Scope |
| --- | --- | --- |
| Vehicle | `MountComponentData`: 5 slots × 24 bytes, with the mounted entity path at `slot*24` | Re-proven on every write |
| Mounted weapon | The slot's entity, which owns its own component records | Weapon-local |
| Local settings | `ProjectileWeaponComponentData` (fire rate), `WeaponDataComponentData` (spread), `WeaponMagazineComponentData`, `WeaponReloadComponentData`, `HealthComponentData` (the mount's health, armor and hit zone) | Weapon-local |
| Attack | `ProjectileWeaponComponentData.projectile_type` → `ProjectileSettings`; `SprayWeaponComponentData` → `DamageInfo`; `BeamWeaponComponentData` → `BeamSettings` → `DamageInfo`; `ArcWeaponComponentData` → `ArcSettings` → `DamageInfo` | Shared rows |
| Damage | `DamageInfo` from the projectile or the spray | Shared rows |
| Explosion | The projectile's impact `ExplosionSettings` and its `DamageInfo` | Shared rows |

Before every write, the runtime re-reads the vehicle's `MountComponentData` and checks that the
slot still names the reviewed weapon. If it does not, for example after a mount swap, the write
fails.

## Accessors

- `hd2.vehicle(name):weapons()`: every mounted weapon, in slot order.
- `hd2.vehicle(name):weapon(identity)`: one mounted weapon. `identity` can be a slot number, a mount
  label (such as `'left_gun'` or `'attach_tank_gun'`), the weapon key (`'<vehicle> / <label>'`) or
  its `semanticId`.
- `hd2.vehicle(name):mount(label):weapon()`: the weapon in that mount.
- `hd2.vehicle('EXO-55 Breakthrough Exosuit'):shield()`: the Breakthrough's shield arm (its left mount, no weapon
  component; see EXO-55 Breakthrough shield arm).
- `weapon:projectile()`, `weapon:explosion('impact')` and `weapon:attack(role)`: the weapon's shared
  attack objects. `weapon:describe()` lists every field with its baseline, scope and required
  acknowledgements.

Each mount is its own weapon. The Maelstrom's main gun, missile pod and twin launchers are separate
weapons, and so are the two arms of each Exosuit. An edit to one never changes another's
weapon-local records.

## Fields

| Field constant | Target | Backing |
| --- | --- | --- |
| `hd2.fields.weapon.fire_rate` | weapon | `ProjectileWeaponComponentData` +8 (rpm) |
| `hd2.fields.weapon.horizontal_spread`, `vertical_spread` | weapon (projectile mounts) | `WeaponDataComponentData` +84 / +88 (mrad, full width; see Spread) |
| `hd2.fields.weapon.capacity` | weapon | `WeaponMagazineComponentData` +136 |
| `hd2.fields.magazine.starting_magazines`, `magazines_from_supply`, `spare_magazines` | weapon | `WeaponMagazineComponentData` +140 / +144 / +148 |
| `hd2.fields.reload.duration` | weapon | `WeaponReloadComponentData` +56 (only where the value is non-zero) |
| `hd2.fields.entity.health`, `hd2.fields.entity.armor` | weapon | The mount's own `HealthComponentData` +0 / +280 |
| `hd2.fields.beam.fire_rate` | weapon | `BeamWeaponComponentData` +104 (rpm: how often the beam applies damage) |
| `hd2.fields.heat.capacity`, `heat_per_shot`, `heat_per_second`, `cool_per_second` | weapon | `WeaponHeatComponentData` +96 / +116 / +120 / +128 |
| `hd2.fields.beam.radius`, `beam.length` | `weapon:attack('primary')` (beam) | Shared `BeamSettings` +4 / +8 |
| `hd2.fields.arc.velocity`, `range`, `distance_at_max_spread`, `max_angle_spread`, `chain_count`, `max_split` | `weapon:attack('primary')` (arc) | Shared `ArcSettings` |
| `hd2.fields.zone.health`, `hd2.fields.zone.armor` | weapon | The mount's single hit zone (Exosuit arms) |
| `hd2.fields.projectile.*` | `weapon:projectile()` | Shared `ProjectileSettings` |
| `hd2.fields.damage.player_standard_damage`, `player_durable_damage`, `ap_*`, `demolition`, `stagger`, `push_force` | `weapon:projectile()`, or the spray attack | Shared `DamageInfo` |
| `hd2.fields.explosion.*_radius`, `hd2.fields.explosion.damage_*` | `weapon:explosion()` | Shared `ExplosionSettings` and its `DamageInfo` |
| `hd2.fields.turret.yaw_speed`, `pitch_speed`, `yaw_min`, `yaw_max`, `pitch_min`, `pitch_max` | weapon (turret mounts only) | The mount's own `TurretComponentData` +12 / +8 / +28 / +32 / +20 / +24 (see Turret motion) |

## Turret motion

Five mounted weapons own a `TurretComponentData`:
- the M-103 Supply FRV gun;
- the TD-220 Bastion `attach_tank_gun` (cannon) and `attach_tank_gun_mg`;
- the TD-110 Maelstrom `attach_tank_gun`;
- the GATER Oil Rig turret.

They take the same turret ids as sentries: one semantic layer. Every other mount aims through its vehicle, seat or
Exosuit arm and has no turret record, so the fields are refused there:
- the M-102 and Super Earth FRV gun;
- the M-104 flamethrower;
- the Maelstrom launchers;
- every Exosuit arm;
- the Guard Dog drones.

| Field | Backing | Range | When it applies |
| --- | --- | --- | --- |
| `turret.yaw_speed` | +12, degrees per second (M-103 130, tank guns 35, GATER 60) | 1 to 720 | Copied into the turret when the vehicle is created: call in a new vehicle |
| `turret.pitch_speed` | +8, degrees per second (M-103 90, tank guns 25, GATER 20) | 1 to 720 | Copied when the vehicle is created |
| `turret.pitch_min` / `pitch_max` | +20 / +24, degrees (M-103 −60/90, tank guns −3/25, GATER −13/60) | −90 to 90, min < max | Re-read every turret update: immediate |
| `turret.yaw_min` / `yaw_max` | +28 / +32, degrees (M-103 and GATER −180/180, tank guns −20/20) | −180 to 180, min < max | Re-read every turret update: immediate |

- **Rates.** The turret update multiplies each rate by the turret's own speed modifier and eases it within the last 5
  degrees of the target.
- **Limits.** An arc of 360 degrees (−180 to 180) turns freely.
- **Pairs.** A limit pair must stay ordered after the operation. A limit the operation does not write keeps its
  reviewed value, so change both in one transaction when they cross (`TURRET_LIMIT_ORDER`).
- **Scope.** Each turret record has one owner, so no field needs `allow_shared`.
- **Evidence.** Every field needs `allow_unverified_effect`, because sentry live evidence does not transfer to vehicles
  (live test: examples/projects/VehicleTuningTest).
- **Open question.** The Bastion and Maelstrom guns carry a ±20 degree horizontal arc. Whether it limits the gun inside
  its turret or the turret itself is part of the live test; the record behind the tanks' 360-degree main-turret
  traverse is not identified.

```lua
-- TD-220 Bastion cannon: a narrow 10-degree arc and more elevation; a deployed Bastion follows at once.
local cannon=hd2.vehicle('TD-220 Bastion MK XVI'):weapon('attach_tank_gun')
hd2.ensure({transaction={id='bastion-arc',target=cannon,allow_unverified_effect=true,changes={
    {field=hd2.fields.turret.yaw_min,expect=-20,value=-5},{field=hd2.fields.turret.yaw_max,expect=20,value=5},
    {field=hd2.fields.turret.pitch_max,expect=25,value=45}}}})
```

## Spread (0.30.4)

Every projectile mount carries the player weapons' spread pair, `hd2.fields.weapon.horizontal_spread` and
`hd2.fields.weapon.vertical_spread`, on its own `WeaponDataComponentData` (+84 / +88). That covers 17 mounts:

- every Exosuit gun (Patriot minigun and missile pod, both Emancipator autocannons, the Lumberer cannon and the
  Breakthrough flak cannon);
- the M-102 / Super Earth FRV gun (one entity: `allow_shared`) and the M-103 gun;
- the Bastion and Maelstrom guns and launchers (Maelstrom slots 3 and 4 are one entity: `allow_shared`);
- the GATER turret and the AX/AR-23 Guard Dog gun.

The values are the full width in milliradians; a shot turns by up to half of it each way. The range is 0 to 1000
(1000 = ±28.6 degrees). The widest native value is the Breakthrough flak cannon's 200.

```lua
-- EXO-55 Breakthrough: flak cannon spread x5 (200 -> 1000 mrad); call in a new Exosuit after the write.
local flak=hd2.vehicle('EXO-55 Breakthrough Exosuit'):weapon('right_gun')
hd2.ensure({transaction={id='breakthrough-spread',target=flak,allow_unverified_effect=true,changes={
    {field=hd2.fields.weapon.horizontal_spread,expect=200,value=1000},
    {field=hd2.fields.weapon.vertical_spread,expect=200,value=1000}}}})
```

Why the mounted guns read it (`scripts/research_mounted_spread_shield.py`, `research/mounted-spread-shield-*.json`):

- **Instance.** WeaponData's post-create callback (game.dll 0x54026D → 0x752370) builds every WeaponData instance
  from its type record when the entity is created. The spread pair lands at instance +0x58 (0x75263D/0x752643). The
  callback belongs to the component, whatever wields the weapon.
- **Shot.** The projectile shot (0x615940) looks up the firing weapon entity's own WeaponData instance (component
  map game+0x3326CE0, 0x3F0 per instance, 0x615976..0x615A3A). It passes instance +0x58 to the turn at 0x759740 on
  every shot (0x615BAB/0x615BBA). No branch tests the wielder. This is the read sentries and the Pelican chin gun
  already rely on.
- **Pellets.** For a plain projectile, the fire routine 0x6128B0 calls the shot once per pellet: `pellet_count` of the
  projectile row, 0x614445..0x6144F3. So every one of the flak round's 40 pellets is turned by the spread.
- **No other route.** The shot is called only from 0x6128B0, and none of the 74 game.dll functions that touch the
  ProjectileWeapon component spawns a projectile row itself.
- **Published values.** The wiki spread of all 13 published mounted weapons equals their +84/+88.

Notes:
- **Timing.** The instance is a copy, so an edit reaches vehicles called in after it. A vehicle already in the world
  keeps its spread.
- **Scope.** Each WeaponData record has one owner (weapon-local). The FRV gun and the Maelstrom launchers are shared
  mounted weapons.
- **Multiplayer.** This is a type-record edit: it reaches every vehicle created on this machine. A shot's spread is
  drawn by the machine that fires it.
- **Acknowledgement.** Every spread field needs `allow_unverified_effect` (not live-tested on a mount).
- **Not exposed.** Spray, beam and arc mounts (M-104, Lumberer flamethrower, Hot Dog, Dog Breath, Rover, K-9) keep
  their WeaponData spread unexposed: the shot's read is not on their attack path. This is the sentry rule.

## EXO-55 Breakthrough shield arm (0.30.4)

The Breakthrough's left mount (`left_gun`, slot 0) holds `combat_walker_shield`. It is a wieldable unit with its own
`HealthComponent`, `WeaponData`, `MeleeShield` and `AbilityWeapon` (the shield bash). It has no projectile, spray,
beam or arc component and **no `ShieldComponent`**: it is a physical shield, not an energy barrier. So there is no
capacity, recharge delay, broken delay or recharge rate to tune (those are the SH-32 / SH-51 barrier fields in
[Backpack authoring](backpack-authoring.md)).

Its health record (one owner) is exactly the wiki anatomy of the Breakthrough:

| Zone | Hit actors | Armor | Health | Field on `hd2.vehicle('EXO-55 Breakthrough Exosuit'):shield()` |
| --- | --- | --- | --- | --- |
| ShieldArm (zone 0) | `damageable_base`, `damageable_arm`, one unnamed | 3 (Medium) | the arm pool, 800 | `entity.health` (800, at least 1) |
| Shield (zone 1) | `damageable_shield` | 4 (Heavy) | its own 5000, does not count toward the arm | `zone.health` (5000, at least 1), `zone.armor` (4, 0 to 10) |

```lua
-- Breakthrough shield plate 5x health (5000 -> 25000); call in a new Exosuit after the write.
local shield=hd2.vehicle('EXO-55 Breakthrough Exosuit'):shield()
hd2.ensure({patch={id='breakthrough-plate',target=shield,field=hd2.fields.zone.health,expect=5000,value=25000,
    allow_unverified_effect=true}})
```

Notes:
- **Zone lookup.** A hit resolves to the zone that lists the hit actor (0x922060, see the SH-20 armor section of
  Backpack authoring). Plate hits use the Shield zone; arm and base hits use the ShieldArm zone, whose damage goes to
  the 800 pool.
- **Mount chain.** Every write re-proves the Exosuit's mount slot 0 like a mounted weapon's.
- **Timing.** The health instance copies the values when the Exosuit is created: an edit reaches Exosuits called in
  after it.
- **Acknowledgement.** All three fields need `allow_unverified_effect`: they use the arms' mount-health model, but
  they are not live-tested on the shield arm.
- **Read-only.**
  - `entity.armor` (+280, the default zone) is only the fallback for an actor no zone lists.
  - The ShieldArm zone's armor (3) is a second zone; the target carries the plate zone only.
- **`:shield()`** errors on vehicles without a reviewed shield mount. `:weapons()` does not list the shield arm.

## Projectile swaps

Mounted projectile weapons are projectile hosts by the same rule as player and support weapons
([attack outputs](attack-outputs.md), mounted hosts). Nine qualify:
- EXO-45 Patriot minigun;
- both EXO-49 Emancipator autocannons;
- EXO-51 Lumberer cannon;
- M-102 Gunner FRV gun and the Super Earth FRV gun (one weapon entity: `allow_shared`);
- M-103 Supply FRV gun;
- GATER Oil Rig turret;
- AX/AR-23 Guard Dog gun.

```lua
local patriot=hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('right_gun')
local source=patriot:projectile_source()
hd2.ensure({transaction={id='patriot-eat',target=source.target,allow_unverified_effect=true,
    allow_unverified_reference=true,changes={{field=source.field,expect=source.expect,
    value=hd2.attack_output('EAT-17 Expendable Anti-Tank')}}}})
```

- **Donors.** Any catalogued projectile output, or another weapon's attack projectile (player, support or mounted).
  Beam, arc and spray outputs are refused.
- **Mounted donors.** A mounted weapon's own output is a donor for any host.
- **Assets.** Packages load first; the Guard Dog gun's package is unknown, so it is refused as a donor.
- **Read-only mounts** give their reason in `projectile_source()`.
- **Slots.** The mount's bullet row slots (`hd2.fields.projectile.impact_explosion`, ...) change every entity that fires
  that row. A slot write edits the row, not the mount: it reaches the mount only while the mount fires that row, and
  it does not follow a swapped projectile ([host swaps and slot writes](attack-outputs.md)).
- **Live evidence.** Three kinds of operation are live-proven, each separately and only for these values:
  - **Host swap:** the Patriot minigun ← EAT-17, LAS-58 Talon and PLAS-1 Scorcher.
  - **Host-native row slot:** the Patriot bullet row's impact explosions (GL-21, Speargun gas, EMS Mortar field,
    EAT-700 napalm), while the minigun fires its own bullet.
  - **Donor-row slot:** the LAS-58 Talon row with the GL-21 grenade blast, while the minigun fires Talon.

  Every other mount, donor, row and effect keeps its acknowledgements.

## Scopes and acknowledgements

- **`weapon_local`:** a record owned by exactly one mount. No `allow_shared` is needed.
- **`shared_mounted_weapon`:** one weapon entity sits in several mounts, so its own records change all
  of them. This applies to the M-102 Gunner FRV and Super Earth FRV gun, and to Maelstrom slots 3
  and 4. Requires `allow_shared=true`.
- **`shared_projectile`, `shared_damage`, `shared_explosion`, `shared_beam`, `shared_arc`:** settings rows. Every consumer listed in
  `otherConsumers` changes, including player and support weapons. For example, the Patriot HMG
  round is also used by the MG-43 and several sentries. Requires `allow_shared=true`.
- **`allow_unverified_effect`:** required for every field that no working reference mod has changed in
  game. The fields that reference mods have changed are the M-103 gun magazine, both Emancipator and
  Lumberer magazines, and the Patriot magazines, fire rate, arm health, armor and hit zone, and
  missile and HMG damage. These are listed in `gameplayEvidence` and need no acknowledgement.

## Not exposed

- **ProjectileWeapon damage/armor-penetration addends (+128/+136):** the type library names +128
  `damage_addends` and +136 `ap_addends`. The M-103 turret reference mod reports them the other way
  round in game. They stay read-only until one in-game test settles it.
- **Mounts without a weapon component:** the Maelstrom turret ring, the M-103 rack and the seats are listed with a
  reason. The Breakthrough's left mount is the shield arm (0.30.4): its arm health and plate health and armor are
  fields, while its default-zone armor, its arm-zone armor and any `shield.*` field (no ShieldComponent) are
  read-only (see EXO-55 Breakthrough shield arm).
- **Spread of spray, beam and arc mounts:** no read on their attack path is shown (the sentry rule).
- **Recoil, sway and ergonomics (WeaponData +0..+32, +104, +356):** each shot kicks the wielder's aim (0x784CE2).
  Which aim a mounted weapon's wielder is (the Exosuit, a seat or the vehicle) is not traced, and no read of sway or
  ergonomics on the mounted fire path is shown.
- **Health "max armor" values (+288, zone +224):** their meaning is not established.

`sdk/VehicleWeaponCapabilities.json` lists every vehicle, mount and field instance. For each field it
gives the baseline, scope, other consumers, acknowledgement, gameplay evidence and API constant. It
never includes a native address or raw resource identifier.

## Guard Dog drones

The five Guard Dog backpacks deploy a drone, and each drone carries one weapon in mount slot 0. The chain is backpack
-> `DepositComponent` +24 (the drone entity) -> the drone `MountComponent` slot 0 -> the drone weapon. Before every
write the runtime re-proves both links: the backpack still names the drone, and the drone mount still holds the
weapon. The drones appear in `sdk/VehicleWeaponCapabilities.json` as carriers (`carrier.kind = backpack_drone`,
keyed by the backpack name).

```lua
local gun=hd2.backpack('AX/AR-23 Guard Dog'):drone():weapon()      -- 'AX/AR-23 Guard Dog / gun'
hd2.ensure({patch={id='dog-drum',target=gun,field=hd2.fields.weapon.capacity,expect=45,value=200,
    allow_unverified_effect=true}})
```

| Drone | Weapon family | Weapon fields |
| --- | --- | --- |
| AX/AR-23 Guard Dog | projectile | fire rate 660, magazine 45, reload, projectile and damage (shared with the AR-23P and the M-103 gun) |
| AX/LAS-5 Rover | beam + heat | `beam.fire_rate` 60, heat 200 / 2 per shot / cools 50, reload, beam and damage, Fire |
| AX/FLAM-75 Hot Dog | spray | magazine 80, spray damage and statuses (the damage row is shared with the FLAM-66 Torcher) |
| AX/ARC-3 K-9 | arc | magazine 100, arc range 55 / chain 2 / split 5, damage, Stun Small |
| AX/TX-13 Dog Breath | spray | magazine 100, spray damage, Gas and Gas Confusion |

**Rover beam (0.30.4).** The Rover gun's own BeamWeapon record carries `beam.fire_mode`, `beam.pulse_beams` and
`beam.pulse_seconds` too (the player fields; `allow_unverified_effect`). Its beam reference is read-only: its record names
BeamType 25, but its default muzzle (Laser. Standard Prism, the LAS-5 Scythe's) patches BeamWeapon +0 to the Scythe's
beam when a weapon is built, and that is live-proven for player weapons only. `rover:beam_source()` says so; the
Scythe's beam swap (its muzzle) may reach the Rover too, which `proof/BeamSwapProof` checks. See
[attack outputs](attack-outputs.md) "Beam swaps".

**A/LAS-98 Laser Sentry (0.30.4).** Its deployed entity is a beam host on the sentry host model (`A/LAS-98 Laser Sentry
/ weapon`, `stratagemBeamHosts`): `hd2.stratagem('A/LAS-98 Laser Sentry'):attack('primary'):beam_source()` returns the
target for `hd2.fields.attack.beam` (any catalogued beam output) and `beam.fire_mode` / `beam.pulse_beams` /
`beam.pulse_seconds`; `beam.fire_rate` stays on `hd2.stratagem(name):deployed_entity():weapon()`. Type-level: every
Laser Sentry on this machine fires the donor beam.

The drone reloads from its backpack (`hd2.backpack(name)` `deposit.*`, the published drone magazines), so the
drone weapon's own spare-magazine counts are not exposed. The drone's health and body zone are backpack fields
(`hd2.backpack(name):drone()`, see [Backpack authoring](backpack-authoring.md)). Every drone field needs
`allow_unverified_effect`.
