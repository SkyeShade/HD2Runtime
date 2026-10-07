# Weapon firing sounds (`hd2.sounds`)

HD2Runtime names the firing sounds of the game's weapons so a mod can use them: on a Runtime Pelican's chin gun, a
custom stratagem's sentry, and (offline only) as a player or support weapon's own firing sound (`weapon.sound`).
The catalogue is read-only: it lists what exists, and a name is what a mod passes. The catalogue returns no Wwise
event, bank or package id. To play a sound directly (and to load a sound's bank with `hd2.require_assets{targets =
{hd2.sounds.asset(name)}}`), see [sounds.md](sounds.md).

Research: [research/weapon-sounds-F5FEE03DCFDB.md](research/weapon-sounds-F5FEE03DCFDB.md). Build F5FEE03DCFDB.

## The names

A sound's name is `<family>/<weapon>[/<part>]`, in lower case:

| family | what | examples |
| --- | --- | --- |
| `pelican` | the Pelican chin gun's own sound | `pelican/chin_autocannon` |
| `vehicle` | vehicle and exosuit mounts | `vehicle/maelstrom/main_gun`, `vehicle/bastion/hmg`, `vehicle/bastion/cannon`, `vehicle/patriot/minigun`, `vehicle/gunner_frv/hmg` |
| `sentry`, `emplacement` | sentries and emplacements | `sentry/gatling`, `sentry/machine_gun`, `sentry/autocannon`, `emplacement/hmg` |
| `eagle`, `backpack` | the Eagle's cannon, the Guard Dog | `eagle/cannon`, `backpack/guard_dog` |
| `support` | support weapons, by designation | `support/mg206`, `support/mg43`, `support/m1000`, `support/ac8` |
| `primary`, `secondary` | primary and secondary weapons, by designation | `primary/ar23`, `primary/sg225`, `secondary/p2` |
| `seaf` | SEAF troopers' weapons; a named weapon's SEAF version is its `/seaf` part | `support/mg43/seaf`, `seaf/1` |
| `automaton`, `illuminate`, `objective`, `other` | enemy and world weapons (from their content path, or numbered from their bank when unidentified) | `automaton/tank_turret_autocannons`, `automaton/hulk/1`, `illuminate/jet_champion_rifle` |

171 sounds: every ProjectileWeapon type of this build that names a firing sound (233 types; one more names an event no
bank defines, and is left out). A type whose sound is exactly another entry's and that no catalogue names (a tutorial
turret, a second Eagle, a mounted copy) is folded into that entry. Older names keep working: `'maelstrom_main_gun'` is
`'vehicle/maelstrom/main_gun'`.

Not in the catalogue: beam, flame, arc and melee weapons (the laser cannons, flamethrowers, the Arc Thrower, the Tesla
Tower, CQC weapons). They have no ProjectileWeapon type, so no sound of this kind.

## Reading the catalogue

```lua
for _, s in ipairs(hd2.sounds.list('sentry')) do
    mod:log(s.name .. ': ' .. s.label .. ' (' .. s.kind .. ')')
end
local hmg = hd2.sounds.describe('vehicle/bastion/hmg')
-- {name = 'vehicle/bastion/hmg', label = 'TD-220 Bastion MK XVI heavy machine gun', kind = 'shot', family = 'vehicle',
--  stratagem = 'E/MG-101 HMG Emplacement', resident_only = false, designed_rpm = 600, range_m = 650, midi = true,
--  pelican_default = false}
```

- `hd2.sounds.list(filter)`: every sound, sorted by name. `filter` is a family (`'support'`) or a table:
  `{family, kind = 'shot' | 'loop', stratagem = true | 'A/G-16 Gatling Sentry', resident_only = true | false,
  text = 'maelstrom'}`. An invalid filter raises an error that names it.
- `hd2.sounds.describe(name)`: one sound, or nil.

Each sound:

| field | meaning |
| --- | --- |
| `name`, `label`, `family` | Its name, a human name, the first part of its name. |
| `kind` | `'shot'`: one event per shot (`midi`: several MIDI notes per shot, one shot interval apart). `'loop'`: started when the gun starts firing and stopped when it stops. |
| `stratagem` | The stratagem whose call-in package holds the sound's bank (the smallest such package). The Runtime loads that package for a Pelican gun that takes the sound. |
| `resident_only` | No stratagem provides its bank. Usable only while the game has a package listing it resident: an enemy's sound in a mission against that faction, a primary weapon's while a player carries it. |
| `designed_rpm` | The rate its weapon was designed for. |
| `range_m` | How far its farthest layer carries, in metres. A heuristic reading of the bank's attenuation curves: a lead, not a measurement. |
| `pelican_default` | The Pelican chin gun's own sound. |

`sdk/WeaponSoundCatalogue.json` holds the same catalogue for tools (ModBuilder): the per-layer ranges, the bank's name,
the fire mode and how many types each entry folds.

## A Pelican gun's sound

```lua
hd2.pelican.spawn({position = p, hover = 60,
    gun = {behave_as = 'gatling_sentry', round = 'ap4', sound = 'sentry/gatling'}})
-- or, in a custom stratagem: pelican = {hover = 60, gun = {behave_as = 'gatling_sentry', sound = 'vehicle/bastion/hmg'}}
```

Any `'shot'` or `'loop'` sound works. The chin gun's own weapon copy takes the sound's fields; nothing shared changes:

- **A shot** replaces its per-shot event. A MIDI sound also switches its posting to MIDI notes, and the gun keeps its
  audio source for the notes still scheduled when it stops (as the game itself does for a MIDI weapon).
- **A loop** gives it a loop start and a loop stop and no per-shot event, as the loop weapons' own records hold them.
  The game starts the loop when the gun starts firing and stops it when the gun stops (once its last shot's interval
  has run out). On another machine that happens on the trigger the host replicates, so every machine hears the loop
  start and stop with the host's fire.
- **`'pelican/chin_autocannon'`** (or no `sound`) leaves the gun's own sound.

The sound is written only while the gun is quiet (no trigger, no shot, no loop playing, no note scheduled). If the gun
is already firing, it is written the next time it stops.

**Its package.** The sound's bank must be loaded:

- with a `stratagem`, the Runtime requests that stratagem's call-in package (a custom stratagem lists it as an asset, so
  every machine loads it before the first call). A Pelican waits up to 10 s for it; a slower package follows as soon as
  it is resident;
- a `resident_only` sound is used only if the game has its package resident at that moment; otherwise the gun keeps its
  own sound (`ASSET_UNAVAILABLE` in the log).

**Several players.** Every machine posts its own shots' sounds from its own copy of the gun, so every compatible
Runtime applies the same sound on its own copy (deferred until its bank is resident there and the gun is quiet).
Machines without the Runtime hear the Pelican's own sound.

### The four example builds

| sound | kind | its bank | its package |
| --- | --- | --- | --- |
| `sentry/gatling` (the A/G-16 Gatling Sentry) | loop, 1600 RPM design, about 160 m | `stratagems_sentry_gatling` | the Gatling Sentry's (`gatling_turret`, 9.2 MB) |
| `vehicle/maelstrom/main_gun` (the TD-110 Maelstrom) | shot, MIDI, 1200 RPM design, about 650 m | `vehicle_storm_tank` | the Maelstrom's (`tank_storm`, 55.9 MB) |
| `pelican/chin_autocannon` (its own) | shot, 300 RPM design, about 650 m | `vehicle_shuttle` | none (nothing is written) |
| `vehicle/bastion/hmg` (the TD-220 Bastion's HMG) | shot, MIDI, 600 RPM design, about 650 m | `wep_heavy_machinegun` | the E/MG-101 HMG Emplacement's (`manned_turret`, 7.4 MB; it holds the same bank as the Bastion's 49.5 MB package) |

## A sentry's sound (`sentry.weapon.sound`, 2026-10-07)

A custom stratagem's sentry takes a catalogue sound on its own weapon copy too (runtime/custom_weapons.lua): the same
fields as the Pelican gun's, written from exactly its type's own catalogued sound (the A/MG-43 Machine Gun Sentry's
`sentry/machine_gun` loop) to the chosen sound's, while it is quiet, in the same transaction as its round. HeavyMgSentry
0.3.2 fires `support/mg206` (the MG-206's per-shot MIDI event; its bank is in the MG-206's own package, which its round
already loads). NOT live-tested.

## A weapon's own firing sound (`weapon.sound`, offline only)

`hd2.fields.weapon.sound` changes the firing sound of a player weapon (`hd2.weapon(name)`) or a support weapon
(`hd2.support_weapon(name)`) through `hd2.patch`, `hd2.transaction` and `hd2.ensure`. The value is a catalogue sound
name (`'support/mg206'`, `'sentry/gatling'`), never an id. **Offline only / not live-tested.**

```lua
hd2.patch({
    id = 'mg43-hmg-sound',
    target = hd2.support_weapon('MG-43 Machine Gun'),
    field = hd2.fields.weapon.sound,
    expect = 'support/mg43',          -- the weapon's own catalogued sound
    value = 'support/mg206',          -- a MIDI shot: the MG-206's per-shot event
    allow_unverified_effect = true,   -- required: a template sound write is not live-tested
})
```

- **What it writes.** The weapon type's ProjectileWeapon record (the template a weapon is built from), exactly as a
  catalogue entry's writes on a Pelican chin copy, relative to the weapon's own record: a **shot** sets the per-shot
  event (+260) and the MIDI flag (+237) to the sound's and clears the loop start and stop (+252, +256); a **loop** sets
  the loop start and stop and clears the per-shot event and the MIDI flag. The three event slots and the MIDI byte are
  one guarded transaction, conflict-checked as one value. Nothing else of the record changes (its secondary events,
  silenced events and MIDI timing stay the weapon's).
- **Instantiation only.** Like `weapon.fire_rate`, the game copies the record when it builds a weapon: weapons built
  after the write (a new call-in, redeploy, reinforce, re-equip) post the new sound; one already built keeps its copy.
  Only this game hears it: every machine reads the events from its own copy of the record.
- **`expect`** is the weapon's own catalogued sound (`currentDefault` of `weapon.sound` in
  `sdk/PlayerWeaponAuthoringCapabilities.json` / `sdk/SupportWeaponAuthoringCapabilities.json`, or
  `weapon:describe()`): every weapon's own sound has its own name, by designation (`primary/ar23`, `support/mg43`).
  Restoring it (`value = expect`) writes the reviewed bytes back and needs no acknowledgement; every other sound
  requires `allow_unverified_effect`.
- **Its package.** Before the write the operation loads the sound's bank through its stratagem's call-in package (the
  same `asset_dependencies` gate a projectile swap uses; `ASSET_UNAVAILABLE` when it cannot be loaded). A
  `resident_only` sound (every primary and secondary weapon's, the enemies') and `'pelican/chin_autocannon'` are refused
  (`RESIDENT_ONLY_SOUND`): no package Runtime can load provides their bank. Choose from
  `hd2.sounds.list({stratagem = true})`.
- **Refused weapons**, each with its reason: no ProjectileWeapon record (beam, arc, spray, melee, thrown and placed
  weapons); fire mode 4 or 7 among its modes (those modes post another per-shot event, +268 / +272: VG-70
  Variable, DBS-2 Double Freedom, SG-22 Bushwhacker, MGX-42 Bullet Storm, SG-88 Break-Action Shotgun); suppressed or
  silenced-switched (they post the silenced events: AR-59 Suppressor, M6C/SOCOM Pistol, M7S SMG, R-72 Censor); a set
  WeaponData event-override table (+1040, unmapped: SG-20 Halt, SG-8 Punisher, SG-8S Slugger, SG-97 Sweeper, R-6
  Deadeye, M90A Shotgun); and the ambiguous identities every ordinary write refuses. A record more than one weapon
  builds from needs `allow_shared` (none of this build's).
- **Coverage.** 53 player weapons and 21 support weapons (`validation/weapon-sound-snapshot.json`: each one's
  reviewed baseline equals its record in the retained snapshot; a MIDI shot, a plain shot and a loop are written,
  read back and rolled back byte for byte on a copy-on-write overlay).

What is proven: the members the fire path reads (game.dll, the research above), the chin-copy writes (offline), the
weapon clone's copy of +260 (live). What is not: hearing any of it in game on a player or support weapon, a loop on a
semi-automatic weapon, and a MIDI shot at a rate its sound was not designed for.

## Status

Offline-tested only: the catalogue, the writes on the gun's own copy (host and other machines), the package gate, the
`weapon.sound` template writes (snapshot overlay) and the API. Not live-tested yet:

- how each sound sounds from the chin gun (its audio source sits at the turret's node; at the CAS rate a MIDI sound gets
  more notes than its own weapon would);
- a loop's start and stop on the host and on a client;
- that a resident package means the bank is loaded into the sound engine;
- the ranges (heuristic);
- any `weapon.sound` write on a player or support weapon.
