# Drop-pod payloads

A support-weapon, backpack, expendable or Resupply call-in lands a hellpod that opens with items. The
runtime lets a mod change what those items are: another support weapon, a backpack, or a consumable
pickup such as a supply box. It can also change how many slots spawn.

```lua
-- Surplus EAT Allocation: the pod opens with two supply boxes (see examples/projects/SurplusEatPodSwap)
local rack=hd2.booster('Surplus EAT Allocation'):granted_stratagem():delivery():rack()
hd2.ensure({plan={id='surplus-eat-pod-swap',operations={
    {id='slot-1',target=rack:slot(1),field=hd2.fields.payload.entity,expect=rack:slot(1):current(),
        value=hd2.pickup('Supply Box'),allow_unverified_reference=true,allow_shared=true},
    {id='slot-2',target=rack:slot(2),field=hd2.fields.payload.entity,expect=rack:slot(2):current(),
        value=hd2.pickup('Supply Box'),allow_unverified_reference=true,allow_shared=true}}}})
```

## Native model

| Step | Native object | Notes |
| --- | --- | --- |
| Call-in | `StratagemDefinition` primary payload | The payload is a hellpod rack entity |
| Rack | `HellpodRackComponent` (568 bytes) | 8 `RackAttach` slots × 64 bytes, then `random_payload_size` (+552) and `spawn_payload_size` (+556) |
| Slot | `RackAttach` | `item` (+0, u64 entity reference), `node` (+8), offsets, animation events, `apply_deltas` (+48), `rack_side` (+52) |
| Item | The referenced entity | Spawned directly from the slot, with no intermediate resource layer |

The pinned type library confirms each member's offset, storage and hidden-name length. The live snapshot's
rack, interactable, loadout-package, backpack and weapon tables are byte-identical to the pinned reference.

- **Surplus EAT.** The booster's granted stratagem (`LATOneshot_Booster`) delivers `weapon_rack_lat_oneshot`.
  That rack's slots 1 and 2 both reference the EAT-17 entity, and `spawn_payload_size` is 2. The ordinary
  EAT-17 call-in uses the same rack entity, so the rack is shared: an edit changes both pods and requires
  `allow_shared`.
- **Slot count.** The count is data-driven: the first `spawn_payload_size` slots spawn. Vanilla racks use
  1, 2, 4 and 6. A single rack may reference the same item several times, and an active slot may be empty
  (the EAT-411 Leveller spawns 2 with slot 2 empty).
- **Shared racks.** 6 racks serve more than one stratagem: EAT-17 and Surplus EAT, MG-43 and its reward
  variant, Resupply and its reward variant, the Health Pack Rack pair, the Jump Pack pair, and the two
  Hellbomb backpacks.

## API

- **Finding a rack.** Use `hd2.stratagem(name):delivery():rack()` or `:payload()`, or
  `hd2.booster(name):granted_stratagem():delivery():rack()`. `hd2.pod_rack(name or semanticId)` also works.
- **Rack methods.** `rack:slots()`, `rack:slot(n)` and `rack:describe()`. `slot:current()` returns the
  current item as a pickup, or `'empty'`.
- **Pickups.** `hd2.pickup(name or semanticId)` returns one reviewed replacement pickup;
  `hd2.pickups(category)` lists them.
- **`hd2.fields.payload.entity`.** Set on a slot. `expect` and `value` are pickups or `'empty'`. Raw
  identifiers are rejected.
- **`hd2.fields.payload.spawn_count`.** Set on the rack; an integer from 1 to 4.

Slots 1 to 4 are authored. Slots 5 to 8 carry no rack side in weapon racks; only one vanilla rack spawns from
them, so they stay read-only.

## Replacement catalog and compatibility

Categories are typed. None is ever inferred from a name:

| Category | Native evidence |
| --- | --- |
| `support_weapon` | `InteractableComponent` zone of type `PickupWeaponSupport` |
| `backpack` | Owns `BackpackComponent` |
| `ammo`, `stim`, `grenade`, `supply` | Zone of type `PickupAmmo`, `PickupHealth`, `PickupGrenades`, `PickupSupplies` or `PickupSuppliesFromRack` |

`InteractType` values 0 to 8 are proven by type-library alias lengths. Later values were renumbered in this
build and are not used.

| State | Meaning |
| --- | --- |
| `PROVEN_COMPATIBLE` | The slot's own vanilla occupant. Restoring it needs no reference acknowledgement |
| `SCHEMA_COMPATIBLE` | Vanilla spawns this entity from some rack slot, but it is untried in this pod |
| `UNVERIFIED_REFERENCE` | A standalone typed pickup that no vanilla rack uses |
| `INCOMPATIBLE` | Deployables, objectives, primary and sidearm pickups. Never offered |

World loot is published separately. `evidence.worldLoot` marks entities found in the loaded
`LevelGenerationSettings` cache (bunker) loot tables. Appearing there proves an entity is a standalone
pickup, not that it is safe in every pod.

## Package risk

A reference is only as good as the assets behind it. Each pickup publishes `residency.packageKey` (an
opaque key for its own loadout package), `alwaysResident`, and the basis for that. Each rack publishes
`residentPackages`: the rack package, its stratagems' packages and its vanilla items' packages.

- **Low risk.** The pickup is the vanilla occupant, it is always resident, or its package key is in the
  rack's `residentPackages`.
- **Always resident.** The Supply Box ships in the Resupply rack's package, and Resupply is available in
  every mission. It is the only always-resident pickup, which is why the live test uses it.
- **High risk (everything else).** This includes other support weapons, health packs, world ammo and
  grenade boxes: their assets load only when their own package does. These writes are allowed only with
  `allow_unverified_reference=true`, and the GUI should show the warning.

Since 0.27 Runtime loads the pickup's own package automatically before writing the slot, when that package
is known; see `asset-loading.md`. The status is `waiting_for_assets` until the package is resident, and the
write fails with `ASSET_UNAVAILABLE` (keeping the vanilla item) if it never becomes resident. This was
live-proven: an EAT-700 in the Stalwart pod and a Grenade Box in the MG-43 pod both spawned usable, with
nobody carrying either item. Each pickup publishes `packageDependency`, with `packageResidency` set to
`LIVE_PROVEN`, `ALWAYS_RESIDENT` or `UNRESOLVED`.

Loading resolves missing assets only. Whether a pickup behaves correctly from a given pod remains
unverified in general, so `allow_unverified_reference` is still required. The exact (rack, slot, pickup)
triples a live test showed working are the exception. Each authored slot publishes them as
`liveVerifiedPickups`, and a write of one of them into exactly that slot needs no `allow_unverified_reference`:

- M-105 Stalwart pod slot 2 <- EAT-700 Expendable Napalm (test A);
- MG-43 Machine Gun pod slot 1 <- Grenade Box (test D);
- Resupply pod slots 1-4 <- Grenade Box (ResupplyTest).

The same pickup in another slot or rack, or another pickup in these slots, keeps the acknowledgement.
`allow_shared` stays required on shared racks (the MG-43 and Resupply pods): it is a scope acknowledgement, not an
unverified one. All pairs are also listed in `liveVerifiedPairs`.

## Guards

Every write re-proves:
- the build fingerprint;
- every consumer stratagem still delivering this rack as its primary payload;
- the rack's ownership, with `random_payload_size` still 0;
- the target slot's attach node;
- the current reviewed reference (a third-party change fails as CONFLICT);
- the replacement's typed pickup component and interaction.

Required acknowledgements:
- `allow_unverified_reference` for any non-vanilla slot item, except a live-verified pickup in its tested slot;
- `allow_unverified_effect` for a spawn-count change;
- `allow_shared` for every write to a shared rack.

## Read-only racks

| Rack | Reason |
| --- | --- |
| MS-11 Solo Silo, Remote Explosives, Carry Data, Cyborg Carry Data, Spire Sterilizer | Deliver deployables or objectives, not pickups |
| TX-41 Sterilizer, Dark Fluid Backpack | Their item entity has no resolvable name, so it cannot be offered as a reviewed pickup |
| Jammed Pod | Draws a random subset (`random_payload_size`), so slot order does not decide what spawns |
