# PelicanCasExample 0.1.8: Pelican Close Air Support on the custom stratagem API

Development example of `hd2.custom_stratagem` (docs/custom-stratagem-api.md). Solo, or with several players on the
HD2Runtime `EXPERIMENTAL CUSTOM MP PROVENANCE BUILD r4` (every lobby member running it and this example).
It is the "autonomous spawned entity" archetype.

0.1.8 (`0.1.8 HOST PELICAN BUILD`): the Pelican is now stated as data (`pelican={hover, orbit, gun}`), so the Runtime
owns its call across machines: a client's call asks the session host to spawn it, every compatible machine mirrors the
chin gun on its own copy, and the host credits its rounds to the caller. The 0.1.7 example (`0.1.7 DEV LINE BUILD`)
spawned it from its own `on_activate` callback, on the host only.

## What it does

The call's beacon is neutralized in its first update, so the carrier delivers nothing. At the activation, one empty
game Pelican flies to the beacon's landing position and holds over it for 60 s. It also orbits the beacon (40 m out,
60 m up, 55 s). Its chin gun has the frozen Pelican CAS configuration, applied to its own copies and records only:

- the MG-206 Heavy Machine Gun's AP4 round (projectile 275);
- 2× the Gatling Sentry's rate (3200 RPM);
- 100 mrad spread and no aim recoil;
- the Gatling casing;
- the 2047-round safe magazine, refilled below 1500;
- the Gatling Sentry's AI with the Runtime target lock and body facing.

The chin gun's kills credit you: the turret's own no-credit tag is cleared.

| | |
|---|---|
| Code | LEFT DOWN LEFT UP LEFT UP |
| Cooldown | 60 s from the call-in's arrival |
| Carrier | an unused owned stratagem with a red (offensive) beacon, an orbital first |
| Assets loaded at mission start | A/G-16 Gatling Sentry, MG-206 Heavy Machine Gun |

The icon is the mod's own editable `images/pelican_close_air_support.png`, referenced as
`hd2.resources.image('pelican_close_air_support')`. The ZIP carries that PNG beside its manifest, and the build compiles
it into the icon's texture and GUI material in the mod's archive. It is already in the game's mask convention, so it is
used as given (an ordinary red-and-white picture would be converted to masks automatically). Edit the PNG and rebuild to
change the icon.

Editing the copy inside the ZIP or in your mod manager's folder changes nothing: the game reads only the icon compiled
into the archive in `mod/`. Edit the project's `images/<id>.png` and rebuild. At load, HD2Runtime.log names the PNG and
SHA-256 the icon was built from, and whether the build compiled it, took it from its cache or recompiled it because the
source changed.

Selecting it in the panel (0.1.4, the Runtime's selector UX pass): the tiles are larger, and the game's own pick sound
plays (`ui sound PLAYED stratagem_pick`). With an empty slot left, the native selector moves on to it. When the
selection leaves no empty slot (the last empty slot filled, or a slot of a full loadout replaced), the native selector
closes as Back closes it (`stratagem selector SELECTOR CLOSE VERIFIED`). A refused close logs `SELECTOR CLOSE REFUSED`
and leaves the selector open for Back.

0.1.5 (the Runtime's payload-families pass): this example's own behaviour is unchanged. The Runtime it ships with adds
the support item, sentry, Eagle and orbital payload families; install it with this Runtime and with the HmgSentryExample
and EagleStunRocketPodsExample of the same pass.

0.1.6 (`0.1.6 FROZEN GUN BUILD`): the example is unchanged; the Runtime it ships with fixes a live regression. A Pelican
called after the custom HMG Sentry was refused (`PELICAN WEAPON REFUSED ... RATE_UNEXPECTED: the deployed Gatling Sentry
... runs 540.00 RPM`), because the chin gun's Gatling values were checked against a deployed sentry. They are now frozen
from the pinned research (the Gatling's 1600 RPM, casing, spread and recoil): no deployed sentry, custom or vanilla, and
no Gatling Sentry type record is read to configure it. Expect `ATTEMPT ... (the frozen Gatling rate 1600 RPM x ...)` and
`ARMED` even with a custom or vanilla sentry deployed.

## Test

1. Aboard the ship, select Pelican Close Air Support in the CUSTOM STRATAGEMS panel. Click it, or press F7 to focus and
   F7 again to select; F6 moves the focus and Ctrl+F7 undoes. Then leave the loadout screen.
2. Expect these log lines:
   - `custom stratagem CUSTOM CARRIERS: ... Pelican Close Air Support = <carrier> (orbital, red beacon) ...`
   - `PRE-MISSION (pelican_close_air_support): READY ...`
3. Start a solo mission. Expect `MISSION (pelican_close_air_support): READY TO CALL`.
4. Call it with the code. Expect, in order:
   - `pelican_close_air_support#1: BEACON ...` and `... delivery <carrier> -> none in its first update`
   - `LANDED`, then `ACTIVATED`
   - `Pelican <entity> on its way to the beacon`
   - `pelican gunship ...: ARMED: chin turret ...: projectile 275 (ap4), 3200 RPM, spread 100 mrad, aim recoil zero,
     magazine 2047, credit to the caller (the host)`
   - `AI: ... 645 -> 213`, then `ORBIT started`
   - `KILL: victim ... by its weapon ... -> credited to <you> (you)`
   - `SUMMARY`
5. Back aboard the ship, expect `RETURN TO SHIP: <carrier> presentation RESTORED`.

## Several players (r4, not live-tested)

Both machines on the r4 Runtime and this example.

- **The host's call:** as solo, plus `CUSTOM MP ITEMS: Pelican network id P, chin turret network id T ... published`.
  The client logs `REMOTE CUSTOM PELICAN: peer <host>, custom pelican_close_air_support, Pelican network id P ...` and
  `REMOTE CUSTOM PELICAN: ...: chin gun MIRRORED on this machine's own copy: projectile 275`, then `its own shot
  interval ... (3200 RPM) on this machine`.
- **A client's call:** the client logs `CUSTOM MP CALL REQUESTED: the session host spawns the Pelican for this call (call
  seq S, loadout slot N, beacon network id B, ...)`. The host logs `CUSTOM MP CALL REQUEST: peer <client> ...: ACCEPTED`,
  `HOST CALL: peer <client>'s pelican_close_air_support ...`, `PELICAN: E spawned on the host for the requesting player`,
  the gunship's `ARMED` and `CREDIT (...): ... its own creditor ... -> <client>`. The client then logs the same
  `REMOTE CUSTOM PELICAN` lines as above for its own call's Pelican.
- On both machines: one Pelican at the same position and orbit, the same rapid full-auto chin gun with the AP4 rounds,
  never the stock autocannon. The kills of a client's Pelican credit that client.

## Limits

- The residual high aim and body-facing behaviour are not corrected (frozen).
- With several players the host keeps the Pelican's flight, hold, orbit, targeting, lifetime and credit; a client only
  draws its own copy's rounds.
