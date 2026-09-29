# WeaponPresentationTest

Live test: the AR-23C Liberator Concussive's **gameplay** armor penetration and its **displayed** label, set
independently. Uses the MODS tab (Mod Options Menu, page **Concussive Penetration**). Needs this HD2Runtime test build
(not the published 0.27.0).

Gameplay penetration is the AP of the Concussive bullets (AP 2 = light armor). The armory label is presentation: one
of the trait tags of its loadout entry, the string LIGHT ARMOR PENETRATING. The game never derives one from the other.

| Option | Choices | Default |
| --- | --- | --- |
| Gameplay penetration | Vanilla (AP 2, light), Medium (AP 3) | **Medium** |
| Displayed label | Vanilla (Light), Light, Medium, Heavy | **Heavy** |

The defaults are deliberately mismatched: the menu should say HEAVY while the gun penetrates medium armor.

## How to test

1. Check the log for `transaction concussive-gameplay-ap APPLIED` (four `damage.ap_*` 2 -> 3) and
   `patch concussive-displayed-ap APPLIED` (`presentation.armor_penetration light -> heavy`).
2. Open the armory (or the loadout screen) and select the Concussive: the trait should read **HEAVY ARMOR
   PENETRATING**. If it still says LIGHT, close the menu, reopen it and check again; if it only updates after a game
   restart, report that (menus may cache).
3. In a mission, shoot medium armor (for example a Devastator torso): with gameplay Medium the
   bullets should penetrate.
4. Set Displayed label to Medium, APPLY, reopen the menu: MEDIUM ARMOR PENETRATING, and the gameplay unchanged.
5. Set Gameplay to Vanilla, APPLY: medium armor should now deflect the bullets, while the label stays as set.

Report the label shown after each APPLY (and whether reopening the menu was needed) and the penetration you saw. The
label storage and the armory reader are proven natively (`docs/weapon-presentation.md`); this is their first live
test (`allow_unverified_effect`).
