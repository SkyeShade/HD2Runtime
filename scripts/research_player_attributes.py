"""The per-player ATTRIBUTE STORE armor passives feed: EntityAttribute (game.dll 0x11D9DF0), the customization
manager behind it, the passive and armor-kit tables in game memory, its writers and its readers.
Read-only research against the retained snapshots (research/docs/player-attributes-F5FEE03DCFDB.md).

  py scripts/research_player_attributes.py      # write research/player-attributes-F5FEE03DCFDB.json

Every structural claim is pinned as exact instruction bytes (verified identical in every retained snapshot) and every
value is read from the snapshots. The filediver datalibrary dumps (armor sets, passive bonuses) are third-party
leads: they are compared with the tables the game holds in memory, never used as a source. Names of passives and
modifier effects are the game's own text (the text ids the in-memory rows carry, resolved through the installed
game's strings tables). Nothing writes. Requires capstone and numpy (research only).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/player-attributes-F5FEE03DCFDB.json'
LEADS = Path(r'C:\Users\Skye\Documents\HD2Mods\StrongerOrbitalLaser\local_research\dependencies'
    r'\filediver-reference\datalibrary')

# ---------------------------------------------------------------------------------------------------- globals
G_CUSTOMIZATION = 0x33264F8   # customization manager (= component world + 0xE9FC98); EntityAttribute's store
G_AVATAR = base.G_AVATAR      # 0x3326D20 avatar manager (records 0x78 apart)
G_PLAYER = base.G_PLAYER      # 0x3326468 player manager (entity -> player slot)
G_ENTITY_MANAGER = base.G_ENTITY_MANAGER
F_ENTITY_ATTRIBUTE = 0x11D9DF0
F_PASSIVE_VALUE = 0x11DA090   # float PassiveValue(u32 passiveId, ?, u32 key, float base)
F_APPLY_ATTRIBUTE = 0x87A3C0  # void ApplyAttribute(entity, key, float *inout) (generic Set/Add/Mul combiner)
F_UPDATE_PLAYER = 0x874520    # per-record pending -> applied (kits, passives)
F_UPDATE_ALL = 0x874D80       # per-frame: every record, then passive package load/unload
F_SET_ARMOR = 0x8760B0        # SetArmorKit(mgr, entity, kit id): pending + network field 0xB7D3A2EC
F_SET_HELMET = 0x875CD0
F_SET_CAPE = 0x875EC0
F_ADD_RECORD = (0x5405D0, 0x540660, 0x87BD20, 0x87BE00)
F_MOVE_RECORD = (0x87B5D0, 0x87BE90, 0x87C120)
F_RESIST = 0x87A430           # elemental resistance combiner (fire/arc/gas + all-element + impact)

# Manager layout (offsets from the manager), each proven by the pins below.
M_KITS, M_KIT_COUNT = 0x00, 0x08
M_PASSIVES, M_PASSIVE_COUNT, M_PASSIVE_INDEX, PASSIVE_IDS = 0x20, 0x28, 0x30, 42
M_RECORD_COUNT = 0x8E8
M_MAP = 0x930                 # {u32 key, u32 index} *slots; u32 capacity; u32 empty; u32 multiplier
M_DESCRIPTORS = 0x948         # u64 entity descriptor per record (descriptor +8 = entity, +0x10 = game object id)
M_APPLIED, APPLIED_STRIDE = 0x96C, 0x44
M_PENDING, PENDING_STRIDE = 0xA7C, 0x40
CAPACITY = 4
APPLIED = {0x00: 'u32 (3 on reset; copied from pending +0x00)', 0x04: 'helmet kit id', 0x08: 'cape kit id',
    0x0C: 'armor kit id', 0x10: 'u32 (copied from pending +0x10)', 0x24: 'u32 (pending +0x28)',
    0x28: 'byte', 0x29: 'byte', 0x2C: 'u32 (pending +0x2C)', 0x30: 'u32 (pending +0x38)', 0x34: 'u32 (pending +0x3C)',
    0x38: 'helmet passive id (flags bit 1)', 0x3C: 'armor passive id (flags bit 0)', 0x40: 'u32 (written by 0x877200)'}
MODIFIER_TYPES = {0: 'Set', 1: 'Add', 2: 'Multiply', 3: 'Time'}

PINS = {
    'manager': [
        (0x568EBA, 'lea rax, [rbx + 0xe9fc98]', None, 'manager = component world + 0xE9FC98'),
        (0x568EC1, 'mov qword ptr [rip + {rip}], rax', G_CUSTOMIZATION, 'the only store of the manager global'),
    ],
    'entityAttribute': [
        (0x11D9E08, 'mov r12d, r8d', None, 'flags'),
        (0x11D9E11, 'mov ebx, edx', None, 'key'),
        (0x11D9E19, 'mov r11, qword ptr [rip + {rip}]', G_AVATAR, 'avatar manager: is the entity an avatar?'),
        (0x11D9E41, 'mov r14, qword ptr [r11 + 0xf8]', None, 'avatar map slots'),
        (0x11D9ED1, 'imul rax, rcx, 0x78', None, 'avatar record stride'),
        (0x11D9EDA, 'mov edx, dword ptr [rax + r11 + 0x5478a4]', None, 'avatar -> player game object id'),
        (0x11D9EE2, 'call 0xfd9ba0', None, 'game object id -> player entity'),
        (0x11D9EF5, 'mov r9, qword ptr [rip + {rip}]', G_CUSTOMIZATION, 'customization manager'),
        (0x11D9EFF, 'mov r10d, dword ptr [r9 + 0x938]', None, 'entity map capacity'),
        (0x11D9F06, 'mov esi, dword ptr [r9 + 0x940]', None, 'entity map multiplier'),
        (0x11D9F1D, 'mov r14, qword ptr [r9 + 0x930]', None, 'entity map slots'),
        (0x11D9F24, 'mov ebp, dword ptr [r9 + 0x93c]', None, 'entity map empty key'),
        (0x11D9F7D, 'imul r11, rax, 0x44', None, 'applied record stride'),
        (0x11D9F81, 'mov eax, dword ptr [r11 + r9 + 0x9a8]', None, 'record +0x3C armor passive id'),
        (0x11D9F8D, 'test r12b, 1', None, 'flags bit 0 selects the armor passive'),
        (0x11D9F93, 'mov ecx, dword ptr [r9 + rax*4 + 0x30]', None, 'passive id -> table index'),
        (0x11D9F9D, 'mov rax, qword ptr [r9 + 0x20]', None, 'passive object array'),
        (0x11D9FAA, 'mov edx, dword ptr [r8 + 0x18]', None, 'modifier count'),
        (0x11D9FB4, 'mov r10, qword ptr [r8 + 0x10]', None, 'modifier array'),
        (0x11D9FC2, 'shl rax, 4', None, 'modifier stride 16'),
        (0x11D9FC9, 'cmp dword ptr [rax], ebx', None, 'first modifier whose id == key wins'),
        (0x11D9FDA, 'mov eax, dword ptr [r11 + r9 + 0x9a4]', None, 'record +0x38 helmet passive id'),
        (0x11D9FE6, 'test r12b, 2', None, 'flags bit 1 selects the helmet passive'),
        (0x11DA02A, 'xor eax, eax', None, 'absent: NULL'),
    ],
    'passiveValue': [
        (0x11DA0A4, 'mov ecx, dword ptr [rdx + rax*4 + 0x30]', None, 'passive id -> index'),
        (0x11DA0D0, 'cmp dword ptr [rcx], r8d', None, 'every modifier with the key'),
        (0x11DA0E6, 'mulss xmm2, dword ptr [rcx + 8]', None, 'Multiply: product'),
        (0x11DA0ED, 'addss xmm0, dword ptr [rcx + 8]', None, 'Add: sum'),
        (0x11DA0F4, 'movss xmm1, dword ptr [rcx + 8]', None, 'Set: replaces the base'),
        (0x11DA102, 'addss xmm0, xmm1', None, '(base or Set) + sum'),
        (0x11DA106, 'mulss xmm0, xmm2', None, '* product'),
    ],
    'applyAttribute': [
        (0x87A3CF, 'call 0x11d9df0', None, 'EntityAttribute(entity, key, 3)'),
        (0x87A3E3, 'mov eax, dword ptr [rax + 8]', None, 'Set: *out = value'),
        (0x87A3F1, 'test eax, 0xfffffffd', None, 'Add or Time: *out += value'),
        (0x87A402, 'mulss xmm0, dword ptr [rbx]', None, 'Multiply: *out *= value'),
    ],
    'writers': [
        (0x874556, 'lea r12, [r8 + 0xa7c]', None, 'pending block (0x40 per record)'),
        (0x874565, 'lea r15, [r8 + 0x96c]', None, 'applied record (0x44 per record)'),
        (0x874655, 'mov eax, dword ptr [r12 + 4]', None, 'pending helmet kit'),
        (0x87465A, 'mov dword ptr [r15 + 4], eax', None, 'applied helmet kit (after its package is ready)'),
        (0x874663, 'mov eax, dword ptr [rbx + 0x1c]', None, 'helmet kit Passive'),
        (0x87467F, 'mov dword ptr [r15 + 0x38], eax', None, 'applied helmet passive'),
        (0x8747FA, 'mov eax, dword ptr [r12 + 0xc]', None, 'pending armor kit'),
        (0x8747FF, 'mov dword ptr [r15 + 0xc], eax', None, 'applied armor kit (after its package is ready)'),
        (0x87480C, 'mov eax, dword ptr [rbx + 0x1c]', None, 'armor kit Passive'),
        (0x8748A4, 'mov dword ptr [r15 + 0x3c], eax', None, 'applied armor passive'),
        (0x874DFC, 'lea rbx, [rdi + 0x9a4]', None, 'passive package loop: both passive ids of every record'),
        (0x874EA6, 'mov edx, dword ptr [rdx + 0x30]', None, 'passive +0x30 = package resource'),
        (0x87618E, 'mov r8, qword ptr [r11]', None, 'SetArmorKit: unknown kit -> fallback'),
        (0x876195, 'cmp dword ptr [rax], 0x61b31723', None, 'fallback armor kit B-01 Tactical'),
        (0x8761AF, 'mov dword ptr [rsi + rdi + 0xa88], r8d', None, 'pending armor kit'),
        (0x8761B7, 'mov edx, 0xb7d3a2ec', None, 'network field of the armor kit'),
        (0x8761D1, 'call 0xfd97e0', None, 'replicate the field'),
        (0x54060E, 'movups xmmword ptr [rax + rbx + 0x96c], xmm0', None, 'new record zeroed (passives = 0)'),
    ],
    'armorRating': [
        (0x8781F7, 'mov edx, dword ptr [rdi + r10 + 0x978]', None, 'applied armor kit id'),
        (0x87822F, 'mov ecx, dword ptr [rbx + 0x1c]', None, 'the KIT passive, not the record passive'),
        (0x878232, 'mov r8d, 0xafae3b47', None, 'armor-rating key'),
        (0x87824A, 'jmp 0x11da090', None, 'PassiveValue'),
    ],
}


def text_lookup():
    """Game text by id, from the installed game's strings tables (None when the game data is unavailable)."""
    try:
        import hd2_game_data
        import hd2_text
        data = hd2_game_data.Data()
        tables = [data.read(archive, main) for archive, _, kind, main, *_ in data.tables()
            if kind == hd2_text.STRINGS_TYPE and main[1] >= 16]
        us = hd2_text.language_hash('us')
    except Exception:  # noqa: BLE001 - names are a convenience; every structural proof stands without them
        return lambda value: None

    def text(value):
        try:
            return hd2_text.lookup(tables, value, us) if value else None
        except Exception:  # noqa: BLE001
            return None
    return text


# ---------------------------------------------------------------------------------------------- image tools
class Code:
    def __init__(self, image: base.Image):
        self.image, self.data = image, image.data
        pe = struct.unpack_from('<I', self.data, 60)[0]
        exc, size = struct.unpack_from('<II', self.data, pe + 24 + 112 + 3 * 8)
        self.funcs = sorted(struct.unpack_from('<III', self.data, exc + 12 * i) for i in range(size // 12))
        self.starts = [f[0] for f in self.funcs]
        text = np.frombuffer(self.data[:base.TEXT[1] + 8], dtype=np.uint8).astype(np.int64)
        disp = text[0:-3] | (text[1:-2] << 8) | (text[2:-1] << 16) | (text[3:] << 24)
        self.disp = np.where(disp >= 2 ** 31, disp - 2 ** 32, disp)
        self.index = np.arange(len(self.disp))

    def function_of(self, rva):
        import bisect
        i = bisect.bisect_right(self.starts, rva) - 1
        start, _, unwind = self.funcs[i]
        while True:  # chained unwind info -> primary function
            info = unwind & ~3
            if not (self.data[info] >> 3) & 4:
                return start
            count = self.data[info + 2]
            start, _, unwind = struct.unpack_from('<III', self.data, info + 4 + ((count + 1) & ~1) * 2)

    def calls_to(self, target):
        hits = np.nonzero((self.index + 4 + self.disp) == target)[0]
        return [(int(i) - 1, 'call' if self.data[i - 1] == 0xE8 else 'jmp') for i in hits if self.data[i - 1] in (0xE8, 0xE9)]

    def insns(self, start, end):
        return list(self.image.md.disasm(self.data[start:end], start))

    def setup(self, site):
        """Last writes of ecx/edx/r8d before a call, decoding from the function start."""
        function = self.function_of(site)
        last = {}
        for insn in self.image.md.disasm(self.data[function:site + 5], function):
            if insn.address >= site:
                break
            match = re.match(r'(edx|rdx|r8d|r8|ecx|rcx)\b', insn.op_str)
            if match and insn.mnemonic in ('mov', 'lea', 'xor', 'movzx', 'movsxd'):
                register = {'rdx': 'edx', 'r8': 'r8d', 'rcx': 'ecx'}.get(match.group(1), match.group(1))
                source = insn.op_str.split(', ', 1)[1]
                if insn.mnemonic == 'xor' and source == match.group(1):
                    last[register] = 0
                elif insn.mnemonic == 'mov' and re.fullmatch(r'0x[0-9a-f]+|\d+', source):
                    last[register] = int(source, 0)
                else:
                    last[register] = insn.mnemonic + ' ' + insn.op_str
        return function, last

    def immediate_sites(self, value):
        packed, out, start = struct.pack('<I', value), [], base.TEXT[0]
        while True:
            at = self.data.find(packed, start, base.TEXT[1])
            if at < 0:
                return out
            start = at + 1
            for back in range(1, 8):
                insn = next(self.image.md.disasm(self.data[at - back:at - back + 15], at - back), None)
                if insn and insn.address < at < insn.address + insn.size and '0x%x' % value in insn.op_str:
                    out.append({'rva': insn.address, 'function': self.function_of(insn.address),
                        'asm': insn.mnemonic + ' ' + insn.op_str})
                    break


# ---------------------------------------------------------------------------------------------- snapshots
def hashmap(mem, at):
    slots, capacity, empty, multiplier = struct.unpack('<QIII', mem.read(at, 20))
    raw = mem.read(slots, capacity * 8) if capacity else b''
    pairs = [struct.unpack_from('<II', raw, 8 * i) for i in range(capacity)]
    return [(k, v) for k, v in pairs if k != empty], {'capacity': capacity, 'empty': empty, 'multiplier': multiplier}


def lookup(pairs, key):
    return dict(pairs).get(key)


def read_passive(mem, pointer):
    head = mem.read(pointer, 0x38)
    pid, name, icon, mods, count, stats, stat_count, package = struct.unpack_from('<IIQQqQqI', head, 0)
    raw = mem.read(mods, 16 * count) if count else b''
    modifiers = [struct.unpack_from('<IIfI', raw, 16 * k) for k in range(count)]
    raw = mem.read(stats, 12 * stat_count) if stat_count else b''
    stat_rows = [struct.unpack_from('<Iff', raw, 12 * k) for k in range(stat_count)]
    return {'id': pid, 'name': name, 'icon': icon, 'modifiers': modifiers, 'stats': stat_rows, 'package': package,
        'pointer': pointer}


def entity_attribute(mem, mgr, entity, key, flags):
    """Python replica of EntityAttribute (after the avatar -> player hop): the matching modifier or None."""
    pairs, _ = hashmap(mem, mgr + M_MAP)
    index = lookup(pairs, entity)
    if index is None or index == 0xFFFFFFFF:
        return None
    record = mgr + M_APPLIED + index * APPLIED_STRIDE
    for bit, offset in ((1, 0x3C), (2, 0x38)):
        passive = mem.u32(record + offset)
        if not passive or not flags & bit:
            continue
        slot = struct.unpack('<i', mem.read(mgr + M_PASSIVE_INDEX + 4 * passive, 4))[0]
        pointer = slot >= 0 and mem.ptr(mem.ptr(mgr + M_PASSIVES) + 8 * slot)
        if not pointer:
            continue
        for mod in read_passive(mem, pointer)['modifiers']:
            if mod[0] == key:
                return {'source': 'armor' if bit == 1 else 'helmet', 'passive': passive, 'type': MODIFIER_TYPES.get(mod[1]),
                    'value': round(mod[2], 6)}
    return None


def leads():
    if not LEADS.is_dir():
        return None, None
    data = (LEADS / 'generated_customization_passive_bonuses.dl_bin').read_bytes()
    passives, at = {}, 4
    for _ in range(struct.unpack_from('<I', data, 0)[0]):
        size = struct.unpack_from('<I', data, at + 12)[0]
        at += 24
        pid, name, icon, mo, mc, so, sc, package = struct.unpack_from('<IIQqqqqI', data, at)
        passives[pid] = {'name': name, 'icon': icon, 'package': package,
            'modifiers': [struct.unpack_from('<IIfI', data, at + mo + 16 * k) for k in range(mc)],
            'stats': [struct.unpack_from('<Iff', data, at + so + 12 * k) for k in range(sc)]}
        at += size
    data = (LEADS / 'generated_customization_armor_sets.dl_bin').read_bytes()
    kits, at = {}, 4
    for _ in range(struct.unpack_from('<I', data, 0)[0]):
        size = struct.unpack_from('<I', data, at + 12)[0]
        at += 24
        kits[struct.unpack_from('<I', data, at)[0]] = struct.unpack_from('<IIIIIIIIQI', data, at)
        at += size
    return passives, kits


def same_rows(a, b):
    return [(x[0], x[1], round(x[2], 5), x[3]) for x in a] == [(x[0], x[1], round(x[2], 5), x[3]) for x in b]


def observe(name, keys, lead_passives, lead_kits, text):
    mem = base.Mem(name)
    out = {'snapshot': name}
    mgr = mem.ptr(mem.game + G_CUSTOMIZATION)
    world = mem.ptr(mem.game + base.G_COMPONENT_WORLD)
    out['managerMinusComponentWorld'] = '0x%X' % (mgr - world)
    header = mem.read(mgr, 0x40)
    kit_array, kit_count = struct.unpack_from('<QI', header, M_KITS)
    passive_array, passive_count = struct.unpack_from('<QI', header, M_PASSIVES)
    index = struct.unpack('<%di' % PASSIVE_IDS, mem.read(mgr + M_PASSIVE_INDEX, 4 * PASSIVE_IDS))
    passives = [read_passive(mem, mem.ptr(passive_array + 8 * i)) for i in range(passive_count)]
    out['passiveTable'] = {'count': passive_count, 'idIndexConsistent': all(index[p['id']] == i for i, p in
        enumerate(passives)), 'unusedIds': [i for i in range(PASSIVE_IDS) if index[i] < 0]}
    if lead_passives is not None:
        out['passiveTable']['equalToLead'] = sum(1 for p in passives if p['id'] in lead_passives and
            lead_passives[p['id']]['name'] == p['name'] and lead_passives[p['id']]['icon'] == p['icon'] and
            lead_passives[p['id']]['package'] == p['package'] and
            same_rows(lead_passives[p['id']]['modifiers'], p['modifiers']) and
            [tuple(round(v, 5) for v in s[1:]) + (s[0],) for s in lead_passives[p['id']]['stats']] ==
            [tuple(round(v, 5) for v in s[1:]) + (s[0],) for s in p['stats']])
    kit_pointers = struct.unpack('<%dQ' % kit_count, mem.read(kit_array, 8 * kit_count))
    kits = {}
    for pointer in kit_pointers:
        row = struct.unpack_from('<IIIIIIIIQI', mem.read(pointer, 0x30), 0)
        kits[row[0]] = row
    out['kitTable'] = {'count': kit_count, 'byType': {t: sum(1 for r in kits.values() if r[9] == t) for t in (0, 1, 2)},
        'nonArmorKitsWithPassive': sum(1 for r in kits.values() if r[9] != 0 and r[7])}
    if lead_kits is not None:
        out['kitTable']['equalToLead'] = sum(1 for k, r in kits.items() if lead_kits.get(k) == r)
    # Entity map, records, and the avatar -> player hop EntityAttribute performs.
    pairs, meta = hashmap(mem, mgr + M_MAP)
    out['entityMap'] = meta
    em = mem.ptr(mem.game + G_ENTITY_MANAGER)
    goids, _ = hashmap(mem, em + 0xF22EC8)
    avatar = mem.ptr(mem.game + G_AVATAR)
    avatars, _ = hashmap(mem, avatar + 0xF8)
    hops = []
    for entity, slot in avatars:
        goid = mem.u32(avatar + slot * 0x78 + 0x5478A4)
        resolved = lookup(goids, goid)
        hops.append({'avatarEntity': '0x%X' % entity, 'playerGameObject': goid,
            'playerEntity': None if resolved is None else '0x%X' % mem.u32(em + 0xF32F20 + resolved * 24)})
    out['avatarToPlayer'] = hops
    player = mem.ptr(mem.game + G_PLAYER)
    player_pairs, _ = hashmap(mem, player + 0xD0)
    by_name = {p['id']: p for p in passives}
    players = []
    for entity, record in sorted(pairs, key=lambda kv: kv[1]):
        applied = mem.read(mgr + M_APPLIED + record * APPLIED_STRIDE, APPLIED_STRIDE)
        pending = mem.read(mgr + M_PENDING + record * PENDING_STRIDE, PENDING_STRIDE)
        descriptor = mem.ptr(mgr + M_DESCRIPTORS + 8 * record)
        player_index = lookup(player_pairs, entity)
        u = lambda blob, offset: struct.unpack_from('<I', blob, offset)[0]  # noqa: E731
        kit_name = lambda kit: kit in kits and (text(kits[kit][4]) or text(kits[kit][3]))  # noqa: E731
        row = {'entity': '0x%X' % entity, 'record': record,
            'descriptorEntity': '0x%X' % mem.u32(descriptor + 8) if descriptor else None,
            'playerSlot': None if player_index is None else mem.u32(player + 0x3B4 + player_index * 0x20),
            'applied': {'0x%02X' % o: '0x%08X' % u(applied, o) for o in range(0, APPLIED_STRIDE, 4)},
            'pending': {'0x%02X' % o: '0x%08X' % u(pending, o) for o in range(0, PENDING_STRIDE, 4)},
            'armorKit': {'id': '0x%08X' % u(applied, 0x0C), 'name': kit_name(u(applied, 0x0C)),
                'kitPassive': kits.get(u(applied, 0x0C), [0] * 10)[7]},
            'helmetKit': {'id': '0x%08X' % u(applied, 0x04), 'name': kit_name(u(applied, 0x04))},
            'capeKit': {'id': '0x%08X' % u(applied, 0x08), 'name': kit_name(u(applied, 0x08))},
            'armorPassive': u(applied, 0x3C), 'helmetPassive': u(applied, 0x38)}
        entries = []
        for source, pid in (('armor', row['armorPassive']), ('helmet', row['helmetPassive'])):
            if pid and pid in by_name:
                p = by_name[pid]
                row[source + 'PassiveName'] = text(p['name'])
                for key, kind, value, description in p['modifiers']:
                    entries.append({'source': source, 'passive': pid, 'key': '%08X' % key,
                        'type': MODIFIER_TYPES.get(kind, kind), 'value': round(value, 6), 'text': text(description)})
        row['entries'] = entries
        row['entityAttribute'] = {'%08X' % key: entity_attribute(mem, mgr, entity, key, 3) for key in keys
            if entity_attribute(mem, mgr, entity, key, 3)}
        players.append(row)
    out['players'] = players
    mem.close()
    return out, passives, kits


# ------------------------------------------------------------------------------------------------------- main
def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PINS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    code = Code(image)
    text = text_lookup()
    lead_passives, lead_kits = leads()

    # Reader census: every EntityAttribute call, its key, flags and how the result is consumed.
    census = []
    for site, kind in code.calls_to(F_ENTITY_ATTRIBUTE):
        function, regs = code.setup(site)
        after = [i.mnemonic + ' ' + i.op_str for i in code.insns(site, site + 80)[1:7]]
        uses = ('type' if any('[rax + 4]' in a for a in after) else '') + \
            ('+value' if any('[rax + 8]' in a for a in after) else '')
        census.append({'site': site, 'kind': kind, 'function': function,
            'key': '%08X' % regs['edx'] if isinstance(regs.get('edx'), int) else regs.get('edx'),
            'flags': regs.get('r8d'), 'entity': regs.get('ecx') if not isinstance(regs.get('ecx'), int) else regs['ecx'],
            'reads': uses or 'presence', 'next': after[:4]})
    for row in census:  # the wrapper 0x4CDC60 / 0x4CDC40 takes the key in edx from its callers
        if row['function'] in (0x4CDC40, 0x4CDC60):
            row['key'] = 'from caller'
    wrapper_callers = []
    for wrapper in (0x4CDC60, F_RESIST, 0x87A590, 0x87A810, 0x87AEF0):
        for site, kind in code.calls_to(wrapper):
            function, regs = code.setup(site)
            wrapper_callers.append({'wrapper': wrapper, 'site': site, 'function': function,
                'key': '%08X' % regs['edx'] if wrapper == 0x4CDC60 and isinstance(regs.get('edx'), int) else None})
    passive_value_callers = []
    for site, kind in code.calls_to(F_PASSIVE_VALUE):
        function, regs = code.setup(site)
        passive_value_callers.append({'site': site, 'kind': kind, 'function': function,
            'key': '%08X' % regs['r8d'] if isinstance(regs.get('r8d'), int) else regs.get('r8d'),
            'passiveFrom': regs.get('ecx')})

    observations, passives, kits = [], None, None
    keys = set()
    for name in SNAPSHOTS[:1]:
        _, passives, kits = observe(name, [], lead_passives, lead_kits, text)
    for p in passives:
        keys.update(m[0] for m in p['modifiers'] if m[0])
    keys.update(int(r['key'], 16) for r in census if isinstance(r['key'], str) and re.fullmatch(r'[0-9A-F]{8}', r['key']))
    for name in SNAPSHOTS:
        observation, _, _ = observe(name, sorted(keys), lead_passives, lead_kits, text)
        observations.append(observation)

    # Key catalogue: the game's text bound to each modifier row, the passives carrying it, every reader.
    catalogue = {}
    for p in passives:
        for key, kind, value, description in p['modifiers']:
            if not key:
                continue
            entry = catalogue.setdefault('%08X' % key, {'text': None, 'passives': [], 'entityAttributeSites': [],
                'immediateSites': []})
            entry['text'] = entry['text'] or text(description)
            entry['passives'].append({'id': p['id'], 'name': text(p['name']), 'type': MODIFIER_TYPES.get(kind),
                'value': round(value, 6)})
    for row in census:
        if isinstance(row['key'], str) and re.fullmatch(r'[0-9A-F]{8}', row['key']):
            catalogue.setdefault(row['key'], {'text': None, 'passives': [], 'entityAttributeSites': [],
                'immediateSites': []})['entityAttributeSites'].append('0x%X' % row['site'])
    for key, entry in catalogue.items():
        entry['immediateSites'] = ['0x%X in 0x%X' % (s['rva'], s['function']) for s in code.immediate_sites(int(key, 16))]
    for wrapper in wrapper_callers:
        if wrapper['key']:
            catalogue.setdefault(wrapper['key'], {'text': None, 'passives': [], 'entityAttributeSites': [],
                'immediateSites': []})['entityAttributeSites'].append('0x%X via 0x4CDC60' % wrapper['site'])

    for row in census:
        row['effect'] = catalogue.get(row['key'], {}).get('text') if isinstance(row['key'], str) else None
    passive_table = [{'id': p['id'], 'name': text(p['name']), 'nameId': '%08X' % p['name'], 'icon': '%016X' % p['icon'],
        'package': '%08X' % p['package'], 'modifiers': [{'key': '%08X' % k, 'type': MODIFIER_TYPES.get(t, t),
        'value': round(v, 6), 'text': text(d)} for k, t, v, d in p['modifiers']],
        'stats': [[s[0], round(s[1], 6), round(s[2], 6)] for s in p['stats']],
        'armorKits': sorted(text(r[4]) or text(r[3]) or '%08X' % k for k, r in kits.items() if r[9] == 0 and r[7] == p['id'])}
        for p in sorted(passives, key=lambda q: q['id'])]

    document = {
        'schemaVersion': 1,
        'build': 'F5FEE03DCFDB',
        'generatedBy': 'scripts/research_player_attributes.py',
        'gameDll': base.PROFILE_DLL_SHA,
        'pins': proofs,
        'pinnedBytesMismatchPerSnapshot': relocation,
        'globals': {'customizationManager': G_CUSTOMIZATION, 'avatarManager': G_AVATAR, 'playerManager': G_PLAYER},
        'functions': {
            'EntityAttribute': {'rva': F_ENTITY_ATTRIBUTE, 'signature': 'const Modifier *EntityAttribute(u32 entity, '
                'u32 key, u32 flags)', 'algorithm': [
                'if entity is an avatar (avatar manager map +0xF8): entity = player entity of avatar record +0x5478A4 '
                '(game object id -> entity via 0xFD9BA0); otherwise the entity is used as given',
                'record = customization manager entity map (+0x930) lookup; absent -> NULL',
                'flags bit 0: armor passive = record +0x3C; bit 1: helmet passive = record +0x38 (armor first)',
                'passive id -> manager +0x30 u32[42] -> index into manager +0x20 passive object array',
                'returns the FIRST modifier {u32 key, u32 type, f32 value, u32 text id} whose key matches; '
                'no combination: the caller interprets type and value; absent -> NULL (caller keeps its default)']},
            'PassiveValue': {'rva': F_PASSIVE_VALUE, 'signature': 'float PassiveValue(u32 passiveId, ?, u32 key, '
                'float base)', 'formula': '(last Set value, else base) + sum(Add) then * product(Multiply); Time ignored; '
                'reads a passive by id (callers pass the KIT passive), not the per-player record'},
            'ApplyAttribute': {'rva': F_APPLY_ATTRIBUTE, 'semantics': 'Set: *out = v; Add or Time: *out += v; '
                'Multiply: *out *= v; absent: unchanged', 'staticCallers': len(code.calls_to(F_APPLY_ATTRIBUTE))},
            'updatePlayerCustomization': {'rva': F_UPDATE_PLAYER, 'role': 'pending -> applied per record; when the '
                'new kit package is ready it copies the kit id and sets applied +0x38/+0x3C = kit +0x1C (Passive)'},
            'updateAll': {'rva': F_UPDATE_ALL, 'callers': ['0x%X' % s for s, _ in code.calls_to(F_UPDATE_ALL)],
                'role': 'calls 0x874520 for every record, then collects the 2 passive ids of every player slot '
                '(0x606820 = player slot of an entity) and loads/unloads passive +0x30 packages on change'},
            'setKit': {'armor': F_SET_ARMOR, 'helmet': F_SET_HELMET, 'cape': F_SET_CAPE,
                'callers': {name: sorted({'0x%X' % code.function_of(s) for s, _ in code.calls_to(f)})
                    for name, f in (('armor', F_SET_ARMOR), ('helmet', F_SET_HELMET), ('cape', F_SET_CAPE))}},
        },
        'layouts': {
            'customizationManager': {'0x000': 'HelldiverCustomizationKit *kits[]', '0x008': 'u32 kit count (411)',
                '0x020': 'HelldiverCustomizationPassiveBonusSettings *passives[]', '0x028': 'u32 passive count (32)',
                '0x030': 'i32 passive id -> passives[] index, 42 ids (-1 = unused)',
                '0x8E8': 'u32 record count', '0x8F0': 'inline entity map slots',
                '0x930': 'entity map {slots*, u32 capacity 8, u32 empty 0, u32 multiplier 2}; slot = '
                    '(probe + entity * multiplier) & (capacity - 1), linear probing; value = record index',
                '0x948': 'u64 entity descriptor per record (+8 entity, +0x10 game object id)',
                '0x96C': 'applied records, 0x44 bytes, capacity 4', '0xA7C': 'pending (network) records, 0x40 bytes'},
            'appliedRecord': {'0x%02X' % k: v for k, v in APPLIED.items()},
            'pendingRecord': {'0x04': 'helmet kit id (net field set by 0x875CD0)', '0x08': 'cape kit id (0x875EC0)',
                '0x0C': 'armor kit id (0x8760B0, net field 0xB7D3A2EC)', 'other': 'copied into the applied record '
                '(offsets in appliedRecord); unnamed'},
            'passive': {'0x00': 'u32 id', '0x04': 'u32 name text id', '0x08': 'u64 icon', '0x10': 'Modifier *',
                '0x18': 'i64 modifier count', '0x20': 'stat modifier *', '0x28': 'i64 stat count',
                '0x30': 'u32 package resource (0 = none)'},
            'modifier': {'0x00': 'u32 key (thin hash)', '0x04': 'u32 type 0 Set / 1 Add / 2 Multiply / 3 Time',
                '0x08': 'f32 value', '0x0C': 'u32 text id'},
            'kit': {'0x00': 'u32 id', '0x0C': 'u32 name (upper)', '0x10': 'u32 name (cased)', '0x1C': 'u32 Passive',
                '0x20': 'u64 archive (package)', '0x28': 'u32 type 0 armor / 1 helmet / 2 cape', '0x30': 'bodies',
                '0x38': 'body count'},
        },
        'passiveTable': passive_table,
        'snapshots': observations,
        'readerCensus': census,
        'wrapperCallers': wrapper_callers,
        'passiveValueCallers': passive_value_callers,
        'keys': dict(sorted(catalogue.items())),
        'writers': {
            'appliedPassives': 'only 0x874520 writes applied +0x38/+0x3C (from the kit Passive when the kit changes); '
                'new records are zeroed (0x5405D0, 0x540660, 0x87BD20, 0x87BE00); 0x87B5D0/0x87BE90/0x87C120 move '
                'whole records (compaction). A one-off full .text sweep (not re-run here) found no other stride-0x44 '
                'write to +0x9A4/+0x9A8; the other hits use other objects (e.g. 0x6941B0, stride 0x34).',
            'boosters': 'not in this store: the record holds exactly two passive ids (armor, helmet) and nothing else feeds '
                'EntityAttribute',
            'armorRating': 'AFAE3B47 (armor rating) is read through PassiveValue with the applied ARMOR KIT passive '
                '(0x878160, 0x12A15E0, 0x14E7430, 0x1915EB0), not through the record passive slot',
        },
        'verdicts': {
            'stackingSemantics': 'per key the first match wins (armor slot, then helmet slot when flags bit 1 is set); two '
                'passives sharing a key never combine; inside one passive several rows with one key combine only in '
                'PassiveValue ((Set|base) + sum Add) * prod Multiply)',
            'perPlayerSwap': 'feasible: write applied record +0x3C of that player (ids 0-41 with a table entry); '
                'EntityAttribute reads it on every call; it persists until the armor kit changes (0x874520 rewrites it); '
                '0x874D80 loads the passive package itself. Armor rating does not follow (kit passive).',
            'secondPassive': 'feasible natively: the helmet slot +0x38 is 0 for every vanilla helmet (no helmet kit has a '
                'passive) yet every flags=3 reader consults it; a second passive there adds keys the armor passive '
                'lacks. Flags=1 readers (flinch 73734D67, bleed A68930C2 at 0xC2259, Integrated Explosives 54A69284) '
                'ignore it.',
            'trueStacking': 'needs a Runtime-owned merged passive (private object; never edit a shared vanilla '
                'passive): its modifier list holds the combined values; registering it needs a free id (4, 22-30) and '
                'a passives[] slot (array has no proven spare capacity) - not proven',
        },
        'unproven': [
            'live behaviour of any write (offline only)', 'multiplayer: the applied record is per peer, derived from '
            'replicated pending kits; which peer evaluates each effect is not proven',
            'keys with no direct reader (CC530B21, 33C9C713, 35F17BEC, B4F88129, AD5289FE, 22035F3C, 2559B40D, CD79A687, '
            'F6D67313): data-driven readers (0x7D26BF settings +0xD4, 0x9CABCC locomotion data) are leads',
            'effects of keys no passive carries (9EB4681A, 678DA8D1, 5E3E9018, B85618F2) and of 8933E7F4, 0DFF0E42',
            'which readers run per frame versus once at spawn (stim/grenade capacity)',
            'only one armor (RS-100 Sanctioner, Reduced Signature) is present in the retained snapshots',
        ],
        'writes': [],
    }
    OUTPUT.write_text(json.dumps(document, indent=1, allow_nan=False) + '\n', encoding='utf-8')
    print('wrote', OUTPUT)
    for observation in observations:
        for row in observation['players']:
            print(observation['snapshot'][-46:], row['entity'], row['armorKit']['name'], row.get('armorPassiveName'),
                [(e['key'], e['type'], e['value']) for e in row['entries']])


if __name__ == '__main__':
    main()
