# ExplosionCatalogueTest

Opt-in live test for the explosion catalogue (docs/explosions.md). Requires HD2Runtime 0.30.0-dev. Build with
`python build.py`; do not deploy automatically. Nothing here is live-tested yet: every write carries the
acknowledgements the catalogue asks for. The log starts with `EXPLOSION CATALOGUE 0.1.0 BUILD`.

| Part | What it does | Look for |
| --- | --- | --- |
| Edit | `hd2.explosion('stratagem/orbital_120mm_he_barrage/shell_impact')`: inner radius 3.3 -> 5 m, outer radius 10 -> 14 m | each 120mm shell's blast reaches farther |
| Payload | the R-36 Eruptor's impact explosion becomes `weapon/plas15_loyalist/impact` (mission effects package) | an Eruptor shell bursts with the Loyalist's small plasma blast and no shrapnel |
| Spawn | host only: an enemy you kill releases the Orbital Gas Strike's shell explosion where it died | a gas cloud at each kill (rate-limited to 6 at once, 1 a second) |

Report: whether each part behaved as described, and anything that looked or sounded wrong (a missing effect, no
sound).
