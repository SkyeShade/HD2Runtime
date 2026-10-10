# BreakthroughProof

Development proof for HD2Runtime 0.30.4. It tests two things (docs/vehicle-weapons.md "Spread" and "EXO-55
Breakthrough shield arm", research/docs/mounted-spread-shield-F5FEE03DCFDB.md):

- **Mounted spread:** `weapon.horizontal_spread` / `weapon.vertical_spread` (WeaponData +84/+88). The projectile shot
  reads it for every shot and every pellet.
- **The EXO-55 Breakthrough shield arm:** the left mount, a physical shield with no energy-shield component. It has
  an arm pool of 800 and a plate zone of 5000 health, armor 4.

Each test is one toggle in the mod's options page (MODS tab). Every value is copied when the Exosuit is created, so
**call in a new Exosuit after changing a toggle**. An Exosuit already on the ground keeps the old values. The two
flak toggles edit the same fields: turn x5 off before zero, or the second is refused and logged (CONFLICT).

| Toggle (default) | Change | Expected |
|---|---|---|
| Flak cannon spread x5 (on) | flak spread 200 -> 1000 mrad (both axes) | the 40 pellets of each shot spread about five times wider (a cone of about ±29 degrees); far fewer pellets hit a distant target |
| Flak cannon zero spread (off; x5 off first) | flak spread 200 -> 0 | the pellets fly in one tight line, like a slug |
| Shield plate 5x health (on) | plate zone health 5000 -> 25000 | the shield plate takes about five times the damage before it breaks |
| Shield plate armor 5 (off) | plate zone armor 4 -> 5 | armor-penetration-4 attacks (heavy machine guns, Hulk cannons...) stop damaging the plate, or do far less |
| Shield arm 5x health (off) | arm pool 800 -> 4000 | the shield arm (not the plate) survives about five times the damage |
| Patriot minigun zero spread (off) | EXO-45 minigun spread 50 -> 0 | the minigun's bullets stop spreading: a control test on another mount |

For each toggle, report:
- what you saw, compared with a vanilla Exosuit;
- the log line (APPLIED, or the error);
- anything that looked broken: the shield vanishing, the Exosuit not spawning, or a crash.

For the plate, a quick test is to shoot it yourself with a friendly support weapon from outside the Exosuit, or to
let enemies shoot it, and count how long it lasts.

Solo first. Then, if you can, with a friend running the same mod. The values belong to the machine that creates the
Exosuit and fires the shot, so report who called it in and who drove it.
