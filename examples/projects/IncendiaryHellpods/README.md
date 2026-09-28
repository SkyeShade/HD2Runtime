# IncendiaryHellpods

Enlarges the explosion Firebomb Hellpods adds to every hellpod impact: radii from 2/4 m to 3/6 m, standard damage from 200 to 300, and burn status strength from 20 to 40.

The explosion is selected by a literal in game code's hellpod-impact booster branch, and every write re-proves that branch's exact instructions. The explosion row and its damage row are separate native objects, so each is its own plan operation. Requires allow_shared, because other consumers of these settings rows cannot be fully excluded, and allow_unverified_effect, because no booster edit is gameplay-proven. Built only; never deployed or launched.
