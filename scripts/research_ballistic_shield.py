"""Why SH-20 Ballistic Shield `entity.armor` = 5 did not stop the MG-206 HMG (AP 4). Read-only; nothing writes.

Re-derives, from the pinned datalibrary, the retained snapshot's unpacked game.dll image and that snapshot's
heap state:

* Identity: StratagemDefinition -> weapon_rack_ballistic_shield -> RackAttach.Item -> ballistic_shield_backpack,
  its complete component set, and the HealthComponent record Runtime binds (`entity.armor` = record +280).
* The HealthComponent anatomy: default zone (+64) and every populated DamageableZone (38 x 552 from +520), with
  armor, angle check, max armor, ignore-armor-on-self, durable share, damage multiplier, explosion routing and the
  zone actor list (+456, 24 thin hashes).
* The native damage path, pinned as exact decoded instructions at exact RVAs:
    - zone resolution by hit actor (default zone only when no zone lists the actor),
    - per-instance armor copied from the definition when a health instance is created,
    - the hit builder replacing the definition armor with that instance copy,
    - the armor-vs-AP damage factor (AP - armor >= 1 -> 1.0, 0 <= AP - armor < 1 -> 0.65, else 0),
    - the angle-selected AP, the avatar-only armor curve, and entity-delta override copies.
* Snapshot heap evidence: angle thresholds, avatar-manager occupants, override-copy count.
* A damage model for the HMG and comparison weapons against the shield plate, and the live-test design.

Requires the research-only packages capstone and numpy.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

try:
    import capstone
    import numpy
except ImportError as error:  # research dependency only
    raise SystemExit('research_ballistic_shield requires capstone and numpy: ' + str(error))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import snapshot_image  # noqa: E402
from migration import build_view  # noqa: E402

HELPERS = ROOT.parent / 'StrongerOrbitalLaser/scripts/research'
OUTPUT = ROOT / 'research/ballistic-shield-F5FEE03DCFDB.json'
ENTITY_RESEARCH = ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json'
SUPPORT_RESEARCH = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
ENTITY_DOMAIN = ROOT / 'domains/entity_authoring.lua'
PROFILE_DLL_SHA = build_profile.ACTIVE['gameDllSha256']

SH20 = 'SH-20 Ballistic Shield Backpack'
SH20_PATH = 'content/fac_helldivers/equipment/backpacks/ballistic_shield_backpack/ballistic_shield_backpack'
RELATED = {
    'SH-20 rack': 'content/fac_helldivers/hellpod/weapon_rack/weapon_rack_ballistic_shield',
    'SH-20 small rack': 'content/fac_helldivers/hellpod/weapon_rack/weapon_rack_ballistic_shield_small',
    'SH-20 mk2 variant': 'content/fac_helldivers/equipment/backpacks/ballistic_shield_backpack_mk2/'
        'ballistic_shield_backpack_mk2',
    'SH-20 small variant': 'content/fac_helldivers/equipment/backpacks/ballistic_shield_backpack_small/'
        'ballistic_shield_backpack_small',
    'SH-51 backpack': 'content/fac_helldivers/equipment/backpacks/directional_energy_shield/'
        'directional_energy_shield_backpack',
    'SH-51 deployed barrier': 'content/fac_helldivers/equipment/backpacks/directional_energy_shield/'
        'directional_energy_shield',
    'SH-51 rack': 'content/fac_helldivers/hellpod/weapon_rack/weapon_rack_directional_energy_shield',
    'Exosuit shield': 'content/fac_helldivers/vehicles/combat_walker_shield/combat_walker_shield',
    'Automaton soldier shield': 'content/fac_cyborgs/equipment/weapons/soldier_shield/soldier_shield',
    'Helldiver avatar': 'content/fac_helldivers/cha_avatar/avatar_helldiver',
}

RECORD_SIZE, ZONES, ZONE_BASE, ZONE_STRIDE, DEFAULT_ZONE, ZONE_INFO = 22096, 38, 520, 552, 64, 456
# DamageableZoneInfo members read here: offset -> (storage, hidden-name length, filediver name).
ZONE_MEMBERS = {
    96: ('UINT32', 9, 'zone_name'),
    196: ('ENUM_INT32', 17, 'damage_multiplier'),
    200: ('ENUM_INT32', 21, 'damage_multiplier_dps'),
    204: ('FP32', 29, 'projectile_durable_resistance'),
    216: ('UINT32', 5, 'armor'),
    220: ('UINT8', 17, 'armor_angle_check'),
    224: ('UINT32', 9, 'max_armor'),
    228: ('UINT8', 20, 'ignore_armor_on_self'),
    232: ('INT32', 6, 'health'),
    248: ('FP32', 19, 'affects_main_health'),
    323: ('UINT8', 22, 'affected_by_explosions'),
    324: ('FP32', 27, 'explosive_damage_percentage'),
}
DAMAGE_MULTIPLIER = ['None', 'Critical', 'Normal', 'Reduced', 'Symbolic']
FLT_MAX = 3.4028234663852886e+38

# Pinned instructions: (rva, exact capstone text, RIP target or None, role).
PINS = {
    'zoneResolver_0x922060': [
        (0x922067, 'lea r9, [rdx + 0x268]', None, 'zone[0].zone_name (+0x208 + 0x60) of the HealthComponent record'),
        (0x92207d, 'lea rcx, [r9 + 0x168]', None, 'zone actor list (+0x1c8 = +456 of the zone)'),
        (0x92208a, 'cmp eax, r11d', None, 'actor thin hash == hit actor'),
        (0x922096, 'cmp r8d, 0x18', None, '24 actors per zone'),
        (0x9220a1, 'add r9, 0x228', None, 'next zone (552-byte stride)'),
        (0x9220a8, 'cmp r10, 0x26', None, '38 zones'),
        (0x9220ae, 'lea rax, [rdx + 0x40]', None, 'no zone lists the actor -> default zone (+64)'),
        (0x9220c0, 'imul rcx, rax, 0x228', None, 'matched zone index * 552'),
        (0x9220c7, 'lea rax, [rdx + 0x208]', None, 'matched zone = +520 + index * 552'),
    ],
    'hitBuilder_0x12a15e0': [
        (0x12a1d96, 'call 0x507430', None, 'definition record by resource hash'),
        (0x12a1e61, 'call 0x922060', None, 'resolve zone for the hit actor'),
        (0x12a1e71, 'mov ecx, dword ptr [rax + 0x60]', None, 'zone_name -> event+0x7c'),
        (0x12a1e78, 'mov ecx, dword ptr [rax + 0xcc]', None, 'projectile_durable_resistance -> event+0x4c (per hit)'),
        (0x12a1e82, 'mov ecx, dword ptr [rax + 0xd8]', None, 'definition armor -> event+0x50 (provisional)'),
        (0x12a1e96, 'mov ecx, dword ptr [rax + 0xe0]', None, 'max_armor -> event+0x54'),
        (0x12a1f3a, 'mov edi, dword ptr [r12 + 0x60]', None, 'resolved zone name'),
        (0x12a2316, 'call 0x507920', None, 'settings record of the live health instance'),
        (0x12a231b, 'imul r8, rbx, 0x1b8', None, 'health instance index * 0x1b8'),
        (0x12a2325, 'add r8, qword ptr [r13 + 0x1058]', None, 'health manager instance array'),
        (0x12a232c, 'cmp edi, dword ptr [rax + 0xa0]', None, 'resolved zone is the default zone (+64 + 0x60)?'),
        (0x12a2334, 'mov eax, dword ptr [r8 + 0x5c]', None, 'default zone -> INSTANCE armor +0x5c'),
        (0x12a2340, 'add rcx, 0x268', None, 'walk zone names'),
        (0x12a2353, 'add rcx, 0x228', None, 'zone stride'),
        (0x12a235a, 'cmp eax, 0x26', None, '38 zones'),
        (0x12a2368, 'mov eax, dword ptr [r8 + rax*4 + 0x60]', None, 'zone i -> INSTANCE armor +0x60 + 4*i'),
        (0x12a1fa3, 'movss dword ptr [r14 + 0x50], xmm0', None, 'event+0x50 = float(instance armor)'),
        (0x12a228d, 'movzx eax, byte ptr [r12 + 0xdc]', None, 'armor_angle_check -> event+0x72'),
        (0x12a229a, 'movzx eax, byte ptr [r12 + 0xe4]', None, 'ignore_armor_on_self -> event+0x73 (per hit)'),
        (0x12a22a7, 'mov ecx, dword ptr [r12 + 0xc4]', None, 'damage_multiplier -> event+0x6c (per hit)'),
    ],
    'projectileEvent_0x12a25b0': [
        (0x12a2669, 'call 0x12a15e0', None, 'build hit event'),
        (0x12a2691, 'subss xmm3, xmm4', None, '1 - durable share'),
        (0x12a26d1, 'addss xmm1, dword ptr [rbx + 0x98]', None, '(1-d)*standard + d*durable'),
        (0x12a26d9, 'movss dword ptr [rbx + 0x98], xmm1', None, 'event+0x98 = durable-weighted damage'),
    ],
    'instanceCreate_0x91d580': [
        (0x91d61c, 'call 0x507920', None, 'definition (or entity-delta copy) of the new instance'),
        (0x91d626, 'imul r13, rcx, 0x1b8', None, 'instance index * 0x1b8'),
        (0x91d637, 'add r13, qword ptr [rdi + 0x1058]', None, 'health manager instance array'),
        (0x91d740, 'mov eax, dword ptr [rsi + 0x118]', None, 'definition default-zone armor (+280 = entity.armor)'),
        (0x91d74d, 'mov dword ptr [r13 + 0x5c], eax', None, '-> instance +0x5c'),
        (0x91d746, 'lea rbx, [rsi + 0x2e0]', None, 'definition zone[0].armor (+736)'),
        (0x91d751, 'lea rdi, [r13 + 0xf8]', None, 'instance zone arrays'),
        (0x91d75a, 'mov r12d, 0x26', None, '38 zones'),
        (0x91d770, 'mov eax, dword ptr [rbx]', None, 'zone[i].armor'),
        (0x91d772, 'mov dword ptr [rdi - 0x98], eax', None, '-> instance +0x60 + 4*i'),
        (0x91d7fd, 'add rdi, 4', None, 'next instance slot'),
        (0x91d801, 'add rbx, 0x228', None, 'next definition zone'),
        (0x91d808, 'sub r12, 1', None, 'loop'),
    ],
    'instanceCreateRegistration': [
        (0x53de33, 'jmp 0x91d580', None, 'component create thunk'),
        (0x55b994, 'lea rax, [rip - 0x1db6b]', 0x53de30, 'thunk address'),
        (0x55b99b, 'mov qword ptr [rcx + 0xf0dc50], rax', None, 'registered in the component create-callback table'),
    ],
    'definitionLookup_0x507430_0x507920': [
        (0x50743f, 'mov r10, qword ptr [rax + 0xf12b78]', None, 'loaded HealthComponentData table'),
        (0x507463, 'imul eax, eax, 0x3ea', None, '1002 index rows'),
        (0x5074b1, 'imul rax, rcx, 0x5650', None, 'record index * 22096'),
        (0x5074b8, 'add rax, 0x3ea0', None, 'records follow 1002 x 16-byte index rows'),
        (0x50797a, 'mov rdi, qword ptr [r11 + 0x1070]', None, 'per-instance override hash'),
        (0x5079d2, 'imul rax, rax, 0x5650', None, 'override record'),
        (0x5079d9, 'add rax, qword ptr [r11 + 0x10b0]', None, 'override array'),
        (0x5079ec, 'jmp 0x507430', None, 'no override -> definition'),
        (0x929b2d, 'call 0x507430', None, 'override creation copies the definition'),
        (0x929b57, 'call 0x20988f0', None, 'memcpy 0x5650'),
        (0x929b69, 'call 0x515540', None, 'then applies an entity delta'),
        (0x50753e, 'cmp dword ptr [rax + rcx*4], 0xe0', None, 'delta component type 0xE0 = HealthComponentData'),
    ],
    'damageFactor_0x129c9f0': [
        (0x129ca3e, 'call 0x129c7c0', None, 'angle-selected AP'),
        (0x129ca54, 'movss xmm9, dword ptr [rbx + 0x50]', None, 'armor (instance copy)'),
        (0x129ca5a, 'movss xmm7, dword ptr [rip + 0x112a30e]', 0x23C6D70, '1.0'),
        (0x129ca64, 'mov rcx, qword ptr [rip + 0x208a2b5]', 0x3326D20, 'avatar manager'),
        (0x129cadf, 'call 0x129c940', None, 'avatar only: armor-level curve'),
        (0x129cabc, 'subss xmm0, xmm9', None, 'AP - armor'),
        (0x129cac5, 'comiss xmm0, xmm7', None, '>= 1'),
        (0x129caca, 'movaps xmm6, xmm7', None, '-> factor 1.0'),
        (0x129cafa, 'comiss xmm0, xmm8', None, '>= 0'),
        (0x129cb00, 'movss xmm6, dword ptr [rip + 0x112a074]', 0x23C6B7C, '-> factor 0.65; otherwise 0'),
        (0x129cb55, 'cmp byte ptr [rbx + 0x73], 0', None, 'ignore_armor_on_self'),
        (0x129cb5b, 'movaps xmm6, xmm7', None, '-> factor 1.0'),
        (0x129cb66, 'mulss xmm1, xmm11', None, 'factor * damage * event+0x94'),
        (0x129cb77, 'call 0x2108e78', None, 'floor'),
        (0x129cb9a, 'mulss xmm1, dword ptr [rcx + rax*4]', None, 'damage multiplier table [0, 1.5, 1, 0.75, 0.25]'),
    ],
    'explosionFactor_0x129d180': [
        (0x129d228, 'subss xmm0, dword ptr [rdi + 0x50]', None, 'AP - armor (same rule)'),
        (0x129d26d, 'movss xmm6, dword ptr [rip + 0x1129907]', 0x23C6B7C, '0.65'),
        (0x129d275, 'cmp byte ptr [rdi + 0x73], sil', None, 'ignore_armor_on_self'),
        (0x129d346, 'call 0x921a80', None, 'zone index by name'),
        (0x129d36c, 'cmp byte ptr [rax + 0x143], sil', None, 'affected_by_explosions'),
        (0x129d37b, 'cmovne rdx, rax', None, 'zone explosive % if set, else the default zone'),
    ],
    'apByAngle_0x129c7c0': [
        (0x129c7ce, 'mulss xmm0, dword ptr [rdx + 0x88]', None, 'impact direction . surface normal'),
        (0x129c831, 'mulss xmm1, dword ptr [rip + 0x112aef7]', 0x23C7730, 'radians -> degrees'),
        (0x129c83d, 'test eax, eax', None, 'event type 0 = projectile'),
        (0x129c8ac, 'mov rcx, qword ptr [rip + 0x21d097d]', 0x346D230, 'projectile angle thresholds'),
        (0x129c87a, 'mov rcx, qword ptr [rip + 0x21d09b7]', 0x346D238, 'DPS angle thresholds'),
        (0x129c8de, 'movss xmm0, dword ptr [rbx + rax*4 + 0x9c]', None, 'AP[direct, slight, large, extreme]'),
    ],
}
CONSTANTS = {0x23C6D70: 1.0, 0x23C6B7C: 0.65, 0x23C7730: 57.2957763671875}
DAMAGE_MULTIPLIER_TABLE = 0x21CF898
AVATAR_CURVE = 0x21CEFF0
DAMAGE_GROUP_TYPE = 0xE0A72CF0
COMPARISON_WEAPONS = ('MG-206 Heavy Machine Gun', 'APW-1 Anti-Materiel Rifle', 'MG-43 Machine Gun',
    'RS-422 Railgun', 'LAS-99 Quasar Cannon')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def hexid(value: int) -> str:
    return f'0x{value:016X}'


def u32(raw, at): return struct.unpack_from('<I', raw, at)[0]
def i32(raw, at): return struct.unpack_from('<i', raw, at)[0]
def f32(raw, at): return struct.unpack_from('<f', raw, at)[0]


class Names:
    def __init__(self):
        sys.path.insert(0, str(HELPERS))
        from probe_components import resource_hash
        self.resource_hash = resource_hash
        fd = build_profile.FILEDIVER
        self.paths, self.thin = {}, {}
        for line in (fd / 'hashes/hashes.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if line and not line.startswith('//'):
                self.paths[resource_hash(line)] = line
        for line in (fd / 'hashes/thinhashes.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.strip()
            if line:
                self.thin.setdefault(resource_hash(line) >> 32, line)

    def name(self, value):
        return None if not value else self.thin.get(value, f'0x{value:08X}')


def check_layout(library):
    outer = library.layout('HealthComponentData')
    index, records = outer['members']
    record = library.layout(records['type_hash'])
    default = next(m for m in record['members'] if m['offset64'] == DEFAULT_ZONE)
    zones = next(m for m in record['members'] if m['offset64'] == ZONE_BASE)
    zone = library.layout(default['type_hash'])
    have = {m['offset64']: (m['storage'], library.name_length(int(m['name'].split('=')[1].split(',')[0], 16)))
        for m in zone['members']}
    bad = [off for off, (storage, length, _) in ZONE_MEMBERS.items() if have.get(off) != (storage, length)]
    geometry = {'indexRows': index['array_or_bits'], 'records': records['array_or_bits'],
        'recordSize': records['size64'] // records['array_or_bits'], 'defaultZoneSize': default['size64'],
        'zoneSlots': zones['array_or_bits'], 'zoneStride': zones['size64'] // zones['array_or_bits'],
        'zoneInfoSize': zone['size64']}
    expected = {'indexRows': 1002, 'recordSize': RECORD_SIZE, 'defaultZoneSize': ZONE_INFO, 'zoneSlots': ZONES,
        'zoneStride': ZONE_STRIDE, 'zoneInfoSize': ZONE_INFO}
    if bad or any(geometry[k] != v for k, v in expected.items()):
        raise ValueError(f'HealthComponent / DamageableZoneInfo layout changed: {bad} {geometry}')
    return geometry


def zone_values(raw, base, names, record_offset_base):
    out = {'recordOffsetOfZone': record_offset_base}
    for off, (storage, _, name) in ZONE_MEMBERS.items():
        at = base + off
        if storage in ('UINT32', 'ENUM_INT32'):
            value = u32(raw, at)
        elif storage == 'INT32':
            value = i32(raw, at)
        elif storage == 'UINT8':
            value = raw[at]
        else:
            value = f32(raw, at)
            value = None if value >= FLT_MAX else round(value, 6)
        out[name] = value
        out.setdefault('recordOffsets', {})[name] = at
    out['zone_name'] = names.name(out['zone_name'])
    out['damage_multiplier'] = DAMAGE_MULTIPLIER[out['damage_multiplier']]
    out['damage_multiplier_dps'] = DAMAGE_MULTIPLIER[out['damage_multiplier_dps']]
    return out


def anatomy(view, names, resource):
    table = view.component('HealthComponentData')
    entry = table.owners.get(resource)
    if entry is None:
        return None
    record, row = entry
    raw = table.records[record]
    zones = []
    for index in range(ZONES):
        base = ZONE_BASE + index * ZONE_STRIDE
        if not u32(raw, base + 96):
            continue
        zone = zone_values(raw, base, names, base)
        zone['index'] = index
        zone['actors'] = [names.name(v) for v in struct.unpack_from('<24I', raw, base + ZONE_INFO) if v]
        zones.append(zone)
    owners = table.owners_of(record)
    return {'resource': hexid(resource), 'path': names.paths.get(resource), 'recordIndex': record, 'indexRow': row,
        'ownerCount': len(owners), 'owners': [names.paths.get(o, hexid(o)) for o in owners],
        'recordSha256': sha(raw), 'mainHealth': i32(raw, 0),
        'defaultZone': zone_values(raw, DEFAULT_ZONE, names, DEFAULT_ZONE), 'zones': zones}


def rack_items(view, resource):
    table = view.component('HellpodRackComponentData')
    entry = table.owners.get(resource)
    if entry is None:
        return None
    raw = table.records[entry[0]]
    return sorted({hexid(struct.unpack_from('<Q', raw, slot * 64)[0]) for slot in range(8)
        if struct.unpack_from('<Q', raw, slot * 64)[0]})


class Image:
    def __init__(self, data):
        self.data = data
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True

    def pin(self, rva, text, target, role):
        insn = next(self.md.disasm(self.data[rva:rva + 16], rva), None)
        if insn is None:
            raise ValueError(f'undecodable instruction at {rva:#x}')
        got = insn.mnemonic + ' ' + insn.op_str
        rip = None
        for op in insn.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                rip = insn.address + insn.size + op.mem.disp
        if got != text or rip != target:
            raise ValueError(f'pin drifted at {rva:#x}: {got!r} (rip {rip}) != {text!r} ({target})')
        return {'rva': f'0x{rva:X}', 'bytes': self.data[rva:rva + insn.size].hex(), 'asm': got,
            'ripTarget': None if target is None else f'0x{target:X}', 'role': role}


class Heap:
    def __init__(self, snap, game):
        self.snap, self.game = snap, game

    def read(self, address, size):
        region = self.snap.region(address)
        if region is None or region['status'] != snapshot_image.CAPTURED or address + size > region['base'] + region['size']:
            return None
        self.snap.handle.seek(region['data_offset'] + address - region['base'])
        return self.snap.handle.read(size)

    def u32(self, a):
        raw = self.read(a, 4)
        return None if raw is None else struct.unpack('<I', raw)[0]

    def ptr(self, a):
        raw = self.read(a, 8)
        value = None if raw is None else struct.unpack('<Q', raw)[0]
        return value if value and 0x10000 <= value < 0x800000000000 else None

    def hashmap(self, base, table, capacity, empty):
        pointer, count, sentinel = self.ptr(base + table), self.u32(base + capacity), self.u32(base + empty)
        if not pointer or not count or count > 1 << 20:
            return {}
        raw = self.read(pointer, count * 8) or b''
        out = {}
        for i in range(len(raw) // 8):
            key, value = struct.unpack_from('<Ii', raw, i * 8)
            if key != sentinel and value != -1:
                out[key] = value
        return out


def heap_evidence(snap, names):
    base = snap.modules['game.dll']['base']
    heap = Heap(snap, base)
    angles = {}
    for label, rva in (('projectile', 0x346D230), ('dps', 0x346D238)):
        pointer = heap.ptr(base + rva)
        raw = pointer and heap.read(pointer, 16)
        angles[label] = None if raw is None else [round(v, 3) for v in struct.unpack('<4f', raw)]
    health = heap.ptr(base + 0x3326688)
    avatar = heap.ptr(base + 0x3326D20)
    instances = heap.hashmap(health, 0x1030, 0x1038, 0x103C) if health else {}
    handles = heap.ptr(health + 0x1048) if health else None

    def resource_of(entity):
        index = instances.get(entity)
        handle = None if index is None or not handles else heap.ptr(handles + 8 * index)
        raw = handle and heap.read(handle, 8)
        return None if raw is None else struct.unpack('<Q', raw)[0]

    occupants = []
    for entity in (heap.hashmap(avatar, 0xF8, 0x100, 0x104) if avatar else {}):
        resource = resource_of(entity)
        occupants.append({'entity': f'0x{entity:X}', 'healthResource': resource and hexid(resource),
            'path': names.paths.get(resource)})
    overrides = heap.hashmap(health, 0x1070, 0x1078, 0x107C) if health else {}
    return {'snapshot': build_profile.SNAPSHOT_NAME, 'gameDllBase': f'0x{base:X}',
        'angleThresholdsDegrees': angles,
        'healthInstances': len(instances), 'healthOverrideCopies': len(overrides),
        'avatarManagerOccupants': occupants,
        'note': ('The retained snapshot is in the ship: one health instance (the Helldiver avatar), no override '
            'copies, and the avatar manager (whose armor-level curve replaces AP-vs-armor) holds only '
            'avatar_helldiver.')}


def damage_rows(view):
    group = view.settings_table('damage').group_by_type(DAMAGE_GROUP_TYPE)
    support = json.loads(SUPPORT_RESEARCH.read_text(encoding='utf-8'))
    out = {}
    for weapon in support['weapons']:
        name = weapon['catalogIdentity']
        if name not in COMPARISON_WEAPONS:
            continue
        attack = weapon['runtimeAttacks'][0]
        record_type = attack['damageInfo']['recordType']
        rows = group.row_for_type(record_type)
        if len(rows) != 1:
            raise ValueError(f'damage row for {name} ambiguous')
        row, raw = rows[0]
        values = {'standard_damage': i32(raw, 4), 'durable_damage': i32(raw, 8),
            'ap': list(struct.unpack_from('<4I', raw, 12)), 'demolition': u32(raw, 28)}
        research = attack['resolvedFields']
        if (values['standard_damage'], values['durable_damage'], values['ap']) != (research['standard_damage'],
                research['durable_damage'], [research['ap_direct'], research['ap_slight'], research['ap_large'],
                research['ap_extreme']]):
            raise ValueError(f'damage row for {name} disagrees with support-weapon research')
        out[name] = dict(values, damageRow=row, damageType=record_type, kind=attack['kind'])
    missing = set(COMPARISON_WEAPONS) - set(out)
    if missing:
        raise ValueError(f'comparison weapons missing: {sorted(missing)}')
    return out


def factor(ap, armor):
    difference = numpy.float32(ap) - numpy.float32(armor)
    if difference >= numpy.float32(1.0):
        return numpy.float32(1.0)
    if difference >= numpy.float32(0.0):
        return numpy.float32(0.65)
    return numpy.float32(0.0)


def per_hit(weapon, armor, durable):
    d = numpy.float32(durable)
    mixed = (numpy.float32(1.0) - d) * numpy.float32(weapon['standard_damage']) \
        + d * numpy.float32(weapon['durable_damage'])
    value = numpy.float32(max(numpy.float32(0.0), factor(weapon['ap'][0], armor) * mixed))
    return int(math.floor(float(value))), float(mixed)


def runtime_binding(resource):
    """The generated domain's backing for the SH-20 fields (read-only parse of domains/entity_authoring.lua)."""
    text = ENTITY_DOMAIN.read_text(encoding='utf-8')
    fields = {}
    for match in re.finditer(r'\["backing"\]=(\{[^}]*\})', text):
        body = match.group(1)
        if f'["resource"]="{resource}"' not in body:
            continue
        key = re.search(r'\["instanceKey"\]="(backpack:sh-20-[^"]*:(entity\.\w+))"', text[match.end():match.end() + 800])
        if not key:
            continue
        fields[key.group(2)] = {'instanceKey': key.group(1),
            'component': re.search(r'\["component"\]="([^"]+)"', body).group(1),
            'recordIndex': int(re.search(r'\["recordIndex"\]=(\d+)', body).group(1)),
            'offset': int(re.search(r'\["offset"\]=(\d+)', body).group(1)),
            'storage': re.search(r'\["storage"\]="([^"]+)"', body).group(1)}
    if set(fields) != {'entity.health', 'entity.armor'}:
        raise ValueError(f'SH-20 runtime binding not found: {sorted(fields)}')
    return fields


def build():
    names = Names()
    library = build_view.TypeLibrary((build_profile.datalibrary() / 'dl_library.dl_typelib').read_bytes())
    geometry = check_layout(library)
    view = build_view.from_datalibrary(build_profile.datalibrary(), {})
    if view.build['entitiesSha256'] != build_profile.ENTITY_SHA256 or \
            view.build['typelibSha256'] != build_profile.TYPELIB_SHA256:
        raise ValueError('pinned datalibrary changed')
    health_type_index = view.component('HealthComponentData').type_index
    if health_type_index != 0xE0:
        raise ValueError('HealthComponentData type index changed')

    # Identity chain.
    entity_research = json.loads(ENTITY_RESEARCH.read_text(encoding='utf-8'))
    backpack = next(b for b in entity_research['backpacks'] if b['name'] == SH20)
    shield = names.resource_hash(SH20_PATH)
    rack = names.resource_hash(RELATED['SH-20 rack'])
    if hexid(shield) != backpack['resource'] or backpack['rack']['ownerResources'] != [hexid(rack)]:
        raise ValueError('SH-20 identity chain changed')
    if rack_items(view, rack) != [hexid(shield)]:
        raise ValueError('SH-20 rack does not attach exactly the ballistic shield entity')
    import research_entity_authoring as entity_authoring  # full component list via the pinned entity report
    native = entity_authoring.Native()
    components = sorted(c['name'] for c in native.report(hexid(shield))['components'] if c['name'])
    if not {'BackpackComponentData', 'WieldableComponentData', 'AttachableComponentData',
            'MeleeShieldComponentData', 'HealthComponentData'} <= set(components) \
            or 'AvatarComponentData' in components:
        raise ValueError('SH-20 component set changed')
    melee = native.component(hexid(shield), 'MeleeShieldComponentData')
    melee_raw = native.record('MeleeShieldComponentData', melee['record_index'])
    melee_shield = {'recordIndex': melee['record_index'], 'recordSize': len(melee_raw), 'raw': melee_raw.hex(),
        'owners': [native.path(r) for r in native.owners('MeleeShieldComponentData')[melee['record_index']]],
        'finding': ('36-byte record (hit-effect type 29, a 65.0 float, flags, two thin hashes); no armor, health '
            'or AP member. Melee-block tuning, not on the projectile damage path.')}
    main = anatomy(view, names, shield)
    zone0 = main['zones'][0] if main['zones'] else None
    # Exact bytes Runtime re-proves before a zone write: zone 0's name hash and its whole 24-slot actor list.
    shield_record = view.component('HealthComponentData').records[main['recordIndex']]
    zone_guards = [{'offset': ZONE_BASE + 96, 'hex': shield_record[ZONE_BASE + 96:ZONE_BASE + 100].hex(),
        'role': 'zone 0 name hash ("shield")'},
        {'offset': ZONE_BASE + ZONE_INFO, 'hex': shield_record[ZONE_BASE + ZONE_INFO:ZONE_BASE + ZONE_INFO + 96].hex(),
        'role': 'zone 0 hit actors ("damageable", "collision", 22 empty slots)'}]
    if not (main['ownerCount'] == 1 and len(main['zones']) == 1 and zone0['zone_name'] == 'shield'
            and set(zone0['actors']) == {'damageable', 'collision'}):
        raise ValueError('SH-20 zone anatomy changed')

    # Health deltas: the only producer of per-instance override copies.
    health_deltas = []
    for resource, delta in view.deltas.items():
        entries = [(e['offset'], e['size']) for e in delta['entries'] if e['component'] == health_type_index]
        if entries:
            health_deltas.append({'deltaResource': hexid(resource), 'path': names.paths.get(resource),
                'healthOffsets': [offset for offset, _ in entries]})
    if any(o >= DEFAULT_ZONE for d in health_deltas for o in d['healthOffsets']):
        raise ValueError('an entity delta now touches HealthComponent zones')

    related = {}
    for label, path in RELATED.items():
        resource = names.resource_hash(path)
        item = {'path': path, 'resource': hexid(resource),
            'components': sorted(n for n, t in view.components.items() if resource in t.owners)}
        health = anatomy(view, names, resource)
        if health:
            item['health'] = {k: health[k] for k in ('recordIndex', 'ownerCount', 'mainHealth')}
            item['health']['defaultZoneArmor'] = health['defaultZone']['armor']
            item['health']['zones'] = [{'index': z['index'], 'name': z['zone_name'], 'armor': z['armor'],
                'maxArmor': z['max_armor'], 'health': z['health'], 'actors': z['actors']} for z in health['zones']]
        items = rack_items(view, resource)
        if items is not None:
            item['rackItems'] = [{'resource': r, 'path': names.paths.get(int(r, 16))} for r in items]
        related[label] = item

    # Code proof against the retained snapshot's unpacked game.dll.
    snap = snapshot_image.Snapshot(build_profile.SNAPSHOT)
    if snap.game_dll_sha256.upper() != PROFILE_DLL_SHA.upper():
        raise ValueError('snapshot game.dll is not the profile build')
    _, data = snap.module_image('game.dll')
    image = Image(data)
    code = {group: [image.pin(*pin) for pin in pins] for group, pins in PINS.items()}
    constants = {f'0x{rva:X}': round(f32(data, rva), 7) for rva in CONSTANTS}
    if any(abs(f32(data, rva) - value) > 1e-6 for rva, value in CONSTANTS.items()):
        raise ValueError('damage-factor constants changed')
    multiplier = [round(f32(data, DAMAGE_MULTIPLIER_TABLE + 4 * i), 6) for i in range(5)]
    curve = [[round(f32(data, AVATAR_CURVE + 8 * i), 6), round(f32(data, AVATAR_CURVE + 8 * i + 4), 6)]
        for i in range(5)]
    if multiplier != [0.0, 1.5, 1.0, 0.75, 0.25]:
        raise ValueError('damage multiplier table changed')
    heap = heap_evidence(snap, names)
    snap.close()
    if [o['path'] for o in heap['avatarManagerOccupants']] != [RELATED['Helldiver avatar']]:
        raise ValueError('avatar manager occupant is not the Helldiver avatar')

    # Damage model against the shield plate (zone 0) for head-on hits.
    weapons = damage_rows(view)
    durable = zone0['projectile_durable_resistance']
    predictions = []
    for name, weapon in weapons.items():
        for armor in (3, 4, 5, 6):
            damage, mixed = per_hit(weapon, armor, durable)
            predictions.append({'weapon': name, 'apDirect': weapon['ap'][0], 'zone0Armor': armor,
                'factor': float(factor(weapon['ap'][0], armor)), 'durableWeightedDamage': round(mixed, 3),
                'damagePerHit': damage,
                'hitsToBreak': None if damage == 0 else math.ceil(main['mainHealth'] / damage)})

    lookup = {(p['weapon'], p['zone0Armor']): p for p in predictions}
    if lookup[('MG-206 Heavy Machine Gun', 4)]['damagePerHit'] != 45 or \
            lookup[('MG-206 Heavy Machine Gun', 5)]['damagePerHit'] != 0:
        raise ValueError('HMG damage model changed; update the answer text')
    binding = runtime_binding(hexid(shield))
    if binding['entity.armor']['offset'] != DEFAULT_ZONE + 216:
        raise ValueError('Runtime entity.armor binding changed')
    zone_armor_offset = ZONE_BASE + 0 * ZONE_STRIDE + 216
    return {
        'schemaVersion': 1,
        'question': ('SH-20 Ballistic Shield entity.armor set to 5; the MG-206 HMG (AP 4) still damages the '
            'shield. Why?'),
        'source': {'build': build_profile.BUILD_ID, 'datalibrary': 'build profile ' + build_profile.BUILD_ID,
            'entitiesSha256': build_profile.ENTITY_SHA256, 'typelibSha256': build_profile.TYPELIB_SHA256,
            'snapshot': build_profile.SNAPSHOT_NAME, 'gameDllSha256': PROFILE_DLL_SHA,
            'unpackedImageSha256': sha(data), 'writes': 0},
        'answer': {
            'summary': ('Runtime\'s entity.armor for the SH-20 writes the DEFAULT damage zone (record 292 +280). '
                'Every bullet that hits the shield resolves to damage zone 0 "shield" (it lists the hit actors '
                '"damageable" and "collision"), whose own armor (record 292 +736) stayed 4. HMG AP 4 vs armor 4 '
                'is the equal case: factor 0.65, so the shield still loses floor(0.65 * 69.5) = 45 HP per bullet. '
                'Armor 5 on zone 0 would give AP - armor = -1 -> factor 0 -> no damage.'),
            'activeField': {'entity': SH20_PATH, 'resource': hexid(shield), 'component': 'HealthComponentData',
                'recordIndex': main['recordIndex'], 'indexRow': main['indexRow'], 'zoneIndex': 0,
                'zoneName': 'shield', 'zoneActors': zone0['actors'], 'member': 'DamageableZoneInfo.armor (+216)',
                'recordOffset': zone_armor_offset, 'storage': 'u32', 'vanilla': zone0['armor'],
                'ownerCount': main['ownerCount'], 'sharedWith': [], 'guards': zone_guards},
            'classification': {
                'zone0.armor (+736)': ('ACTIVE_AT_INSTANTIATION: copied into the health instance (+0x60) when the '
                    'shield entity spawns; every plate hit reads that copy. Edits reach shields spawned after the '
                    'write, not a shield already in the world.'),
                'entity.armor (+280, default zone)': ('DORMANT_OR_METADATA for the SH-20 plate: also copied at '
                    'spawn (instance +0x5c) but only consulted for hits on an actor no zone lists; the SH-20\'s '
                    'only zone lists the shield actors. It equals zone 0 in vanilla (both 4), which is why the '
                    'wiki "Main / Heavy" correlation looked right.'),
                'zone0.projectile_durable_resistance (+724), damage_multiplier (+716), ignore_armor_on_self (+748)': (
                    'ACTIVE_DIRECT: read from the definition record on every hit.'),
            },
        },
        'layout': dict(geometry, defaultZoneOffset=DEFAULT_ZONE, zoneBase=ZONE_BASE),
        'identity': {'stratagem': backpack['stratagemRoot'], 'rack': hexid(rack), 'item': hexid(shield),
            'components': components, 'meleeShield': melee_shield, 'sameEntityWornHeldDropped': (
                'One entity: the rack attaches only this item and it owns Backpack, Wieldable, Attachable, '
                'MeleeShield and Health; there is no separate held-shield unit with its own HealthComponent.')},
        'healthComponent': main,
        'runtimeBinding': {'domain': str(ENTITY_DOMAIN.relative_to(ROOT)), 'fields': binding,
            'finding': 'entity.armor is bound to offset 280 (default-zone armor), not to zone 0 armor at 736.'},
        'healthDeltas': {'count': len(health_deltas), 'entries': health_deltas,
            'finding': 'No entity delta touches any HealthComponent zone; none targets a shield.'},
        'related': related,
        'code': code,
        'constants': {'values': constants, 'damageMultiplierTable': multiplier, 'avatarArmorCurve': curve},
        'heap': heap,
        'damageModel': {
            'rule': ('factor = 1.0 if AP - armor >= 1; 0.65 if 0 <= AP - armor < 1; else 0. ignore_armor_on_self '
                'forces 1.0. Avatars (Helldivers) use the armor-level curve instead. damage = floor(factor * '
                '((1-d)*standard + d*durable) * m) * multiplier[damage_multiplier]; d = zone durable share, '
                'm = event+0x94 (assumed 1.0 here).'),
            'apSelection': ('AP[i] with i = first angle threshold >= the angle from the surface normal '
                '(projectile thresholds 25/60/80/90 degrees). Head-on hits use AP direct.'),
            'shieldPlate': {'zone': 0, 'durableShare': durable, 'damageMultiplier': zone0['damage_multiplier'],
                'mainHealth': main['mainHealth'], 'zoneHealth': zone0['health'],
                'note': 'zone health -1: damage goes to the 1000 main pool (affects_main_health 1.0).'},
            'weapons': weapons, 'predictions': predictions},
        'recommendation': {
            'api': ('Bind the SH-20 armor to zone 0: expose hd2.backpack(SH-20):zone("shield") with zone.armor '
                '(record 292 +736, vanilla 4), or remap the backpack\'s armor field to +736. Stop presenting '
                '+280 as the shield armor: classify it dormant (fallback-only) and gate it behind '
                'allow_unverified_effect, or write both +280 and +736 in one operation group. Document that the '
                'change applies to shields spawned after the write.'),
            'guards': ('Re-prove at write time: record 292 unique owner, zone 0 name hash "shield", actors '
                '["damageable", "collision"], expected armor 4.'),
        },
        'liveTest': {
            'setup': ('Apply the write, then call in a NEW SH-20 (a shield already spawned keeps its instance '
                'armor). Drop it or have a teammate hold it; shoot head-on (angle <= 25 degrees) and count '
                'hits. Use projectile weapons without explosions.'),
            'expected': [
                'Vanilla control, zone 0 armor 4: HMG 45 per hit, breaks on hit 23; Railgun 337 per hit, breaks on 3.',
                'Zone 0 armor 5 (new shield): HMG and APW-1 (AP 4) deal 0 and never break it; Railgun (AP 5) '
                '219 per hit, breaks on 5.',
                'Old shield spawned before the write: still HMG 45 per hit (proves instantiation semantics).',
                'Zone 0 armor 3 (optional): HMG 69 per hit, breaks on 15; MG-43 (AP 3, 0 vs vanilla) 28 per hit.',
                'Reproduce the report: entity.armor (+280) = 5 alone, new shield: HMG still 45 per hit.',
            ],
        },
        'unproven': [
            'The shield unit\'s physics actor list was not decoded (bundles.*.nxa); zone 0 lists "damageable" and '
            '"collision". Any other hittable actor would fall back to the default zone.',
            'event+0x94 (caller damage scale) is assumed 1.0; it changes hit counts, not the zero/non-zero outcome.',
            'No live observation yet of zone 0 armor on the SH-20.',
            'SH-51: entity.health/entity.armor bind the backpack body (record 296, no zones); the barrier is a '
            'separate entity (record 80, zone 0 body_front armor 1, max armor 2, 450 HP). Not traced here.',
        ],
    }


def main() -> None:
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['answer'], indent=1))
    for p in report['damageModel']['predictions']:
        print(p['weapon'], 'AP', p['apDirect'], 'armor', p['zone0Armor'], 'factor', p['factor'],
            'per hit', p['damagePerHit'], 'hits', p['hitsToBreak'])


if __name__ == '__main__':
    main()
