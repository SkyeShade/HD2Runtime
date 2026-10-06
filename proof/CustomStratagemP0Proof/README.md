# CustomStratagemP0Proof 0.12.0 (development only): the custom text write proof

This build makes the **Orbital 120mm HE Barrage** present as the **Orbital Gas Barrage**:

| What | Value | Through |
| --- | --- | --- |
| Name | `ORBITAL GAS BARRAGE` | Runtime-owned text, the development path (`runtime/stratagem_presentation.lua` `apply_text`) |
| Cased name | `Orbital Gas Barrage` | the same |
| Description | `Calls down a barrage of gas shells.` | the same |
| Icon | this proof's custom icon (checkerboard, green X in a green frame) | the public `presentation_icon` with `hd2.resources.image` |
| Calldown code | Up Up Down Down | the public `calldown_code` |

**Never written:** the payload, cooldown, stable id and type; account items, inventory and the loadout; the HUD.
Calling it in fires the **normal 120mm barrage**.

The public presentation fields do not take custom text yet. This proof is the live test that decides whether they will.

## The custom text

The texts are one Runtime-owned text table ([Custom text](../../docs/custom-text.md)). It is appended after the game's
own text tables in the game's text registry, using a spare place the game leaves there:

- no game text table, entry or registration is changed, and the game's array is never grown;
- the ids are this mod's own: `<mod>/text/<id>`, hashed as the game hashes its keys, and absent from every game table;
- the table holds all 15 game languages; this proof gives English text, which every language shows.

## Guards before the text write

If any guard fails, the write is refused and nothing is written.

1. The game build, the presentation readers, the text registry code, its only registrar and every text consumer path
   (pins).
2. The carrier row by catalogue identity, with its exact native name, cased name and description.
3. The Runtime text table registered, or registered now, with none of its ids in a game table.
4. Each text resolving, in the current language, to exactly its own text.

**After the write**, the proof checks:
- the ids read back, and each resolves to its text;
- the identity, the icon and any text member not given are unchanged;
- non-target bytes are unchanged and the page protection is restored.

If any check fails, it restores at once. While the text is applied, the Runtime keeps its table registered: the game
drops it on a language change, and the Runtime registers it again on the next update. If that is refused, the 120mm's
own text is restored so nothing shows blank.

## Restore

**MODS > Custom Stratagem Proof**, aboard the ship:
- **"Custom text"** off + APPLY: the 120mm's own name and description, and the Runtime table taken out of the registry;
- **"Custom icon and code"** off + APPLY: its own icon and code.

The mission HUD builds each slot once per mission and keeps it. A finalizer also restores the text before the Lua state
closes. Without Mod Options Menu nothing is applied.

**Which build is running:**
- the first log line is `CustomStratagemP0Proof 0.12.0 CUSTOM-TEXT-WRITE BUILD: ...`;
- the mod manager lists `CustomStratagemP0Proof 0.12.0`;
- F9 prints `F9 [0.12.0 CUSTOM-TEXT-WRITE]`.

Build with `py scripts/build_custom_projectile_proof.py --only CustomStratagemP0Proof`.

## Live test

Solo, as host. Do not test multiplayer.

1. Remove every older CustomStratagemP0Proof. Install the HD2Runtime runtime ZIP and `CustomStratagemP0Proof-0.12.0.zip`
   from `build/test-artifacts/`.
2. **Before any text write:** aboard the ship, check the build line and the `text probe (before any text write):` block
   with `TEXT PROBE RESULT: PASS`.
3. **The writes:** wait for:
   - `custom icon and code (public ensure): ... APPLIED`;
   - `[HD2Runtime] stratagem presentation custom text APPLIED: Orbital 120mm HE Barrage (type 136, stable id 1063322614):
     name 0x4FAAD695 -> ... "ORBITAL GAS BARRAGE"; ...`, whose checks must all say `true`;
   - `custom text APPLIED aboard the ship ...`.
4. **Ship UI:** open the loadout screen. The 120mm's entry should show the custom icon. Its details should show
   **Orbital Gas Barrage** and **Calls down a barrage of gas shells.** Open a stratagem slot so the grid is built.
5. Select it and leave the screen. The `saved ship loadout` line should name `Orbital 120mm HE Barrage (type 136, stable
   id 1063322614)` and say the row `holds the Runtime text and the custom icon`.
6. **Mission HUD:** start a solo mission. Check the `record entry` line (`its text shows: name "ORBITAL GAS BARRAGE"`,
   ...) and the `HUD slot` line. Then open the stratagem menu. The slot should show **ORBITAL GAS BARRAGE**, the custom
   icon and Up Up Down Down.
7. **Normal 120mm:** enter Up Up Down Down and confirm the normal 120mm barrage.
8. **Optional, the language change:** after the mission, aboard the ship, switch the game's text language and back. Each
   change should log `the game rebuilt its text registry (language us -> ..); Runtime text registered again`. Then
   reopen the loadout screen: the custom name and description show in every language. Screens open during the change
   may show the text blank until they are reopened (docs/custom-text.md).
9. **Restore:** aboard the ship, switch both toggles off and APPLY. Check the `RESTORED` line, whose checks must all
   say `true` and which ends with `Runtime text table unregistered`, and the ensure's restore line. Reopen the loadout
   screen: the 120mm shows its own name, description and icon.

**If the game crashes:** stop and do not retry. Send `%APPDATA%\Arrowhead\Helldivers2\dumps\` (the newest `.dmp`),
`%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\HD2Runtime.log`, and the last step you did.

Send:
- every `CustomStratagemP0Proof` and `[HD2Runtime]` line;
- an F9 line from the ship and one from the mission;
- what the loadout screen (step 4), the stratagem menu (step 6) and the loadout screen after the restore (step 9)
  showed. Screenshots help.
