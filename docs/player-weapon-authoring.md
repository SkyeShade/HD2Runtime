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

`heat.cool_per_second_cold`, `heat.cool_per_second_hot`, `heat.warmup` and `heatsink.from_ammo_box` are derived read-only conveniences. `heat.overheat_cooldown` has no value of its own; see "Warm-up and cooldown after overheat" below for the fields to edit. Since 0.30.2 the Scythe and Dagger resolve to their proven roots; the Dagger's old 2000-vs-100 heat disagreement came from the wrong root, and its own root agrees with the published values.

`WeaponMagazineComponentData` stores capacity at offset 136, starting magazines at 140, supply refill at 144, and maximum spare magazines at 148. `WeaponRoundsComponentData` stores two feed capacities at 72/76, spare rounds at 80, supply refill at 84, and starting rounds at 88. These offsets are internal metadata; mod declarations use semantic field constants.

Displayed recoil and rounds-feed total capacity are derived read-only values. Edit the four drift/climb recoil inputs or the two feed capacities separately. Projectile and DamageInfo identifiers remain read-only because reference replacement is outside this release. P-2 Peacemaker and P-19 Redeemer expose their weapon-level fields; their customization-supplied projectile, damage, and effective magazine override paths remain unavailable and fail closed.

Seven weapons tie on every compared stat with a second root: CQC-42 Machete, CQC-73 Entrenchment Tool, GP-31 Grenade Pistol, LAS-5 Scythe, LAS-7 Dagger, P-72 Crisper, and SMG-37 Defender. Until 0.30.2 they were blocked (DUPLICATE). Since 0.30.2 each resolves to its proven root (`research/weapon-roots-F5FEE03DCFDB.json`, applied by `scripts/generate_weapon_authoring.py`):

| Weapon | Root | The other root | Proof |
|---|---|---|---|
| GP-31 Grenade Pistol | `0x52E4334E6A128CAF` | the AR/GL-21 One-Two underbarrel | underbarrel host |
| P-72 Crisper | `0x3F92BA65EF65CCA9` | the SMG/FLAM-34 Stoker underbarrel | underbarrel host |
| LAS-5 Scythe | `0x27EE1ED8F6FB6356` | `laser_rifle_charge` | equipped snapshot |
| LAS-7 Dagger | `0x7B06196E90154C88` | a non-loadout beam entity | equipped snapshot |
| SMG-37 Defender | `0x4E4A613EB9BF5C24` | the SEAF SMG | equipped snapshot |
| CQC-73 Entrenchment Tool | `0x7E1F76163C667E4B` | the CQC-72 support shovel | equipped snapshot |
| CQC-42 Machete | `0x792D5D2A340FD6E6` | the CQC-20 Breaching Hammer | its call-in rack attaches the other |

Each catalog entry keeps both `candidateRoots` and a `rootCorrection` (the proof kind). The GP-31 and the Dagger read different values than before, because the first-listed root was the wrong weapon. A field that a default customization item overwrites at every build stays read-only, whatever its own research says.

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

## Missiles: P-33 Missile Pistol, P-92 Warrant (0.30.4, offline only)

The P-33 and the P-92 spawn a missile entity per shot (ProjectileWeapon +40), like the W.A.S.P. Their flight is the
missile's own SeekingMissile record. They take the same `missile.*` fields on `hd2.weapon(name)`. The P-33's
ProgrammableAmmo missile (+584) takes `function_missile.*`. All need `allow_unverified_effect`.

Native values: P-33 starting 10, minimum 10, preferred 100 m/s, acceleration 200, turn 15 / 18, guidance delay 0.01 s.
P-92 Warrant: 90 / 90 / 90 m/s, turn 30 / 30. Meaning, ranges, the re-proven link and multiplayer are in
[support weapons: Missiles](support-weapon-api.md#missiles-wasp-spear-commando-0304-offline-only). Research:
`research/docs/wasp-rocket-F5FEE03DCFDB.md`.

## Wind-up and Trident-like beam blasts (0.30.4, offline only)

Research: `research/docs/las-beam-overhaul-comparison.md` (credit: [Bans](https://ayakamods.com/members/bans.388863/)'s [True Lasgun Beam Overhaul](https://ayakamods.com/mods/true-lasgun-beam-overhaul.4681/) was the lead; every member is proven
from the type library and the retained snapshot). All fields need `allow_unverified_effect`.

**Wind-up (the firing charge), `WeaponHeatComponent`**, on every heat weapon (LAS-16 / LAS-17 Sickles, LAS-5 Scythe,
LAS-7 Dagger, LAS-12 Sai, LAS-13 Trident, LAS-58 Talon; support: LAS-98, LAS-99 Quasar):

| Field | Member | Meaning (lead) | Sickle | Quasar |
| --- | --- | --- | --- | --- |
| `heat.firing_charge` | +148 FP32 | charge needed before the first shot | 100 | 100 |
| `heat.charge_gain_per_second` | +152 FP32 | charge gained per second while the trigger is held | 200 | 33 |
| `heat.charge_loss_per_second` | +156 FP32 | charge lost per second after release | 75 | 500 |
| `heat.reset_charge_after_shot` | +160 UINT8 | the charge starts over after every shot | false | true |

+148 / +152 reproduces every published wind-up (Sickles and LAS-98 0.5 s; Sai, Trident and Talon 0; the Quasar about
3 s). So the Sickles' wind-up is `heat.firing_charge` 0 (instant) or a lower `heat.charge_gain_per_second` (longer).

### Warm-up and cooldown after overheat

Stats editors and the wiki list a weapon's **Warmup** and **Cooldown After Overheat**. Neither is a member of the
weapon's records; each follows from fields you can edit.

- **Warm-up** is `heat.firing_charge / heat.charge_gain_per_second`, the charge built before the first shot divided by
  the charge gained per second. The catalogue publishes it as the read-only `heat.warmup`: derived, with the reason
  "edit heat.firing_charge or heat.charge_gain_per_second". Examples: Sickle 100 / 200 = 0.5 s; LAS-99 Quasar
  Cannon 100 / 33 = about 3 s; Sai, Trident and Talon 0. To shorten the Quasar's charge to 1.5 s, set
  `heat.charge_gain_per_second` 33 -> 66, or `heat.firing_charge` 100 -> 50. Both fields need
  `allow_unverified_effect` (their names are leads, see above).
- **Cooldown after overheat** has no proven member of its own. `heat.overheat_lock` is only the flag that locks the
  weapon at maximum heat. An overheated weapon cools from `heat.capacity` at `heat.cool_per_second`, scaled by the
  game's cold and hot multipliers (`heat.cool_per_second_cold` / `_hot`). `heat.overheat_cooldown` stays read-only,
  and its reason names those two fields. Example: the Quasar's one 100-heat shot fills its 100 capacity, and
  100 / 6.66 per second = about 15 s before the multipliers. To halve it, double `heat.cool_per_second`
  (6.66 -> 13.32), or lower `heat.capacity` together with `heat.heat_per_shot`.
- **Open lead, not exposed:** WeaponHeat +140 (FP32, unnamed) is 400 on every other player heat weapon. On the
  Quasar it is 6.66, the same as its cooling rate, and the Quasar is the only player heat weapon with +144 (lead
  name `needs_reload_after_overheat`) 0. It may be the cooling rate while overheated. If a live test shows that the Quasar's cooldown does not follow
  `heat.cool_per_second`, this member is the next thing to prove (`research/docs/entity-component-table-pointers.md`).

```lua
local quasar=hd2.support_weapon('LAS-99 Quasar Cannon')
hd2.ensure({transaction={id='quick-quasar',target=quasar,allow_unverified_effect=true,changes={
    {field=hd2.fields.heat.charge_gain_per_second,expect=33,value=66},          -- warm-up about 1.5 s
    {field=hd2.fields.heat.cool_per_second,expect=6.659999847412109,value=13.32}, -- cooldown about 7.5 s
}}})
```

If these writes are refused with "the game reads its WeaponHeatComponentData table from another place", another mod
has moved the heat table ([diagnostics](diagnostics.md) "Component tables another mod moved").

**The Trident's beam blast, `BeamWeaponComponent`**, on every beam weapon (LAS-5 Scythe, LAS-7 Dagger, LAS-13
Trident; support: LAS-98, 40-K Meltagun):

| Field | Member | Trident | Continuous beams | 40-K |
| --- | --- | --- | --- | --- |
| `beam.fire_mode` | +100 typed enum | 6 (pulsed; the game's code branches on it) | 4 | 5 |
| `beam.fire_rate` | +104 INT32 rpm | 300 | 60 | 50 |
| `beam.pulse_beams` | +108 INT32 | 2 | 1 | 1 |
| `beam.pulse_seconds` | +112 FP32 | 0.15 | 0 | 1.4 |

The Trident is a beam weapon (a BeamWeapon component, no ProjectileWeapon), not a projectile: each pulse is the same
instant ray query every beam makes. A Trident-like Scythe is one transaction on the Scythe's own record:

```lua
local scythe=hd2.weapon('LAS-5 Scythe')
hd2.ensure({transaction={id='trident-scythe',target=scythe,allow_unverified_effect=true,changes={
    {field='beam.fire_mode',expect=4,value=6},{field='beam.fire_rate',expect=60,value=300},
    {field='beam.pulse_beams',expect=1,value=2},{field='beam.pulse_seconds',expect=0,value=0.15}}}})
```

- **Only weapons that already have a BeamWeapon component.** Turning a projectile weapon (a Sickle, the Sai) into a
  beam weapon means adding a component to its entity, as Bans's True Lasgun Beam Overhaul does by moving the weapon's entity
  map membership list. HD2Runtime does not: it is the entity map change the 0.30.3 stray-row diagnostic reports, other
  players' games would not have the component, and the saved state would differ.
- **Names are leads.** `beam.pulse_beams` and `beam.pulse_seconds` are named from the Trident's values and a
  third-party mod's labels; the live tests decide them (`proof/BeamBlastProof`): a Trident-like Scythe; the Trident
  with +112 1.0 and with +108 1 and 6; a Sickle with no wind-up and with a 2 s wind-up.

**Beam swaps** (0.30.4, offline only; [attack outputs](attack-outputs.md) "Beam swaps"): the LAS-5 Scythe, LAS-7 Dagger
and LAS-13 Trident fire any catalogued beam output through `weapon:beam_source()` and `hd2.fields.attack.beam`
(`allow_unverified_reference` and `allow_unverified_effect`). The Dagger and Trident write their own BeamWeapon +0; the
Scythe's default muzzle (Laser. Standard Prism) patches that member when the weapon is built, so its swap writes the
muzzle's delta row (`allow_shared`: the AX/LAS-5 Rover drone gun defaults to the same muzzle). A Trident-like Scythe
with the Trident's own beam is the transaction above plus this swap:

```lua
local source=hd2.weapon('LAS-5 Scythe'):beam_source()
hd2.ensure({patch={id='scythe-trident-beam',target=source.target,field=hd2.fields.attack.beam,expect=source.expect,
    value=hd2.attack_output('LAS-13 Trident'),allow_shared=true,allow_unverified_reference=true,
    allow_unverified_effect=true}})
```

Projectile weapons (the Sickles, the Sai, the Talon, every ballistic weapon) never fire a beam: they have no BeamWeapon
component and Runtime does not add one. They fire laser bolts through projectile swaps instead (the Talon, Sickle,
Sai and Quasar outputs; see "Lasers everywhere").

The LAS-5 Scythe resolves to `laser_rifle` since 0.30.2: an equipped snapshot holds that root, and the published
Scythe heat data (12.5 heat/s, cooling 12.8 - 8.5 - 6.4) matches it only (`laser_rifle_charge` is another weapon).
Its heat rates are writable. Its heat capacity and heatsinks stay read-only: its default Laser Heatsink overwrites
them every time the weapon is built, so a write there would never show.
