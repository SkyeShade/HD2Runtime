"""Runtime-owned custom stratagem text (docs/custom-text.md): how a StratagemInfo text id becomes displayed text, how the
game registers its text, and how the Runtime can add its own text without touching a game text entry. Read-only,
offline: the helldivers2.exe and game.dll images and the seven retained snapshots of build F5FEE03DCFDB, and the game's
text resources from its archives.

Proves:

1. The lookup (exe 0x321C40; GUI API +0x10 slot +0x3E0, and +0x3E8 = 0x321DA0 for the current language). It reads the
   registry [exe+0x1A101E0] = {u32 count, u32 capacity, table pointer array, allocator} ONCE (count and array) and
   walks the tables in order; per table it binary-searches the language hash, then the id, and returns table + offset;
   no table -> the empty string (exe 0x165012A). The table format (scripts/hd2_text.py) is reproduced byte for byte
   for every vanilla text resource.
2. The registry's code. The only functions that reference the registry: add 0x321AA0 (+0x3D0; it appends a resource's
   data pointer at [count] and then increments count, reallocating and freeing the array when it is full), clear
   0x321C20 -> 0x3269F0 (+0x3D8; count = 0, the array and its capacity kept), lookup 0x321C40 (the only reader of the
   entries), and the shutdown frees (0x1CF780, 0x326090, 0x326D50). Four unreferenced helpers remain (0x326170,
   0x326180, 0x3269D0, 0x326BB0).
3. Who registers. Every game.dll use of the add, clear and set-language slots (a scan of all loads of the GUI API
   global): add only in 0x12FEDC0 (and the unreferenced 0x12FED80), clear only in 0x12FEDC0, set language only in
   0x12FF050. 0x12FEDC0 clears (unless no language was set yet), then registers localization/<base>_<language> for 17
   fixed bases, localization/voiceover/phonetics_<language>, and a fallback resource when none registered. 0x12FF050
   (set language, then 0x12FEDC0) runs from 0x12FE920 when the requested language differs from the current one and
   its package is loaded; 0x12FE920 runs inside 0xAB5000, which the plugin entry point 0x4EE6C0 (registered by
   0x4EEAD0 and given a float, the frame time) calls each update, and from the game setup.
4. The consumers. The mission menu name (row +0x28, 0x66D559) is looked up by its callers through +0x3E8 (0x1837087,
   0x1838D72); the loadout details name (+0x28 / +0x2C, 0x179D95D / 0x179D962) is a localized text argument (0x143A110,
   kind 0xA) that 0x13006A0 looks up through +0x3E8 (0x1300905); the description (+0x30, 0x189FBD0) goes through
   0x191FCE0 -> 0x143A030 -> 0x13006A0, looked up through +0x3E8 (0x1300795). Every path ends in 0x321C40.
5. The registry in every snapshot: count, capacity, the tables (named by matching the game's text resources), the
   current language; the language table (game.dll +0x37C5650: 15 codes) and their hashes.
6. The proof's custom text ids collide with no vanilla id in any language, and a mod's key namespace keeps two mods'
   ids apart.

Output: research/stratagem-text-F5FEE03DCFDB.json.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import struct
import sys

import capstone
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import hd2_game_data  # noqa: E402
import hd2_text  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/stratagem-text-F5FEE03DCFDB.json'
REGISTRY, LANGUAGE, EMPTY = 0x1A101E0, 0x190C9BC, 0x165012A
GUI_API = 0x3326308
LANGUAGE_TABLE = 0x37C5650
PROOF_RESOURCE = 'mods/skyeshade/hd2runtime_custom_stratagem_p0_proof'
PROOF_TEXTS = {'orbital_gas_barrage_name': 'ORBITAL GAS BARRAGE', 'orbital_gas_barrage_name_cased': 'Orbital Gas Barrage',
    'orbital_gas_barrage_description': 'Calls down a barrage of gas shells.'}
CARRIER = {'name': 0x4FAAD695, 'nameCased': 0x628B5A83, 'description': 0x35FEBFE6}   # the 120mm (presentation research)

EXE = {
    'lookup': [
        (0x321C5C, 'mov rax, qword ptr [rip + {rip}]', REGISTRY, 'lookup: the text registry'),
        (0x321C6A, 'mov r12d, dword ptr [rax]', None, 'its count, read once'),
        (0x321C76, 'mov r13, qword ptr [rax + 8]', None, 'its table array, read once'),
        (0x321C80, 'mov r14, qword ptr [r13 + rbp*8]', None, 'each table, in order'),
        (0x321CB0, 'mov r9d, dword ptr [rip + {rip}]', LANGUAGE, 'no language given: the current language hash'),
        (0x321CB7, 'mov edx, dword ptr [r14 + 4]', None, 'table +4: language count'),
        (0x321CBB, 'lea r11, [r14 + 0xc]', None, 'table +0xC: the language hashes (binary search)'),
        (0x321CBF, 'mov r15d, dword ptr [r14 + 8]', None, 'table +8: id count'),
        (0x321CC6, 'lea rsi, [rdx + 3]', None, 'the ids follow the languages (binary search)'),
        (0x321D4B, 'imul eax, r10d', None, 'offset index: language x id count + id index ...'),
        (0x321D59, 'mov ecx, dword ptr [rsi + rax*4]', None, '... after the ids'),
        (0x321D5C, 'test ecx, ecx', None, 'offset 0: not in this table, the next one'),
        (0x321D62, 'add rax, r14', None, 'the text: table + offset'),
        (0x321D69, 'cmp ebp, r12d', None, 'every table in turn'),
        (0x321D72, 'lea rax, [rip + {rip}]', EMPTY, 'no table has it: the empty string'),
        (0x321DA0, 'xor edx, edx', None, 'GUI API +0x3E8: the current language ...'),
        (0x321DA2, 'jmp 0x321c40', None, '... through the lookup'),
    ],
    'add': [
        (0x321AF5, 'cmp qword ptr [rip + {rip}], rsi', REGISTRY, 'add: the registry (created on first use)'),
        (0x321B4B, 'call 0x5f2290', None, "the resource's data pointer"),
        (0x321B5A, 'mov r8d, dword ptr [rbx]', None, 'count'),
        (0x321B5D, 'mov edx, dword ptr [rbx + 4]', None, 'capacity'),
        (0x321B64, 'cmp ecx, edx', None, 'full: a larger array ...'),
        (0x321BF1, 'call qword ptr [rax + 0x40]', None, '... and the old one freed'),
        (0x321C06, 'mov qword ptr [rax + rcx*8], rbp', None, 'the pointer at [count] ...'),
        (0x321C0C, 'inc dword ptr [rbx]', None, '... then the count'),
    ],
    # 0.30.2: how the add grows a full array (the Runtime's REGISTRY_FULL growth reproduces it through the same
    # allocator and keeps the old array allocated): capacity < 8 -> 8, else capacity + capacity / 2; the allocator at
    # registry +0x10; its vtable +0x30 allocates (self, out {pointer, size}, bytes, alignment 8) and returns out.
    'grow': [
        (0x321B6C, 'cmp edx, 8', None, 'grow: under 8 ...'),
        (0x321B87, 'mov edi, 8', None, '... becomes 8'),
        (0x321B78, 'shr rdi, 1', None, 'else capacity / 2 ...'),
        (0x321B7B, 'add rdi, rdx', None, '... added to the capacity'),
        (0x321BA9, 'mov rcx, qword ptr [rbx + 0x10]', None, 'the allocator: registry +0x10'),
        (0x321BAD, 'lea r8d, [rdi*8]', None, 'bytes: 8 per table pointer'),
        (0x321BB5, 'mov r9d, 8', None, 'alignment 8'),
        (0x321BC3, 'call qword ptr [r10 + 0x30]', None, 'allocate: vtable +0x30'),
        (0x321BC7, 'mov rsi, qword ptr [rax]', None, 'the new array: the first qword of the result'),
        (0x321BDE, 'call 0x1267850', None, 'the old pointers copied'),
        (0x321BF4, 'mov qword ptr [rbx + 8], rsi', None, 'the new array stored ...'),
        (0x321BF8, 'mov dword ptr [rbx + 4], edi', None, '... then the new capacity'),
    ],
    'allocate': [
        (0x5C2E10, 'mov qword ptr [rsp + 8], rbx', None, 'allocate of the registry allocator (vtable +0x30)'),
        (0x5C2E20, 'test r8, r8', None, 'zero bytes: an empty result'),
        (0x5C2E3C, 'mov rcx, qword ptr [rcx + 0x20]', None, 'its backing allocator ...'),
        (0x5C2E48, 'call qword ptr [rax + 0x30]', None, '... allocates'),
        (0x5C2E51, 'lock xadd qword ptr [rbx + 0x28], r8', None, 'thread-safe counters'),
        (0x5C2EC5, 'movups xmmword ptr [rdi], xmm0', None, 'the {pointer, size} result in the buffer of the caller'),
        (0x5C2EC2, 'mov rax, rdi', None, 'returns the buffer'),
    ],
    'clear': [
        (0x321C20, 'mov rcx, qword ptr [rip + {rip}]', REGISTRY, 'clear: the registry ...'),
        (0x321C2E, 'jmp 0x3269f0', None, '... resized to 0'),
        (0x326A4A, 'mov dword ptr [rcx], ebx', None, 'count = 0; the array and its capacity kept'),
    ],
    'setLanguage': [
        (0x321DDB, 'mov dword ptr [rip + {rip}], eax', LANGUAGE, 'set language: the hash of its code (upper 32 bits)'),
    ],
}
GAME = {
    'registration': [
        (0x12FEDDC, 'cmp dword ptr [rcx + 0x1a098], -1', None, 'a language was set before ...'),
        (0x12FEE05, 'call qword ptr [rcx + 0x3d8]', None, '... the registry is cleared'),
        (0x12FEE1D, 'lea rax, [rip + {rip}]', 0x22C25D8, '"localization/strings_glossary" (the first of 17 bases)'),
        (0x12FEF04, 'lea rax, [rip + {rip}]', 0x22C27D0, '"localization/temp_strings" (the last)'),
        (0x12FEF24, 'lea r8, [rip + {rip}]', 0x22C27C4, '"%s_%s": <base>_<language code>'),
        (0x12FEF69, 'mov r8, qword ptr [rdx + 0x3d0]', None, 'each registered (GUI API +0x3D0)'),
        (0x12FEFA9, 'lea r8, [rip + {rip}]', 0x22C27A0, '"localization/voiceover/phonetics_%s"'),
        (0x12FEFEE, 'mov r8, qword ptr [rdx + 0x3d0]', None, 'registered'),
        (0x12FF02F, 'call qword ptr [rdx + 0x3d0]', None, 'nothing registered: the fallback resource'),
    ],
    'languageChange': [
        (0x12FE92E, 'mov ecx, dword ptr [rcx + 0x1a09c]', None, 'the requested language ...'),
        (0x12FE939, 'cmp ecx, dword ptr [rdi + 0x1a098]', None, '... differs from the current one'),
        (0x12FE964, 'call r8', None, "its text package is loaded (GUI API +0x328)"),
        (0x12FE96E, 'call 0x12ff050', None, 'apply it'),
        (0x12FF128, 'call qword ptr [rdx + 0x3f0]', None, 'set language'),
        (0x12FF13E, 'call 0x12fedc0', None, 'then the registration (the registry is rebuilt)'),
        (0x12FF17B, 'lea rcx, [rip + {rip}]', 0x22C2790, '"text_language" (the setting)'),
    ],
    'update': [
        (0xAB4C29, 'mov rcx, qword ptr [rip + {rip}]', 0x347CEC8, 'the game update ...'),
        (0xAB4C30, 'call 0x12fe920', None, '... checks for a language change'),
        (0x4EE6E6, 'movaps xmm1, xmm6', None, 'the plugin entry point passes its float (the frame time) ...'),
        (0x4EE6E9, 'call 0xab5000', None, '... to the game update'),
        (0x4EEAE6, 'lea rax, [rip + {rip}]', 0x4EE6C0, 'the entry point, registered in the plugin API table'),
    ],
    'consumers': [
        (0x1837046, 'call 0x66d4b0', None, 'mission menu: the name id (row +0x28) ...'),
        (0x1837087, 'mov rax, qword ptr [rcx + 0x3e8]', None, '... looked up (GUI API +0x3E8)'),
        (0x1838D49, 'call 0x66d4b0', None, 'mission menu: the name id (row +0x28) ...'),
        (0x1838D72, 'mov rax, qword ptr [rdx + 0x3e8]', None, '... looked up (GUI API +0x3E8)'),
        (0x179DA3B, 'mov r8d, esi', None, 'loadout details: the name id (row +0x28 / +0x2C) ...'),
        (0x179DA3E, 'mov edx, 0x341f7711', None, '... as a text argument'),
        (0x143A143, 'mov dword ptr [rsp + 4], 0xa', None, 'argument kind 0xA: a text id'),
        (0x13008F3, 'mov edx, dword ptr [rsi + 8]', None, 'the formatter: a text-id argument ...'),
        (0x1300905, 'mov rax, qword ptr [rcx + 0x3e8]', None, '... looked up (GUI API +0x3E8)'),
        (0x189FBD0, 'mov edx, dword ptr [rbx + 0x30]', None, 'loadout details: the description id (row +0x30) ...'),
        (0x189FBD6, 'call 0x191fce0', None, '... to the description text ...'),
        (0x191FD1C, 'call 0x143a030', None, '... formatted ...'),
        (0x143A06C, 'call 0x13006a0', None, '... by the formatter'),
        (0x1300795, 'mov rax, qword ptr [rcx + 0x3e8]', None, 'which looks the id up (GUI API +0x3E8)'),
    ],
}
SLOTS = {0x3D0: 'add', 0x3D8: 'clear', 0x3E0: 'lookup(id, language)', 0x3E8: 'lookup(id)', 0x3F0: 'set language'}
SLOT_TARGETS = {0x3D0: 0x321AA0, 0x3D8: 0x321C20, 0x3E0: 0x321C40, 0x3E8: 0x321DA0, 0x3F0: 0x321DB0}


def rip_references(image: base.Image, text, target):
    """Instructions whose rip-relative operand resolves to target (one int32 view per byte phase)."""
    found = set()
    size = text[1] - text[0]
    lite = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for phase in range(4):
        count = (size - phase) // 4
        view = numpy.frombuffer(image.data, dtype='<i4', offset=text[0] + phase, count=count).astype(numpy.int64)
        positions = numpy.arange(count, dtype=numpy.int64) * 4 + text[0] + phase
        keys = positions + 4 + view
        for tail in (0, 1, 4):
            for hit in numpy.nonzero(keys == target - tail)[0]:
                at = int(positions[hit])
                # The longest decode ending at the displacement's instruction end: a REX prefix decodes on its own too.
                for back in range(10, 0, -1):
                    start = at - back
                    insn = next(lite.disasm_lite(image.data[start:start + 16], start, 1), None)
                    if insn and insn[1] == back + 4 + tail:
                        text_ = insn[2] + ' ' + insn[3]
                        m = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', text_)
                        if m and start + insn[1] + int(m.group(2), 16) * (1 if m.group(1) == '+' else -1) == target:
                            found.add(start)
                            break
    return sorted(found)


def slot_uses(image: base.Image, references):
    """Every use of the add / clear / lookup / set-language slots reached from a load of the GUI API global: the API
    pointer, its +0x10 table, then the slot (followed by register, 40 instructions)."""
    uses = {name: [] for name in SLOTS.values()}
    lite = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for at in references:
        listing = list(lite.disasm_lite(image.data[at:at + 400], at))
        if not listing:
            continue
        first = listing[0][2] + ' ' + listing[0][3]
        m = re.match(r'mov (\w+), qword ptr \[rip', first)
        if not m:
            continue
        api, table = {m.group(1)}, set()
        for address, size, mnemonic, operands in listing[1:40]:
            text = mnemonic + ' ' + operands
            mm = re.match(r'mov (\w+), qword ptr \[(\w+) \+ 0x10\]$', text)
            if mm and mm.group(2) in api:
                table.add(mm.group(1))
                continue
            mm = re.search(r'qword ptr \[(\w+) \+ (0x3d0|0x3d8|0x3e0|0x3e8|0x3f0)\]', text)
            if mm and mm.group(1) in table and mnemonic in ('call', 'mov', 'jmp'):
                uses[SLOTS[int(mm.group(2), 16)]].append(address)
            mm = re.match(r'(?:mov|lea|xor|pop) (\w+),', text)
            if mm:
                api.discard(mm.group(1))
                table.discard(mm.group(1))
            if mnemonic == 'ret' or (mnemonic == 'jmp' and 'qword ptr' not in operands):
                break
    return {name: sorted(set(v)) for name, v in uses.items()}


def function_of(image: base.Image, rva):
    """The .pdata function holding rva (its primary entry, following chained unwind info)."""
    data = image.data
    pe = struct.unpack_from('<I', data, 60)[0]
    exc_rva, exc_size = struct.unpack_from('<II', data, pe + 24 + 112 + 3 * 8)
    if not hasattr(image, '_pdata'):
        table = numpy.frombuffer(data[exc_rva:exc_rva + exc_size // 12 * 12], dtype='<u4').reshape(-1, 3)
        image._pdata = table[table[:, 0] < table[:, 1]]
    table = image._pdata
    i = int(numpy.searchsorted(table[:, 0], rva, side='right')) - 1
    if i < 0 or not table[i, 0] <= rva < table[i, 1]:
        # A leaf function without unwind data: it starts after the int3 padding before it.
        at = rva
        while at > rva - 0x100 and data[at - 1] != 0xCC:
            at -= 1
        return at if data[at - 1] == 0xCC else None
    begin, unwind = int(table[i, 0]), int(table[i, 2])
    for _ in range(10):
        if not (data[unwind] >> 3) & 4:
            break
        count = data[unwind + 2]
        begin, _, unwind = struct.unpack_from('<III', data, unwind + 4 + ((count + 1) & ~1) * 2)
    return begin


def vanilla_texts(data: hd2_game_data.Data):
    """Every text resource in the game's archives: {name: bytes}; and the byte-identical rebuild check."""
    found, rebuilt, differs = {}, 0, []
    for archive, name, kind, main, *_ in data.tables():
        if kind != hd2_text.STRINGS_TYPE or main[1] < 16:
            continue
        body = data.read(archive, main)
        found[name] = body
        if hd2_text.build(hd2_text.parse(body)) == body:
            rebuilt += 1
        else:
            differs.append('0x%016X' % name)
    return found, rebuilt, differs


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    exe_name = [k for k in snap.modules if k.endswith('.exe')][0]
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    exe, game = base.Image(exe_data, exe_base, base.EXE_TEXT), base.Image(game_data, game_base, base.TEXT)
    exe_pins = {group: [exe.prove(*row) for row in rows] for group, rows in EXE.items()}
    game_pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    strings = {0x22C25D8: 'localization/strings_glossary', 0x22C27D0: 'localization/temp_strings', 0x22C27C4: '%s_%s',
        0x22C27A0: 'localization/voiceover/phonetics_%s', 0x22C2790: 'text_language'}
    for rva, text in strings.items():
        if game.cstr(rva) != text:
            raise ValueError('a string moved: %r' % text)
    if exe_data[EMPTY] != 0:
        raise ValueError('the lookup fallback is not the empty string')
    flat_exe = [p for rows in exe_pins.values() for p in rows]
    flat_game = [p for rows in game_pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat_game, flat_exe) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)

    # Who touches the registry (exe) and who calls the registry slots (game.dll).
    registry_refs = rip_references(exe, base.EXE_TEXT, REGISTRY)
    registry_functions = sorted({function_of(exe, at) or at for at in registry_refs})
    expected = {0x1CF780, 0x321AA0, 0x321C20, 0x321C40, 0x326090, 0x326170, 0x326180, 0x3269D0, 0x326BB0, 0x326D50}
    if set(registry_functions) != expected:
        raise ValueError('the registry is referenced by other code: %s' % [hex(f) for f in registry_functions])
    unreferenced = {}
    for helper in (0x326170, 0x326180, 0x3269D0, 0x326BB0):
        pointer = struct.pack('<Q', exe_base + helper)
        unreferenced['0x%X' % helper] = {'ripReferences': len(rip_references(exe, base.EXE_TEXT, helper)),
            'pointerInImage': exe_data.find(pointer) >= 0}
    if any(v['ripReferences'] or v['pointerInImage'] for v in unreferenced.values()):
        raise ValueError('a registry helper is referenced: %r' % unreferenced)
    api_refs = rip_references(game, base.TEXT, GUI_API)
    uses = slot_uses(game, api_refs)
    use_functions = {name: sorted({function_of(game, at) or at for at in v}) for name, v in uses.items()}
    if (use_functions['add'] != [0x12FED80, 0x12FEDC0] or use_functions['clear'] != [0x12FEDC0]
            or use_functions['set language'] != [0x12FF050]):
        raise ValueError('another game.dll function registers text: %r' % {k: [hex(f) for f in v]
            for k, v in use_functions.items()})
    for at in (0x1837087, 0x1838D72, 0x1300905, 0x1300795):
        if at not in uses['lookup(id)']:
            raise ValueError('a consumer lookup is not a GUI API +0x3E8 use: %x' % at)
    registrar_callers = {'0x12FEDC0': ['0x%X' % c for c in (0x12FF13E, 0x12FF312)]}
    for caller in (0x12FF13E, 0x12FF312):
        if game.insn(caller).mnemonic != 'call' or game.insn(caller).op_str != '0x12fedc0':
            raise ValueError('the registration callers moved')

    # The game's text resources.
    data = hd2_game_data.Data()
    tables, rebuilt, differs = vanilla_texts(data)
    if differs:
        raise ValueError('hd2_text.build does not reproduce %d text resources: %r' % (len(differs), differs[:5]))
    parsed = {name: hd2_text.parse(body) for name, body in tables.items()}
    by_language = {}
    vanilla_ids = set()
    for name, table in parsed.items():
        for language, texts in table.items():
            by_language.setdefault(language, set()).add(name)
            vanilla_ids |= set(texts)
    codes = {hd2_text.language_hash(code): code for code in hd2_text.LANGUAGES}
    if set(by_language) - set(codes):
        raise ValueError('a text resource holds an unknown language: %r' % sorted(set(by_language) - set(codes)))
    names = {}
    bases = ['strings_glossary', 'strings_equipment', 'strings_encyclopedia', 'strings_galactic_war', 'strings_names',
        'strings_enemyvoiceovers', 'strings_utility', 'strings_community', 'strings_ui', 'strings_assignments',
        'strings_presidents_elections', 'strings_voiceovers', 'strings_missions', 'strings_hud', 'strings_world',
        'strings_video_ost', 'temp_strings']
    for code in hd2_text.LANGUAGES:
        for item in bases:
            names[hd2_archive_hash('localization/%s_%s' % (item, code))] = 'localization/%s_%s' % (item, code)
        names[hd2_archive_hash('localization/voiceover/phonetics_%s' % code)] = 'localization/voiceover/phonetics_%s' % code
    shipped = Counter('registered name' if n in names else 'other' for n in tables)
    missing_bases = sorted({item for item in bases if not any(hd2_archive_hash('localization/%s_%s' % (item, c)) in tables
        for c in hd2_text.LANGUAGES)})
    samples = {}
    for code in hd2_text.LANGUAGES:
        language = hd2_text.language_hash(code)
        found = [parsed[n][language].get(CARRIER['name']) for n in by_language.get(language, ()) if
            CARRIER['name'] in parsed[n].get(language, {})]
        samples[code] = found[0] if found else None

    # The registry, the language and the language table in every snapshot.
    snapshots = []
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        exe_at = mem.s.modules[[k for k in mem.s.modules if k.endswith('.exe')][0]]['base']
        registry = mem.ptr(exe_at + REGISTRY)
        count, capacity = mem.u32(registry), mem.u32(registry + 4)
        array = mem.ptr(registry + 8)
        entries = []
        for i in range(count):
            table = mem.ptr(array + 8 * i)
            head = mem.read(table, 12)
            magic, nl, n = struct.unpack('<III', head)
            languages = struct.unpack('<%dI' % nl, mem.read(table + 12, 4 * nl))
            match = [names.get(k, '0x%016X' % k) for k, body in tables.items()
                if body[:12] == head and struct.unpack_from('<%dI' % nl, body, 12) == languages
                and mem.read(table, min(len(body), 4096)) == body[:4096]]
            entries.append({'index': i, 'magic': '0x%08X' % magic, 'languages': [codes.get(x, '0x%08X' % x)
                for x in languages], 'ids': n, 'resource': match[0] if len(match) == 1 else match})
        language_table = []
        for i in range(24):
            entry = mem.ptr(mem.game + LANGUAGE_TABLE + 8 * i)
            if not entry:
                break
            code = mem.read(mem.ptr(entry + 8), 8).split(b'\0')[0].decode('ascii')
            language_table.append(code)
        current = mem.u32(exe_at + LANGUAGE)
        api = mem.ptr(mem.game + GUI_API)
        table10 = mem.ptr(api + 0x10)
        slots = {SLOTS[k]: '0x%X' % (mem.ptr(table10 + k) - exe_at) for k in SLOTS}
        allocator = mem.ptr(registry + 0x10)
        vtable = mem.ptr(allocator)
        snapshots.append({'snapshot': name, 'count': count, 'capacity': capacity, 'spare': capacity - count,
            'currentLanguage': codes.get(current, '0x%08X' % current), 'languageTable': language_table,
            'apiSlots': slots, 'tables': entries,
            'allocator': {'vtable': '0x%X' % (vtable - exe_at), 'allocate': '0x%X' % (mem.ptr(vtable + 0x30) - exe_at),
                'free': '0x%X' % (mem.ptr(vtable + 0x40) - exe_at)}})
        mem.close()
    if any(item['allocator'] != {'vtable': '0x168B5A0', 'allocate': '0x5C2E10', 'free': '0x5C2ED0'}
            for item in snapshots):
        raise ValueError('the registry allocator differs: %r' % [item['allocator'] for item in snapshots])
    for item in snapshots:
        if item['languageTable'] != list(hd2_text.LANGUAGES):
            raise ValueError('the language table differs: %r' % item['languageTable'])
        if item['apiSlots'] != {SLOTS[k]: '0x%X' % v for k, v in SLOT_TARGETS.items()}:
            raise ValueError('the GUI API text slots differ: %r' % item['apiSlots'])
        if any(entry['magic'] != '0x%08X' % hd2_text.MAGIC for entry in item['tables']):
            raise ValueError('a registered table is not a text table')

    # The proof's custom text: ids from the mod's own keys.
    custom = {}
    for key, text in PROOF_TEXTS.items():
        full = hd2_text.custom_key(PROOF_RESOURCE, key)
        value = hd2_text.text_id(full)
        custom[key] = {'key': full, 'id': '0x%08X' % value, 'text': text, 'vanillaCollision': value in vanilla_ids,
            'otherModId': '0x%08X' % hd2_text.text_id(hd2_text.custom_key('mods/someone/other_mod', key))}
    if any(item['vanillaCollision'] for item in custom.values()):
        raise ValueError('a proof text id collides with a vanilla id')
    entries = {hd2_text.language_hash(code): {int(v['id'], 16): v['text'] for v in custom.values()}
        for code in hd2_text.LANGUAGES}
    custom_table = hd2_text.build(entries)
    for code in hd2_text.LANGUAGES:
        language = hd2_text.language_hash(code)
        registered = [tables[n] for n in tables if language in parsed[n] and n in names]
        for v in custom.values():
            if hd2_text.lookup(registered, int(v['id'], 16), language) != '':
                raise ValueError('a proof id resolves through vanilla text')
            if hd2_text.lookup(registered + [custom_table], int(v['id'], 16), language) != v['text']:
                raise ValueError('the proof table does not resolve its own text')
        if hd2_text.lookup(registered + [custom_table], CARRIER['name'], language) != samples[code]:
            raise ValueError('appending the proof table changed a vanilla text')

    result = {'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0,
        'exe': {'sha256': base.PROFILE_EXE_SHA}, 'gameDll': {'sha256': base.PROFILE_DLL_SHA},
        'pins': {'exe': exe_pins, 'game': game_pins}, 'pinnedBytesMismatchPerSnapshot': relocation,
        'registry': {'global': '0x%X' % REGISTRY, 'layout': {'count': 0, 'capacity': 4, 'tables': 8, 'allocator': 0x10},
            'currentLanguage': '0x%X' % LANGUAGE, 'emptyText': '0x%X' % EMPTY,
            'referencingFunctions': ['0x%X' % f for f in registry_functions], 'unreferencedHelpers': unreferenced,
            'apiSlots': {SLOTS[k]: '0x%X' % v for k, v in SLOT_TARGETS.items()},
            'gameSlotUses': {k: ['0x%X' % a for a in v] for k, v in uses.items()},
            'gameSlotUseFunctions': {k: ['0x%X' % f for f in v] for k, v in use_functions.items()},
            'registrationCallers': registrar_callers,
            'growth': {'policy': 'capacity < 8 -> 8, else capacity + capacity / 2 (the add, 0x321B6C)',
                'allocatorVtable': '0x168B5A0', 'allocate': '0x5C2E10', 'free': '0x5C2ED0',
                'allocateCall': '(self, out {pointer, size}, bytes, 8) -> out (vtable +0x30)',
                'runtimeRule': 'the same allocator and policy; the array pointer, then the capacity; the old array '
                    'is kept allocated (a lookup may still read it)'}},
        'format': {'magic': '0x%08X' % hd2_text.MAGIC, 'type': '0x%016X' % hd2_text.STRINGS_TYPE,
            'header': ['magic', 'language count', 'id count'], 'then': ['language hashes (ascending)',
                'ids (ascending)', 'language x id offsets from the table start (0 = absent)', 'NUL-terminated UTF-8'],
            'idRule': 'upper 32 bits of MurmurHash64A (seed 0) of the key',
            'vanillaTables': len(tables), 'rebuiltByteForByte': rebuilt, 'vanillaIds': len(vanilla_ids),
            'tablesPerLanguage': {codes[k]: len(v) for k, v in sorted(by_language.items())},
            'languagesPerTable': sorted(Counter(len(t) for t in parsed.values()).items()),
            'shippedNames': dict(shipped), 'basesNotShipped': missing_bases},
        'languages': [{'code': code, 'hash': '0x%08X' % hd2_text.language_hash(code), 'sample120mmName': samples[code]}
            for code in hd2_text.LANGUAGES],
        'snapshots': snapshots,
        'proofText': {'resource': PROOF_RESOURCE, 'texts': custom, 'tableBytes': len(custom_table),
            'resolvesInEveryLanguage': True, 'vanillaTextUnchanged': True},
        'conclusion': ('Every displayed stratagem text id is looked up by exe 0x321C40, the only reader of the text '
            'registry, which walks its tables in order. A table the Runtime owns, appended after the game\'s own '
            'into spare registry capacity, makes the Runtime\'s ids resolve on every path without changing any game '
            'table or registration. The game rebuilds the registry from its own list on a language change, so the '
            'Runtime re-registers after one; it never grows the array (only the game does that, at startup).')}
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; tables', len(tables), 'rebuilt', rebuilt, '; registry',
        [(s['count'], s['capacity']) for s in snapshots], '; slot functions',
        {k: v for k, v in result['registry']['gameSlotUseFunctions'].items()})


def hd2_archive_hash(name):
    import hd2_archive
    return hd2_archive.resource_hash(name)


if __name__ == '__main__':
    main()
