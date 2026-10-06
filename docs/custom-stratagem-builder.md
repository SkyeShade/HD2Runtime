# Custom stratagems for builders: the schema and the project format (HD2Runtime 0.30.0-dev)

This page is for tools that create custom stratagems, such as a future ModBuilder, rather than for hand-written Lua.
The API itself is [custom-stratagem-api.md](custom-stratagem-api.md).

**Status: development.** Everything here describes the same `hd2.custom_stratagem.register` the examples call. With
several players (experimental) a client runs its support, expendable and sentry deliveries and native orbitals, and
the host spawns its Pelican.

The ten custom stratagem examples of 2026-10-06 are custom_stratagems.json projects (each `proof/<name>/
custom_stratagems.json`, copied to `sdk/fixtures/custom_stratagems/<name>.json`): every family a builder needs has a
working example.

## The files

| File | What it is |
|---|---|
| `sdk/CustomStratagemSchema.json` | The fields a custom stratagem has: types, units, ranges, defaults, support status, reviewed donors, and the catalogues a builder's dropdowns read. |
| `sdk/schemas/custom_stratagems.project.schema.json` | A JSON Schema (2020-12) of the project file, `custom_stratagems.json`: its structure and ranges. |
| `sdk/tools/custom_stratagem_project.py` | The validator (structure, ranges, donors, family rules, code collisions) and the compiler to Lua. |
| `sdk/fixtures/custom_stratagems/*.json` | The examples as project files: the ten projects (HmgSentryExample, EAT23Example, EAT17GExample, EAT17CExample, PelicanCannonExample, PelicanCasExplosive, PelicanGasExample, PelicanEmsExample, OrbitalEmsBarrageExample, GasBarrageExample), EagleStunRocketPodsExample and GasEatExample. |

Both schema files are generated from the Runtime's own limits and catalogues (`scripts/generate_custom_stratagem_schema.py`,
part of `scripts/regenerate_domains.py --check`): a range in the schema is the range the Runtime enforces at
registration. The tests check this at every limit (tests/test_custom_stratagem_project.py). No raw offset, hash or
entity number appears in either file. Donors are named, because a donor's package must be known.

## The schema (`CustomStratagemSchema.json`)

| Key | Contents |
|---|---|
| `schemaVersion`, `hd2RuntimeVersion`, `format` | `1`, the Runtime version it was generated from, and the project format id (`hd2runtime-custom-stratagems/1`). |
| `status` | The support status (development, solo host). |
| `metadata` | `id`, `name`, `name_cased`, `description`, `icon`, `code`, `cooldown`, `uses`, `traits`, `assets`. |
| `carrier` | `group`, `slots`, `beacon`, `prefer_families`, `allow_families`, `exclude`. |
| `families` | Each payload family: its fields, its carrier rules (`beacon`, `allowFamilies`) and notes. `builder: false` marks `script`, the Lua-only family. |
| `podFamily` | The carrier pod payload family (`pod`), beside `families` (whose list is unchanged for tools that read it). |
| `familyOptions` | Options added to a family since: `expendable.pod` (what its carrier weapon's own pod holds) and its carrier group. |
| `unsupported` | Fields that are refused, with the reason (all shared definitions). |
| `limits` | At most 16 custom stratagems; at most 64 orbital shells per call. |
| `catalogs` | The dropdowns (below). |

Each field has a `type` (`string`, `integer`, `number`, `enum`, `list`, `object`, `image`, or a donor type such as
`support_donor`). It also carries `required` / `optional`, `default`, `min` / `max` (`exclusiveMin` when the minimum
itself is refused), `unit`, `catalog` (the catalogue its value comes from), `reviewedDonor: true` (only reviewed
donors are accepted) and `doc`.

### Metadata and carrier

| Field | Type | Range / values | Default |
|---|---|---|---|
| `id` | string | `^[a-z][a-z0-9_]*$`, at most 48 characters; unique across every mod | required |
| `name` | string | 1 to 64 characters (the HUD name) | required |
| `name_cased` | string | 1 to 64 characters (the panel's and loadout's name) | `name` |
| `description` | string | 1 to 400 characters | required |
| `icon` | image | `{"image": "<id>", "source": "images/<id>.png"}` | required |
| `code` | list of directions | 1 to 8 of `up`, `down`, `left`, `right`; never equal to, the start of, or started by another custom stratagem's code; never equal to any native code (`nativeCodes`), nor the start of, or started by, a catalogued one | required |
| `cooldown` | number, seconds from the call-in's arrival | above 0, at most 600 (refused for an Eagle) | the carrier's own |
| `uses` | integer, calls per mission | 1 to 100, each player's own; the last call's cooldown outlasts the mission (refused for an Eagle) | unlimited |
| `traits` | list of strings | at most 4 labels of 1 to 32 printable characters, after the automatic CUSTOM STRATAGEM | the family's |
| `assets` | list of stratagem names | the `stratagems` catalogue | none (a payload's own donors are added) |
| `carrier.group` | enum | a `carrierGroups` name: `orbital`, `any_red`, `any`, `support`, `support_pod`, `expendable`, `sentry`, `emplacement`, `eagle`; refused when it cannot carry the payload | the payload family's default group |
| `carrier.slots` | integer | 1..8: a pod capacity to ask for (`support_pod` and `expendable` only; at least the pod's items) | the pod's items |
| `carrier.beacon` | enum | `offensive` (red), `support` (blue), `any` | required unless `carrier.group` is given |
| `carrier.prefer_families`, `carrier.allow_families` | list of families | the `carrierFamilies` catalogue | any family |
| `carrier.exclude` | list of stratagem names | the `stratagems` catalogue | none |

### Payload families

| Family | Carrier | Fields |
|---|---|---|
| `support` | `support` beacon | `items`: exactly one `{donor, count?, modify?}`. `donor` must be a `supportDonors` entry with `deliverable: true`. `count` must equal that donor's rack count. `modify` (weapon donors only, `modifiable: true`) takes the weapon fields below plus `impact_explosion` and `rounds` (1..64, default 1). |
| `pod` (`podFamily`) | group `support_pod` (a `support` beacon) | `items`: 1 to 8 `{item, count?, modify?, allow_unverified_effect?}`. `item` is a `podItems` key (`support_weapon/<name>`, `backpack/<name>`, `player_weapon/<name>`); an `unverified` item (a primary) needs `allow_unverified_effect: true`. `modify` (weapon items only) takes the support `modify` fields. Each item once; the carrier's capacity (`podCarriers`) decides. Compiles to `delivery = {family = 'support', items = {{item = hd2.support_weapon(...)}, ...}}`. Solo host only. |
| `expendable` | group `expendable` (a `support` beacon) | `weapon` (a `cloneDonors` entry: the donor whose clone is delivered), `presentation` (`name`: the text its prompt, map label and weapon panel show, default the stratagem's `name`; `icon`: an image id for its marker and prompt icon, default the stratagem's icon; `"donor"` keeps the donor's own), `modify` (the weapon fields below without `projectile`, plus `impact_explosion` and `rounds`), `round` (another support weapon's round the clone fires: a `cloneDonors[].rounds` name, e.g. the RL-77 Airburst's; not with `modify.impact_explosion`), `level` (`presentation`, `model`, `full`; default `full`), `pod` (`familyOptions.expendable.pod`: `{"item": "clone", "count": n}` plus other `podItems`; default the carrier weapon's vanilla rack). The carrier weapon is the first free entry of the donor's `pool` whose rack holds the pod; its own stratagem is also the beacon carrier (condensed); the custom stratagem is unavailable while none is free. |
| `sentry` | `support` beacon, `allow_families` = `["sentry"]` | `donor` (a `sentryDonors` entry), `weapon` (the weapon fields below). |
| `eagle` | `offensive` beacon, `allow_families` = `["eagle"]` | `donor` (an `eagleDonors` entry), `uses` (1..20 per rearm; default the donor's), `rearm_seconds` (1..600; default Eagle Rearm's cooldown), `payload.impact_explosion` (only donors with `impactExplosionReplaceable: true`). No `cooldown`. |
| `orbital` | any beacon | `shell` (an `orbitals` entry; its first shell is fired), `pattern` (an `orbitals` entry; default Orbital 120mm HE Barrage), `salvos` (1..16), `shells_per_salvo` (1..16; at most 64 shells in all), `shell_interval` (0..10 s), `salvo_interval` (0..30 s), `scatter` and `salvo_scatter` (0..100, the pattern record's units), `impact_explosion`. Explicit intervals are exact (no random part). |
| `pelican` | any beacon (the examples: `offensive`, prefer `orbital`) | `hover` (seconds over the beacon, required), `orbit` (`radius`, `altitude`, `duration`, `period`, `entry`), `approach` (`distance`, `height`) and `gun`, its chin turret on its own copies: `round` (`native`: its own autocannon round; `standard`, `ap4`, `strafing_run`, `strafing_run_pattern`), `behave_as` (`gatling_sentry`: the Gatling AI; without it its own burst AI), `rate_multiplier` (1, 1.5, 2) or `rpm` (30..3000, with the Gatling AI), `casing` (`gatling`, `own`), `spread`, `recoil` (`false`), `unlimited_ammo`, `face_target`, `sound` (`pelicanSounds`), `impact_explosion` (`pelicanExplosionDonors`: a slow donor needs `rpm` at most its `maxRpm`), `aim_height` (0..3 m, with the Gatling AI). `gun = {"round": "native"}` alone is the vanilla autocannon (Pelican Cannon Support): its chin turret is left exactly as the game spawned it on every machine, only its kills are credited to the caller. |
| `silo` | `support` beacon (group `support`) | `donor` (a `siloDonors` entry: `MS-11 Solo Silo`), `blast` (required; a `blastExplosions` name, requested where the call's missile detonates), `fallback` (a `blastExplosions` name, requested instead when the blast's packages are not resident on the host). An `objective` blast (the Cyborg Production Unit's) loads about 300 MB of objective packages at mission start. Compiles to `silo = {...}`. Several players: the host requests the blast for every caller. |
| `script` | any | Not representable: the mod delivers in Lua callbacks (`on_activate`, `ctx:barrage`, `hd2.pelican.spawn`, ...). |

The weapon fields (support `modify`, sentry `weapon`), each on the call's own entity only:

| Field | Type | Range | Unit |
|---|---|---|---|
| `projectile` | `projectileDonors` name | the round a support weapon fires (its package becomes an asset) | |
| `rpm` | number | 30..3000; refused for a type that binds a rate-of-fire selector | rounds per minute |
| `spread` | number | above 0, at most 100 | milliradians (full width) |
| `ammo` | integer | 1..2047 | rounds per magazine |
| `recoil` | enum | `zero` | |

### Catalogues (the dropdowns)

| Catalogue | Entries | Used by |
|---|---|---|
| `supportDonors` | Every catalogued support weapon and backpack: `name`, `family`, `deliverable`, `count` (its rack), `items` (each item's kind and round), `modifiable`, `packageKnown`. | `support.items[].donor` |
| `projectileDonors` | Support weapons whose round is reviewed: `name`, `projectile`. | `projectile` |
| `cloneDonors` | Support weapons with a reviewed expendable clone class: `name`, `projectile` (the clone's round), `pool` (the carrier weapons in order: `name`, `stableId`), `packageKnown`. | `expendable.weapon` |
| `sentryDonors` | Catalogued sentries: `name`, `deployedEntity`, `supported`. | `sentry.donor` |
| `eagleDonors` | Reviewed Eagles: `name`, `uses`, `cooldown`, `strikeProjectile`, `impactExplosionReplaceable`. | `eagle.donor` |
| `orbitals` | Reviewed orbitals: `name`, `pattern` (its vanilla salvos, shells, intervals, scatter), `packageKnown`. | `orbital.shell`, `orbital.pattern` |
| `explosionDonors` | Reviewed explosion donors: `Orbital EMS Strike` (188: stun, a 15 s static field, no damage), `Orbital Gas Strike` (82: a 15 s, 15 m gas cloud). | every `impact_explosion` but a Pelican gun's |
| `pelicanExplosionDonors` | The explosions a Pelican gun may take: `name`, `kind` (`automatic`: one blast a round; `slow`: a volume) and `maxRpm` (a slow donor's). | `pelican.gun.impact_explosion` |
| `pelicanSounds` | Every firing sound of the catalogue (docs/weapon-sounds.md). | `pelican.gun.sound` |
| `nativeCodes` | Every native stratagem code: `stableId`, `name` (catalogued ones), `catalogued`, `code`. | the `code` check |
| `siloDonors` | Reviewed missile silos: `name`, `stableId`, `packageKnown`, `detonation` (the missile's own explosion type). | `silo.donor` |
| `blastExplosions` | Every catalogued explosion whose packages are known: `name`, `source` (`behavior`: a named one; `weapon`), `type`, `objective` (its effect and sound ship in objective packages). | `silo.blast`, `silo.fallback` |
| `carrierFamilies` | `backpack`, `eagle`, `emplacement`, `mine`, `mission`, `orbital`, `sentry`, `support`, `vehicle` | `carrier.*_families` |
| `carrierGroups` | Every carrier group: `name`, `beacon`, `families`, `pod`, `weapon`, `eagle`, `doc`, `payloads` (the payload keys that may use it) and `defaults` (those whose default it is). | `carrier.group` |
| `podItems` | Every item a carrier pod may hold: `key`, `name`, `kind`, `role` (weapon or backpack slot), `status` (`confirmed`, or `unverified` with its `acknowledgement`). | `pod.items[].item`, `expendable.pod[].item` |
| `podCarriers` | Every exclusive carrier rack: `name` (its stratagem), `capacity`, `roles` (its usable slots). | the capacity a pod needs |
| `beacons`, `directions` | The beacon kinds and the code directions. | `carrier.beacon`, `code` |
| `stratagems` | Every catalogued stratagem name. | `assets`, `carrier.exclude` |

## The project format (`custom_stratagems.json`)

A mod project (the folder with `hd2runtime.json`) may hold a `custom_stratagems.json`:

```json
{
  "format": "hd2runtime-custom-stratagems/1",
  "log": "optional: one line the mod logs at load",
  "stratagems": [{
    "id": "hmg_sentry",
    "name": "A/HMG-206 HEAVY MACHINE GUN SENTRY",
    "name_cased": "A/HMG-206 Heavy Machine Gun Sentry",
    "description": "Deploys a machine gun sentry that fires the MG-206 heavy machine gun's armor-piercing rounds at a deliberate 400 rounds per minute.",
    "icon": {"image": "hmg_sentry", "source": "images/hmg_sentry.png"},
    "code": ["down", "up", "left", "left", "down", "up"],
    "cooldown": 150,
    "carrier": {"beacon": "support", "prefer_families": ["sentry"], "allow_families": ["sentry"]},
    "payload": {"family": "sentry", "donor": "A/MG-43 Machine Gun Sentry",
                "weapon": {"projectile": "MG-206 Heavy Machine Gun", "rpm": 400, "spread": 5, "ammo": 300}}
  }]
}
```

- **`payload.family`** selects the family; its other keys are that family's fields. It compiles to the API's
  `delivery = {family = 'support', items = ...}`, `delivery = {family = 'expendable', ...}`, `sentry = {...}`,
  `eagle = {...}`, `orbital = {...}`, `pelican = {...}` or `silo = {...}`. An expendable `presentation.icon` image id must have its `images/<id>.png`.
- **Compiling** gives `src/addon.lua`: a generated header (with the source's SHA-256), then one
  `hd2.custom_stratagem.register{...}` per stratagem. The output is deterministic: the same JSON always gives the same
  bytes.
- **A hand-written `src/addon.lua`** (no generated header) is never overwritten: the compile refuses.
- **Invalid input is never compiled.** The validator lists every problem as `where: what`. The Runtime checks
  everything again when the mod loads.
- The Runtime never reads the JSON in game; it runs the compiled Lua.

### Commands

```text
py <SDK>/hd2.py custom-stratagem validate <project folder or JSON file>
py <SDK>/hd2.py custom-stratagem compile <project folder>
py <SDK>/hd2.py build <project folder>
```

`build` compiles `custom_stratagems.json` first, when the project has one.

## Icons: source and compiled

- **The source** is `images/<id>.png` in the project: 256 x 256, the editable picture
  ([custom-images.md](custom-images.md)). The game's icon masks are used as given. Other art is converted
  automatically; `"images": {"<id>": "raw"}` in `hd2runtime.json` opts out.
- **The compiled icon** is built by `hd2.py build`: the mod's own icon family (a texture and a GUI material,
  `<resource>/images/<id>`), inside the mod's archive (`mod/9ba626afa44a3aa3.patch_0`). A source-hash cache
  (`build/.image-cache/`) recompiles only a changed PNG. No vanilla resource is replaced.
- **The ZIP** carries the source PNG and `custom_stratagems.json` at its root, outside `mod/`. The game never reads
  them. Editing the PNG in an installed mod folder changes nothing: rebuild instead.

**The rebuild loop for a builder:**
1. Replace `images/<id>.png`, or edit `custom_stratagems.json`.
2. Run `hd2.py build <project>`.
3. Read `build/build-report.json` beside the ZIP.
4. Install the new ZIP (HD2 Arsenal).

`build/build-report.json` holds:
- `artifact`, `artifact_sha256` and `version`: the ZIP just written;
- `image_sources`: per image, its `file`, `source_sha256`, `prepared` (how it was converted), `resource` and `build`
  (`compiled`, `cache hit` or `recompiled: source changed`);
- `custom_stratagems`: `source`, `sha256`, `ids` and `images`;
- `requires` (the dependency contract) and `resources` (the packed Lua).

The same report (without the artifact fields) is also inside the ZIP. At load the Runtime logs each icon's build record
once, so the log shows which PNG the installed mod was compiled from.

## What a builder cannot express

These are refused with the reason in `unsupported`; they are shared definitions:
- explosion sizes;
- an Eagle's strike pattern or projectile, or an Eagle cooldown;
- backpack modifications;
- another count of a DONOR's rack, or two donors in one pod (a carrier pod, `pod`, holds its own items up to its rack's
  capacity: 1 or 2);
- a carrier pod's spawn-count write, a secondary or throwable pod item, or a carrier pod with several players;
- a sentry's impact explosion;
- an expendable clone's `projectile` (it fires its donor's round), a clone on a weapon outside the donor's component
  class, or on a carrier weapon a lobby member brings (the custom stratagem is unavailable instead);
- raw numbers.

Anything procedural (a Pelican, a barrage aimed in a callback, a reaction to a kill) stays Lua.
