"""Prove the effective upper limit of a live DepositComponent amount. Read-only; nothing writes.

Question: a Maxigun backpack whose DepositComponent definition says capacity = start_amount = 3000 shows 3000
after call-in, then drops to about 1017 after a few rounds, and a resupply only brings it back to about
1024. This script re-derives the cause from the unpacked game.dll and helldivers2.exe images and the
engine's loaded network configuration in the retained snapshots:

1. Deposit state. The DepositComponent manager (game.dll global) keeps the live amount per instance in a
   u32 array (manager+0x50, 8-byte rows). It is initialised from start_amount (capacity when negative).
   Fire consumption subtracts from it; resupply sets min(amount + refill, capacity). No code compares it
   with 1023/1024.
2. Replication. Each write of the amount is followed by a queued game-object field write of the field
   `remaining` with a pointer to that live u32. The queue accepts only game objects this peer owns. The
   flush first calls the engine's field validator with clamp = 1 (net API +0xA0), then the setter (+0xB8).
3. Engine validator (helldivers2.exe). For an int field with `bits` < 32 it accepts
   min <= value <= min + 2^bits - 1 and otherwise clamps the value in place, through the caller's pointer.
   That pointer is the deposit's own live amount, so the owner's local state is clamped too.
4. Network config. In every game-object type carrying `remaining`, that field uses the type
   `deposit_value` = {int, bits 10, min 0}, so the live amount can never exceed 1023. The config is read
   from the engine's loaded network configuration in each retained snapshot.

Every native relationship is pinned as exact instruction bytes at exact RVAs. Names come from the engine's
32-bit IdString hash (upper half of 64-bit Murmur64A), confirmed by several independent matches.
Requires the research-only packages capstone and numpy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

try:
    import capstone
except ImportError as error:  # research dependency only
    raise SystemExit('research_deposit_limits requires capstone: ' + str(error))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_entity_authoring as entity_research
import snapshot_image
import snapshot_regions
from hd2_archive import resource_hash

OUTPUT = ROOT / 'research/deposit-limits-F5FEE03DCFDB.json'
CAPABILITIES = ROOT / 'sdk/BackpackAuthoringCapabilities.json'
PROFILE_DLL_SHA = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
PROFILE_EXE_SHA = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06'
SNAPSHOTS = sorted(snapshot_regions.SNAPSHOT.parent.glob('F5FEE03DCFDB-*.hd2snap'))
EXE = 'helldivers2.exe'
DLL_TEXT = (0x1000, 0x1000 + 0x210FA93)

# game.dll anchors
DEPOSIT_MANAGER = 0x33265E8        # DepositComponent manager pointer
ENGINE_API = 0x3326308             # engine plugin API pointer; +0x40 is the network API table
LINKED_AMMO_MANAGER = 0x3326AA8    # WeaponLinkedAmmoComponent manager pointer
WEAPON_LINKER_MANAGER = 0x33267F8  # WeaponLinkerComponent manager pointer
# helldivers2.exe anchors
NETWORK_CONFIG_SLOT = 0x1A10268    # pointer to the object holding the loaded network config
VALIDATE_FIELD, SET_FIELD, OWNED = 0x34C220, 0x34C3E0, 0x34CF50  # net API +0xA0, +0xB8, +0x168
VALIDATOR = 0x34BAB0

FIELD_REMAINING, FIELD_DRONE = 'remaining', 'drone'
TYPE_DEPOSIT_VALUE, TYPE_GAME_OBJECT_ID = 'deposit_value', 'game_object_id'
# Independent confirmations of the name hash: other network field types whose names resolve too.
NAME_CHECKS = {'bool': (0, 1, 0), 'uint16': (1, 16, 0), 'unsigned': (1, 32, 0)}

# (rva, exact instruction text, role). Every entry is decoded and must match exactly.
DLL_PROOF = {
    'depositManagerIdentity': [
        (0x881D7F, 'lea rdx, [rip + 0x19c9ea2]', '"DepositComponent" name in the manager grow function'),
        (0x88229D, 'lea r8, [rip + 0x19c9954]', '"deposit" pool debug line ({ "max" : %u, "capacity" : 32 })'),
        (0x8822B8, 'mov rbx, qword ptr [rip + 0x2aa4329]', 'the next function (instance removal) uses the manager global'),
    ],
    'definitionGetter': [
        (0x502732, 'mov r11, qword ptr [rip + 0x2e23eaf]', 'instance -> DepositComponent definition record lookup'),
        (0x87F17B, 'mov ecx, dword ptr [rax + 0x80]', 'definition +128 = refill_style'),
    ],
    'createInitialAmount': [
        (0x881478, 'mov rcx, r14', 'instance'),
        (0x88147E, 'call 0x502710', 'definition record'),
        (0x881488, 'mov ecx, dword ptr [rax + 4]', 'start_amount'),
        (0x88148D, 'jns 0x881491', 'negative start_amount ...'),
        (0x88148F, 'mov ecx, dword ptr [rax]', '... falls back to capacity'),
        (0x8814A4, 'mov dword ptr [rdx + rax], ecx', 'live amount (manager+0x50 row) = initial amount'),
        (0x8814AE, 'mov dword ptr [rsi], ecx', 'the creation field value is a separate copy'),
        (0x8814B6, 'mov dword ptr [r15 + rax*8], 0x69889752', 'creation field: remaining'),
        (0x8814C7, 'mov qword ptr [r15 + rax*8 + 8], rsi', 'points at the copy, not at the live amount'),
        (0x8814EF, 'mov dword ptr [r15 + rax*8], 0xa5ae4500', 'creation field: drone'),
        (0x534181, 'mov dword ptr [r12 + rax*8], 0x69889752', 'second creation builder: remaining'),
        (0x5341BA, 'mov dword ptr [r12 + rax*8], 0xa5ae4500', 'second creation builder: drone'),
    ],
    'consume': [
        (0x87FA1B, 'test byte ptr [rcx + 0x14], 1', 'instance owned by this peer?'),
        (0x87FC7B, 'cmp eax, ecx', 'requested amount vs live amount'),
        (0x87FC7D, 'ja 0x87fd41', 'not enough: nothing consumed'),
        (0x87FC83, 'sub ecx, eax', 'amount - consumed'),
        (0x87FC85, 'mov edx, 0x69889752', 'field remaining'),
        (0x87FC8E, 'mov dword ptr [rax + r13*8], ecx', 'live amount written'),
        (0x87FC96, 'lea r8, [rax + r13*8]', 'pointer to the live amount'),
        (0x87FCA2, 'mov ecx, dword ptr [rcx + 0x10]', 'game object id of the instance'),
        (0x87FCA5, 'call 0xfd97e0', 'queue field write'),
        (0x87FD1F, 'mov ecx, 0x86a4e082', 'non-owner: request message to the owner'),
        (0x87FD34, 'call 0xbde430', 'send'),
        (0x87FD3D, 'sub dword ptr [rax + r13*8], r14d', 'non-owner: local prediction'),
    ],
    'resupply': [
        (0x87FDE8, 'call 0x502710', 'definition record'),
        (0x87FDF8, 'mov ebx, dword ptr [rax]', 'capacity'),
        (0x87FDFA, 'mov eax, dword ptr [rax + 8]', 'refill_amount'),
        (0x87FE05, 'mulss xmm0, xmm2', 'refill_amount x caller-supplied scale (xmm2)'),
        (0x87FE09, 'maxss xmm1, xmm0', 'at least 1.0'),
        (0x87FE15, 'addss xmm1, xmm0', '+ live amount'),
        (0x87FE2B, 'cmp eax, ebx', 'vs definition capacity'),
        (0x87FE2D, 'cmovb ebx, eax', 'min(amount + refill, capacity): the only code clamp'),
        (0x87FE30, 'mov dword ptr [rdi + rsi*8], ebx', 'live amount written'),
        (0x87FE26, 'mov edx, 0x69889752', 'field remaining'),
        (0x87FE42, 'lea r8, [rax + rsi*8]', 'pointer to the live amount'),
        (0x87FE5A, 'jmp 0xfd97e0', 'queue field write'),
    ],
    'fieldQueue': [
        (0xFD9817, 'cmp ecx, 0x7fff', 'no game object: skip'),
        (0xFD9833, 'mov rbx, qword ptr [rax + 0x168]', 'net API +0x168: exists and owned by this peer'),
        (0xFD9846, 'call rbx', ''),
        (0xFD984A, 'jle 0xfd98a4', 'not owned: not queued'),
        (0xFD9851, 'mov dword ptr [rsp + 0x20], ebp', 'entry +0 game object id'),
        (0xFD9855, 'mov dword ptr [rsp + 0x24], r15d', 'entry +4 field hash'),
        (0xFD985A, 'mov qword ptr [rsp + 0x28], r14', 'entry +8 value pointer (the live amount)'),
    ],
    'fieldFlush': [
        (0xFDDF00, 'mov byte ptr [rsp + 0x28], 0', 'argument 6: log = 0'),
        (0xFDDF0C, 'mov byte ptr [rsp + 0x20], 1', 'argument 5: clamp = 1'),
        (0xFDDF11, 'mov r9, qword ptr [rbx + 0x10]', 'value pointer'),
        (0xFDDF15, 'mov r10, qword ptr [r8 + 0xa0]', 'net API +0xA0: validate and clamp'),
        (0xFDDF23, 'call r10', ''),
        (0xFDDF3F, 'call qword ptr [r10 + 0xb8]', 'net API +0xB8: set field'),
    ],
    'displayState': [
        (0x87F5EF, 'cmp dword ptr [r8 + r12*8], ecx', 'per-frame: displayed copy (+0x48) vs live amount (+0x50)'),
        (0x87F60C, 'mov dword ptr [rdx + r12*8], ecx', 'displayed copy follows the live amount'),
        (0x88085A, 'mov r10, qword ptr [rip + 0x2aa5d87]', 'amount getter'),
        (0x88086E, 'mov eax, dword ptr [rax + rcx*8]', 'returns the live amount'),
    ],
    'weaponAmmoReadout': [
        (0x772722, 'call 0x880850', 'linked-ammo rounds = live deposit amount'),
        (0x772887, 'mov eax, dword ptr [rax + 4]', 'linked-ammo maximum = start_amount ...'),
        (0x77288C, 'jns 0x7727d3', ''),
        (0x772892, 'mov eax, dword ptr [rcx]', '... or capacity when start_amount is negative'),
        (0x742B49, 'mov rcx, qword ptr [rip + 0x2be3f58]', 'weapon rounds getter, linked-ammo branch'),
        (0x742B52, 'call 0x7725b0', ''),
        (0x742B76, 'mov r9, qword ptr [rip + 0x2be3c7b]', 'WeaponLinkerComponent lookup'),
        (0x742C51, 'inc ebp', '+1 only for a weapon with a valid linked unit'),
        (0x76D26D, 'lea r8, [rip + 0x1adcb8c]', '"weapon_linker" pool debug line'),
        (0x76D288, 'mov rbx, qword ptr [rip + 0x2bb9569]', 'the next function uses the WeaponLinker manager global'),
    ],
}
EXE_PROOF = {
    'validatorIntClamp': [
        (0x34BABE, 'mov rdi, rdx', 'field type descriptor'),
        (0x34BAC7, 'movzx edx, byte ptr [rdx + 0xc]', 'kind (0 bool, 1 int, 2 float, ...)'),
        (0x34BAD4, 'mov rsi, r8', 'value pointer (caller-owned)'),
        (0x34BB65, 'movzx ecx, byte ptr [rdi + 0xd]', 'bits'),
        (0x34BB69, 'cmp ecx, 0x20', '32-bit ints are not range checked'),
        (0x34BB72, 'mov r12d, dword ptr [r8]', 'value'),
        (0x34BB78, 'mov r14d, dword ptr [rdi + 0x10]', 'min'),
        (0x34BB85, 'sub edx, r14d', 'value - min'),
        (0x34BB88, 'shl eax, cl', '1 << bits'),
        (0x34BB8A, 'cmp edx, eax', ''),
        (0x34BB8C, 'jb 0x34c1e6', 'in range: accept'),
        (0x34BB95, 'lea edi, [r14 - 1]', ''),
        (0x34BB99, 'add edi, r8d', 'max = min + 2^bits - 1'),
        (0x34BBBB, 'lea rcx, [rip + 0x132e2be]', '"... value %d as int out of range [%d..%d]." (only when log = 1)'),
        (0x34BBD6, 'cmp byte ptr [rsp + 0xd8], bpl', 'clamp flag (argument 6)'),
        (0x34BBE6, 'cmp eax, edi', ''),
        (0x34BBE8, 'jg 0x34bbf3', 'above max: max'),
        (0x34BBEF, 'cmovl edi, r14d', 'below min: min'),
        (0x34BBF3, 'mov dword ptr [rsi], edi', 'clamped value written back through the caller pointer'),
    ],
    'validateByName': [
        (0x34C27E, 'lea r9, [rcx + rcx*4]', 'game object type row (stride 0x50) ...'),
        (0x34C286, 'add r9, qword ptr [rbp + 0x78]', '... in config +0x78'),
        (0x34C28A, 'mov r8d, dword ptr [r9 + 0x18]', 'field count'),
        (0x34C293, 'mov rdx, qword ptr [r9 + 0x38]', 'field name hashes'),
        (0x34C297, 'cmp dword ptr [rdx + rax*4], esi', 'find the field by name'),
        (0x34C2A8, 'mov rcx, qword ptr [r9 + 0x20]', 'field type indices'),
        (0x34C2B4, 'mov rcx, qword ptr [rbp + 0x18]', 'field types (config +0x18) ...'),
        (0x34C2BC, 'lea rdx, [rcx + r8*8]', '... stride 0x18'),
        (0x34C2C0, 'movzx ecx, byte ptr [rsp + 0x88]', 'log flag passed through'),
        (0x34C2CC, 'mov r8, r14', 'caller value pointer passed through'),
        (0x34C2CF, 'movzx ecx, byte ptr [rsp + 0x80]', 'clamp flag passed through'),
        (0x34C2E2, 'call 0x34bab0', ''),
    ],
    'networkConfigAnchor': [
        (0x34C4C5, 'mov rax, qword ptr [rip + 0x16c3d9c]', 'network config holder'),
        (0x34C4D2, 'mov rcx, qword ptr [rax]', 'config'),
        (0x34C4D5, 'mov r8d, dword ptr [rcx + 0x70]', 'game object type count'),
        (0x34C4D9, 'mov rbx, qword ptr [rcx + 0x78]', 'game object types'),
        (0x34CFA7, 'mov qword ptr [rip + 0x16c32ba], rax', 'holder set at network startup'),
    ],
    'ownedCheck': [
        (0x34CF62, 'call qword ptr [rax + 0xf8]', 'exists'),
        (0x34CF81, 'call qword ptr [rax + 0x170]', 'owned'),
        (0x3DC981, 'lea rdx, [rip + 0x12a37a8]', 'Lua name "game_object_owned" ...'),
        (0x3DC991, 'lea rdx, [rip + 0x6d8]', '... bound to 0x3dd070 ...'),
        (0x3DD0A1, 'call qword ptr [r8 + 0x170]', '... which calls the same +0x170 slot'),
    ],
}
STRINGS = {'dll': {0x224BC28: 'DepositComponent', 0x224BBF8: '"deposit" : { "max" : %u, "capacity" : 32 }',
        0x2249EA8: '"weapon_linked_ammo" : { "max" : %u, "capacity" : 384 }',
        0x2249E00: '"weapon_linker" : { "max" : %u, "capacity" : 256 }'},
    'exe': {0x1679E80: 'Game object `%s`, field index %d, value %d as int out of range [%d..%d].',
        0x1680130: 'game_object_owned'}}


def h32(name: str) -> int:
    """Engine IdString32: upper half of Murmur64A (the resource hash)."""
    return resource_hash(name) >> 32


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class Image:
    def __init__(self, data: bytes):
        self.data = data
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def insn(self, rva):
        found = next(self.md.disasm(self.data[rva:rva + 16], rva), None)
        if found is None:
            raise ValueError('undecodable instruction at %x' % rva)
        return found

    def cstr(self, rva):
        return self.data[rva:self.data.index(b'\0', rva)].decode('latin-1')

    def target(self, insn):
        text = insn.op_str
        if '[rip + ' in text:
            return insn.address + insn.size + int(text.split('[rip + ')[1].split(']')[0], 16)
        return None

    def prove(self, groups, strings):
        out = {}
        for group, rows in groups.items():
            proven = []
            for rva, text, role in rows:
                insn = self.insn(rva)
                asm = insn.mnemonic + ' ' + insn.op_str
                if asm != text:
                    raise ValueError('%s %x is %r, expected %r' % (group, rva, asm, text))
                row = {'rva': rva, 'bytes': self.data[rva:rva + insn.size].hex(), 'asm': asm, 'role': role}
                target = self.target(insn)
                if target is not None:
                    row['ripTarget'] = target
                    if target in strings:
                        if self.cstr(target) != strings[target]:
                            raise ValueError('string at %x changed' % target)
                        row['string'] = strings[target]
                proven.append(row)
            out[group] = proven
        return out


def check_targets(proof):
    """Pinned globals the proof depends on."""
    expect = {('depositManagerIdentity', 0x8822B8): DEPOSIT_MANAGER, ('definitionGetter', 0x502732): DEPOSIT_MANAGER,
        ('displayState', 0x88085A): DEPOSIT_MANAGER, ('weaponAmmoReadout', 0x742B49): LINKED_AMMO_MANAGER,
        ('weaponAmmoReadout', 0x742B76): WEAPON_LINKER_MANAGER, ('weaponAmmoReadout', 0x76D288): WEAPON_LINKER_MANAGER,
        ('networkConfigAnchor', 0x34C4C5): NETWORK_CONFIG_SLOT, ('networkConfigAnchor', 0x34CFA7): NETWORK_CONFIG_SLOT,
        ('ownedCheck', 0x3DC991): 0x3DD070}
    rows = {(group, row['rva']): row for group, items in proof.items() for row in items}
    for key, value in expect.items():
        if key in rows and rows[key].get('ripTarget') != value:
            raise ValueError('%s %x no longer targets %x' % (key[0], key[1], value))


def field_immediates(data):
    """Every .text occurrence of the two deposit field hashes (as imm32 bytes)."""
    found = {}
    for name in (FIELD_REMAINING, FIELD_DRONE):
        needle, at, hits = struct.pack('<I', h32(name)), DLL_TEXT[0], []
        while True:
            at = data.find(needle, at, DLL_TEXT[1])
            if at < 0:
                break
            hits.append(at)
            at += 1
        found[name] = hits
    return found


class Memory:
    def __init__(self, path: Path):
        self.snap = snapshot_image.Snapshot(path)
        self.game = self.snap.modules['game.dll']['base']
        self.exe = self.snap.modules[EXE]['base']

    def read(self, address, size):
        region = self.snap.region(address)
        if region is None or region['status'] != 1 or address + size > region['base'] + region['size']:
            raise ValueError('address %x not captured' % address)
        self.snap.handle.seek(region['data_offset'] + address - region['base'])
        return self.snap.handle.read(size)

    def u32(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def ptr(self, address):
        return struct.unpack('<Q', self.read(address, 8))[0]


def network_config(path: Path) -> dict:
    """The engine's loaded network config: API slots, the remaining/drone field types in every object type."""
    memory = Memory(path)
    api = memory.ptr(memory.game + ENGINE_API)
    net = memory.ptr(api + 0x40)
    slots = {hex(offset): memory.ptr(net + offset) - memory.exe for offset in (0xA0, 0xB8, 0x168)}
    if slots != {'0xa0': VALIDATE_FIELD, '0xb8': SET_FIELD, '0x168': OWNED}:
        raise ValueError('network API slots changed: %s' % slots)
    config = memory.ptr(memory.ptr(memory.exe + NETWORK_CONFIG_SLOT))
    type_count, types = memory.u32(config + 0x10), memory.ptr(config + 0x18)
    object_count, objects = memory.u32(config + 0x70), memory.ptr(config + 0x78)

    def field_type(index):
        raw = memory.read(types + index * 0x18, 0x18)
        return {'index': index, 'nameHash': struct.unpack_from('<I', raw, 0)[0], 'kind': raw[12], 'bits': raw[13],
            'min': struct.unpack_from('<i', raw, 16)[0], 'bytes': raw.hex()}

    remaining, drone = h32(FIELD_REMAINING), h32(FIELD_DRONE)
    carriers, used = [], {}
    names_by_hash = {h32(name): name for name in (TYPE_DEPOSIT_VALUE, TYPE_GAME_OBJECT_ID, *NAME_CHECKS)}
    table = memory.read(objects, object_count * 0x50)
    for index in range(object_count):
        row = table[index * 0x50:(index + 1) * 0x50]
        count = struct.unpack_from('<I', row, 0x18)[0]
        if not count:
            continue
        hashes = struct.unpack('<%dI' % count, memory.read(struct.unpack_from('<Q', row, 0x38)[0], count * 4))
        if remaining not in hashes:
            continue
        kinds = struct.unpack('<%dI' % count, memory.read(struct.unpack_from('<Q', row, 0x20)[0], count * 4))
        at = hashes.index(remaining)
        carrier = {'objectType': index, 'nameHash': '0x%08X' % struct.unpack_from('<I', row, 0)[0],
            'fieldCount': count, 'remainingIndex': at, 'remainingType': kinds[at]}
        if drone in hashes:
            carrier['droneType'] = kinds[hashes.index(drone)]
        carriers.append(carrier)
        for key in ('remainingType', 'droneType'):
            if key in carrier and carrier[key] not in used:
                described = field_type(carrier[key])
                described['name'] = names_by_hash.get(described['nameHash'])
                used[carrier[key]] = described
    checks = {}
    for index in range(type_count):
        described = field_type(index)
        name = names_by_hash.get(described['nameHash'])
        if name in NAME_CHECKS:
            checks.setdefault(name, []).append([described['kind'], described['bits'], described['min']])
    memory.snap.close()
    return {'snapshot': path.name, 'networkApiSlots': slots, 'fieldTypeCount': type_count,
        'objectTypeCount': object_count, 'remainingCarriers': carriers,
        'fieldTypes': {str(k): v for k, v in sorted(used.items())}, 'nameHashChecks': checks}


def deposit_definitions(native):
    members = native.typelib_module.layout(native.typelib, 'DepositComponent', structured=True)['members']
    layout = [{'offset': m['offset64'], 'storage': m['storage'], 'size': m['size64'],
        'nameLength': int(str(m['name']).rsplit('=', 1)[1])} for m in members]
    records = []
    for record, owners in sorted(native.owners('DepositComponentData').items()):
        raw = native.record('DepositComponentData', record)
        capacity, start, refill = struct.unpack_from('<IiI', raw, 0)
        records.append({'record': record, 'owners': [native.path(o) or '0x%016X' % o for o in owners],
            'capacity': capacity, 'startAmount': start, 'refillAmount': refill,
            'refillStyle': struct.unpack_from('<I', raw, 128)[0]})
    return layout, records


def exposed_fields(limit):
    data = json.loads(CAPABILITIES.read_text(encoding='utf-8'))
    out = []
    for item in data['fieldInstances']:
        if item.get('domain') != 'deposit' and not str(item.get('semanticFieldId', '')).startswith('deposit.'):
            continue
        maximum = item.get('max')
        out.append({'instanceKey': item['instanceKey'], 'field': item['semanticFieldId'],
            'backpack': item['target'].get('backpack'), 'default': item.get('currentDefault'),
            'editable': item.get('editable'), 'sdkMin': item.get('min'), 'sdkMax': maximum,
            'effectiveLiveMax': limit, 'sdkMaxExceedsLiveLimit': maximum is not None and maximum > limit})
    return out


def main():
    base = snapshot_image.Snapshot(snapshot_regions.SNAPSHOT)
    if base.game_dll_sha256 != PROFILE_DLL_SHA or base.executable_sha256 != PROFILE_EXE_SHA:
        raise ValueError('snapshot module fingerprints differ from the pinned profile')
    _, dll = base.module_image('game.dll')
    _, exe = base.module_image(EXE)
    base.close()
    dll_image, exe_image = Image(dll), Image(exe)
    dll_proof = dll_image.prove(DLL_PROOF, STRINGS['dll'])
    exe_proof = exe_image.prove(EXE_PROOF, STRINGS['exe'])
    check_targets({**dll_proof, **exe_proof})

    immediates = field_immediates(dll)
    known = {FIELD_REMAINING: {0x534185, 0x87FC86, 0x87FE27, 0x8814BA}, FIELD_DRONE: {0x29DBFB, 0x5341BE, 0x87F473, 0x8814F3}}
    if {k: set(v) for k, v in immediates.items()} != known:
        raise ValueError('field hash immediates changed: %s' % immediates)
    if any(struct.pack('<I', h32(n)) in exe for n in (FIELD_REMAINING, FIELD_DRONE)):
        raise ValueError('the engine references a deposit field hash directly')

    configs = [network_config(path) for path in SNAPSHOTS]
    limits = set()
    for config in configs:
        for carrier in config['remainingCarriers']:
            described = config['fieldTypes'][str(carrier['remainingType'])]
            if described['name'] != TYPE_DEPOSIT_VALUE or described['kind'] != 1:
                raise ValueError('remaining is not a deposit_value int in %s' % config['snapshot'])
            limits.add(described['min'] + (1 << described['bits']) - 1)
        for name, expected in NAME_CHECKS.items():
            if list(expected) not in config['nameHashChecks'].get(name, []):
                raise ValueError('name hash check %s failed' % name)
    if len(limits) != 1:
        raise ValueError('remaining has more than one range: %s' % limits)
    limit = limits.pop()

    native = entity_research.Native()
    layout, records = deposit_definitions(native)
    first = configs[0]
    deposit_value = next(v for v in first['fieldTypes'].values() if v['name'] == TYPE_DEPOSIT_VALUE)
    report = {'schemaVersion': 1, 'sourceSnapshot': snapshot_regions.SNAPSHOT.name,
        'modules': {'gameDll': {'sha256': PROFILE_DLL_SHA, 'unpackedImageSha256': sha(dll)},
            'executable': {'sha256': PROFILE_EXE_SHA, 'unpackedImageSha256': sha(exe)}},
        'names': {'hash': 'IdString32 = Murmur64A(name) >> 32',
            'fields': {FIELD_REMAINING: '0x%08X' % h32(FIELD_REMAINING), FIELD_DRONE: '0x%08X' % h32(FIELD_DRONE)},
            'types': {TYPE_DEPOSIT_VALUE: '0x%08X' % h32(TYPE_DEPOSIT_VALUE),
                TYPE_GAME_OBJECT_ID: '0x%08X' % h32(TYPE_GAME_OBJECT_ID)},
            'independentChecks': {name: {'hash': '0x%08X' % h32(name), 'kindBitsMin': list(v)}
                for name, v in NAME_CHECKS.items()}},
        'liveAmountLimit': {'max': limit, 'min': deposit_value['min'], 'bits': deposit_value['bits'],
            'fieldType': TYPE_DEPOSIT_VALUE, 'field': FIELD_REMAINING,
            'classification': 'network schema (engine network_config field type), enforced by the engine on the '
                'owning peer, in place on its live state; not a game.dll constant and not a DepositComponent member',
            'writableControl': None},
        'gameDll': {'depositManager': DEPOSIT_MANAGER, 'engineApi': ENGINE_API,
            'linkedAmmoManager': LINKED_AMMO_MANAGER, 'weaponLinkerManager': WEAPON_LINKER_MANAGER,
            'liveState': {'array': 'manager+0x50', 'stride': 8, '+0': 'live amount (u32)',
                '+4': 'drone game object id (network field drone)'},
            'displayState': {'array': 'manager+0x48', 'stride': 8, '+0': 'copy of the live amount',
                '+4': 'refill_style'},
            'fieldHashImmediates': {k: sorted(v) for k, v in immediates.items()},
            'proof': dll_proof},
        'executable': {'networkConfigSlot': NETWORK_CONFIG_SLOT,
            'networkApi': {'0xA0': VALIDATE_FIELD, '0xB8': SET_FIELD, '0x168': OWNED}, 'validator': VALIDATOR,
            'proof': exe_proof},
        'networkConfig': configs,
        'typeLibrary': {'DepositComponent': layout, 'note': 'No member other than capacity bounds the amount.'},
        'depositDefinitions': records,
        'exposedDepositFields': exposed_fields(limit),
        'model': [
            'live amount (u32, manager+0x50) starts at start_amount, or capacity when start_amount < 0',
            'the creation message carries a clamped copy; the owner keeps the unclamped value until its next write',
            'consume: amount -= n (owner); a non-owner asks the owner and predicts locally',
            'resupply: amount = min(amount + max(1, refill_amount * scale), capacity)',
            'every owner write queues (game object, remaining, &amount); only owned objects are queued',
            'flush: engine validate(clamp=1) writes min(amount, 1023) back into the live amount, then sets the field',
            'remaining is deposit_value = int, 10 bits, min 0 in every object type that carries it',
            'the weapon readout shows the live amount over start_amount (capacity when start_amount < 0)'],
        'writes': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', newline='\n')
    print(json.dumps({'limit': limit, 'deposit_value': deposit_value,
        'carriers': [len(c['remainingCarriers']) for c in configs], 'snapshots': [c['snapshot'] for c in configs],
        'exceeding': sorted({f['backpack'] for f in report['exposedDepositFields'] if f['sdkMaxExceedsLiveLimit']})},
        indent=1))


if __name__ == '__main__':
    main()
