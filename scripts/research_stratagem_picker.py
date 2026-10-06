"""Can the Runtime add a VISUAL stratagem card to the ship loadout picker: a second card that shows a Runtime-owned
custom name, icon and description but selects the native token stratagem (docs/custom-stratagems.md, "A virtual card in
the ship loadout picker: research")? Read-only, offline: the game.dll image and the seven retained snapshots of build
F5FEE03DCFDB. Nothing is written. The third-party Stratagem MultiSelect mod is a lead only: every claim here is proven in
game code. Constraint of the question: data writes only, no native calls or hooks, no StratagemInfo, account,
catalogue, inventory or save writes.

Proves, along open -> candidates -> cards -> presentation -> enabled state -> click -> selected type -> save:

1. The loadout UI exists only while the loadout screen does: ui = [[game+0x347CE38]+0xB0] (0x8745B9), the stratagem
   screen at ui+0xD2850 (0x146E0BC), its card list at screen+0x6D0 = ui+0xD2F20 (0x146E67D). In every retained snapshot
   [[game+0x347CE38]+0xB0] is 0: no snapshot holds a picker.
2. The card list is a generic list control rebuilt from scratch by the grid builder (0x18D8710, called when the grid
   opens for a slot, 0x146ED65): clear (0x18D27B0), list mode 3 (0x18D09D0), four cards per row (0x18D877F with
   0x18CDA40), one candidate per owned, selectable type 1..149 (0x136FC20), sorted, then one add per candidate
   (0x18D43A0) and the layout (0x18D44B0). An entry is a 32-bit catalogue item key (+0x92990), an enabled byte
   (+0x92DC2) and a badge byte (+0x92EC2), at most 256 entries, in rows (+0x92318) grouped by stratagem category
   (+0x92854). The add has no key check, but the builder makes one card per type. Neither the entry nor the card widget
   stores the type or the stable id.
3. Cards on screen are a virtualised pool (row widgets at list+0xB00, stride 0xAED0, four card widgets each, stride
   0x2B68). The realize pass (0x18D2B60) fills each visible card from its key (0x18D3801 -> 0x18CAFB0): key -> catalogue
   item -> stable id -> type (0x11F2490) -> StratagemInfo row; the icon is the row's +0xB0, bound as a GUI material by
   native code when the card is filled (0x18CB590 -> 0x18DC5D0; 0x19438AE -> 0x144F800). The card label is built from
   the item key (0x179C920). The detail panel (name, description, preview) is filled on every focus change from the
   focused key and its row (0x18D7210 -> 0x191D040 -> 0x11F2490). Realize runs on scrolling, navigation and focus moves.
4. The enabled byte gates a click (0x18CFA39 -> 0x18D2690). A confirm reads the key at the focused cell (0x18D5E59),
   stores it (screen+0x178C98, 0x18D5E68), refocuses the FIRST card with that key (0x18D5E81) and returns 3; the
   selection handler maps that key through the catalogue item to the type (0x146E1C9..) and writes the slot.
5. Enabled state: the builder disables a card whose type is in the record being edited. After a pick, the refresh
   (0x18D1890) enables every entry, then, per record entry, calls the per-card helper (0x18D1440, the one MultiSelect
   calls) with enabled 0: it disables the FIRST entry with that key, flips the realized card's flag (+0x2B5A bit 2) and
   redraws it (0x18CA560, native). A realize redraws a card from its enabled byte (0x18D374A -> 0x18CDF30).

Output: research/stratagem-picker-F5FEE03DCFDB.json.
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

OUTPUT = ROOT / 'research/stratagem-picker-F5FEE03DCFDB.json'
MULTISELECT = Path(r'C:\Users\Skye\Downloads\Stratagem MultiSelect (1)')
G_LOADOUT_UI_OWNER = 0x347CE38      # [owner+0xB0] = the loadout UI while it exists
UI_ROOT = 0xB0
CARD_LIST = 0xD2F20                  # ui + 0xD2850 (stratagem screen) + 0x6D0 (its card list)
ADD_CARD = (0x18D43A0, 0x18D44AE)    # the list's add, whole body

GAME = {
    'loadoutUi': [
        (0x8745B9, 'mov rax, qword ptr [rip + {rip}]', G_LOADOUT_UI_OWNER, 'the loadout UI owner'),
        (0x8745C0, 'mov rcx, qword ptr [rax + 0xb0]', None, 'its UI object (0 when no loadout screen exists)'),
        (0x146E0BC, 'add rcx, 0xd2850', None, 'the stratagem screen inside the UI'),
        (0x146E67D, 'lea rcx, [rdi + 0xd2f20]', None, 'its card list (screen + 0x6D0)'),
    ],
    'gridBuild': [
        (0x146ED65, 'call 0x18d8710', None, 'the grid opens for a slot: the builder (screen, slot key, record)'),
        (0x18D8A78, 'call 0x18d27b0', None, 'the card list is cleared'),
        (0x18D8A8B, 'call 0x18d09d0', None, 'list mode 3 (stratagems)'),
        (0x18D877F, 'mov byte ptr [r15 + 0x92fd1], 1', None, 'four cards per row'),
        (0x18CDA70, 'mov eax, 4', None, 'row capacity: four'),
        (0x18D8AB5, 'call 0x136fc20', None, 'each type 1..149: owned and selectable'),
        (0x18D8BF1, 'mov eax, dword ptr [r11 + 4]', None, 'the candidate\'s catalogue item key ...'),
        (0x18D8BF8, 'mov dword ptr [rsp + r9*4 + 0x50], eax', None, '... is the card\'s identity'),
        (0x18D8BFD, 'mov eax, dword ptr [rbx + 0xb8]', None, 'its section: the row\'s category'),
        (0x18D8C0A, 'mov dword ptr [rsp + r9*4 + 0x58], eax', None, 'its type: used to sort only'),
        (0x18D8C40, 'call 0x20be230', None, 'candidates sorted'),
        (0x18D8C75, 'call 0x18d43a0', None, 'one add per candidate (key, section, enabled, badge)'),
        (0x18D8C8B, 'call 0x18d44b0', None, 'layout, scroll extent and realize'),
    ],
    'cardList': [
        (0x18D43B3, 'cmp r11d, 0x100', None, 'at most 256 cards'),
        (0x18D43CD, 'cmp ebx, dword ptr [r10 + rax*4 + 0x92854]', None, 'a new section starts a new row'),
        (0x18D4437, 'mov byte ptr [rax + r10 + 0x92dc2], r9b', None, 'entry: enabled byte'),
        (0x18D444B, 'mov byte ptr [rcx + r10 + 0x92ec2], al', None, 'entry: badge byte'),
        (0x18D445A, 'mov dword ptr [r10 + rax*4 + 0x92990], edx', None, 'entry: the key, nothing else'),
        (0x18D4469, 'inc dword ptr [r10 + 0x92984]', None, 'card count'),
        (0x18D4470, 'inc dword ptr [r10 + rax*4 + 0x92318]', None, 'the row\'s card count'),
    ],
    'realize': [
        (0x18D3170, 'mov eax, dword ptr [rsi + 0x92fc4]', None, 'per visible card: the list mode'),
        (0x18D375E, 'mov edx, dword ptr [rsi + r10*4 + 0x92990]', None, 'mode 3: the entry\'s key'),
        (0x18D3801, 'call 0x18cafb0', None, 'the card widget is filled from the key'),
        (0x18D374A, 'call 0x18cdf30', None, 'and drawn from the entry\'s enabled byte'),
        (0x18CE02C, 'mov word ptr [rcx + 0x2b5a], dx', None, 'card flag (bit 2: disabled)'),
        (0x18CE033, 'call 0x18ca560', None, 'native redraw'),
    ],
    'cardPresentation': [
        (0x18CAFBD, 'mov dword ptr [rcx + 0x2b5c], edx', None, 'card widget: its key'),
        (0x18CB000, 'cmp dword ptr [rax + 4], ebx', None, 'the catalogue item with that key'),
        (0x18CB069, 'call 0x179c920', None, 'label: built from the item key'),
        (0x18CB40A, 'call 0x11f2490', None, 'item stable id -> type'),
        (0x18CB488, 'mov r10, qword ptr [r12 + rbx*8 + 0x37cb600]', None, 'the type\'s StratagemInfo row'),
        (0x18CB541, 'mov rax, qword ptr [r10 + 0xb0]', None, 'icon: the row\'s +0xB0 ...'),
        (0x18CB548, 'mov qword ptr [rcx], rax', None, '... into the card\'s image descriptor ...'),
        (0x18CB590, 'call 0x18dc5d0', None, '... applied to the image element'),
        (0x19438AE, 'call 0x144f800', None, 'the element binds a material by resource id (a native GUI object)'),
        (0x144F86A, 'call 0x12ee1e0', None, 'the material resolved through the GUI'),
    ],
    'detailPanel': [
        (0x18D72A6, 'call 0x18d2270', None, 'focus change: the focused key'),
        (0x18D72C5, 'jmp 0x191d040', None, 'the detail panel is filled from it'),
        (0x191D54D, 'call 0x11f2490', None, 'key -> type'),
        (0x191D561, 'mov rax, qword ptr [r12 + rax*8 + 0x37cb600]', None, 'name, description, preview: the row\'s'),
    ],
    'click': [
        (0x18CFA39, 'call 0x18d2690', None, 'a click on a card ...'),
        (0x18D270F, 'movzx eax, byte ptr [rax + rcx + 0x92dc2]', None, '... needs its enabled byte'),
        (0x18D5E59, 'call 0x18d2270', None, 'confirm: the key at the focused cell'),
        (0x18D2301, 'mov ecx, dword ptr [rdi + rax*4 + 0x92990]', None, 'read from the entry'),
        (0x18D5E68, 'mov dword ptr [rbp + 0x178c98], ebx', None, 'stored as the picked key'),
        (0x18D5E81, 'call 0x18d1280', None, 'focus moves to the FIRST card with that key'),
        (0x18D5E96, 'mov eax, 3', None, 'confirm'),
        (0x146E1C9, 'mov edx, dword ptr [rdi + 0x24b4e8]', None, 'the selection handler: the picked key ...'),
        (0x146E1F0, 'cmp dword ptr [rax + 4], edx', None, '... its catalogue item (then stable id -> type -> slot)'),
    ],
    'enabledState': [
        (0x18D8BEC, 'mov byte ptr [rsp + r9*4 + 0x60], r12b', None, 'build: a card whose type is selected is disabled'),
        (0x18D1964, 'mov byte ptr [rax + r12 + 0x92dc2], 1', None, 'after a pick: every entry enabled ...'),
        (0x18D1A1E, 'xor r8d, r8d', None, '... then, per record entry, enabled 0 ...'),
        (0x18D1A24, 'call 0x18d1440', None, '... through the per-card helper (MultiSelect calls it with 1)'),
        (0x18D1480, 'cmp dword ptr [rcx + r9*4 + 0x92990], edx', None, 'helper: the FIRST entry with the key'),
        (0x18D14B0, 'mov byte ptr [r9 + rcx + 0x92dc2], sil', None, 'helper: its enabled byte'),
        (0x18D152F, 'mov word ptr [rcx + 0x2b5a], dx', None, 'helper: the realized card\'s flag'),
        (0x18D1536, 'call 0x18ca560', None, 'helper: native redraw'),
    ],
    'save': [
        (0x146E692, 'call 0x18d1890', None, 'after the slot write: the refresh'),
    ],
}


def add_card_reads_no_key():
    """The add's whole body: the key array is written once and never read (no duplicate check)."""
    import capstone
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    start, end = ADD_CARD
    touches = [f'{i.mnemonic} {i.op_str}' for i in md.disasm(game_data[start:end], start) if '0x92990' in i.op_str]
    return touches


def picker_in_snapshots():
    """Every retained snapshot: is a loadout UI (and so a card list) present?"""
    out = {}
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        owner = mem.ptr(mem.game + G_LOADOUT_UI_OWNER)
        ui = mem.u64(owner + UI_ROOT) if owner else None
        out[name] = {'owner': bool(owner), 'uiRoot': ui or 0}
        mem.close()
    return out


def multiselect_summary():
    """The lead's mechanism, as its own source states it (not proof)."""
    return {'present': MULTISELECT.exists(), 'module': 'mods/OnlyTanks/stratagem_multiselect',
        'state': ['ui = [[owner]+0xB0], loadout screen when ui+0x2808 == 0', 'record = ui+0x10+[ui+0x27D0]*0x9F0',
            'card list = ui+0xD2F20: count +0x92984, keys +0x92990, enabled bytes +0x92DC2',
            'card key = the catalogue item (kind 10) +4 whose +8 is the stable id'],
        'nativeCall': ('every 3 frames, for each selected type whose card is disabled: the per-card helper 0x18D1440 '
            '(list, key, 1)'),
        'helperEffect': ['the enabled byte of the first entry with the key (data)',
            'the realized card widget\'s flag +0x2B5A bit 2 (data)', 'the card redraw 0x18CA560 (native)']}


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
    add_touches = add_card_reads_no_key()
    if add_touches != ['mov dword ptr [r10 + rax*4 + 0x92990], edx']:
        raise ValueError('the add touches the key array otherwise: %r' % add_touches)
    snapshots = picker_in_snapshots()
    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0, 'pins': pins,
        'pinnedBytesMismatchPerSnapshot': relocation, 'addCardKeyArrayAccess': add_touches,
        'pickerInSnapshots': snapshots, 'multiselect': multiselect_summary(),
        'cardList': {'owner': 'ui + 0xD2F20 (the stratagem screen ui + 0xD2850, + 0x6D0); ui = [[game+0x347CE38]+0xB0]',
            'lifetime': 'exists only while the loadout UI exists; rebuilt from scratch whenever the grid opens for a slot',
            'entry': {'key': '+0x92990 + i*4 (catalogue item key)', 'enabled': '+0x92DC2 + i', 'badge': '+0x92EC2 + i'},
            'count': '+0x92984 (at most 256)', 'rows': '+0x91F14 (last row), +0x92318 + r*4 (cards in the row, 4 max)',
            'sections': '+0x92748 (count), +0x92854 (category), +0x9274C (first row), +0x927D0 (first card)',
            'widgets': ('virtualised: row widgets at +0xB00 (stride 0xAED0, 4 card widgets each at +0x110, stride '
                '0x2B68); visible rows from +0x928D8, realized rows +0x91F0C; card widget key +0x2B5C, flag +0x2B5A')},
        'determinations': {
            'cardObject': ('A list entry holds only a catalogue item key, an enabled byte and a badge byte; the card on '
                'screen is a pooled widget refilled from that key by native code.'),
            'candidateList': ('A dynamic list (at most 256 entries, rows of 4, grouped by category), cleared and rebuilt '
                'by the grid builder: one card per owned, selectable type.'),
            'duplicateKeys': ('The list accepts a repeated key (the add never reads the key array), but the builder '
                'makes one card per type, and the refresh, the per-card helper and focus-by-key act on the FIRST '
                'entry with a key.'),
            'storesType': 'No: the type is derived from the key (catalogue item -> stable id -> type) at each use.',
            'storesStableId': 'No: the stable id is the catalogue item\'s, looked up from the key.',
            'clickReads': ('The key of the focused cell (gated by its enabled byte); the handler resolves key -> '
                'catalogue item -> stable id -> type and writes that type into the slot.'),
            'cardAfterBuild': ('Only by writing the list arrays (key, enabled, badge, row and card counts, later '
                'sections\' first-card index) and waiting for the game to realize the row; the game\'s own add and '
                'layout are native calls.'),
            'greyedCard': ('Its enabled byte is data (a write makes it clickable), but its dimmed look is redrawn only '
                'by native code: on the game\'s next realize of that row.'),
            'spareCapacity': '256 entries minus the owned, selectable stratagems; four cards per row.',
            'autoLayout': ('A card added to a row with a free cell is laid out by the next realize; a card needing a '
                'new row needs the native layout (row positions, scroll extent).'),
            'creationHelper': 'Yes, native (add 0x18D43A0, layout 0x18D44B0): excluded, a native call.',
            'perInstancePresentation': ('No. Every visual of a card is rebuilt by native code from its key and the '
                'StratagemInfo row: the icon (row +0xB0, bound as a GUI material when the card is filled), the label '
                '(from the item key) and the detail panel (name, description, preview, on each focus change). No '
                'per-card field holds a presentation the game reads back; overriding one needs native calls, a '
                'StratagemInfo write or a catalogue write.'),
            'virtualCardIdentity': ('Only its list index, while the grid lives. After a pick the slot holds the token\'s '
                'type, and the save its stable id: which card was clicked is not recorded. The only rule that '
                'survives save and restore is record order: the later of two token entries is the virtual one (the '
                'rule of the mission-time slot conversion).'),
            'rebuilds': ('Every grid open rebuilds the list (an inserted entry is gone); every realize refills the '
                'visible cards from their keys; every focus change refills the detail panel.')},
        'conclusion': ('Not feasible under the constraints. A second token card could be represented with data '
            'writes (it would select the native token, and the refresh disables only the first card with a key), but '
            'it would look exactly like the token card: the card\'s icon, label and detail panel come from the token\'s '
            'StratagemInfo row through native code at every fill. A Runtime-presented virtual card needs a native '
            'call, a StratagemInfo write or a catalogue write. Nothing built; no live test.')}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; snapshots with mismatches',
        sum(1 for v in relocation.values() if v), '; snapshots with a picker',
        sum(1 for v in snapshots.values() if v['uiRoot']))


if __name__ == '__main__':
    main()
