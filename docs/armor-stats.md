# Armor stats: rating, speed, stamina (development)

`hd2.armor_stats` reads and changes where a Helldiver armor's ARMOR RATING, SPEED and STAMINA REGEN come from. No armor
stores its own numbers. Each armor piece of a kit has a **weight** (light, medium or heavy), and the weight indexes three
per-weight tables in game.dll. The writable levers are:
- a kit's piece weights, for every player wearing that kit;
- the local player's own armor bonus and stamina factor.

The tables themselves and the damage curve are read-only (see [Why the class tables are read-only](#why-the-class-tables-are-read-only)).

```lua
local kit = hd2.armor_stats.kit('FS-37 Ravager')     -- or by id: 0x1F9BFA78, '1F9BFA78'
local now = kit:describe()                           -- pieces per slot, the stats they give now
hd2.mod():log(('rating %g, speed %g, stamina regen %g'):format(now.stats.rating, now.stats.speed,
    now.stats.stamina_regen))

-- Every armor piece of the kit heavy (rating 150 from the next hit; speed / stamina from the next armor apply).
hd2.transaction({id = 'ravager-heavy', target = kit, allow_shared = true, allow_unverified_effect = true,
    changes = kit:changes('heavy')})
-- One slot only, kept in place while the mod runs:
hd2.ensure({patch = {id = 'ravager-torso', target = kit, field = hd2.fields.armor_kit.piece_weight_torso,
    expect = 'light', value = 'medium', allow_shared = true, allow_unverified_effect = true}})

hd2.armor_stats.class('heavy'):describe()            -- the heavy table values now (read-only)
hd2.armor_stats.damage_curve():describe()            -- damage multiplier by armor value (read-only)

local me = hd2.armor_stats.player()                  -- the local player's own avatar (solo)
local r = me:set({stamina_factor = 0.5, armor_bonus = 1, allow_unverified_effect = true})
if r.status == 'refused' then hd2.mod():log(r.code .. ': ' .. r.reason) end
me:restore()                                         -- the game's own values again
```

**Status: development. Not live-tested.** Every write needs `allow_unverified_effect = true`. A kit write also needs
`allow_shared = true`, because every player wearing that kit reads its pieces. The live test is
`proof/ArmorStatProbe`. Research: `research/armor-stats-F5FEE03DCFDB.json` and
`research/docs/armor-stats-F5FEE03DCFDB.md`, with kit names from `research/armor-names-F5FEE03DCFDB.json`. The
generated domain is `domains/armor_stats.lua` (`scripts/generate_armor_stats.py`).

## Where the numbers come from

| Table (game.dll) | light / medium / heavy | Read by |
| --- | --- | --- |
| armor `0x21CB160` | 0, 1, 2 | every hit (0x12A15E0), the armory |
| speed `0x2160678` | 1.1, 1.0, 0.9 | the armor apply (0x877AB0), the armory |
| stamina `0x21C6F78` | 0.75, 1.0, 1.5 | the armor apply (0x877AB0), the armory |

- **Armor value A.** The mean of `armor[weight]` over the kit's armor pieces in slots 2 to 9, without the hips (torso,
  legs, arms, shoulders; 5 to 7 pieces). The kit passive is then applied: Extra Padding adds 1.0; Unflinching,
  Supplemental Adrenaline and Blunt-Force Mitigation add 0.5; Concussive Padding (Reinforced) adds 0.6.
  - A is read on **every hit** on the player. The avatar damage multiplier is `curve(A)`, keyed on A alone (the
    attack's penetration does not enter it):

    | A | -1 | 0 (light) | 1 (medium) | 2 (heavy) | 3 (heavy + Extra Padding) |
    | --- | --- | --- | --- | --- | --- |
    | damage x | 1.66 | 1.25 | 1.0 | 0.75 | 0.65 |

    It is linear between the points, 0.65 above 3 and 1.0 below -1.
- **Speed factor S and stamina factor F.** The mean of `speed[weight]` / `stamina[weight]` over **every** armor piece
  of the kit (hips and the kit's cape-slot piece included). The game computes them when it **applies** the kit
  (0x877AB0, at a kit change and from 0x81BE70): F goes to the avatar, S to its locomotion speed slot 3.
  - F scales stamina **drain and regen** alike, and the jump, dive, climb and slide costs. "Stamina regen 125" on
    light armor (F 0.75) is a display transform, not a 1.25x regen.
  - **How the game consumes S is unproven.** S is written into the locomotion record and smoothed there, but no
    reader of that product was found statically.
- **What the armory shows.** RATING = 100 + (A - 1) x 50 = 50 + 50 x A. SPEED = 500 x S. STAMINA REGEN = 100 x (2 - F).
  The armory's own averager skips the hips and the cape piece, so for 43 kits the gameplay factors differ slightly from
  the displayed ones (heavy 0.9 becomes 0.911). `describe()` gives both (`speed_factor` / `stamina_factor` are the
  gameplay values, `display_speed_factor` / `display_stamina_factor` the armory's).
- **The class label** (Light / Medium / Heavy in the armory) is the torso piece's weight.

## The API

| Call | Returns |
| --- | --- |
| `hd2.armor_stats.kit(id or name)` | A kit target (`{resource = 'armor_kit', armor_kit = '1F9BFA78'}`). By id (a number or 8 hex digits) or by game name in any case. A name several kits share (for example `B-01 Tactical`, 9 kits) raises `AMBIGUOUS_ARMOR_KIT` with their ids; an unknown one raises `UNKNOWN_ARMOR_KIT`. |
| `hd2.armor_stats.kits()` | Every armor kit of the build (135): `{id, name, passive, passive_name, class, vanilla = {rating, speed, stamina, armor_value, speed_factor, stamina_factor, damage_multiplier}}`. Offline. |
| `hd2.armor_stats.class('light' / 'medium' / 'heavy')` | A weight class target (read-only). `hd2.armor_class` is the same function. Unknown: `UNKNOWN_ARMOR_CLASS`. |
| `hd2.armor_stats.damage_curve()` | The damage curve target (read-only). |
| `hd2.armor_stats.player()` | The local player's avatar members (development, solo). |

### Kit targets

- `kit:describe()` returns:
  - `pieces`: `{[slot] = {weight, weights, count}}`, the live pieces per slot (`count` bodies have one);
  - `stats` = `{rating, speed, stamina_regen, armor_value, armor_base, damage_multiplier, speed_factor, stamina_factor,
    display_speed_factor, display_stamina_factor, class}`, for the stocky body, with the tables as they are now;
  - `slim_stats` only when the slim body differs;
  - `passive` = `{id, name, armor}`, the passive's armor rows;
  - `vanilla` (the research's numbers), `source` (`'live'` when the game is readable, else `'research'` with a
    `reason`), `scope`, `lifecycle` and `fields`.
- `kit:fields()` lists the piece weight fields, one per slot the kit has an armor piece in.
- `kit:changes(weight, slots)` returns the change list `{{field, expect, value}}` that puts every armor piece (or the
  slots given) at a weight, for `hd2.transaction` or `hd2.ensure`. It adds no acknowledgement.
- `kit:preview({torso = 'heavy', ...})` gives the stats with those weights, without writing.

**Fields.** `armor_kit.piece_weight.<slot>` (`hd2.fields.armor_kit.piece_weight_torso`, ...). The slots are `cape`,
`torso`, `hips`, `left_leg`, `right_leg`, `left_arm`, `right_arm`, `left_shoulder` and `right_shoulder`. The slot
names are the filediver labels; the slot numbers (1 to 9) are what the game reads.
- **Value.** `'light'`, `'medium'` or `'heavy'` (or 0, 1, 2). `expect` is the kit's vanilla weight in that slot
  (`kit:fields()[i].currentDefault`).
- **What is written.** The weight of the kit's armor piece in that slot, in **every body** (stocky, slim and the
  any-body pieces) that has one: one guarded 4-byte write per piece.
- **When it takes effect.**
  - The armor rating: the **next hit**, for every player wearing the kit on this machine. The armory follows at once.
  - Speed and stamina: the next time the game applies the kit (a respawn or an armor change).
  - The torso slot also changes the armory class label.
- **Steps.** Changing one piece moves A by 1/n, where n is the number of counted pieces (5 to 7). Arbitrary values such
  as rating 137 on one kit are not possible this way: use the per-player armor bonus.
- **The log.** Every applied write logs a note with the stats the kit now gives (the stocky body).

```lua
-- RS-100 Sanctioner's torso heavy: rating 50 -> 70 (A 0 -> 0.4, damage x1.25 -> x1.15), class Light -> Heavy.
hd2.patch({id = 'sanctioner-torso', target = hd2.armor_stats.kit('4DD749C6'),
    field = hd2.fields.armor_kit.piece_weight_torso, expect = 'light', value = 'heavy',
    allow_shared = true, allow_unverified_effect = true})
```

### Class and damage curve targets

- `hd2.armor_stats.class(name):describe()` returns:
  - `rating` = `{value (A), display (50 + 50 x A), vanilla}`;
  - `speed` = `{value, display (500 x factor), vanilla}`;
  - `stamina` = `{value, display (100 x (2 - F)), vanilla}`;
  - `damage_multiplier`, the curve at that armor value;
  - `source`, `editable = false` and the reason.
- `hd2.armor_stats.damage_curve():describe()` returns `{points = {{armor_value, damage}}, vanilla, source}`.
- **Fields.** `armor_class.rating` (A units, reviewed range -1 to 4), `armor_class.speed` (0.5 to 1.5),
  `armor_class.stamina` (0.25 to 2), and `armor_damage_curve.at_minus_1`, `at_0`, `at_1`, `at_2`, `at_3` (0 to 4).
  - A request is validated in full: `allow_shared`, `allow_unverified_effect`, the vanilla `expect`, the range.
  - Then it is refused with `WRITE_REFUSED_IMAGE_PAGE`. Nothing is read or written.

### The local player

`hd2.armor_stats.player()`:
- `:describe()` returns `{entity, avatar, slot, armor_bonus, stamina_factor, armor_kit, derived, effective_armor_value,
  overridden}`, or `nil, code, reason`. `derived` is what the worn kit gives now (the same shape as a kit's `stats`).
- `:set({armor_bonus, stamina_factor, allow_unverified_effect = true})` writes one or both members.
- `:restore()` puts the game's own values back.

A refusal never raises: it returns `{status = 'refused', code, reason}`.

| Member | What it does | Range | Lasts |
| --- | --- | --- | --- |
| `armor_bonus` (avatar manager +0x546AC4 + slot x 0x1B8) | Added to the armor value of every hit on this avatar; the sum is clamped to -1..3 when the bonus is not 0. | -1 to 3 | Live. A status effect writes -1 on apply and 0 on removal. |
| `stamina_factor` (avatar manager +0x53E900 + slot x 0x1238) | The armor's F: scales stamina drain and regen and the action costs. | 0.1 to 3 | Live until the game next applies the armor (a respawn or an armor change), which writes the kit's F again. Call `set` again then. |

- **Which avatar.** The local player's avatar comes from the game's player list. Its avatar manager slot comes from the
  game's own entity -> slot map (avatar manager +0xF8), the map the stamina writer, the hit's armor reader and the armor
  modifier setter use. The research pins both members by their readers. This feature adds 12 pins for the map lookup
  and the 0x1B8 stride; `scripts/validate_armor_stats_snapshot.py` proves them in all seven snapshots.
- **What a member must hold before a write.** The game's own value, or the value this Runtime last wrote there.
  - Armor bonus: 0 or -1.
  - Stamina factor: the F the worn kit's pieces give now, or the F its vanilla pieces give (the avatar still holds that
    one after a kit write, until the next armor apply).
  - Anything else is refused with `UNEXPECTED_STATE`; for example, a status effect may have changed it.
- **Scope.** Solo only: with several players, `set` is refused with `NOT_SOLO`. Which machine evaluates a hit on a
  remote player is not proven. `restore` still works.
- **Codes.** `ACKNOWLEDGEMENT_REQUIRED`, `OUT_OF_RANGE`, `INVALID_OPTION`, `NO_PLAYER`, `NO_LOCAL_AVATAR`,
  `NO_AVATAR_SLOT`, `UNEXPECTED_STATE`, `NOT_SOLO`, `NOT_PRIVATE`, `UNAVAILABLE`, `UNSUPPORTED_BUILD`,
  `GUARD_REJECTED`.

## Why the class tables are read-only

The research reads the three tables and the curve from game.dll's read-only initialized-data section (PE flags
0x40000040). At run time, the game's loader leaves that whole range **PAGE_EXECUTE_READWRITE** (0x40): game.dll
`+0x2112000`, 0x528000 bytes, in all seven retained snapshots (`validation/armor-stats-snapshot.json`, `imagePages`).

The guarded write accepts a target page only if it is READONLY (opened to READWRITE for the write, then restored) or
READWRITE, never copy-on-write and never executable (`core/page_protection.lua`, `docs/guarded-patch.md`). That rule
is not relaxed here:
- the snapshot validation sends a guarded transaction directly at the heavy armor entry;
- it is REJECTED before any page is opened (`failed=protection`), with nothing written.

So `armor_class.*` and `armor_damage_curve.*` are validated and then refused.

**Writing them needs the user's decision.** A narrow exception would accept an EXECUTE_READWRITE page as a data
target only for these exact 12-byte and 40-byte extents, with:
- the build fingerprint;
- the research's 177 pins;
- the vanilla bytes as expected;
- protection never changed.

No such exception exists today. The proof therefore exercises the writable levers instead.

## Guards (kit writes)

Before any memory is touched, every kit write proves:
- **The build.** It is the one the research covers (`ARMOR_BUILD_CHANGED`).
- **The code.** Every instruction pin of the research, the 12 slot-map pins and the consumers' constants, read from
  game.dll's image.
- **The kit.** The customization manager pointer, then the kit table's entry at the kit's research index. That entry's
  row must carry the kit's id (`ARMOR_KIT_MOVED` otherwise), the armor type, its passive and its body count.
- **The pieces.** Its bodies and each body's piece array. Each array is a transaction context.
- **The current bytes.** Every target piece holds the reviewed vanilla weight or the desired one. Anything else is a
  `CONFLICT` naming who holds the bytes.

The pieces are ordinary private read-write memory, so no page protection is changed. Each piece is read back, and every
other byte of the captured arrays must be unchanged. An ensure restores the vanilla weights when it is disabled.

## Validation

- `scripts/validate_armor_stats_snapshot.py` -> `validation/armor-stats-snapshot.json`, on all seven retained
  snapshots, on a copy-on-write overlay:
  - the pins and the vanilla tables;
  - the image pages' protection and the refused direct transaction;
  - every kit at its index with its vanilla pieces (a guarded no-op each). The Lua replicas of the averagers give the
    research's numbers for all 135 kits;
  - round trips: Sanctioner torso heavy (rating 70, class Heavy), Ravager all heavy (rating 150). Exact bytes, the
    note and the live describe follow, and the inverse restores;
  - the local player: slot 0, armor bonus 0 and stamina factor 0.75 = the Sanctioner's F. `set` and `restore` give the
    exact bytes. A third-party value is refused;
  - every rejection listed under Guards.
- `tests/test_armor_stats.py`: the domain against the research, the targets and descriptors, every refusal, the
  per-player write on a synthetic world (solo, restore, third-party values), the wiring, and the probe.
- Packaged scenario `proof-armor-stats`, read-only, on the reference snapshot: see `proof/ArmorStatProbe`.

## Not live-tested

Nothing here has been tried in game. `proof/ArmorStatProbe` 0.1.0 is the live test:
- **F9** cycles the local player's stamina factor: 0.5 (sprint much longer), then 1.5 (much shorter), then the
  game's own value.
- **Ctrl+F9** cycles the worn armor kit's pieces: all heavy (damage x0.75), all light (x1.25), then vanilla. Every hit
  on the local player logs the health lost.
