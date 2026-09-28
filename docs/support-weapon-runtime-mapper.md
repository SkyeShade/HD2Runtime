# Support weapon runtime mapper

The support mapper reuses HD2Runtime's bounded entity/component/settings scan and the same
snapshot reader used by the player-weapon mapper. It adds support-catalog normalization and a
graph report; it does not add another memory scanner.

Run it offline with:

```powershell
py -B hd2.py snapshot scan-support-weapons <build>.hd2snap wiki_support_weapons.json
```

The command writes `SupportWeaponRuntimeMap.json`,
`SupportWeaponRuntimeMap.identity-candidates.json`, `support_weapon_identity_summary.json`, and
`SupportWeaponRuntimeMap.log`. The committed current-build result is
[`research/support-weapon-runtime-F5FEE03DCFDB.json`](../research/support-weapon-runtime-F5FEE03DCFDB.json).

The report preserves every imported attack and its parent/child relationships. Runtime branches
are linked only through schema-labelled native references and matching typed records. The mapper
now follows `ProjectileInfo -> ExplosionSettings -> DamageInfo`,
`DamageInfo -> StatusEffectSettings`, `ExplosiveComponentData -> ExplosionSettings`, and
`HellpodRackComponentData -> spawned attack entity`. Missing branches remain explicit.

Current snapshot results are 35 resolved identities out of 35: 27 unique roots and eight
duplicate-resource groups. Eighteen explosion branches and eight status branches are structurally
linked. C4 resolves to its placed explosive entity. Solo Silo preserves a separate stratagem
payload/silo root and missile-damage owner. CQC-72 remains a two-resource duplicate because both
MeleeWeapon, WeaponData, customization, and damage records are byte-identical.

ARC-3's `ArcWeaponComponentData` rate is the native `-1` charge-controlled sentinel. Its owned
`WeaponChargeComponentData` supplies 0.7/1.4 second charge timing and 1.0/1.1/1.2 charge levels;
the catalog's 60 RPM remains a diagnostic display value. GL-28's schema-labelled rate selector is
`160/240/320`; 240 is the default element and the catalog value is the high element. Its identity
is supported by the linked projectile and explosion graph rather than by suppressing this
diagnostic disagreement.

Three of the nine catalogued backpack-dependent weapons own a `WeaponLinkedAmmoComponentData`
record in the mapped root set. Since 0.26.0 the link is resolved: the record draws from the Backpack
inventory slot through a tag that only the weapon's own backpack carries, and that backpack's
`DepositComponent` is the ammunition store (see [Backpack ammunition](backpack-ammo.md)).
Standalone backblast ownership and charge native-consumer semantics also remain open.

The future semantic direction is `hd2.support_weapon(name)` with branch-aware access. It is not a
public runtime API yet. Snapshot evidence does not prove enough live ownership for guarded support
weapon writes, and duplicate identities have no canonical resource. All output remains read-only:
`writes=0`, `protectionChanges=0`, and `fixtureFallback=disabled`.
