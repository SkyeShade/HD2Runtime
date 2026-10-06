"""Where a dropped or held support weapon's icon and name come from, and whether one call's EAT-17G can look different
from the vanilla EAT-17 (docs/research/support-item-presentation-F5FEE03DCFDB.md). Read-only, offline.

Proves on build F5FEE03DCFDB, from the game.dll image, the seven retained snapshots, the pinned entity tables and the
game's archives:

1. The presentation data is TYPE data. The weapon's icon and name live in two component type tables that the game
   reads in place: EncyclopediaEntry (entity manager +0xF126D8; lookup 0x4F8A50 by the entity's type hash) and
   Spottable (+0xF12860; lookup 0x4FE440). Neither lookup has an instance resolver, the instance-copy switch
   (0x5740B0) has no case for either table, and the Spottable instance records hold no icon. Every record has one
   owner entity. (Equipment does have an instance resolver, 0x5092B0, but holds no weapon-specific icon or name: its
   drop icon is the shared drop_support for every support weapon.)
2. The consumers (all of them read the type record of the entity's own type hash):
   - HUD weapon panel 0x1827740 (from 0x1825F40, only when the wielded entity +0xBCD4 changes): a loadout-table
     weapon (0x11E78E0: game+0x33269E8 +0x1B28, six categories, support = 2) takes EncyclopediaEntry +0x10 (else +8)
     as the name and +0x30 as the image (GUI API +0xD8: the material's slot texture, with fallback; 0x1450120);
     only a non-table entity falls back to its StratagemInfo row (0x11F2D00: +0x28 / +0xB0).
   - Interaction prompt 0xFFB710 (every game update 0xAB5000, up to 32 prompts): the zone label is "#ITEM", so the
     text is EncyclopediaEntry +8 (prefix +0x24 only for loadout category 1); an Item (marker type 10) takes
     Spottable +0x38 as the icon with kind = Spottable +0x40 (2: a GUI material by name, no fallback); a hellpod rack
     takes StratagemInfo[rack +0x28] +0xB0 instead.
   - Minimap item layer 0x18B13D0 (from 0x18A7C60: clip_center / clip_distance / atlas_scissor): Spottable +0x38
     through GUI API +0xD8 (with fallback), EncyclopediaEntry +8 as the label.
   - Equipment icon list 0x182F560 (from 0x182D9E0): Spottable +0x38 (kind +0x40), else EncyclopediaEntry +0x30
     (kind 1), 32 x 32, through 0x1832A00 (a template GUI material and the texture by name).
   - Player equipment card 0x1819A70: EncyclopediaEntry +0x30 and Spottable +0x38, set when changed (0x1450120).
   - Notifications 0x13D0A90 and a list 0x198B960: Spottable +0x38 through 0x67CB70, EncyclopediaEntry +8.
   - The ping (0xA48AA0) copies the Spottable record to the stack; the replicated ping names only the entity.
3. The values: Spottable +0x38 of every support weapon IS its stratagem's icon value (StratagemInfo +0xB0: a GUI
   material and an atlas sprite, always resident); EncyclopediaEntry +8 / +0 / +0x14 ARE the stratagem's name, cased
   name and description ids; EncyclopediaEntry +0x30 is a different, mission-only weapon image (material + sprite).
4. The carrier weapon. A support weapon type no player brings can carry a mission-scoped presentation: the
   EAT-700 (expendable_napalm_launcher) has exactly the EAT-17's components, equipment, magazine and backblast, a
   rocket that differs only in its direct-hit damage and impact explosion, only its own stratagem row delivers its
   rack, and it is in no world loot table (the EAT-17 is).

Output: research/support-item-presentation-F5FEE03DCFDB.json. Nothing is written to the game; no artwork is made.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from capstone import x86  # noqa: E402

import hd2_game_data  # noqa: E402
import hd2_image  # noqa: E402
import hd2_text  # noqa: E402
import research_event_state as base  # noqa: E402
import research_image_resources as images  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
from scan import settings, tables, xref  # noqa: E402

OUTPUT = ROOT / 'research/support-item-presentation-F5FEE03DCFDB.json'
CALLDOWN = ROOT / 'research/stratagem-calldown-F5FEE03DCFDB.json'
POD_PAYLOADS = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
MISSION = [s for s in SNAPSHOTS if 'mission' in s]
ENTITY_MANAGER = 0x346BF98
LOADOUT_WEAPONS = 0x33269E8            # loadout weapon table: categories at +0x1B28 (start) / +0x1B44 (count)
SPOTTABLE_MANAGER = 0x3326450
TYPE_TABLES = {'EncyclopediaEntryComponentData': 0xF126D8, 'SpottableComponentData': 0xF12860,
    'EquipmentComponentData': 0xF12BC0, 'InteractableComponentData': 0xF12C18, 'LoadoutEntryComponentData': 0xF12560}
LOOKUPS = {0x4F8A50: 'encyclopedia', 0x4FE440: 'spottable', 0x508E90: 'equipment_type', 0x5092B0: 'equipment',
    0x50ACB0: 'interactable', 0x50AC10: 'interactable_type'}
INSTANCE_COPY_SWITCH = (0x5740B0, 0x577400)
EAT17, EAT700, EAT411 = 0x80932FA0ED6901D3, 0xB2B5E0D185605F9E, 0x7617642765AC38C7
FAMILY = {'EAT-17': EAT17, 'EAT-700': EAT700, 'EAT-411': EAT411}

# Reviewed instruction pins: (rva, exact instruction, rip target or None, role). Re-decoded on every run and
# compared byte for byte in every retained snapshot.
PINS = {
    'lookups': [
        (0x4F8A5F, 'mov r10, qword ptr [rax + 0xf126d8]', None, 'EncyclopediaEntry lookup: the type table'),
        (0x4F8AD1, 'add rcx, 0x17c', None, '... records after the 1330-slot index (0x17C x 0x38 = 0x5320)'),
        (0x4F8AD8, 'imul rax, rcx, 0x38', None, '... a 0x38-byte TYPE record; no instance map anywhere'),
        (0x4FE44F, 'mov r10, qword ptr [rax + 0xf12860]', None, 'Spottable lookup: the type table'),
        (0x4FE4C1, 'add rcx, 0x134', None, '... records after the 1386-slot index (0x134 x 0x48 = 0x56A0)'),
        (0x508E9F, 'mov r10, qword ptr [rax + 0xf12bc0]', None, 'Equipment type lookup'),
        (0x5092D2, 'mov r11, qword ptr [rip + 0x2e1dae7]', 0x3326DC0, 'Equipment resolver: the equipment manager'),
        (0x509359, 'add rax, qword ptr [r11 + 0x90]', None, '... the entity\'s own 0xE8 copy at +0x90 if one exists'),
        (0x50936C, 'jmp 0x508e90', None, '... else the type record'),
        (0x575A0E, 'call 0x508e90', None, 'the instance-copy switch has an Equipment case (none for the other two)'),
    ],
    'hudWeaponPanel': [
        (0x12EC040, 'call 0x1825f40', None, 'mission HUD root 0x12EBC50 -> weapon panel update'),
        (0x1826999, 'cmp ebx, dword ptr [rax + 0xbcd4]', None, 'rebuilt only when the wielded entity changes ...'),
        (0x18269AE, 'mov dword ptr [rax + 0xbcd4], ebx', None, '... (or the dirty flag +0xBCD1)'),
        (0x1826A61, 'call 0x1827740', None, 'name and image of the wielded weapon'),
        (0x1827762, 'mov rcx, qword ptr [rax]', None, 'the entity\'s TYPE hash (handle +0)'),
        (0x1827778, 'call 0x11e78e0', None, 'a loadout-table weapon ...'),
        (0x1827786, 'call 0x4f8a50', None, '... reads its EncyclopediaEntry'),
        (0x1827792, 'call 0x11f2d00', None, 'else the stratagem row whose payload list names the type ...'),
        (0x18277AB, 'mov rbx, qword ptr [rbx + 0xb0]', None, '... its icon (+0x28 its name)'),
        (0x18277C2, 'mov edx, dword ptr [rax + 0x10]', None, 'name: EncyclopediaEntry +0x10 (short upper) ...'),
        (0x18277C9, 'mov edx, dword ptr [rax + 8]', None, '... else +8 (upper)'),
        (0x18277CC, 'mov rbx, qword ptr [rax + 0x30]', None, 'image: EncyclopediaEntry +0x30'),
        (0x18277DB, 'call 0x143bf90', None, 'the name id to the text widget'),
        (0x18277F5, 'mov rax, qword ptr [rcx + 0xd8]', None, 'GUI API +0xD8: the material\'s slot texture (fallback)'),
        (0x1827841, 'call qword ptr [r9 + 0x338]', None, 'texture size -> aspect'),
        (0x18278B9, 'call 0x1450120', None, 'image bound by name (atlas sprite, else texture)'),
        (0x11E78E5, 'mov rbx, qword ptr [rip + 0x213f0fc]', LOADOUT_WEAPONS, 'the loadout weapon table'),
        (0x11E78F2, 'lea r9, [rbx + 0x1b28]', None, 'category starts (+0x1B28) and counts (+0x1C)'),
        (0x11E7920, 'cmp qword ptr [rax], rcx', None, 'entry +8 == the type'),
        (0x11E7944, 'cmp r11d, 7', None, 'six categories (support = 2)'),
        (0x11F2D25, 'mov r8d, dword ptr [rbx + 0xa0]', None, 'StratagemInfo payload count ...'),
        (0x11F2D38, 'cmp qword ptr [r10 + rax*8], rcx', None, '... payload +0x98 [i] == the type'),
        (0x11E7B57, 'mov eax, r11d', None, 'category of a type (the prompt\'s prefix condition)'),
    ],
    'interactionPrompt': [
        (0xAB5E52, 'call 0xffb710', None, 'every game update (0xAB5000)'),
        (0xFFBE85, 'call 0x50acb0', None, 'the candidate\'s Interactable'),
        (0xFFC2AE, 'call 0x4fe440', None, 'Spottable of the TYPE'),
        (0xFFC2BF, 'mov ecx, dword ptr [rax + 0x14]', None, 'marker type ...'),
        (0xFFC2C2, 'sub ecx, 0xa', None, '... Item (10) or Sample (11)'),
        (0xFFC2D2, 'mov rsi, qword ptr [rip + 0x232a177]', SPOTTABLE_MANAGER, 'the Spottable instance manager: '
            'only to find the entity\'s descriptor'),
        (0xFFC3FF, 'call 0x4fe440', None, 'the descriptor\'s TYPE -> Spottable'),
        (0xFFC404, 'mov rcx, qword ptr [rax + 0x38]', None, 'icon = Spottable +0x38 (marker_icon)'),
        (0xFFC341, 'mov qword ptr [rsi + rbx + 0x10], rcx', None, 'prompt entry +0x10: the icon name'),
        (0xFFC34A, 'call 0x67cc40', None, 'kind = Spottable +0x40 (marker_texture_type)'),
        (0xFFC34F, 'mov dword ptr [rsi + rbx + 0x18], eax', None, 'prompt entry +0x18: kind (2 = GUI material)'),
        (0xFFC41D, 'mov r14, qword ptr [rip + 0x232a634]', 0x3326A58, 'Item: is it a hellpod rack? ...'),
        (0xFFC6CB, 'mov ecx, dword ptr [rdx + rax + 0x28]', None, '... the rack\'s own stratagem type'),
        (0xFFC703, 'mov rax, qword ptr [rax + 0xb0]', None, '... that row\'s icon instead'),
        (0xFFC71E, 'mov dword ptr [r15 + r12 + 0x18], 2', None, '... kind 2 (GUI material)'),
        (0xFFC4EC, 'call 0x4f8a50', None, 'EncyclopediaEntry of the type ...'),
        (0xFFC4F6, 'mov eax, dword ptr [rax + 8]', None, '... +8: the upper-case name'),
        (0xFFC504, 'call 0xb5c310', None, 'name override: objective shells only'),
        (0xFFC519, 'mov dword ptr [r15 + r12 + 0x2c], eax', None, 'prompt entry +0x2C: the text id'),
        (0xFFC53B, 'mov ebx, dword ptr [rax + 0x24]', None, 'prefix: EncyclopediaEntry +0x24 ...'),
        (0xFFC546, 'cmp eax, 1', None, '... only for loadout category 1'),
        (0xFFC777, 'mov eax, dword ptr [rcx + r11 + 0x40]', None, 'else the zone label (the EAT\'s: "#ITEM")'),
        (0x67CCED, 'call 0x4fe440', None, 'kind getter: Spottable of the type ...'),
        (0x67CCF5, 'mov eax, dword ptr [rdi + 0x40]', None, '... +0x40'),
        (0xB5C357, 'cmp dword ptr [r12 + rax*8 + 0x1c20], 0x64', None, 'name override: component kind 100 ...'),
        (0xB5C436, 'call 0x502190', None, '... ObjectiveShell data'),
        (0x5021A6, 'mov r10, qword ptr [rax + 0xf129f8]', None, 'the ObjectiveShell type table'),
    ],
    'markers': [
        (0x12EC155, 'call 0x18a7c60', None, 'HUD root -> minimap (clip_center / clip_distance / atlas_scissor)'),
        (0x18A871F, 'call 0x18b13d0', None, 'minimap item layer'),
        (0x18B1AC5, 'call 0x4fe440', None, 'Spottable of the type ...'),
        (0x18B1ACA, 'mov rbx, qword ptr [rax + 0x38]', None, '... marker icon'),
        (0x18B1AF2, 'mov r8, qword ptr [rdx + 0xd8]', None, 'GUI API +0xD8 (material slot texture, fallback)'),
        (0x18B1B43, 'call 0x4f8a50', None, 'EncyclopediaEntry ...'),
        (0x18B1B4D, 'mov eax, dword ptr [rax + 8]', None, '... +8: the label'),
        (0x12EBEDA, 'call 0x182d9e0', None, 'HUD root -> equipment icon list'),
        (0x182DBD3, 'call 0x182f560', None, '... per entry'),
        (0x1831117, 'call 0x4fe440', None, 'Spottable of the type ...'),
        (0x1831128, 'mov r9d, dword ptr [rax + 0x40]', None, '... kind = +0x40'),
        (0x183112C, 'mov rdx, qword ptr [rax + 0x38]', None, '... icon = +0x38'),
        (0x1831148, 'call 0x4f8a50', None, 'else EncyclopediaEntry ...'),
        (0x1831159, 'mov rdx, qword ptr [rax + 0x30]', None, '... +0x30'),
        (0x183115D, 'mov r9d, 1', None, '... kind 1'),
        (0x1831178, 'call 0x1832a00', None, 'set the 32 x 32 icon'),
        (0x1832A62, 'cmp ebp, 2', None, 'kind 2 / other: a vanilla template material ...'),
        (0x1832A71, 'call 0x1450230', None, '... and the texture by name'),
        (0x12EBDA7, 'call 0x1819a70', None, 'HUD root -> player equipment card'),
        (0x181A883, 'call 0x4f8a50', None, 'EncyclopediaEntry of a loadout-table weapon ...'),
        (0x181A89B, 'mov rcx, qword ptr [rax + 0x30]', None, '... +0x30 (set when it changes)'),
        (0x181A939, 'call 0x4fe440', None, 'Spottable ...'),
        (0x181A94A, 'mov r9, qword ptr [rax + 0x38]', None, '... +0x38 (set when it changes)'),
        (0x181A9A3, 'call 0x1450120', None, 'image bound by name'),
        (0xA496C2, 'call 0x4fe440', None, 'ping: Spottable of the type ...'),
        (0xA496CE, 'movups xmm1, xmmword ptr [rax + 0x30]', None, '... the whole record copied ...'),
        (0xA496E1, 'movaps xmmword ptr [rbp + 0xc0], xmm1', None, '... to the stack (no instance copy)'),
    ],
    'equipment': [
        (0x182BE14, 'call 0x508e90', None, 'drop wheel: Equipment TYPE record ...'),
        (0x182BE1E, 'mov rbp, qword ptr [rax + 0x98]', None, '... drop_icon_ui (drop_support for every support weapon)'),
        (0x8C222A, 'call 0x5092b0', None, 'show_in_pickup_widget getter (no static caller)'),
    ],
}

# The on-screen identity of each consumer function (the data path is pinned above; the identity is the evidence's).
CONSUMERS = {
    0x1827740: ('HUD weapon panel (wielded weapon name + image)', 'STRONG',
        'weapon_function/bullet + heat icons beside it; rebuilt on a wielded-entity change'),
    0x1827C20: ('HUD weapon panel, alternate state', 'STRONG', 'same reads as 0x1827740'),
    0x1827690: ('HUD weapon panel getter (no static caller)', 'PLAUSIBLE', 'same reads as 0x1827740'),
    0xFFB710: ('interaction prompt (pickup prompt)', 'STRONG',
        'up to 32 prompt widgets of the local avatar, built every game update; zone label "#ITEM"'),
    0x18B13D0: ('minimap item layer (map marker)', 'STRONG', 'clip_center / clip_distance / edge_fade / atlas_scissor'),
    0x182F560: ('equipment icon list (32 x 32 icons; inventory manager)', 'PLAUSIBLE', 'squad / equipment icons'),
    0x1819A70: ('player equipment card (weapon image, equipment icon)', 'PLAUSIBLE', 'inventory + avatar managers'),
    0x13D0A90: ('HUD notification / feed entry', 'PLAUSIBLE', 'stratagem-icon consumer 0x13D14E4, beacon colours'),
    0x198B960: ('HUD list entry with a checkmark', 'PLAUSIBLE', 'content/ui/shared/misc/checkmark_icon'),
    0xA48AA0: ('ping / spotting', 'STRONG', 'SpottedEntity / SpottedPosition: the replicated ping names the entity'),
    0x182A550: ('HUD name text (short upper, else upper)', 'PLAUSIBLE', 'called 3x by the HUD root'),
    0x182C790: ('HUD name text (short upper, else upper)', 'PLAUSIBLE', 'no static caller'),
    0x182BAF0: ('drop wheel', 'STRONG', 'content/ui/mission/hud/wheel/drop/drop_support'),
}
MEMBERS = {'encyclopedia': {0x0: 'loc_name', 0x8: 'loc_name_upper', 0x10: 'loc_name_short_upper',
    0x14: 'description', 0x24: 'prefix', 0x28: 'fluff', 0x30: 'icon'},
    'spottable': {0x14: 'marker_type', 0x38: 'marker_icon', 0x40: 'marker_texture_type'}}


def hexid(value: int) -> str:
    return '0x%016X' % value


def prove_pins(image: xref.CodeImage) -> dict:
    out = {}
    for group, rows in PINS.items():
        out[group] = []
        for rva, asm, target, role in rows:
            pin = image.pin(rva, role, asm)
            if target is not None and pin.get('ripTarget') != target:
                raise ValueError('pin %x: rip target %r, expected %x' % (rva, pin.get('ripTarget'), target))
            out[group].append(pin)
    return out


def raw_slot_readers(image: xref.CodeImage, slot: int) -> list[dict]:
    """Every instruction in game.dll whose displacement is the type-table slot (leaf functions included)."""
    lo, hi = image.text
    needle, out = slot.to_bytes(4, 'little'), []
    at = image.data.find(needle, lo, hi)
    while at >= 0:
        start = image.root(at) or next((p for p in range(at, at - 0x2000, -1) if p % 16 == 0 and
            image.data[p - 1] == 0xCC), None)
        if start is not None:
            for ins in image.md.disasm(image.data[start:at + 16], start):
                if ins.address <= at < ins.address + ins.size:
                    if any(op.type == x86.X86_OP_MEM and op.mem.disp == slot for op in ins.operands):
                        out.append({'rva': ins.address, 'function': start, 'asm': ins.mnemonic + ' ' + ins.op_str})
                    break
                if ins.address > at:
                    break
        at = image.data.find(needle, at + 1, hi)
    return out


def reads_after(image: xref.CodeImage, function: int, call_site: int, window: int = 40) -> list[int]:
    """Displacements read through the returned record (rax and its register copies) until the next call."""
    insns = image.function_insns(function)
    index = next((i for i, ins in enumerate(insns) if ins.address == call_site), None)
    if index is None:
        return []
    regs, found = {'rax'}, []
    for ins in insns[index + 1:index + 1 + window]:
        if ins.mnemonic == 'call':
            break
        for op in ins.operands:
            if op.type == x86.X86_OP_MEM and op.mem.base and ins.reg_name(op.mem.base) in regs \
                    and ins.mnemonic not in ('nop', 'lea'):
                found.append(op.mem.disp)
        if ins.mnemonic == 'mov' and len(ins.operands) == 2 and ins.operands[0].type == x86.X86_OP_REG:
            dst = ins.reg_name(ins.operands[0].reg)
            if ins.operands[1].type == x86.X86_OP_REG and ins.reg_name(ins.operands[1].reg) in regs:
                regs.add(dst)
            elif dst in regs and dst != 'rax':
                regs.discard(dst)
    return sorted(set(found))


def census(image: xref.CodeImage) -> dict:
    """Every call of the presentation lookups and the record members read after it; every direct table reader."""
    sites = {}
    for function, name in LOOKUPS.items():
        rows = []
        for ins in image.references(function):
            root = image.root(ins.address)
            reads = reads_after(image, root, ins.address) if root and ins.mnemonic == 'call' else []
            label = CONSUMERS.get(root)
            rows.append({'site': ins.address, 'function': root, 'kind': ins.mnemonic, 'reads': reads,
                'consumer': label[0] if label else None})
        sites[name] = rows
    direct = {component: raw_slot_readers(image, slot) for component, slot in TYPE_TABLES.items()}
    lo, hi = INSTANCE_COPY_SWITCH
    switch_slots = sorted({op.mem.disp for ins in image.md.disasm(image.data[lo:hi], lo) for op in ins.operands
        if op.type == x86.X86_OP_MEM and op.mem.disp in TYPE_TABLES.values()})
    member_readers = {}
    for table, members in MEMBERS.items():
        for offset, member in members.items():
            member_readers['%s+0x%X %s' % (table, offset, member)] = sorted({'0x%X' % r['function'] for r in
                sites[table] if offset in r['reads']})
    unresolved = {name: sorted({'0x%X' % r['function'] for r in rows if r['kind'] == 'call' and not r['reads']
        and r['function']}) for name, rows in sites.items() if name in ('encyclopedia', 'spottable')}
    return {'sites': sites, 'directTableReaders': direct, 'unresolvedCallers': unresolved,
        'instanceCopySwitchSlots': ['0x%X' % s for s in switch_slots],
        'instanceCopySwitchCovers': {name: slot in switch_slots for name, slot in TYPE_TABLES.items()},
        'memberReaders': member_readers}


def game_texts():
    data = hd2_game_data.Data()
    tables_ = [data.read(archive, main) for archive, _, kind, main, *_ in data.tables()
        if kind == hd2_text.STRINGS_TYPE and main[1] >= 16]
    us = hd2_text.language_hash('us')

    def text(value):
        try:
            return hd2_text.lookup(tables_, value, us) if value else None
        except Exception:  # noqa: BLE001 - a missing id is an observation, not an error
            return None
    return text


def weapon_rows(t: tables.EntityTables, text) -> dict:
    enc, spot = t.component('EncyclopediaEntryComponentData'), t.component('SpottableComponentData')
    equip, entry = t.component('EquipmentComponentData'), t.component('LoadoutEntryComponentData')
    inter = t.component('InteractableComponentData')
    rows = json.loads(CALLDOWN.read_text(encoding='utf-8'))['presentation']['rows']
    by_icon = {}
    for row in rows:
        by_icon.setdefault(int(row['icon'], 16), []).append(row)
    out = {}
    for resource in t.find('equipment/support_weapons/'):
        def u(component, offset, width=4):
            record = component.record_of(resource)
            return None if record is None else int.from_bytes(component.raw(record)[offset:offset + width], 'little')
        marker = u(spot, 0x38, 8)
        stratagems = by_icon.get(marker, []) if marker else []
        name, cased, desc = u(enc, 8), u(enc, 0), u(enc, 0x14)
        label = u(inter, 8 + 52)
        out[t.label(resource)] = {
            'resource': hexid(resource),
            'encyclopedia': {'record': enc.record_of(resource), 'owners': len(enc.owners(enc.record_of(resource)))
                    if enc.record_of(resource) is not None else 0,
                'loc_name': cased and '0x%08X' % cased, 'loc_name_upper': name and '0x%08X' % name,
                'loc_name_short_upper': u(enc, 0x10), 'description': desc and '0x%08X' % desc,
                'prefix': u(enc, 0x24) and '0x%08X' % u(enc, 0x24), 'icon': u(enc, 0x30, 8) and hexid(u(enc, 0x30, 8)),
                'text': {'name': text(name), 'nameCased': text(cased), 'prefix': text(u(enc, 0x24))}},
            'spottable': {'record': spot.record_of(resource), 'owners': len(spot.owners(spot.record_of(resource)))
                    if spot.record_of(resource) is not None else 0,
                'marker_type': u(spot, 0x14), 'marker_icon': marker and hexid(marker),
                'marker_texture_type': u(spot, 0x40)},
            'equipment': {'equipment_type': u(equip, 0x80), 'drop_icon_ui': u(equip, 0x98, 8) and
                hexid(u(equip, 0x98, 8)), 'show_in_pickup_widget': u(equip, 0xC6, 1)},
            'interactZoneLabel': {'id': label and '0x%08X' % label, 'text': text(label)},
            'loadoutEntryId': u(entry, 0),
            'stratagemRows': [{'type': r['type'], 'nativeTypeName': r['nativeTypeName'], 'id': r['id'],
                'nameIsEncyclopediaUpper': r['name'] == name, 'nameCasedIsEncyclopediaName': r['nameCased'] == cased,
                'descriptionIsEncyclopedia': r['description'] == desc} for r in stratagems],
        }
    return out


def type_table_identity(t: tables.EntityTables) -> dict:
    """In every snapshot the entity manager's type table IS the pinned table, byte for byte (read in place)."""
    out = {}
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        try:
            em = mem.ptr(mem.game + ENTITY_MANAGER)
            out[name] = {component: mem.read(mem.ptr(em + slot), len(t.component(component).body)) ==
                t.component(component).body for component, slot in TYPE_TABLES.items()}
        finally:
            mem.close()
    return out


def snapshot_observations(t: tables.EntityTables, weapons: dict) -> dict:
    mat, tex = hd2_image.MATERIAL_TYPE, hd2_image.TEXTURE_TYPE
    values = {}
    for label, row in weapons.items():
        if row['encyclopedia']['icon']:
            values[label + '.encyclopedia.icon'] = int(row['encyclopedia']['icon'], 16)
        if row['spottable']['marker_icon']:
            values[label + '.spottable.marker_icon'] = int(row['spottable']['marker_icon'], 16)
    resources, table, world, instance_icons = {}, {}, {}, {}
    marker_bytes = {struct.pack('<Q', v) for k, v in values.items() if k.endswith('marker_icon')}
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        try:
            rm = images.Manager(mem)
            sprites = (mem.ptr(rm.rm + 0x2A0), mem.u32(rm.rm + 0x2B4))
            kinds = {}
            for key, value in values.items():
                kinds[key] = {'material': rm.lookup(mat, value)[0], 'texture': rm.lookup(tex, value)[0],
                    'atlasSprite': images.resolve(mem, sprites[0], sprites[1], 24, 0x10, 0, value) is not None}
            summary = {}
            for kind in ('encyclopedia.icon', 'spottable.marker_icon'):
                rows = [v for k, v in kinds.items() if k.endswith(kind)]
                summary[kind] = {'values': len(rows), 'material': sum(r['material'] == 'present' for r in rows),
                    'atlasSprite': sum(r['atlasSprite'] for r in rows),
                    'texture': sum(r['texture'] == 'present' for r in rows)}
            resources[name] = summary
            g = mem.ptr(mem.game + LOADOUT_WEAPONS)
            found = {}
            for label, resource in FAMILY.items():
                for k in range(6):
                    start, count = mem.u32(g + 0x1B28 + 4 * k), mem.u32(g + 0x1B28 + 4 * k + 0x1C)
                    if any(mem.u64(g + (start + i) * 32 + 8) == resource for i in range(count or 0)):
                        found[label] = k + 1
            table[name] = found
            if name in MISSION:
                manager = mem.ptr(mem.game + SPOTTABLE_MANAGER)
                count, handles = mem.u32(manager + 0x10), mem.ptr(manager + 0x38)
                kinds_present = {}
                for i in range(count or 0):
                    handle = mem.ptr(handles + 8 * i)
                    kind = handle and mem.u64(handle)
                    if kind and (t.name(kind) or '').find('/support_weapons/') >= 0:
                        kinds_present[t.label(kind)] = kinds_present.get(t.label(kind), 0) + 1
                world[name] = {'spottableInstances': count, 'supportWeapons': kinds_present}
                block = b''
                for stride in (0x48, 0x30, 0x18):
                    block = mem.read(mem.ptr(manager + 0x40), stride * (count or 0)) or b''
                    if block:
                        break
                instance_icons[name] = {'bytesSearched': len(block), 'markerIconFound': any(m in block
                    for m in marker_bytes)}
        finally:
            mem.close()
    return {'resourceKinds': resources, 'loadoutWeaponCategory': table, 'worldSupportWeapons': world,
        'spottableInstanceBlockHoldsAnIcon': instance_icons}


def carrier_candidates(t: tables.EntityTables, weapons: dict) -> list[dict]:
    view = settings.SettingsView(t)
    pods = json.loads(POD_PAYLOADS.read_text(encoding='utf-8'))
    loot = {e for table in pods['worldLoot']['tables'] for e in table['entries']}
    racks = {}
    for rack in pods['racks']:
        for slot in rack['slots']:
            if slot['item']:
                racks.setdefault(slot['item'], set()).update(c['name'] for c in rack['consumers'])
    pw = t.component('ProjectileWeaponComponentData')
    base_components = set(t.entity(EAT17))
    eat_projectile = view.decode('projectile', pw.decode(pw.record_of(EAT17))['0'])
    out = []
    for label, row in weapons.items():
        resource = int(row['resource'], 16)
        if resource == EAT17:
            continue
        components = set(t.entity(resource))
        same = {c: (t.component(c).raw(t.component(c).record_of(resource)) ==
            t.component(c).raw(t.component(c).record_of(EAT17))) for c in ('WeaponMagazineComponentData',
            'BackblastComponentData') if c in components}
        projectile = None
        if pw.record_of(resource) is not None:
            kind = pw.decode(pw.record_of(resource))['0']
            p = view.decode('projectile', kind)
            if p is not None:
                differing = sorted(k for k in eat_projectile if eat_projectile[k] != p.get(k))
                projectile = {'type': p['0'], 'differsFromEat17': differing}
            else:
                projectile = {'type': kind, 'differsFromEat17': ['no projectile row']}
        flight_same = projectile is not None and set(projectile['differsFromEat17']) <= {'0', '4', '8', '60', '144'}
        eligible = components == base_components and all(same.values()) and len(same) == 2 and flight_same
        out.append({'weapon': label, 'resource': row['resource'], 'sameComponentsAsEat17': components ==
            base_components, 'sameRecords': same, 'equipmentType': row['equipment']['equipment_type'],
            'projectile': projectile, 'flightSameAsEat17': flight_same,
            'inWorldLoot': row['resource'] in loot, 'deliveredBy': sorted(racks.get(row['resource'], [])),
            'eatCompatible': eligible})
    out.sort(key=lambda c: (not c['eatCompatible'], c['inWorldLoot'], c['weapon']))
    return out


def main():
    t = tables.pinned()
    image = xref.CodeImage.from_snapshot('game.dll')
    pins = prove_pins(image)
    flat = [p for rows in pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    text = game_texts()
    weapons = weapon_rows(t, text)
    identity = type_table_identity(t)
    if not all(all(v.values()) for v in identity.values()):
        raise ValueError('a type table is not the pinned table in place: %r' % identity)
    found = census(image)
    if found['instanceCopySwitchCovers']['EncyclopediaEntryComponentData'] or \
            found['instanceCopySwitchCovers']['SpottableComponentData']:
        raise ValueError('the instance-copy switch reaches a presentation table')
    observations = snapshot_observations(t, weapons)
    candidates = carrier_candidates(t, weapons)
    eat = weapons['lat_oneshot']
    matched = [r for r in weapons.values() if r['stratagemRows']]
    checks = {
        'weaponsWhoseMarkerIconIsAStratagemIcon': '%d of %d' % (len(matched), len(weapons)),
        'markerIconIsStratagemIcon': all(r['stratagemRows'] and all(s['nameIsEncyclopediaUpper'] for s in
            r['stratagemRows']) for r in weapons.values() if r['spottable']['marker_icon'] and r['stratagemRows']),
        'eat17ZoneLabel': eat['interactZoneLabel']['text'],
        'everyRecordOneOwner': all(r['encyclopedia']['owners'] == 1 and r['spottable']['owners'] == 1
            for r in weapons.values() if r['encyclopedia']['record'] is not None and r['spottable']['record']
            is not None),
        'dropIconsShared': sorted({r['equipment']['drop_icon_ui'] for r in weapons.values()}),
    }
    result = {
        'build': 'F5FEE03DCFDB', 'writes': 0, 'protectionChanges': 0,
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': relocation,
        'typeTables': {'slots': {k: '0x%X' % v for k, v in TYPE_TABLES.items()}, 'inPlaceInEverySnapshot': identity},
        'lookups': {'0x%X' % k: v for k, v in LOOKUPS.items()},
        'consumers': {'0x%X' % k: {'screen': v[0], 'identity': v[1], 'evidence': v[2]} for k, v in CONSUMERS.items()},
        'census': found,
        'weapons': weapons,
        'checks': checks,
        'snapshots': observations,
        'carrierCandidates': candidates,
        'verdicts': VERDICTS,
        'conclusion': CONCLUSION,
    }
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat), '; carrier candidates',
        [c['weapon'] for c in candidates if c['eatCompatible']], '; checks', checks)


VERDICTS = {
    'hudWeaponPanel': {'source': 'EncyclopediaEntry of the wielded entity\'s TYPE: name +0x10 else +8 (text ids), '
        'image +0x30 (material name -> slot texture, with fallback)', 'instance': False,
        'timing': 'when the wielded entity changes', 'confidence': 'CONFIRMED (code) / STRONG (screen)'},
    'pickupPrompt': {'source': 'text EncyclopediaEntry +8 of the TYPE ("#ITEM" zone label); icon Spottable +0x38 of '
        'the TYPE with kind Spottable +0x40 = 2 (GUI material by name, NO fallback); a rack: StratagemInfo[rack +0x28] '
        '+0xB0', 'instance': False, 'timing': 'every game update', 'confidence': 'CONFIRMED (code) / STRONG (screen)'},
    'mapMarker': {'source': 'Spottable +0x38 of the TYPE (GUI API +0xD8, with fallback); label EncyclopediaEntry +8',
        'instance': False, 'timing': 'every HUD update', 'confidence': 'CONFIRMED (code) / STRONG (minimap) / '
        'PLAUSIBLE (full map: not separately traced)'},
    'otherHud': {'source': 'equipment list, player card, notifications: the same two TYPE records',
        'instance': False, 'confidence': 'CONFIRMED (code) / PLAUSIBLE (screen)'},
    'perInstancePath': {'exists': False, 'confidence': 'CONFIRMED for the lookups and the instance-copy switch; '
        'STRONG for the whole consumer set (5 inline table readers, two script getters and 0x198B960 not traced '
        'to the screen)'},
    'carrierWeapon': {'candidate': 'EAT-700 Expendable Napalm (expendable_napalm_launcher)', 'confidence': 'STRONG'},
    'customIcon': {'spottableMarkerIcon': 'the same consumer classes as StratagemInfo +0xB0 (material required on '
        'the prompt; fallback elsewhere): the Runtime image family is accepted by the code (STRONG, not live)',
        'encyclopediaIcon': 'material-with-fallback and texture-by-name readers only (STRONG, not live)'},
    'customText': {'verdict': 'every reader passes a u32 id that only the game\'s one text lookup resolves '
        '(research/stratagem-text: 0x321C40 is the registry\'s only reader); a Runtime id resolves there',
        'confidence': 'STRONG (dev path only; custom text is not public)'},
}
CONCLUSION = ('No consumer of a dropped or held support weapon\'s icon or name reads per-instance data: the HUD weapon '
    'panel, the pickup prompt, the minimap and the other HUD lists all look up EncyclopediaEntry and Spottable by the '
    'entity\'s TYPE hash, in the shared type tables, and neither table has an instance copy. One call\'s EAT-17 cannot '
    'look different from another EAT-17, and the EAT-17\'s own records must never be written (it is in player '
    'loadouts and in the world loot table). The feasible design is a carrier weapon: deliver the EAT-700 Expendable '
    'Napalm (same components, equipment, magazine and backblast as the EAT-17; only its own row delivers it; in no '
    'loot table) and give its two type records a mission-scoped presentation (EncyclopediaEntry +8 / +0x30, Spottable '
    '+0x38) only while no lobby member brings the EAT-700, restored exactly on the return to the ship.')


if __name__ == '__main__':
    main()
