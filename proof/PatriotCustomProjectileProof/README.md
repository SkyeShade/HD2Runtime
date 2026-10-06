# PatriotCustomProjectileProof (development only)

The EXO-45 Patriot Exosuit's primary weapon, its right_gun minigun, fires `dev/talon_combined` through weapon
projectile replacement (`docs/custom-projectile-rows.md#weapon-projectile-replacement`). It is **not** a public mod: it
calls Runtime internals that may change. No public API changed for it.

Build with `py scripts/build_custom_projectile_proof.py` and install the development `HD2Runtime-<version>-runtime.zip`
and `PatriotCustomProjectileProof-0.1.0.zip` from `build/test-artifacts/`. **Install no other carrier proof alongside
it** (ReprimandCustomProjectileProof, ReprimandFireModeProof, LiberatorConcussiveFireModeProof): they bind the same
carrier, and the last binding wins (a warning is logged). Call in a fresh Patriot after APPLY: the projectile is copied
into the exosuit when the game builds it.

## How it works

| Step | What | Evidence |
| --- | --- | --- |
| Suppression | `attack.projectile` of `hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('right_gun')` (its ProjectileWeapon +0) is swapped from the native bullet (type 148) to the carrier (type 324: no effect, no unit, damage type 0, no explosion) | the same swap is live-proven on this minigun for the EAT-17, Talon and Scorcher; the carrier is not one of those, so the request gives `allow_unverified_effect` |
| Replacement | each carrier whose **source** is the minigun is replaced by one `dev/talon_combined` from the carrier's spawn point, along its direction | the source identity is the minigun's catalogued entity type `0x08F6089289C83D22` (the attack output's owner), because no weapon name is catalogued for mounted weapons |
| Confirmation | the next update finds the custom projectile in its pool slot (the definition's base type) | counted as `confirmed`; anything else is `not` and logged |
| Suppression check | a type 148 shot from the minigun is a suppression failure: logged `SUPPRESSION FAILED`, never replaced | type 148 is shared (Gatling and machine-gun sentries fire it too): only the minigun's count |

**Creditor.** Which entity owns a mounted weapon's shot, and so which peer it is credited to, is not proven offline:
the weapon update looks the owner up in a component manager, which is the avatar for a handheld weapon. This binding
accepts a minigun shot credited to the local peer **or to no peer** (`credit = 'local_or_none'`), and logs the
creditor, owner and source of the first 100 shots so the live run shows the real attribution. Shots credited to
another peer are not replaced. In multiplayer, if the game credits exosuit shots to no peer, another player's Patriot
on the host would be replaced too (untested).

## Keys (host, in a mission)

- **F12**: replacement on / off. Off, the minigun fires the invisible, harmless carrier alone.
- **F9**: carriers, replaced, confirmed in the pool, dropped (rate), refused, not the local player's, other sources,
  native bullets seen (suppression held / FAILED), latency, and the last burst's shot count and rpm.

## What the log shows

```
mission started: replacement binding: carrier output/v1/projectile/td-110-maelstrom-slot-2 (type 324) from EXO-45
  Patriot Exosuit / right_gun -> dev/talon_combined; native output/v1/projectile/exo-45-patriot-exosuit-right-gun
  (type 148) suppressed: bound
projectile replacement: TD-110 Maelstrom / slot_2 shot N: carrier slot S (type 324) at (...) travelled D m (...);
  owner O, source W (EXO-45 Patriot Exosuit / right_gun); custom dev/talon_combined from (...) along (...) -> slot M,
  the avatar at (...); creditor local peer | none; owner O (the local avatar | type ...); source W (type
  08F6089289C83D22 EXO-45 Patriot Exosuit / right_gun); projectile type 324 in EXO-45 Patriot Exosuit / right_gun
  (output/v1/projectile/exo-45-patriot-exosuit-right-gun, native type 148); latency one game update (dt X ms),
  carrier flew D m = T ms before the read
projectile replacement: EXO-45 Patriot Exosuit / right_gun (...) burst: N shots (N custom, 0 native) over T s = R rpm
projectile replacement: TD-110 Maelstrom / slot_2 -> dev/talon_combined: C carriers, R replaced (R confirmed in the
  pool, 0 not), 0 dropped (rate), 0 refused, ...; 0 native ... shots seen (suppression held); latency one game update:
  mean X ms, max Y ms; carrier flight before the read max Z ms
```

**Latency.** Runtime reads the pool once per update, before the game update that fires weapons, so a carrier is read
in the update after it was spawned, and the custom projectile enters the game in that update: one game update (one
frame) after the shot. The log gives that update's `dt` and how long the carrier had flown when read (its distance
travelled over its speed; 0 ms on the Reprimand).

**Rate.** The minigun fires 1200 rpm (20 per second). Replacement allows 30 per second (a burst of 40) and 24 per
update, so it never drops a minigun shot.

## Live test

1. Call in a fresh Patriot and fire the minigun: every shot is the plasma-looking, arcing `dev/talon_combined`, with
   the Eruptor blast on impact; **no minigun bullet or tracer** is visible, and there is no second projectile.
2. F9 after a few bursts: `carriers` = `replaced` = `confirmed`, `dropped` 0, `refused` 0, `native bullets seen: 0
   (suppression held)`, and the last burst about 1200 rpm.
3. Long sustained fire (the minigun holds 1350 rounds): the counts stay equal and `dropped` stays 0.
4. F12 off: the minigun fires nothing visible and deals no damage (the carrier alone). F12 on: replacement is back.
5. Aim: hip and moving; report any offset or delay against the reticle.
6. Send the `projectile replacement:` lines, especially the first `shot N` lines (creditor, owner, source, latency).
