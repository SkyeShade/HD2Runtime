# Custom text

**Status: live-verified through the development path; not public yet.** A mod's own stratagem name and description
("Orbital Gas Barrage") are Runtime-owned text. CustomStratagemP0Proof 0.12.0 (2026-10-02) showed them in the ship
loadout and the mission on the Orbital 120mm HE Barrage, and registered the text again after language changes (live
evidence family `stratagem_presentation_custom_text`). It is still not public:
- `hd2.resources.text` does not exist;
- the public presentation fields refuse a Runtime text value.

The development path is `runtime/stratagem_presentation.lua` `apply_text`. Making it public is a separate step.

It never borrows, overwrites or replaces a game text. Evidence: `research/stratagem-text-F5FEE03DCFDB.json`
(`scripts/research_stratagem_text.py`), proven on the helldivers2.exe and game.dll of build F5FEE03DCFDB, all retained
snapshots and the game's 264 text resources.

## How the game shows a stratagem's text

**The row holds ids.** A StratagemInfo row holds three text ids: +0x28 the name, +0x2C the cased name, +0x30 the
description. An id is the upper 32 bits of MurmurHash64A (seed 0) of a key.

**One lookup.** Every reader resolves an id through one function, `helldivers2.exe 0x321C40` (GUI API +0x3E0 / +0x3E8):

| Text | Reader | Lookup |
| --- | --- | --- |
| Mission stratagem menu name | `0x66D559` (+0x28) | its callers, `0x1837087` and `0x1838D72` (+0x3E8) |
| Loadout details name | `0x179D95D` / `0x179D962` (+0x28 / +0x2C) | a text argument (kind 0xA, `0x143A110`) the formatter `0x13006A0` looks up (`0x1300905`) |
| Loadout details description | `0x189FBD0` (+0x30) | `0x191FCE0` → `0x143A030` → `0x13006A0`, looked up at `0x1300795` |

**The registry.** The lookup reads the text registry `[exe+0x1A101E0]`: `{u32 count, u32 capacity, table pointers,
allocator}`.
- It reads the count and the array once.
- It walks the tables in order. In each, it binary-searches the current language, then the id.
- The first table holding the pair wins. If none does, the text is empty (never a crash).
- `0x321C40` is the only code that reads the registry's entries.

**The table format** (`scripts/hd2_text.py`), reproduced byte for byte for all 264 game text resources:
1. a header: `0x3E85F3AE`, the language count, the id count;
2. the language hashes, ascending;
3. the ids, ascending;
4. language-major offsets from the table start (0 = absent);
5. NUL-terminated UTF-8 texts.

**Who registers.** Only the game's language routine, `game.dll 0x12FEDC0`. A scan of every game.dll use of the
registry functions finds no other add, clear or set-language call.
- **At startup:** it registers `localization/<base>_<language>` for 17 fixed bases (two do not exist in this build) and
  the voice-over phonetics. Every retained snapshot holds 17 tables in an array of capacity 18.
- **On a language change** (`0x12FF050`): it sets the language, clears the registry (count 0; the array and its
  capacity are kept) and registers its own tables again. Any other table is dropped.
- **Thread:** the change runs inside the game update (`0xAB5000`, called by the plugin entry point `0x4EE6C0` with the
  frame time).

## The Runtime's text

**One table for every mod.** The Runtime builds one text table holding every mod's texts in all 15 game languages.
It registers that table by appending its pointer to the registry, after the game's tables:

- **The append:** the slot first, then the count, through the guarded transaction, which re-proves the registry
  before each write. A reader sees either the old count, or the new count with the slot already written.
- **Spare capacity only.** The Runtime never grows, reallocates or frees the game's array. Only the game does that, at
  startup. There is one spare place in every snapshot, and one table holds all mods' texts, so that place is enough.
- **Never a game entry.** No game table, entry or registration is changed. When texts change, a new Runtime table
  replaces the Runtime's own pointer.
- **Memory that is never freed.** The table lives in Runtime-owned read-only memory that stays allocated even after the
  Lua state closes, because the game may keep a pointer to a text it looked up. Old tables also stay allocated.
- **After a language change.** The game drops the table. While a row shows Runtime text, the Runtime registers it again
  on the next update, once the registry is unchanged over two updates. If that is refused, the carrier's own text is
  restored, so nothing shows blank.

**A full registry (0.30.2).** Every retained snapshot holds 17 tables in an array of capacity 18, and one Runtime
table holds every mod's texts, so the number of mods never matters. When the place is taken anyway, `REGISTRY_FULL`
is refused and one read-only line is logged, `text REGISTRY FULL (read-only diagnostic: what holds each place)`,
naming each table: a game table (by name when English), a table in the Runtime format that this Runtime did not
register (another HD2Runtime copy, or one loaded earlier in the session), or another shape. The game grows its
array only through its own allocator (and frees the old array through it), so the Runtime never grows it with its
own memory.

A custom stratagem whose text is refused this way still runs (0.30.2): its carrier keeps its own name and
description and takes the custom icon and code (`carrier presentation TEXT FALLBACK: ...`). Every other text refusal
still refuses the presentation.

**Ids.** A text's key is `<mod resource id>/text/<id>`, hashed the way the game hashes its own keys:
- mod-local: another mod's text of the same id has another id;
- never published.

**Languages.** The game's 15 text languages are `us`, `gb`, `bp`, `de`, `es`, `fr`, `it`, `jp`, `ko`, `ms`, `pl`, `pt`,
`ru`, `cn` and `tc`, the codes of the game's own language table. The research records the 120mm's name in each, which
shows the language: for example `BARRAGEM ORBITAL DT DE 120 mm` under `bp`, `DESCARGA AE DE 120 MM ORBITAL` under
`ms` and `軌道120mm高爆彈彈幕` under `tc`.

A text gives a `default` (used for every language it does not give), and may add texts for any of those codes. Every
language therefore shows the mod's text, and none shows blank.

## Guards

Before anything is registered or written, every condition must hold. Otherwise it is refused with nothing written:

| Code | Refused when |
| --- | --- |
| `UNSUPPORTED_BUILD` | the registry code, its only registrar, the language change path, or a consumer path differs (64 pins) |
| `UNAVAILABLE` | the game has not registered its text or set a language yet |
| `UNSUPPORTED_LANGUAGE` | the current language is not one of the 15 |
| `ID_COLLISION` | a game table already holds a Runtime id |
| `REGISTRY_FULL` | the registry has no spare capacity |
| `REGISTRY_CHANGED` | the registry changed between reading and writing, or is not private read-write memory |
| `VERIFY_FAILED` | after the write, a text does not resolve exactly; the registration is undone |
| `CONFLICT` | a carrier text member is not its reviewed native id |

**Defining texts.** Two keys of one mod with the same id are refused. So is the same id redefined with other text.

**After the write**, the presentation write checks:
- the ids read back, and each text resolves, in the current language, to exactly its own text;
- the identity, the icon and any text member not given are unchanged;
- non-target bytes are unchanged and the protection is restored.

If any check fails, it restores at once.

**Restore:** it writes the native ids back. It also takes the Runtime table out of the registry when it is the last
entry; the table stays allocated.

## Timing and limits

- **Apply aboard the ship, before the UI that shows it is built.** The loadout screen builds its texts when it opens,
  and the mission HUD builds its slots once per mission. A change made during a mission shows from the next mission. The
  HUD is never hot-swapped.
- **A language change while Runtime text is shown.** The game rebuilds its registry, refreshes its text, and only then
  lets the Runtime register again (the next update). Text that the game rebuilt in that update may show blank until its
  screen is rebuilt. Whether the refresh is immediate is not proven offline; the live proof checks it.
- **Multiplayer:** presentation is local. Other players see the stratagem's own text.
- **Live-proven** (CustomStratagemP0Proof 0.12.0): the game drawing Runtime text in the ship loadout and the mission,
  and the registration again after language changes. English (default) text on the 120mm only.

## Planned public API

```lua
local name = hd2.resources.text('gas_barrage_name', 'ORBITAL GAS BARRAGE')
local desc = hd2.resources.text('gas_barrage_desc', {default = 'Calls down a barrage of gas shells.',
                                                     fr = 'Déclenche un barrage d\'obus à gaz.'})
hd2.ensure({transaction = {id = 'gas-barrage-text', target = hd2.stratagem('Orbital 120mm HE Barrage'), changes = {
    {field = hd2.fields.stratagem.presentation_name, expect = 'Orbital 120mm HE Barrage', value = name},
    {field = hd2.fields.stratagem.presentation_description, expect = 'Orbital 120mm HE Barrage', value = desc}}}})
```

The handle hides the id, the key, the registry and the table. The guards above become the fields' guards.

## Evidence and tests

- `research/stratagem-text-F5FEE03DCFDB.json`: the pins, the registry in every snapshot, the registrar scan, the format
  rebuild, the language table and the proof ids (none collides with any of the game's 24 827 ids).
- `tests/test_custom_text.py`: the format, the Lua table equal to `scripts/hd2_text.py`'s, the handles, registration,
  every refusal, a language change, replacement, and the presentation path with its restore and guards.
- `scripts/validate_stratagem_calldown_snapshot.py`: on every retained snapshot the proof's texts register as the 18th
  table, resolve exactly and restore.
- `scripts/validate_packaged_runtime.py` (`proof-text-write`, `proof-text-write-refused`): the shipped artifact on the
  snapshot's real registry.
