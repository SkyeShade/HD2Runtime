# Asset loading (package residency)

A reference swap is only as good as the assets behind it. When an EAT-700 is put into a Stalwart pod, or a
Reprimand fires Talon projectiles, the reference points at resources that live in another item's package. If
nobody in the session carries that item, the package was never loaded. The pod then spawns a purple
question mark, and the projectile is invisible or broken.

HD2Runtime 0.27 loads those packages automatically, through the same native system the game uses for
loadouts. Mod authors never see or pass package IDs.

**Status: live-proven in game** (2026-09-29) for pod-payload pickups and projectile references. In all three
passing tests the donor item was not carried by anyone and the replacement loaded and worked. See
[Live results](#live-results).

## The model (proven offline on build F5FEE03DCFDB)

- Each item has a generated loadout package (`packages/generated/loadout/<item>`), named by
  `LoadoutPackageComponentData`. It holds the item's meshes, projectiles, effects and pickups. Every package
  name used by the catalog exists in the build's `bundle_database.data`.
- A package is resident while some system holds a reference on it in game.dll's
  **RefcountedPackageSystem**. This is a single global instance with a reference map of package ID to
  count. The game has about 107 call sites that request or release references in batches. The 0→1
  transition queues an asynchronous engine load; 1→0 queues an unload.
- The game takes these references for:
  - every player's loadout on the ship;
  - "all loadouts" plus stratagem payloads and level-generation world loot while preparing a mission;
  - hot-joining players' loadouts mid-mission, loaded locally in about 40 to 100 ms;
  - armory previews.

  Items nobody carries are not loaded.
- Evidence in `research/package-residency-F5FEE03DCFDB.json`:
  - In three retained snapshots, every loadout package in the reference map belongs to the equipped
    loadout.
  - The resident set is exactly the equipped items.
  - One snapshot (armory preview) shows a package that was referenced but still loading, which proves the
    load is asynchronous.
  - Crash-dump log rings show the lifecycle phases above.
- Lua: the Stingray `ResourcePackage` API exists, but its constructor (`Application.resource_package`) is
  stripped from this build. Mods therefore cannot load packages from Lua.

## What Runtime does

1. **Catalog.** `scripts/generate_package_residency.py` builds `domains/package_residency.lua` from the
   research. It maps each semantic object to the package that owns its resources:
   - 331 objects;
   - 260 with a known dependency: 253 own a package, and 7 use the package of the vanilla holder;
   - 71 unknown.

   Some packages are proven by their identity in the build, but their name has not been recovered. These
   are loaded the same way. The public metadata marks them `packageNamed=false` and shows no name.

   A dependency is published only when it is structurally proven. It is never inferred transitively.
2. **Dependency collection.** A validated patch, transaction or plan records the packages its new
   references need:
   - a pod slot that receives a pickup;
   - a vehicle mount that receives another mounted weapon;
   - a projectile or explosion reference taken from another weapon.

   Same-package swaps and vanilla values need nothing.
3. **Loading.** Before the first write, the scheduler gate:
   1. re-proves the build fingerprint;
   2. re-proves the exact code bytes of the native request and release functions, and of the engine's
      `has_loaded` and package-lookup functions;
   3. checks the reference-map instance and that the map is less than 75% full;
   4. calls the same `RefcountedPackageSystem` request the game uses for loadouts, once per package per
      session.
4. **Waiting.** The operation's status is `waiting_for_assets`. Every 0.25 s Runtime reads the engine's
   package list and part states. It is never blocking. When every part is loaded, the normal guarded write
   runs.
5. **Failure.** The operation is rejected with `ASSET_UNAVAILABLE` and the vanilla reference stays in
   place. This happens if:
   - the package is not resident after 90 s;
   - a proof fails;
   - the budget (64 packages per session) is spent;
   - the runtime cannot request packages.

   For a known dependency, Runtime never writes a reference to assets it could not confirm resident, so it
   produces no silent purple objects. Unknown dependencies are covered under
   [Reference semantics versus package residency](#reference-semantics-versus-package-residency).

### Retention and ownership

Runtime retains its references for the rest of the session and never releases natively. Live objects
(spawned pods, fired projectiles, a vehicle already on the map) use the assets without holding references.
Runtime cannot prove that nothing depends on a package, so it never unloads one. `hd2.require_assets`
cancellation and operation disable only drop Runtime's bookkeeping. Packages the game referenced are never
touched.

## Public API

Most mods need nothing new. `hd2.patch`, `hd2.transaction`, `hd2.plan` and `hd2.ensure` load dependencies
automatically.

```lua
-- Offline metadata for tools: known / autoLoadSupported / derivation / package short name. No IDs.
local info = hd2.asset_dependency(hd2.pickup('EAT-700 Expendable Napalm'))

-- Optional: warm packages up front (for example, at mod load) so later writes apply without waiting.
local watch = hd2.require_assets({id='warm-eat', targets={hd2.pickup('EAT-700 Expendable Napalm')}})
-- watch.status: waiting_for_assets -> complete (result.status 'RESIDENT') | rejected (ASSET_UNAVAILABLE)
```

`require_assets` takes typed handles only: pickups, weapons, support weapons, throwables, vehicles,
backpacks, mounted-weapon candidates and projectile handles. There is deliberately no
`hd2.load_package(id)`.

`sdk/AssetDependencyCapabilities.json` (contract `hd2runtime.asset_dependencies.v1`) publishes a
`packageDependency` entry per semantic object with these fields:
- `known`;
- `autoLoadSupported`;
- `derivation`;
- `package` (short name only; null when the name is not recovered);
- `packageNamed`;
- `liveTested` (this object was the replacement in a passing live test);
- `packageLiveLoaded` (its package was loaded live);
- `blocker`.

It also publishes `referenceFamilies`, the proof level of package loading per reference family, and
`liveEvidence`. It contains no hashes. Tools such as HD2RuntimeGUI should show objects with `known=false`
as "may appear as a missing asset".

## Reference semantics versus package residency

These are two separate questions, and the loader answers only the second:

| Question | Answered by | Acknowledgement |
| --- | --- | --- |
| Does the game behave correctly with this reference in this slot (pod rack, mount, attack)? | Gameplay evidence per slot | `allow_unverified_reference` stays required where it was |
| Are the referenced assets loaded? | Package residency (this page) | None: loaded automatically, or `ASSET_UNAVAILABLE` |

Package residency proof level per reference family (`referenceFamilies`):

| Family | Package residency | Reference / slot compatibility |
| --- | --- | --- |
| Pod-payload pickup | **Live-proven** (tests A, D and E) | Unverified in general (`allow_unverified_reference`), except the exact live-verified (rack, slot, pickup) triples (`liveVerifiedPairs`, slot `liveVerifiedPickups`) |
| Projectile reference | **Live-proven** (test B) | Unchanged: only approved compatibility classes can be swapped |
| Explosion reference | Offline-proven; same loader path and source-weapon packages as projectile references | Unchanged |
| Vehicle mount | Offline-proven; live test C was inconclusive | Unverified (`allow_unverified_reference`) |

A reference whose package is unknown gets no automatic load. The write behaves as before 0.27, gated by
the same acknowledgement. The pod catalog and the projectile catalog mark these entries `UNRESOLVED`.

Pod swaps to non-vanilla pickups and mount swaps still require `allow_unverified_reference`, because their
gameplay semantics remain unverified. LAS-58 Talon was previously blocked as a projectile source
(`SOURCE_WEAPON_REQUIRED`), since the only failure observed was missing assets. Its package is now known, so
the swap is accepted and loads `laser_pistol` first; this was confirmed live. The composition catalogs now
classify every source with a known package as `PACKAGE_AUTO_LOADED` and keep the pre-loader observation in
`observedWithoutLoader`. A source observed to need its own package whose package is unknown stays
rejected.

## Lifecycle

- **Static mod.** The operation is declared at load. The gate requests the packages on its first tick,
  usually on the ship. The write waits until they are resident, and the mission load keeps them because
  Runtime still holds its reference.
- **In-mission option change.** A re-bound ensure re-runs the guarded path. The package is already held (no
  second native request) or is requested now. Mid-mission loads are a normal native pattern (hot-join).
- **Pod payload.** The rack reference is written only after the pickup's package is resident, so every pod
  spawned afterwards finds its assets. Pods already in flight are unaffected.

## Multiplayer

Loading is local. Each client loads the loadouts it knows about. A host with the mod loads the package for
itself only. Clients without the mod still see whatever their own game resolves, and may still see a missing
asset for an object whose authority is the host. Runtime makes no claim about remote clients, except between
compatible Runtimes through synced asset loading (below, development).

## Synced asset loading (development)

`runtime/asset_sync.lua` and `runtime/asset_sync_protocol.lua`. Built and tested offline only; not exported to
mods and nothing a mod has to opt into.

**Behaviour.** Every package a mod's own request makes Runtime load is shared with the lobby: `hd2.require_assets`,
the reference swaps of `hd2.patch`, `hd2.plan` and `hd2.transaction` (and `hd2.ensure` through them), and the
explosion and spawn actions that load their assets first. Runtime-internal loads are never shared (custom
stratagems sync their own assets: `CUSTOM MP ASSETS`; Pelican guns, explosion donors, beacons, slot conversion,
the selector). Another lobby member running the same Runtime version with the same catalog loads the same
packages through the same loader, so a networked entity or projectile that uses them finds its assets there
too, even though that player does not have the mod.

- The local shared set: the distinct catalog packages shared gates requested, at most 24 (the rest is logged
  once as not shared).
- Publishing: the set as this machine's lobby member property `hd2as`, through the peer channel
  (`runtime/peer_channel.lua`, the game's PlayFab member data). It is posted again in every lobby this machine
  joins, so a joiner reads it too. Nothing is published while the set is empty.
- Reading: in the Runtime's own update, every 3 s and only in a joined lobby of at least 2 members, every other
  member's `hd2as` value. For a compatible member, each listed package this machine's catalog knows and does not
  hold yet is requested through the normal asset gate (`synced-<peer>`); its residency is polled like any other
  gate's. Runtime starts this at load in the game (`api/hd2.lua`), so a player with no mod at all still loads
  what a compatible peer's mods need.

**Protocol `hd2as/1`.**

```
hd2as/1;<runtime version>;<catalog hash>;<seq>;<pkg>,<pkg>,...
```

`<runtime version>` is `domains/metadata.lua`'s version. `<catalog hash>` is the FNV-1a 32 (8 uppercase hex
digits) of every package id `core/assets` accepts (the package residency catalog plus the stratagem call-in
packages), sorted, one per line. `<seq>` (1 to 2^31-1, no leading zeros) rises on every change of the set.
`<pkg>` is a package id as 16 uppercase hex digits without `0x`: 1 to 24 of them, strictly ascending. The value
is at most 512 bytes. A value that does not match the grammar exactly is refused whole. The sender is the lobby
member the value was read from, never a field.

**Compatibility rule.** A peer's packages are loaded only when its Runtime version and catalog hash both equal
this machine's. Anything else is logged once (`its assets are not loaded here`) and ignored. A package id this
machine's catalog does not know is logged once and skipped (the identity rule of every Runtime request: never
load an id the catalog does not list). A player without the Runtime publishes nothing and cannot be told
anything: its game shows whatever it loaded itself.

**Limits.**

- 24 packages per peer (the published set).
- The 64-package budget and the 75 % reference-map fill limit apply to everything Runtime holds. Synced packages
  are requested only while Runtime holds fewer than 48 (`asset_sync.RESERVE` = 16 stay for this machine's own
  mods and custom stratagems); the rest is refused with `ASSET_UNAVAILABLE` and logged.
- Catalog identities only. Level, faction and objective content is not covered.
- The PlayFab post rate: the `hd2as` and `hd2rt` keys share one post per 5 s, nothing in the first 10 s of a
  lobby, and the first post waits for the game's own `platform_lobby` post. A change reaches the peers seconds
  later; nothing waits for it.
- Retention is the session's, as for every Runtime load: a synced package is never released.

**Log lines** (`[HD2Runtime] SYNCED ASSETS ...`, each distinct line once):

- `SYNCED ASSETS: publishing seq <n>, <k> package(s) for the lobby's compatible Runtimes: <name> (for <mod>); ...`
- `SYNCED ASSETS: peer <peer> (seq <n>) asks for <k> package(s): <names>`
- `SYNCED ASSETS: peer <peer>: requesting <k> package(s) here: <names>`, then
  `... <k> package(s) resident here: <names>` or `... loading failed (ASSET_UNAVAILABLE: ...)`
- `SYNCED ASSETS: peer <peer>: already held here: <names>`
- `SYNCED ASSETS: peer <peer> runs Runtime <v> (catalog <h>): its assets are not loaded here (...)`
- `SYNCED ASSETS: peer <peer> asks for package <hex>, unknown to this catalog: skipped`
- `SYNCED ASSETS: peer <peer> published a malformed value (<why>): ignored`
- `SYNCED ASSETS: peer <peer>: refused <names> (ASSET_UNAVAILABLE: synced packages use at most 48 ...)`
- the channel's own: `PEER CHANNEL POSTED: hd2as = "hd2as/1;..."`

**Not proven live.**

- A second member-data key next to `hd2rt` (the engine call takes the key as a parameter; only `hd2rt` has been
  posted and read live).
- A client loading a peer's package, and the peer's networked entity or projectile then drawing with it on that
  client.
- Joiners: a member joining a lobby where the value is already posted, and loading mid-mission.
- Nothing gates a networked swap on the peers being ready: a mod's change applies on its own machine as before,
  whether or not the peers have loaded the package yet.

## Security

- Package identities come only from the generated catalog, keyed by semantic object. Each identity is
  checked against the build's bundle database.
- Every native call first re-proves the build fingerprint and exact code bytes. A changed byte fails closed
  with `ASSET_UNAVAILABLE`.
- There is no raw-ID API or generic "load anything" route. The budget bounds reference-map growth, and the
  fill limit keeps the native map (which has no overflow path) far from capacity.

## Validation

- `scripts/validate_asset_residency_snapshot.py` checks the following against all three snapshots:
  - proofs on real memory;
  - resident, mid-load and absent states;
  - rejection of tampered code bytes, a wrong build and uncatalogued packages;
  - deduplication (two operations, one native request);
  - bookkeeping-only release;
  - the 90 s timeout;
  - pass-through when there is no dependency;
  - the budget.
- `scripts/validate_packaged_runtime.py` runs the four asset-test examples from the built ZIP with a
  simulated loader. Each requests its package once, waits, then applies.

## Live results

Recorded in `research/package-residency-live-evidence.json`. Runtime commit `cff6d0f` was run from the
test build in `build/test-artifacts/assets-0.27/`. In every test, nobody carried the donor item.

| Test | Project | Family | Result |
| --- | --- | --- | --- |
| A | `AssetTestStalwartPodEat700` | Pod-payload pickup | **Pass.** The pod spawned a real, usable EAT-700 instead of the purple question mark. |
| B | `AssetTestReprimandTalonProjectile` | Projectile reference | **Pass.** The Reprimand fired the Talon projectile with correct visuals and function. |
| D | `AssetTestMg43PodGrenadeBox` | Pod-payload pickup | **Pass.** The Grenade Box spawned correctly and could be picked up. |
| C | `AssetTestFrvBastionCannon` | Vehicle mount | **Inconclusive.** The Pelican did not deliver the FRV, so the mount was never observed. |

Before 0.27 these swaps wrote a valid reference, but the assets were missing unless someone equipped the
donor item. With the loader, the donor item no longer needs to be in the mission.

### Vehicle mounts

A vehicle-mount live test is not required for 0.27.0. Mount swaps still require
`allow_unverified_reference`, and the mount family is published as offline-proven only. The mount path uses
the same gate and native request as the live-proven families. The Bastion-cannon-on-FRV case also mixes in
an unverified mount-compatibility question.

A later test, if wanted: M-102 Gunner FRV `slot_0` ← the M-103 Supply FRV gun. This is the same FRV
chassis and weapon family, and the gun lives in a different package (`ammo_rack_mounted_turret`).

### Still worth testing

- A client without the mod joining a host with the mod (multiplayer caveat above).
- An explosion-reference swap from another weapon's package.
