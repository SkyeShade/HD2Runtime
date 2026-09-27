# Player weapon authoring

HD2Runtime 0.13.0 exposes reviewed semantic writes for the complete 80-weapon player catalog. The generated [capability catalog](../sdk/PlayerWeaponAuthoringCapabilities.json) is the canonical GUI input. It records current defaults, backing component or settings record, scalar storage, provenance, editability, derived fields, and shared write scope without publishing runtime addresses.

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

Displayed recoil and rounds-feed total capacity are derived read-only values. Edit the four drift/climb recoil inputs or the two feed capacities separately. Projectile and DamageInfo identifiers remain read-only because reference replacement is outside this release. P-2 Peacemaker and P-19 Redeemer expose their weapon-level fields; their customization-supplied projectile and damage paths remain unavailable and fail closed.

The seven ambiguous identities are CQC-42 Machete, CQC-73 Entrenchment Tool, GP-31 Grenade Pistol, LAS-5 Scythe, LAS-7 Dagger, P-72 Crisper, and SMG-37 Defender. Their catalog entries remain visible to tools, but ordinary `hd2.weapon(name)` writes are blocked until runtime ownership can select one resource without guessing.
