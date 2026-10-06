"""How the native stratagem picker decides that a card is BLOCKED / UNAVAILABLE, draws it, and refuses a pick of it; and
which of those states the Runtime may set for a vanilla carrier stratagem that a selected custom stratagem reserves
(docs/research/stratagem-blocking-F5FEE03DCFDB.md). Read-only, offline: the game.dll image and the seven retained
snapshots of build F5FEE03DCFDB (research_stratagem_calldown.SNAPSHOTS), and the game's text resources. Nothing is
written. Builds on research/stratagem-picker-F5FEE03DCFDB.json (the card list) and the selector's loadout pins.

Proves:

1. Arrowhead's "disabled item" switch is SERVER data: 0x12E8020 applies an online override blob ("OnlineOverrideData" /
   "OnlineOverrideDataPeerSynced", the peer-synced copy): it clears the catalogue flag of every item it listed before
   (the global list game+0x37CF520, count game+0x37CF5A0), then sets it on the item of every override entry of type
   0x6EE9B997 (entry +0x10 = the item's stable id). The flag is the catalogue definition's byte +0xB5
   (catalogue + 0x1CE4 + index * 0xB8 + 0xB5 = catalogue + 0x1D99 + index * 0xB8). Its only two writers are in 0x12E8020;
   it is read by the grid builders of every armory list, the details panel, the loadout slot panel and the saved-loadout
   validation. It does NOT hide a card: the candidate filter 0x136FC20 reads the row's enabled (+0xC0 bit 0) and
   selectable (+0x80 bit 1) flags and ownership, never this flag.
2. The grid builder 0x18D8710 copies that flag into each card's list entry as its second state byte (+0x92EC2 + i,
   the byte research/stratagem-picker called the "badge"); the first (+0x92DC2 + i, "enabled") is 0 only for a type the
   edited record already holds. The add 0x18D43A0 is the ONLY writer of +0x92EC2 (a full linear sweep of .text); its
   readers are the realize pass (three list modes) and the gate 0x18D2720.
3. The native BLOCKED treatment is drawn from that byte: the realize pass (0x18D2B60; stratagem cards 0x18D37C4) hands
   it to the row's card setter 0x18CDF30, which sets the card widget flag +0x2B5A bit 0x100 and redraws (0x18CA560): the
   card's overlay element +0x1C18 (an image element built with material 0x61C5699658BEC440, 48 x 48 units, centred) is
   shown, the card is drawn at 50% opacity (mask 0x104 = disabled or blocked, 0x23C6AD0), and its unfocused frame is red
   (alpha 0.6, rgb 0.694 / 0.078 / 0; 0x23C8700) instead of grey (0x23C9AC0).
4. The native REFUSAL reads the same list byte: both select paths of the list input 0x18CF930 (the mouse click on the
   hovered card, 0x18CFA62 -> 0x18CFAA6; the select action on the focused card, 0x18CFDA5 -> 0x18CFDAC) refuse a card
   whose blocked byte is set, exactly as they refuse a greyed card (enabled 0): result 6, no pick, no sound, only the
   details refresh. The details panel's "DISABLED" notice (text 0x6CEF24E3) and its button lock (+0x91A0 bit 2) read
   the CATALOGUE flag (0x191D172), not the list byte.
5. Lifetime: the list (and so the byte) is cleared and rebuilt each time the grid opens for a slot (0x146ED65 ->
   0x18D27B0 clear) and cleared again on close (0x146F430); the post-pick refresh 0x18D1890 rewrites only the enabled
   bytes. A visible card shows the byte only after the next realize: the per-frame list update 0x18D5770 (called every
   frame by the stratagem screen 0x18D5650 while a selection is open, 0x1468702) realizes once when the one-shot flag
   +0x928FA is set (it then copies the scrollbar's drag byte +0x92902 into it); the game sets that flag itself to ask for
   a realize on the next frame (0x18D1BE2, 0x18D1FC0), and the list clear zeroes it (0x18D293F).

Output: research/stratagem-blocking-F5FEE03DCFDB.json (read by scripts/generate_stratagem_blocking.py).
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/stratagem-blocking-F5FEE03DCFDB.json'

# The loadout UI and its stratagem grid (research/stratagem-picker-F5FEE03DCFDB.json, domains/stratagem_selector.lua).
G_LOADOUT_UI_OWNER = 0x347CE38      # [owner + 0xB0] = the loadout UI while it exists
G_CATALOGUE = 0x347CEF8
G_DISABLED_LIST, G_DISABLED_COUNT = 0x37CF520, 0x37CF5A0
UI_ROOT, SELECTION_OPEN, SUB_STATE, EDITED_SLOT = 0xB0, 0x273990, 0x2818, 0x281C
SCREEN, LIST = 0xD2850, 0xD2F20      # ui + SCREEN = the stratagem screen; ui + LIST = its card list (screen + 0x6D0)
GRID_SHOWN = 0x178C60                # screen + : the per-frame update runs the list update while it is set
MODE, STRATAGEM_MODE = 0x92FC4, 3
COUNT, KEYS, ENABLED, BLOCKED, MAX_CARDS = 0x92984, 0x92990, 0x92DC2, 0x92EC2, 256
SCROLL_MOVED, REALIZE_REQUEST, SCROLLBAR_ACTIVE = 0x928F8, 0x928FA, 0x92902
CAT = {'rangeFirst': 0xD1D0C, 'rangeLast': 0xD1D10, 'index': 0xD1D48, 'records': 0xB9CE4, 'recordStride': 0x18,
    'recordDefinition': 0, 'recordKey': 4, 'recordId': 8, 'definitions': 0x1CE4, 'definitionStride': 0xB8,
    'definitionCount': 0x1CE0, 'disabled': 0xB5}
DISABLED_TEXT = 0x6CEF24E3
OVERLAY_MATERIAL = 0x61C5699658BEC440
CONSTANTS = {'blockedFrame': 0x23C8700, 'normalFrame': 0x23C9AC0, 'dimmed': 0x23C6AD0, 'full': 0x23C6D70}

GAME = {
    'loadoutUi': [
        (0x8745B9, 'mov rax, qword ptr [rip + {rip}]', G_LOADOUT_UI_OWNER, 'the loadout UI owner'),
        (0x8745C0, 'mov rcx, qword ptr [rax + 0xb0]', None, 'its UI object (0 while no loadout screen exists)'),
        (0x14686BB, 'mov dword ptr [rsi + 0x2818], eax', None, 'the sub-state (10: a stratagem slot)'),
        (0x14686C1, 'cmp byte ptr [rsi + 0x273990], r14b', None, 'a selection is open ...'),
        (0x1468702, 'call 0x18d5650', None, '... then the stratagem screen updates, every frame'),
        (0x146E6D4, 'mov dword ptr [rdi + 0x281c], esi', None, 'the edited slot'),
        (0x146E0BC, 'add rcx, 0xd2850', None, 'the stratagem screen inside the UI'),
        (0x146E67D, 'lea rcx, [rdi + 0xd2f20]', None, 'its card list (screen + 0x6D0)'),
    ],
    'serverDisabled': [
        (0x12E803B, 'lea rdx, [rip + {rip}]', 0x22C2248, 'the online override blob ("OnlineOverrideData")'),
        (0x12E8055, 'lea rdx, [rip + {rip}]', 0x22C2228, 'and its peer-synced copy ("OnlineOverrideDataPeerSynced")'),
        (0x12E80FC, 'mov byte ptr [rcx + rsi + 0x1d99], 0', None, 'every item listed before: catalogue flag cleared'),
        (0x12E811B, 'mov dword ptr [rip + {rip}], ebx', G_DISABLED_COUNT, 'the list restarts'),
        (0x12E808A, 'mov r8d, 0x6ee9b997', None, 'override entries of this type ...'),
        (0x12E81AE, 'mov byte ptr [rcx + rsi + 0x1d99], 1', None, '... set the flag of their item (entry +0x10)'),
        (0xB68ADE, 'call 0x12e8020', None, 'applied when the online data arrives'),
        (0x103F607, 'call 0x12e8020', None, 'and when it is refreshed'),
    ],
    'candidateFilter': [
        (0x136FC89, 'test byte ptr [r10 + 0xc0], 1', None, 'a card exists only for an enabled row ...'),
        (0x136FC97, 'test byte ptr [r10 + 0x80], 2', None, '... that is selectable and owned (never the catalogue flag)'),
    ],
    'gridBuild': [
        (0x146ED65, 'call 0x18d8710', None, 'the grid opens for a slot: the builder, its only caller'),
        (0x18D8A78, 'call 0x18d27b0', None, 'the list is cleared'),
        (0x18D8A7D, 'mov edx, 3', None, 'list mode 3 ...'),
        (0x18D8A8B, 'call 0x18d09d0', None, '... (the stratagem list)'),
        (0x18D0A19, 'mov dword ptr [rcx + 0x92fc4], ebx', None, 'the list mode'),
        (0x18D8A90, 'mov r14, qword ptr [rip + {rip}]', G_CATALOGUE, 'the account catalogue'),
        (0x18D8B37, 'mov edx, dword ptr [r14 + 0xd1d0c]', None, 'its stratagem range: first ...'),
        (0x18D8B3E, 'mov r9d, dword ptr [r14 + 0xd1d10]', None, '... and end'),
        (0x18D8B4E, 'lea r8, [r14 + 0xd1d48]', None, 'the range\'s record indexes'),
        (0x18D8B63, 'lea r11, [r14 + 0xb9ce4]', None, 'the records (stride 0x18)'),
        (0x18D8B6E, 'cmp dword ptr [r11 + rcx*8 + 8], r10d', None, 'the record whose +8 is the row\'s stable id'),
        (0x18D8B99, 'mov byte ptr [rsp + r9*4 + 0x60], 1', None, 'card enabled'),
        (0x18D8B9F, 'mov eax, dword ptr [r11]', None, 'the record\'s definition index'),
        (0x18D8BA2, 'imul rcx, rax, 0xb8', None, 'definitions: stride 0xB8'),
        (0x18D8BA9, 'movzx eax, byte ptr [rcx + r14 + 0x1d99]', None, 'the definition\'s server-disabled flag ...'),
        (0x18D8BB2, 'mov byte ptr [rsp + r9*4 + 0x61], al', None, '... becomes the card\'s BLOCKED byte'),
        (0x18D8BEC, 'mov byte ptr [rsp + r9*4 + 0x60], r12b', None, 'a type already in the record: greyed instead'),
        (0x18D8BF1, 'mov eax, dword ptr [r11 + 4]', None, 'the card key: the record\'s +4'),
        (0x18D8C60, 'movzx eax, byte ptr [rbx + 1]', None, 'blocked byte ...'),
        (0x18D8C67, 'movzx r9d, byte ptr [rbx]', None, '... and enabled byte ...'),
        (0x18D8C75, 'call 0x18d43a0', None, '... into the add'),
        (0x18D4469, 'inc dword ptr [r10 + 0x92984]', None, 'the card count'),
        (0x18D445A, 'mov dword ptr [r10 + rax*4 + 0x92990], edx', None, 'entry: key'),
        (0x18D444B, 'mov byte ptr [rcx + r10 + 0x92ec2], al', None, 'entry: BLOCKED byte (its only writer)'),
        (0x18D4657, 'jmp 0x18d2b60', None, 'layout, then the realize (inside the build)'),
    ],
    'treatment': [
        (0x18D37C4, 'movzx ebp, byte ptr [r10 + rsi + 0x92ec2]', None, 'realize (stratagem cards): the blocked byte'),
        (0x18D37CD, 'movzx r14d, byte ptr [r10 + rsi + 0x92dc2]', None, 'and the enabled byte'),
        (0x18D3801, 'call 0x18cafb0', None, 'the card filled from its key'),
        (0x18D374A, 'call 0x18cdf30', None, 'then drawn from the two bytes'),
        (0x18CE05D, 'shr ax, 8', None, 'blocked -> card flag bit 0x100'),
        (0x18CE086, 'mov word ptr [rcx + 0x2b5a], dx', None, 'stored, then redrawn'),
        (0x18CA585, 'movzx ebx, byte ptr [rcx + 0x2b5b]', None, 'redraw: bit 0x100 ...'),
        (0x18CA5A4, 'add rcx, 0x1c18', None, '... shows the overlay element'),
        (0x18CA5B0, 'mov eax, 0x104', None, 'disabled or blocked ...'),
        (0x18CA5B5, 'test word ptr [rdi + 0x2b5a], ax', None, '... dims the card'),
        (0x18CA5C3, 'movss xmm1, dword ptr [rip + {rip}]', CONSTANTS['dimmed'], 'to 0.5'),
        (0x18CA8A8, 'test bl, bl', None, 'blocked, unfocused: the frame ...'),
        (0x18CA8AC, 'movaps xmm0, xmmword ptr [rip + {rip}]', CONSTANTS['blockedFrame'], '... red'),
        (0x18CA8B5, 'movaps xmm0, xmmword ptr [rip + {rip}]', CONSTANTS['normalFrame'], 'otherwise grey'),
        (0x18CA04B, 'lea rsi, [r13 + 0x1c18]', None, 'card construction: the overlay element ...'),
        (0x18CA05A, 'movabs r8, 0x61c5699658bec440', None, '... its material'),
        (0x18CA072, 'mov dword ptr [rbp - 0x59], 0x42400000', None, '... 48 units'),
    ],
    'refusal': [
        (0x18CFA39, 'call 0x18d2690', None, 'click on the hovered card: its enabled byte ...'),
        (0x18CFA40, 'je 0x18cfdf1', None, '... 0: refused'),
        (0x18CFA62, 'call 0x18d2720', None, 'its blocked byte ...'),
        (0x18CFAA4, 'test al, al', None, '...'),
        (0x18CFAA6, 'jne 0x18cfb4f', None, '... set: no pick'),
        (0x18CFD97, 'call 0x18d2690', None, 'select on the focused card: enabled byte ...'),
        (0x18CFD9E, 'je 0x18cfdf1', None, '... 0: refused'),
        (0x18CFDA5, 'call 0x18d2720', None, 'blocked byte ...'),
        (0x18CFDAA, 'test al, al', None, '...'),
        (0x18CFDAC, 'jne 0x18cfdf1', None, '... set: refused'),
        (0x18CFDF1, 'mov eax, 6', None, 'result 6: no pick'),
        (0x18D270F, 'movzx eax, byte ptr [rax + rcx + 0x92dc2]', None, 'gate 0x18D2690: the enabled byte'),
        (0x18D279F, 'movzx eax, byte ptr [rax + rcx + 0x92ec2]', None, 'gate 0x18D2720: the blocked byte'),
        (0x18D5B06, 'cmp eax, 4', None, 'the grid confirm picks on result 4 only'),
    ],
    'details': [
        (0x191D172, 'movzx r13d, byte ptr [rcx + rsi + 0x1d99]', None, 'details panel: the CATALOGUE flag ...'),
        (0x191D194, 'or word ptr [rbp + 0x91a0], 4', None, '... locks its button'),
        (0x191D225, 'mov edx, 0x6cef24e3', None, '... and shows "DISABLED"'),
    ],
    'lifetime': [
        (0x18D1964, 'mov byte ptr [rax + r12 + 0x92dc2], 1', None, 'post-pick refresh: enabled bytes only'),
        (0x18D1A24, 'call 0x18d1440', None, 'then greys the record\'s types'),
        (0x146F430, 'call 0x18d27b0', None, 'the selection close clears the list'),
        (0x18D293F, 'mov word ptr [rdi + 0x928f9], bp', None, 'the clear zeroes the realize request'),
    ],
    'realizeRequest': [
        (0x18D565A, 'cmp byte ptr [rcx + 0x178c60], 0', None, 'the stratagem screen shows its grid ...'),
        (0x18D5737, 'call 0x18d5770', None, '... and runs the per-frame list update'),
        (0x18D581D, 'movzx eax, byte ptr [rbx + 0x928fa]', None, 'the one-shot realize request ...'),
        (0x18D5824, 'movzx ecx, byte ptr [rbx + 0x92902]', None, '... the scrollbar drag byte ...'),
        (0x18D582B, 'mov byte ptr [rbx + 0x928fa], cl', None, '... replaces it every frame'),
        (0x18D585D, 'call 0x18d2b60', None, 'either set: the realize'),
        (0x18D1BE2, 'mov byte ptr [rbx + 0x928fa], 1', None, 'the game requests one itself (scroll-to)'),
        (0x18D1FC0, 'mov byte ptr [rbx + 0x928fa], 1', None, 'and on a scrolling focus move'),
    ],
}

# Every instruction of .text whose memory operand ends in one of these displacements (a full linear sweep).
SWEEP = {'blockedByte': '0x92ec2]', 'enabledByte': '0x92dc2]', 'catalogueDisabled': '0x1d99]',
    'realizeRequest': '0x928fa]', 'listClearWord': '0x928f9]'}


def image():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    snap.close()
    return base.Image(game_data, game_base, base.TEXT)


def sweep(game):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.skipdata = True
    out = {name: [] for name in SWEEP}
    start, end = base.TEXT
    for address, _, mnemonic, operands in md.disasm_lite(game.data[start:end], start):
        if '0x' not in operands:
            continue
        for name, suffix in SWEEP.items():
            if suffix in operands:
                out[name].append('0x%X: %s %s' % (address, mnemonic, operands))
    return out


def classify(rows, writer_words=('mov byte', 'mov word', 'inc', 'or ', 'and ')):
    writers = [r for r in rows if any(r.split(': ', 1)[1].startswith(w) for w in writer_words)
        and ', ' in r and '[' in r.split(', ')[0]]
    return {'all': rows, 'writers': writers, 'readers': [r for r in rows if r not in writers]}


def constants(game):
    def vec(rva):
        return [round(v, 4) for v in struct.unpack_from('<4f', game.data, rva)]
    return {name: {'rva': rva, 'value': vec(rva)} for name, rva in CONSTANTS.items()}


def disabled_text():
    """The details panel's notice, from the game's own text resources ('us')."""
    try:
        import hd2_game_data
        import hd2_text
        data = hd2_game_data.Data()
        language = hd2_text.language_hash('us')
        for archive, name, kind, main, *_ in data.tables():
            if kind != hd2_text.STRINGS_TYPE or main[1] < 16:
                continue
            entries = hd2_text.parse(data.read(archive, main)).get(language, {})
            if entries.get(DISABLED_TEXT):
                return {'id': '0x%08X' % DISABLED_TEXT, 'us': entries[DISABLED_TEXT], 'resource': '0x%016X' % name}
    except Exception as error:  # the archives are optional for this research
        return {'id': '0x%08X' % DISABLED_TEXT, 'unavailable': repr(error)}
    return {'id': '0x%08X' % DISABLED_TEXT, 'us': None}


def snapshot_facts(name):
    """One retained snapshot: no loadout UI; the server-disabled list and every catalogue flag; the stratagem range."""
    mem = base.Mem(name)
    owner = mem.ptr(mem.game + G_LOADOUT_UI_OWNER)
    ui = mem.u64(owner + UI_ROOT) if owner else 0
    cat = mem.ptr(mem.game + G_CATALOGUE)
    listed = mem.u32(mem.game + G_DISABLED_COUNT)
    ids = [mem.u32(mem.game + G_DISABLED_LIST + 4 * k) for k in range(min(listed or 0, 32))]
    definitions = mem.u32(cat + CAT['definitionCount'])
    flagged = [k for k in range(definitions or 0)
        if mem.read(cat + CAT['definitions'] + k * CAT['definitionStride'] + CAT['disabled'], 1) != b'\0']
    first, last = mem.u32(cat + CAT['rangeFirst']), mem.u32(cat + CAT['rangeLast'])
    keys, same = 0, 0
    for position in range(first, last):
        index = mem.u32(cat + CAT['index'] + 4 * position)
        record = cat + CAT['records'] + index * CAT['recordStride']
        _, key, stable = struct.unpack('<III', mem.read(record, 12))
        keys += 1 if key else 0
        same += 1 if key == stable else 0
    mem.close()
    return {'loadoutUi': bool(ui), 'disabledListCount': listed, 'disabledListIds': ['0x%08X' % i for i in ids],
        'catalogueDefinitions': definitions, 'catalogueDefinitionsFlagged': len(flagged),
        'stratagemRange': [first, last], 'stratagemRecordsWithKey': keys, 'keyEqualsStableId': same}


MECHANISMS = [
    {'id': 'catalogue-disabled-flag', 'status': 'PROVEN',
        'what': ('Arrowhead\'s switch: the catalogue definition byte +0xB5, set from the online override data (entries of '
            'type 0x6EE9B997) and its peer-synced copy; the native "disabled item" (card visible, blocked look, '
            'refused, details "DISABLED" with a locked button).'),
        'where': 'catalogue [game+0x347CEF8] + 0x1CE4 + definition * 0xB8 + 0xB5; applied by 0x12E8020',
        'scope': ('GLOBAL / server-derived: one byte per catalogue item for the whole game (every armory grid, the details '
            'panel, the loadout slot panel, the saved-loadout validation); the peer-synced variant comes from the host'),
        'rebuilt': ('re-derived by the game only for the ids its override list held (game+0x37CF520) whenever online '
            'override data is applied; a byte set by anyone else is never cleared by the game'),
        'nativeVisual': True, 'nativeRefusal': True, 'nativeDetailsNotice': True,
        'safety': ('NOT ALLOWED without the user\'s decision: an account catalogue write of server-derived data, read by '
            'save validation and every armory list; not implemented'), 'implemented': False},
    {'id': 'card-blocked-byte', 'status': 'PROVEN',
        'what': ('The card list entry\'s second state byte (+0x92EC2 + i): the grid builder\'s copy of the catalogue flag. '
            'Drives the SAME native treatment (overlay icon, 50% opacity, red frame) and the SAME refusal (both select '
            'paths, result 6) as the server switch.'),
        'where': 'ui + 0xD2F20 (card list) + 0x92EC2 + entry index; ui = [[game+0x347CE38]+0xB0]',
        'scope': 'UI-LOCAL, per card: this machine\'s loadout UI object, only while the grid is open',
        'rebuilt': ('yes: cleared and rebuilt from the catalogue flag whenever the grid opens for a slot; cleared on '
            'close; NOT touched by the post-pick refresh. A change shows on the next realize (the one-shot request)'),
        'nativeVisual': True, 'nativeRefusal': True, 'nativeDetailsNotice': False,
        'safety': ('ALLOWED with guards: UI-local private memory, no executable change, no native call; guarded '
            'transaction (expected byte, key identity, private RW owner, read-back), restored exactly'),
        'implemented': True},
    {'id': 'realize-request', 'status': 'PROVEN (code); HYPOTHESIS (live order: no snapshot holds a loadout UI)',
        'what': ('The list\'s one-shot "realize next frame" flag (+0x928FA): the per-frame list update realizes once when '
            'it is set and then overwrites it with the scrollbar drag byte; the game sets it itself (scroll-to).'),
        'where': 'card list + 0x928FA (+0x92902 scrollbar drag; screen + 0x178C60 must show the grid)',
        'scope': 'UI-LOCAL, transient (consumed next frame; zeroed by every list clear)',
        'rebuilt': 'consumed by the game the next frame; zeroed by the clear',
        'nativeVisual': 'makes the blocked byte visible at once (the realize refills the visible cards)',
        'nativeRefusal': False, 'nativeDetailsNotice': False,
        'safety': 'ALLOWED with guards: written 0 -> 1 only, while the scrollbar is idle; never owned (the game consumes it)',
        'implemented': True},
    {'id': 'card-enabled-byte', 'status': 'PROVEN',
        'what': ('The first state byte (+0x92DC2 + i): 0 = "already in this loadout" (greyed: 50% opacity, no red frame, '
            'no overlay icon); refused the same way.'),
        'where': 'card list + 0x92DC2 + entry index',
        'scope': 'UI-LOCAL, per card',
        'rebuilt': 'rebuilt at every grid open AND rewritten for every card by the post-pick refresh (0x18D1890)',
        'nativeVisual': 'the greyed "selected" look, not the blocked look', 'nativeRefusal': True,
        'nativeDetailsNotice': False,
        'safety': 'possible but wrong semantics (it says "already selected") and re-written after every pick; not used',
        'implemented': False},
    {'id': 'card-widget-flags', 'status': 'PROVEN',
        'what': 'The realized card widget\'s flag word (+0x2B5A: bit 2 greyed, bit 0x100 blocked).',
        'where': 'card list + 0xB00 + row * 0xAED0 + 0x110 + card * 0x2B68 + 0x2B5A',
        'scope': 'UI-LOCAL, per visible card (a pooled widget)',
        'rebuilt': 'rewritten by every realize from the list bytes; drawn only by the native redraw 0x18CA560',
        'nativeVisual': 'only after a native redraw', 'nativeRefusal': False, 'nativeDetailsNotice': False,
        'safety': 'not needed (the list byte plus the realize request covers it); not used', 'implemented': False},
    {'id': 'row-enabled-selectable', 'status': 'PROVEN',
        'what': 'StratagemInfo row +0xC0 bit 0 (enabled) and +0x80 bit 1 (selectable), and catalogue ownership.',
        'where': 'StratagemInfo table game+0x37CB600; catalogue definition +0x14',
        'scope': 'GLOBAL row / account data',
        'rebuilt': 'no',
        'nativeVisual': 'none: the card is not built at all (hidden, not blocked)', 'nativeRefusal': 'n/a',
        'nativeDetailsNotice': False,
        'safety': 'NOT ALLOWED: a StratagemInfo row-global / account write, and it hides instead of blocking',
        'implemented': False},
    {'id': 'details-panel-notice', 'status': 'PROVEN',
        'what': ('The details panel\'s "DISABLED" notice and its button lock: read from the CATALOGUE flag of the focused '
            'key when the panel is filled (0x191D040). No per-card or UI-local input.'),
        'where': 'details panel ui + 0xD2850 + 0x99D70: +0xB08C0 notice element, +0x91A0 button flags',
        'scope': 'reachable only through the catalogue flag (global) or a native call',
        'rebuilt': 'refilled on every focus change',
        'nativeVisual': True, 'nativeRefusal': 'the details button (no pick path in the loadout grid)',
        'nativeDetailsNotice': True,
        'safety': 'NOT reproducible UI-locally; would need the catalogue write (decision) or a native call; not done',
        'implemented': False},
]


def main():
    game = image()
    pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    scan = sweep(game)
    access = {name: classify(rows) for name, rows in scan.items()}
    blocked_writers = [r.split(':')[0] for r in access['blockedByte']['writers']]
    if blocked_writers != ['0x18D444B']:
        raise ValueError('the blocked byte has other writers: %r' % blocked_writers)
    flag_writers = [r.split(':')[0] for r in access['catalogueDisabled']['writers']]
    if flag_writers != ['0x12E80FC', '0x12E81AE']:
        raise ValueError('the catalogue flag has other writers: %r' % flag_writers)
    if game.data[0x18CA05C:0x18CA064] != struct.pack('<Q', OVERLAY_MATERIAL):
        raise ValueError('the overlay material changed')
    snapshots = {name: snapshot_facts(name) for name in SNAPSHOTS}
    text = disabled_text()
    result = {'build': 'F5FEE03DCFDB', 'gameDllSha256': base.PROFILE_DLL_SHA, 'exeSha256': base.PROFILE_EXE_SHA,
        'writes': 0, 'protectionChanges': 0, 'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'access': access, 'constants': constants(game), 'disabledText': text, 'snapshots': snapshots,
        'mechanisms': MECHANISMS,
        'layout': {
            'loadout': {'ownerGlobal': G_LOADOUT_UI_OWNER, 'root': UI_ROOT, 'selectionOpen': SELECTION_OPEN,
                'subState': SUB_STATE, 'gridSubState': 10, 'editedSlot': EDITED_SLOT, 'maxLoadoutEntries': 4,
                'screen': SCREEN, 'list': LIST},
            'grid': {'shown': GRID_SHOWN, 'mode': MODE, 'stratagemMode': STRATAGEM_MODE, 'count': COUNT,
                'maxCards': MAX_CARDS, 'keys': KEYS, 'enabled': ENABLED, 'blocked': BLOCKED,
                'scrollMoved': SCROLL_MOVED, 'realizeRequest': REALIZE_REQUEST, 'scrollbarActive': SCROLLBAR_ACTIVE,
                'requestContext': 12},
            'catalogue': dict(CAT, **{'global': G_CATALOGUE}),
            'treatment': {'cardFlags': 0x2B5A, 'blockedBit': 0x100, 'overlayElement': 0x1C18,
                'overlayMaterial': '0x%016X' % OVERLAY_MATERIAL, 'overlayUnits': 48, 'opacity': 0.5,
                'frame': constants(game)['blockedFrame']['value'], 'refusalResult': 6,
                'detailsText': text.get('us')}},
        'determinations': {
            'arrowheadSwitch': ('Server data: the catalogue definition byte +0xB5, set by 0x12E8020 from the online '
                'override data (and its peer-synced copy from the host). It is account-catalogue state read by save '
                'validation and every armory grid: a Runtime write would be a catalogue / server-data change.'),
            'perCardState': ('The grid builder copies that byte into each card\'s list entry (+0x92EC2). That entry byte '
                'alone drives the native blocked treatment (overlay icon element +0x1C18, 50% opacity, red frame) and '
                'the native refusal of both select paths. It is UI-local and per card, and the game rebuilds it from '
                'the catalogue at every grid open.'),
            'visualTiming': ('The visible cards are realized inside the build, before any Runtime update can run; the '
                'list byte shows on the next realize. The list\'s one-shot request (+0x928FA, the game\'s own '
                '"realize next frame") makes that the next frame.'),
            'detailsPanel': ('Not reproducible UI-locally: its "DISABLED" notice and button lock read the catalogue '
                'flag of the focused key; a blocked carrier\'s details show its normal name and description.'),
            'noSnapshotPicker': ('No retained snapshot holds a loadout UI ([[game+0x347CE38]+0xB0] == 0), and none has a '
                'server-disabled item (the override list is empty, no catalogue flag is set): the per-card path is '
                'proven in code only and needs a live test.')},
        'conclusion': ('A UI-local per-card native mechanism exists and is the one the game uses for its own disabled '
            'treatment and refusal: the card list entry\'s blocked byte. runtime/stratagem_blocking.lua sets it (and '
            'the one-shot realize request) for exactly the reserved carriers while the grid is open, re-applies after '
            'every rebuild, and restores it exactly. The server switch (catalogue flag) and the details notice are not '
            'written: a decision for the user.')}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; snapshots with mismatches',
        sum(1 for v in relocation.values() if v), '; blocked-byte writers', blocked_writers, '; text', text.get('us'))


if __name__ == '__main__':
    main()
