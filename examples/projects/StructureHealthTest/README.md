# StructureHealthTest

Live test: Automaton fabricator (native class `spawner_factory_conscript_base`) main health 1500 -> 150.

**Result: inconclusive (2026-09-29).** The write applied cleanly, but the fabricators tested seemed to need about the
usual number of Railgun shots. Only one of the five fabricator variants is edited and the variant cannot be
identified in game, so this is not a failure. Structure health stays offline-proven and now requires
`allow_unverified_effect`.

A possible explanation, not established: the fabricator's fatal `insides` zone has its own 400-health pool and forwards
0% of its damage to main health, so a fabricator destroyed through that zone needs the same shots either way.

Stronger tests: `FabricatorHealthAllVariants` (all five variants, shoot the housing) and `GazerHealthTest` (a
named, visually unmistakable structure).
