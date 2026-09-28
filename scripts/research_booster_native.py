"""Trace Booster implementation through the unpacked game.dll image. Read-only; nothing writes.

The on-disk game.dll is packed; the retained snapshot holds the unpacked image the game runs.
This script re-derives, from that image and the pinned type library:

* Identity: game.dll's own enum-name table for `Booster` ([None, ..., Count], indexed by
  value) and for `StratagemType`. Every entry must match the type library's hidden alias
  length, so all 20 boosters resolve to one enum value each.
* The generic booster system: `IsBoosterActive(booster)` and every call site with its
  literal booster argument, plus the native Booster definition table in game.dll .data
  (one 0x38-byte row per enum value; tuning scalar at +8, granted stratagem type at +4).
* Every code reference into that table, decoded and classified (reads only; no stores).
* Code-selected settings rows (hellpod-impact explosions, stim status, Dead Sprint status),
  checked against every decoded data carrier of ExplosionType / StatusEffectType.

Every writable relationship is pinned as exact instruction bytes at exact RVAs so the
runtime can re-prove it live. Requires the research-only packages capstone and numpy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

try:
    import capstone
    import numpy
except ImportError as error:  # research dependency only; never needed at runtime or in tests
    raise SystemExit('research_booster_native requires capstone and numpy: ' + str(error))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_booster_authoring as booster_research
import research_entity_authoring as entity_research
import snapshot_image
import snapshot_regions

OUTPUT = ROOT / 'research/booster-native-F5FEE03DCFDB.json'
PROFILE_DLL_SHA = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
IMAGE_SIZE = 0x4744000
TEXT = (0x1000, 0x1000 + 0x210FA93)
DATA = (0x263C000, 0x263C000 + 0x119B5FC)
# Reviewed anchors, each re-proven below from structure (not trusted by address alone).
BOOSTER_NAMES_RVA = 0x21DD630          # const char *[22] {None, ..., Count}
STRATAGEM_NAMES_RVA = 0x21D4AA0        # const char *[151] {None, ..., Count}
IS_BOOSTER_ACTIVE_RVA = 0x856D40       # bool IsBoosterActive(<this unused>, Booster edx)
TABLE_RVA, TABLE_STRIDE, TABLE_ROWS = 0x32FDA90, 0x38, 21
TABLE_BOUND_RVA = 0x11F860E            # cmp edi, 0x15 in the table walker
GRANT_RVA = 0x857007                   # table[booster].+4 -> StratagemSettings[type].+0x50 grant
STRATAGEM_TABLE_RVA = 0x37CB600        # runtime StratagemSettings pointer table (profile.table_rva)
HELLPOD_IMPACT = {'FieryDrop': (0x92C0E1, 0x92C102, 83), 'ShockPods': (0x92C163, 0x92C191, 335),
    'SmokePods': (0x92C1E7, 0x92C215, 400)}
STATUS_LINKS = {'CombatDrugs': (0x11C9A11, 0x11C9A7B, 29), 'DeathMarch': (0x0A8B4FF, 0x0A8B5AA, 59)}

# Consumer semantics are read off the decoded instruction sequence at each site (see
# docs/booster-authoring.md). Keys are native member names.
SEMANTICS = {
    'Vitality': ('booster.damage_taken_scale', 'Incoming damage to a Helldiver is multiplied by the value '
        'and truncated to an integer (int(damage * value)).'),
    'Stamina': ('booster.stamina_scale', 'Multiplies the stamina efficiency factor; sprint stamina drain '
        'is divided by it and the regeneration input is multiplied by it.'),
    'MuscleEnhancement': ('booster.terrain_slowdown_scale', 'Multiplies the terrain slowdown fraction; '
        'movement factor becomes 1 - slowdown * value.'),
    'UAVRecon': ('booster.radar_range_scale', 'Multiplies the radar scan scale (base 0.025).'),
    'IncreasedReinforcementBudget': ('booster.reinforcements_per_player', 'Added to each player\'s '
        'reinforcement budget and truncated to an integer when the budget is initialised.'),
    'FlexibleReinforcementBudget': ('booster.reinforcement_cooldown_scale', 'Multiplies the reinforcement '
        'refill cooldown read from the mission settings before it is scheduled.'),
    'LocalizationConfusion': ('booster.encounter_rate_scale', 'Multiplies the encounter spawn rate; the two '
        'encounter/reinforcement timers are divided by it.'),
    'FastExtraction': ('booster.extraction_time_scale', 'Multiplies the call-in time of the Extract '
        'stratagem (StratagemType 148).'),
    'SlowStunResistance': ('booster.slow_scale', 'Multiplies the slow/stun amount applied to a Helldiver.'),
    'DoubleSampleChance': ('booster.double_sample_chance', 'Probability that a picked-up sample counts twice.'),
    'DeathMarch': ('booster.health_floor', 'Health fraction below which Dead Sprint stops draining health '
        'and stops allowing exhausted sprinting.'),
    'BigEnemiesDropSamples': ('booster.sample_drop_cap', 'Mission cap on samples dropped by large enemies '
        '(truncated to an integer).'),
    'FireExtinguish': ('booster.burn_decay_bonus', 'Burn decay is multiplied by 1 / (1 - value) while the '
        'booster is active; values at or above 1 divide by zero.'),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def hexbytes(data: bytes) -> str:
    return data.hex()


class Image:
    def __init__(self, data: bytes, base: int):
        self.data, self.base = data, base
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True

    def u32(self, rva):
        return struct.unpack_from('<I', self.data, rva)[0]

    def f32(self, rva):
        return struct.unpack_from('<f', self.data, rva)[0]

    def cstr(self, rva):
        return self.data[rva:self.data.index(b'\0', rva)].decode('latin-1')

    def pointer_rva(self, rva):
        pointer = struct.unpack_from('<Q', self.data, rva)[0]
        if not self.base <= pointer < self.base + len(self.data):
            raise ValueError('pointer outside game.dll at %x' % rva)
        return pointer - self.base

    def insn(self, rva):
        found = next(self.md.disasm(self.data[rva:rva + 16], rva), None)
        if found is None:
            raise ValueError('undecodable instruction at %x' % rva)
        return found

    def rip_target(self, insn):
        for op in insn.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
                return insn.address + insn.size + op.mem.disp
        return None

    def proof(self, rva, role):
        insn = self.insn(rva)
        return {'rva': rva, 'bytes': hexbytes(self.data[rva:rva + insn.size]), 'role': role,
            'asm': insn.mnemonic + ' ' + insn.op_str}


def enum_table(image, rva, count, lengths, prefix):
    names = [image.cstr(image.pointer_rva(rva + 8 * index)) for index in range(count)]
    if names[0] != 'None' or names[-1] not in ('Count', 'COUNT'):
        raise ValueError(prefix + ' name table framing changed')
    mismatches = [v for v, name in enumerate(names) if len(prefix + '_' + name) != lengths[v]]
    if len(names) != len(lengths) or mismatches:
        raise ValueError(prefix + ' name table disagrees with type-library alias lengths: ' + str(mismatches))
    return names


CALLEES = {'explosion': (0x13C0A80,), 'status': (0xBEBDE0, 0x699E40, 0x69B1F0, 0x69AEC0)}


def callee_literals(sweep, callees, kind):
    """Call sites of the given functions whose r8d argument resolves to `kind`, plus the count of
    call sites whose argument is dynamic (data-driven)."""
    names = {'call 0x%x' % callee for callee in callees}
    found, dynamic, total = [], 0, 0
    for i, (rva, _, mnemonic, operands) in enumerate(sweep):
        if mnemonic + ' ' + operands not in names:
            continue
        total += 1
        known = {}
        for j in range(max(0, i - 40), i):
            m, o = sweep[j][2], sweep[j][3]
            if m in ('call', 'jmp') or m.startswith('j'):
                known = {}
                continue
            zero = re.fullmatch(r'(\w+), \1', o)
            if m == 'xor' and zero:
                known[zero.group(1)] = 0
                continue
            literal = re.fullmatch(r'(\w+), (0x[0-9a-f]+|\d+)', o)
            if m == 'mov' and literal:
                known[literal.group(1)] = int(literal.group(2), 0)
                continue
            offset = re.fullmatch(r'(\w+), \[(\w+) \+ (0x[0-9a-f]+|\d+)\]', o)
            if m == 'lea' and offset:
                register = offset.group(2)
                base = known.get(register)
                if base is None and register.startswith('r') and register[1:].isdigit():
                    base = known.get(register + 'd')
                if base is None and register.startswith('r') and register[1:].isalpha():
                    base = known.get('e' + register[1:])
                known[offset.group(1)] = None if base is None else base + int(offset.group(3), 0)
                continue
            dest = re.match(r'(\w+),', o)
            if dest:
                known[dest.group(1)] = None
        value = known.get('r8d')
        if value is None:
            dynamic += 1
        elif value == kind:
            found.append(rva)
    return {'calls': total, 'dynamicOrBranchedArgumentCalls': dynamic, 'literalCallSites': found}


def carrier_scan(native, explosion_types, status_types):
    """Every decoded data carrier of ExplosionType / StatusEffectType, scanned for the given types.
    Offsets come from the pinned type library (record types of each component table)."""
    hits = {'explosion': [], 'status': []}

    def component(name, members, want, family):
        count = native.table(name)[4]
        for index in range(count):
            record = native.record(name, index)
            for offset, elements, stride in members:
                for k in range(max(elements, 1)):
                    if struct.unpack_from('<I', record, offset + k * stride)[0] in want:
                        hits[family].append({'carrier': name, 'record': index, 'offset': offset + k * stride})

    for name, members in {'ExplosiveComponentData': [(36, 0, 0), (40, 0, 0)],
            'BackblastComponentData': [(8, 0, 0)], 'MinefieldComponentData': [(24, 0, 0)],
            'ProjectileClusterComponentData': [(4, 0, 0)], 'WeaponChargeComponentData': [(200, 0, 0)],
            'DisplacementComponentData': [(56, 0, 0)], 'RagdollSyncComponentData': [(24, 15, 112)],
            'VehicleCrashComponentData': [(24, 15, 112)], 'GibEntityComponentData': [(24, 0, 0)]}.items():
        component(name, members, explosion_types, 'explosion')
    for name, members in {'StratagemScramblerComponentData': [(24, 0, 0)],
            'EnvironmentalEffectTagComponentData': [(4, 0, 0)], 'VehicleComponentData': [(3616, 8, 4)],
            'ShieldComponentData': [(108, 0, 0)], 'DisplacementComponentData': [(180, 12, 24)],
            'WeaponHeatComponentData': [(20, 3, 24)]}.items():
        component(name, members, status_types, 'status')
    _, projectile = snapshot_regions.region_bytes('projectile')
    for row in range(350):
        for offset in (144, 156):
            if struct.unpack_from('<I', projectile, 44 + row * 272 + offset)[0] in explosion_types:
                hits['explosion'].append({'carrier': 'ProjectileSettings', 'record': row, 'offset': offset})
    _, beam = snapshot_regions.region_bytes('beam')
    for row in range(30):
        if struct.unpack_from('<I', beam, 44 + row * 112 + 96)[0] in explosion_types:
            hits['explosion'].append({'carrier': 'BeamSettings', 'record': row, 'offset': 96})
    _, damage = snapshot_regions.region_bytes('damage')
    for row in range(649):
        for offset in (44, 52, 60, 68):
            if struct.unpack_from('<I', damage, 100 + row * 76 + offset)[0] in status_types:
                hits['status'].append({'carrier': 'DamageInfo', 'record': row, 'offset': offset})
    _, status = snapshot_regions.region_bytes('status')
    templates = status[11916:]
    for row in range(struct.unpack_from('<I', templates, 32)[0]):
        for k in range(4):
            if struct.unpack_from('<i', templates, 40 + row * 40 + 4 + k * 8)[0] in status_types:
                hits['status'].append({'carrier': 'StatusEffectTemplate', 'record': row, 'offset': 4 + k * 8})
    return {'explosionCarriers': 11, 'statusCarriers': 8, 'hits': hits,
        'notDecoded': ['DestructionEffect (a union inside the destruction settings library)']}


def linear_sweep(image):
    """Every decoded .text instruction as (rva, size, mnemonic, operands)."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.skipdata = True
    return list(md.disasm_lite(image.data[TEXT[0]:TEXT[1]], TEXT[0]))


def main():
    native = entity_research.Native()
    library = booster_research.TypeLibrary(native.typelib, native.probe)
    snap = snapshot_image.Snapshot(snapshot_regions.SNAPSHOT)
    if snap.game_dll_sha256 != PROFILE_DLL_SHA:
        raise ValueError('snapshot game.dll fingerprint differs from the pinned profile')
    base, data = snap.module_image('game.dll')
    snap.close()
    image = Image(data, base)
    if struct.unpack_from('<I', data, struct.unpack_from('<I', data, 60)[0] + 80)[0] != IMAGE_SIZE:
        raise ValueError('game.dll SizeOfImage changed')

    # Identity: the game's own enum-name tables, validated against the type library.
    booster_lengths = library.lengths('Booster')
    names = enum_table(image, BOOSTER_NAMES_RVA, 22, booster_lengths, 'Booster')
    stratagem_names = enum_table(image, STRATAGEM_NAMES_RVA, 151, library.lengths('StratagemType'),
        'StratagemType')
    name_strings = [image.pointer_rva(BOOSTER_NAMES_RVA + 8 * index) for index in range(22)]

    # The native Booster definition table (static .data, one row per enum value).
    bound = image.insn(TABLE_BOUND_RVA)
    if (bound.mnemonic, bound.op_str) != ('cmp', 'edi, 0x15'):
        raise ValueError('booster table walker bound changed')
    rows = []
    for index in range(TABLE_ROWS):
        at = TABLE_RVA + index * TABLE_STRIDE
        raw = data[at:at + TABLE_STRIDE]
        rows.append({'value': index, 'nativeName': names[index], 'rowRva': at, 'bytes': hexbytes(raw),
            'id': struct.unpack_from('<I', raw, 0)[0], 'grantedStratagemType': struct.unpack_from('<I', raw, 4)[0],
            'scalar': round(struct.unpack_from('<f', raw, 8)[0], 6), 'enabled': raw[12],
            'displayKind': struct.unpack_from('<I', raw, 0x30)[0], 'resourceThinHash': struct.unpack_from('<I', raw, 0x34)[0]})

    sweep = linear_sweep(image)
    index_by_rva = {rva: i for i, (rva, _, _, _) in enumerate(sweep)}
    rip = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')

    # IsBoosterActive: every direct call site and its literal booster argument.
    gate_function = hexbytes(data[IS_BOOSTER_ACTIVE_RVA:IS_BOOSTER_ACTIVE_RVA + 0x66])
    calls = []
    target = 'call 0x%x' % IS_BOOSTER_ACTIVE_RVA
    for i, (rva, size, mnemonic, operands) in enumerate(sweep):
        if mnemonic + ' ' + operands != target:
            continue
        argument = None
        for back in range(1, 25):
            _, _, m, o = sweep[i - back]
            literal = re.fullmatch(r'edx, (0x[0-9a-f]+|\d+)', o)
            if m == 'mov' and literal:
                argument = int(literal.group(1), 0)
                break
            if re.match(r'(e|r)dx\b', o) or m == 'call':
                argument = m + ' ' + o
                break
        calls.append({'rva': rva, 'booster': argument if isinstance(argument, int) else None,
            'dynamicArgument': None if isinstance(argument, int) else argument})

    # Every RIP-relative reference into the booster table, classified.
    references = []
    end = TABLE_RVA + TABLE_ROWS * TABLE_STRIDE
    for i, (rva, size, mnemonic, operands) in enumerate(sweep):
        match = rip.search(operands)
        if not match:
            continue
        address = rva + size + int(match.group(2), 16) * (1 if match.group(1) == '+' else -1)
        if not TABLE_RVA <= address < end:
            continue
        row, offset = divmod(address - TABLE_RVA, TABLE_STRIDE)
        destination = operands.split(',')[0]
        store = 'ptr [rip' in destination and mnemonic not in ('cmp', 'test', 'comiss', 'ucomiss')
        references.append({'rva': rva, 'asm': mnemonic + ' ' + operands, 'row': row, 'offset': offset,
            'kind': 'store' if store else ('address' if mnemonic == 'lea' else 'load')})
    if any(item['kind'] == 'store' for item in references):
        raise ValueError('booster table has a direct store; it is not static')

    def gate_before(rva, booster, limit=60):
        i = index_by_rva[rva]
        for back in range(1, limit):
            prior = sweep[i - back]
            if prior[2] in ('int3', 'ret'):
                return None
            if prior[2] + ' ' + prior[3] == target:
                literal = hex(booster) if booster > 9 else str(booster)
                for k in range(1, 25):
                    m, o = sweep[i - back - k][2], sweep[i - back - k][3]
                    if m == 'mov' and o == 'edx, ' + literal:
                        return [sweep[i - back - k][0]], prior[0]
                    register = re.fullmatch(r'edx, (r\d+d|e[a-z]{2})', o)
                    if m == 'mov' and register:
                        # Argument passed through a register loaded with the literal earlier.
                        for j in range(k + 1, 60):
                            mm, oo = sweep[i - back - j][2], sweep[i - back - j][3]
                            if mm in ('int3', 'ret'):
                                return None
                            if mm == 'mov' and oo == register.group(1) + ', ' + literal:
                                return [sweep[i - back - j][0], sweep[i - back - k][0]], prior[0]
                        return None
                return None
        return None

    # Tuning scalars: every +8 load, attributed to the gate that guards it.
    tuning = {}
    for item in references:
        if item['kind'] != 'load' or item['offset'] != 8:
            continue
        name = names[item['row']]
        gate = gate_before(item['rva'], item['row'])
        entry = tuning.setdefault(name, {'value': item['row'], 'readers': [], 'gates': [], 'ungatedReaders': []})
        if not gate and name != 'SlowStunResistance':
            # A standalone getter (no gate in its function); recorded, not used as proof.
            entry['ungatedReaders'].append(image.proof(item['rva'], 'getter'))
            continue
        entry['readers'].append(image.proof(item['rva'], 'reader'))
        if gate:
            entry['gates'].append({'mov': [image.proof(rva, 'gate_argument') for rva in gate[0]],
                'call': image.proof(gate[1], 'gate_call')})
    # Motivational Shocks' reader sits behind a second check on the same path as its gate.
    shocks = tuning.get('SlowStunResistance')
    if shocks and not shocks['gates']:
        shocks['gates'].append({'mov': [image.proof(0x69A323, 'gate_argument')],
            'call': image.proof(0x69A328, 'gate_call')})
    for name, entry in tuning.items():
        if not entry['gates']:
            raise ValueError('table reader without a proven booster gate: ' + name)
        row = rows[entry['value']]
        entry['baseline'] = row['scalar']
        entry['semanticFieldId'], entry['effect'] = SEMANTICS[name]
        for reader in entry['readers']:
            insn = image.insn(reader['rva'])
            if image.rip_target(insn) != row['rowRva'] + 8:
                raise ValueError('reader does not resolve to the row scalar: ' + name)

    # Granted stratagem: table[booster].+4 -> StratagemSettings[type].+0x50 (use count).
    grant = [image.proof(rva, 'grant') for rva in (0x857007, 0x857017, 0x85701B, 0x85702B, 0x85706E,
        0x85707E, 0x857085, 0x857089)]
    if image.rip_target(image.insn(0x85707E)) != STRATAGEM_TABLE_RVA:
        raise ValueError('grant path no longer indexes the StratagemSettings runtime table')
    granted = [row for row in rows if row['grantedStratagemType']]

    # Code-selected settings rows.
    selectors = {}
    for name, (gate_rva, select_rva, kind) in {**HELLPOD_IMPACT, **STATUS_LINKS}.items():
        selectors[name] = {'value': names.index(name), 'nativeType': kind,
            'family': 'explosion' if name in HELLPOD_IMPACT else 'status',
            'gate': [image.proof(gate_rva, 'gate_argument'), image.proof(image.insn(gate_rva).address
                + image.insn(gate_rva).size, 'gate_call')],
            'selector': image.proof(select_rva, 'selector')}

    # Every call to the explosion-spawn and status-apply functions, with its literal type.
    literal_sites = {name: callee_literals(sweep, CALLEES[info['family']], info['nativeType'])
        for name, info in selectors.items()}
    carriers = carrier_scan(native, {info['nativeType'] for info in selectors.values()
        if info['family'] == 'explosion'}, {info['nativeType'] for info in selectors.values()
        if info['family'] == 'status'})

    # The settings rows and stratagem record these links select, through the production parsers.
    explosion_types = sorted(info['nativeType'] for info in selectors.values() if info['family'] == 'explosion')
    status_types = sorted(info['nativeType'] for info in selectors.values() if info['family'] == 'status')
    live = json.loads(snapshot_regions.run_lua(r'''
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local b=require('hd2runtime/core/bytes')
local stratagem=require('hd2runtime/core/stratagem')
local reader=Reader.new(source)
local roots=discover.locate(source,reader,profile,{explosion=true,damage=true,status=true})
local function hex(s)return (s:gsub('.',function(c)return string.format('%02x',c:byte())end))end
local function row(key,kind)
 local r=assert(roots[key].records[kind],key..' '..kind..' absent')
 return {kind=kind,group=r.group,row=r.row,offset=r.offset,bytes=hex(r.bytes)}
end
local out={explosion={},damage={},status={},stratagem={}}
for _,kind in ipairs({''' + ','.join(map(str, explosion_types)) + r'''})do
 local e=row('explosion',kind);out.explosion[#out.explosion+1]=e
 local d=b.u32(roots.explosion.records[kind].bytes,4)
 if d~=0 then out.damage[#out.damage+1]=row('damage',d)end
end
for _,kind in ipairs({''' + ','.join(map(str, status_types)) + r'''})do
 out.status[#out.status+1]=row('status',kind)
 local d=b.u32(roots.status.records[kind].bytes,44)
 if d~=0 then out.damage[#out.damage+1]=row('damage',d)end
end
local records=stratagem.capture_all(source,reader,profile)
for _,r in ipairs(records)do if r.record_kind==''' + str(granted[0]['grantedStratagemType']) + r''' then
 out.stratagem[#out.stratagem+1]={kind=r.record_kind,id=r.id,group=r.group,row=r.row,offset=r.offset,
  package=r.package,payloads=r.payloads,use_count=r.use_count,cooldown=r.cooldown,cooldown_type=r.cooldown_type,
  has_shared_uses_pool=r.has_shared_uses_pool}
end end
return require('hd2runtime/primary_mapper/json').encode(out)
''').decode())
    if len(granted) != 1 or len(live['stratagem']) != 1:
        raise ValueError('granted stratagem link is not unique')

    report = {'schemaVersion': 1, 'sourceSnapshot': snapshot_regions.SNAPSHOT.name,
        'gameDll': {'sha256': PROFILE_DLL_SHA, 'imageSize': IMAGE_SIZE, 'unpackedImageSha256': sha(data),
            'textSha256': sha(data[TEXT[0]:TEXT[1]])},
        'pinnedReferences': {'typelib': sha(native.typelib)},
        'boosterNames': {'rva': BOOSTER_NAMES_RVA, 'names': names, 'stringRvas': name_strings,
            'typeLibraryAliasLengths': booster_lengths},
        'stratagemTypeNames': {'rva': STRATAGEM_NAMES_RVA, 'count': len(stratagem_names),
            'LATOneshot_Booster': stratagem_names.index('LATOneshot_Booster'), 'Extract': stratagem_names.index('Extract'),
            'AmmoRack': stratagem_names.index('AmmoRack')},
        'isBoosterActive': {'rva': IS_BOOSTER_ACTIVE_RVA, 'bytes': gate_function, 'calls': calls},
        'boosterTable': {'rva': TABLE_RVA, 'stride': TABLE_STRIDE, 'rows': rows,
            'bound': image.proof(TABLE_BOUND_RVA, 'row_bound'), 'references': references,
            'directStores': 0},
        'tuning': tuning, 'grant': {'proof': grant, 'stratagemTableRva': STRATAGEM_TABLE_RVA,
            'granted': [{'booster': r['nativeName'], 'value': r['value'], 'stratagemType': r['grantedStratagemType'],
                'stratagemTypeName': stratagem_names[r['grantedStratagemType']]} for r in granted]},
        'selectors': selectors, 'literalSelectorSites': literal_sites, 'dataCarriers': carriers,
        'settingsRows': {'explosion': live['explosion'], 'damage': live['damage'], 'status': live['status']},
        'grantedStratagemRecord': live['stratagem'][0],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'names': names[1:21], 'calls': len(calls),
        'tuning': {k: (v['baseline'], len(v['readers']), len(v['gates'])) for k, v in tuning.items()},
        'granted': report['grant']['granted'], 'literalSelectorSites': literal_sites}, indent=1))


if __name__ == '__main__':
    main()
