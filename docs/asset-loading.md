# Asset loading (package residency)

A reference swap is only as good as the assets behind it. When an EAT-700 is put into a Stalwart pod, or a
Reprimand fires Talon projectiles, the reference points at resources that live in another item's package. If
nobody in the session carries that item, the package was never loaded. The pod then spawns a purple
question mark, and the projectile is invisible or broken.

HD2Runtime 0.27 loads those packages automatically, through the same native system the game uses for
loadouts. Mod authors never see or pass package IDs.

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

   Runtime never writes a reference to assets it could not confirm resident, so it produces no silent purple
   objects.

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
- `package` (short name only);
- `liveTested`;
- `blocker`.

It contains no hashes. Tools such as HD2RuntimeGUI should show objects with `known=false` as "may appear as
a missing asset".

## Reference semantics versus package residency

These are two separate questions, and the loader answers only the second:

| Question | Answered by | Acknowledgement |
| --- | --- | --- |
| Does the game behave correctly with this reference in this slot (pod rack, mount, attack)? | Gameplay evidence per slot | `allow_unverified_reference` stays required where it was |
| Are the referenced assets loaded? | Package residency (this page) | None: loaded automatically, or `ASSET_UNAVAILABLE` |

Pod swaps to non-vanilla pickups and mount swaps still require `allow_unverified_reference`, because their
gameplay semantics remain unverified. LAS-58 Talon was previously blocked as a projectile source
(`SOURCE_WEAPON_REQUIRED`), since the only failure observed was missing assets. Its package is now known, so
the swap is accepted and loads `laser_pistol` first. Sources whose dependency remains unknown stay rejected.

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
asset for an object whose authority is the host. Runtime makes no claim about remote clients.

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

## Live tests still required

The native semantics are proven offline. The in-game effect has not been live-tested (`liveTested=false`).

| Project | Checks |
| --- | --- |
| **A** `AssetTestStalwartPodEat700` | Nobody brings EAT-700. The Stalwart pod should contain two real EAT-700s. |
| **B** `AssetTestReprimandTalonProjectile` | Nobody brings the Talon. Reprimand shots should be visible Talon lasers with damage. |
| **C** `AssetTestFrvBastionCannon` | Nobody brings a Bastion. The FRV gunner mount should show the Bastion cannon; gameplay semantics are still unverified. |
| **D** `AssetTestMg43PodGrenadeBox` | The MG-43 pod's second item should be a Grenade Box that can be picked up. |

Record `[HD2Runtime] assets for <id> requested/resident` log lines, and test once solo and once with a
client that does not have the mod.
