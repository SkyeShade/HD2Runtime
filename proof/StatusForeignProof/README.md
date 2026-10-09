# StatusForeignProof

Development proof for HD2Runtime 0.30.4 (built against the 0.30.4 development runtime):

1. **Status effect stats** (`hd2.status_effect`). At load it applies values strongly different from vanilla:
   - fire lasts **10 s** (vanilla 3) and deals **300** per tick (vanilla 100);
   - gas deals **100** per tick (vanilla 25). Gas, gas_2 and gloom share this row, so all three change.

   Report whether burning enemies burn visibly longer and die faster, and whether gas kills visibly faster. The P-35
   Re-Educator, a Gas Grenade or the Orbital Gas Strike work for gas; a Flame Sentry, the Torcher or a Breaker
   Incendiary work for fire.
2. **Values changed by mods outside HD2Runtime** (`hd2.inspect`, `hd2.diagnostics.foreign_values`). Press Ctrl+F9: the
   log lists the state and owner of a set of common values (vanilla / runtime / foreign). If you run a data-file mod
   (a patched archive) that changes one of them, it should show `foreign owner=unknown`, and its `FOREIGN VALUE` line
   should be in the log once.

Turn it off by removing it; nothing it applies outlives the game session.
