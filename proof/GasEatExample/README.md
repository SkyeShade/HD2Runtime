# GasEatExample 0.1.7: EAT-17G Gas Expendable Anti-Tank on the custom stratagem API

Development example of `hd2.custom_stratagem` (docs/custom-stratagem-api.md). It is the "custom support weapon"
archetype. Solo, or with several players on the experimental multiplayer Runtime build (below).

0.1.7 (`0.1.7 MULTIPLAYER PROVENANCE BUILD`): the gas is declared as DATA,
`delivery={family='support',items={{donor='EAT-17 Expendable Anti-Tank',modify={impact_explosion='Orbital Gas Strike'}}}}`,
instead of an `on_delivered` callback. The definition is the same as `sdk/fixtures/custom_stratagems/GasEatExample.json`.
Solo, it behaves exactly as before. With several players (HD2Runtime `EXPERIMENTAL CUSTOM MP GAS EAT PROVENANCE BUILD
r3`):
- a delivered launcher's rocket is gas **whoever fires it**: the caller or another player who picked it up;
- **every** compatible Runtime converts its own copy of that rocket, so every player sees the gas explosion and cloud.
  Each Runtime derives the change from this same registered definition (a callback cannot be derived on another
  machine). The caller publishes only the launchers' network ids.

Install 0.1.7 on every player's machine; the 0.1.6 ZIP is renamed `OLD`.

0.1.6 (`0.1.6 DEV LINE BUILD`): the HD2Runtime 0.30 development line. It requires HD2Runtime 0.30.0-dev or newer
(`requires.hd2runtime.min_version`; the custom stratagem API is not in 0.28.0, so an older Runtime now shows its update
warning instead of failing at load). The example itself is unchanged.

## What it does

1. The call throws a blue (support) beacon. Its carrier is an unused owned support weapon, else a backpack, else it is
   refused.
2. In the beacon's first update its delivery becomes the vanilla EAT-17's: one guarded 4-byte write of that beacon only.
   The game's own hellpod then brings the EAT-17's own rack with two launchers.
3. The Runtime reads exactly those two launchers from the game's records:
   - the pod naming this beacon;
   - its rack;
   - the rack's slots, resolved through the game's network id map.

   Nothing else in the world is scanned.
4. Each of those two launchers' rocket is changed while it flies. One guarded 4-byte write of that rocket's own
   impact-explosion copy turns 376 into the Orbital Gas Strike's explosion 82. On impact it produces the Gas Strike's
   explosion and its 15 s gas cloud instead of the EAT's anti-tank blast; the direct hit stays the EAT's.

Every other EAT-17 stays 100 % vanilla, including one in your own loadout and one picked up from the world. So do the
EAT-17's StratagemInfo, its weapon definition, its projectile row 132 and the Gas Strike's chain.

It is a support stratagem everywhere it shows, matching its support carrier policy:

- **Aboard the ship:** its custom panel tile and its loadout slot overlay are coloured with a support stratagem's icon
  colour set (the EAT-17's: blue), not the red set of the saved Orbital Precision Strike token.
- **In the mission:** its HUD slot and its beacon are its support carrier's (blue).

The icon is the mod's own editable `images/eat17_gas.png`, referenced as `hd2.resources.image('eat17_gas')`. The ZIP
carries that PNG beside its manifest, and the build compiles it into the icon's texture and GUI material in the mod's
archive. It is already in the game's mask convention, so it is used as given (an ordinary red-and-white picture would be
converted to masks automatically). Edit the PNG and rebuild to change the icon.

Editing the copy inside the ZIP or in your mod manager's folder changes nothing: the game reads only the icon compiled
into the archive in `mod/`. Edit the project's `images/<id>.png` and rebuild. At load, HD2Runtime.log names the PNG and
SHA-256 the icon was built from, and whether the build compiled it, took it from its cache or recompiled it because the
source changed.

| | |
|---|---|
| Code | DOWN DOWN RIGHT UP RIGHT (no relation to any native code or the other examples' codes) |
| Cooldown | 70 s from the call-in's arrival (the EAT-17's) |
| Assets loaded at mission start | the Orbital Gas Strike (its explosion), the EAT-17 (the delivery) |
| Icon | a placeholder (a launcher and a cloud) |

Selecting it in the panel (0.1.4, the Runtime's selector UX pass): the tiles are larger, and the game's own pick sound
plays (`ui sound PLAYED stratagem_pick`). With an empty slot left, the native selector moves on to it. When the
selection leaves no empty slot (the last empty slot filled, or a slot of a full loadout replaced), the native selector
closes as Back closes it (`stratagem selector SELECTOR CLOSE VERIFIED`). A refused close logs `SELECTOR CLOSE REFUSED`
and leaves the selector open for Back.

0.1.5 (the Runtime's payload-families pass): this example's own behaviour is unchanged. The Runtime it ships with adds
the support item, sentry, Eagle and orbital payload families; install it with this Runtime and with the HmgSentryExample
and EagleStunRocketPodsExample of the same pass.

## Test

1. Expect `REGISTERED eat17_gas ... ship icon colours: EAT-17 Expendable Anti-Tank's (support, blue)`.
   Select EAT-17G Gas Expendable Anti-Tank in the CUSTOM STRATAGEMS panel: its tile and its loadout slot icon are blue.
   Expect `CUSTOM CARRIERS: ... = <a support weapon> (support, blue beacon)` and `PRE-MISSION (eat17_gas): READY`.
2. Start a solo mission. Expect `MISSION (eat17_gas): READY TO CALL ... delivery the vanilla EAT-17 Expendable Anti-Tank
   pod`.
3. Call it. Expect:
   - `eat17_gas#1: beacon ... delivery <carrier> -> EAT-17 Expendable Anti-Tank in its first update`
   - a blue beam
   - `ACTIVATED`
   - `support pod CAPTURED (eat17_gas#1): pod ... -> rack ... (type 147): 2 items ...`
   - `eat17_gas#1: DELIVERED: pod ..., rack ...: weapons A, B`
   - `weapon A: its projectiles (type 132) explode as Orbital Gas Strike's on impact (explosion 82 instead of 376)`
4. Pick up a launcher and fire it at enemies. Expect
   `projectile impact CONVERTED (... weapon A): projectile 132 ... impact explosion 376 -> 82`, then a gas cloud where
   it hits and `weapon A: its projectile ... requested Orbital Gas Strike's explosion 82 on impact`.
5. Fire both launchers.
6. Control: call a vanilla EAT-17 (or bring one in your loadout) and fire it. Expect a normal anti-tank blast and no
   CONVERTED line for it.

## Several players (experimental Runtime build)

1. Both players install the same Runtime build and this example. Expect `CUSTOM MP ASSETS: eat17_gas resident for
   remote presentation/payload` on every machine at mission start.
2. The caller logs `CUSTOM MP ITEMS: launcher network ids A, B (call beacon network id N) published ...`.
3. Every other machine logs `REMOTE CUSTOM ITEM: peer <caller>, custom eat17_gas, launcher network id A (entity X on
   this machine) ...` for each launcher.
4. Fire, or let another player pick up and fire, a launcher:
   - the caller logs `PROJECTILE CONVERTED ... (fired by ...)`;
   - every other machine logs `REMOTE CUSTOM ITEM: peer ...'s custom eat17_gas launcher network id A (entity X here):
     CONVERTED ...`.

   Everyone sees the gas cloud. The kill credit is the game's own: the player who fired it.

## Limits

- With several players: a rocket fired before another machine has correlated the launcher (the caller's next post, then
  the lobby update; not yet measured) keeps the vanilla blast on that machine.
- Kills by the rocket and its explosion credit the player who fires it: the game's own creditor, the wielder's peer.
  The gas cloud's damage-over-time instigator is not traced (unproven).
- A point-blank shot that hits before the Runtime's next read stays vanilla (logged `MISSED`).
- Self-gassing applies, as with the Gas Strike.
- Whether the picked-up launcher keeps its entity is the main live question (the research expects so).
