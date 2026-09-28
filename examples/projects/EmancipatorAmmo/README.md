# EmancipatorAmmo

Recreates the Emancipator Ammo v1 reference mod: `hd2.vehicle('EXO-49 Emancipator Exosuit'):weapon('left_gun')`
and `:weapon('right_gun')` each go from 100 to 150 rounds (`weapon.capacity`, `WeaponMagazineComponentData`
+136). The reference mod found the two records by trial. The runtime reaches them through the vehicle's
`MountComponentData` slots, and each slot's weapon owns its own record, so no `allow_shared` is needed.
This was built only, not deployed or launched.
