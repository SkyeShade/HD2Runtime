# FabricatorHealthAllVariants

Live test: every Automaton fabricator variant (5 native classes), main health 1500 -> 150.

Why: `StructureHealthTest` edited one variant of five and was inconclusive. With all five changed, every fabricator
on the map carries the edit.

What to verify: on an Automaton mission, shoot a fabricator's armored housing, away from the vent opening, with a
weapon that penetrates armor 5 (for example the Railgun) and count the hits. Compare with a mission without the mod.
- With the mod it should fall to a small fraction of the vanilla number of housing hits.
- Destroying it through the vent is not a test: the vent reaches the fatal `insides` zone, which has its own
  400-health pool and forwards none of its damage to main health, so it is unaffected by this edit.
- If housing hits still take the vanilla count with every fabricator edited, main health does not govern the housing;
  that is a useful result too.

Structure health is offline-proven only, so the operations pass `allow_unverified_effect`.
