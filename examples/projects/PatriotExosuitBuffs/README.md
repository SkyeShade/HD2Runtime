# PatriotExosuitBuffs

Recreates the EXO-45 Patriot Buff 1.12.0 reference mod from semantic targets:

- **Hull:** main health goes from 1800 to 8000, and every hull damage zone's health goes to 8000.
  Zones with armor below 4 go to 4.
- **Missile arm (`left_gun`):** the magazine goes from 14 to 30. The arm's health and its single hit zone's
  health go from 800 to 8000, and both armor values go from 3 to 10. The missile's own `DamageInfo` changes: 1250/1250 -> 2000/2000,
  AP large 5 -> 6, AP extreme 0 -> 3, stagger 40 -> 50.
- **HMG arm (`right_gun`):** the magazine goes from 1350 to 2000, the fire rate from 1200 to 600 rpm, and the
  arm's health and armor match the missile arm. The HMG round's `DamageInfo` changes: 90/23 -> 500/150, and
  AP 3/3/3/1 -> 5/5/5/5.
- **Call-in:** the cooldown goes from 420 to 250 s.

The HMG round `DamageInfo` is shared with other machine guns, including the MG-43 and sentries. That is why
this recreation needs `allow_shared`, and why the reference mod's change also affects those weapons. The
missile `DamageInfo` is used only by the Patriot missile. The reference mod also raises the separate
"max armor" values (`HealthComponentData` +288 and each zone's +224) from 0. Their meaning is not
established, so they are not exposed and are left unchanged; that is the only part of the reference mod
this recreation omits. This was built only, not deployed or launched.
