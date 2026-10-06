"""Can two loadout slots hold the same stratagem type, and can the Runtime treat one of them as a virtual custom
stratagem? (docs/custom-stratagems.md, "Duplicate slots and virtual stratagems: research"). Read-only, offline: the
game.dll image and the seven retained snapshots of build F5FEE03DCFDB. Nothing is written. The third-party Stratagem
MultiSelect mod is a lead only: every claim here is proven in game code.

Proves, along picker -> save -> mission record -> HUD -> matcher -> call-in:

1. The picker refuses duplicates in the UI only. The grid builder marks each candidate card enabled (0x18D8B99) and
   clears that flag when the card's type is already in a slot of the loadout record being edited (0x18D8BCB..0x18D8BEC).
   Selection refuses a second vehicle of a category (StratagemInfo +0x104 bits, 0x146E5BF). The pick (0x189D050: slot
   index < 4, card key) sets the slot widget's type and draws that type's row icon (0x1893600). No later stage refuses a
   duplicate: MultiSelect only re-enables greyed cards through the game's per-card helper (0x18D1440).
2. Save and restore keep slots in order and do not deduplicate: one {stable id, uses} pair per slot (0x17513C1..), and
   the restore appends pairs in order (research/stratagem-identity-F5FEE03DCFDB.json). The peer sync writes slots by
   index (0x11E8360). The HUD list has one slot per record entry, each taking its entry's type.
3. Per-slot state: uses (slot +0x18C, 0x66D3D0), cooldown end (slot +0x1A0) and in-flight beacons keyed by
   (peer, slot index) (0x66D200).
4. Per-type state: the code. The matcher (0x66D8C0) takes each slot's type and copies THAT TYPE's code (0xA106C0);
   the per-player scrambler remaps the type, never the slot (0x66DDA3). It keeps ONE candidate per type (a type-indexed
   map, 0x66DC10): a second matching slot of the same type replaces the first only when it has more uses or the first
   is not ready (0x66DC3D..0x66DCAF). The player's input cannot choose between two slots of one type.
5. Presentation and payload are per type: the loadout slot widget, the HUD slot and the menu name read the type's row.

Output: research/stratagem-duplicates-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/stratagem-duplicates-F5FEE03DCFDB.json'
MULTISELECT = Path(r'C:\Users\Skye\Downloads\Stratagem MultiSelect (1)')

GAME = {
    'gridDuplicateDisable': [
        (0x18D8B99, 'mov byte ptr [rsp + r9*4 + 0x60], 1', None, 'each candidate card: enabled'),
        (0x18D8BBC, 'mov r8d, dword ptr [r13 + 0x788]', None, 'the loadout record being edited: its slot count'),
        (0x18D8BD9, 'cmp r10d, dword ptr [r13 + rcx*8 + 0x188]', None, 'the card\'s type against each slot\'s type'),
        (0x18D8BEC, 'mov byte ptr [rsp + r9*4 + 0x60], r12b', None, 'already selected: the card is disabled (greyed)'),
    ],
    'vehicleCategoryGate': [
        (0x146E5BF, 'test dword ptr [rax + 0x104], 0x400000', None, 'a slot already holds a vehicle of this category'),
    ],
    'pick': [
        (0x189D050, 'cmp edx, 4', None, 'the pick: a slot index below 4 ...'),
        (0x189D076, 'call 0x11f2490', None, '... and a card key, resolved to a type'),
        (0x189D08E, 'call 0x1893600', None, 'the slot widget takes the type'),
        (0x1893613, 'mov dword ptr [rcx + 0x128c], edi', None, 'slot widget: its type'),
        (0x1893650, 'mov rdx, qword ptr [rdi + 0xb0]', None, 'slot widget: its icon from the type\'s row'),
    ],
    'cardEnableHelper': [
        (0x18D1440, 'mov qword ptr [rsp + 0x10], rsi', None, 'the per-card enable helper MultiSelect calls'),
        (0x18D1480, 'cmp dword ptr [rcx + r9*4 + 0x92990], edx', None, 'finds the card by key'),
    ],
    'save': [
        (0x17513C1, 'mov eax, dword ptr [rdi + 0x788]', None, 'save: every slot of the record, in order ...'),
        (0x17513FE, 'mov rax, qword ptr [r10 + rax*8]', None, '... its type\'s row ...'),
        (0x1751402, 'mov eax, dword ptr [rax + 4]', None, '... stable id ...'),
        (0x1751408, 'mov eax, dword ptr [rcx]', None, '... and the slot\'s uses: one pair per slot ...'),
        (0x175140A, 'add rcx, 0x30', None, '... no duplicate check'),
    ],
    'matcher': [
        (0x66DADC, 'mov r8d, dword ptr [r15 + rcx*8 + 0x188]', None, 'the matcher: each slot\'s type'),
        (0x66DB9B, 'call 0xa106c0', None, 'the code of that TYPE (the row\'s), copied'),
        (0x66DBC9, 'cmp dword ptr [rsp + rdx*4 + 0x70], eax', None, 'compared with the input'),
        (0x66DC10, 'mov ebp, dword ptr [r13 + rsi*4]', None, 'one candidate per type: the type\'s entry'),
        (0x66DC3D, 'call 0x66d3d0', None, 'a second slot of the same type: the kept slot\'s uses ...'),
        (0x66DC4C, 'call 0x66d3d0', None, '... and this slot\'s uses'),
        (0x66DC51, 'cmp eax, esi', None, 'more uses ...'),
        (0x66DCAF, 'mov dword ptr [rsp + rbp*4 + 0xa0], r14d', None, '... or the kept slot not ready: this slot replaces it'),
        (0x66DCB9, 'mov dword ptr [r13 + rsi*4], r12d', None, 'a new type: a new candidate'),
        (0x66DDA3, 'add r14d, dword ptr [rax + r15 + 0x53ea68]', None, 'the scrambler remaps the TYPE per player ...'),
        (0x66DDB6, 'imul eax, edx, 0x95', None, '... modulo 149'),
    ],
    'perSlotState': [
        (0x66D3E5, 'mov eax, dword ptr [rdx + rcx*8 + 0x18c]', None, 'uses: per slot'),
        (0x66D24A, 'mov rcx, qword ptr [rsi + 0x1a0]', None, 'cooldown end: per slot ...'),
        (0x66D258, 'cmp rcx, qword ptr [rax + 0x18]', None, '... against the clock'),
        (0x66D28D, 'cmp dword ptr [r9 + rcx*8 + 0x18], r10d', None, 'in-flight beacons: keyed by (peer, slot index)'),
    ],
    'peerSync': [
        (0x11E8360, 'mov r14d, dword ptr [r12 + rdi*4 + 4]', None, 'peer sync: slot by slot, by index'),
        (0x11E8365, 'mov dword ptr [rcx + 0x188], r14d', None, 'no duplicate check'),
    ],
    'hud': [
        (0x183A053, 'mov edx, dword ptr [r9 + r12*8 + 0x188]', None, 'each HUD slot: its record entry\'s type'),
    ],
}


def multiselect_summary():
    """The lead's mechanism, as its own source states it (not proof)."""
    present = MULTISELECT.exists()
    return {'present': present, 'module': 'mods/OnlyTanks/stratagem_multiselect', 'core': ('every 3 frames, re-enables '
        'each card the grid greyed because its stratagem is already selected, through the game\'s per-card enable '
        'helper (located by a byte signature)'), 'vehicles': ('clears StratagemInfo +0x104 category bits '
        '0x00100000 / 0x00200000 / 0x00400000 on every row (a global row write)'),
        'notTouched': ['the saved loadout', 'the mission player record', 'the HUD', 'the matcher', 'executable code']}


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    game = base.Image(game_data, game_base, base.TEXT)
    pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'pins': pins,
        'pinnedBytesMismatchPerSnapshot': relocation, 'multiselect': multiselect_summary(),
        'slotIdentity': {'preserved': ['the loadout record (slot order)', 'the save (one pair per slot, in order)',
                'the restore (appended in order)', 'the peer sync (by index)', 'the HUD (one slot per record entry)',
                'uses, cooldown and in-flight beacons (per slot)'],
            'perType': ['the calldown code (the matcher copies the type\'s code)', 'the candidate choice (one per type)',
                'presentation (loadout slot widget, HUD slot, menu name)', 'the payload (the type\'s row)']},
        'determinations': {
            'duplicatesCoexist': ('Yes in game logic: only the picker UI greys a selected card; save, restore, '
                'mission record, peer sync and HUD keep both slots by index. Reaching it needs a write to the '
                'loadout UI state (the card enabled flag) or a native UI call.'),
            'matcherDistinguishesSlots': ('No for two slots of one type: they share the type\'s code and the matcher '
                'keeps one candidate per type, chosen by uses and readiness, not by the input.'),
            'differentCodes': 'No: the code is read from the type\'s row; no per-slot code exists.',
            'slotSpecificPresentation': 'No: every presentation reader takes the type\'s row.',
            'virtualStratagemRegistry': ('Not feasible without executable hooks: code, candidate choice, presentation '
                'and payload are all per type.')},
        'conclusion': ('Two slots can hold one type, but the game cannot treat them differently: the calldown code, '
            'the matcher\'s candidate choice, the presentation and the payload are properties of the type. A Runtime '
            'virtual stratagem on a duplicate slot is not possible without executable hooks.')}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; snapshots with mismatches',
        sum(1 for v in relocation.values() if v))


if __name__ == '__main__':
    main()
