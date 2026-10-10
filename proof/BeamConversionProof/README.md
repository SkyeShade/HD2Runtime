# BeamConversionProof

Development proof for the HD2Runtime beam conversion (`docs/beam-conversion.md`). It uses only the public API:
`hd2.weapon(name):beam_conversion()` and `hd2.ensure`. Each test is one toggle on the mod's options page (MODS tab,
**Beam Conversion Proof**). Every toggle is off by default.

It supersedes `MultiBeamProof` and `LiberatorBeamProof`. Those experiment proofs still work on their own. The Runtime
refuses to mix the two: while an experiment's copy of the BeamWeapon table is live, every conversion is refused, and
the other way round.

## Rules for every test

1. **Solo only.** A conversion is applied only in a game with no other player. If someone joins, the Runtime restores
   every converted weapon that is not in use and shows a notice. A weapon of a converted type carried by another
   player crashes this game when it spawns, so leave the lobby, or quit if a converted weapon is still in use.
2. **The weapon must not exist while its toggle changes.** Equip *other* weapons, keep the armory closed, then turn the
   toggle on. Wait until the log shows `APPLIED`; the ensure retries every 5 to 20 s until the weapon is gone. Then
   equip the weapon and deploy. To turn a test off, unequip the weapon first.
3. **Restart the game after the session.** A weapon spawned while converted can leave a stale private copy behind.

## Tests

| Toggle | Change | Expected |
|---|---|---|
| Sickle: Trident pulses | conversion | The Sickle fires Trident pulses at 300 rpm (two beams per pulse) with the Trident's beam and sound. Each pulse adds 1.15 heat from the Sickle's own heat sink. It overheats and changes heat sinks as usual. The Sickle's wind-up does not apply. |
| Double-Edge Sickle: Trident pulses | conversion | Trident pulses. Its heat-stage projectiles no longer fire; its heat-stage self-damage may still apply. Report whether it still burns you. |
| Sai: Trident pulses | conversion | Trident pulses, one per trigger pull or held. Report which. Heat per pulse is the Sai's own. |
| Talon: Trident pulses at 600 rpm | conversion, `beam.fire_rate` 600 (the pulse is fitted to 0.067 s) | Talon pulses at about 550 to 600 rpm, clearly faster than the Trident. |
| Liberator: Trident pulses, damage x10, AP 4 | conversion; its own damage row 600 / 60, AP 4 | Each pulse hit deals 10 times the Trident's damage: medium enemies die in 1 to 2 pulses. AP 4 pierces armor the Trident cannot. The real Trident is unchanged; check it on the same enemies. One round per pulse from the Liberator's magazine. |
| Reprimand: Trident pulses, range 100 m | conversion; its own beam row length 200 -> 100 m | The Reprimand's beam stops at 100 m: it hits nothing past 100 m and its drawn beam ends there. |
| Trident: 600 rpm with a 0.05 s pulse | the real Trident: `beam.fire_rate` 300 -> 600, `beam.pulse_seconds` 0.15 -> 0.05 | The Trident fires about 550 to 600 pulses a minute. |
| Trident control: 600 rpm, 0.15 s pulse (capped) | `beam.fire_rate` 300 -> 600 only (turn the fast test off first) | Still about 330 to 360 rpm. The 0.15 s pulse caps the rate. |

## What to report

For each toggle:

- what you saw, compared with vanilla;
- the lines of `HD2Runtime.log` that start with `BEAM CONVERSION`, `[BeamConversionProof]` and `transaction beamconv-`;
- any crash, with the newest dump.

What would show the model wrong:

- a weapon that still fires bullets after `APPLIED`;
- a weapon that cannot fire or reload;
- a damage or range change that does nothing;
- a changed real Trident when only the Liberator's damage was set.
