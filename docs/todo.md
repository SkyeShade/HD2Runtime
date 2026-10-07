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

Research started 2026-10-07 (feasibility pass); not designed or built yet.
