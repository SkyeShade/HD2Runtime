# StructureHealthTest

Live test: Automaton fabricator (native class `spawner_factory_conscript_base`) main health 1500 -> 150.

What to verify: on an Automaton mission, compare the anti-tank hits needed to destroy a fabricator housing (armor 5)
with and without the mod. Destroying it by grenade in the vent is not a useful test. The other four fabricator
classes (assault, airborne, phalanx, standard) stay vanilla, so a fabricator that still needs the vanilla damage is
one of those variants, not a failure.

The class name is native: its anatomy matches both the Automaton Fabricator and Warp Gateway wiki pages, so no wiki
name is attached. Built only.
