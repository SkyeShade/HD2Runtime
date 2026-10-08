# WeaponRootsTest

Live test for the seven weapons HD2Runtime 0.30.2 unblocks. They were refused as DUPLICATE identities; each now
resolves to its proven root (`research/weapon-roots-F5FEE03DCFDB.json`). Uses the MODS tab (page **Weapon Roots
Test**). Every toggle is on by default.

| Weapon | Change | What to look for |
|---|---|---|
| LAS-7 Dagger | heat capacity 100 -> 400 | about 4x longer firing before it overheats |
| LAS-5 Scythe | heat per second 12.5 -> 3 | about 4x longer firing before it overheats |
| GP-31 Grenade Pistol | starting rounds 4 -> 12, spare 6 -> 20 | the ammo counter |
| P-72 Crisper | magazine capacity 50 -> 150 | the fuel counter |
| SMG-37 Defender | fire rate 520 -> 1100 rpm | twice the fire rate |
| CQC-42 Machete | damage 300 -> 1500 | one hit kills most small enemies |
| CQC-73 Entrenchment Tool | damage 165 -> 1500 | one hit kills most small enemies |

The game copies these values into a weapon when it builds it. Equip the weapons, then start a mission, or re-equip
or redeploy after the mod applied. The log line `APPLIED` for each `weapon-roots-*` operation says the write was
verified; only what you see in game shows its effect.
