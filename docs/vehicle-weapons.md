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
| Local settings | `ProjectileWeaponComponentData` (fire rate), `WeaponMagazineComponentData`, `WeaponReloadComponentData`, `HealthComponentData` (the mount's health, armor and hit zone) | Weapon-local |
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
- **Mounts without a weapon component:** the Maelstrom turret ring, the Breakthrough's left mount and
  seats are listed with a reason.
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

The drone reloads from its backpack (`hd2.backpack(name)` `deposit.*`, the published drone magazines), so the
drone weapon's own spare-magazine counts are not exposed. The drone's health and body zone are backpack fields
(`hd2.backpack(name):drone()`, see [Backpack authoring](backpack-authoring.md)). Every drone field needs
`allow_unverified_effect`.
