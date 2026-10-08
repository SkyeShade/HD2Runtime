# PurifierIncendiaryCharge

Live test: PLAS-101 Purifier **charged** shots set what their blast hits on fire (Fire, strength 2, the AR-2 Coyote
value), like the first game's incendiary upgrade. The blast's size and damage are unchanged, and nothing lingers on the
ground: only what the blast hits catches fire. Uncharged shots are unchanged (they fire their own projectile and
explosion).

The status goes into the first empty status slot of the charged shot's own explosion
(`weapon/plas101_purifier/impact`, damage row 313, used by no other weapon). Writes need `allow_unverified_effect`:
only the charged levels fire this row, and a status on an explosion is not live-proven yet.

What to verify (solo or host):
- fully charge a shot into a group of Scavengers or Troopers: the enemies in the blast catch fire;
- uncharged shots: no fire;
- the log line `plan purifier-incendiary-charge APPLIED`.
