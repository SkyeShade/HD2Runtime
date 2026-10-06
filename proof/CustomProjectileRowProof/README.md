# CustomProjectileRowProof (development only)

Live proof for Runtime-owned custom projectile rows (`docs/custom-projectile-rows.md`). It is **not** an example of a
public API: it calls Runtime internals that may change. Build it with `py scripts/build_custom_projectile_proof.py`,
which also builds the matching development runtime into `build/test-artifacts/`.

Install both ZIPs from `build/test-artifacts/`: the development `HD2Runtime-<version>-runtime.zip` (it replaces the
installed HD2Runtime for the test) and `CustomProjectileRowProof-0.1.0.zip`.

## Keys (host, in a mission)

Each custom projectile is a Runtime-owned clone of the LAS-58 Talon row (type 144) with one component taken from a
donor projectile (`docs/custom-projectile-rows.md#components`):

- **F7**: visual only, from the PLAS-1 Scorcher (its spawn particle effects).
- **F5**: damage only, from the RS-422 Railgun (600 / 225, armor penetration 5, instead of the Talon's 200 / 20, 3).
- **F6**: ballistics only, from the GL-21 Grenade Launcher (about 100 m/s with gravity: a visible lob).
- **F10**: impact explosion only, from the R-36 Eruptor (its shell blast and shrapnel).
- **F11**: all four together.
- **F8**: a vanilla LAS-58 Talon bolt from the same origin in the same direction, for comparison.
- **F9**: checks that every vanilla projectile row (and the table entries 0 and 351) is byte-identical to the moment
  the mission started, and that every custom row is unchanged.

Every shot leaves 1.0 m ahead of the held weapon along its forward axis, so they follow where the weapon points. No
muzzle or camera transform is researched, so this approximates the muzzle. Without a weapon in the hands, shots leave at
chest height along the direction your Helldiver faces. Each shot line names its source (`[held weapon pose]` or
`[avatar facing (...)]`); see `docs/custom-projectile-rows.md#aiming`.

The first shot of a variant may log `waiting_for_assets`: its packages load first (the Talon's and its donors'), then
the projectile fires.

## Avatar lifecycle

A mission is announced before your Helldiver lands, so the proof defines its projectiles at mission start. It then
follows the local avatar, checking every 0.5 s and before every key press, and logs:

- `waiting for avatar`, with a reminder every 10 s that names the failing step;
- `avatar became available: entity N (via the player list)`;
- `avatar lost: <reason>` after a death or other loss;
- `avatar restored: entity N replaces entity M` after a reinforcement or respawn;
- `mission ended`.

While it waits, the keys log `waiting for avatar (<reason>)` instead of firing. Definitions stay ready across
missions, so no restart is needed.

The avatar is found through the player list first, and through Runtime's `handles.local_avatar` otherwise. Runtime's
action layer uses that function, which also asks the player list first and only then scans the owned health
records. If the action layer does not resolve the same avatar, a `note:` line says so once: spawns would then be
refused with `NO_LOCAL_AVATAR`. No such line appeared in the 2026-09-30 live run.

## Report

The checklist is in `docs/custom-projectile-rows.md#live-test`.
