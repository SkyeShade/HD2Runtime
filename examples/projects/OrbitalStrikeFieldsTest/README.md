# OrbitalStrikeFieldsTest 0.1.0

Live test for the orbital bombardment pattern fields and the call-in time (`docs/stratagem-authoring.md`, "Orbital
bombardment pattern" and "Call-in time"). Requires HD2Runtime 0.30.0-dev+ / API 1 and Bingus Shared Loader v15+.
Mod Options Menu is optional: without it every option keeps its default.

Every write needs `allow_unverified_effect`: the fields are code-proven offline
(`validation/orbital-fields-snapshot.json`), not yet in game. They are type-record writes: every call of the stratagem
on this machine uses them. Play as the host, solo first; with several players every machine must run this mod.

## Options (MODS page "Orbital Strike Fields Test")

| Option | Default | Change |
|---|---|---|
| EMS Strike: barrage | on | Orbital EMS Strike: 1 salvo of 1 shell -> 5 salvos of 3 shells, 1.5 s between salvos, scatter 1 -> 20 |
| Napalm Barrage: one shell | on | Orbital Napalm Barrage: 5 salvos of 5 shells -> 1 salvo of 1 shell, scatter 25 -> 1 |
| 120mm: 1 s call-in | on | Orbital 120mm HE Barrage call-in 5 s -> 1 s |
| 380mm: 15 s call-in | on | Orbital 380mm HE Barrage call-in 6 s -> 15 s |
| Gatling: pause between bursts | off | Orbital Gatling Barrage: 0 s -> 1 s between its 4 salvos |
| 500kg: delayed dispatch | off | Eagle 500kg Bomb call-in 0 s -> 5 s |

## Checklist (report each line: pass / fail / not seen)

1. The log shows `ORBITAL STRIKE FIELDS 0.1.0 BUILD` and one `APPLIED` line per option that is on.
2. **EMS barrage.** Call the Orbital EMS Strike: 15 EMS bursts in 5 waves of 3 over about 10 s, spread over a wide area,
   instead of one burst on the beacon. Enemies are stunned by each.
3. **Precision napalm.** Call the Orbital Napalm Barrage: exactly one napalm shell, on the beacon, instead of 25.
4. **Fast 120mm.** Time from the beacon landing to the first shell: about 1 s plus the shell's flight, instead of 5 s.
   Ship upgrades shorten the call-in (the native 5 s showed 4 s), so expect less than the set value.
5. **Slow 380mm.** Time from the beacon landing to the first shell: about 15 s instead of 6 s.
6. **Off by default, then on (MODS page, APPLY, next call).** Gatling Barrage: clear 1 s pauses between its 4 bursts.
   Eagle 500kg Bomb: the jet arrives about 5 s later than usual.
7. **Restore.** Turn an option off and APPLY: the log shows the ensure restoring its baseline, and the next call is
   vanilla again.
8. A barrage already firing keeps its salvo and shell counts; a beacon already thrown keeps its call-in.

Save `HD2Runtime.log` after the session (the game overwrites it at launch).
