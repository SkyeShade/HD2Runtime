# Backpack ammunition

Three support weapons carry no ammunition of their own: the M-1000 Maxigun, the B/FLAM-80 Cremator and
the GL-28 Belt-Fed Grenade Launcher. Their ammunition is stored in the backpack delivered with them, so
the runtime authors it on the backpack.

```lua
-- M-1000 Maxigun: 1000/1000/500 -> 1023/1023/1000 (see examples/projects/MaxigunBackpackAmmo)
local backpack=hd2.support_weapon('M-1000 Maxigun'):backpack()
hd2.ensure({transaction={id='maxigun-backpack-ammo',target=backpack,allow_unverified_effect=true,changes={
    {field=hd2.fields.deposit.capacity,expect=1000,value=1023},
    {field=hd2.fields.deposit.start_amount,expect=1000,value=1023},
    {field=hd2.fields.deposit.refill_amount,expect=500,value=1000}}}})
```

## Native chain

| Step | Native object | Proof |
| --- | --- | --- |
| Call-in | `StratagemDefinition` primary payload | The payload is the weapon's hellpod rack |
| Delivery | `HellpodRackComponent`, 8 slots × 64 bytes | Slot 0 holds the weapon, slot 1 the backpack |
| Weapon feed | Weapon `WeaponLinkedAmmoComponent`: `tag` (+0), `ammo_mode` (+8), `inventory_slot` (+12) | `inventory_slot` is `Backpack` (6) |
| Pairing | Backpack `TagComponent` | Only this backpack carries the weapon's linked-ammo tag; the two tag fields share one enum type |
| Ammunition | Backpack `DepositComponent`: `capacity` (+0), `start_amount` (+4), `refill_amount` (+8), `refill_style` (+128) = Ammo | The record has one owner, and scraped capacity and supply values match exactly |

The member names above come from Filediver. The pinned type library confirms each one's offset,
storage and hidden-name length. The live snapshot's linked-ammo, deposit, tag and rack tables are
byte-identical to the pinned reference.

What the chain establishes:

- **The gun holds nothing.** None of the three weapons owns a `WeaponMagazineComponent`, and none has
  a placeholder capacity. The Maxigun's `WeaponReloadComponent.has_shared_deposit` is false, because
  that flag is for mounted weapons that read their vehicle's deposit.
- **The backpack is authoritative.** The weapon fires from the item in the Backpack slot that carries
  its tag, and that item's deposit is the ammunition count.
- **Nothing else is affected.** Each deposit record and each tag has exactly one owner, so an edit
  changes only that weapon's backpack.
- **Resupply refills the deposit.** A supply pickup adds `refill_amount` (Maxigun 500). The ammo-box
  amount is half of that (250), applied by game code; it is not a stored value, so it follows
  `refill_amount` and cannot be authored separately.

| Weapon | Backpack | Capacity | Start | From supply | Wiki (capacity / supply / ammo box) |
| --- | --- | --- | --- | --- | --- |
| M-1000 Maxigun | `M-1000 Maxigun Backpack` | 1000 | 1000 | 500 | 1000 / 500 / 250 |
| B/FLAM-80 Cremator | `B/FLAM-80 Cremator Backpack` | 500 | 500 | 250 | 500 / 250 / 125 |
| GL-28 Belt-Fed Grenade Launcher | `GL-28 Belt-Fed Grenade Launcher Backpack` | 120 | 120 | 60 | 120 / 60 / 30 |

## API

- `hd2.support_weapon(name):backpack()`: the backpack that stores the weapon's ammunition. It raises
  an error for weapons whose ammunition is not backpack-owned.
- `hd2.backpack(name):weapon()`: the reverse link. `hd2.backpack(name):describe().feeds` names the
  weapon.
- **Fields.** `hd2.fields.deposit.capacity` (1 to 1023), `hd2.fields.deposit.start_amount`
  (0 to 1023) and `hd2.fields.deposit.refill_amount` (0 to 1023). All three are integers. See
  [The 1023 limit](#the-1023-limit).
- **Acknowledgement.** `allow_unverified_effect` is required: ownership is proven, but no edit has been
  confirmed in game yet. `allow_shared` is never needed.
- **Consistency.** Keep `start_amount` no greater than `capacity`.
- **Re-proof.** Every write re-proves the whole chain: the rack still delivers the reviewed weapon and
  backpack, the weapon still draws from the Backpack slot through the same tag, and the backpack
  still carries that tag.

## GUI metadata

`sdk/BackpackAuthoringCapabilities.json` publishes each weapon-fed backpack with:

- `feeds`: the support weapon, its semantic ID, and the chain.
- `ammo`: capacity, start, refill and the derived ammo-box value, plus the wiki fingerprints.
- a `backpack_ammo` setting group.

Each field carries `uiGroup: "backpack_ammo"`, a display name, `min`/`max`, and the acknowledgement.
`sdk/SupportWeaponAuthoringCapabilities.json` links each weapon to its backpack through
`ammoBackpack` (backpack name, semantic ID, accessor, baseline). A GUI can therefore show one page per
weapon: call-in, weapon, then backpack ammo.

## Team-reload backpacks (0.30.4, offline only)

The GR-8 Recoilless Rifle, AC-8 Autocannon, FAF-14 Spear, RL-77 Airburst Rocket Launcher and StA-X3 W.A.S.P.
Launcher are delivered with a backpack whose `DepositComponent` names the weapon in `assisted_reload_weapon_path`
(+136). That deposit is what the wearer reloads from once the weapon's own spares are spent, and what a teammate's
assisted reload always uses. One unit is one reload (a full magazine; on the AC-8 a 5-round clip). Research:
`research/team-reload-ammo-F5FEE03DCFDB.json`.

```lua
-- GR-8: the backpack holds 12 rockets and gets 6 per resupply (5 / full / 3 natively)
local backpack=hd2.support_weapon('GR-8 Recoilless Rifle'):backpack()
hd2.ensure({transaction={id='gr8-backpack',target=backpack,allow_unverified_effect=true,changes={
    {field=hd2.fields.deposit.capacity,expect=5,value=12},
    {field=hd2.fields.deposit.refill_amount,expect=3,value=6}}}})
```

| Weapon | Backpack | Capacity | Start | From supply | Wiki (spare / supply) |
| --- | --- | --- | --- | --- | --- |
| GR-8 Recoilless Rifle | `GR-8 Recoilless Rifle Backpack` | 5 | -1 (full) | 3 | 5 / 3 |
| AC-8 Autocannon | `AC-8 Autocannon Backpack` | 10 | -1 (full) | 5 | supply 25 rounds = 5 clips |
| FAF-14 Spear | `FAF-14 Spear Backpack` | 4 | -1 (full) | 2 | 4 / 2 |
| RL-77 Airburst Rocket Launcher | `RL-77 Airburst Rocket Launcher Backpack` | 5 | -1 (full) | 3 | 5 / 3 |
| StA-X3 W.A.S.P. Launcher | `StA-X3 W.A.S.P. Launcher Backpack` | 5 | -1 (full) | 3 | 5 / 3 |

- **Fields:** `deposit.capacity` (1 to 1023), `deposit.start_amount` (-1 to 1023; **-1 = full**, the native value:
  the live amount starts at the capacity, so raising only the capacity also raises the call-in amount), and
  `deposit.refill_amount` (0 to 1023). The [1023 limit](#the-1023-limit) applies to every deposit.
- **Acknowledgement:** `allow_unverified_effect` (the readers are traced in game code; not yet shown in game).
- **Re-proof:** every write re-proves that the call-in rack still delivers the weapon with this backpack and that the
  deposit still names the weapon.
- **Visuals:** the backpack shows up to its own number of rocket/clip models (5 on the GR-8 pack); above that it
  shows all of them until the amount drops below.
- **Lifecycle:** the start applies to backpacks called in after the write; capacity and refill are read again on every
  resupply. A teammate's assisted reload costs one unit, like the wearer's own.
- `hd2.support_weapon(name):backpack()` returns the backpack; `hd2.backpack(name):describe().feeds.relationship` is
  `team_reload` (`backpack_ammo` for the three weapon-fed backpacks above).

The weapon itself can also carry spares now (magazine weapons): see
[Team-reload weapons](support-weapon-api.md#team-reload-weapons-0304-offline-only).

## Not covered

- **Live remaining ammunition:** this is per-mission instance state, not a definition field.
- **The C4 pack:** its deposit refills its detonator the same way (`assisted_reload_weapon_path`), but the detonator
  is not a catalogued support weapon; it stays read-only.
- **The assisted-reload record:** each reload from the backpack costs its +20 (1 on every weapon); the member's name
  is not proven, so it is not offered.
- **The Cremator's weapon-side fields:** they remain blocked, because the weapon still resolves to two
  native roots. Its backpack is reached only through its own call-in rack, so its ammunition is
  authorable.

## The 1023 limit

A live test set the Maxigun backpack to 3000 / 3000 / 1500. A new call-in showed 3000 rounds; after a few shots
the count snapped to about 1017, and a resupply refilled only to about 1024, while the HUD kept 3000 as its
maximum. `scripts/research_deposit_limits.py` (output `research/deposit-limits-F5FEE03DCFDB.json`) traces why,
from the game.dll and executable images and all three retained snapshots:

1. **The live count.** Each deposit's current amount is a 32-bit value in game.dll's DepositComponent manager. At
   creation it is set from `start_amount` (or `capacity` when the start is negative). That is why a new call-in
   shows 3000.
2. **Every change is a network write.** Firing subtracts from the count and queues a write of the network field
   `remaining`, passing a pointer to the live count. Resupply sets `min(count + refill, capacity)` (the only clamp
   in game code, against the definition's capacity) and queues the same write.
3. **The engine validates the field in place.** When the owning peer flushes the write, the engine's field
   validator runs with clamping on. `remaining` has the field type `deposit_value` (integer, 10 bits, minimum 0),
   so its range is 0..1023. An out-of-range value is clamped **and written back through the pointer**: the
   owner's own live count becomes 1023. This happens in solo play too.
4. **The HUD maximum is `start_amount`** (or `capacity` when the start is negative), which is why it showed 3000.

So 3000 → first shot 2999 → clamped to 1023 → six more shots → 1017, and resupply `min(1017 + 1500, 3000)` → 1023.
Nothing in game code compares against 1023 or 1024; the limit is the engine's network schema (29 object types
carry `remaining`, all with `deposit_value`). No definition field raises it. The only place it is stored is the
engine's loaded network type table, which also sets the wire width every peer uses, so Runtime never writes it.

What this means:

- Runtime bounds `deposit.capacity`, `deposit.start_amount` and `deposit.refill_amount` to 1023 and refuses larger
  values with the reason, instead of letting a write land that the game silently caps.
- Every deposit has this limit: the Cremator (500) and GL-28 (120) have more headroom than the Maxigun (1000).
- A `start_amount` below `capacity` lowers the HUD's maximum, not the real capacity.
- The observed "1024" is not reconciled: the code gives 1023. The diagnostic's 1023 test shows whether the HUD
  reads one higher at full.
- Live status: `backpack_deposit_ammo` is `live_partial` in `sdk/LiveEvidenceCatalog.json`. Capacities up to 1023
  are not yet gameplay-proven.
