# Player weapon authoring

HD2Runtime 0.18.0 exposes reviewed semantic writes for the complete 80-weapon player catalog and
preserves the earlier ammo semantic aliases.
The generated [capability catalog](../sdk/PlayerWeaponAuthoringCapabilities.json) and [ammo capability catalog](../sdk/PlayerWeaponAmmoCapabilities.json) are the canonical GUI inputs. They record current defaults, backing component or settings record, scalar storage, provenance, editability, derived fields, and shared write scope without publishing runtime addresses.

`hd2.weapon(name)` is the identity root. `patch`, `transaction`, and `ensure` freshly resolve that identity at application time, check the game fingerprints and ownership chain, compare the declared expected value, and pass an exact-width change to the existing guarded transaction engine. A shared settings field is rejected unless the declaration includes `allow_shared=true`. A weapon with multiple indistinguishable runtime resources is rejected for ordinary writes.

Use `hd2.plan` when one logical modification spans multiple semantic targets,
such as ProjectileSettings terminal slots and linked DamageInfo fields. Plans
validate the complete per-phase write set and can be wrapped by `ensure`. See
[guarded composition plans](composition-plans.md).

The opt-in Concussive validation mod is intentionally one declaration:

```lua
local hd2=require('mods/skyeshade/hd2runtime')

return hd2.ensure({
    patch={
        id='concussive-1100-rpm',
        target=hd2.weapon('AR-23C Liberator Concussive'),
        field=hd2.fields.weapon.fire_rate,
        expect=400,
        value=1100,
    },
})
```

Projectile drop is authored through its real inputs. The Verdict defaults are velocity 285, mass 15, drag approximately 1.2, and gravity 1:

```lua
hd2.transaction({
    id='verdict-reduced-drop',
    target=hd2.weapon('P-113 Verdict'),
    allow_shared=true,    -- projectile and DamageInfo rows are shared settings objects
    changes={
        {field=hd2.fields.projectile.drag, expect=1.2, value=0.3},
        {field=hd2.fields.projectile.gravity, expect=1, value=0.25},
    },
})
```

Since the coverage pass, `projectile.penetration_slowdown` (ProjectileSettings +64) is published on all 67 player
projectile branches, and `projectile.lifetime` (+52) on the 10 whose native lifetime is non-zero. The research is
`scripts/research_player_projectile_members.py`.
- **Member proof.** Both members were proven on support weapons by their hidden name lengths (20 and 9) and exact
  wiki values.
- **Independent check.** Each player weapon's own wiki value matches too: penetration slowdown on 67/67 and
  lifetime on 10/10. No value disagrees.
- **Lifetime 0.** A lifetime of 0 means "no explicit limit". Setting it would add a limit rather than tune one, so
  those branches stay unpublished.
- **Sharing.** Like the other projectile members these are shared ProjectileSettings rows, so writes need
  `allow_shared`.

Damage lanes remain independent exact-width fields. This example changes the Verdict's standard damage and direct AP lane while leaving the other AP lanes untouched:

```lua
hd2.transaction({
    id='verdict-damage-example',
    target=hd2.weapon('P-113 Verdict'),
    allow_shared=true,    -- projectile and DamageInfo rows are shared settings objects
    changes={
        {field=hd2.fields.damage.player_standard_damage, expect=140, value=150},
        {field=hd2.fields.damage.ap_direct, expect=3, value=4},
    },
})
```

Non-projectile fields use their native family settings. ARC-12 range is backed by `ArcSettings`:

```lua
hd2.patch({
    id='blitzer-range-example',
    target=hd2.weapon('ARC-12 Blitzer'),
    field=hd2.fields.arc.range,
    expect=25,
    value=30,
})
```

Detachable magazines expose their direct native values under `hd2.fields.magazine`. The ammo-box value is derived from the supply refill and is read-only:

```lua
hd2.transaction({
    id='jar-more-reserve',
    target=hd2.weapon('JAR-5 Dominator'),
    changes={
        {field=hd2.fields.magazine.capacity, expect=15, value=20},
        {field=hd2.fields.magazine.spare_magazines, expect=6, value=8},
        {field=hd2.fields.magazine.starting_magazines, expect=4, value=6},
        {field=hd2.fields.magazine.magazines_from_supply, expect=6, value=8},
    },
})
```

`hd2.fields.weapon.capacity` remains accepted for projects written against 0.13, but it is a
deprecated compatibility alias when it resolves to the same reviewed magazine record as
`hd2.fields.magazine.capacity`. New projects should use the magazine field. A transaction that
declares both aliases with the same desired value is reduced to one physical write. Different
desired values are rejected as `SEMANTIC_CONFLICT` during descriptor validation, before runtime
discovery, page protection changes, or writes.

Rounds-fed weapons retain separate feed and reserve-round semantics. Total capacity and ammo-box refill are derived read-only values:

```lua
hd2.transaction({
    id='punisher-ammo',
    target=hd2.weapon('SG-8 Punisher'),
    changes={
        {field=hd2.fields.rounds.feed_capacity_1, expect=8, value=10},
        {field=hd2.fields.rounds.feed_capacity_2, expect=8, value=10},
        {field=hd2.fields.rounds.spare_rounds, expect=60, value=80},
        {field=hd2.fields.rounds.rounds_from_supply, expect=60, value=80},
        {field=hd2.fields.rounds.starting_rounds, expect=32, value=40},
    },
})
```

The older `weapon.feed_capacity_1` and `weapon.feed_capacity_2` constants remain accepted aliases
for `rounds.feed_capacity_1` and `rounds.feed_capacity_2`. Generated GUI metadata marks the older
names deprecated and non-preferred, so only the canonical rounds controls are editable. The
capability catalog includes a complete identical-backing audit; `weapon.base_capacity` is recorded
as a separate read-only native view because its underlying-base semantics differ from effective
magazine capacity even where both currently read the same bytes.

The current build's customization catalog provides 52 magazine, heatsink, and canister option identities with names and AddPaths. Twenty player weapons select a default option. The research pass inspected all 191 occupied `WeaponCustomizationComponentData` records: only 20 catalog option IDs and six catalog AddPaths occur, and no alternate allowed-option collection or option-owned effect record is present. Effective values remain visible in the capability catalogs, but attachment selection and option-effect editing fail closed.

Seven player weapons own `WeaponHeatComponentData`. The five uniquely resolved weapons expose direct guarded fields through `hd2.fields.heat.*` and `hd2.fields.heatsink.*`:

```lua
hd2.transaction({
    id='sickle-heat-tuning',
    target=hd2.weapon('LAS-16 Sickle'),
    changes={
        {field=hd2.fields.heat.capacity, expect=100, value=140},
        {field=hd2.fields.heat.cool_per_second, expect=8, value=12},
        {field=hd2.fields.heatsink.spare, expect=3, value=5},
    },
})
```

`heat.cool_per_second_cold`, `heat.cool_per_second_hot`, and `heatsink.from_ammo_box` are derived read-only conveniences. Warmup and overheat cooldown remain unresolved. Scythe and Dagger retain duplicate-resource blocking, and Dagger also has unresolved native/wiki scaling disagreements.

`WeaponMagazineComponentData` stores capacity at offset 136, starting magazines at 140, supply refill at 144, and maximum spare magazines at 148. `WeaponRoundsComponentData` stores two feed capacities at 72/76, spare rounds at 80, supply refill at 84, and starting rounds at 88. These offsets are internal metadata; mod declarations use semantic field constants.

Displayed recoil and rounds-feed total capacity are derived read-only values. Edit the four drift/climb recoil inputs or the two feed capacities separately. Projectile and DamageInfo identifiers remain read-only because reference replacement is outside this release. P-2 Peacemaker and P-19 Redeemer expose their weapon-level fields; their customization-supplied projectile, damage, and effective magazine override paths remain unavailable and fail closed.

The seven ambiguous identities are CQC-42 Machete, CQC-73 Entrenchment Tool, GP-31 Grenade Pistol, LAS-5 Scythe, LAS-7 Dagger, P-72 Crisper, and SMG-37 Defender. Their catalog entries remain visible to tools, but ordinary `hd2.weapon(name)` writes are blocked until runtime ownership can select one resource without guessing.

## Firing sound (`weapon.sound`, offline only)

`hd2.fields.weapon.sound` sets a weapon's firing sound to a catalogue sound name, on its type's ProjectileWeapon
record (instantiation only: weapons built after the write). `expect` is the weapon's own catalogued sound; any other
sound needs `allow_unverified_effect` and loads its bank's package first; resident-only sounds (every primary and
secondary weapon's own) are refused. Not live-tested. See [weapon firing sounds](weapon-sounds.md#a-weapons-own-firing-sound-weaponsound-offline-only).

```lua
hd2.patch({id = 'liberator-maelstrom', target = hd2.weapon('AR-23 Liberator'), field = hd2.fields.weapon.sound,
    expect = 'primary/ar23', value = 'vehicle/maelstrom/main_gun', allow_unverified_effect = true})
```

## LAS-17 Double-Edge Sickle heat levels

The LAS-17 `WeaponHeatComponent` carries three typed `HeatLevelSetting` entries (stride 24). Each entry names the
heat at which it applies (+0), the projectile fired from that heat (+4: the published LAS-17 P, P1 and P2), and the
status applied to the wielder while firing (+20). Self-damage is data-driven:

| Level | Heat (of 200) | Wielder status | Tick damage |
| --- | --- | --- | --- |
| 1 | 50 | `hotshot_laser_rifle` | 20 |
| 2 | 100 | `hotshot_laser_rifle_2` | 40 |
| 3 | 190 | `hotshot_laser_rifle_3` | 100, and its damage row applies Fire (strength 10): the self-ignition |

The ignition threshold is the level-3 threshold. It uses the status's damage row, not a hard-coded heat callback,
and the three damage rows are referenced by nothing else.

Fields (all `allow_unverified_effect`):

- `heat.level_1_threshold` .. `heat.level_3_threshold` (0 to 10000).
- `heat.level_1_self_status` .. `heat.level_3_self_status`: one of the three LAS-17 statuses, or `none` for no
  self-damage at that level. Setting level 3 to `hotshot_laser_rifle_2` keeps the heavy pulses without the Fire.
  Other statuses are not offered.
- `heat.overheat_lock` (+80): false only on the LAS-17 among every heat weapon (the other record without it is a
  camera that never overheats). True should make it lock at maximum heat like the LAS-16.

Not offered: redirecting the ignition to another status. That would be the level-3 damage row's status slot,
which only this weapon uses, and it is not authored in this release.
`examples/projects/DoubleEdgeOverheatTest` is the live test.

The LAS-5 Scythe still has no writable fields. Its catalog identity is DUPLICATE: `laser_rifle` and
`laser_rifle_charge` fire the same BeamSettings row. The published Scythe heat data (12.5 heat/s, cooling
12.8 - 8.5 - 6.4) matches `laser_rifle` only. Changing the identity would touch about 45 generated catalogs, so it
is left for a reviewed disambiguation after this release.
