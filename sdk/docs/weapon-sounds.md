# Weapon firing sounds (`hd2.sounds`)

HD2Runtime names the firing sounds of the game's weapons so a mod can use them, today on a Runtime Pelican's chin gun.
The catalogue is read-only: it lists what exists, and a name is what a mod passes. No Wwise event, bank or package id
is ever returned or accepted.

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

## Status

Offline-tested only: the catalogue, the writes on the gun's own copy (host and other machines), the package gate and
the API. Not live-tested yet:

- how each sound sounds from the chin gun (its audio source sits at the turret's node; at the CAS rate a MIDI sound gets
  more notes than its own weapon would);
- a loop's start and stop on the host and on a client;
- that a resident package means the bank is loaded into the sound engine;
- the ranges (heuristic).
