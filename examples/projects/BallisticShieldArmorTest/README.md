# BallisticShieldArmorTest

Live test for the SH-20 Ballistic Shield's plate armor (`docs/backpack-authoring.md`, `research/ballistic-shield-F5FEE03DCFDB.json`).

A report set the shield's `entity.armor` to 5 and the AP 4 HMG still damaged it. That field is the default-zone
armor, which the game uses only as a fallback. Every hit on the plate resolves to damage zone 0 "shield", whose armor
stayed 4, and AP 4 against armor 4 is the equal case (65 % damage). This mod sets **zone 0 armor 4 → 5**
(`hd2.backpack('SH-20 Ballistic Shield Backpack'):damage_zone('shield')`, `zone.armor`).

## How to test

1. Wait for `ballistic-shield-plate-armor` `APPLIED` in `HD2Runtime.log`.
2. Call in a **new** SH-20 (armor is copied into a shield when it spawns; one already in the world keeps 4).
3. Drop it, or have a teammate hold it, and shoot the plate head-on with weapons that do not explode. Count hits.

| Shield | Weapon (AP) | Expected per hit | Hits to break |
| --- | --- | --- | --- |
| New shield (armor 5) | MG-206 HMG or APW-1 AMR (AP 4) | 0 | never |
| New shield (armor 5) | RS-422 Railgun, unsafe or safe mode (AP 5) | about 219 | about 5 |
| A shield called in **before** the write | MG-206 HMG (AP 4) | about 45 | about 23 |
| Vanilla control (mod off) | MG-206 HMG (AP 4) | about 45 | about 23 |

Report which rows matched. The AP 4 row is the decisive one: no damage at all proves zone 0 is the plate's active
armor. The pre-write shield row shows the spawn-time copy.
