# Custom images

A mod can give a stratagem its own icon. `hd2.resources.image(id)` names an image the mod ships, and
`hd2.fields.stratagem.presentation_icon` takes it as a value ([Stratagem presentation](stratagem-presentation.md)).

```lua
local icon = hd2.resources.image('orbital_gas_barrage_icon')    -- images/orbital_gas_barrage_icon.png
hd2.ensure({patch = {id = 'gas-barrage-icon', target = hd2.stratagem('Orbital 120mm HE Barrage'),
    field = hd2.fields.stratagem.presentation_icon, expect = 'Orbital 120mm HE Barrage', value = icon}})
```

Setting the value back to the stratagem's own name (or disabling the ensure) restores its icon.

## The image

- **File:** `images/<id>.png` in the mod project, an ordinary editable PNG. The id is 1 to 64 lowercase letters, digits
  or underscores.
- **Format:** a 256 x 256 PNG, not interlaced. The game's own icon textures are masks: R = the category-coloured art, G =
  the white art, on black. Ship either:
  - a mask: B = 0 and A = 255 everywhere. It is used exactly as given;
  - an ordinary red-and-white picture on a dark or transparent background. The build converts it to the masks
    automatically.
- **Build:** `py hd2.py build` compiles each PNG into the image's texture and GUI material. It packs them into the mod's
  own archive, under the mod's own name; the archive loads with the mod at startup and stays loaded. The ZIP also
  carries every editable `images/<id>.png` beside its manifest, outside the installed folder. Edit the PNG and rebuild to
  change the icon.

The handle names the image and nothing else. It holds no hash, file name or archive detail. The handle does not prove
the image is loaded; the check runs before each write.

## Editable source images

**Preparation.** The build reads each `images/<id>.png` and prepares it:
- **A mask** (B = 0 and A = 255 in every pixel) is used as given. Masks compile byte for byte as before.
- **Any other picture** is read as red-and-white icon art and converted to the masks:
  - red becomes R, white becomes G;
  - dark or transparent pixels become empty.

  It is converted in the build, never in the source file.
- **An image meant to be drawn exactly as given** (a diagnostic, for instance) is declared raw in `hd2runtime.json`:

  ```json
  "images": {"<id>": "raw"}
  ```

**The cache.** The compiled texture is cached per project in `build/.image-cache/`, keyed by:
- the conversion rule's version;
- the preparation (auto or raw);
- the SHA-256 of the PNG.

A rebuild reuses an entry while the PNG is unchanged. A changed PNG compiles again. An entry whose own digest fails is
never used.

**The build report.** `build-report.json` lists each image's file, its SHA-256 and how it was prepared.

**Why the build compiles, not the game.** The game loads a custom icon's texture and GUI material from the mod's archive
at startup, before any Lua runs. The Runtime never creates engine resources. A missing material crashed the loadout grid
(History, 0.9.0). So the conversion runs when the mod is built, and the running game reads what the build compiled.

## Guards

`presentation_icon` writes a custom image only when all of these hold. Otherwise the operation is refused before
anything is written (`ASSET_UNAVAILABLE`):

- **The game build:** every game reader of the icon member, and the material and texture lookups they reach, are the
  reviewed code.
- **The complete family:** the image's texture and its GUI icon material are loaded.
- **The exact material:** the material is exactly the icon material of its name, and it resolves to that texture.
- **No clash:** no atlas sprite of the game has its name.

The usual presentation guards also apply: the stratagem by its catalogue identity, its reviewed native icon, and a
guarded write that verifies the bytes around it. A custom image is a `presentation_icon` value only. The name,
cased name and description fields refuse it.

**When to apply:** aboard the ship, before the mission. The loadout screen builds its icons when it opens, and the
mission HUD builds each slot once per mission. A change made during a mission shows from the next mission
([Stratagem presentation](stratagem-presentation.md)).

**Multiplayer:** presentation is local. Other players see the stratagem's own icon.

## Why an image is a family

A stratagem's icon value names three things of one name:
- a **GUI material**, whose image property is that same name;
- an **atlas sprite**, on the shared stratagem icon atlas;
- a standalone **texture**.

Every vanilla icon is a loaded material and an atlas sprite. The loadout grid draws the icon as the GUI material, and
that path has no fallback. So the SDK builds every image as:
- a 256 x 256 BC1 texture, in the format of the game's icon textures;
- a GUI icon material: the vanilla icon material, the same for all 111 vanilla icons except that its one slot names
  this image's texture.

No atlas sprite is needed: every path that asks for one also handles its absence.

| Consumer of the icon value | Needs | If missing |
| --- | --- | --- |
| Loadout grid entries and other material widgets (4 readers, 8 widget kinds) | a **GUI material** of that name | null material, **crash** |
| ... their pixels | an atlas sprite, else the material's slot texture by name | missing-texture fallback |
| Material-slot images (3 readers) | the material's slot texture name | missing-material fallback |
| Image widgets (4 readers) | an atlas sprite, else a **texture** of that name | missing-texture fallback |

Evidence:
- `research/stratagem-icon-consumers-F5FEE03DCFDB.json`: every reader of the icon value;
- `research/stratagem-icon-family-F5FEE03DCFDB.json`: the material format and the lookups, pinned and checked on all
  seven retained snapshots;
- `research/image-resources-F5FEE03DCFDB.json`: the texture format, the archive and loading.

## History

- **0.9.0 (2026-10-01): crash.** A texture-only image crashed the game when a loadout slot was opened. The loadout
  grid looked the icon up as a GUI material, got null, and the engine read through it.
- **0.10.0 (2026-10-02): read-only probe, PASS.** The running game loaded the complete family from the mod's archive,
  and its material resolved to the custom texture.
- **0.11.0 (2026-10-02): write, LIVE VERIFIED.** The guarded write set only the Orbital 120mm HE Barrage's icon member,
  aboard the ship:
  - the loadout UI, including the loadout grid, drew the custom icon;
  - the carrier kept its type, stable id, name and description;
  - the mission loadout stayed valid, the restore worked, and nothing crashed.

  The guards of that development write are now the public field's guards.

Live-proven on the Orbital 120mm HE Barrage. Every other stratagem uses the same member and readers, but is not
individually tested.
