# Custom stratagems: the development API (HD2Runtime 0.30.0-dev)

`hd2.custom_stratagem`, the `hd2.pelican.spawn` gun options and `hd2.ownership` turn the live-proven custom stratagem
mechanisms into one API. A mod states what its stratagem is and does. The Runtime does the rest:

- the selection;
- the carrier;
- the presentation and code;
- the beacon;
- the cooldown;
- every guarded write;
- every restore.

**Status: development; the host's calls.** This API is exported for development and testing. It is not part of a
release contract yet. With several players everything runs in an EXPERIMENTAL scope (see "Several players"): the
host's calls, and a client's own support deliveries (live-proven with the Gas EAT, r3), native orbitals and Pelican
requests (r4, not live-tested). The rest of multiplayer is unproven.

**Versions.** The custom stratagem system is the HD2Runtime 0.30 development line (`VERSION` = `0.30.0-dev`; no release
is tagged).
- `hd2.version_label` is the full version (`0.30.0-dev`), as the startup line and the artifact names show it.
- `hd2.version` is the compatibility version (`0.30.0`, MAJOR.MINOR.PATCH): mods built with an SDK before 0.28 parse
  nothing else.
- A mod using this API requires `"min_version": "0.30.0-dev"` (`hd2runtime.json`). The custom stratagem API is not
  in 0.28.0.

**Builders.** A mod's custom stratagems can also be a data file, `custom_stratagems.json`, that the SDK validates and
compiles into `src/addon.lua`. The machine-readable schema is `sdk/CustomStratagemSchema.json`. See
[custom-stratagem-builder.md](custom-stratagem-builder.md). Lua callbacks stay the escape hatch for what data cannot say.

Examples, each using the public API only:

- `proof/PelicanCasExample`: an autonomous spawned entity;
- `proof/GasBarrageExample`: a projectile payload or barrage;
- `proof/GasEatExample`: a custom support weapon;
- `proof/HmgSentryExample`: a custom sentry (`sentry`);
- `proof/EagleStunRocketPodsExample`: a custom Eagle (`eagle`);
- `proof/EAT17GExample`: an expendable clone (`expendable`, the condensed carrier group, a two-launcher pod).

**The instance-local rule.** Everything a custom stratagem changes, it changes on the exact entities, items and
projectiles its own call spawned: their own copies and records. A shared definition (a weapon type, a projectile row,
an explosion row, an Eagle's data, a rack list) is never written. A vanilla stratagem of the same donor stays vanilla
before, during and after the custom one is used, in the same mission. A change with no reviewed per-instance path is
refused at registration, with the reason; it is never approximated by a global write.

**The carrier rule** is the one exception, and only for records the CARRIER exclusively owns: its StratagemInfo row's
presentation and code, an expendable carrier weapon's type records (the clone) and a carrier's own pod rack (a carrier
pod). They are written at mission start before the carrier can be called (owner count re-proved before every write),
never after a call in that mission, and restored byte for byte aboard the ship before the armory or loadout UI. The
carrier is a vanilla stratagem nobody in the lobby picked, so no vanilla call reads them meanwhile.

## How a custom stratagem works

```
ship:    the player selects it in the Runtime's CUSTOM STRATAGEMS panel (F6 focus, F7 select, Ctrl+F7 undo, or a click)
         -> the game's own pick sound; the native selector moves on to the next empty slot, or, with none left,
            closes as Back closes it
         -> the saved loadout holds a vanilla token (Orbital Precision Strike); nothing of the save, account or
            catalogue changes
         -> a CARRIER is allocated for it from what the account owns (its policy); aboard the ship the carrier is native
mission: (solo host) for each custom stratagem in turn: its assets resident -> the carrier presents as it (name, cased
         name, description, icon, code) -> its cooldown armed -> ONLY its virtual slots become the carrier
         -> READY TO CALL
call:    the carrier's own beacon (its beam colour); in its FIRST update the beacon's delivery is replaced (one guarded
         write of that beacon): 'runtime' = nothing, the mod (or an `orbital` table) delivers; or the donor's own
         vanilla delivery (a support pod, a sentry pod, an Eagle strike)
         -> the exact delivered items, sentry or jet captured and modified (their own records only)
         -> on_called, on_beacon_created, on_beacon_landed, on_activate (and on_delivered) with a call context
ship:    the carrier's presentation and code restored exactly (at the latest when the loadout screen opens)
```

The carrier is a borrowed vanilla stratagem. Its identity (type, stable id) never changes. It is never in the
player's loadout, and two custom stratagems never share one.

## Register

```lua
local hd2=require('mods/skyeshade/hd2runtime')
hd2.custom_stratagem.register({
    id='orbital_gas_barrage',                -- a-z, 0-9, _ (starts with a letter; at most 48); unique across mods
    name='ORBITAL GAS BARRAGE',              -- the HUD's name
    name_cased='Orbital Gas Barrage',        -- the panel's and loadout's
    description='Calls down a barrage of gas shells.',
    icon=hd2.resources.image('orbital_gas_barrage'),  -- the mod's editable images/orbital_gas_barrage.png (256 x 256;
                                             -- masks, or red-and-white art the build converts: docs/custom-images.md)
    code={'up','up','down','down'},          -- 1 to 8 directions
    cooldown=60,                             -- seconds from the call-in's arrival (default: the carrier's own)
    uses=4,                                  -- calls per mission, each player's own (default: unlimited)
    traits={'Orbital','Anti-Tank','Caustic'},-- the panel's ITEM TRAITS after CUSTOM STRATAGEM (default: the family's)
    carrier={beacon='offensive',prefer_families={'orbital'}},
    assets={'Orbital Gas Strike','Orbital 120mm HE Barrage'},
    delivery='runtime',                      -- the default
    on_activate=function(ctx) ctx:barrage({shell='Orbital Gas Strike',pattern='Orbital 120mm HE Barrage'}) end,
})
```

A spec error raises at load time; the mod's mistake is never guessed around. The rules:

- the id is unique;
- the texts are 1–64 characters (descriptions up to 400);
- the icon is one of the mod's images;
- the code is never equal to, the start of, or started by another registered custom stratagem's code;
- one payload family per custom stratagem (`delivery`, `sentry`, `eagle` or `orbital`; none: the mod delivers);
- a support delivery and a sentry need a support carrier; an Eagle needs an offensive one;
- `on_delivered` needs a delivery (support, sentry or Eagle).

Every field is plain data (names, numbers, tables), so a tool can write a custom stratagem without code. The callbacks
stay available as an escape hatch.

### `uses`: calls per mission

`uses` (1 to 100, a whole number) limits how many times each player calls the custom stratagem in a mission. The
Runtime counts the calls from the player's own slot (runtime/slot_cooldown.lua); every call before the last keeps the
definition's `cooldown` (or the carrier's own). The call that uses the last of them ends with the longest cooldown
the guarded cooldown write allows, 3600 s: longer than any mission, so the slot stays unavailable and the HUD shows
it cooling. The log says `USES: n of N` at each call and `SPENT for this mission` at the last.
- **Why not the game's own use counter.** The game's uses are the stratagem row's (+80), applied by the mission host
  when the mission builds its records, and the custom stratagem's carrier is converted later. The fixed-cooldown
  write is this machine's own entry's, the same write the cooldown already makes (live-proven, on clients too).
- **Several players.** Each player's Runtime counts its own calls: every player has their own uses.
- **Not for an Eagle.** Its `eagle.uses` are per rearm.

### `traits`: the panel's ITEM TRAITS

Up to four labels of 1 to 32 characters, shown in upper case after the automatic `CUSTOM STRATAGEM` (a repeat of it, or
of another label, is dropped). Without `traits`, the panel shows the payload family's (`SUPPORT WEAPON`, `ORBITAL`, the
custom model, the round, ...). Presentation only: not part of the registry hash.

### `code`

A code **equal** to a vanilla stratagem's own code is refused at registration, naming that stratagem: the game would
call it instead (live r25: DOWN LEFT DOWN UP RIGHT is the MG-43 Machine Gun's). A weapon variant's own row is its
carrier and takes the custom code, so the variant's own vanilla code is exempt.

It is checked again aboard the ship and at mission start, against every reviewed native code:

- A selectable stratagem with an equal code, a code it starts, or a code that starts it refuses the custom stratagem.
- A mission-only stratagem with such a code is guarded instead: the mission record is checked at mission start and
  watched afterwards. If a related entry appears, that slot returns to its token for the rest of the mission.

### `carrier`: the carrier policy

| field | meaning |
|---|---|
| `group` | The carrier GROUP its carrier is drawn from (see *Carrier groups*). Optional: default its payload family's group. With a group, `beacon` is optional (the group's). |
| `slots` | A pod capacity to ask the group for (1..8; the `support_pod` and `expendable` groups only; at least the pod's items). |
| `beacon` | `'offensive'` (a red beam), `'support'` (a blue beam) or `'any'`: the beacon the player throws. Required unless `group` is given. |
| `prefer_families` | Catalogue families in order of preference: `'orbital'`, `'eagle'`, `'sentry'`, `'emplacement'`, `'mine'`, `'support'`, `'backpack'`. With a group: within its families. |
| `allow_families` | The only families it may take. Default: the preferred ones (with a group: its families). With neither field, any family. |
| `exclude` | Stratagems never taken. |

A definition that gives only the older fields (`beacon`, `prefer_families`, `allow_families`) keeps its allocation and
its registry hash exactly as before: its group is then only a label (`describe`).

### Carrier groups

A group is a pool of vanilla carriers defined by **structure** (the carrier's beam, its catalogue family, its pod), never
by a fixed list. The allocator draws a definition's carrier from its group's members that no lobby member picked and no
other custom stratagem holds, ranked and logged (`CUSTOM CARRIERS`, `EXPENDABLE CARRIERS`). A group a payload cannot
use is refused at registration with the reason. `hd2.custom_stratagem.groups()` returns this table as data.

| group | members (structure) | payloads that may use it (default **bold**) |
|---|---|---|
| `orbital` | catalogue family orbital, any beam colour (the Orbital EMS Strike's is blue); its own delivery is replaced | runtime, Runtime bombardment, native orbital, Pelican |
| `any_red` | any red beam (row +0xD4 = 1), every family but Eagles; for payloads that deploy nothing needing an in-game item icon | **runtime**, **Runtime bombardment**, **native orbital**, **Pelican** |
| `any` | any eligible carrier, any beam | runtime, Runtime bombardment, native orbital, Pelican |
| `support` | a blue support or backpack carrier whose beacon is REDIRECTED to a donor's vanilla pod (the carrier's own pod never comes) | **support delivery (`donor`)**, also runtime, bombardments, Pelican |
| `support_pod` | a blue support or backpack carrier delivering its OWN pod: an exclusive rack (one owner, one consumer row) rewritten for the mission; capacity = its usable rack slots (1 or 2); each slot's role (weapon or backpack) takes its kind | **carrier pod (`item`)** |
| `expendable` | the carrier WEAPON's own stratagem (the EAT-700, then the EAT-411, for the EAT-17's class): one vanilla stratagem is the beacon carrier, the clone and the pod (CONDENSED); a separate blue support/backpack carrier only when that stratagem cannot carry a beacon | **expendable** |
| `weapon` | a support weapon's OWN stratagem for its variant (the M-1000 Maxigun: its class is itself, so it has no other carrier): its row is the beacon carrier, its own type the variant, its own pod the delivery; a separate blue support/backpack carrier only when that row cannot carry a beacon. A native pick of the weapon makes the variant unavailable; a selected variant blocks the weapon | **weapon** |
| `sentry` | catalogue family sentry (blue): the donor sentry's pod by redirect | **sentry** |
| `emplacement` | catalogue family emplacement | (none yet) |
| `eagle` | catalogue family eagle (red, limited uses; the discovery's Eagle mode) | **eagle** |

**How the pod racks differ (research carrier-pod-items section 11).** 51 of the 56 hellpod racks (every weapon and
backpack rack but the One True Flag's) are ONE unit, the weapon-rack unit (56 nodes). A weapon rack and a backpack rack
do not differ in model, scene graph or attach routine: only in the node each RackAttach slot names and its side. The
nodes: 1992741347 (the main weapon, side 2), 2145467647 (a second weapon, side 1), 85105251 (the main backpack, side
2), 3993544543 (a backpack beside a weapon, side 1); `attach_1` (3902607911) is the default node of every unconfigured
slot. A slot's **role** is its vanilla item's kind; an empty slot inside the spawn count (only the EAT-411 Leveller's
slot 1) takes its rack's kind (weapon). A pod item goes only into a slot of its role.

**Availability.** A definition that requested a group, every carrier pod and every expendable definition follow the
availability rule: when its group has no free member it is **UNAVAILABLE** (the panel tile warns and names the lobby
picks that took the candidates; picking it is refused; picked already, it unpicks itself: the slot is plainly the
Orbital Precision Strike token). A definition with only the older policy fields keeps its earlier behaviour (refused at
mission start, `PRE-MISSION: NOT READY`).

**What a carrier must be** (discovery guards, always applied):

- owned, selectable and enabled;
- unlimited uses (an Eagle carrier: its reviewed uses per rearm instead);
- not in the current loadout;
- never a mission or objective type or a vehicle;
- an Eagle only for an `eagle` custom stratagem, which takes nothing but an Eagle;
- every call-in package known (the mission loader's rule: a support weapon's package is its weapon's);
- a reviewed presentation and a native code;
- never any registered custom stratagem's asset or delivery.

**How it is chosen:**

- **Never shared:** two custom stratagems never take one carrier. The one with no carrier left is refused, alone.
- **By identity:** every registered custom stratagem is allocated, whatever is selected, so the carrier of an id never
  depends on the selection (see *Several players*).
- **Deterministic:** for one mod set, native selection and build. The most constrained custom stratagem goes first,
  then by id.
  Within one, the order is:
  1. the preferred family;
  2. for offensive stratagems, a red ping first;
  3. the call-in class;
  4. the stable id.
- **When:** allocated aboard the ship and cached. It is checked again whenever the saved loadout changes and every 5 s,
  and allocated again at mission start against the saved loadout and this mission's stratagem records.

### `assets`

Stratagems whose call-in packages the custom stratagem needs in the mission (a shell's explosion, a gun's
round...). They are requested at mission start, and the custom stratagem is not callable until every one is
resident. Listed assets are never carriers. The donors a payload table names (a weapon's round, an explosion donor, a
shell) are added automatically.

## Payload families

| field | the call | carrier |
|---|---|---|
| (none) / `delivery='runtime'` | Nothing native; the mod delivers in `on_activate`. | any policy |
| `delivery={family='support', items=...}` | The donor's vanilla support pod; its exact items captured and modified. | `beacon='support'` (group `support`) |
| `delivery={family='support', items={{item, count, modify}}}` | A CARRIER POD: the carrier's own pod (no redirect), its exclusive rack holding these items for the mission. | group `support_pod` |
| `delivery={family='expendable', weapon, presentation, modify, level, pod}` | A mission-scoped clone of the donor weapon on an unused carrier weapon of its class, delivered by that weapon's own pod (`pod`: what it holds). | group `expendable` (`beacon='support'`) |
| `delivery={family='weapon', weapon, round, model, model_use, presentation}` | A mission-scoped variant of a support weapon on its OWN type (its class is itself: the M-1000 Maxigun): its round, its model (the mod's own), its name and icon; delivered by its own pod. | group `weapon` (`beacon='support'`) |
| `sentry={donor, weapon}` | The donor sentry's vanilla pod; its exact sentry captured, its own weapon configured. | `beacon='support'`, sentry family only |
| `eagle={donor, uses, payload}` | The donor Eagle's own strike; its exact jet captured, its rockets' impacts changed. | `beacon='offensive'`, Eagle family only |
| `orbital={shell, pattern, ...}` | A Runtime bombardment at the activation. | any policy |
| `orbital={pattern, impact_explosion, native=true}` | The donor's own native barrage; its shells' impacts changed on every machine's own copies. | any policy (the examples: `beacon='offensive'`, orbital preferred) |
| `pelican={hover, orbit, gun, approach}` | A Runtime-spawned Pelican over the beacon (the session host spawns it). | any policy (the examples: `beacon='offensive'`, orbital preferred) |
| `silo={donor, blast, fallback}` | The donor silo's vanilla pod; where exactly this call's missile detonates, the session host requests the blast explosion. | `beacon='support'` (group `support`) |

A donor is a catalogued name (`'MG-43 Machine Gun'`) or a typed handle (`hd2.support_weapon(name)`,
`hd2.backpack(name)`). Raw projectile, explosion or entity numbers are never accepted: a donor's package must be known.

### `delivery`: support weapons and backpacks

```lua
delivery={family='support',items={
    {donor=hd2.support_weapon('AC-8 Autocannon'),count=2,modify={rpm=150,ammo=6}},
}}
```

- **The pod:** in its first update the beacon's delivery becomes the donor's, so the game's own hellpod comes with the
  donor's own rack. Any catalogued support weapon or backpack whose pod rack is reviewed can be a donor
  (`domains/pod_payload_authoring.lua`): the AC-8 delivers its autocannon and its backpack, the B-1 its supply pack.
- **The capture:** exactly the items that pod's rack holds (the pod naming this beacon, then its rack). Each one is
  associated with the call (`ctx.items`; the weapons also in `ctx.weapons`) and keeps its kind (`'weapon'` or
  `'backpack'`).
- **`modify`:** applied to each delivered weapon's own records (see *Weapon modifications*), plus:
  - `impact_explosion = donor`: each projectile the weapon fires explodes on impact as the donor's does (launchers and
    rockets: one guarded write of that projectile's own impact copy while it flies);
  - `rounds = n` (1..64): how many of its projectiles are converted (default 1, an EAT-17 has one).
- **`count`:** must equal the rack's own count (the rack lists are shared definitions).
- **Not supported** (refused at registration): two donors in one call (one native pod delivers one rack); another
  count; a backpack's `modify` (no instance-local backpack field is reviewed yet).
- `{stratagem = 'EAT-17 Expendable Anti-Tank'}`, the older form, is the same delivery with no `modify`.

### `delivery.items[].item`: a carrier pod (development; solo host)

```lua
carrier={group='support_pod',slots=2},
delivery={family='support',items={
    {item=hd2.support_weapon('MG-43 Machine Gun'),modify={ammo=300}},   -- (no rpm: its fire-rate selector)
    {item=hd2.backpack('B-1 Supply Pack')},
}}
```

The carrier delivers its OWN pod: no beacon redirect, no beacon write. Its rack decides what spawns, so it is written
for the mission (`runtime/carrier_pod.lua`; research carrier-pod-items):

- **The carrier:** a `support_pod` group member: a blue support or backpack stratagem nobody in the lobby picked, whose
  rack record has exactly one owner entity and one consumer row (itself), with room for the items in slots of their
  roles (`describe(id).pod`: rack, capacity, slots). 41 racks qualify; 29 hold one item, 12 hold two (the AC-8, B/FLAM-80,
  B/MD C4, FAF-14, GL-28, GR-8, M-1000, RL-77 and W.A.S.P. a weapon and a backpack; the EAT-700, EAT-411 and MGX-42 two
  weapons).
- **Items** (`domains/carrier_pod_items.lua`), each `{item, count, modify, allow_unverified_effect}`:
  - support weapons a vanilla rack delivers and backpacks: CONFIRMED kinds;
  - primaries (`hd2.weapon(name)`) only with `allow_unverified_effect = true`: a rack-held primary is not live-tested;
  - secondaries, throwables and entities without a pickup zone are refused;
  - `modify`: the weapon fields (*Weapon modifications*) per weapon item; never on a backpack.
  Each item once (give it a `count`); at most 8 in all; the carrier's capacity decides.
- **The write** (at mission start, before the carrier can be called; never after a call of it in the mission): only the
  RackAttach item of each slot, the items in the rack's usable slots in order (each in a slot of its role), every other
  slot that holds an item written EMPTY (so a count an upgrade raises spawns nothing extra). Nodes, sides,
  `apply_deltas`, the spawn count and +560 are never written. Re-proved right before the write: the record identity and
  ONE owner, one live row naming the rack (its carrier), every slot exactly its vanilla item and node, every item package
  resident. Restored byte for byte aboard the ship (`RETURN TO SHIP: carrier pod ... RESTORED`); a slot another writer
  changed is a CONFLICT (nothing written).
- **The capture:** the call's own rack (the pod naming its beacon); each slot is checked against the planned layout
  (`POD: n items, each in its planned slot`), and each weapon gets its own item's `modify`.
- **Several players:** refused in this pass (a rack written on one machine only).

### `delivery={family='expendable'}`: a clone of an expendable weapon (development)

```lua
carrier={group='expendable'},                                       -- or the older {beacon='support', ...}
delivery={family='expendable',weapon=hd2.support_weapon('EAT-17 Expendable Anti-Tank'),
    presentation={name='EAT-17G GAS EXPENDABLE ANTI-TANK',icon=hd2.resources.image('eat17g')},   -- optional
    modify={impact_explosion='Orbital Gas Strike'},                                             -- optional
    pod={{item='clone',count=2}},                                   -- optional: what its own pod holds
    level='full'}                                                    -- or 'model', 'presentation', or a Mod Options choice
```

**Condensed (the `expendable` group).** The carrier weapon's OWN stratagem carries the beacon too: its row presents as
the custom stratagem and answers to its code, its weapon type is the clone, and its own pod delivers it. One vanilla
stratagem is used, no beacon redirect is written. That stratagem must be a carrier under the carrier rules (the
discovery's guards on that one row: owned, selectable, enabled, unlimited, not in any lobby pick, its call-in package
known, a reviewed presentation and a native code, a blue beam). Only when it is not (for example the account does not own
it) does a separate blue support carrier throw the beacon, redirected to the weapon's own pod as before (`FALLBACK`,
with the reason); when neither works the definition is UNAVAILABLE. With several players an only-unowned row stays the
carrier for every machine (refused locally, never remapped). The log: `EXPENDABLE CARRIERS: <id> = <weapon> (CONDENSED
...)` or `(FALLBACK ...)`.

**`pod`.** What the carrier weapon's own pod holds, as a carrier pod's items plus `{item = 'clone', count = n}` (the
carrier weapon itself, the clone; at least one). A pool weapon whose rack cannot hold the pod (its usable slots and
their roles) is never the carrier weapon (`... (its pod holds at most N, M asked)`). For the EAT-17's class both racks
hold two: the EAT-700's slots already hold two of its launchers (nothing written); the EAT-411's slot 1 is empty at the
rack unit's `attach_1` node (one slot item written). Without `pod` the pod is the carrier weapon's vanilla rack (the
EAT-411's: one launcher).

A support delivery shows its donor's name and icon everywhere: every pickup prompt, map marker and weapon panel reads
the weapon's TYPE records, so one call's EAT-17 cannot look different from another EAT-17 (research:
`docs/research/carrier-weapon-clone-F5FEE03DCFDB.md`). The expendable family delivers a **clone** instead.

- **The carrier weapon:** an unused vanilla weapon of the donor's expendable component class, in order. For the
  EAT-17 (today's only donor) the pool is the **EAT-700 Expendable Napalm**, then the **EAT-411 Leveller**: their
  components are the EAT-17's, so their magazine, backblast, discard ability and drop mode already are. A weapon of
  another class (the AC-8: reloadable, no backblast) can never be a clone and is refused. The first candidate that is
  not taken is the carrier weapon:
  - taken by a NATIVE pick of any lobby member (that player brings that weapon: it must never change);
  - taken by another expendable custom stratagem the lobby selects (never two definitions on one carrier weapon type).

  Claims are made in id order from data every machine holds alike, so every machine computes the same carrier weapon.
- **The donor itself, the pool's last member** (the user's rules of 2026-10-06): when both clone carriers are taken, a
  definition whose pod holds only the clone uses the **regular EAT-17** from its own native pod. There is no clone and
  no type write (the EAT-17 is in the world loot table); only the call's own launchers change, per projectile, and they
  keep the EAT-17's name and icon. Its beacon is a separate blue support carrier.

  It is **reserved like every carrier weapon**:
  - a native EAT-17 pick takes it;
  - two definitions never share it;
  - as the last viable carrier it is **blocked** in the native picker.

  So the EAT-17C with the EAT-700 and the EAT-411 both picked blocks the EAT-17. The EAT-17C and the EAT-17G together,
  with one native EAT picked, block the other two. With all three picked natively the definition is UNAVAILABLE.
  There is no fallback beside a native pick.
- **The clone (each mission):** at mission start, before any entity of the carrier weapon exists, its own type
  records are made the donor's from the donor's REVIEWED values (pinned research; the donor is only ever read). Then
  its pod row's presentation (`runtime/carrier_presentation.lua`: name, cased name, description and icon) becomes the
  custom stratagem's, so the pod and its marker show it too. Both are restored byte for byte aboard the ship (the
  loadout screen opening is the hard boundary), never mid-mission.
- **The pod:** condensed, the beacon IS the carrier weapon's own stratagem, so the game's own hellpod brings that
  weapon's rack with nothing changed; in the fallback, in its first update the beacon's delivery becomes the carrier
  weapon's own stratagem. With `pod` its rack holds the pod's items (written at mission start, after the clone and before
  the presentation). The capture and `modify` are a support delivery's: exactly that rack's launchers, each configured on
  its own records; `impact_explosion` converts each launcher's own rockets.
- **`presentation`:** what the carrier weapon shows on its pickup prompt, map label and weapon panel. Default: the
  custom stratagem's `name` and `icon`. `'donor'` keeps the donor's own. A Runtime text the game cannot show, or an icon
  family that is not loaded and exact, is never written: the donor's own is borrowed and the log says so.
- **`level`** (development staging): `'presentation'` (the name, the marker / prompt icon and the weapon panel image:
  3 members), `'model'` (also the donor's model, sight, grip and wielder animations), `'full'` (also the donor's round,
  sounds and handling; the default). A Mod Options choice of these values is read at each mission start (the example
  binds one); with several players every member must choose the same (it is part of the registry hash).
- **Availability:** a definition with no free carrier weapon (or whose free carrier weapon can neither carry its beacon
  nor find a separate support carrier) is UNAVAILABLE:
  - its tile in the custom panel is dimmed with a warning mark and its tooltip names who took the candidates;
  - picking it is refused (nothing written);
  - picked already, it **unpicks itself**: its slot is plainly the `Orbital Precision Strike` token again (no
    conversion, no presentation, no payload);
  - re-evaluated every second aboard the ship (each change logged once: `AVAILABILITY (<id>): ...`), frozen at mission
    start: an unavailable definition is simply not converted.
- **Several players:** every compatible Runtime converts the same carrier weapon from the same synced definition and
  allocation (a client only after it agrees with the host); every machine converts each expendable id the synced
  lobby selects, whoever picked it, so another player's launchers are the clone everywhere. The carrier map hash input
  names the carrier weapon of an expendable entry (a value, never new grammar: every other entry and the hd2rt/1
  protocol are unchanged). A machine that sets up after an entity of the carrier weapon exists (a join after a
  delivery) does not convert (`CARRIER_PRESENT`) and shows the vanilla carrier weapon. Without custom multiplayer an
  expendable custom stratagem with several players is refused.
- **Not supported** (refused at registration): a donor without a reviewed clone class; `modify.projectile` (the clone
  fires its donor's round); a red carrier policy.

### `delivery={family='weapon'}`: a variant of a support weapon on its own type (development)

```lua
carrier={group='weapon'},
delivery={family='weapon',weapon=hd2.support_weapon('M-1000 Maxigun'),
    round=hd2.attack_output('LAS-58 Talon'),                -- optional: a round of the weapon's own class
    model=hd2.resources.model('laser_maxigun'),             -- optional: the mod's own model (docs/custom-models.md)
    model_use='apply',                                      -- or 'check', or a Mod Options choice of those
    presentation={name='LAS-1000 LASER MAXIGUN',icon=hd2.resources.image('laser_maxigun')}}   -- optional
```

**What a variant is.** A weapon whose component class is itself (today the **M-1000 Maxigun**: spin-up,
backpack-fed ammo, the ammo belt; no other support weapon has its components) can be carried by no other type. So its
variant converts **its own type** for one mission (`runtime/weapon_clone.lua` variant; research
`docs/research/weapon-variants-F5FEE03DCFDB.md`).

**The carrier group `weapon`.**
- The weapon's own stratagem is the beacon carrier, the variant and the pod (condensed): its row presents as the
  custom stratagem and answers to its code.
- Its own vanilla pod delivers the weapon with its own items (the Maxigun's backpack too).
- Only when that row cannot carry a beacon (for example the account does not own it) does a separate blue support
  carrier throw it.

**No fallback** (the user's rule of 2026-10-06). Its pool is the weapon alone:
- anyone in the lobby bringing the weapon natively makes the variant UNAVAILABLE (its tile warns, a pick is refused,
  a selected one unpicks itself);
- a selected variant BLOCKS the weapon in the native picker.

**What changes, on the weapon's own records only, for the mission:**
- **presentation:** the clone's three members (pickup prompt and map name, weapon panel image, marker icon). Default:
  the custom stratagem's name and icon.
- **`round`:** ProjectileWeapon +0. It must be a catalogued attack output (`hd2.attack_output`) of the **weapon's own
  compatibility class**; the Maxigun's is `conventional_plain`, and the LAS-58 Talon's 144 is one. An unverified donor
  is refused. Its package is a dependency of the definition, loaded at mission start; the write is refused
  (`ROUND_NOT_RESIDENT`) until it is resident.
- **`model`:** UnitComponent +0 UnitPath becomes the mod's own unit (`hd2.resources.model`; docs/custom-models.md).
  It is written only when the model is loaded and exact (`MODEL READY`) and the UnitPath consumer review proves on the
  running game.dll. Otherwise the vanilla model is kept and the log says why; the round and name still apply.
- **`model_use = 'check'`** only logs `MODEL READY` / `MODEL NOT READY` and keeps the vanilla model: use it for a first
  live test of the model patch loading.

**Lifecycle.**
- Everything is written at mission start, before any entity of the weapon exists (`CARRIER_PRESENT` otherwise), in one
  guarded transaction.
- Each record must have one owner and its exact native bytes.
- It is restored byte for byte aboard the ship, never mid-mission.

**Several players.** Every compatible Runtime converts the same type from the synced definition (as the expendable
clone). The round, the model's digest and its `model_use` are part of the registry hash, so every machine needs the
same mod build and the same choice.

**Not supported** (refused at registration): a weapon that is not a reviewed variant host, `modify`, `pod`, `level`, a
round of another class, `model_use` without `model`, a carrier group other than `weapon`.

### `sentry`: a custom sentry

```lua
carrier={beacon='support',prefer_families={'sentry'},allow_families={'sentry'}},
sentry={donor='A/MG-43 Machine Gun Sentry',
    weapon={projectile=hd2.support_weapon('MG-206 Heavy Machine Gun'),rpm=400,spread=5,ammo=300}},
```

- **The pod:** the donor sentry's vanilla hellpod deploys the donor's chassis, with its own AI, targeting, spin-up and
  model.
- **The capture:** the pod naming this beacon, then its content: exactly that sentry (`ctx.sentry`, role `'sentry'`).
  Nothing else in the world is scanned.
- **`weapon`:** configured on that sentry's own records (see *Weapon modifications*). Every other sentry of the same
  type stays vanilla, including the donor in your own loadout.
- **The rate:** written to the sentry's own rate slot and current rate. A sentry binds no rate-of-fire selector, so its
  other rate slots are dormant (the MG-43 Sentry's 630 / 630 / 900: research custom-payloads "sentryWeapons"). A weapon
  whose type binds one is refused for `rpm`.
- **Credit:** a sentry's kills credit its caller natively. The Runtime logs its credit state (read-only).

### `eagle`: a custom Eagle

```lua
carrier={beacon='offensive',prefer_families={'eagle'},allow_families={'eagle'}},
eagle={donor='Eagle 110mm Rocket Pods',uses=5,payload={impact_explosion='Orbital EMS Strike'}},
```

- **The carrier:** an unused, owned Eagle. The allocator treats the Eagle family as a first-class constraint: an
  `eagle` custom stratagem takes nothing else, and no other custom stratagem takes an Eagle.
- **`uses`** (1..20, default the donor's): the slot becomes a member of the Eagle fleet with its own uses:
  - the slot's entry gets `uses` (the game decrements them at each call);
  - the carrier's uses per rearm become `uses` for the mission, so a native rearm gives it `uses` again;
  - with no native Eagle in the loadout (no Eagle Rearm in the mission record) nothing native can rearm it: the Runtime
    writes the slot's uses back once they reach 0 and the rearm time has passed (`rearm_seconds`, 1..600; default
    Eagle Rearm's own cooldown, read live: 150 s).
  - Everything goes back to the carrier's own at the mission's end.
- **The strike:** in its first update the beacon's delivery becomes the donor's; the game's own Eagle flies the donor's
  run. The Runtime identifies the call's jet: the one donor jet first seen at this beacon's activation, while no other
  beacon of the donor's type activated then (otherwise it refuses: the run stays vanilla). `ctx.jet`, role
  `'eagle_jet'`.
- **The call's rockets** (live 2026-10-04: the 110mm's rockets come from the pods mounted on its jet; their source
  is a pod, their owner the jet): a projectile of the donor's strike type is the call's only when both hold, checked
  per projectile:
  - its source is a pod named by the call's jet's own mount record, in the slot the jet's type mounts that pod in
    (research custom-payloads "eagleMount");
  - its owner is the call's jet.

  The binding follows the jet **entity** (its id carries a generation: a reused id never matches) for up to 30 s after
  the activation. A vanilla run's rockets name its own pods and its own jet, so they are never the call's.
- **`payload.impact_explosion = donor`:** each of the call's rockets (the donor's strike projectile) explodes on impact
  as the donor's does. Only donors whose strike projectile has an impact explosion and no expiry explosion (Rocket Pods,
  Airstrike, Gas, Smoke, Napalm); not the Cluster Bomb or 500 kg. The rocket's direct hit stays.
- **Logs:** each call logs its state transitions: `JET CAPTURED`, `ROCKETS BOUND`, each `PAYLOAD POD`, each rocket's
  guarded write (`projectile impact CONVERTED` / `REFUSED`) and one `ROCKETS RESULT` (`NOT PROVEN` when no rocket of
  the call was converted). `hd2.custom_stratagem.verbose(true)` adds the per-rocket TRACE: every candidate rocket, each
  impact, the jet in the Eagle manager and the explosion requests read from the game's queue. Without verbose none of
  those reads happen. See `proof/EagleStunRocketPodsExample/README.md`.
- **Not supported:** a cooldown (an Eagle keeps its native cooldown and rearm), `pattern` and `payload.projectile`
  (the strike pattern and projectile are the donor's EagleComponentData, a shared definition with no reviewed per-call
  field: choose the donor whose run you want).

### `orbital`: a Runtime bombardment

```lua
orbital={shell='Orbital EMS Strike',pattern='Orbital 120mm HE Barrage',salvos=3,shells_per_salvo=4,
    shell_interval=0.3,salvo_interval=2,scatter=20,impact_explosion='Orbital Gas Strike'},
```

| field | meaning |
|---|---|
| `shell` | A reviewed orbital whose first shell is fired: 120mm, 380mm, Airburst, EMS, Gas, Gatling, Napalm, Precision, Smoke, Walking. |
| `pattern` | A reviewed orbital whose vanilla salvo pattern is the base (default the 120mm's 5 salvos of 3). |
| `salvos`, `shells_per_salvo` | 1..16 each; at most 64 shells in all. |
| `shell_interval`, `salvo_interval` | Seconds (0..10, 0..30). An explicit interval is exact (no random part). |
| `scatter`, `salvo_scatter` | 0..100: the per-shell scatter half-width and the salvo-centre scatter, in the pattern record's own units (the 120mm's `scatter` is 27). |
| `impact_explosion` | Each shell explodes on impact as the donor's does (that shell's own impact copy, found by its exact pool slot). |

The barrage fires at the activation (the landing position); `on_activate` still runs. The shells are fired from the
caller (their kills credit natively). **Not supported:** `explosion_scale` (an explosion's size is its shared row:
every shell of that explosion would change). Choose another `impact_explosion` donor instead.

**`native = true`: the donor's own barrage.**

```lua
orbital={pattern='Orbital 120mm HE Barrage',impact_explosion='Orbital Gas Strike',native=true},
```

- In its first update the beacon's delivery becomes `pattern`'s own, so the game creates the donor's native barrage at
  the activation. That barrage is a networked object: every player's machine fires its own copy of it with the same
  seed, so every machine sees the same salvos, trajectory and pattern.
- Each shell of that barrage (the 120mm: 194 and 137) explodes on impact as `impact_explosion`'s does: one guarded
  write of each shell's own impact copy, on every compatible machine's own copies (*Several players*). The barrage's
  own salvos, timings and every other barrage stay vanilla.
- The call's barrage is recognised at its first shell: its delivery type is this custom stratagem's carrier, its
  creator is the caller's peer, its target is at the call's beacon (3 m), and exactly one call matches. Otherwise it
  stays vanilla (`BARRAGE NOT TAKEN`).
- Only `pattern`, `impact_explosion` (required) and `native` are accepted: the donor's own barrage is used exactly as
  the game reads it, so `salvos`, `shell` or intervals are refused.
- The shells credit natively (the game's own creditor, never written).

### `pelican`: a Pelican CAS

```lua
pelican={hover=60,orbit={radius=40,altitude=60,duration=55},
    gun={behave_as='gatling_sentry',rate_multiplier=2,round='ap4',spread=100,recoil=false,unlimited_ammo=true,
    face_target=true}},
```

The same options as `hd2.pelican.spawn` (*Pelican gunship*): the beacon is neutralized and the Runtime spawns a Pelican
over it at the activation, associated with the call. The session host spawns it (a client's call asks the host:
*Several players*). Its gun's packages (the Gatling Sentry's, the MG-206's for `round='ap4'`, and for `gun.sound` the
stratagem that provides that sound's bank, `hd2.sounds.describe(name).stratagem`; docs/weapon-sounds.md) become assets.

### `silo`: a custom silo (2026-10-06, NOT live-tested)

```lua
carrier={group='support'},
silo={donor='MS-11 Solo Silo',blast='Cyborg Production Unit',fallback='NUX-223 Hellbomb'},
```

- **The pod:** in its first update the beacon's delivery becomes the donor's, so the game's own hellpod brings the
  donor's silo (its rack entity) with its two rack items: the missile (slot 0) and the laser remote (slot 1;
  research/silo-payload-F5FEE03DCFDB.json). The silo, its remote, its launch and the missile's own blast (ExplosionType
  135) stay vanilla. `MS-11 Solo Silo` is the only reviewed donor.
- **The capture:** the pod naming this beacon, its rack, each slot's item (`ctx.missile`; roles `silo`, `missile`,
  `remote`). Read-only.
- **The detonation:** read every update while the missile exists. Its own detonation is queued with its type (135) and
  its own entity as the source (event natives: the explosive's request pins), so the queue entry gives the exact point
  at once. If the missile is gone after it left the silo (more than 15 m from where it was first read), its last read
  position is used (`inferred`). If it ends before it left the silo (the silo destroyed first), there is no blast.
- **`blast`:** a catalogued explosion (`hd2.explosions.list()`): a named one (`'Cyborg Production Unit'`, `'Hellbomb'`)
  or a weapon's. It is requested at the detonation point by the session host only (`hd2.explosions.spawn`: HOST_ONLY on
  a client), credited to the host's player. `fallback`: requested instead when the blast's packages are not resident
  on the host.
- **Assets:** the blast's and the fallback's packages are the definition's assets, requested at mission start on
  every machine whose lobby picked it, before it can be called. The Cyborg Production Unit's are two objective
  packages, about 300 MB together (its effect ships only with the whole production unit, its sound in its own audio
  package), so such a definition may take up to 90 s to load (`OBJECTIVE_ASSET_TIMEOUT`).
- **No countdown:** the launch sequence is the missile explosive's armed ability, timed in code (research
  silo-payload); no data field delays it, and the Runtime has no in-mission positional sound post.
- **Several players:** a client runs its own call (the silo client family) and publishes its missile's network id
  (`CUSTOM MP ITEMS: missile network id N`). The host watches its own copy of that missile (`REMOTE CUSTOM SILO`) and
  requests the blast where it detonates. What other players see of a host-requested explosion is unproven.

### Weapon modifications

The keys of `delivery.items[k].modify` and `sentry.weapon`, applied to the one entity's own records only (the game's
own copy routines make that entity a private ProjectileWeapon record and magazine first):

| key | meaning | how |
|---|---|---|
| `projectile` | The round a support weapon fires (its name or `hd2.support_weapon(name)`). Its package becomes an asset. | the entity's own ProjectileWeapon copy, its chambered round |
| `rpm` | 30..3000 rounds a minute. Refused, at registration, for a weapon whose type binds the fire-rate selector (the MG-43 Machine Gun, the MG-206, the M-105 Stalwart: the game rebuilds its rate from its type's three slots; their modes are `hd2.fields.fire_rate.modes`). | its own rate slot and current rate |
| `spread` | Over 0, at most 100 mrad. | its own WeaponData instance |
| `ammo` | 1..2047 rounds per magazine (an 11-bit network field). | its own magazine copy (the tracer pattern off) |
| `recoil` | `'zero'`. | its own WeaponData instance |

Each one is guarded (the solo host, the mission, the entity associated with this call and alive, its values still the
type's) and verified after the write, including that the type's own records are unchanged. A refusal leaves the
entity vanilla and is logged (`custom weapon REFUSED`).

### Explosion donors

`impact_explosion` names a reviewed donor whose whole chain (explosion, damage, status rows) is checked on the real
game before every use, and whose package must be resident:

| donor | explosion | effect |
|---|---|---|
| `'Orbital Gas Strike'` | 82 | the gas cloud |
| `'Orbital EMS Strike'` | 188 | no damage; a strong stun and a 15 s static field |

### Callbacks and the call context

Callbacks run as the registering mod, inside the Runtime's update (the game thread):

| callback | when |
|---|---|
| `on_called(ctx)` | The call-in started: the record entry's call-in in flight, or the beacon first seen. |
| `on_beacon_created(ctx)` | The beacon's first update (its delivery already changed). |
| `on_beacon_landed(ctx)` | Its countdown started: `ctx.position` is the landing position. |
| `on_activate(ctx)` | The beacon activated: deliver now. |
| `on_delivered(ctx)` | The delivery is known and its data modifications applied: `ctx.items` / `ctx.weapons`, `ctx.sentry` or `ctx.jet`. |

`ctx` fields:

| field | meaning |
|---|---|
| `ctx.id` | The custom stratagem. |
| `ctx.call_id` | `'<id>#<n>'`, unique in the mission. |
| `ctx.n` | The call's number in the mission. |
| `ctx.player` | The caller, the local player. |
| `ctx.slot` | The loadout slot, when known. |
| `ctx.carrier` | `{name, stable_id, type}`. |
| `ctx.beacon` | `{entity, network}`. |
| `ctx.position` | The landing position (else the activation position). |
| `ctx.delivery` | The delivery. |
| `ctx.items`, `ctx.weapons` | A support delivery's captured items (each `{entity, kind, entity_type, projectile}`), and its weapons. |
| `ctx.sentry` | A sentry's captured sentry. |
| `ctx.jet`, `ctx.converted` | An Eagle's captured jet; how many of its rockets were converted. |

`ctx` methods:

| method | does |
|---|---|
| `ctx:log(text)` | A log line tagged with the call. |
| `ctx:associate(entity, role)` | Associates an entity the call spawned with it (see *Spawned instances*). |
| `ctx:spawned(role)` | The live entities associated with the call. |
| `ctx:barrage{shell, pattern, target}` | A Runtime bombardment (below). |

A delivered weapon (`ctx.weapons[k]`) or sentry (`ctx.sentry`) has `.entity` and these methods (the data fields call
them for you):

- `weapon:configure{projectile, rpm, spread, ammo, recoil}`: *Weapon modifications*, with a projectile type the mod
  already resolved.
- `weapon:set_impact_explosion('Orbital Gas Strike', {rounds = n})`: this weapon's projectiles explode as the donor's
  do on impact.
  - **What changes:** each projectile's own copy of its impact explosion (one guarded 4-byte write while it flies).
  - **What stays vanilla:** the weapon, its type, its projectile row and every other weapon.
  - **Whoever fires it:** the payload follows this exact weapon. A player who picks it up fires the same payload; the
    kill credit stays the game's own (the wielder).
  - **Rounds:** one per weapon by default (an EAT-17 has one).
  - **Donors:** only reviewed ones (*Explosion donors*), whose whole chain is checked first.
  - **Several players:** only a payload declared as data (`delivery.items[].modify.impact_explosion`) is converted by
    every compatible Runtime. One a callback attaches converts on the caller's machine only (logged).
- `weapon:credit()`: its kill credit as the game computes it (read-only).

### `ctx:barrage{shell, pattern, target, impact_explosion}`

Fires `shell`'s reviewed shell (the Orbital Gas Strike's 197) through the game's own projectile wrapper. The salvo
pattern is `pattern`'s (read from its live record, which must be exactly vanilla; for example the 120mm's 5 salvos of
3). `target` defaults to `ctx.position`. The `orbital` table is the same barrage stated as data, with counts and
intervals.

- `shell` (and `impact_explosion`) must be among the custom stratagem's assets, since their packages must be resident.
- Nothing shared is written; the shell's own chain does the rest (with `impact_explosion`, each shell's own impact copy).
- Known differences from a native barrage are listed in `runtime/bombardment_executor.lua` (DIFFERENCES).

## Several players (EXPERIMENTAL test build)

**Status: a development build, live-tested with two players.** The build banner is
`EXPERIMENTAL CUSTOM MP RELEASE-HARDENING BUILD r7` (r2 fixed the crash of the `...GAS EAT PROOF BUILD`: research
section 12; r3, the Gas EAT provenance build, is research section 14; r4 is section 15; r5 is sections 16 and 17; r6 is
sections 18 and 19 and is LIVE-PROVEN; r7 is section 20, offline-validated only).

**Live-proven in r6 (two players, 2026-10-05):** two-way custom pick synchronization; remote custom icons; the frozen
lobby-wide carrier map and the custom call identity through carrier -> custom id; Gas EAT and EAT-17G multiplayer
provenance (the condensed carrier, cross-player launcher pickup, per-peer projectile realization); the Gas Barrage from the
host and from a client (every peer converting its own shell copies); the Pelican CAS from the host and from a client (the
client's request validated and spawned by the host, its network provenance, the remote private weapon mirroring at about
3200 RPM, the caller's credit); the public-matchmaking protection; the native blocked-card state.

**Incompatible registries fail closed (0.30 rule; r9, offline only):** when any lobby member runs another custom
stratagem registry or Runtime version (or names a custom id not registered here), custom stratagems are DISABLED
lobby-wide, on every machine: no carrier is allocated or frozen, no token converted, no custom call run and no provenance
published; vanilla gameplay is untouched. The on-screen warning reads `CUSTOM STRATAGEMS DISABLED` / `Incompatible
custom-stratagem mods detected.` / `All players must use the same custom stratagems and versions.`; every custom tile is
unavailable with that reason and a pick is refused. Custom slots already selected are kept, and in a mission each one's
token (Orbital Precision Strike) is LOCKED (its own record entry unavailable all mission: it is never called). Every
other custom slot whose multiplayer setup is refused is locked the same way. The full registry hash is the compatibility
contract: no partial or intersection compatibility. A lobby member with no Runtime at all does not trigger this rule.
A member value that cannot be read (a read while the game rewrites it) is not a mismatch: that member keeps its last
state for 10 s (`READ_ERROR_GRACE`), and only a member still unreadable after that counts as invalid; its next good read
is processed afresh, so it never stays invalid once readable again.

**r7 (offline only, not live-tested):**
- *Carrier blocking by feasibility:* a native card is blocked only when picking it would leave a currently satisfiable
  selected custom stratagem without a carrier (the deterministic allocator re-run with that card picked; lobby-wide with
  custom multiplayer). EAT-17G with the EAT-700 and the EAT-411 both free blocks neither; with one picked the other is
  blocked (`CARRIER BLOCKS`, `CARRIER BLOCK RELEASED`).
- *Lifecycle:* mission-scoped state (the frozen map and snapshot, evidence, calls, provenance) ends with the mission. The
  custom slots persist across a mission only through the explicit ship loadout state: frozen at the mission entry,
  restored back aboard the ship when the saved loadout still holds the launched order (`SHIP LOADOUT RECONCILED`), else
  cleared. Each Runtime then posts its ship state once (a new seq); a peer's pre-mission state waits for it (30 s grace);
  another lobby id forgets every member.
- *Logging:* per-shell conversions after the first and the Pelican cadence samples after the first need
  `hd2.custom_stratagem.verbose(true)`; the lifecycle lines and summaries stay.
- The public-matchmaking notice is twice its original size, scaled with the screen height (the same share of the screen
  at 1080p, 1440p, ultrawide and 4K).

**r6 (live-proven):**
- *Native barrages:* a custom barrage binds to the call whose beacon dispatched it (exact, on the caller) or to its
  creator's one unbound recent call of that id (another machine; a beacon copy's creation position, since a copy has no
  owned position). `BARRAGE MATCH DEBUG` names every candidate when it does not bind.
- *Host-call requests:* each one is logged as RECEIVED, then SEQUENCE, PICK, CARRIER, EVIDENCE and BEACON CHECK, then
  ACCEPTED or one REFUSED reason; the custom identity comes from the observed beacon's carrier. A client's call spawns at
  its beacon copy's creation position.
- *Pelican cadence on other machines:* the replicated rate is recognised within 1 % (live: 299.96).
- *Carrier reservations:* the carriers the selected custom stratagems reserve (ref-counted over every slot and teammate)
  are BLOCKED on the open native stratagem grid with the game's own disabled-card state (runtime/stratagem_blocking.lua;
  research/stratagem-blocking-F5FEE03DCFDB.json); a custom stratagem whose carriers are all taken is unavailable in the
  custom panel, and picking it is refused.
- `hd2.custom_stratagem.describe` and `groups` are reachable by mods (they were documented but not exported).
- The public-matchmaking notice is three times larger and rate-limited; a lagging lobby advertisement is re-set at most
  every 10 s, without a notice.

**r5 (offline only, not live-tested):**
- *Published picks:* the Runtime's own virtual slots. The game's saved loadout only validates them: it lags every pick
  made with the loadout screen open, so a custom LAST pick no longer publishes a transient `-,-,-,-`. A slot counts as
  vanilla only when the saved loadout, with the screen closed, contradicts it for 3 s (`PICKS:` logged once).
- *Native custom barrages:* the barrage watch is asset-gated. While its donor's package is loading it WAITS and retries
  (`BARRAGE WATCH WAITING`, then `ARMED`); the custom stratagem is not READY TO CALL until it is armed.
- *Frozen carrier map:* at the mission start, carrier -> custom id (`FROZEN CARRIER MAP`) is the mission-time
  discriminator of every carrier beacon and thrown ball.
- *Native evidence:* every Runtime caches its own observations of other players' calls (thrown balls every 0.1 s,
  beacon copies) by beacon network id for 45 s (`CUSTOM MP EVIDENCE`). A host-call request is validated against that
  cache, not against what the game still holds when the slower request arrives. One host call per beacon.
- *Expendable (condensed) carriers:* the EAT-700 / EAT-411 carrier uses the same launcher provenance as the Gas EAT. The
  `expendable` group lists its lifecycle members in `groups()`: the MLS-4X Commando and MGX-42 Bullet Storm are
  expendable, but carry no EAT-17 clone (other component sets).

- **Pick sync:** every Runtime publishes its custom picks over the peer channel (`hd2rt/1`, live-proven) and reads every
  other lobby member's.
- **With every lobby member a compatible Runtime:**
  - the carriers come from the synced table: one per custom id the lobby selects;
  - the host publishes the table and carrier hashes, and each client checks its own against them;
  - the host runs its own calls as before;
  - a client runs its own **support deliveries** (the Gas EAT, live-proven r3), **expendables** and **native
    orbitals** (the Gas Barrage, r4), **asks the session host for its Pelican CAS** (r4), and runs its own
    **sentries** (2026-10-06, not live-tested: *Sentries across machines*). Eagles and Runtime bombardments stay
    host-only;
  - a custom call's payload is converted by **every** compatible Runtime on its own copies: a Gas EAT launcher's rocket
    is gas whoever fires it (*Gas EAT provenance*), a native custom barrage's shells are gas (*Native orbitals across
    machines*), and a host-spawned Pelican's chin gun is mirrored (*Pelican CAS across machines*).
- **Otherwise:** the earlier behaviour (the host runs its own calls, a client none).

Mods state the payload as data only; the networking (network ids, requests, provenance) is the Runtime's own and is not
part of the API.

Logged once per session: `CUSTOM STRATAGEMS MULTIPLAYER EXPERIMENTAL: N players (...)`.

### Pick sync and the shared carrier map (this build)

**What each machine publishes:**
`hd2rt/1;<version>;<registry hash>;<seq>;<slot0..3>[;host:<table>:<carrier>][;items:<id>@<beacon>=<item>+<item>,...]`
`[;calls:<id>@<beacon>#<call seq>=<slot>:<carrier hash>,...]`.
- A slot is a custom id or `-`.
- `items` (in a mission): the entities this machine's calls created, by the game's network ids (the same on every
  machine), with the call's beacon network id: a Gas EAT call's launchers; a native custom barrage (a confirmation:
  every machine derives it itself); on the host, a Pelican and its chin turret. Nothing else: no address, no type, no
  value to write.
- `calls` (in a mission, r4): calls this client asks the session host to run (the Pelican CAS): the custom id, its
  beacon's network id, the call's sequence number, the loadout slot and this machine's carrier map hash. Never a gun
  configuration, a projectile, a rate, an address or a write.
- The registry hash covers each definition's payload (r4), so machines whose same id declares another payload never
  agree. Install the same Runtime build and the same examples on every machine.
- A pick, a replacement, a clear or a reset publishes a new state (seq + 1). An unchanged state is never reposted.
- The sender is the lobby member the value was read from, never anything in the value.

**What each machine accepts:**
- A malformed value or an unregistered id: that member's custom state is ignored.
- Another Runtime version or registry: incompatible.
- No value: waited for 45 s, then reported.
- Custom multiplayer is enabled only while every member is compatible.

Logged on change: `CUSTOM MP STATE` (every member's slots with their custom ids), `CUSTOM MP CARRIERS`,
`CUSTOM MP AGREEMENT`.

**At mission start:**
- The native picks: every player's record entry except their synced custom slots.
- One carrier per custom id the lobby selects:
  - the same id on several players or slots shares one carrier, and each slot and call keeps its own state;
  - distinct ids get distinct carriers;
  - a native pick anywhere is never a carrier.
- The host's hashes are a checksum. A client whose hashes differ, or that gets none within 60 s, runs nothing.
- A custom slot whose record entry holds neither the token nor its carrier is a `CUSTOM MP DESYNC`. This machine's own
  such id does not run.

**Other players' picks on the loadout screen (display only):** the synced table is the authority. Live, a teammate's
native slots read empty aboard the ship (the game had not sent that player's slots yet), so the overlay no longer waits
for the token. A teammate slot gets its custom icon when:
- one loadout panel is bound to that player's peer id (the panel's own peer binding; r4: never the panel's index, the
  host or client role, or the panel's record, which may not hold that player's loadout yet);
- that player is compatible and its synced state names a custom id registered here for that slot;
- the slot's icon box is drawn and visible (a faded panel hides it).

It is drawn on that box whatever the native slot shows. Nothing is written; this player's own slots keep the stricter
rule (the slot must show the token). When the loadout screen opens (and when it changes) the panel map is logged once:
`REMOTE OVERLAY MAP: panel 0 -> peer A (this machine; ...), panel 1 -> peer B (a teammate; record owner, local flag)`.
Each drawn slot logs `REMOTE OVERLAY DRAWN: panel N, peer P, slot S: <id> at x, y, w x h` once; a slot that cannot be
placed logs `REMOTE OVERLAY REFUSED: peer P, slot N, reason R` once per reason. Only the icon is shown: no text surface
of a teammate panel is researched. See research sections 13 to 15.

**Other players' custom slots on the teammate stratagem HUD (a mission; display only; not live-tested):** while the
stratagem key is held, the game shows every teammate's four stratagems. Each card shows this machine's copy of that
player's stratagem record entry ([research](research/teammate-hud-F5FEE03DCFDB.md)). A custom stratagem's owner
converts only its own copy, so here the entry still holds the token, and the card showed Orbital Precision Strike. The
copy is the game's replicated state, and the custom multiplayer reads it (a thrown ball's slot must hold the token), so
it is never written. The card instead gets the custom stratagem's icon over its icon (`stratagem_slot_overlay.lua`
`mission_remote_slots`) when:
- the card's panel is bound to that player (the panel's own player entity, matched to a peer in the player list);
- the card's record entry is that player's loadout slot, and **the mission's frozen synced table** names a custom id
  registered here for that slot. The card's type alone never decides: a real Precision Strike stays native;
- the card shows that id's token or its frozen carrier (the owner's game may have sent the converted record);
- the card is drawn (nothing while the key is not held);
- the lobby does not now report that player's Runtime incompatible (a rejoin with another mod set).

The overlay covers the card's icon square, which also holds its frame and background. It is drawn on the native slot
grey and coloured as this player's own slots colour it. The card's own cooldown (its lit band: the part of the icon
lit while it recharges) is followed with a shade over the unlit part. The native timer, uses and arrows next to the
icon are not covered. Cooldown, activation, the record and the card are the game's own and untouched. Logged once per
mission and slot: `TEAMMATE HUD OVERLAY DRAWN: panel N, peer P, slot S (record entry E): <id> over the card showing
type T (its token | its carrier)`. A card that cannot be drawn logs `TEAMMATE HUD OVERLAY REFUSED: peer P, slot N,
reason R` once per reason. Holding or releasing the key logs nothing.

**Who threw a beacon:** the thrown ball carries its thrower's session peer id and record entry, replicated to every
machine (runtime/call_ins.lua). `CUSTOM MP CALL` names the thrower from it. Only after 5 s without a ball does it fall
back, labelled, to the synced table.

**The client-write proof (support deliveries, native orbitals, Pelican requests):** a client's own call writes, on this
machine only:
- its own record entry;
- that entry's cooldown;
- its own beacon's delivery (the donor's: the EAT-17's pod, the 120mm's barrage; none for a Pelican);
- the impact copies, in its own projectile pool, of a tracked custom call's projectiles (a Gas EAT launcher's rockets,
  a native custom barrage's shells; its own calls' or another machine's, correlated by network id);
- the private copies of its own copy of a host-spawned Pelican's chin turret (*Pelican CAS across machines*).

Every other family (sentries, Eagles, Runtime bombardments) stays host-only: a client refuses its own call of it.

`NOT_OWNED` still refuses another machine's beacon. `NOT_LOCAL` still refuses another player's projectile for every
binding that does not follow a delivered launcher's provenance.

**Gas EAT provenance (r3):** live, each machine exploded its own copy of a Gas EAT rocket: the caller's was gas, the
others' the vanilla blast. And another player's shot from the caller's launcher was refused on the caller's machine.
Now:
- the payload follows the exact launcher, never the player who fires it; the creditor is reported, never a gate;
- the caller publishes each call's launcher network ids (`CUSTOM MP ITEMS`);
- every other compatible Runtime accepts them only when every check holds, then binds those launchers the same way
  (`REMOTE CUSTOM ITEM`), and converts its OWN copy of their rockets. The checks: the sender's synced picks select the
  id; the id is registered here with a data-declared payload; this machine saw that call's beacon (and its ball's
  thrower is the sender); the assets are resident here; each network id resolves here to the delivery's own launcher
  type;
- the change is derived from this machine's own registered definition, never from the value;
- a member leaving, or the mission ending, forgets its launchers;
- every custom id the synced lobby selects has its declared assets requested on every compatible machine
  (`CUSTOM MP ASSETS: <id> resident for remote presentation/payload`). Only those ids are requested, never every
  registered one.

Live-proven (r3, 2026-10-04): pick sync, the carrier map agreement, launcher network ids correlating across machines,
every Runtime converting its own copy, original-owner and cross-picked launchers both gas, the credit following the
actual shooter, and the custom assets resident on compatible machines. The logs: `CLIENT WRITE PROOF`, `CLIENT WRITE
VERIFIED`, `CLIENT CALL CAPTURED`, `PROJECTILE CONVERTED` on the caller; `CUSTOM MP CALL`, `REMOTE CUSTOM ITEM` and
`REMOTE OBSERVED` on the others, all with network ids. See
[research/runtime-peer-messaging](research/runtime-peer-messaging-F5FEE03DCFDB.md), sections 10, 11 and 14.

**Native orbitals across machines (r4, not live-tested).** A native custom barrage (`orbital={..., native=true}`) is
the game's own networked barrage: every machine fires its own shells of its own copy, with the same seed. So the payload
is converted on every machine's own copies, and nothing is sent to do it:
- **The caller** (host or client) runs its call locally: its own slot, cooldown and beacon (its delivery becomes the
  donor's). At the barrage's first shell it takes the one barrage whose delivery type is its carrier, whose creator is
  this machine's peer and whose target is at its beacon (`DELIVERED: the native ... barrage, entity E (network id N)`),
  then converts that barrage's shells on its own copies (`BARRAGE SHELLS`). It publishes the barrage's network id as a
  confirmation (`CUSTOM MP ITEMS: barrage network id N`).
- **Every other compatible Runtime** derives the same barrage from its own copy at that copy's first shell: its delivery
  type maps to the custom id, its creator is a lobby member whose frozen synced picks select the id, and exactly one
  beacon of that id seen here, thrown by that creator, is at its target (`REMOTE CUSTOM BARRAGE: ... derived from its
  carrier type, its creator and its target`). The published network id then only confirms it (`CONFIRMED`); it binds
  the barrage there if the derivation did not.
- The salvos, trajectory and pattern are the game's own on every machine; the credit is the game's own (never written).
  A vanilla 120mm barrage (its own delivery type) and every other orbital stay vanilla.

**Pelican CAS across machines (r4, not live-tested).** A Runtime-spawned Pelican exists for everyone only when the
session host spawns it. So:
- **A client's call** keeps its own slot, cooldown and beacon (neutralized), and publishes a request (`calls`: the
  custom id, its beacon's network id, the call's sequence number, the loadout slot, its carrier map hash):
  `CUSTOM MP CALL REQUESTED`.
- **The host** runs a request once, only when every check holds: the sender's frozen synced picks hold that id in that
  slot, its carrier map hash is the host's, the sequence is new for that sender, this machine saw that call's carrier
  beacon, and its thrown ball names the sender (`CUSTOM MP CALL REQUEST: ... ACCEPTED`, or `REFUSED: why`). It then
  spawns the Pelican at that beacon for that player (`HOST CALL`), keeps its spawn, hold, orbit, targeting and lifetime,
  and publishes the Pelican's and its chin turret's network ids.
- **Every compatible machine** (the requesting client too) correlates them and gives its own copy of the chin turret the
  gun's private presentation, derived from its own registered definition: its round, rate slot and casing (its own
  ProjectileWeapon copy), its spread and zero recoil, and its fire interval while the host's replicated rate seed
  stands (`REMOTE CUSTOM PELICAN: ... chin gun MIRRORED`). Never what replicates (the current rate, rounds, trigger, AI,
  behaviour) and never a shared definition. Without the mirror a client draws the stock autocannon rounds.
- **Credit:** the host writes each of the chin gun's rounds' creditor (its own copy) to the requesting player before the
  round's first step (`CREDIT (...)`), so its kills credit that player as for the host's own call.

### Who runs a call

A beacon belongs to its **thrower's machine** (research beacon-redirect, corrected 2026-10-03). Only that machine
holds the beacon's state and runs its activation. So each player's own Runtime runs that player's calls. The one
exception is a payload only the host can create for everyone (a Runtime-spawned Pelican): the client still runs its
call (slot, cooldown, beacon) and the host spawns the payload on its validated request.

- **The host:** its calls run as in solo. Its custom slots are converted, presented, cooled down and delivered.
- **A client:**
  - With custom multiplayer enabled and agreeing with the host, it runs its own support deliveries (the Gas EAT proof)
    and native orbitals, and requests its Pelican CAS from the host.
  - Otherwise it refuses its own calls (`MISSION: custom stratagems REFUSED on this machine: it is a client ...`).
  - A refused custom slot stays the token (Orbital Precision Strike), and calling it calls the token natively.
  - A client's calls would need client-side writes: its own beacon's delivery, its own record entry, and (for most
    payloads) a spawn or a projectile write on a client. None of these is proven safe, so `NOT_HOST` stays everywhere.
- **Another machine's beacon** (a copy with no state here) is never changed (`NOT_OWNED`) and never becomes a call
  here. A copy of a carrier type is reported (`CUSTOM MP CALL`).

### The guards

**Removed (the selection, aboard the ship):**
- the selector's `NOT_SOLO` (`solo only: N players (a direct write sends no per-slot message to peers)`);
- the same check in the selector's advance to the next empty slot, in its native close and in the slot focus move.

These write this machine's own loadout UI only: its own record, its own slot widgets, its edited slot. Every other guard
stays: the panel bound to the local record, the local panel group and flag, the record's shape, the token.

What the old guard protected still holds: the write sends no per-slot message, so other players' loadout screens show the
token only once the game itself sends the loadout (`rpc_sync_stratagems` when the screen is left; `sync_loadout` at
launch). It was a guard on what peers see, not on the write's inputs.

**Lifted for a custom stratagem call only (the experimental scope, `runtime/multiplayer.lua`):**

| Write | Why it was solo-only | Kept |
|---|---|---|
| Slot conversion | the converted entry is not sent to peers | the local player's own record entry (by its peer id); mission, host, carrier, token, guarded transaction |
| Slot cooldown | the end replicates to peers | the converted entry; its row's own cooldown type (not shared) |
| Beacon first-update change | the changed delivery stays on this machine | a beacon owned here (`NOT_OWNED` for a copy), normal mode, exact timers |
| Runtime bombardment and its shells' impact copy | the shells exist on this machine only | the host's avatar as the source, the reviewed records, the donor's chain |
| Projectile impact bindings | a peer explodes its own copy | the exact bound source; the creditor is the local player, except for a provenance binding (a delivered launcher, a native custom barrage: every compatible Runtime converts its own copy) |
| Weapon configuration (sentry, launchers) | its copies are not sent to peers | the entity associated with the call; its own records only |
| Pelican hold, orbit, gun, target and kill credit | its flight state, copies and target are the host's | a Runtime-spawned Pelican associated with the call; on the host only (its rounds' creditor: the requesting player) |
| Pelican chin gun mirror (r4) | its copies are not sent to peers | another machine's Pelican copy correlated by network id: its chin turret's own private copies; never the replicated rate, rounds, trigger or AI |

- **Only the Runtime passes the scope.** None of these modules is exported to mods.
- **Per entity:** the scope comes only from a call the orchestrator marked (`mark_call`). A table that merely carries a
  `call_id` (for example a mod's own `call` for `hd2.pelican.spawn`) does not get it.
- **Everything else keeps the solo guard:** the proofs, the duplicate-token conversion, the bombardment payload proof.

### What a machine can see of the others (replicated state only)

| Data | What it shows |
|---|---|
| The loadout screen's per-player records (aboard the ship) | Each lobby player's slots. A custom slot holds **the token**, the same type as a native pick of it: the custom id is not visible (`CUSTOM MP LOBBY`) |
| Every peer's stratagem record (a mission) | Its loadout (raw types). The token until that player's Runtime converts the slot; the carrier only if the game sends that record again after the conversion (unproven: live-test it) |
| Another machine's beacon | Its type (the carrier for a custom call). Its thrower is the one peer whose record holds that carrier, once synced |
| Another player's custom selection, mods, account ownership | Not visible |

**Can a custom id be reconstructed remotely?**
- **From the token:** no. A native Orbital Precision Strike pick looks the same.
- **From a converted carrier:** yes, once the converting machine's record reaches this one. Every peer with the same mod
  set computes the same id → carrier map, and no player natively selects a carrier.
  - In this build only the host converts, so only the host's picks can be reconstructed (by the clients).
  - That happens only if the game re-sends the host's record after the conversion (`CUSTOM MP PICKS: peer ... record
    entry ... (reconstructed ...)`).
  - Any other change of a token is reported as `CUSTOM MP DESYNC`.

**Runtime networking: the peer channel, live-proven.**
[research/runtime-peer-messaging](research/runtime-peer-messaging-F5FEE03DCFDB.md) found no pure-Lua path:
- the engine's Lua network API needs the game's hash-checked network config;
- the Bingus Shared Loader has no messaging;
- the game's RPCs have native handlers only.

The game's own PlayFab lobby member data carries one member property, `hd2rt` (`runtime/peer_channel.lua`):
- the RuntimePeerHelloProof passed live both ways, with matching peer ids, a 225-byte value and in a mission;
- custom stratagems publish their picks on it (above, *Pick sync*).

The model is **caller executes, host verifies**. The host cannot run a client's call: the beacon belongs to its
thrower's machine.

### The lobby allocator (by custom id)

With custom multiplayer enabled, the allocation covers only the ids the synced lobby table selects, and its native
picks come from every player's record minus their synced custom slots (see *Pick sync*). Without it (solo, or a
lobby member without a compatible Runtime), the rules below apply unchanged.

1. **The same ordered candidate list on every peer.** Every registered custom stratagem is allocated, not only what
   this player selected: definitions by (fewest eligible, id); candidates by (family preference, red ping, call-in
   class, stable id). Inputs are sorted, so player order, join order and table iteration never matter.
2. **Lobby-wide native picks are skipped.** These are this machine's saved loadout and every peer record **as first
   seen** in the mission. A carrier that a faster peer's Runtime converted, and the game synced, is never taken for a
   native pick. Entries changed since first sight are logged.
3. **The same id reuses its carrier.** Every player and every slot selecting that id gets it, so Gas Barrage on two players
   is one carrier.
4. **Another id skips it.** Two ids never share a carrier, so Gas Barrage and Pelican CAS take two orbitals.
5. **Otherwise the id claims the first remaining candidate.**

**Ownership:** with several players it never ranks. A carrier this account does not own is refused locally (`NOT OWNED
here`), never remapped.

Tests: tests/test_custom_stratagem_lobby.py, tests/test_custom_stratagem_multiplayer.py.

### Calls and ownership

A carrier is shared; a call never is. Every call has its own:
- call id;
- caller (the local player of the machine running it: `ctx.player`, `ctx.player_peer`);
- slot, beacon, capture and associated entities;
- configured weapon, barrage and impact bindings;
- record entry and cooldown.

Another machine's beacon of the same carrier is reported, never joined to a call here.

| Payload | Credit with several players |
|---|---|
| Pelican CAS | spawned by the host. The host's own call: its chin gun's rounds credit the host. A client's call (r4): the host writes each round's creditor (its own copy) to the requesting player before the round's first step; the client's own copies of the rounds are drawn only |
| Eagle rockets | converted only when the projectile's creditor is the local player: the host's jet's rockets |
| Gas EAT launchers | any player can pick one up, and its rocket is gas whoever fires it, on every compatible machine. The credit is the game's own: live, another player's shot from the caller's launcher was credited to that player (the wielder) |
| HMG Sentry | its kills credit the caller natively (the sentry is its caller's) |
| Native custom barrage shells (r4) | the game's own creditor (never written): the barrage's caller, as for a vanilla barrage |
| Runtime bombardment shells | fired from the host's avatar: the host |
| A remote player's call | run on its thrower's machine; a Pelican request runs on the host for that player (above) |

No donor's ownership is changed.

### Sentries across machines (2026-10-06, NOT live-tested)

A sentry's weapon configuration (`sentry.weapon`) is data every compatible Runtime applies to its OWN copy of the
call's sentry, as the Pelican's chin gun is mirrored: every machine fires a turret's rounds from its own copy of the
turret's data (live, the Pelican's), so a configuration on one machine alone shows, and hits, on that machine only.
- **The caller.** It runs its own call, a client too (the sentry family is a client family). Once its pod's sentry is
  captured, it publishes the sentry's network id (`CUSTOM MP ITEMS: sentry network id N`).
- **The creator configures it whole.** The machine that created the sentry (its world record's created-here flag; the
  caller's own pod) writes every field: the round, the rate, the spread, the recoil and the magazine.
- **Every other machine mirrors it** on its own copy (`REMOTE CUSTOM SENTRY`; runtime/custom_weapons.lua role
  `published`): the round (its own ProjectileWeapon copy and its own magazine copy with the pattern off and the
  chambered round), the spread and the aim recoil. Never the rate or the ammunition: the game replicates those from
  the creator (its current RPM entry, the 11-bit round counts).
- **Why the host guard can change here.** It protected writes on an entity this machine does not simulate. A client's
  own sentry is created by its own pod on its own machine (the same condition the host has for its own sentry), and
  a copy takes only what each machine reads from its own data for its own shots.
- **The registry hash** includes the sentry's weapon, so every machine applies the same one.

### What other players see (unproven; live-test it)

| Family | Expected on the other machines |
|---|---|
| Slot conversion | the host's slot shows the carrier's own name there only if the record is re-sent; the cooldown replicates as a remaining time |
| Support / sentry delivery | the donor's native pod (spawned by the host's beacon, replicated) |
| Weapon configuration | host-local: others may see vanilla rounds |
| Gas EAT impact conversion | converted on every compatible Runtime's own copy (r3); a shot fired before another machine has correlated the launcher stays vanilla there |
| Eagle | the donor's native run; the converted impacts happen on the host only |
| Orbital (Runtime bombardment) | the shells exist on the host only (SpawnProjectile sends nothing): others may see no shells at all |
| Orbital (native custom barrage, r4) | the game's own barrage on every machine (same seed); its shells converted on every compatible Runtime's own copies |
| Pelican CAS | the Pelican replicates (network ids); its chin gun mirrored on every compatible Runtime's own copy (r4) |
| Silo | the donor's native pod and missile (spawned by the caller's beacon, replicated); the blast the host's request |

### Multiplayer log lines

| Line | When |
|---|---|
| `CUSTOM STRATAGEMS MULTIPLAYER EXPERIMENTAL` | once per session, the first time custom stratagems meet more than one player |
| `CUSTOM MP PEERS` | the players and stratagem records this machine sees (ship and mission start, on change) |
| `CUSTOM MP LOBBY` | each lobby player's slots on the loadout screen (on change) |
| `CUSTOM MP CARRIERS` | the id → carrier map, with the rule |
| `CUSTOM MP PICKS` | every player's custom picks this machine knows: its own, and the others' (the token, or reconstructed) |
| `CUSTOM MP CALL` | this machine's call (peer, custom id, call id, slot, beacon), or another machine's carrier beacon (thrower when known) |
| `CUSTOM MP DESYNC` | a peer converted a token to a carrier this machine maps to no custom stratagem |
| `CUSTOM MP RECORD` | any other change of a peer record entry |
| `CUSTOM MP ITEMS` | this machine's call published its entities' network ids (launchers, a barrage, a Pelican and its chin turret) |
| `REMOTE CUSTOM ITEM` | another machine's launcher correlated here (or REFUSED, with the reason), and each conversion of its rocket's copy here |
| `REMOTE CUSTOM BARRAGE` | another machine's native custom barrage derived (or confirmed) here, and its shells converted on this machine's copies |
| `REMOTE CUSTOM PELICAN` | a host-spawned Pelican correlated here, and its chin gun mirrored on this machine's own copy |
| `REMOTE CUSTOM SILO` | another machine's silo missile correlated here, its launch and its detonation (the host requests the blast) |
| `CUSTOM MP CALL REQUESTED` / `CUSTOM MP CALL REQUEST` | a client asked the host to run its call / the host ACCEPTED or REFUSED it |
| `HOST CALL` | the host runs a validated request for that player |
| `CUSTOM MP ASSETS` | a custom id the synced lobby selects is resident here for remote presentation and payload |
| `REMOTE OVERLAY MAP` | the loadout screen's panel → peer map (once when it opens or changes) |
| `REMOTE OVERLAY DRAWN` / `REMOTE OVERLAY REFUSED` | a teammate's synced custom slot drawn on its panel (once) / that cannot be drawn (once per reason) |
| `TEAMMATE HUD OVERLAY DRAWN` / `TEAMMATE HUD OVERLAY REFUSED` | in a mission, a teammate's custom slot drawn on the teammate stratagem HUD (once per mission and slot) / that cannot be drawn (once per reason) |

No line is logged per frame.

## Pelican gunship (`hd2.pelican.spawn` options)

```lua
hd2.pelican.spawn({position=ctx.position,hover=60,call=ctx,credit_to=ctx.player,
    orbit={radius=40,altitude=60,duration=55},
    gun={behave_as='gatling_sentry',rate_multiplier=2,round='ap4',spread=100,recoil=false,unlimited_ammo=true,
        face_target=true}})
```

**`gun`** configures the Pelican's own chin gun, on its own copies and records only:

| option | values |
|---|---|
| `round` | `'standard'` or `'ap4'` (the MG-206's round 275). |
| `behave_as='gatling_sentry'` | The Gatling Sentry's AI, casing and rate, with the Runtime target lock. |
| `rate_multiplier` | 1, 1.5 or 2 (times the Gatling Sentry's rate). |
| `spread` | In mrad, up to 100. |
| `recoil=false` | No aim recoil. |
| `unlimited_ammo=true` | The 2047-round safe magazine, refilled below 1500. |
| `face_target=true` | The body turns toward the lock. |
| `sound='sentry/gatling'` | Its firing sound: any name of the weapon sound catalogue (`hd2.sounds.list()`, docs/weapon-sounds.md), a per-shot sound (`'vehicle/maelstrom/main_gun'`, `'vehicle/bastion/hmg'`, `'support/mg206'`, ...) or a loop (`'sentry/gatling'`, `'sentry/machine_gun'`, `'support/m1000'`, ...). On its own weapon copy only; every compatible machine applies it to its own copy. The package of the stratagem that provides the sound's bank is loaded (a custom stratagem lists it as an asset); a resident-only sound is applied only while the game has its package resident. `'pelican/chin_autocannon'` (or no `sound`) keeps its own; `'maelstrom_main_gun'` still means `'vehicle/maelstrom/main_gun'`. Optional; offline-tested only. |

The other options:

- **`orbit`:** it circles its anchor once it holds there. Needs `hover`.
- **`credit_to`:** must be the local player. The chin gun's kills credit that player.
- **`call`:** associates the Pelican and its chin turret with the custom stratagem call.

Extra `on_event` kinds: `gun_armed`, `gun_refused`, `gun_ended`.

## What a custom stratagem uses: `hd2.custom_stratagem.describe(id)`

Read-only plain data (nil for an unknown id), from the mission's allocation, else the ship's:

| field | meaning |
|---|---|
| `group`, `group_source` | Its carrier group, and `'requested'` (it named it) or `'default'` (its payload family's; a label for an older policy). |
| `carrier` | `{name, stable_id, type, family, beacon, beam, condensed, fallback, local_refused}`: the vanilla stratagem whose beacon it throws (nil before an allocation). `condensed`: an expendable definition's carrier weapon carries the beacon too; `fallback`: why it did not. |
| `carrier_weapon` | `{name, stable_id, entity, level}`: an expendable definition's carrier weapon and its clone level. |
| `pod` | `{carrier, rack, path, exclusive, capacity, written, items = {{item, kind, count}}, slots = {{slot, item, label}}}`: whose rack delivers, its record, its capacity, whether it is written now, its items and their planned slots (a vanilla rack: `vanilla = true`). |
| `slots` | The pod capacity it needs. |
| `available`, `reason` | Whether it can be picked now, and why not. |
| `state`, `calls` | Its mission state and calls. |

`hd2.custom_stratagem.groups()` returns the carrier groups (*Carrier groups*) as data.

## Ownership

`hd2.ownership.credit_to_player(entity, player)` makes an associated autonomous entity's kills credit the local player.

**How it works.** The game credits a hit to the peer that owns the shooter's network object, unless the shooter carries
a no-credit tag. A self-wielding turret the Runtime summoned carries that tag. One guarded write of that entity's own
Tag record clears it. No mask, creditor structure or network object is part of the API.

**Refused unless:**

- the Runtime's update;
- the solo host;
- the local player;
- the entity belongs to that player's custom stratagem call;
- the entity wields itself and has a network id.

**Native credit.** Weapons the player holds (the Gas EAT's launchers) and shells fired from the avatar (the Gas
Barrage) are credited natively; nothing is needed for them.

## Spawned instances

`ctx:associate(entity, role)` records that this exact entity belongs to that call and player: a Pelican, its chin turret
(associated automatically), a pod, a delivered weapon.

- **Lookup:** `hd2.custom_stratagem.instance_of(entity)` returns the association, or nil.
- **Identity:** an association names one live entity by its full id. Every lookup checks that the entity still exists.
  No type and no shared definition is ever used to identify an instance: a vanilla entity of the same type is never
  associated.
- **Scope:** the mission. Associations are dropped at its end.
- **Kills:** kills whose last hit came from an associated entity are logged against the call:
  `KILL: victim ... by its weapon ... -> credited to ...`.

## Logging

One line per state transition:

- `REGISTERED`, `CUSTOM CARRIERS`, `PRE-MISSION`, `MISSION ... READY TO CALL / REFUSED`;
- for each call: `BEACON`, its delivery change, `LANDED`, `ACTIVATED`, `DELIVERED`, `COOLDOWN`, `KILL` (the first 5 per
  call);
- `MISSION END` and `RESTORED`.

Refusals are always logged. `hd2.custom_stratagem.verbose(true)` adds every carrier candidate and its verdict, and each
custom Eagle call's per-rocket trace with its read-only probes.

## What is proven, and what is not

**Live-proven parts** (the proofs they come from):

- the virtual selection and the token;
- the carrier presentation lifecycle;
- the slot conversion;
- the first-update beacon change (`'none'`, and a support carrier to an orbital delivery);
- the fixed cooldown;
- the Runtime gas shells;
- the Pelican's spawn, hold and orbit;
- the chin gun configuration and its kill credit;
- the first custom-stratagem API examples, without Stratagem MultiSelect (the user's report, 2026-10-04).

**Live-tested in the payload families build (2026-10-04, the user's log):**

- **Custom sentry, Gatling chassis (HmgSentryExample 0.1.0): works.** The beacon redirect, the capture of exactly the pod's
  sentry, its own ProjectileWeapon and magazine copies, every value read back, and the type records unchanged.
- **Custom Eagle (EagleStunRocketPodsExample 0.1.0): NOT working.**
  - Working: the redirect to the Eagle 110mm Rocket Pods and the jet capture.
  - Failing: the rocket binding ended one update later (`jet ... is gone ... 0 converted`). No rocket was converted, and
    no EMS field was seen.
- **Regression found:** a Pelican CAS called after the custom sentry was refused (`RATE_UNEXPECTED`). Its gun had used a
  deployed Gatling Sentry as its reference.

**Live-tested in the diagnostic builds (2026-10-04, the user's logs):**

- **The sentry on the MG-43 Machine Gun Sentry chassis at 400 RPM** (HmgSentryExample 0.2.0): works; only its own
  records changed. The rate guard refuses only a type that binds a rate-of-fire selector.
- **The Pelican's gun is frozen** (`runtime/pelican_weapon.lua` `M.FROZEN`; PelicanCasExample 0.1.6): it armed after
  the HMG Sentry. No deployed sentry and no Gatling Sentry type record is read to configure it.
- **The Eagle rocket binding follows the jet entity** (EagleStunRocketPodsExample 0.2.0, the trace). The jet was
  captured, but its rockets came from the jet's two mounted pods (source) with the jet as their owner, so none was the
  call's.
- **The Eagle rockets through the ownership hierarchy: LIVE-PROVEN** (EagleStunRocketPodsExample 0.3.0):
  - the jet captured, its right and left pods bound from its own mount record;
  - the call's type-82 rockets captured with the jet as their owner;
  - each converted 229 -> 188 on its own impact copy, read back;
  - the game queued explosion 188;
  - unrelated projectiles stayed vanilla.

**Still to prove live:** that the explosion 188 the rockets request presents as the Orbital EMS Strike's (the static
field and the stun status).

**Live-tested: the expendable clone, EAT17GExample 0.1.0 (2026-10-05, the user's report and HD2Runtime.log):**

- **Works (the user):** the clone's model, animations, sound and rocket at the levels exercised; the gas conversion; the
  availability rule.
- **The log, three missions, the carrier weapon the EAT-411 Leveller each time** (the EAT-700 was in the loadout), the
  beacon carrier the M-105 Stalwart:
  - presentation level: `weapon clone APPLIED ... 4 writes`, two calls, each `beacon APPLIED ... delivery M-105 Stalwart
    -> EAT-411 Leveller` and `support pod CAPTURED ...: 1 item ... in slots 0`, each launcher's rocket `impact explosion
    184 -> 82`; back aboard the ship `weapon clone RESTORED: EAT-411 Leveller is its own weapon again: 4 writes; every
    record its native bytes: true` and both carrier presentations `RESTORED ... exact true`;
  - model level: 19 writes, one call, one launcher, `184 -> 82`, every restore exact;
  - full level: 34 writes, two calls, one launcher each, the rocket 132 (the EAT-17's) `376 -> 82`; the log ends in that
    mission (no restore line recorded).
  - Availability: with the EAT-700 and the EAT-411 both picked, `AVAILABILITY (eat17g_clone): UNAVAILABLE ...` and
    `UNPICKED loadout slot 3`; removing one made it available again.
- **The problems it showed:** (a) one launcher per call: the redirect brought the EAT-411's own pod, whose rack holds
  one launcher; (b) two vanilla stratagems used (the Stalwart as the beacon carrier, the EAT-411 as the carrier weapon).
  Built since (not live-tested): the condensed `expendable` group and the carrier pod (EAT17GExample 0.2.0, "EAT-17G POD
  BUILD").

**New in the 0.30.0-dev pass, NOT live-tested:**

- **The lobby-shaped carrier allocation** (above).
- **The experimental multiplayer build:** the selection with several players, the host's calls with several players
  (the scope), a client's refusal, the native set as first seen and the `CUSTOM MP` diagnostics.
- **The Eagle log reduced to state transitions**, with the trace behind verbose.
- **The startup progress display** (docs/getting-started.md, "Startup progress").
- **The builder schema and `custom_stratagems.json`** (offline tooling; the Runtime sees the same Lua it always did).

**New in the earlier builds and NOT live-tested:**

- **The orchestrator:** several custom stratagems in one mission, with policies and per-definition state.
- **The pod and rack capture** of support deliveries other than the EAT-17; the support-package rule (+0xF8).
- **The per-projectile impact explosion** beyond the Gas EAT.
- **The selector UX pass:** larger tiles, the pick sound, the native selector close. The live log of 2026-10-04 shows
  `SELECTOR CLOSE VERIFIED` and the pick sound played; the visual confirmation is not reported yet.
- **The orbital families:** the explicit pattern and each shell's impact explosion.

**Not supported:**

- a client's own Eagle or Runtime bombardment calls (host-only; the experimental client families are listed
  in "Several players");
- Runtime networking for mods (the peer channel is the Runtime's own; mods state payloads as data);
- what other players see of a Runtime bombardment's shells or a sentry's configuration (host-local: see "Several
  players");
- the gas cloud's damage-over-time attribution (untraced);
- explosion sizes (shared rows), an Eagle's strike pattern or projectile (shared EagleComponentData), backpack
  modifications, another count of a DONOR's rack, two donors per pod (no reviewed per-instance path for any of them);
- a carrier pod's spawn-count write (more items than its rack's usable slots), a secondary or throwable pod item, a
  carrier pod with several players (this pass).
