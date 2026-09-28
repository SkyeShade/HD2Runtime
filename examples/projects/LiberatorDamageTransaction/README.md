# LiberatorDamageTransaction

The reference beginner example for weapon damage. It raises the AR-23 Liberator's damage and armor penetration:

| Field | Constant | Baseline | Value |
| --- | --- | --- | --- |
| Standard damage | `hd2.fields.damage.player_standard_damage` | 90 | 120 |
| Durable damage | `hd2.fields.damage.player_durable_damage` | 22 | 35 |
| AP direct | `hd2.fields.damage.ap_direct` | 2 | 3 |
| AP slight angle | `hd2.fields.damage.ap_slight` | 2 | 3 |
| AP large angle | `hd2.fields.damage.ap_large` | 2 | 3 |
| AP extreme angle | `hd2.fields.damage.ap_extreme` | 0 | 2 |

What it teaches:

- **Ownership.** Damage is owned by the projectile, reached as
  `hd2.weapon('AR-23 Liberator'):attack('primary'):projectile()`. The weapon root owns weapon-local values
  such as fire rate.
- **Armor penetration** is four fields, one per impact angle. There is no single "AP" field for typed weapons;
  the legacy `hd2.fields.damage.armor_penetration` belongs to the original fixed JAR-5 patch only.
- **Baselines differ between weapons.** The AR-23C Liberator Concussive, for example, is 75 / 35 with AP 2 / 2 / 2 / 2.
  Read `expect` from `sdk/PlayerWeaponAuthoringCapabilities.json` (`currentDefault`), ModBuilder, or
  `projectile:describe()`; never copy it from another weapon.
- **One transaction.** All six fields are in one DamageInfo record, so they belong in one `transaction`. Use a
  `plan` only for operations on different objects.
- **Shared scope.** That DamageInfo record is also used by the AR-23A Liberator Carbine and the StA-52 Assault
  Rifle (`sharedWithWeapons`), so `allow_shared=true` is required and those weapons change too.

Requires HD2Runtime 0.23.2+. Built only; not deployed automatically.
