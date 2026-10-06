# SelectionSoundProof 0.1.0 (development only): identify the native selection sound

**No memory write, no selection, no native call.** A key plays one of the loadout screen's own UI sound events through
the engine's Wwise Lua API. Nothing plays unless a key is pressed.

- **The call:** `stingray.WwiseWorld.trigger_event(stingray.Wwise.wwise_world(world), name)`.
- **The world:** the game's own "Game World", the one whose sound world the game posts its UI sounds on. It is matched
  by its exact address, and nothing plays without that match.
- **The name:** a string whose FNV-1 hash is the game's event id. Wwise posts that id, so it is the very same event the
  game plays, not an imitation.

Research (`docs/custom-stratagems.md`, "The selection sound"):
- **When the selector moves on:** a native pick that leaves an empty slot posts no sound of its own. A panel transition
  after it may play one, but its ids are not readable offline.
- **When a pick fills the last slot:** the game posts the picker-close event, and the same event on Back.
- **When a slot is selected and the grid opens:** the slot-select event.

This proof lets you hear each one and tell which is the selection sound you expect.

**Which build is running:**
- the first log line is `SelectionSoundProof 0.1.0 UI SOUND IDENTIFICATION BUILD: ...`;
- F9 prints `F9 [0.1.0 UI SOUND IDENTIFICATION]`.

## Keys

| Key | Event |
| --- | --- |
| F5 | picker close (event 0x0DBB2A14) |
| F6 | slot select / grid open (event 0x3C38FC71) |
| F7 | `ui_generic_select` |
| F8 | `ui_armory_item_hover_select` |
| F9 | status: the API, the Game World match, each event known to the sound engine (nothing plays) |

## Live test

Install the HD2Runtime runtime ZIP and `SelectionSoundProof-0.1.0.zip` only. Solo, aboard the ship, no mission.

1. Press **F9** and note the status line.
2. **Natively**, in the loadout screen, listen to:
   - a stratagem selection that leaves an empty slot;
   - a selection that fills the last slot;
   - selecting a slot (the grid opening);
   - Back.
3. Press **F5, F6, F7 and F8** one at a time. For each, say which native sound from step 2 it matches, or none.

Send the `SelectionSoundProof` and `[HD2Runtime] ui sound` lines and your notes.
