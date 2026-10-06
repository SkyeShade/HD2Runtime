# PodProbe 0.1.0 (development only): read-only hellpod probe

**Writes nothing.** It observes the first per-call object that selects what a hellpod delivers: the pod's
**TransportComponent** element (`[game+0x3326518]`, 0x40 bytes each), from the offline research in
`docs/research/carrier-families-F5FEE03DCFDB.md`:

| Member | Meaning |
| --- | --- |
| element +0x0 | the content resource hash (a weapon rack, a sentry, ...). It is copied from the beacon's dispatcher record when the pod is created, and read once by the host when the content spawns |
| element +0x8 | the spawned content entity (not yet spawned until then) |
| element +0xC | the spawn timer: armed at landing (0.5 s); the content spawns when it crosses zero |
| replicated block +0 / +8 / +0xC / +0x10 | the content hash, kind, type, and the network id of the beacon that spawned the pod |

For every pod it logs:
- its content, named from the catalogue's payload lists;
- its type;
- the beacon that spawned it (matched by network id);
- when it lands and when its content spawns.

That gives the per-pod window in which a later, separate proof could change the content per call.

## Live test

1. Install `HD2Runtime-0.28.0-runtime.zip` (this build) and `PodProbe-0.1.0.zip`, **with no other beacon proof
   installed**. The first proof line is `PodProbe 0.1.0 READ-ONLY HELLPOD PROBE`; `pins: … (15 pins)` must follow in the
   mission.
2. Start a **solo** mission. One at a time, each to its `POD SUMMARY` line, throw:
   - **AC-8 Autocannon**;
   - a **backpack**;
   - **A/G-16 Gatling Sentry**;
   - a **minefield**;
   - an **emplacement**.
3. **Send** every line starting with `POD`, plus one `Ctrl+F11` line while a pod is falling.
