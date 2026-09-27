# Player weapon authoring

HD2Runtime 0.15.0 exposes reviewed semantic writes for the complete 80-weapon player catalog. This
patch release fixes duplicate ammo semantic aliases while preserving the 0.14.0 authoring API.
The generated [capability catalog](../sdk/PlayerWeaponAuthoringCapabilities.json) and [ammo capability catalog](../sdk/PlayerWeaponAmmoCapabilities.json) are the canonical GUI inputs. They record current defaults, backing component or settings record, scalar storage, provenance, editability, derived fields, and shared write scope without publishing runtime addresses.

`hd2.weapon(name)` is the identity root. `patch`, `transaction`, and `ensure` freshly resolve that identity at application time, check the game fingerprints and ownership chain, compare the declared expected value, and pass an exact-width change to the existing guarded transaction engine. A shared settings field is rejected unless the declaration includes `allow_shared=true`. A weapon with multiple indistinguishable runtime resources is rejected for ordinary writes.

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
    changes={
        {field=hd2.fields.projectile.drag, expect=1.2, value=0.3},
        {field=hd2.fields.projectile.gravity, expect=1, value=0.25},
    },
})
```

Damage lanes remain independent exact-width fields. This example changes the Verdict's standard damage and direct AP lane while leaving the other AP lanes untouched:

```lua
hd2.transaction({
    id='verdict-damage-example',
    target=hd2.weapon('P-113 Verdict'),
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

The current build's customization catalog provides 52 magazine, heatsink, and canister option identities with names and AddPaths. Nineteen player weapons select a default magazine option. Their effective values are visible in the ammo capability catalog, but their override records and per-weapon allowed-option graph are not sufficiently owned for guarded writes. `magazine.*` remains read-only for those weapons. Selecting a different preset, or editing `magazine.option[n]`, therefore fails closed in this release.

`WeaponMagazineComponentData` stores capacity at offset 136, starting magazines at 140, supply refill at 144, and maximum spare magazines at 148. `WeaponRoundsComponentData` stores two feed capacities at 72/76, spare rounds at 80, supply refill at 84, and starting rounds at 88. These offsets are internal metadata; mod declarations use semantic field constants.

Displayed recoil and rounds-feed total capacity are derived read-only values. Edit the four drift/climb recoil inputs or the two feed capacities separately. Projectile and DamageInfo identifiers remain read-only because reference replacement is outside this release. P-2 Peacemaker and P-19 Redeemer expose their weapon-level fields; their customization-supplied projectile, damage, and effective magazine override paths remain unavailable and fail closed.

The seven ambiguous identities are CQC-42 Machete, CQC-73 Entrenchment Tool, GP-31 Grenade Pistol, LAS-5 Scythe, LAS-7 Dagger, P-72 Crisper, and SMG-37 Defender. Their catalog entries remain visible to tools, but ordinary `hd2.weapon(name)` writes are blocked until runtime ownership can select one resource without guessing.
