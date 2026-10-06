# ExtractionPelicanProbe 0.1.0 (development only, read-only): the extraction Pelican, observed

**Nothing is written, spawned or called.** The probe watches the game's own extraction Pelican during a normal
extraction, to check the offline research (docs/research/pelican-cas-F5FEE03DCFDB.md, "Pelican variants"):

- the extraction Pelican is the entity `shuttle_gunship`, delivered by the mission stratagem `Extract` (type 148) the way
  a vehicle's Pelican is delivered from its beacon;
- its flight is behaviour **202**, which it gets from its **entity type**, not from the mission;
- behaviour 202's holding stage 5 circles its anchor (30 m, a code constant, 30 m up). Every update it asks whether to
  abort (no helldiver left) and whether to **land** (stage 6): a player within 50 m of its landing point plus
  mission-wide state;
- its chin turret is a separate entity (`shuttle_gunship_turret_hmg`, behaviour 645).

## Which build is running

The first line is `ExtractionPelicanProbe 0.1.0 EXTRACTION PELICAN PROBE (read-only)`; Ctrl+Shift+F12 prints the
status.

## Live test

**Setup:** this hand-off's HD2Runtime runtime ZIP and `ExtractionPelicanProbe-0.1.0.zip`; solo or with others.

1. Play a normal mission to its extraction and call the extraction as usual (the game's own extraction: the probe only
   reads).
2. Expect `EXTRACTION PELICAN SEEN ... type shuttle_gunship ... behaviour 202`, `EXTRACTION PELICAN STAGE` lines,
   `EXTRACTION PELICAN TURRET`, and while it circles before landing, `EXTRACTION PELICAN CIRCLE` every 2 s (its target
   against its anchor; players near its landing point).
3. Try once to stay **more than 50 m away** from the landing zone for a while when it arrives (does it keep circling?),
   then go in and extract normally.
4. Expect `EXTRACTION PELICAN GONE` and `EXTRACTION PELICAN SUMMARY`.

**Send** every line starting with `ExtractionPelicanProbe`, `EXTRACTION PELICAN` and `Ctrl+Shift+F12`, and say what
you saw: how high and how wide it circled, when it landed, whether its gun fired.
