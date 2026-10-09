"""Where the game reads each entity component table from, and whether that is the table HD2Runtime writes
(research/docs/entity-component-table-pointers.md). Read-only, offline: the game.dll image and every retained snapshot
of build F5FEE03DCFDB. Nothing is written.

The report behind it: "editing the Heat Per Shot and Cool Per Sec for the LAS-12 Sai has no effect". A third-party mod
(True Lasgun Beam Overhaul) repoints the entity manager's per-component table pointers of BeamWeapon, WeaponHeat and
WeaponMagazine to private copies. The mod is a LEAD only (where to look); everything below is proven from game code
and snapshot data.

Proves:

1. The global. The entity manager constructor 0xFDA190 stores `this` in [game.dll + 0x346BF98] (0xFDA356); the entity
   file loader 0xFDB440 runs on that manager (its only callers: 0xAE0D84 lea rcx, [r9 + 0xE49F0], and the reload
   0xFDB860 on its own argument).
2. The layout. The loader reads each component table's index from the file framing (the u32 before the table's DL
   frame, 0xFDB5D0), loads the table in place and stores the table's data address (frame + 0x18, 0xFDB798, i.e. the
   entity-allocation offset HD2Runtime's profile names + 28) in manager + 0xF12478 + 8 x index (0xFDB636): one
   8-byte pointer per component type, indexed by the component index.
3. The readers. Every code reference to a profile component's slot (a [reg + slot] operand anywhere in .text, leaf
   functions included) is listed and classified: the type lookup (manager loaded from the global, the slot read, the
   capacity as the hash modulus, record = table + record_offset + stride x index), the default-record fallback, or
   other. The game reads the records ONLY through the slot: no code holds a second copy of the table address.
4. The snapshots. In every retained snapshot, for every component in schemas/current.lua: [[game + 0x346BF98] +
   0xF12478 + 8 x index] == the production-located entity allocation + profile offset + 28, the exact table
   core/entity_catalog.lua reads and the write domains write.

Output: research/entity-component-table-pointers-F5FEE03DCFDB.json. `--check` compares with the committed output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from capstone import x86  # noqa: E402

import build_profile  # noqa: E402
import snapshot_image  # noqa: E402
import snapshot_regions  # noqa: E402
from scan import xref  # noqa: E402

OUTPUT = ROOT / 'research/entity-component-table-pointers-F5FEE03DCFDB.json'
BUILD = 'F5FEE03DCFDB'
ENTITY_MANAGER = 0x346BF98      # [game.dll + this] = entity manager
SLOT_BASE = 0xF12478            # manager + SLOT_BASE + 8 x component index = that component's table
TABLE_FROM_FRAME = 0x18         # table = DL frame ('LDLD' magic) + 0x18 = profile offset + 28
PROFILE_TO_TABLE = 28
GAME_GLOBAL = 0x3326340         # [game.dll + this] = the Game object (research event-state); manager = Game + 0xE49F0
GLOBAL_PINS = [
    (0xFDA356, 'mov qword ptr [rip + 0x2491c3b], rbx',
     'entity manager constructor 0xFDA190 stores this in the global [game.dll + 0x346BF98]'),
    (0xAE0D84, 'lea rcx, [r9 + 0xe49f0]', 'the loader runs on the entity manager (Game + 0xE49F0)'),
    (0xAE0D8B, 'call 0xfdb440', 'entity file loader 0xFDB440'),
    (0xFDB456, 'mov r13, rcx', 'loader: r13 = the entity manager'),
    (0xFDB5D0, 'mov r12d, dword ptr [rbx + r15]', 'loader: the component index, from the u32 before the DL frame'),
    (0xFDB5F2, 'cmp eax, 0x444c444c', 'loader: the DL frame magic (LDLD)'),
    (0xFDB798, 'lea r14, [rsi + 0x18]', 'loader: the table = DL frame + 0x18 (profile offset + 28)'),
    (0xFDB636, 'mov qword ptr [r13 + r12*8 + 0xf12478], r14',
     'loader: manager + 0xF12478 + 8 x index := the table (one pointer per component type)'),
]


def hx(value: int) -> str:
    return '0x%X' % value


def profile_components() -> dict:
    """schemas/current.lua components through the production Lua (no hand parsing)."""
    raw = snapshot_regions.run_lua(r'''
local json=require('hd2runtime/primary_mapper/json')
local out={}
for name,c in pairs(profile.components)do
 out[name]={offset=c.offset,index=c.index,indices=c.indices,records=c.records,record_offset=c.record_offset,
  stride=c.stride,type=c.type,header=c.header}
end
return json.encode({components=out,exe=profile.exe_sha,dll=profile.dll_sha,entity_size=profile.entity_size})
''')
    return json.loads(raw)


def snapshot_entity_base(path: Path) -> int:
    """The entity allocation base as runtime/discover.lua locates it (the owner core/entity_catalog.lua reads)."""
    raw = snapshot_regions.run_lua(r'''
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local reader=Reader.new(source)
local roots=discover.locate(source,reader,profile,{entity=true})
local owner=roots.entity.owner or roots.entity
return string.format('%.0f',owner.base)
''', snapshot=path)
    return int(raw.decode())


# ------------------------------------------------------------------------------------------------ code
def _insn(img: xref.CodeImage, rva: int):
    try:
        return img.insn(rva)
    except ValueError:
        return None


def slot_sites(img: xref.CodeImage, disp: int) -> list:
    """Every instruction in .text whose memory operand displacement is `disp` (leaf functions included: a raw byte
    scan, each hit re-decoded from every possible instruction start that covers it)."""
    lo, hi = img.text
    needle = struct.pack('<I', disp)
    found = {}
    at = img.data.find(needle, lo, hi)
    while at >= 0:
        for start in range(at - 7, at):
            ins = _insn(img, start)
            if ins is None or start + ins.size < at + 4 or start + ins.size > at + 8:
                continue
            if any(op.type == x86.X86_OP_MEM and op.mem.disp == disp and op.mem.base != x86.X86_REG_RIP
                   for op in ins.operands):
                found[start] = ins
                break
        at = img.data.find(needle, at + 1, hi)
    return [found[a] for a in sorted(found)]


def global_load(img: xref.CodeImage, site) -> dict | None:
    """The `mov reg, [rip -> 0x346BF98]` that loads the site's base register (searched in linear decodes that land
    exactly on the site; the register must not be written in between)."""
    mem = next(op for op in site.operands if op.type == x86.X86_OP_MEM)
    base = mem.mem.base
    root = img.root(site.address)
    starts = ([root] if root is not None and site.address - root < 0x4000 else []) +         list(range(site.address - 0x80, site.address))
    for start in starts:
        seq, at = [], start
        while at < site.address:
            ins = _insn(img, at)
            if ins is None:
                break
            seq.append(ins)
            at += ins.size
        if at != site.address:
            continue
        for k in range(len(seq) - 1, -1, -1):
            ins = seq[k]
            if ins.mnemonic == 'mov' and len(ins.operands) == 2 and ins.operands[0].type == x86.X86_OP_REG \
                    and ins.operands[0].reg == base and img.rip_target(ins) == ENTITY_MANAGER:
                return {'rva': ins.address, 'asm': ins.mnemonic + ' ' + ins.op_str}
            written = {_canonical(ins.reg_name(r)) for r in ins.regs_access()[1]}
            if _canonical(ins.reg_name(base)) in written:
                break
    return None


_LEGACY = {'a': 'rax', 'b': 'rbx', 'c': 'rcx', 'd': 'rdx'}


def _canonical(name: str) -> str:
    """The 64-bit register a (sub)register belongs to."""
    name = name.lower()
    if name.startswith('r') and name[1:2].isdigit():
        return name.rstrip('dwb')
    for short, full in (('si', 'rsi'), ('di', 'rdi'), ('bp', 'rbp'), ('sp', 'rsp')):
        if short in name:
            return full
    for letter, full in _LEGACY.items():
        if name in ('r' + letter + 'x', 'e' + letter + 'x', letter + 'x', letter + 'l', letter + 'h'):
            return full
    return name


def classify(img: xref.CodeImage, site, c: dict) -> dict:
    seq = img.disasm(site.address, site.address + 0xA0)[:40]
    imms = set()
    for ins in seq:
        for op in ins.operands:
            if op.type == x86.X86_OP_IMM:
                imms.add(op.imm & 0xFFFFFFFF)
            if op.type == x86.X86_OP_MEM:
                imms.add(op.mem.disp & 0xFFFFFFFF)
    nxt = seq[1] if len(seq) > 1 else None
    default = None
    if nxt is not None and nxt.mnemonic == 'add' and nxt.operands[1].type == x86.X86_OP_IMM:
        value = nxt.operands[1].imm
        if value >= c['record_offset'] and (value - c['record_offset']) % c['stride'] == 0:
            default = (value - c['record_offset']) // c['stride']
    capacity = c['indices'] in imms or (c['indices'] - 1) in imms
    # the record address: the stride, or the record offset itself or scaled by an lea (HellpodPayload: 12 x index +
    # 0x1CC x 8; WeaponMagazine: (index + 0x36) x 0xA0 by lea + shl)
    record = c['stride'] in imms or any(v and v * k == c['record_offset'] for v in imms for k in (1, 2, 4, 8, c['stride']))
    if default is not None:
        kind = 'default_record'
    elif capacity and record:
        kind = 'lookup'
    elif capacity:
        kind = 'lookup_index_only'
    else:
        kind = 'other'
    out = {'rva': hx(site.address), 'asm': site.mnemonic + ' ' + site.op_str, 'function': hx(img.root(site.address)
        or 0) if img.root(site.address) else None, 'kind': kind,
        'capacityImmediate': capacity, 'recordImmediate': record}
    if default is not None:
        out['defaultRecord'] = default
    write = site.operands[0].type == x86.X86_OP_MEM
    out['writesSlot'] = write
    return out


def prove_code(img: xref.CodeImage, components: dict) -> dict:
    pins = [img.pin(rva, role, asm) for rva, asm, role in GLOBAL_PINS]
    writers = [hx(i.address) for i in img.references(ENTITY_MANAGER)
               if i.operands and i.operands[0].type == x86.X86_OP_MEM and i.mnemonic.startswith('mov')]
    generic = [{'rva': hx(i.address), 'asm': i.mnemonic + ' ' + i.op_str,
                'function': hx(img.root(i.address)) if img.root(i.address) else None,
                'writesSlot': i.operands[0].type == x86.X86_OP_MEM}
               for i in slot_sites(img, SLOT_BASE)]
    per = {}
    for name in sorted(components):
        c = components[name]
        slot = SLOT_BASE + 8 * c['index']
        sites = []
        for ins in slot_sites(img, slot):
            row = classify(img, ins, c)
            load = global_load(img, ins)
            row['managerFromGlobal'] = load is not None
            if load:
                row['globalLoad'] = {'rva': hx(load['rva']), 'asm': load['asm']}
            sites.append(row)
        lookups = [s for s in sites if s['kind'] == 'lookup' and s['managerFromGlobal']]
        lookup_pins = []
        if lookups:
            first = lookups[0]
            lookup_pins = [img.pin(int(first['globalLoad']['rva'], 16), 'lookup: the entity manager from the global',
                                   first['globalLoad']['asm']),
                           img.pin(int(first['rva'], 16), 'lookup: the ' + name + ' table from slot ' + str(c['index']),
                                   first['asm'])]
        per[name] = {'index': c['index'], 'slot': hx(slot), 'profileOffset': c['offset'],
            'tableOffset': c['offset'] + PROFILE_TO_TABLE, 'indices': c['indices'], 'stride': c['stride'],
            'recordOffset': c['record_offset'], 'sites': sites,
            'kinds': {k: sum(1 for s in sites if s['kind'] == k) for k in sorted({s['kind'] for s in sites})},
            'everySiteReadsTheManagerFromTheGlobal': all(s['managerFromGlobal'] for s in sites),
            'slotWrittenOutsideTheLoader': any(s['writesSlot'] for s in sites),
            'lookupPins': lookup_pins}
    return {'pins': pins, 'globalWriters': writers, 'genericSlotSites': generic, 'components': per}


# ------------------------------------------------------------------------------------------------ snapshots
def snapshot_names() -> list[str]:
    folder = build_profile.snapshot_directory()
    return sorted(p.name for p in folder.glob(BUILD + '-*.hd2snap'))


def snapshot_facts(components: dict, code: dict) -> dict:
    out = {}
    folder = build_profile.snapshot_directory()
    pin_rvas = [(int(p['rva']), bytes.fromhex(p['bytes'])) for p in code['pins']]
    for comp in code['components'].values():
        pin_rvas += [(int(p['rva']), bytes.fromhex(p['bytes'])) for p in comp['lookupPins']]
    for name in snapshot_names():
        path = folder / name
        snap = snapshot_image.Snapshot(path)
        try:
            if snap.game_dll_sha256.upper() != code['dllSha256']:
                out[name] = {'skipped': 'another build'}
                continue
            game = snap.modules['game.dll']['base']

            def read(address, size):
                region = snap.region(address)
                if region is None or region['status'] != 1 or address + size > region['base'] + region['size']:
                    return None
                snap.handle.seek(region['data_offset'] + address - region['base'])
                return snap.handle.read(size)
            pins_ok = sum(read(game + rva, len(raw)) == raw for rva, raw in pin_rvas)
            manager = struct.unpack('<Q', read(game + ENTITY_MANAGER, 8))[0]
            region = snap.region(manager + SLOT_BASE)
            base = snapshot_entity_base(path)
            entity_region = snap.region(base)
            rows, matched, moved = {}, 0, []
            game_object = struct.unpack('<Q', read(game + GAME_GLOBAL, 8))[0]
            for cname in sorted(components):
                c = components[cname]
                pointer = struct.unpack('<Q', read(manager + SLOT_BASE + 8 * c['index'], 8))[0]
                expected = base + c['offset'] + PROFILE_TO_TABLE
                framing = read(base + c['offset'] - 4, 4)
                ok = pointer == expected
                matched += ok
                rows[cname] = {'pointerIsProfileTable': ok,
                    'indexFraming': struct.unpack('<I', framing)[0] == c['index'] if framing else None}
                if not ok:
                    # Not the game's loader (its only slot writer stores the in-place table): describe where it points.
                    target = snap.region(pointer)
                    frame = read(pointer - PROFILE_TO_TABLE, PROFILE_TO_TABLE)
                    rows[cname].update({'insideEntityAllocation': base <= pointer < base + entity_region['size'],
                        'target': {'type': hx(target['type']), 'protect': hx(target['protect']),
                                   'regionSize': hx(target['size'])} if target else None,
                        'targetFramingTypeMatches': bool(frame) and frame[:4] == bytes.fromhex(c['header'])[:4],
                        'targetDlSize': struct.unpack_from('<I', frame, 16)[0] if frame else None,
                        'profileDlSize': struct.unpack_from('<I', bytes.fromhex(c['header']), 16)[0]})
                    moved.append(cname)
            out[name] = {'gameDll': hx(game), 'entityManager': hx(manager),
                'managerRegion': {'type': hx(region['type']), 'protect': hx(region['protect']),
                                  'private': region['type'] == 0x20000},
                'entityAllocation': {'base': hx(base), 'protect': hx(entity_region['protect'])},
                'managerIsGamePlus0xE49F0': manager == game_object + 0xE49F0,
                'pinsByteIdentical': pins_ok, 'pins': len(pin_rvas), 'movedTables': moved,
                'componentsMatched': matched, 'components': len(components), 'perComponent': rows}
        finally:
            snap.close()
    return out


def overheat_cooldown_lead() -> dict:
    """The Quasar's "Cooldown After Overheat" (the same report): WeaponHeat members that could hold it, from the
    retained snapshot's records and the type library (research/las-beam-overhaul-comparison names the owners). Data
    only: no code read proves what the game does with them, so nothing here is exposed."""
    from migration import build_view
    view = build_view.from_snapshot(build_profile.SNAPSHOT)
    table = view.component('WeaponHeatComponentData')
    library = build_view.TypeLibrary((build_profile.FILEDIVER / 'datalibrary/dl_library.dl_typelib').read_bytes())
    layout = library.layout(build_view.dl_hash('WeaponHeatComponent'))
    named = {72: None, 76: None, 80: 'heat.overheat_lock', 84: 'heatsink.starting', 88: 'heatsink.from_supply',
             92: 'heatsink.spare', 96: 'heat.capacity', 116: 'heat.heat_per_shot', 120: 'heat.heat_per_second',
             128: 'heat.cool_per_second', 132: 'native hot multiplier', 136: 'native cold multiplier',
             148: 'heat.firing_charge', 152: 'heat.charge_gain_per_second', 156: 'heat.charge_loss_per_second',
             160: 'heat.reset_charge_after_shot'}
    members = [{'offset': m['offset64'], 'storage': m['storage'], 'nameLength': int(m['name'].split('=')[-1]),
                'field': named.get(m['offset64'])} for m in layout['members'] if m['offset64'] >= 72]
    research = json.loads((ROOT / 'research/las-beam-overhaul-comparison-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    owners = {r['record']: ', '.join(o['name'] or (o['path'] or o['resource']).rsplit('/', 1)[-1] for o in r['owners']) or 'unowned'
              for r in research['heat148']['records']}
    rows = []
    for index, raw in enumerate(table.records):
        rows.append({'record': index, 'owner': owners.get(index), 'capacity': struct.unpack_from('<f', raw, 96)[0],
                     'coolPerSecond': round(struct.unpack_from('<f', raw, 128)[0], 6),
                     'plus140': round(struct.unpack_from('<f', raw, 140)[0], 6), 'plus144': raw[144]})
    heatsink = [r for r in rows if r['plus144'] == 1]
    other = [r for r in rows if r['plus144'] == 0]
    return {'members': members, 'records': rows,
            'plus140On144Records': sorted({r['plus140'] for r in heatsink}),
            'plus144ZeroRecords': [{'owner': r['owner'], 'plus140': r['plus140'], 'coolPerSecond': r['coolPerSecond']}
                                   for r in other],
            'verdict': 'No overheat-lockout duration member is proven. WeaponHeat +140 (FP32, unnamed, name length 31) '
                       'is the lead: 400 on 28 of 30 records (every other player heat weapon), 2 on laser_rifle_charge, '
                       'and 6.66 on the LAS-99 Quasar, its own cooling rate; the Quasar is also the only weapon with '
                       '+144 (UINT8, lead name needs_reload_after_overheat) 0. It may be the cooling rate while '
                       'overheated; a live test of heat.cool_per_second on the Quasar decides it. Not exposed.'}


def build() -> dict:
    profile = profile_components()
    components = profile['components']
    img = xref.CodeImage.from_snapshot()
    if (img.sha256 or '').upper() != profile['dll']:
        raise ValueError('the analysed game.dll is not the profile build')
    code = prove_code(img, components)
    code['dllSha256'] = profile['dll']
    snapshots = snapshot_facts(components, code)
    used = [s for s in snapshots.values() if 'skipped' not in s]
    per = code['components']
    checks = {
        'globalWrittenOnlyByTheConstructor': code['globalWriters'] == ['0xFDA356'],
        'slotsWrittenOnlyByTheLoader': not any(c['slotWrittenOutsideTheLoader'] for c in per.values())
            and [g['rva'] for g in code['genericSlotSites'] if g['writesSlot']] == ['0xFDB636'],
        'everyComponentHasAGlobalLookup': all(c['lookupPins'] for c in per.values()),
        'everySlotSiteReadsTheManagerFromTheGlobal': all(c['everySiteReadsTheManagerFromTheGlobal']
                                                          for c in per.values()),
        'snapshots': len(used),
        'snapshotsWithEveryPointerOnTheProfileTable': sum(s['componentsMatched'] == s['components'] for s in used),
        # every other pointer: outside the entity allocation, in private read-write memory (not the game's loader,
        # whose only stores are the in-place tables): a table another program moved.
        'everyOtherPointerMovedOutsideTheGame': all(not row['insideEntityAllocation'] and row['target']
            and row['target']['type'] == '0x20000' and row['target']['protect'] == '0x4'
            for s in used for row in s['perComponent'].values() if not row['pointerIsProfileTable']),
        'movedTables': sorted({(name, c) for name, s in snapshots.items() if 'skipped' not in s
                               for c in s['movedTables']}),
        'managerIsGamePlus0xE49F0': all(s['managerIsGamePlus0xE49F0'] for s in used),
        'everySnapshotPinByteIdentical': all(s['pinsByteIdentical'] == s['pins'] for s in used),
        'managerIsPrivateMemory': all(s['managerRegion']['private'] for s in used),
    }
    return {'build': BUILD, 'gameDll': {'sha256': profile['dll']}, 'executable': {'sha256': profile['exe']},
        'writes': 0, 'protectionChanges': 0,
        'lead': 'True Lasgun Beam Overhaul (Bans), Source/core.lua and fixtures.json (beam_private / heat_private / '
                'magazine_private: global_rva 0x346BF98, manager_field 0xF12CE8 / 0xF12CC8 / 0xF124A0). Lead only: '
                'no code or data copied; every fact below is proven from game.dll and the snapshots.',
        'entityManagerGlobal': hx(ENTITY_MANAGER), 'slotBase': hx(SLOT_BASE),
        'slotFormula': '[game.dll + 0x346BF98] + 0xF12478 + 8 x component index',
        'tableFormula': 'entity allocation + profile component offset + 28 (DL frame + 0x18)',
        'code': code, 'snapshots': snapshots, 'checks': checks, 'overheatCooldownLead': overheat_cooldown_lead()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    result = build()
    text = json.dumps(result, indent=1) + '\n'
    if args.check:
        if OUTPUT.read_text(encoding='utf-8') != text:
            raise SystemExit('stale: ' + str(OUTPUT))
        print('up to date')
        return
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    print(json.dumps(result['checks'], indent=1))


if __name__ == '__main__':
    main()
