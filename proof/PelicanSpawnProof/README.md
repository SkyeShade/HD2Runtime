# PelicanSpawnProof 0.2.0 (development only): the hover anchor, and what other players see

The live test of `hd2.pelican.spawn` (docs/event-scripting.md, "Pelicans"). The spawn uses the public API only; the
observation of every Pelican uses the Runtime's read-only Pelican readers (internal, never a write).

**0.1.0 live result:** the empty spawn, the 60 s hold and the departure worked; the Pelican hovered about 252 m from the
requested point. The cause: the game takes a Pelican's hover point from its **anchor**, filled at creation from the
spawn context, and 0.1.0 passed none, so the anchor was the world origin (research/docs/pelican-cas-F5FEE03DCFDB.md,
section 5b).

**What changed in 0.2.0:**
1. The Runtime now passes its own copy of the game's neutral spawn context with only the anchor set (as a beacon sets
   it for a vehicle drop). The Pelican is created 250 m back along your heading and 80 m up, flies in and hovers over
   the requested point (25 m east of you).
2. The host may have other players in the mission (the API is host only).
3. Every machine with this proof logs every transport Pelican it has (`SEEN PELICAN (HOST|CLIENT)`): entity, network
   id, position, stage, release, anchor, removal.

**Never done:** no patch, hook or detour; no game code overwritten; no shared Pelican or vehicle definition, no
StratagemInfo, no save or account data written.

## Which build is running

- The first line is `PelicanSpawnProof 0.2.0 HOVER-ANCHOR + MULTIPLAYER BUILD`.
- Ctrl+F11 prints `[0.2.0 HOVER-ANCHOR + MULTIPLAYER BUILD]`, HOST or CLIENT.

## Live test 1: solo (the hover anchor)

**Setup:** this hand-off's HD2Runtime runtime ZIP and `PelicanSpawnProof-0.2.0.zip` (PelicanCasProof may stay
installed); the Pelican Cover Flag mod disabled; solo, as host.

1. Land, stand somewhere open, press **Ctrl+F8**.
2. Expect `Ctrl+F8 [0.2.0 ...]: requested to hover at (...) (25 m east of you) ... created at (...)`,
   `PELICAN SPAWN REQUESTED ... anchor (...)`, `PELICAN SPAWN CREATED ... anchor (...) read back ... verified true`,
   `PELICAN EXISTS`, `SEEN PELICAN (HOST)`, `PELICAN STAGE` lines, then `PELICAN HOVERING: ... N m from the requested
   position horizontally` (a few metres, not ~250), `PELICAN HELD: ... 60.0 s`, `PELICAN STATE` every 5 s,
   `PELICAN DEPARTING`, `PELICAN GONE`, `PELICAN SUMMARY`.
3. **Watch:** it flies in from behind you and hovers about 25 m east of where you stood; walk away: it stays.

## Live test 2: multiplayer (what clients see)

**Setup:** two machines, both with this hand-off's runtime ZIP and `PelicanSpawnProof-0.2.0.zip`; one hosts.

1. In the mission, the **host** presses Ctrl+F8 (a client's Ctrl+F8 only says it is a client).
2. Both play on until `PELICAN GONE` on the host.
3. **Watch on the client:** does the Pelican appear, where, does it hover over the same point, and does it stay the
   60 s or leave early?

**Send** from every machine every line starting with `Ctrl+F8`, `Ctrl+F11`, `PELICAN` and `SEEN PELICAN`, and say what
each player saw.
