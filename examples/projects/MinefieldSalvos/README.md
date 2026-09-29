# MinefieldSalvos

Live test: MD-6 Anti-Personnel Minefield salvos 6 -> 2 (48 mines -> 16).

**Result: live-proven (2026-09-29).** The launcher fired two salvos and stopped. `minefield.salvos` no longer needs
`allow_unverified_effect` on any of the four minefields; `minefield.mines_per_salvo` was not tested and still does.
Counts stay reduce-only.

Observed behaviour: the mines landed in only one portion (about a quadrant) of the launcher's normal 360-degree
pattern, not spread thinly around the whole circle. Successive salvos cover different rotational sectors, so
reducing the salvo count truncates the angular deployment sequence rather than reducing density evenly.

What to verify: call in the MD-6 on open, flat ground and watch where the mines land.
