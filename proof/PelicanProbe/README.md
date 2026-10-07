# PelicanProbe 0.1.0 (development only): the game's own Pelican, observed and held

The first step toward Pelican Close Air Support. It answers, live, what the offline research
(`research/docs/pelican-cas-F5FEE03DCFDB.md`) predicts from the game's code:

- how the game's transport Pelican flies, hovers, releases, departs and is removed;
- whether its cargo already exists when the Runtime first sees it (the research says yes: no per-call cargo window);
- whether **one per-instance write** keeps it over its drop point for 60 s, after which it leaves on its own.

It also logs, aboard the ship, the **read-only carrier allocation** for the two custom stratagems:

    CUSTOM CARRIER: Gas Barrage = <X>, Pelican CAS = <Y>; distinct = true

It converts nothing, presents nothing and summons no Pelican. The Pelican it observes is the one **your own vehicle or
exosuit call-in** sends.

## What it writes

Only the hold, once per Pelican (on by default; **Ctrl+F8** turns it off and on). When a Pelican is seen released over
its drop point, ONE guarded 8-byte write moves **that Pelican's own release time** (its Behavior record, P+0x178), so
it departs 60 s after its release instead of 0.6 s. Then the game takes over: it departs, flies out and removes itself.

The hold is refused, with nothing written, unless:
- you are in a mission, as host, solo;
- the entity is still a transport Pelican, with the same Behavior record and behaviour id;
- it is released (stage 6 and released, or stage 7);
- its release time is exactly as observed, and its native departure has not been reached;
- the hold is between 0 and 120 s and extends the native time.

Never written: the Pelican's or any vehicle's settings, StratagemInfo, the cargo, other Pelicans, save data, the account.

## Which build is running

- The first line is `PelicanProbe 0.1.0 PELICAN PROBE + HOLD`.
- In the mission, `pins: the Transport, Behavior and transform components ... researched code` and
  `PELICAN WATCH: running; hold 60 s after each release` follow.

## Live test

**Setup:**
- install this hand-off's HD2Runtime runtime ZIP and `PelicanProbe-0.1.0.zip` only (no other proof);
- disable Stratagem MultiSelect and Vanilla Plus Megapack;
- bring **one vehicle or exosuit you own** (any M-102/103/104 FRV, TD-110, TD-220, EXO-45/49/51/55);
- play **solo**, as host.

**SHIP**
1. Leave the loadout screen. Expect the `CUSTOM CARRIER: Gas Barrage = ..., Pelican CAS = ...; distinct = true` line
   and one `CUSTOM CARRIER: <name> -> ...` line per custom stratagem (or a `REFUSED` line with its reason).

**MISSION**
2. Call your vehicle once. Watch the Pelican; do not get in the vehicle until the Pelican has gone.
3. Expect, in order:
   - `PELICAN SEEN`: its cargo (the vehicle) and whether it was `ALREADY SPAWNED`, and the beacon it came from;
   - `PELICAN STAGE` lines (approach, hover);
   - `PELICAN RELEASED`: how long it hovered before releasing, and its height above the beacon;
   - `PELICAN HELD: ... departs 60.0 s after its release (native 0.6 s); verified true`;
   - the Pelican **stays over the drop point for about a minute**;
   - `PELICAN DEPARTING` about 60 s after the release, then `PELICAN GONE` and `PELICAN SUMMARY` about 14 s later.
4. Optional control: press **Ctrl+F8** (hold OFF) and call a second vehicle: it should leave right after the release.
5. **Send** every line starting with `CUSTOM CARRIER` or `PELICAN`, plus one `Ctrl+F11` line while the Pelican hovers.

**Also report:** whether the Pelican visibly hovered about 60 s, whether it left and disappeared normally, and anything
odd (the vehicle, the Pelican's engines or animation, the drop).
