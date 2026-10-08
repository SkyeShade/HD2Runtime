# Custom models (HD2Runtime 0.30.0)

A mod can ship its own **model** for a custom weapon: a unit of its own name that the game loads beside the vanilla
one. The vanilla model is never replaced or edited. The Runtime points the custom weapon at the custom unit for one
mission only and restores it aboard the ship (`hd2.custom_stratagem`, `delivery.family = 'weapon'`;
[custom-stratagem-api.md](custom-stratagem-api.md)).

Live-tested on 2026-10-06 (solo host, `proof/LaserMaxigunExample` 0.1.1): the Talon round and the debug model were seen in play, and every record was restored exactly aboard the ship. Multiplayer is not tested (docs/live-evidence.md, `custom_stratagem_weapon_variant`).

## A model project file

`models/<id>.json` in the mod project. The id is 1 to 64 lowercase letters, digits or underscores.

```json
{"base": "M-1000 Maxigun", "palette": "debug"}
```

```json
{"base": "M-1000 Maxigun", "palette": {"all": "#FF2A2A", "rows": {"2": "#20E0FF", "6": "#FFFFFF"}}}
```

- **`base`** is the weapon whose unit the model derives from. The reviewed bases are listed in
  `sdk/ModelBaseCapabilities.json`; today that is the M-1000 Maxigun.
- **`palette`** sets the model's colours:
  - `"debug"` gives each of the base material's 8 colour zones its own bright colour: red, green, blue, yellow,
    magenta, cyan, white, orange. A first look also tells which zone is which part of the weapon.
  - `{"all": colour, "rows": {"<zone>": colour}}` sets colours as `"#RRGGBB"`; zones are `"0"` to `"7"`. A zone that
    is given no colour keeps the base's.

In Lua, the mod names its model with `hd2.resources.model('<id>')`.

## What the build makes

`hd2.py build` derives three resources from the base unit in **your installed game**. They take the mod's own names:

| Resource | Name | What it is |
|---|---|---|
| unit | `<mod>/models/<id>` | the base unit's exact bytes (its mesh, nodes, LODs), with its body material slot naming the material below |
| material | `<mod>/models/<id>/m_weapon` | the base body material's exact bytes, with its colour table (material LUT) naming the texture below |
| texture | `<mod>/models/<id>/lut` | the base material LUT (23 x 8 RGBA16F, 5 mips) with the palette in its base colour column; every other value is the base's |

**What stays the base's own.** The unit's bones, state machine, physics and animations, its other materials (shadow,
collision) and every other texture of the body material are the base's own resources, referenced by name. So the
custom model animates, spins up and links its ammo belt exactly as the base does.

**Where it ships.** The three resources go into a **patch of the base weapon's own package archive**
(`mod/b2c627b3ba7e0c0a.patch_0` for the Maxigun). They load exactly when the game loads that package, beside every
vanilla resource they reference, in the vanilla unit's own pattern.

**What else the ZIP holds.** The mod's own archive carries the build record `<mod>/hd2runtime_models`: the base, the
game build, the base unit and its SHA-256, the three names and their digests. The ZIP root also holds the
`models/<id>.json` source; the game never reads it.

**Checks and caching.**
- The installed base parts must be byte-identical to the reviewed ones (SHA-256 in `sdk/ModelBaseCapabilities.json`).
  If the game was updated or the base is modded, the build stops with the reason; the Runtime never guesses.
- The derived parts are cached in `build/.model-cache`, keyed by the model file, the base facts and the mod resource.
- To use another game folder, set `HD2_GAME_DATA` to its `data` folder.

The mod ZIP holds a derived copy of game data (the Maxigun's mesh, about 2.7 MB), built from your installation, as
HD2 model mods do.

## When the Runtime uses it

`runtime/model_resources.lua` `ready` is the whole guard. Before a custom weapon's UnitPath names the model, all of
these must hold; otherwise nothing is written:
- the mod's build record names this model;
- it was derived from the weapon being converted, on this game build, from the reviewed base unit;
- the unit, the material and the LUT are all **loaded** in the game's resource table (read exactly as the game's own
  lookup reads it).

`runtime/weapon_clone.lua` also re-proves the UnitPath consumer review on the running game.dll. That covers every
call site of the UnitComponent type lookup and every type-table read (research:
`research/docs/weapon-variants-F5FEE03DCFDB.md`).

`delivery.model_use = 'check'` only logs whether the model is ready (`MODEL READY` / `MODEL NOT READY`) and keeps the
vanilla model. Use it for a first live test that the patch loads.

## Limits

- **Shape.** The shape is the base's. A different mesh needs a unit made in a 3D tool on the base's skeleton (with
  its node names: muzzle, belt and backpack link); a later stage can take it as a model source.
- **Colour.** Only the base colour column of the LUT is set. The other columns (likely roughness, metalness and
  secondary colours) keep the base's.
- **Multiplayer.** Every machine must run the same mod build: the model's digest is part of the custom stratagem
  registry hash, and a machine without it fails closed (custom slots locked).
