"""Capture native evidence for Booster authoring. Read-only; nothing writes memory.

Boosters have no component or settings type of their own. The pinned type library
references the native `Booster` enum from exactly two places, and both are followed:

* StratagemInfo +280: a per-stratagem list of {Booster, payload, entity-delta key,
  package}. In the current build only the Resupply stratagem has an entry.
* StatusEffectSusceptibility +112: a per-susceptibility booster gate with an override
  effect, inside StatusEffectReceiverComponentData.

Booster identity comes from the native enum and the game's own UI template, which binds
each native member name to a booster icon. Member names are matched to enum values by
hidden-name length in the pinned type library; values that share a length stay as
candidate sets. Scraped wiki values are fingerprints only.

A booster field is published writable only when a native record is linked either
structurally (a pointer chain) or by a unique exact multi-value fingerprint, and every
field requires an explicit acknowledgement because no booster edit is gameplay-proven.
"""
from __future__ import annotations

import hashlib
import json
import mmap
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_entity_authoring as entity_research
import research_magazine_attachments as attachment_research
import snapshot_regions

WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_boosters.json'
NAMED_STRATAGEMS = entity_research.NAMED_REFERENCE
OUTPUT = ROOT / 'research/booster-authoring-F5FEE03DCFDB.json'
TYPELIB_HASHES = entity_research.FILEDIVER / 'hashes/dl_type_names.txt'
STATUS_ROWS, STATUS_ROOT, STATUS_STRIDE = 71, 44, 152
TURRET_COMPONENTS = ('ProjectileWeaponComponentData', 'WeaponMagazineComponentData')
RECEIVER = 'StatusEffectReceiverComponentData'
RACK_COMPONENT = 'HellpodRackComponentData'

# Reviewed catalog bridge: wiki display name -> native UI icon key. It names catalog
# entries only; every key must also be a letter subsequence of the wiki name.
WIKI_TO_ICON = {
    'Hellpod Space Optimization': 'BoosterHellpodopt', 'Vitality Enhancement': 'BoosterVitality',
    'UAV Recon Booster': 'BoosterRecon', 'Stamina Enhancement': 'BoosterStamina',
    'Muscle Enhancement': 'BoosterMuscle', 'Increased Reinforcement Budget': 'BoosterIncreasedbudget',
    'Flexible Reinforcement Budget': 'BoosterFlexiblebudget', 'Localization Confusion': 'BoosterLocalization',
    'Expert Extraction Pilot': 'BoosterExpert', 'Motivational Shocks': 'BoosterShocks',
    'Experimental Infusion': 'BoosterInfusion', 'Firebomb Hellpods': 'BoosterFirebomb',
    'Dead Sprint': 'BoosterDeadsprint', 'Armed Resupply Pods': 'BoosterArmedpods',
    'Sample Extricator': 'BoosterSampleextricator', 'Sample Scanner': 'BoosterSamplescanner',
    'Stun Pods': 'BoosterStunpods', 'Concealed Insertion': 'BoosterConcealedinsertion',
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


class TypeLibrary:
    """Enum value -> hidden alias name length, from the pinned stripped type library."""

    def __init__(self, data: bytes, probe):
        self.data, self.dl_hash = data, probe.dl_hash
        header = struct.Struct('<4s8I')
        _, _, types, enums, members, values, aliases, _, _ = header.unpack_from(data)
        self.enums = enums
        self.enum_hashes = header.size + 4 * types
        type_desc = self.enum_hashes + 4 * enums
        self.enum_desc = type_desc + 36 * types
        member_desc = self.enum_desc + 32 * enums
        self.values = member_desc + 72 * members
        self.aliases = self.values + 16 * values
        offsets = set()
        for i in range(types):
            v = struct.unpack_from('<9I', data, type_desc + 36 * i)
            offsets.update(o for o in (v[0], v[8]) if o != 0xFFFFFFFF)
        for i in range(enums):
            v = struct.unpack_from('<IIB3xIIIII', data, self.enum_desc + 32 * i)
            offsets.update(o for o in (v[0], v[7]) if o != 0xFFFFFFFF)
        for m in range(members):
            offsets.update(o for o in struct.unpack_from('<3I', data, member_desc + 72 * m)[:2] if o != 0xFFFFFFFF)
        for j in range(values):
            comment = struct.unpack_from('<IIQ', data, self.values + 16 * j)[1]
            if comment != 0xFFFFFFFF:
                offsets.add(comment)
        for j in range(aliases):
            name = struct.unpack_from('<II', data, self.aliases + 8 * j)[0]
            if name != 0xFFFFFFFF:
                offsets.add(name)
        self.sorted = sorted(offsets)
        self.index = {o: i for i, o in enumerate(self.sorted)}

    def lengths(self, name: str) -> dict[int, int]:
        target = self.dl_hash(name)
        for i in range(self.enums):
            if struct.unpack_from('<I', self.data, self.enum_hashes + 4 * i)[0] != target:
                continue
            _, _, _, count, start, _, _, _ = struct.unpack_from('<IIB3xIIIII', self.data, self.enum_desc + 32 * i)
            result = {}
            for j in range(start, start + count):
                main, _, value = struct.unpack_from('<IIQ', self.data, self.values + 16 * j)
                offset = struct.unpack_from('<II', self.data, self.aliases + 8 * main)[0]
                k = self.index[offset]
                result[value] = self.sorted[k + 1] - offset - 1
            return result
        raise ValueError(name + ' enum absent')


def ui_template(snapshot: Path) -> tuple[list[tuple[str, str]], str]:
    """Native member name -> icon key pairs from the game's booster DataTemplate."""
    key = b'x:Key="BoosterDataTemplate"'
    with open(snapshot, 'rb') as handle:
        mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        at = mapped.find(key)
        if at < 0:
            raise ValueError('booster UI template absent from snapshot')
        block = bytes(mapped[at:at + 20000])
    block = block[:block.index(b'</DataTemplate>')]
    pairs = re.findall(rb'Value="([A-Za-z0-9_]+)">\s*<Setter TargetName="BoosterIconsContentControl" '
        rb'Property="ContentTemplate" Value="\{DynamicResource (Booster[A-Za-z]+)\}"', block)
    return [(a.decode(), b.decode()) for a, b in pairs], sha(block)


def main():
    native = entity_research.Native()
    library = TypeLibrary(native.typelib, native.probe)
    booster_lengths = library.lengths('Booster')
    cracked = [line[len('Booster_'):] for line in TYPELIB_HASHES.read_text(encoding='utf-8').splitlines()
        if line.startswith('Booster_') and line not in ('Booster_None', 'Booster_Count')]
    pairs, template_sha = ui_template(snapshot_regions.SNAPSHOT)
    names = {name: icon for name, icon in pairs}
    if len(names) != 18:
        raise ValueError('unexpected booster UI template size')

    # Candidate enum values per native name (hidden alias length == len('Booster_' + name)).
    by_length = {}
    for value, length in booster_lengths.items():
        if value not in (0, max(booster_lengths)):
            by_length.setdefault(length, []).append(value)
    candidates = {name: sorted(by_length.get(8 + len(name), [])) for name in names}

    # Native effect link 1: StratagemInfo booster entries (live).
    stratagem_links = json.loads(snapshot_regions.run_lua(r'''
local Reader=require('hd2runtime/runtime/reader')
local b=require('hd2runtime/core/bytes')
local stratagem=require('hd2runtime/core/stratagem')
local reader=Reader.new(source)
local records,region=stratagem.capture_all(source,reader,profile)
local bytes=reader.read(region,0,profile.stratagem.size,true)
local out={}
for _,r in ipairs(records)do
 local ptr=b.pointer(bytes,r.offset+280);local count=b.pointer(bytes,r.offset+288)
 if count>0 then
  assert(ptr>=region.base and ptr+count*32<=region.base+profile.stratagem.size,'booster list outside table')
  local at=ptr-region.base
  for i=0,count-1 do
   local e=at+i*32
   out[#out+1]={recordKind=r.record_kind,id=r.id,payloads=r.payloads,entryIndex=i,
    booster=b.u32(bytes,e),reserved=b.u32(bytes,e+4),payload=b.resource(bytes,e+8),
    entityDelta=b.resource(bytes,e+16),package=b.resource(bytes,e+24)}
  end
 end
end
return require('hd2runtime/primary_mapper/json').encode(out)
''').decode())
    named = {}
    for group in json.loads(NAMED_STRATAGEMS.read_text(encoding='utf-8')):
        for items in group.values():
            for item in items['items']:
                named[item['id']] = item['debug_name']
    for link in stratagem_links:
        link['referenceDebugName'] = named.get(link['id'])

    # Entity delta chain for each stratagem booster entry (pinned table proven identical live).
    deltas_file = (attachment_research.DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    base, live_deltas = snapshot_regions.region_bytes('entity_deltas')
    delta_equality = {'identical': live_deltas[:len(deltas_file)] == deltas_file or
        snapshot_regions.compare_pinned(live_deltas[:len(deltas_file)], base, deltas_file)['identical']}
    if not delta_equality['identical']:
        raise ValueError('live entity delta table differs from the pinned reference')
    deltas, layout = attachment_research.entity_deltas(deltas_file)
    rack_index = native.probe.find_component(native.entities, RACK_COMPONENT)
    rack_component_index = struct.unpack_from('<I', native.entities, rack_index[4] - 4)[0]
    for link in stratagem_links:
        entry = deltas[int(link['entityDelta'], 16)]
        attached = []
        for item in entry['entries']:
            # HellpodRackComponent items are 64-byte slots whose first 8 bytes name the entity.
            if item['component'] == rack_component_index and item['size'] == 8 and item['offset'] % 64 == 0:
                resource = struct.unpack_from('<Q', item['bytes'], 0)[0]
                if not resource:
                    continue
                hexed = entity_research.hexid(resource)
                owned = {c['name'] for c in native.report(hexed)['components'] if c['resolved']}
                attached.append({'resource': hexed, 'path': native.path(resource),
                    'rackSlot': item['offset'] // 64, 'dataOffset': item['dataOffset'],
                    'weaponEntity': 'ProjectileWeaponComponentData' in owned})
        link['delta'] = {'hashmapSlot': entry['hashmapSlot'], 'settingsIndex': entry['settingsIndex'],
            'patchedComponent': RACK_COMPONENT, 'patchedComponentIndex': rack_component_index,
            'attachedEntities': attached}

    # Live equality of the entity tables relied on below.
    entity_base, live_entity = snapshot_regions.region_bytes('entity')
    tables = {}
    for name in TURRET_COMPONENTS + (RECEIVER, RACK_COMPONENT):
        _, _, _, _, offset = native.probe.find_component(native.entities, name)
        _, capacity, record_offset, size, count = native.table(name)
        start = offset + 28
        spans = ((offset, start + capacity * 16), (start + record_offset, start + record_offset + count * size))
        if not all(live_entity[a:b] == native.entities[a:b] for a, b in spans):
            raise ValueError(name + ' differs live')
        tables[name] = True

    # Turret entities attached by booster deltas.
    turrets = []
    for link in stratagem_links:
        for item in link['delta']['attachedEntities']:
            if not item['weaponEntity']:
                continue
            components = {}
            for name in TURRET_COMPONENTS:
                found = native.component(item['resource'], name)
                ownership = native.ownership(found)
                raw = native.record(name, found['record_index'])
                components[name] = {'recordIndex': found['record_index'], 'indexRow': found['index_row'],
                    'ownerCount': ownership['ownerCount'], 'uniqueOwner': ownership['uniqueOwner']}
                if name == 'ProjectileWeaponComponentData':
                    components[name].update({'fireRate': round(struct.unpack_from('<f', raw, 8)[0], 6),
                        'projectileType': struct.unpack_from('<I', raw, 0)[0]})
                else:
                    components[name].update({'magazine': list(struct.unpack_from('<4I', raw, 136))})
            turrets.append({'resource': item['resource'], 'entityRow': native.entity_row(int(item['resource'], 16)),
                'booster': link['booster'], 'components': components})

    # Native effect link 2: booster-gated susceptibilities.
    gates = []
    owners = native.owners(RECEIVER)
    _, _, _, size, count = native.table(RECEIVER)
    for record in range(count):
        raw = native.record(RECEIVER, record)
        for zone in range(8):
            for slot in range(33):
                at = zone * 5816 + 8 + slot * 176
                booster = struct.unpack_from('<I', raw, at + 112)[0]
                if booster:
                    gates.append({'booster': booster, 'record': record, 'zone': zone, 'slot': slot,
                        'owners': [native.path(o) or entity_research.hexid(o) for o in owners.get(record, [])],
                        'susceptibilityType': struct.unpack_from('<I', raw, at + 140)[0],
                        'parameters': [round(v, 6) for v in struct.unpack_from('<2f', raw, at + 144)],
                        'baseEffect': '0x%016X' % struct.unpack_from('<Q', raw, at)[0],
                        'overrideEffect': '0x%016X' % struct.unpack_from('<Q', raw, at + 120)[0]})

    # Native effect link 3 (fingerprint): stat-modifying status rows (live).
    status_base, status = snapshot_regions.region_bytes('status')
    status_rows = []
    for row in range(STATUS_ROWS):
        at = STATUS_ROOT + row * STATUS_STRIDE
        pointer, entries = struct.unpack_from('<QQ', status, at + 104)
        if not entries:
            continue
        array = pointer - status_base
        if not (0 <= array and array + entries * 8 <= len(status)):
            raise ValueError('status multiplier array outside allocation')
        status_rows.append({'row': row, 'type': struct.unpack_from('<i', status, at)[0],
            'offset': at, 'strength': round(struct.unpack_from('<f', status, at + 36)[0], 6),
            'duration': round(struct.unpack_from('<f', status, at + 40)[0], 6),
            'multiplierArrayOffset': array,
            'multipliers': [{'stat': struct.unpack_from('<I', status, array + 8 * i)[0],
                'value': round(struct.unpack_from('<f', status, array + 8 * i + 4)[0], 6)} for i in range(entries)]})
    damage_base, damage = snapshot_regions.region_bytes('damage')
    status_references = {}
    for i in range(649):
        at = 100 + i * 76
        for offset in (44, 52, 60, 68):
            kind = struct.unpack_from('<I', damage, at + offset)[0]
            if kind:
                status_references[kind] = status_references.get(kind, 0) + 1

    wiki = json.loads(WIKI.read_text(encoding='utf-8'))['boosters']
    catalog = []
    for booster in wiki:
        name = booster['name']
        icon = WIKI_TO_ICON.get(name)
        entry = {'name': name, 'wikiIndexOrder': booster.get('indexOrder'), 'uiIcon': icon,
            'nativeName': None, 'enumValue': None, 'enumValueCandidates': [], 'identityEvidence': []}
        if icon:
            if not subsequence(icon[len('Booster'):].lower(), re.sub('[^a-z]', '', name.lower())):
                raise ValueError('reviewed icon key is not a subsequence of the wiki name: ' + name)
            native_name = next(n for n, i in names.items() if i == icon)
            values = candidates[native_name]
            entry.update({'nativeName': native_name, 'enumValueCandidates': values,
                'enumValue': values[0] if len(values) == 1 else None})
            entry['identityEvidence'].append('game UI template binds native member ' + native_name + ' to ' + icon)
            entry['identityEvidence'].append('type-library alias length resolves '
                + ('a unique value' if len(values) == 1 else 'a candidate set of ' + str(len(values))))
        catalog.append(entry)
    unnamed_values = sorted(set(v for vs in by_length.values() for v in vs)
        - set(v for e in catalog for v in (e['enumValueCandidates'] if len(e['enumValueCandidates']) == 1 else [])))

    report = {'schemaVersion': 1, 'sourceSnapshot': snapshot_regions.SNAPSHOT.name,
        'pinnedReferences': {'entities': sha(native.entities), 'typelib': sha(native.typelib),
            'entityDeltas': sha(deltas_file), 'namedStratagems': sha(NAMED_STRATAGEMS.read_bytes())},
        'wikiDataset': sha(WIKI.read_bytes()),
        'boosterEnum': {'values': len(booster_lengths), 'aliasLengths': booster_lengths,
            'crackedNames': cracked, 'uiTemplateSha256': template_sha, 'uiPairs': pairs,
            'nameCandidates': candidates},
        'typeLibraryBoosterReferences': ['StratagemInfo+280 (0xB6CAFF2E list)', 'StatusEffectSusceptibility+112'],
        'liveEquality': {'entityDeltas': delta_equality, 'entityTables': tables},
        'stratagemBoosterEntries': stratagem_links, 'boosterTurrets': turrets,
        'susceptibilityGates': gates, 'statModifyingStatusRows': status_rows,
        'statusTypeReferencesFromDamageInfo': status_references,
        'catalog': catalog, 'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'}
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'entries': [(l['recordKind'], l['booster'], l['referenceDebugName'],
        [a['resource'] for a in l['delta']['attachedEntities']]) for l in stratagem_links],
        'turrets': [(t['resource'], t['components']['ProjectileWeaponComponentData']['fireRate'],
            t['components']['WeaponMagazineComponentData']['magazine']) for t in turrets],
        'gates': [(g['booster'], g['owners'], g['susceptibilityType'], g['parameters']) for g in gates],
        'statusRows': [(r['row'], r['type'], r['strength'], r['duration'], r['multipliers']) for r in status_rows],
        'identities': [(e['name'], e['nativeName'], e['enumValueCandidates']) for e in catalog]}, indent=1))


if __name__ == '__main__':
    main()
