# BoosterTuning

Tunes four boosters through the typed booster API. Vitality Enhancement's damage-taken multiplier goes from 0.9 to 0.75, Expert Extraction Pilot's extraction call-in multiplier from 0.7 to 0.5, and Sample Scanner's double-sample chance from 0.15 to 0.3. Surplus EAT Allocation's granted EAT stratagem goes from 2 uses to 4.

The first three are the boosters' own rows in game.dll's native Booster definition table. Every write re-proves the Booster enum-name table, the table row identities, and the exact gate and consumer instructions. The granted stratagem is reached through the table's granted-stratagem member. Its use count is read when the stratagem is granted, so it applies from the next mission.

Requires allow_unverified_effect because no booster edit is gameplay-proven. Built only; never deployed or launched.
