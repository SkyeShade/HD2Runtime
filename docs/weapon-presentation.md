# Weapon presentation: armory traits

When a mod changes a weapon's gameplay, the armory may still describe the vanilla weapon. The trait labels it shows
("LIGHT ARMOR PENETRATING", "ONE HANDED", "EXPLOSIVE", ...) are presentation data of their own, and Runtime edits them
separately from gameplay.

```lua
-- AR-23C Liberator Concussive: the menu says MEDIUM ARMOR PENETRATING (examples/projects/WeaponPresentationTest).
-- Live-proven for the Concussive's light, medium and heavy labels: no acknowledgement.
local concussive=hd2.weapon('AR-23C Liberator Concussive')
hd2.ensure({patch={id='concussive-label',target=concussive,field=hd2.fields.presentation.armor_penetration,
    expect='light',value='medium'}})
```

The weapon-function menu's mode labels and icons (GAS / STUN, FLAK, HE, ...) are a different native member, on the
fired projectile: see [mode labels and icons](weapon-feeds.md#mode-labels-and-icons).

## Native model

Proven on build F5FEE03DCFDB (`scripts/research_weapon_presentation.py`, `research/weapon-presentation-F5FEE03DCFDB.json`):

- **Traits are stored.** Every armory item has a `LoadoutEntryComponent` (193 records, each owned by one item):
  `{+0 id, +4 LoadoutItemType, +8, +12 u32[5]}`. The five u32 at +12 are its trait tags: localization string IDs,
  0 = empty slot.
- **The armory reads exactly those.** The trait view-model builder (game.dll 0x14E4A20) looks the item up in the
  LoadoutEntry table and, for each of the five slots with a non-zero ID, creates a trait whose `Text` is the localized
  string of that ID. The armory template binds `SelectedItem.WeaponData.Traits`
  (`ObservableCollection<testament.WeaponTrait>`).
- **Nothing derives a label from gameplay.** No reader of DamageInfo armor penetration chooses a label; the
  Concussive shows LIGHT ARMOR PENETRATING because its record holds that string ID. So Runtime never changes a label
  when AP changes, and never changes AP when a label changes.
- **Stat rows are computed.** The stat builder (0x14E41F0) picks WeaponStatType rows (damage, capacity, recoil, fire
  rate, ...) by output family and computes them from the weapon's component data and customization when the menu
  builds the item. No struct in the type library stores a WeaponStatType value: there is no display value to edit.
  They follow gameplay edits of the data they read (not live-verified).
- **Refresh.** The trait builder runs inside the item view-model builder (0x14E7430), which menu presenters run when
  a menu is entered. An open menu keeps the labels it built: close and reopen the armory or loadout screen.
- **Strings.** The labels are the game's own localized strings (15 languages in the loaded tables; 0x03F97B57 is
  en-US). Runtime selects among existing string IDs only; it never rewrites text.

## Fields

| Field | Value |
| --- | --- |
| `hd2.fields.presentation.armor_penetration` | `'none'`, `'light'`, `'medium'`, `'heavy'`, `'light_anti_tank'`, `'anti_tank'` |
| `hd2.fields.presentation.traits` | ordered list of up to five trait IDs from `sdk/WeaponPresentationCapabilities.json` |

| Choice | Label shown |
| --- | --- |
| `light` | LIGHT ARMOR PENETRATING |
| `medium` | MEDIUM ARMOR PENETRATING |
| `heavy` | HEAVY ARMOR PENETRATING |
| `light_anti_tank` | LIGHT ANTI-TANK |
| `anti_tank` | ANTI-TANK |
| `none` | no penetration label |

- `armor_penetration` replaces the weapon's single penetration label in place, adds one in the first empty slot, or
  (`none`) removes it and keeps the other tags packed. The other traits never change.
- `traits` writes the whole list (24 named traits: one handed, explosive, incendiary, stun, heat, beam, rounds reload,
  stationary reload, team weapon, guided, ...).
- Both are the same five slots, so they are never combined in one plan.
- Weapons that show several penetration labels (the Halt: one per feed; the LAS-17 Double-Edge Sickle: one per heat
  level; the P-33) edit them with `traits`, not the single selector.
- **Acknowledgement.** `allow_unverified_effect`, except the live-proven scope: the AR-23C Liberator Concussive's
  `armor_penetration` set to light, medium or heavy (2026-09-30: the armory said HEAVY while the bullets stayed AP 3;
  reopening the menu was enough, no restart). Its other labels, every other weapon and `traits` keep it.
- **Scope.** Weapon-local (every LoadoutEntry record has one owner).
- **Coverage.** 103 weapons have writable traits and 100 a writable penetration label. Two tags (EAT-411, EAT-700)
  have no string in any loaded table and stay read-only.

`weapon:presentation()` (player and support weapons) returns the current traits with labels, the penetration label,
the choices, writability and reasons.

## Validation

- `scripts/validate_weapon_modes_snapshot.py`: every writable weapon's label and traits apply as no-ops, change
  exactly one slot (replace or add) or remove the label, read back and roll back exactly, never touch the next
  LoadoutEntry record, and a third-party slot value is a CONFLICT; unknown, duplicate and sixth traits and a stale
  LoadoutEntry index row are refused. It pins the Concussive write (slot 1: LIGHT -> MEDIUM ARMOR PENETRATING, 4 bytes).
- The packaged-runtime scenario `example-weapon-presentation-test` runs the live test from the built ZIP: the label
  and the gameplay AP are separate operations, and neither writes the other's bytes.
