# EnemyHealthTest

Live test: Charger main health 2400 -> 240.

What to verify: fight Chargers spawned after the mod loads, and count the hits one weapon needs to kill one through
the body (not the head). It should take about a tenth of what a Charger Behemoth needs; the Behemoth is a separate
class (3000 health) and stays vanilla, so it is the control. Chargers already on the map keep their health.

Main health (HealthComponent +0) is gameplay-proven on vehicles and the Shield Relay. The Charger identity is proven
by an exact 17-zone anatomy match. This test confirms the effect on enemies. Built only.
