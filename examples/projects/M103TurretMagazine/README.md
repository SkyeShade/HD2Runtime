# M103TurretMagazine

Recreates the magazine part of the Better M-103 FRV Turret 1.31 reference mod. The M-103 roof gun's own
`WeaponMagazineComponentData` goes from 120 to 600 rounds. It is found with
`hd2.vehicle('M-103 Supply FRV'):mount('gun'):weapon()`.

The reference mod also sets the gun's `ProjectileWeaponComponent` damage/armor-penetration addends. The
pinned type library names +128 `damage_addends` and +136 `ap_addends`, but the mod's author reports the
opposite from in-game testing, so those fields stay read-only until one in-game test settles it.
This was built only, not deployed or launched.
