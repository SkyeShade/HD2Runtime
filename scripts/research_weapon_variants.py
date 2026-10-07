"""Can a support weapon's OWN type become a custom variant of itself for one mission, with a Runtime-owned model "on the
side" (research/docs/weapon-variants-F5FEE03DCFDB.md)? Read-only, offline.

The expendable clone (scripts/research_carrier_weapon_clone.py) turns an unused weapon type of the donor's component
class into the donor. A weapon whose class has ONE member (the M-1000 Maxigun: WindUp, LinkedAmmo and the ammo chain)
can only ever be carried by itself, so its variant converts its own type, only while nobody in the lobby brings it:
* presentation: EncyclopediaEntry +8 (name), +0x30 (weapon panel image), Spottable +0x38 (marker / prompt icon), the
  clone's three members, from the carrier's own native values;
* round: ProjectileWeapon +0 ProjType := a catalogued attack output of the weapon's own compatibility class (the
  LAS-58 Talon's 144 for the Maxigun's 306);
* model: UnitComponent +0 UnitPath := a Runtime-owned unit resource the mod ships beside the vanilla one (a patch of
  the weapon's own package archive: every dependency co-resident with it, as the vanilla unit's are).

Proves on build F5FEE03DCFDB, from the pinned entity tables, the game.dll image and the installed game data:
1. The host's component class (every support weapon type with its exact component set): the Maxigun alone.
2. Its four written records: one owner each, their index rows and an FNV-1a of their native bytes; the presentation
   members' native bytes; its native ProjType and UnitPath; the marker texture kind.
3. Every consumer of UnitPath (the UnitComponent type table, slot 0xF12738, is read by exactly three instructions: the
   type lookup 0x4F95C0, the default record getter 0x4F9B40 and the delta copy 0x6EAC90; the lookup has 20 call sites in
   19 functions): each either copies the whole record, reads another member (+0x10 Radius, +0x84 the hot-join corpse
   ability) or passes the unit path to an engine unit call (spawn and resource queries, resolved by the resource
   manager by name). None compares it with a constant, keys a table with it or sends it over the network; the one
   114-slot map is read only when an entity has NO UnitComponent. Pinned (call site bytes).
4. The unit's own data (the installed game's archive): its package archive, main and GPU sizes, the material list
   (header +0x70: count, u32 slot ids, u64 materials), the body material and its material LUT texture (23x8
   R16G16B16A16_FLOAT, 5 mips), and which references stay in the same archive (its bones / state machine / physics,
   animations, the body textures) and which are shared (archive 18235e0c9ec0e636: the template material, the shared
   art textures, m_character_shadow, m_collision) - the derived model keeps every one of them.

Output: research/weapon-variants-F5FEE03DCFDB.json. Nothing is written to the game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import pickle
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import hd2_game_data  # noqa: E402
from scan import tables, xref  # noqa: E402
import research_support_item_presentation as presentation  # noqa: E402

OUTPUT = ROOT / 'research/weapon-variants-F5FEE03DCFDB.json'
CACHE = ROOT / 'build/scan-cache/weapon-variants-resources.pkl'
BUILD = 'F5FEE03DCFDB'

HOSTS = {'M-1000 Maxigun': 0x43A58CB89CFA197C}
UNIT_SLOT = 0xF12738
UNIT_LOOKUP = 0x4F95C0
PRESENTATION_MEMBERS = (('EncyclopediaEntryComponentData', 0x8, 4, 'name'),
    ('EncyclopediaEntryComponentData', 0x30, 8, 'image'), ('SpottableComponentData', 0x38, 8, 'icon'))
WRITTEN = ('EncyclopediaEntryComponentData', 'SpottableComponentData', 'UnitComponentData',
    'ProjectileWeaponComponentData')
TYPES = ('unit', 'package', 'bones', 'physics', 'state_machine', 'material', 'texture', 'animation', 'particles',
    'wwise_bank', 'wwise_dep', 'ragdoll_profile')
MATERIALS_AT = 0x70                    # unit header: offset of the material list
LUT_AT = 0x114                         # body material: the material LUT texture reference
TEXTURE_HEADER = 0xC0                  # texture main part: the Stingray header, then the DDS header
SHARED_ARCHIVE = '18235e0c9ec0e636'


def H(name: str) -> int:
    return hd2_game_data.murmur64(name.encode())


def fnv1a(data: bytes) -> str:
    h = 2166136261
    for byte in data:
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return '%08X' % h


def hexid(value: int) -> str:
    return '0x%016X' % value


# ------------------------------------------------------------------------------------------------- the host
def component_class(t: tables.EntityTables, resource: int) -> list[str]:
    """Every support weapon type with exactly the host's component set (the host included), by path."""
    own = set(t.entity(resource))
    out = []
    for other in t.find('equipment/support_weapons/'):
        try:
            if set(t.entity(other)) == own:
                out.append(t.name(other) or hexid(other))
        except KeyError:
            continue
    return sorted(out)


def host_facts(t: tables.EntityTables, name: str, resource: int) -> dict:
    rows = t.entity(resource)
    records = {}
    for component in WRITTEN:
        comp = t.component(component)
        record = rows[component]
        owners = comp.owners(record)
        if owners != [resource]:
            raise ValueError('%s %s is not exclusively owned: %r' % (name, component, owners))
        index_row = next(row for row, res, _rec in comp.rows() if res == resource)
        records[component] = {'indexRow': index_row, 'recordIndex': record, 'ownerCount': 1,
            'fnv1a': fnv1a(comp.raw(record))}

    def member(component, offset, width):
        return t.component(component).raw(rows[component])[offset:offset + width]
    unit = member('UnitComponentData', 0, 8)
    proj = member('ProjectileWeaponComponentData', 0, 4)
    klass = component_class(t, resource)
    return {
        'entity': hexid(resource), 'stratagem': name, 'path': t.name(resource),
        'componentClass': klass, 'pool': [name] if len(klass) == 1 else None,
        'components': sorted(rows),
        'records': records,
        'presentation': [{'component': c, 'offset': o, 'width': w, 'role': role,
            'native': member(c, o, w).hex(), 'donor': member(c, o, w).hex()} for c, o, w, role in PRESENTATION_MEMBERS],
        'markerKind': struct.unpack_from('<I', member('SpottableComponentData', 0x40, 4))[0],
        'projectile': struct.unpack_from('<I', proj)[0],
        'round': {'component': 'ProjectileWeaponComponentData', 'offset': 0, 'width': 4, 'native': proj.hex()},
        'model': {'component': 'UnitComponentData', 'offset': 0, 'width': 8, 'native': unit.hex(),
            'unit': hexid(struct.unpack_from('<Q', unit)[0])},
    }


# ------------------------------------------------------------------------------------------------- consumers
# Every call site of the type lookup, reviewed from its disassembly (scripts/research_weapon_variants.py prints the
# instructions after each call as evidence; the site bytes are pinned): what it does with the returned record.
COPY, RADIUS, CORPSE = 'record copy', 'reads +0x10 Radius only', 'reads +0x84 OnHotjoinCorpseRepairAbilityPatch only'
SPAWN, QUERY = 'UnitPath into the engine unit spawn call [[G]+8]+8', 'UnitPath into the engine unit query [[G]+0x18]+0x700'
ACCESSOR = 'a generic accessor reached only through a function table (no direct callers)'
REVIEWED = {
    0x4F967B: (COPY, 'copies the whole 0x88-byte record into its output'),
    0x4F9784: (COPY, 'copies the whole 0x88-byte record into its output'),
    0x4F99B1: (COPY, 'copies the whole 0x88-byte record into its output'),
    0x4F9C2C: (ACCESSOR, 'tail call: returns the record pointer'),
    0x5B1C7D: (RADIUS, 'min(constant, +0x10) * constant'),
    0x60A6FF: (RADIUS, '+0x10 compared and squared'),
    0x6EAD74: (COPY, 'the entity delta: the whole record (default record when absent) into a per-entity copy'),
    0x7D92F4: (RADIUS, 'min(constant, +0x10) * scale'),
    0x801399: (RADIUS, 'min(constant, +0x10) * scale'),
    0x8025CE: (RADIUS, 'min(constant, +0x10) * scale'),
    0x804229: (RADIUS, 'min(constant, +0x10) * scale'),
    0x87008E: (SPAWN, 'rdx = [record] (UnitPath), then the engine call'),
    0x870A0D: (CORPSE, '+0x84 passed to the ability call 0x11509E0'),
    0x139495F: (ACCESSOR, 'returns UnitPath (else the LocalUnit path through 0x4F3120, else its input)'),
    0x13959FE: (SPAWN, 'UnitPath (else the LocalUnit path) as rdx into the engine call'),
    0x13968F2: (SPAWN, 'UnitPath (else the LocalUnit path) as rdx into the engine call'),
    0x1396C08: (SPAWN, 'UnitPath as is; only without a UnitComponent the 114-slot map (G+0xF12480) supplies one'),
    0x139AACF: (SPAWN, 'UnitPath (else the LocalUnit path) as rdx into the engine call'),
    0x14CB012: (QUERY, 'UnitPath (else the LocalUnit path) as rdx; the call returns a 0x4C-byte record'),
    0x18E9E35: (QUERY, 'UnitPath (else the LocalUnit path) as rdx; the call returns a 0x4C-byte record'),
}


def evidence(image: xref.CodeImage, site: int, count: int = 10) -> list[str]:
    out, rva = [], site
    for _ in range(count):
        ins = image.insn(rva)
        if ins is None:
            break
        out.append('%X: %s %s' % (rva, ins.mnemonic, ins.op_str))
        rva += ins.size
    return out


def consumers(image: xref.CodeImage) -> dict:
    readers = presentation.raw_slot_readers(image, UNIT_SLOT)
    sites = sorted(image.calls_to(UNIT_LOOKUP))
    if set(sites) != set(REVIEWED):
        raise ValueError('the UnitComponent lookup call sites changed: %r' % sorted(set(sites) ^ set(REVIEWED)))
    reader_rvas = sorted(r['rva'] for r in readers)
    if reader_rvas != [0x4F95CF, 0x4F9B47, 0x6EAD85]:
        raise ValueError('the UnitComponent type-table readers changed: %r' % ['0x%X' % r for r in reader_rvas])
    rows = [{'site': '0x%X' % s, 'function': '0x%X' % image.root(s), 'kind': REVIEWED[s][0], 'note': REVIEWED[s][1],
        'asm': evidence(image, s)} for s in sites]
    pins = [image.pin(s, 'UnitComponent type lookup call site') for s in sites]
    for r in readers:
        pins.append(image.pin(r['rva'], 'UnitComponent type-table read'))
    kinds = {}
    for r in rows:
        kinds[r['kind']] = kinds.get(r['kind'], 0) + 1
    return {
        'typeTableSlot': '0x%X' % UNIT_SLOT,
        'typeTableReaders': [{'rva': '0x%X' % r['rva'], 'function': '0x%X' % r['function'], 'asm': r['asm']}
            for r in readers],
        'lookup': '0x%X' % UNIT_LOOKUP, 'callSites': len(sites), 'functions': len({r['function'] for r in rows}),
        'sites': rows, 'byKind': kinds,
        'pins': [{'rva': p['rva'], 'hex': p['bytes'], 'label': p['role']} for p in pins],
        'notes': [
            'no site compares UnitPath with a constant, keys a table with it or serializes it; the one 114-slot map '
            '(0x1396C08) is read only when an entity has NO UnitComponent',
            '0x4F9B40 (the third type-table reader) returns the default record (type table + 0x455B8), never an '
            'entity\'s',
            'the record copies (0x4F9660, 0x4F9760, 0x4F9950, the entity delta 0x6EAC90) carry UnitPath unchanged into '
            'an output or per-entity copy; no mission snapshot holds a UnitComponent copy (carrier-weapon-clone '
            'research)',
            'GAP: the two generic accessors (0x4F9B60, 0x1394950) are reached only through function tables, so their '
            'users are not enumerable statically; the stage C live test covers them',
            'the engine resolves a unit name through its resource manager, the table runtime/image_resources.lua '
            'reads: a resident Runtime-owned unit is found exactly as a vanilla one'],
    }


# ------------------------------------------------------------------------------------------------- the model
def read_model(resource: int) -> dict:
    """The host unit's archive rows and the bytes of the unit, its materials and textures (cached)."""
    key = hashlib.sha256(('%016X|v1' % resource).encode()).hexdigest()
    if CACHE.is_file():
        cached = pickle.loads(CACHE.read_bytes())
        if cached.get('key') == key:
            return cached
    types = {H(n): n for n in TYPES}
    data = hd2_game_data.Data()
    unit_type = H('unit')
    found = data.find({(resource, unit_type)})
    archive = found[(resource, unit_type)][0]
    rows = [r for r in data.tables() if r[0] == archive]
    blobs = {}
    for _a, name, kind, main, stream, gpu in rows:
        label = types.get(kind, '0x%016X' % kind)
        if label in ('unit', 'material', 'texture'):
            blobs[(label, name)] = (data.read(archive, main), data.read(archive, stream, '.stream'),
                data.read(archive, gpu, '.gpu_resources'))
    index = {}
    wanted = set()
    for (label, name), (main, _s, _g) in blobs.items():
        for o in range(0, len(main) - 7, 4):
            wanted.add(struct.unpack_from('<Q', main, o)[0])
    for a, name, kind, *_ in data.tables():
        if name in wanted:
            index.setdefault(name, set()).add((types.get(kind, '0x%016X' % kind), a))
    out = {'key': key, 'archive': archive,
        'rows': [(types.get(k, '0x%016X' % k), n, m[1], s[1], g[1]) for _a, n, k, m, s, g in rows],
        'blobs': blobs, 'index': index}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(out))
    return out


def dds(main: bytes) -> dict:
    if main[TEXTURE_HEADER:TEXTURE_HEADER + 4] != b'DDS ':
        raise ValueError('not a texture with a DDS header at 0xC0')
    d = TEXTURE_HEADER
    height, width = struct.unpack_from('<II', main, d + 12)
    mips = struct.unpack_from('<I', main, d + 28)[0]
    fourcc = main[d + 84:d + 88]
    dxgi = struct.unpack_from('<I', main, d + 128)[0] if fourcc == b'DX10' else None
    return {'width': width, 'height': height, 'mips': mips, 'fourcc': fourcc.decode(), 'dxgi': dxgi}


def model_facts(t: tables.EntityTables, resource: int) -> dict:
    m = read_model(resource)
    blobs, index, archive = m['blobs'], m['index'], m['archive']
    unit = blobs[('unit', resource)][0]
    gpu = blobs[('unit', resource)][2]
    at = struct.unpack_from('<I', unit, MATERIALS_AT)[0]
    count = struct.unpack_from('<I', unit, at)[0]
    slots = struct.unpack_from('<%dI' % count, unit, at + 4)
    materials = struct.unpack_from('<%dQ' % count, unit, at + 4 + 4 * count)
    in_archive = {n for _l, n, *_ in m['rows']}
    mats = []
    body = None
    for k, (slot, mat) in enumerate(zip(slots, materials)):
        where = 'own archive' if mat in in_archive else ('shared archive ' + SHARED_ARCHIVE if any(
            a == SHARED_ARCHIVE for _k, a in index.get(mat, ())) else 'elsewhere')
        entry = {'slot': '0x%08X' % slot, 'slotName': t.thin.get(slot), 'material': hexid(mat),
            'name': t.name(mat), 'at': '0x%X' % (at + 4 + 4 * count + 8 * k), 'where': where}
        mats.append(entry)
        if mat in in_archive and ('material', mat) in blobs and body is None:
            body = (k, mat)
    if body is None:
        raise ValueError('the unit has no material of its own archive')
    k, mat = body
    mbytes = blobs[('material', mat)][0]
    lut = struct.unpack_from('<Q', mbytes, LUT_AT)[0]
    if ('texture', lut) not in blobs:
        raise ValueError('the body material\'s +0x%X is not a texture of the archive' % LUT_AT)
    lmain, lstream, lgpu = blobs[('texture', lut)]
    lut_format = dds(lmain)
    refs = []
    for o in range(0, len(mbytes) - 7, 4):
        v = struct.unpack_from('<Q', mbytes, o)[0]
        if v in index and v != mat:
            kinds = sorted({kk for kk, _a in index[v]})
            archives = sorted({a for _k, a in index[v]})
            refs.append({'at': '0x%X' % o, 'resource': hexid(v), 'kinds': kinds, 'name': t.name(v),
                'where': 'own archive' if v in in_archive else ('shared archive ' + SHARED_ARCHIVE
                    if SHARED_ARCHIVE in archives else 'shared (%d archives)' % len(archives))})
    unit_refs = sorted({'0x%X' % o for o in range(0, 0x30, 8) if struct.unpack_from('<Q', unit, o)[0] == resource})
    if unit_refs != ['0x20', '0x8']:
        raise ValueError('the unit names its own resource at %r' % unit_refs)
    if mbytes.find(struct.pack('<Q', mat)) >= 0:
        raise ValueError('the body material names itself')
    half = lgpu[:lut_format['width'] * lut_format['height'] * 8]
    return {
        'archive': archive, 'package': hexid(int(archive, 16)),
        'resources': len(m['rows']),
        'unit': {'resource': hexid(resource), 'name': t.name(resource), 'main': len(unit), 'gpu': len(gpu),
            'stream': len(blobs[('unit', resource)][1]), 'mainSha256': hashlib.sha256(unit).hexdigest(),
            'gpuSha256': hashlib.sha256(gpu).hexdigest(),
            'ownNameAt': unit_refs, 'materialsAt': '0x%X' % at, 'materials': mats},
        'body': {'slotIndex': k, 'material': hexid(mat), 'main': len(mbytes),
            'mainSha256': hashlib.sha256(mbytes).hexdigest(),
            'template': hexid(struct.unpack_from('<Q', mbytes, 0x18)[0]), 'lutAt': '0x%X' % LUT_AT,
            'references': refs},
        'lut': {'texture': hexid(lut), 'main': len(lmain), 'gpu': len(lgpu), 'stream': len(lstream),
            'format': lut_format, 'mainSha256': hashlib.sha256(lmain).hexdigest(),
            'gpuSha256': hashlib.sha256(lgpu).hexdigest(),
            'rows': lut_format['height'], 'columns': lut_format['width'],
            'baseColour': [[round(struct.unpack_from('<e', half, (r * lut_format['width']) * 8 + 2 * c)[0], 4)
                for c in range(3)] for r in range(lut_format['height'])]},
        'layout': {'archiveAlignment': [16, 64], 'entriesSorted': 'by type hash, then name hash',
            'writer': 'scripts/hd2_archive.py make_resource_archive (no stream parts needed)'},
    }


VERDICTS = {
    'pool': 'the M-1000 Maxigun is the only support weapon with its component set (WeaponWindUp, WeaponLinkedAmmo, '
        'TwoPointChainAttachTarget): its variant can only ever be carried by its own type, so its pool is itself; '
        'a native pick of it in the lobby makes the variant unavailable and, selected, the variant blocks it in the '
        'native picker (the user\'s rule of 2026-10-06: no fallback)',
    'records': 'the four written records each have one owner (the Maxigun): carrier-local under the carrier rule',
    'model': 'every UnitPath consumer copies the record, reads another member, or passes the name to an engine unit '
        'call that resolves it through the resource manager: a resident Runtime-owned unit is found exactly as the '
        'vanilla one; a missing one is refused before any write (the Runtime reads the same resource table)',
    'residency': 'shipped as a patch of the host\'s own package archive, the derived unit, its body material and its '
        'LUT load with that package, beside every vanilla resource they reference (the vanilla unit\'s own pattern)',
    'multiplayer': 'type data is local memory: every machine with the mod converts its own Maxigun type from the '
        'synchronized definition at mission start (as the expendable clone); the model is part of the registry hash, '
        'so a machine without it fails closed (r9)',
    'confidence': 'STRONG (code, data and snapshots); not live: the patch load (stage B) and the write (stage C) are '
        'the live tests',
}
STAGED_TESTS = [
    {'stage': 'A', 'title': 'the variant without a model', 'build': 'presentation + the Talon round on the '
        'Maxigun\'s own type; its own pod (weapon and backpack)', 'liveTest': 'the custom Maxigun fires Talon '
        'shots, shows its name and icon; restored aboard the ship; teammates see the same'},
    {'stage': 'B', 'title': 'the model loads (no write)', 'build': 'the mod ships the derived unit, material and LUT '
        'as a patch of the Maxigun\'s archive; the Runtime only reads whether they are resident',
        'liveTest': 'a mission with the Maxigun package loaded: no crash; MODEL RESIDENT logged'},
    {'stage': 'C', 'title': 'the model write', 'build': 'UnitPath := the derived unit for the mission, guarded by '
        'its residency', 'liveTest': 'the called Maxigun shows the debug palette in first and third person, its '
        'spin-up, belt and backpack link work; restored aboard the ship; a vanilla Maxigun later is vanilla'},
]
OPEN_QUESTIONS = [
    'whether the engine accepts a unit in a non-boot archive patch whose name differs from its bones / state '
    'machine / physics (stage B)',
    'the LUT column semantics beyond base colour (column 0); the debug palette changes only column 0',
    'a mesh of a different shape needs a unit authored in a 3D tool on the Maxigun\'s skeleton (later)',
]


def generate() -> dict:
    t = tables.pinned()
    image = xref.CodeImage.from_snapshot('game.dll')
    hosts = {name: host_facts(t, name, res) for name, res in HOSTS.items()}
    models = {name: model_facts(t, res) for name, res in HOSTS.items()}
    uses = consumers(image)
    return {'build': BUILD, 'writes': 0, 'protectionChanges': 0, 'hosts': hosts, 'models': models,
        'unitPathConsumers': uses, 'verdicts': VERDICTS, 'stagedTests': STAGED_TESTS,
        'openQuestions': OPEN_QUESTIONS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true', help='fail when the output is not current')
    args = parser.parse_args(argv)
    result = generate()
    text = json.dumps(result, indent=1) + '\n'
    if args.check:
        if OUTPUT.read_text(encoding='utf-8') != text:
            raise SystemExit(str(OUTPUT.relative_to(ROOT)) + ' is not current')
        return
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    u = result['unitPathConsumers']
    print('wrote', OUTPUT.relative_to(ROOT), '; hosts', list(result['hosts']), '; class',
        result['hosts']['M-1000 Maxigun']['componentClass'], '; consumers', u['callSites'], u['byKind'])


if __name__ == '__main__':
    main()
