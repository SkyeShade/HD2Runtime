"""Armor passive EFFECTS beyond the modifier rows: the effect package of a passive (how 0x874D80 turns the 32-bit
passive +0x30 field into a 64-bit package and loads it), the data-driven and stat-driven readers of the passive keys
that have no direct EntityAttribute reader, and the non-modifier mechanisms (Integrated Explosives, Adreno-
Defibrillator). Read-only research against the retained snapshots (research/docs/passive-effects-F5FEE03DCFDB.md).

  py scripts/research_passive_effects.py          # write research/passive-effects-F5FEE03DCFDB.json
  py scripts/research_passive_effects.py --no-scan  # skip the full-memory key census (about 30 s)

Every structural claim is pinned as exact instruction bytes (identical in every retained snapshot); every value is read
from the snapshots or the installed game's bundles. Passive names and modifier texts come from
research/player-attributes-F5FEE03DCFDB.json (the game's own text ids, resolved by scripts/research_player_attributes.py).
Nothing writes. Requires capstone and numpy (research only).
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
import struct
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import hd2_game_data as gdata  # noqa: E402
import research_event_state as base  # noqa: E402
import research_package_residency as rpr  # noqa: E402
import research_player_attributes as rpa  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/passive-effects-F5FEE03DCFDB.json'
ATTRIBUTES = ROOT / 'research/player-attributes-F5FEE03DCFDB.json'
BOOSTERS = ROOT / 'research/booster-native-F5FEE03DCFDB.json'

G_CUSTOMIZATION = rpa.G_CUSTOMIZATION     # 0x33264F8
G_PREVIOUS_IDS = 0x37CED80                # u32[8]: the passive ids 0x874D80 loaded last (2 per player slot)
G_PACKAGE_SYSTEM = 0x347CEB0              # RefcountedPackageSystem instance (= core/assets loader.instanceGlobalRva)
F_REQUEST, F_RELEASE = 0x12FE350, 0x12FE4E0   # = core/assets loader.requestRva / releaseRva
F_RESOLVE = 0x12689C0                     # u64 *ResolveDependencyPackage(u64 *out, u32 thin)
G_DEP_TABLE_COUNT, G_DEP_TABLES = 0x348D398, 0x3799DD0   # generated_add_resource_dependencies instances
G_LOOKUP = 0x3799810                      # hash_lookup map {u64 *slots; u32 capacity; ...; u64 empty; u32 multiplier}
G_BOOSTER_ROWS, BOOSTER_STRIDE, BOOSTER_ROWS = 0x32FDA90, 0x38, 0x15
G_STATS = 0x3326AC0                       # per-entity stat component manager (20 stats)
STAT_DEFAULTS = 0x2141790                 # f32[20] stat defaults (used when the entity has no stat record)
F_GET_STAT, F_SET_STAT, F_PASSIVE_STATS = 0xA079B0, 0xA076C0, 0x11DA190
G_ZONE_MANAGER = 0x3326830                # = component world + 0x7C6098 ("ability damage zone" manager)
PACKAGE_FIELD = 0x30
THIN_PACKAGES = {17: 0x644F8A3B, 19: 0x638B9586}
LOOKUP_TYPE, LOOKUP_NAME = 0x7056BC19C69F0F07, 0xE3F2851035957AF5
TYPE_NAMES = (b'unit', b'particles', b'material', b'texture', b'wwise_bank', b'wwise_dep', b'package', b'state_machine',
    b'entity', b'prefab', b'animation', b'bones', b'physics', b'level', b'lua', b'config', b'hash_lookup')

PINS = {
    'passivePackageLoader': [   # 0x874D80, called once per world update from 0x571250
        (0x874DC8, 'call 0x874520', None, 'every record: pending -> applied (sets +0x38/+0x3C)'),
        (0x874DFC, 'lea rbx, [rdi + 0x9a4]', None, 'record +0x38 (helmet passive) of record 0'),
        (0x874E19, 'call 0x606820', None, 'player slot of the record entity'),
        (0x874E29, 'mov eax, dword ptr [rbx - 0x40]', None, 'record +0x3C armor passive -> ids[2*slot]'),
        (0x874E33, 'mov eax, dword ptr [rbx - 0x44]', None, 'record +0x38 helmet passive -> ids[2*slot+1]'),
        (0x874E4A, 'lea r14, [rip + {rip}]', G_PREVIOUS_IDS, 'the 8 ids loaded last time'),
        (0x874E5F, 'call 0x21049d0', None, 'memcmp(ids, previous, 0x20): nothing changed -> done'),
        (0x874E88, 'cmp edi, eax', None, 'per entry: new id == previous id -> skip'),
        (0x874EA6, 'mov edx, dword ptr [rdx + 0x30]', None, 'PREVIOUS passive +0x30 (32-bit package key)'),
        (0x874EAE, 'call 0x12689c0', None, 'resolve the key to a 64-bit package id'),
        (0x874EB3, 'cmp qword ptr [rsp + 0x20], 0', None, 'no package (key 0 or unknown) -> skip'),
        (0x874EBB, 'mov rcx, qword ptr [rip + {rip}]', G_PACKAGE_SYSTEM, 'RefcountedPackageSystem'),
        (0x874EC7, 'mov r8d, 1', None, 'one package'),
        (0x874ECD, 'call 0x12fe4e0', None, 'RELEASE the previous passive package'),
        (0x874EEF, 'mov edx, dword ptr [rdx + 0x30]', None, 'NEW passive +0x30'),
        (0x874EF7, 'call 0x12689c0', None, 'resolve'),
        (0x874F04, 'mov rcx, qword ptr [rip + {rip}]', G_PACKAGE_SYSTEM, 'RefcountedPackageSystem'),
        (0x874F16, 'call 0x12fe350', None, 'REQUEST the new passive package (asynchronous load)'),
        (0x874F30, 'movups xmmword ptr [rip + {rip}], xmm6', G_PREVIOUS_IDS, 'remember the ids'),
    ],
    'resolveDependencyPackage': [   # 0x12689C0(u64 *out, u32 thin)
        (0x12689D4, 'mov esi, dword ptr [rip + {rip}]', G_DEP_TABLE_COUNT, 'number of dependency tables'),
        (0x12689EA, 'lea rbx, [rip + {rip}]', G_DEP_TABLES, 'dependency table pointers'),
        (0x12689F6, 'mov r9d, dword ptr [r10 + 8]', None, 'table entry count'),
        (0x1268A0A, 'cmp dword ptr [r10 + rcx*8], edx', None, 'entry {u32 thin, pad, u64 name} (stride 16): thin match'),
        (0x1268A2A, 'mov r9, qword ptr [r10 + r8*8 + 8]', None, 'the 64-bit dependency name'),
        (0x1268A2F, 'mov r8d, dword ptr [rip + {rip}]', G_LOOKUP + 8, 'hash_lookup map capacity'),
        (0x1268A36, 'mov r10d, dword ptr [rip + {rip}]', G_LOOKUP + 0x18, 'hash_lookup map multiplier'),
        (0x1268A4A, 'mov r11, qword ptr [rip + {rip}]', G_LOOKUP + 0x10, 'hash_lookup map empty key'),
        (0x1268A51, 'mov rbx, qword ptr [rip + {rip}]', G_LOOKUP, 'hash_lookup map slots {u64 key, u64 value}'),
        (0x1268A87, 'mov rdi, qword ptr [rbx + rax*8 + 8]', None, 'value = the package resource id'),
        (0x1268A99, 'mov qword ptr [r14], rdi', None, '*out = package (0 when either lookup misses)'),
    ],
    'tableSources': [
        (0x12687D7, 'lea rcx, [rip + {rip}]', 0x22BFDF8, '"generated_add_resource_dependencies.dl_bin" (DL instances)'),
        (0x1268921, 'mov qword ptr [r13 + rax*8], rsi', None, 'registers each instance in the dependency table list'),
        (0x1268917, 'inc r11d', None, 'table count++'),
        (0xFD176B, 'movabs rdx, 0xe3f2851035957af5', None, 'resource name hash_lookup'),
        (0xFD1780, 'movabs rcx, 0x7056bc19c69f0f07', None, 'resource type hash_lookup'),
        (0xFD1A0B, 'mov qword ptr [rip + {rip}], rax', G_LOOKUP, 'the map is parsed out of the hash_lookup resource'),
    ],
    'boosterPackageLoader': [   # the same mechanism for boosters (0x8568A0, also called from 0x571250)
        (0x8569B0, 'lea r14, [rip + {rip}]', G_BOOSTER_ROWS, 'booster table (21 rows of 0x38)'),
        (0x8569E3, 'mov edx, dword ptr [rdi + r14 + 0x34]', None, 'booster row +0x34 (32-bit package key)'),
        (0x8569E8, 'call 0x12689c0', None, 'resolve'),
        (0x856A07, 'call 0x12fe350', None, 'request'),
    ],
    'passiveStats': [   # 0x11DA190: the passive STAT rows feed the per-entity stat component
        (0x11DA1CC, 'mov r13, qword ptr [rip + {rip}]', G_STATS, 'stat component manager'),
        (0x11DA410, 'mov eax, dword ptr [r15 + r9 + 0xa88]', None, 'PENDING armor kit (pending +0x0C), not record +0x3C'),
        (0x11DA465, 'mov eax, dword ptr [rcx + 0x1c]', None, 'the kit Passive'),
        (0x11DA48F, 'mov r8d, dword ptr [rdx + 0x28]', None, 'passive stat row count'),
        (0x11DA4A0, 'mov r14, qword ptr [rdx + 0x20]', None, 'passive stat rows {u32 stat, f32 add, f32 mul}'),
        (0x11DA4C6, 'cmp eax, 0x14', None, '20 stats'),
        (0x11DA4D4, 'addss xmm0, dword ptr [rbp + rax*4 - 0x80]', None, 'add[stat] += row add'),
        (0x11DA4DA, 'mulss xmm1, dword ptr [rsp + rax*4 + 0x30]', None, 'mul[stat] *= row mul'),
        (0x11DA609, 'mov eax, dword ptr [r15 + r9 + 0xa80]', None, 'PENDING helmet kit (pending +0x04)'),
        (0x11DA7D2, 'call 0xa079b0', None, 'GetStat (base: entity stat record, else defaults)'),
        (0x11DA7D7, 'mulss xmm0, dword ptr [rsp + rdi + 0x30]', None, 'base * mul'),
        (0x11DA7DF, 'addss xmm0, xmm2', None, '+ add'),
        (0x11DA7E6, 'call 0xa076c0', None, 'SetStat(entity, stat, value)'),
        (0xA07CC4, 'call 0x11da190', None, 'from the stat component add/refresh 0xA07B10 (spawn time)'),
        (0xA07A20, 'lea rcx, [rip + {rip}]', STAT_DEFAULTS, 'stat defaults f32[20]'),
    ],
    'reloadSpeed': [    # 0x774A40(stat manager, wielder, weapon): reload multiplier
        (0x774A61, 'mov r8d, 0xa', None, 'stat 10: general reload'),
        (0x774AE8, 'cmp edi, dword ptr [rbp + rsi*8]', None, 'weapon == inventory slot 0 (primary)'),
        (0x774AEE, 'mov r8d, 0xd', None, 'stat 13: primary reload'),
        (0x774B02, 'cmp edi, dword ptr [rbp + rsi*8 + 4]', None, 'weapon == slot 1 (sidearm)'),
        (0x774B08, 'mov r8d, 0xf', None, 'stat 15: sidearm reload'),
        (0x774B1C, 'cmp edi, dword ptr [rbp + rsi*8 + 8]', None, 'weapon == slot 2 (support)'),
        (0x774B22, 'mov r8d, 0xe', None, 'stat 14: support reload'),
    ],
    'meleeDamageZone': [   # 0x7D01C0: ability damage zone hit; zone settings +0xD4 = passive key
        (0x573121, 'lea rcx, [rdi + 0x7c6098]', None, 'ability damage zone manager (component world + 0x7C6098)'),
        (0x57312B, 'call 0x7cee60', None, 'zone update -> 0x7D01C0 per active zone'),
        (0x7D26AF, 'mov edx, dword ptr [rsi + 0xd4]', None, 'key = zone settings +0xD4 (0 -> skipped)'),
        (0x7D26BF, 'call 0x11d9df0', None, 'EntityAttribute(zone owner, key, 3)'),
        (0x7D26C9, 'cmp dword ptr [rax + 4], 2', None, 'Multiply rows only'),
        (0x7D26D7, 'mulss xmm0, dword ptr [rax + 8]', None, 'damage multiplier *= value'),
        (0x4918E, 'mov dword ptr [rbp + 0x2b], 0x2559b40d', None, 'compiled-in zone settings: +0xD4 = melee damage key'),
    ],
    'locomotion': [   # 0x9C94C0: movement speed tiers, tier +0x18 = passive key
        (0x9C95CF, 'call 0x513c60', None, 'locomotion settings of the entity (component data, 0x1210 per type)'),
        (0x9C9628, 'imul rax, rax, 0x22c', None, 'state entry (0x22C)'),
        (0x9CA50E, 'mov r8d, 0x108', None, 'second tier table (+0x108) vs first (+8)'),
        (0x9CA51D, 'lea r13, [rax + r10]', None, 'tier table'),
        (0x9CABB9, 'mov edx, dword ptr [rax + r13 + 0x18]', None, 'tier (0x20 bytes) +0x18 = passive key (0 -> skipped)'),
        (0x9CABCC, 'call 0x11d9df0', None, 'EntityAttribute(entity, key, 3)'),
        (0x9CABDB, 'mulss xmm1, xmm0', None, 'tier speed *= value'),
        (0x5137F8, 'add rax, 0x1980', None, 'entity-type component data record (entity manager table)'),
    ],
    'integratedExplosives': [   # 0x822140 (avatar death handling)
        (0x82252F, 'mov edx, 0x54a69284', None, '"armor explodes after the wearer dies"'),
        (0x822536, 'mov r8d, 1', None, 'flags 1: armor slot only'),
        (0x822589, 'lea r8d, [r9 + 0x42]', None, 'status effect type 0x42 (66)'),
        (0x82258D, 'call 0x699e40', None, 'apply the status effect to the dead avatar'),
    ],
    'arcStatusScale': [
        (0x87A590, 'cmp r8d, 2', None, 'element 2 only'),
        (0x87A5AB, 'mov edx, 0x8933e7f4', None, 'key without text (Conduit, Acclimated, Adreno, Desert Stormer)'),
        (0x87A613, 'cvttss2si rcx, xmm0', None, 'integer amount * value, at least 1'),
    ],
}

# Reader status per key: (mechanism, reader, follows a write of record +0x3C?, how a live test sees it).
DIRECT = 'direct reader'
DATA = 'data-driven reader'
STAT = 'stat row (kit passive, spawn time)'
KIT = 'kit passive (PassiveValue)'
NONE = 'none found'
KEYS = {
    'AF8B7112': (DIRECT, '12 sites (0x64A890, 0x756D50, 0x81F470, ...)', True, 'enemies notice the player later while moving (hard to measure)'),
    '14ECCE15': (DIRECT, '0x64C6F0', True, 'enemies must be closer to notice the player'),
    '432A7993': (DIRECT, '0x6784E0', True, 'points of interest are identified from farther away'),
    'B62B4AFD': (DIRECT, 'ApplyDamage 0x9235F0', True, 'falls / leg hits never injure the legs'),
    'A189ADB6': (DIRECT, 'ApplyDamage 0x9235F0', True, 'stamina bar refills on taking damage'),
    '2CFAECA3': (DIRECT, 'ProduceDamage 0x129DD30', True, 'less damage from chest hits'),
    '1F98D152': (DIRECT, '0x129D180', True, 'less damage from explosions (e.g. own grenade)'),
    '4DF29271': (DIRECT, 'resistance combiner 0x87A430', True, 'less fire damage'),
    '4BDF39C4': (DIRECT, 'resistance combiner 0x87A430', True, 'less arc damage'),
    '6E99CCE5': (DIRECT, 'resistance combiner 0x87A430', True, 'less gas damage'),
    'B5A50096': (DIRECT, 'resistance combiner 0x87A430', True, 'less fire / gas / acid / arc damage'),
    '25A59469': (DIRECT, '0x87A430, 0x63B730', True, 'less impact / collision damage'),
    'FBF54A40': (DIRECT, '0xC1FC0 (via 0x4CDC60)', True, 'fewer limb injuries'),
    'A68930C2': (DIRECT, '0xC1FC0 (flags 1), 0x699E40', True, 'chest bleed does no damage'),
    '73734D67': (DIRECT, '0x829E90, 0x82D930, 0x8354B0, 0xA8C1F0 (flags 1)', True, 'no aim flinch when hit'),
    '54A69284': (DIRECT, '0x822140 (flags 1) -> status effect 66', True, 'the body explodes after death (needs the package)'),
    'CB814D05': (DIRECT, '0xB51860', True, 'occasionally survives lethal damage'),
    '11A3C04C': (DIRECT, '0x93FD50', True, 'knocked prone less often'),
    '86A99BB9': (DIRECT, '0x87AEF0 (from 0x581320, 0xB517F0)', True, 'limbs take more hits before injury'),
    'C36935A9': (DIRECT, '0x68AEC0', True, 'less recoil crouched / prone'),
    'C8CCB6FA': (DIRECT, '0x759250, 0x8226F0', True, 'faster weapon turning (ergonomics)'),
    '26C969A1': (DIRECT, '0x6C5BC0', True, 'grenades fly farther'),
    'F6FA9626': (DIRECT, '0x9A6990, 0x9ADDC0 (capacity)', True, 'grenade count +2 (capacity: likely at resupply / spawn)'),
    '2875F44A': (DIRECT, '0x9ADF00, 0x9B0570 (capacity)', True, 'stim count +2 (capacity: likely at resupply / spawn)'),
    '93EB16A7': (DIRECT, '0x699E40 (status effect apply)', True, 'stim effect lasts 2 s longer'),
    '21A7BA64': (DIRECT, '0x18AE700', True, 'map markers pulse radar scans'),
    '6938BD56': (DIRECT, '0xA722E0 (presence)', True, 'longer, faster slides'),
    '8933E7F4': (DIRECT, '0x87A590 (from 0x129C9F0, 0x129CF10)', True, 'element-2 status amount scaled x0.05 (likely arc stun buildup)'),
    '0DFF0E42': (DIRECT, '0x1127C10 (presence)', True, 'selects state 0x7DCD5820 instead of 0x0399532A (unnamed)'),
    'AFAE3B47': (KIT, 'PassiveValue with the armor KIT passive (0x878160, 0x12A15E0, 0x14E7430, 0x1915EB0)', False,
        'armor rating does not follow a record swap'),
    '2559B40D': (DATA, '0x7D01C0 (ability damage zones), key = zone settings +0xD4', True, 'melee hits do more damage'),
    'CD79A687': (DATA, '0x9C94C0 (locomotion), key = avatar "jog" tier +0x18', True, 'faster jog'),
    'F6D67313': (DATA, '0x9C94C0 (locomotion), key = avatar "sprint" tier +0x18', True, 'faster sprint'),
    'CC530B21': (STAT, 'stat 13 (primary reload) via 0x774A40 / 0x774B60', False, 'only the kit worn at spawn changes it'),
    '35F17BEC': (STAT, 'stat 14 (support reload) via 0x774A40 / 0x774B60', False, 'only the kit worn at spawn changes it'),
    'B4F88129': (STAT, 'stat 15 (sidearm reload) via 0x774A40 / 0x774B60', False, 'only the kit worn at spawn changes it'),
    '33C9C713': (STAT, 'stat 12 (ammo capacity) via 0x757AA0, 0x762380, 0x76E000, 0x779DC0, 0x77A430, 0x77B1E0, 0x9A67A0, '
        '0x9AA290, 0x9B0870', False, 'only the kit worn at spawn changes it'),
    'AD5289FE': (STAT, 'stat 16 (sidearm draw) via 0x8C0E90, 0xA94EF0', False, 'only the kit worn at spawn changes it'),
    '22035F3C': (STAT, 'stat 17 (sidearm recoil) via 0x784570', False, 'only the kit worn at spawn changes it'),
}
STAT_NAMES = {10: 'reload (all weapons)', 11: 'unnamed (0x607ED0 scales an integer quantity)', 12: 'ammo capacity',
    13: 'primary reload', 14: 'support reload', 15: 'sidearm reload', 16: 'sidearm draw / holster', 17: 'sidearm recoil'}
STAT_KEY = {12: '33C9C713', 13: 'CC530B21', 14: '35F17BEC', 15: 'B4F88129', 16: 'AD5289FE', 17: '22035F3C'}


def prove_all(image):
    out = {}
    for group, rows in PINS.items():
        out[group] = [image.prove(*row) for row in rows]
    return out


def read_lookup(mem):
    g = mem.game
    slots, capacity = mem.ptr(g + G_LOOKUP), mem.u32(g + G_LOOKUP + 8)
    empty, multiplier = mem.u64(g + G_LOOKUP + 0x10), mem.u32(g + G_LOOKUP + 0x18)
    raw = mem.read(slots, 16 * capacity)
    pairs = [struct.unpack_from('<QQ', raw, 16 * i) for i in range(capacity)]
    return {k: v for k, v in pairs if k != empty}, {'capacity': capacity, 'used': sum(1 for k, _ in pairs if k != empty),
        'empty': empty, 'multiplier': multiplier}


def read_dependency_tables(mem):
    g = mem.game
    tables = []
    for t in range(mem.u32(g + G_DEP_TABLE_COUNT)):
        pointer = mem.ptr(g + G_DEP_TABLES + 8 * t)
        entries, count = struct.unpack('<QI', mem.read(pointer, 12))
        raw = mem.read(entries, 16 * count) if count else b''
        tables.append([(struct.unpack_from('<I', raw, 16 * i)[0], struct.unpack_from('<Q', raw, 16 * i + 8)[0])
            for i in range(count)])
    return tables


def resolve(tables, lookup, thin):
    """Python replica of 0x12689C0: (dependency name, package) or (None, 0)."""
    for table in tables:
        for key, name in table:
            if key == thin:
                return name, lookup.get(name, 0)
    return None, 0


def locomotion_tiers(mem, native):
    """The avatar_helldiver locomotion component record: both tier tables (id thin, speed, key)."""
    em = mem.ptr(mem.game + base.G_ENTITY_MANAGER)
    table = mem.ptr(em + 0xF12E30)
    raw = mem.read(table, 0x198 * 16)
    for i in range(0x198):
        resource, index = struct.unpack_from('<QI', raw, 16 * i)
        if resource and native.paths.get(resource, '').endswith('cha_avatar/avatar_helldiver'):
            record = mem.read(table + 0x1980 + index * 0x1210, 0x1210)
            out = {}
            # 0x9CA4EC..0x9CA519: 8 tiers at +8, or 4 tiers at +0x108; the scan stops at the first tier id 0.
            for name, start, limit in (('first(+0x08)', 8, 8), ('second(+0x108)', 0x108, 4)):
                rows = []
                for t in range(limit):
                    tier, speed, key = (struct.unpack_from('<I', record, start + 0x20 * t)[0],
                        struct.unpack_from('<f', record, start + 0x20 * t + 8)[0],
                        struct.unpack_from('<I', record, start + 0x20 * t + 0x18)[0])
                    if not tier:
                        break
                    rows.append({'tier': '%08X' % tier, 'name': native.thin.get(tier), 'speed': round(speed, 4),
                            'key': '%08X' % key if key else None})
                out[name] = rows
            return {'entity': native.paths[resource], 'record': '0x%X' % (table + 0x1980 + index * 0x1210), 'tiers': out}
    return None


def melee_zone_settings(data):
    """Compiled-in ability damage zone settings in game.dll .data that carry the melee key at +0xD4."""
    lo, hi = base.DATA
    rows, at = [], lo
    needle = struct.pack('<I', 0x2559B40D)
    while True:
        at = data.find(needle, at, hi)
        if at < 0:
            return rows
        head = at - 0xD4
        ident, field4, field8, fieldc = struct.unpack_from('<IIII', data, head)
        rows.append({'rva': '0x%X' % head, 'id': '%08X' % ident, '+0x04': field4, '+0x08': field8, '+0x0C': fieldc})
        at += 1


def package_listing(data, package, type_names):
    found = None
    for archive, rname, rtype, main, _stream, _gpu in data.tables():
        if rtype == type_names['package'] and rname == package:
            found = (archive, main)
            break
    if not found:
        return None
    raw = data.read(*found)
    _version, _word, count = struct.unpack_from('<III', raw, 0)
    items = [struct.unpack_from('<QQ', raw, 16 + 16 * i) for i in range(count)]
    names = {v: k for k, v in type_names.items()}
    return {'archive': found[0], 'resources': [{'type': names.get(t, '%016X' % t), 'name': '0x%016X' % n}
        for t, n in items]}


def key_census(name, keys):
    """Every aligned u32 equal to a passive key in the whole snapshot (code immediates, settings, passive rows)."""
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
    wanted = np.array(sorted(keys), dtype='<u4')
    hits = collections.defaultdict(list)
    dll = snap.modules['game.dll']
    for region in snap.regions:
        if region['status'] != 1 or region['size'] < 16:
            continue
        snap.handle.seek(region['data_offset'])
        left, offset = region['size'], 0
        while left > 0:
            size = min(left, 64 << 20)
            blob = snap.handle.read(size)
            arr = np.frombuffer(blob[:len(blob) // 4 * 4], dtype='<u4')
            for i in np.nonzero(np.isin(arr, wanted))[0]:
                address = region['base'] + offset + int(i) * 4
                where = 'game.dll' if dll['base'] <= address < dll['base'] + dll['size'] else 'heap'
                hits[int(arr[i])].append(where)
            offset += size
            left -= size
    snap.close()
    return {'%08X' % k: dict(collections.Counter(hits.get(k, []))) for k in sorted(keys)}


def main():
    scan = '--no-scan' not in sys.argv
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = prove_all(image)
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    code = rpa.Code(image)
    attributes = json.loads(ATTRIBUTES.read_text(encoding='utf-8'))
    passives = {p['id']: p for p in attributes['passiveTable']}
    import research_entity_authoring as rea
    native = rea.Native()

    # Code facts derived (not pinned): callers.
    callers = {name: sorted({'0x%X' % code.function_of(s) for s, _ in code.calls_to(f)}) for name, f in (
        ('passivePackageLoader', 0x874D80), ('resolveDependencyPackage', F_RESOLVE), ('passiveStats', F_PASSIVE_STATS),
        ('statRefresh', 0xA07B10), ('meleeZoneHit', 0x7D01C0), ('locomotionUpdate', 0x9C94C0))}
    get_stat = collections.defaultdict(list)
    for site, _ in code.calls_to(F_GET_STAT):
        function, regs = code.setup(site)
        stat = regs.get('r8d')
        get_stat[str(stat) if isinstance(stat, int) else 'computed: ' + str(stat)].append('0x%X' % function)
    set_stat = []
    for site, _ in code.calls_to(F_SET_STAT):
        function, regs = code.setup(site)
        set_stat.append({'function': '0x%X' % function, 'stat': regs.get('r8d')})
    stat_defaults = [round(v, 4) for v in struct.unpack_from('<20f', data, STAT_DEFAULTS)]

    # Snapshots: the two lookups, the passive keys, the booster keys, residency of the packages.
    loader = rpr.loader_pins(snapshot_image.Snapshot(build_profile.SNAPSHOT))
    boosters = json.loads(BOOSTERS.read_text(encoding='utf-8'))['boosterNames']['names']
    per_snapshot, resolutions = [], {}
    locomotion = None
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        g = mem.game
        lookup, lookup_meta = read_lookup(mem)
        tables = read_dependency_tables(mem)
        mgr = mem.ptr(g + G_CUSTOMIZATION)
        array, count = mem.ptr(mgr + 0x20), mem.u32(mgr + 0x28)
        rows = {}
        for i in range(count):
            p = mem.ptr(array + 8 * i)
            pid, thin = mem.u32(p), mem.u32(p + PACKAGE_FIELD)
            if thin:
                dep, package = resolve(tables, lookup, thin)
                rows[pid] = {'thin': '%08X' % thin, 'dependencyName': '0x%016X' % dep if dep else None,
                    'package': '0x%016X' % package if package else None}
        booster_rows = {}
        for i in range(BOOSTER_ROWS):
            thin = mem.u32(g + G_BOOSTER_ROWS + BOOSTER_STRIDE * i + 0x34)
            if thin:
                dep, package = resolve(tables, lookup, thin)
                booster_rows[boosters[i]] = {'thin': '%08X' % thin, 'dependencyName': '0x%016X' % dep if dep else None,
                    'package': '0x%016X' % package if package else None}
        previous = list(struct.unpack('<8I', mem.read(g + G_PREVIOUS_IDS, 32)))
        if locomotion is None:
            locomotion = locomotion_tiers(mem, native)
        mem.close()
        s = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        resident, refs, _capacity = rpr.residency(s, loader)
        s.close()
        packages = {r['package'] for r in rows.values() if r['package']}
        per_snapshot.append({'snapshot': name, 'hashLookup': lookup_meta,
            'dependencyTables': [{'entries': [['%08X' % k, '0x%016X' % v] for k, v in t]} for t in tables],
            'passivePackages': {str(k): v for k, v in sorted(rows.items())}, 'boosterPackages': booster_rows,
            'loaderPreviousIds': previous,
            'packageState': {p: {'resident': resident.get(int(p, 16)), 'refcount': refs.get(int(p, 16), 0)}
                for p in sorted(packages)}})
        resolutions.setdefault('passives', rows)
        if rows != resolutions['passives']:
            raise ValueError('passive package resolution differs in ' + name)

    # Game data: what the packages hold; every hash_lookup value is a package.
    bundles = gdata.Data()
    type_names = {n.decode(): gdata.murmur64(n) for n in TYPE_NAMES}
    listings = {}
    for pid, row in resolutions['passives'].items():
        listings[row['package']] = package_listing(bundles, int(row['package'], 16), type_names)
    # Names: a hash-list candidate (lead) is used only when it hashes (MurmurHash64A) to the resource id.
    def proven_path(value):
        candidate = native.paths.get(value)
        return candidate if candidate and gdata.murmur64(candidate.encode()) == value else None
    for listing in listings.values():
        for item in listing['resources']:
            item['path'] = proven_path(int(item['name'], 16))
    for row in resolutions['passives'].values():
        row['packagePath'] = proven_path(int(row['package'], 16))
        row['dependencyNamePath'] = proven_path(int(row['dependencyName'], 16))
    mem = base.Mem(SNAPSHOTS[0])
    lookup, _ = read_lookup(mem)
    mem.close()
    package_names = {rname for _a, rname, rtype, *_ in bundles.tables() if rtype == type_names['package']}
    lookup_check = {'entries': len(lookup), 'valuesThatArePackages': sum(1 for v in lookup.values() if v in package_names)}
    thin_halves = {k: {'upper32OfName': '%08X' % (int(v['dependencyName'], 16) >> 32),
        'lower32OfName': '%08X' % (int(v['dependencyName'], 16) & 0xFFFFFFFF)} for k, v in resolutions['passives'].items()}

    census = key_census(SNAPSHOTS[4], {int(k, 16) for k in KEYS}) if scan else None
    if census:
        for key in census:
            needle, at, n = struct.pack('<I', int(key, 16)), 0, 0
            while (at := data.find(needle, at)) >= 0:
                n, at = n + 1, at + 1
            census[key]['gameDllAnyOffset'] = n
            census[key]['passiveRows'] = sum(1 for p in passives.values() for m in p['modifiers'] if m['key'] == key)
    zones = melee_zone_settings(data)

    # The 32-passive table.
    table = []
    counts = collections.Counter()
    for pid in sorted(passives):
        p = passives[pid]
        keys = []
        for m in p['modifiers']:
            key = m['key']
            if key == '00000000':
                mech = ('text only', None, None, 'nothing (STANDARD ISSUE)' if pid == 0 else
                    'the revive mechanism was not located (see verdicts)')
                status = 'none found' if pid else 'no effect'
            else:
                mech = KEYS[key]
                status = mech[0]
            counts[status] += 1
            keys.append({'key': key, 'type': m['type'], 'value': m['value'], 'text': m['text'], 'readerStatus': status,
                'reader': mech[1], 'followsRecordSwap': mech[2], 'observable': mech[3]})
        stats = [{'stat': s[0], 'name': STAT_NAMES.get(s[0]), 'add': s[1], 'mul': s[2],
            'describedBy': STAT_KEY.get(s[0])} for s in p['stats']]
        package = resolutions['passives'].get(pid)
        table.append({'id': pid, 'name': p['name'], 'keys': keys, 'stats': stats,
            'package': package['package'] if package else None,
            'swapCoverage': 'partial' if stats or any(k['followsRecordSwap'] is False for k in keys) else
                'unknown' if any(k['readerStatus'] == NONE for k in keys) else 'full'})

    document = {
        'schemaVersion': 1,
        'build': 'F5FEE03DCFDB',
        'generatedBy': 'scripts/research_passive_effects.py',
        'gameDll': base.PROFILE_DLL_SHA,
        'pins': proofs,
        'pinnedBytesMismatchPerSnapshot': relocation,
        'callers': callers,
        'packageMechanism': {
            'field': 'HelldiverCustomizationPassiveBonusSettings +0x30: u32 thin key (0 = no package)',
            'loader': '0x874D80 (once per world update from 0x571250): after 0x874520 it gathers record +0x3C / +0x38 '
                'of every record into ids[2*playerSlot (+1)], compares with the 8 ids at 0x37CED80, and for every entry '
                'that changed RELEASES the previous passive package (0x12FE4E0) and REQUESTS the new one (0x12FE350), one '
                'id each, on RefcountedPackageSystem 0x347CEB0 - the same request/release functions and instance '
                'core/assets uses. No residency wait: the request only starts the asynchronous load.',
            'resolve': '0x12689C0(out, thin): linear search of the generated_add_resource_dependencies DL instances '
                '(table pointers 0x3799DD0, count 0x348D398; entries {u32 thin, u64 dependency name}) -> 64-bit name; '
                'then the hash_lookup resource map (0x3799810; {u64 name, u64 package}) -> 64-bit package id. Either '
                'miss gives 0 (no load). The thin key is not a half of the 64-bit name.',
            'sameMechanism': 'boosters (0x8568A0): row +0x34 of the 21-row booster table, dependency table 1',
            'thinHalvesCheck': thin_halves,
            'hashLookup': lookup_check,
            'resolved': {str(k): v for k, v in sorted(resolutions['passives'].items())},
            'contents': listings,
        },
        'snapshots': per_snapshot,
        'stats': {
            'component': 'per-entity stat component (manager 0x3326AC0): up to 6 {stat, value} overrides per entity, '
                'defaults f32[20] at 0x2141790',
            'defaults': stat_defaults,
            'passiveStats': '0x11DA190 (from the stat component refresh 0xA07B10, spawn time): for the PENDING armor and '
                'helmet kits, kit +0x1C passive -> stat rows {stat, add, mul}: value = GetStat * prod(mul) + sum(add), '
                'SetStat. The applied record +0x3C is not consulted.',
            'getStatReaders': dict(sorted(get_stat.items())),
            'setStatWriters': set_stat,
            'names': {str(k): v for k, v in STAT_NAMES.items()},
        },
        'dataDriven': {
            'meleeDamageZone': {'reader': '0x7D01C0 (zone hit; owner = [r12])', 'manager': 'component world + 0x7C6098 '
                '(global 0x3326830, physics actor "ability damage zone")', 'keyField': 'zone settings +0xD4',
                'compiledSettingsWithMeleeKey': zones, 'otherKeysInSettings': 'none (game.dll .data holds only 2559B40D)'},
            'locomotion': {'reader': '0x9C94C0', 'keyField': 'speed tier (0x20 bytes) +0x18', 'avatar': locomotion},
        },
        'keyMemoryCensus': {'snapshot': SNAPSHOTS[4], 'counts': census, 'meaning': 'heap / game.dll: aligned u32 '
            'occurrences anywhere in memory (settings, entity data, passive rows, copies); gameDllAnyOffset: '
            'occurrences at any byte offset of the game.dll image (code immediates included). A key with '
            'gameDllAnyOffset 0 and heap == passiveRows exists only in its passive rows: nothing can look it up by '
            'key.'} if census else None,
        'passives': table,
        'readerStatusCounts': dict(counts),
        'verdicts': {
            'packageIdentity': 'derivable: passive 17 -> package 0xC76C97B3DFB67C5C (3 particles, 4 materials, 1 texture, '
                '1 wwise bank: the explosion effect), passive 19 -> package 0x1EEE5C22038560E5 (1 wwise bank '
                'content/audio/passive_armor_constitution). Both are in the bundle database and in no Runtime catalogue. '
                'The package names are not reversed (display names only).',
            'loading': 'catalogue them (generated passive -> package, reviewed) and load through core/assets with '
                'shared=true BEFORE writing the passive; let 0x874D80 add its own reference too. Relying on 0x874D80 '
                'alone leaves the asynchronous load racing the effect and loads on the local peer only.',
            'statDriven': 'reload (13/14/15), ammo capacity (12), sidearm draw (16) and recoil (17) come from the kit '
                'passive stat rows at spawn: a record +0x3C write never changes them; the modifier rows with those keys '
                'are description text only (no code or data holds those keys).',
            'integratedExplosives': '0x822140 applies status effect 66 to the dead avatar when the ARMOR slot (flags 1) '
                'holds 54A69284; the effect assets are the passive package.',
            'adrenoDefibrillator': 'its revive row has key 0 (text only; EntityAttribute key 0 would also match STANDARD '
                'ISSUE); no code reads record +0x3C/+0x38 except EntityAttribute and 0x874D80 and no compare against id '
                '19 was found among the customization users: mechanism not located.',
        },
        'unproven': [
            'live behaviour of everything here (offline only)',
            'what the engine does when the explosion status effect spawns its particles before the package is resident '
            '(crash class per the residency research, not observed)',
            'Adreno-Defibrillator revive mechanism',
            'stat 11 (UNFLINCHING x0.05) and key 0DFF0E42 effects; the names of the passive packages',
            'multiplayer: which peer evaluates the death explosion; peers keep their own applied records',
            'when the capacity readers (grenades, stims) run (spawn or resupply)',
        ],
        'writes': [],
    }
    OUTPUT.write_text(json.dumps(document, indent=1, allow_nan=False) + '\n', encoding='utf-8')
    print('wrote', OUTPUT)
    print('resolved', document['packageMechanism']['resolved'])
    print('reader status counts', dict(counts))


if __name__ == '__main__':
    main()
