# HD2Runtime to-do

Ideas parked for a later pass. Each entry says why it matters and what has to be proven first.

## Synced asset loading (after the per-shot projectile pass)

**Problem.** One player's mod loads a package through the asset loader (a new mech arm, a swapped projectile's unit,
another weapon's round), but the other players never brought that item into the mission, so their game never loads
it. When the networked entity or projectile spawns on their machine, its assets are missing: an asset-load mismatch
(missing visuals at best, a crash at worst).

**Idea.** Every compatible Runtime in the lobby loads the union of the packages any member's mods need, before the
mission (or before the first use), through the existing custom multiplayer lobby table. Custom stratagems already do
this for their own payloads (`CUSTOM MP ASSETS: <id> resident for remote presentation/payload`); the generic version
would let any mod declare its asset needs once and have every peer load them.

**Open questions.**
- What the fallback is for a lobby member without the Runtime (it cannot be told anything): refuse the change, or fail
  closed for that mission.
- Timing: the package must be resident on each machine before the entity that needs it spawns there.
- Which packages may never be loaded by the Runtime (level or faction content).

**Feasibility (research pass 2026-10-07): yes, between machines that all run a compatible Runtime; never for a
player without it.**
- Proven: the lobby channel (`runtime/peer_channel.lua`), compatibility by registry hash (`runtime/custom_mp_sync.lua`),
  each machine deriving the same package list from its own registered data, remote package requests (custom
  stratagems' `CUSTOM MP ASSETS`, live r3), and loading packages nobody in the lobby carries (asset tests A, B, D, E).
- Today `CUSTOM MP ASSETS` is requested in the mission, logs `NOT resident` on a timeout, and nothing waits on it.
- Sketch: mods declare `assets = {typed handles}` statically (hashed into the registry, so no package ids on the wire,
  512-byte value); once sync is enabled aboard the ship each machine gates the union locally; each publishes an
  "assets ready" flag in its `hd2rt` value; a networked swap applies only when every member is ready, else it stays
  vanilla (fail closed); re-checked at mission start, joiners refused or neutralised.
- Limits: the 64-package budget and 75 % refcount-map fill apply to the union; level, faction and objective content
  cannot be covered; the post rate limit delays the ready flag.
- Unknown, needs live tests: what a vanilla client sees when a networked item spawns without its package (placeholder
  or crash); whether a ship-time request survives into the mission on a client; joiners loading mid-mission.

**Built (development, offline only; 2026-10-07): `runtime/asset_sync.lua`** (docs/asset-loading.md, "Synced asset
loading (development)"). A mod's shared asset gates (require_assets, patch/plan/transaction swaps, explosion and
spawn actions) publish their catalog packages under a second member-data key `hd2as` (`hd2as/1;<version>;<catalog
hash>;<seq>;<pkgs>`, at most 24); every member with the same Runtime version and catalog hash requests them through
`core/assets` (`synced-<peer>`), keeping 16 of the 64-package budget for its own requests. The two keys share the
channel's post rate. Started at load in the game, so a player with no mod loads them too. No static declaration was
needed: the packages are published as they are requested.

Remaining:
- The "assets ready" gating of networked swaps: a mod's swap still applies on its own machine whether or not the peers
  have loaded the package (each member could publish which peers' sets are resident; a swap could wait for them, or
  stay vanilla, fail closed).
- Live tests: a second member-data key; machine B (Runtime, no mod) loading machine A's package and A's networked
  entity or projectile drawing with it on B; a joiner; a mismatched version refused.
