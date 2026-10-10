# BeamConversionProof

Development proof for the HD2Runtime beam conversion (`docs/beam-conversion.md`). It uses only the public API:
`hd2.weapon(name):beam_conversion()` and `hd2.ensure`. Each test is one toggle on the mod's options page (MODS tab,
**Beam Conversion Proof**). Every toggle is off by default.

It supersedes `MultiBeamProof` and `LiberatorBeamProof`. Those experiment proofs need a development build that ships
the experiment modules (runtime/experiment_*.lua); the release runtime (0.31.0 and later) does not. The Runtime
refuses to mix the two: while an experiment's copy of the BeamWeapon table is live, every conversion is refused, and
the other way round.

## 0.2.0: two layouts

The Runtime picks the layout per weapon (`describe().layout`, `status().layout`):

- **Add layout** (new in 0.2.0, the default where supported). The weapon keeps ProjectileWeapon and gains BeamWeapon
  through a Runtime-owned membership list. Its ProjectileWeapon type is set to 0, so its projectile path fires nothing.
  No restart is needed afterwards. Not live-tested yet.
  - Tests: Sickle, Sai, Talon, Reprimand, Liberator Penetrator.
- **Swap layout** (live-proven on 2026-10-10 with the Liberator, Talon and Reprimand). ProjectileWeapon is swapped
  out for BeamWeapon. Solo only, and restart the game afterwards.
  - Tests: Double-Edge Sickle, Liberator. Their ammunition or heat stages carry their own projectile, so the add
    layout refuses them.

`BeamConversionSyncProof` covers two machines.

## Rules for every test

1. **Play solo for this proof.** If someone joins, the Runtime restores the swap-converted weapons that are not in use
   at once. It also restores the add-layout ones unless the other player holds the identical conversion.
2. **The weapon must not exist while its toggle changes.**
   - Equip *other* weapons and keep the armory closed, then turn the toggle on.
   - Wait until the log shows `APPLIED`. The ensure retries every 5 to 20 s until the weapon is gone.
   - Then equip the weapon and deploy.
   - To turn a test off, unequip the weapon first.
3. **Restart the game after a swap-layout test** (Double-Edge Sickle, Liberator). A weapon spawned while
   swap-converted can leave a stale private copy behind. The add layout does not.

## Tests

| Toggle | Layout | Change | Expected |
|---|---|---|---|
| Sickle: Trident pulses | add | conversion | Trident pulses at 300 rpm (two beams per pulse) with the Trident's beam and sound. **No bullets.** About 1.15 heat per pulse from its own heat sink (its projectile rate is set below the pulse rate, so heat comes once per pulse). It overheats and changes heat sinks as usual. |
| Double-Edge Sickle: Trident pulses | swap | conversion | Trident pulses. Its heat-stage projectiles no longer fire; its heat-stage self-damage may still apply. Report whether it still burns you. |
| Sai: Trident pulses | add | conversion | Trident pulses, one per trigger pull or held. Report which. No bullets. Heat per pulse is the Sai's own. |
| Talon: Trident pulses at 600 rpm | add | conversion, `beam.fire_rate` 600 (the pulse is fitted to 0.067 s) | Pulses at about 550 to 600 rpm, clearly faster than the Trident. No bullets. Heat: once per pulse. |
| Liberator: Trident pulses, damage x10, AP 4 | swap | conversion; its own damage row 600 / 60, AP 4 | Each pulse hit deals 10 times the Trident's damage: medium enemies die in 1 to 2 pulses. AP 4 pierces armor the Trident cannot. The real Trident is unchanged; check it on the same enemies. One round per pulse. |
| Reprimand: Trident pulses, range 100 m | add | conversion; its own beam row length 200 -> 100 m | The beam stops at 100 m: it hits nothing past 100 m and its drawn beam ends there. No bullets. |
| Liberator Penetrator: Trident pulses (add layout) | add | conversion | Trident pulses, **no bullets, no recoil kick from bullets**, one round per pulse from its magazine, a normal reload (its chamber is turned off, as the 40-K Meltagun's is). |
| Trident: 600 rpm with a 0.05 s pulse | - | the real Trident: `beam.fire_rate` 300 -> 600, `beam.pulse_seconds` 0.15 -> 0.05 | About 550 to 600 pulses a minute. |
| Trident control: 600 rpm, 0.15 s pulse (capped) | - | `beam.fire_rate` 300 -> 600 only (turn the fast test off first) | Still about 330 to 360 rpm. The 0.15 s pulse caps the rate. |

## What to report

For each toggle:

- what you saw, compared with vanilla;
- for the add-layout weapons: any bullet, tracer or bullet impact (there must be none), the heat per pulse (Sickle,
  Talon, Sai) and the rounds per pulse (Penetrator);
- the lines of `HD2Runtime.log` that start with `BEAM CONVERSION`, `[BeamConversionProof]` and `transaction beamconv-`
  (the add layout logs `CONVERTED [add layout, ...]`);
- any crash, with the newest dump.

What would show the model wrong:

- a weapon that still fires bullets after `APPLIED`;
- a weapon that cannot fire or reload;
- a heat weapon that overheats about twice as fast as its pulses explain;
- a damage or range change that does nothing;
- a changed real Trident when only the Liberator's damage was set.
