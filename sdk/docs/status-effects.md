# Status effects on weapon attacks

Since the coverage pass, any mapped player, support or mounted-weapon attack can change which status its hits
apply, or gain one, through typed status references. The research is `scripts/research_status_effects.py` →
`research/status-effects-F5FEE03DCFDB.json`. The public catalog is `sdk/StatusEffectCatalog.json`.

## Native model

A status is applied by the **damage definition** (DamageInfo) that a hit uses. It is not a property of the weapon or
the projectile.

- Every DamageInfo row has four inline status slots at +44+8n. Each slot is a StatusEffectType (u32) followed by a
  strength (f32).
- An unused slot has type 0. Used slots are packed from slot 1: none of the 649 live rows has a gap.
- 500 rows use no slot, 127 use one, 18 use two and 4 use three. None uses all four.
- Every hit that reaches a DamageInfo row applies its statuses:
  - a projectile's direct hit;
  - each explosion;
  - each beam, arc or spray tick;
  - each melee strike.
- A projectile's direct-hit damage and its explosion damage are separate rows, so they have separate slots.
- Several statuses per row are normal. For example, the flamethrowers apply `fire`, `flamer_slowed` and
  `fire_panic` from one row.
- The status definitions are global (StatusEffectSettings, one 152-byte row per status):
  - `status.duration` (+40), which is already authorable;
  - the status's own tick DamageInfo (+44);
  - a string the game stores with the row: its name ("Fire", "Stun Medium", …).

The catalog takes each status's semantic identity from that stored name. The numeric type is not identity: this
build stores "Stun Small" at 37, while filediver's older enum lists it at 36.

## Catalog

The catalog has 71 statuses. A status is **attachable** only when a player-side attack Runtime maps already applies
it through a DamageInfo slot. That proves both the slot mechanism and the status's behaviour on player attacks.
These 11 are attachable:

| Status | Duration | Applied today by (examples) |
| --- | --- | --- |
| `fire` | 3 s | AR-2 Coyote, flamethrowers, Breaker Incendiary, napalm, Orbital Laser |
| `fire_panic` | 1 s | flamethrowers, Crisper, Meltagun |
| `burning_heavy` | 1 s | napalm Eagle / barrage, EAT-700 |
| `flamer_slowed` | 0.5 s | flamethrowers |
| `stun_small` | 1.5 s | Arc Thrower, Blitzer, Tesla Tower |
| `stun_medium` | 3 s | AR-32 Pacifier, SMG-72 Pummeler, EMS mortar and strike |
| `stun_large` | 5 s | Stun Lance, Stun Baton, SG-20 Halt, stun grenade |
| `gas`, `gas_confusion` | 6 s / 5 s | gas grenade, gas mines / mortar / strikes, Re-Educator |
| `gas_2`, `gas_confusion_2` | 10 s / 9 s | TX-41 Sterilizer |

Everything else is catalogued read-only:
- `electric`, acid, bleed and stun massive (only enemies, hazards or other systems apply them);
- stims, terrain and weather;
- character-state statuses.

## API

Each damage object has `damage.status_<k>_type` for every used slot, plus `damage.status_<k>_type` and
`damage.status_<k>_strength` for its first empty slot. Explosion damage objects have the same fields as
`explosion.damage.status_<k>_*`.

```lua
local bullets=hd2.support_weapon('M-1000 Maxigun'):attack('primary'):projectile()
hd2.ensure({plan={id='maxigun-stun',operations={
    {id='stun',target=bullets,allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.damage.status_1_type,expect='none',value='stun_medium'},
        {field=hd2.fields.damage.status_1_strength,expect=0,value=2}}},
}}})
```

- **Values.** A status reference takes catalog semantic IDs, or `'none'`. Only attachable statuses are accepted,
  plus the slot's current status.
- **Clearing.** `'none'` clears only the last used slot, so the slots stay packed.
- **Strength.** Strengths range from 0 to 1000. Use the strength an existing user applies; the catalog lists the
  observed range for each status.
- **Duration.** Editing a status's definition (`status.duration`) is a different operation from choosing which
  status an attack applies. Duration edits are shared by every attack that applies the status.
- **Acknowledgements.**
  - Every status slot write needs `allow_unverified_effect`: the mechanism is native, but a status on an attack
    that does not already use it is not gameplay-proven.
  - Rows shared by several weapons also need `allow_shared`, like every other settings write.

## Guards

At write time the runtime re-proves:
- the damage row's identity and ownership chain;
- that the earlier slots are still used (and, when clearing, that the later slots are empty);
- that the live status table still stores the catalogued name for both the current and the desired status.

A renumbered or edited status table therefore can never be written through a stale catalog.

## Migration

A status slot migrates only when both builds' status tables are available and identical, row for row, with
pointers masked.
- **Same build:** every status field is EXACT.
- **Previous build (datalibrary only, no status table):** all 197 status type slots are UNCHECKED and become
  read-only, with no stale writes.
- **Changed status table:** the fields are BLOCKED until the research is re-run and the catalog regenerated.

## Not supported

- A fifth status: the slot array is fixed at four, and growing it would need object cloning.
- Stratagem, throwable and booster attacks: their DamageInfo rows have the same slots, but their write domains do not
  yet accept status references.
- Enemy-only statuses on player weapons (acid, electric).

## Live tests (built only; not yet gameplay-confirmed)

- `MaxigunStun`: Maxigun bullets apply `stun_medium`, strength 2 (the Pacifier/Pummeler value).
- `LiberatorFireStatus`: Liberator bullets apply `fire`, strength 2 (the Coyote value). The row is shared with
  the Liberator Carbine and StA-52.

An explosion-status swap was not built as a separate test: explosions apply statuses through the same slots of their
own DamageInfo row, so there is no distinct mechanism to test.
