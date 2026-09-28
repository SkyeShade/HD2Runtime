# Backpack ammunition

Three support weapons carry no ammunition of their own: the M-1000 Maxigun, the B/FLAM-80 Cremator and
the GL-28 Belt-Fed Grenade Launcher. Their ammunition is stored in the backpack delivered with them, so
the runtime authors it on the backpack.

```lua
-- M-1000 Maxigun: 1000/1000/500 -> 2000/2000/1000 (see examples/projects/MaxigunBackpackAmmo)
local backpack=hd2.support_weapon('M-1000 Maxigun'):backpack()
hd2.ensure({transaction={id='maxigun-backpack-ammo',target=backpack,allow_unverified_effect=true,changes={
    {field=hd2.fields.deposit.capacity,expect=1000,value=2000},
    {field=hd2.fields.deposit.start_amount,expect=1000,value=2000},
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
- **Fields.** `hd2.fields.deposit.capacity` (1 to 100000), `hd2.fields.deposit.start_amount`
  (0 to 100000) and `hd2.fields.deposit.refill_amount` (0 to 100000). All three are integers.
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

## Not covered

- **Live remaining ammunition:** this is per-mission instance state, not a definition field.
- **Team-reload backpacks:** the recoilless rifle, autocannon, Spear and airburst launcher backpacks use
  deposits too, but through `assisted_reload_weapon_path`. Their weapons also own magazines, and their
  start amount is the `-1` sentinel. The C4 pack's deposit refills its detonator the same way. These are
  a different mechanism and stay read-only.
- **The Cremator's weapon-side fields:** they remain blocked, because the weapon still resolves to two
  native roots. Its backpack is reached only through its own call-in rack, so its ammunition is
  authorable.
