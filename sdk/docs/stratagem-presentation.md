# Stratagem presentation

Four public fields set how a stratagem **looks**: its name, cased name, description and icon. The stratagem stays
itself, with the same type, stable identity, loadout entry, calldown code, cooldown and payload. Only what the
loadout screen and the in-mission stratagem menu show changes.

| Field | Shows |
| --- | --- |
| `hd2.fields.stratagem.presentation_name` | the upper-case name (loadout screen, in-mission stratagem menu) |
| `hd2.fields.stratagem.presentation_name_cased` | the cased name (loadout details) |
| `hd2.fields.stratagem.presentation_description` | the description (loadout details) |
| `hd2.fields.stratagem.presentation_icon` | the icon (loadout slots and grid, in-mission stratagem HUD) |

```lua
-- The Orbital 120mm HE Barrage looks like the Orbital Gas Strike; it is still the 120mm.
hd2.ensure({transaction={id='120mm-looks-like-gas', target=hd2.stratagem('Orbital 120mm HE Barrage'), changes={
    {field=hd2.fields.stratagem.presentation_name,        expect='Orbital 120mm HE Barrage', value='Orbital Gas Strike'},
    {field=hd2.fields.stratagem.presentation_name_cased,  expect='Orbital 120mm HE Barrage', value='Orbital Gas Strike'},
    {field=hd2.fields.stratagem.presentation_description, expect='Orbital 120mm HE Barrage', value='Orbital Gas Strike'},
    {field=hd2.fields.stratagem.presentation_icon,        expect='Orbital 120mm HE Barrage', value='Orbital Gas Strike'}}}})
```

## Values: existing vanilla resources

- **A value names a catalogued stratagem**, either as a string or as `hd2.stratagem(name)`. The field takes that
  stratagem's own value of the same kind: its name, cased name, description or icon. These are existing vanilla
  resources the game keeps loaded.
- **Valid sources** are listed in `presentationSources.stratagems` in `sdk/StratagemAuthoringCapabilities.json`: all
  94 call-in stratagems.
- **`expect` is the stratagem's own name**, its native presentation. Setting the value back to its own name restores
  the original.
- **No raw values:** raw localization ids and image hashes are never published and never accepted. A number, a hash
  string or another kind of target is refused at registration.
- **Fields can be mixed.** Name, description and icon can each come from a different stratagem.
- **One operation group.** The four fields share it with `definition_cooldown`, `max_uses` and `calldown_code`, so one
  transaction can change a stratagem's presentation, code and cooldown together.

There is no category or beacon-colour field. Those members also choose the loadout tab, the HUD colour set and an
index the game does not range-check, so they stay out until their safety is established separately.

**A mod's own icon:** `presentation_icon` also takes `hd2.resources.image(id)`, an image the mod ships
([Custom images](custom-images.md)). The write is refused unless the image's complete icon family is loaded. Custom
text is not public yet; see [Custom resources](#custom-resources).

## When to apply

**Aboard the ship, before the mission.**

- **The loadout screen** reads the presentation when it builds its widgets. Open (or reopen) the loadout screen
  after the change.
- **The mission HUD** builds each stratagem slot's visual once, from its type, when the mission starts. A change made
  during a mission shows in the menu's name at once, but the slot keeps its icon until the next mission.
- **The HUD cache is never written.** Applying aboard the ship lets the game's normal HUD construction use the new
  presentation.

## Guards and restore

- **Build:** every reader of the four members must match the reviewed code of this game build. Otherwise the write
  is refused ("stratagem presentation unavailable on this game build").
- **Identity:** the stratagem is found by its catalogued identity (stable id and package), never by a type number.
- **Exact values:** each member must hold its reviewed native value, or the value this same operation wrote. A value
  written by anyone else is a `CONFLICT`, and nothing is written.
- **Nothing else is touched:** only the member's own bytes change, through the guarded transaction. The type, stable
  id, calldown code, cooldown, payload, account items, inventory and loadout slots are never written.
- **Restore:** an `hd2.ensure` disabled through its `enabled` toggle, or a rolled-back transaction or plan, writes the
  exact native values back. A value someone else changed in between is refused, not overwritten.

## Metadata

`sdk/StratagemAuthoringCapabilities.json`:

- **One field instance per stratagem and field** (94 each):
  - `type: "stratagem_presentation"`, `valueKind: "stratagem"`;
  - `resourceType` (`localization` for the names and the description, `image` for the icon);
  - `currentDefault`, the stratagem's own name;
  - `valueSource` and `applyTiming`;
  - `customValues: "image"` on `presentation_icon`;
  - `liveEvidence` where proven.
- **`presentationCapability` per stratagem:** the four field constants, their resource types, `applyTiming:
  "aboard_the_ship"`, and live evidence. The two non-call-in entries carry a `reason` instead.
- **`presentationSources.stratagems`:** the valid values.
- **`presentationSources.customImages`:** the custom icon capability: its API, source file, guards, refusal and live
  evidence.
- **The summary** counts them as `presentationWritable`.

## Live evidence and limits

- **Live-proven** (`stratagem_presentation`, 2026-10-01, solo host): the Orbital 120mm HE Barrage with the Orbital
  Gas Strike's name, cased name, description and icon.
  - The ship loadout showed the Gas Strike's presentation and still selected the 120mm.
  - The mission HUD showed it.
  - The calldown code and the normal 120mm barrage were unaffected.
  - Restoring brought the 120mm's own presentation back.
- **Tested paths:** first a development module that writes the same members, then the public fields themselves
  (`hd2.ensure`, CustomStratagemP0Proof 0.8.0).
- **Custom icons** (`stratagem_presentation_custom_image`, live-proven 2026-10-02, CustomStratagemP0Proof 0.11.0):
  the 120mm with a mod's own icon family. The loadout UI drew it, the 120mm kept its identity, name and description,
  and the restore worked. An earlier texture-only image (0.9.0) crashed the loadout grid, which draws an icon as a GUI
  material; the SDK now ships every image as the complete family ([Custom images](custom-images.md)).
- **Not tested:** other stratagems and other sources (the same members and readers).
- **Multiplayer:** presentation is local; other players see the stratagem's own presentation.

## Custom resources

- **Icon:** `hd2.resources.image(id)`, public. See [Custom images](custom-images.md).
- **Text:** a mod's own name and description ("Orbital Gas Barrage") are Runtime-owned text the Runtime registers
  with the game's text lookup. Live-verified through the development path (CustomStratagemP0Proof 0.12.0); not public
  yet. See [Custom text](custom-text.md).

Neither ever overwrites a vanilla localization entry or texture.
