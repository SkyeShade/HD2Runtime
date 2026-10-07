"""The full sound-event catalogue (docs/research/sound-events-F5FEE03DCFDB.md): every Wwise Event object in every
wwise_bank of build F5FEE03DCFDB, with its banks, actions, kind, range, the mixer bus it plays on, the game parameters,
switch and state groups its sounds react to, the packages listing its banks and which stratagem or loadout package
provides them; and the sound engine's game parameters, state groups / states, switch groups / switches and busses.
Read-only, offline: the game's bundles, the retained snapshots (game.dll / exe strings, package residency) and the
installed Wwise plugin's strings. Nothing is written to the game or the snapshots.

1. Banks [O]: every wwise_bank resource (the first of identical copies); its name from its wwise_dep resource
   (`content/audio/<bank>`). HIRC objects parsed by scripts/wwise_banks.py; the sound-structure nodes (Sound,
   RandomSequence, Switch, ActorMixer, Layer) are used only where the parse consumed the object exactly.
2. Events [O]: an Event's actions; Play targets walked down (children) and up (parents) for the bus, the RTPCs, the
   switch and state groups. An action's scope is its type's low byte (Wwise AkActionType): 2 / 4 and set_state act on
   the whole sound engine ("global").
3. Kind and range [O]: the Stingray wwise_metadata record of the event (the resource covering the HIRC events): its
   duration type, durations and maximum attenuation (layout: research/wwise-plugin-F5FEE03DCFDB.json "metadata").
4. Init [O]: the Init bank's STMG (state groups, switch groups and their game parameter, game parameters and their
   defaults). State and switch values from set_state / set_switch actions, switch containers, state chunks and the
   switch groups' game-parameter graphs.
5. Names [O]: a name is used only where a string found in the game's own code or data hashes (FNV-1 32, the sound
   engine's own GetIDFromString) to an id of the same kind: game.dll and the executable (retained snapshot), the
   Wwise plugin, and every non-media game resource. The expected number of coincidental matches is measured with a
   control (the same strings with one byte appended) and reported. Everything else stays a numbered id.
6. Packages [O]: every package resource's listing; the stratagems whose call-in packages list a bank
   (research/stratagem-slot-conversion, as core/assets.lua dependencies_for_stratagem resolves them) and the
   loadout-catalogue items (research/package-residency "catalog") whose package lists it; residency in the seven
   retained snapshots. The audio test level's package lists every bank and is left out.

Output: research/sound-events-F5FEE03DCFDB.json (compact rows; an event's actions as 'TYPE:TARGET[:GROUP:VALUE]',
TYPE the Wwise action type in hex: high byte the action, low byte its scope; scripts/wwise_banks.py ACTIONS).
"""
from __future__ import annotations

import collections
import functools
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import hd2_game_data as gdata  # noqa: E402
import snapshot_image  # noqa: E402
import wwise_banks as wb  # noqa: E402

OUTPUT = ROOT / 'research/sound-events-F5FEE03DCFDB.json'
PLUGIN = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\bin\plugins\wwise_pluginw64_release.dll')
TEST_LEVEL = 'packages/content/audio_test_level'
SNAPSHOTS = None   # research_stratagem_calldown.SNAPSHOTS (imported in main)
HEX = lambda v: '%08X' % v  # noqa: E731
# Resource types never scanned for names (media and large binary data).
MEDIA = (b'wwise_bank', b'wwise_stream', b'texture', b'animation', b'physics', b'cloth')
NAME_PATTERN = re.compile(rb'[A-Za-z][A-Za-z0-9_]{3,95}')
# The metadata record: (event id, f32, f32, f32, u32, u32, u32) read by the plugin's duration / position / attenuation
# bindings; field names from research/wwise-plugin-F5FEE03DCFDB.json "metadata" when it exists.
# An RTPC curve's target property 0 is the Volume (Wwise AkRTPC_ParameterID RTPC_Volume = 0) [I].
VOLUME = 0
METADATA_FIELDS = ('id', 'maxAttenuation', 'maxDuration', 'minDuration', 'durationType', 'positionType', 'field6')


def strings_of(blob):
    return set(NAME_PATTERN.findall(blob))


class Corpus:
    """Strings from the game's code and data, by source, for FNV-1 matching."""

    def __init__(self):
        self.by_source = collections.defaultdict(set)

    def add(self, source, blob):
        self.by_source[source] |= strings_of(blob)

    def match(self, kinds):
        """kinds: {kind: set of ids}. Returns ({kind: {id: {'name', 'sources'}}}, control count, string count). A name
        is the matching string as found (the shortest, then first in order, when several case variants match)."""
        names = collections.defaultdict(dict)
        index = {}
        for kind, ids in kinds.items():
            for i in ids:
                index.setdefault(i, []).append(kind)
        every = collections.defaultdict(set)
        for source, strings in self.by_source.items():
            for s in strings:
                every[s].add(source)
        control = 0
        for s, sources in every.items():
            h = wb.fnv1(s)
            if wb.fnv1(s + b'\x01') in index:
                control += 1
            for kind in index.get(h, ()):
                text = s.decode('ascii')
                row = names[kind].get(h)
                if row is None:
                    names[kind][h] = {'name': text, 'variants': [text], 'sources': sorted(sources)}
                else:
                    row['variants'] = sorted(set(row['variants']) | {text})
                    row['sources'] = sorted(set(row['sources']) | sources)
                    row['name'] = sorted(row['variants'], key=lambda v: (v != v.lower(), v))[0]
        return names, control, len(every)


def main():
    import research_entity_authoring as rea
    import research_package_residency as rpr
    from research_stratagem_calldown import SNAPSHOTS as snapshots
    global SNAPSHOTS
    SNAPSHOTS = snapshots

    _chunk = gdata.chunk

    @functools.lru_cache(maxsize=8192)
    def cached(path, c):
        return _chunk(path, c)
    gdata.chunk = cached
    PACKAGE, BANK, DEP, META = (gdata.murmur64(n) for n in (b'package', b'wwise_bank', b'wwise_dep', b'wwise_metadata'))
    media = {gdata.murmur64(n) for n in MEDIA}
    data = gdata.Data()
    packages, banks, deps, metas, sizes, other = {}, {}, {}, {}, {}, {}
    copies = collections.defaultdict(list)
    for archive, rname, rtype, main_part, stream, gpu in data.tables():
        key = (rname, rtype)
        if key not in sizes:
            sizes[key] = main_part[1] + stream[1] + gpu[1]
        if rtype == PACKAGE:
            packages.setdefault(rname, (archive, main_part))
        elif rtype == BANK:
            banks.setdefault(rname, (archive, main_part))
            copies[rname].append((archive, main_part))
        elif rtype == DEP:
            deps.setdefault(rname, (archive, main_part))
        elif rtype == META:
            metas.setdefault(rname, (archive, main_part))
        elif rtype not in media:
            other.setdefault(key, (archive, main_part))
    # Identical copies only (a bank in several archives is the same bytes).
    for rname, parts in copies.items():
        if len(parts) > 1 and len({hashlib.sha256(data.read(*p)).digest() for p in parts}) != 1:
            raise ValueError('bank %016X differs between archives' % rname)

    def bank_name(r):
        try:
            return data.read(*deps[r])[8:].split(b'\0')[0].decode('latin-1')
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------------------------------- 1. the banks
    objects, where = {}, {}
    event_banks = collections.defaultdict(list)
    bank_rows = {}
    stmg = None
    bank_hash = hashlib.sha256()
    for r in sorted(banks):
        raw = data.read(*banks[r])
        bank_hash.update(raw)
        name = bank_name(r)
        tags = [t for t, _o, _s in wb.chunks(raw)]
        objs = wb.hirc(raw)
        counts = collections.Counter(k for k, _b in objs.values())
        bank_rows[r] = {'resource': '%016X' % r, 'name': name, 'bytes': sizes[(r, BANK)], 'chunks': tags,
            'objects': len(objs), 'events': counts.get(wb.EVENT, 0), 'sounds': counts.get(wb.SOUND, 0)}
        for t, o, s in wb.chunks(raw):
            if t == 'STMG':
                if stmg is not None:
                    raise ValueError('two STMG chunks')
                stmg = wb.stmg(raw[o:o + s])
                bank_rows[r]['init'] = True
        for oid, (kind, body) in objs.items():
            if kind == wb.EVENT:
                event_banks[oid].append(r)
            if oid not in objects:
                objects[oid], where[oid] = (kind, body), r
    if stmg is None:
        raise ValueError('no Init bank')

    # The sound structure.
    nodes, inexact = {}, collections.Counter()
    for oid, (kind, body) in objects.items():
        try:
            n = wb.node(kind, body)
        except Exception:  # noqa: BLE001
            n = None
            if kind in (2, 5, 6, 7, 9):
                inexact[kind] += 1
            continue
        if n is None:
            continue
        if n.exact:
            nodes[oid] = n
        else:
            inexact[kind] += 1
    # Music nodes: only the parent and bus, after a one-byte flag (taken where the parent is a known object).
    music_parent = {}
    for oid, (kind, body) in objects.items():
        if kind in (10, 12, 13):
            try:
                r_ = wb.Reader(body, 1)
                n = wb.Node(kind)
                wb._node_base(r_, n)
            except Exception:  # noqa: BLE001
                continue
            if n.parent == 0 or n.parent in objects:
                music_parent[oid] = (n.parent, n.bus)
    busses = {}
    for oid, (kind, body) in objects.items():
        if kind in (8, 18):
            parent = struct.unpack_from('<I', body, 0)[0]
            busses[oid] = {'kind': wb.KINDS[kind], 'parent': parent}
    for oid, b in busses.items():
        if b['parent'] and b['parent'] not in busses:
            b['parent'] = None

    def parent_bus(oid):
        n = nodes.get(oid)
        if n is not None:
            return n.parent, n.bus
        return music_parent.get(oid, (None, None))

    @functools.lru_cache(maxsize=None)
    def ancestors(oid):
        chain, seen = [], set()
        while oid and oid not in seen and len(chain) < 32:
            seen.add(oid)
            chain.append(oid)
            oid = parent_bus(oid)[0]
        return tuple(chain)

    def output_bus(oid):
        for o in ancestors(oid):
            bus = parent_bus(o)[1]
            if bus:
                return bus if bus in busses else None
        return None

    def subtree(oid, limit=4000):
        out, stack = [], [oid]
        seen = set()
        while stack and len(out) < limit:
            o = stack.pop()
            if o in seen:
                continue
            seen.add(o)
            out.append(o)
            n = nodes.get(o)
            if n is not None:
                stack.extend(n.children)
        return out

    # --------------------------------------------------------------------------------------------- 3. metadata
    meta_rows = {r: wb.metadata(data.read(*metas[r])) for r in sorted(metas)}
    event_ids = set(event_banks)
    general = max(meta_rows, key=lambda r: len(set(meta_rows[r]) & event_ids))
    covered = set(meta_rows[general]) & event_ids
    others = {r: rows for r, rows in meta_rows.items() if r != general and rows}

    # ----------------------------------------------------------------------------------------------- 2. events
    states_seen = collections.defaultdict(set)      # state group -> states
    switches_seen = collections.defaultdict(set)    # switch group -> switches
    for g in stmg['switchGroups']:
        for _v, sw, _c in g['points']:
            switches_seen[g['id']].add(sw)
    for n in nodes.values():
        for group, states in n.states:
            states_seen[group].update(states)
        if n.kind == 6 and n.switchGroup:
            target = states_seen if n.switchType == 1 else switches_seen
            target[n.switchGroup].update(n.switches)
    parameter_use = collections.Counter()
    events = {}
    action_types = collections.Counter()
    for eid in sorted(event_banks):
        kind, body = objects[eid]
        acts, parsed = [], []
        for aid in wb.event_actions(body):
            if aid not in objects or objects[aid][0] != wb.ACTION:
                acts.append({'action': HEX(aid), 'missing': True})
                continue
            a = wb.action(objects[aid][1])
            parsed.append(a)
            action_types['%04X' % a['type']] += 1
            row = {'type': '%04X' % a['type'], 'do': a['action'], 'scope': a['scope'], 'target': HEX(a['target'])}
            if 'group' in a:
                row['group'], row['value'] = HEX(a['group']), HEX(a['value'])
                (states_seen if a['type'] >> 8 == 0x12 else switches_seen)[a['group']].add(a['value'])
            if a['type'] >> 8 == 0x13 or a['type'] >> 8 == 0x14:
                parameter_use[a['target']] += 1
            acts.append(row)
        plays = [int(a['target'], 16) for a in acts if a.get('do') == 'play']
        nested = [int(a['target'], 16) for a in acts if a.get('do') == 'play_event']
        rtpcs, volume, sgroups, wgroups, bus_ids = set(), set(), set(), set(), set()
        for t in plays:
            if t not in objects:
                continue
            bus = output_bus(t)
            if bus:
                bus_ids.add(bus)
            for o in set(subtree(t)) | set(ancestors(t)):
                n = nodes.get(o)
                if n is None:
                    continue
                rtpcs.update(r for r, _p in n.rtpcs)
                volume.update(r for r, p in n.rtpcs if p == VOLUME)
                rtpcs.update(n.layerParameters)
                sgroups.update(g for g, _s in n.states)
                if n.kind == 6 and n.switchGroup:
                    (sgroups if n.switchType == 1 else wgroups).add(n.switchGroup)
        for r in rtpcs:
            parameter_use[r] += 1
        m = meta_rows[general].get(eid)
        vo = sorted('%016X' % r for r, rows in others.items() if eid in rows)
        if m is None and vo:
            m = others[min(others, key=lambda r: '%016X' % r)].get(eid)
        packed = [('%s:%s:%s:%s' % (a['type'], a['target'], a['group'], a['value']) if 'group' in a else
            '%s:%s' % (a['type'], a['target'])) if 'type' in a else 'missing:' + a['action'] for a in acts]
        events[eid] = {'banks': sorted(event_banks[eid]), 'actions': packed, 'plays': len(plays), 'nested': nested,
            'global': any(a.get('scope') == 'global' for a in acts), 'effects': wb.effects(parsed),
            'busses': sorted(bus_ids), 'parameters': sorted(rtpcs), 'volumeParameters': sorted(volume),
            'stateGroups': sorted(sgroups),
            'switchGroups': sorted(wgroups), 'metadata': list(m[1:]) if m else None,
            'metadataSource': 'general' if eid in covered else ('voice' if m else None), 'voiceMetadata': len(vo)}

    # An event that posts other events (play_event) carries what they do: their busses, parameters, groups and any
    # global action (to a fixed point).
    changed = True
    while changed:
        changed = False
        for e in events.values():
            for n in e['nested']:
                inner = events.get(n)
                if inner is None:
                    continue
                for key in ('busses', 'parameters', 'volumeParameters', 'stateGroups', 'switchGroups'):
                    merged = sorted(set(e[key]) | set(inner[key]))
                    if merged != e[key]:
                        e[key], changed = merged, True
                if inner['global'] and not e['global']:
                    e['global'], changed = True, True
                merged = sorted(set(e['effects']) | set(inner['effects']))
                if merged != e['effects']:
                    e['effects'], changed = merged, True
    for e in events.values():
        e['nested'] = len(e['nested'])

    # ------------------------------------------------------------------------------------------------- 5. names
    corpus = Corpus()
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    for module in ('game.dll', 'helldivers2.exe'):
        corpus.add(module, snap.module_image(module)[1])
    snap.close()
    corpus.add('wwise plugin', PLUGIN.read_bytes())
    type_names = {gdata.murmur64(n): n.decode() for n in (b'unit', b'level', b'strings', b'state_machine', b'package',
        b'material', b'particles', b'entity', b'prefab', b'config', b'lua', b'hash_lookup', b'wwise_properties',
        b'wwise_metadata', b'network_config', b'font', b'bones', b'ragdoll_profile', b'speedtree', b'geometry_group',
        b'render_config', b'wwise_dep', b'shading_environment_mapping', b'texture_atlas', b'mouse_cursor',
        b'shader_library', b'vector_field', b'shading_environment')}
    for (r, t), part in sorted(other.items()):
        try:
            blob = data.read(*part)
        except Exception:  # noqa: BLE001
            continue
        corpus.add('resource:' + type_names.get(t, '%016X' % t), blob)
    state_values = set().union(*states_seen.values()) if states_seen else set()
    switch_values = set().union(*switches_seen.values()) if switches_seen else set()
    kinds = {'event': set(events), 'parameter': {p['id'] for p in stmg['parameters']} | set(parameter_use),
        'stateGroup': {g['id'] for g in stmg['stateGroups']} | set(states_seen), 'state': state_values,
        'switchGroup': {g['id'] for g in stmg['switchGroups']} | set(switches_seen), 'switch': switch_values,
        'bus': set(busses)}
    names, control, string_count = corpus.match(kinds)
    id_count = len(set().union(*kinds.values()))

    # ---------------------------------------------------------------------------------------------- 6. packages
    def listing(package):
        raw = data.read(*packages[package])
        if len(raw) < 16:
            return None
        _version, _word, count = struct.unpack_from('<III', raw, 0)
        if len(raw) != 16 + 16 * count:
            return None
        return {struct.unpack_from('<QQ', raw, 16 + 16 * i)[::-1] for i in range(count)}
    native = rea.Native()
    bank_packages = collections.defaultdict(list)
    package_info, listings = {}, {}
    for package in sorted(packages):
        items = listing(package)
        if not items:
            continue
        listings[package] = items
        hits = [b for b in banks if (b, BANK) in items]
        if not hits:
            continue
        name = native.path(package)
        package_info[package] = {'package': '0x%016X' % package, 'name': name,
            'bytes': sum(sizes.get(i, 0) for i in items), 'resources': len(items), 'banks': len(hits)}
        if name == TEST_LEVEL:
            continue
        for b in hits:
            bank_packages[b].append(package)
    loader = rpr.loader_pins(snapshot_image.Snapshot(build_profile.SNAPSHOT))
    resident_in = collections.Counter()
    for name in SNAPSHOTS:
        s = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        states, _refs, _capacity = rpr.residency(s, loader)
        s.close()
        for package in package_info:
            if states.get(package):
                resident_in[package] += 1
    for package, info in package_info.items():
        info['residentInSnapshots'] = resident_in[package]

    # Stratagems (call-in packages) and loadout-catalogue items whose package lists a bank.
    slots = json.loads((ROOT / 'research/stratagem-slot-conversion-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    sp = slots['stratagemPackages']
    incomplete = set(sp['callIn']['incomplete'])
    catalogue = json.loads((ROOT / 'schemas/stratagem_authoring_catalog.json').read_text(encoding='utf-8'))
    providers = collections.defaultdict(list)
    for name, s in sorted(catalogue['stratagems'].items()):
        sid = (s.get('root') or {}).get('id')
        if sid is None:
            continue
        listed = sp['callIn']['byStableId'].get(str(sid))
        ids = [i['package'] for i in listed] if listed else ([sp['byStableId'][str(sid)]] if str(sid) in
            sp['byStableId'] else [])
        ids = [p for k, p in enumerate(ids) if p not in ids[:k] and int(p, 16)]
        total, per = 0, []
        for p in ids:
            items = listings.get(int(p, 16))
            total += sum(sizes.get(i, 0) for i in items) if items else 0
            per.append((p, items))
        for b in banks:
            via = [p for p, items in per if items and (b, BANK) in items]
            if via:
                providers[b].append({'kind': 'stratagem', 'name': name, 'stableId': sid, 'packages': via,
                    'bytes': total, 'complete': name not in incomplete})
    residency = json.loads((ROOT / 'research/package-residency-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
    for key, item in sorted(residency['catalog'].items()):
        dep = item.get('dependency') or {}
        if not (item.get('known') and dep.get('package') and dep.get('inBundleDatabase')):
            continue
        items = listings.get(int(dep['package'], 16))
        if not items:
            continue
        for b in banks:
            if (b, BANK) in items:
                providers[b].append({'kind': 'catalog', 'key': key, 'label': item['label'],
                    'package': dep['package'], 'bytes': sum(sizes.get(i, 0) for i in items)})
    for b in providers:
        providers[b].sort(key=lambda p: (p['kind'] != 'stratagem' or not p['complete'], p['bytes'],
            p.get('name') or p.get('key')))

    # -------------------------------------------------------------------------------------------------- output
    def name_of(kind, i):
        row = names.get(kind, {}).get(i)
        return row['name'] if row else None
    result = {
        'build': 'F5FEE03DCFDB', 'writes': 0,
        'banksSha256': bank_hash.hexdigest(),
        'counts': {'banks': len(banks), 'banksWithHirc': sum(1 for b in bank_rows.values() if b['objects']),
            'objects': len(objects), 'events': len(events), 'eventsInSeveralBanks': sum(1 for e in event_banks.values()
                if len(e) > 1), 'nodesParsed': len(nodes), 'nodesNotParsedExactly': {wb.KINDS[k]: v for k, v in
                sorted(inexact.items())}, 'metadataCovered': len(covered), 'packagesListingBanks': len(package_info),
            'actionTypes': dict(sorted(action_types.items()))},
        'names': {'strings': string_count, 'ids': id_count, 'controlMatches': control,
            'matched': {k: len(v) for k, v in sorted(names.items())},
            'rule': 'a string of the game\'s code or data whose FNV-1 32 (lower-cased) equals an id of that kind; the '
                'control is the same strings with one byte appended, matched against every id: the expected number '
                'of coincidental matches'},
        'metadata': {'general': '%016X' % general, 'voice': sorted('%016X' % r for r in others),
            'empty': sorted('%016X' % r for r, rows in meta_rows.items() if not rows), 'fields': METADATA_FIELDS},
        'init': {'volumeThreshold': stmg['volumeThreshold'], 'maxVoices': stmg['maxVoices'],
            'maxVirtualVoices': stmg['maxVirtualVoices']},
        'banks': {b['resource']: {k: v for k, v in b.items() if k != 'resource'} for b in
            sorted(bank_rows.values(), key=lambda b: b['resource'])},
        'bankPackages': {'%016X' % b: ['0x%016X' % p for p in sorted(ps, key=lambda p: (package_info[p]['bytes'], p))]
            for b, ps in sorted(bank_packages.items())},
        'bankProviders': {'%016X' % b: ps[:6] for b, ps in sorted(providers.items())},
        'packages': {p['package']: {k: v for k, v in p.items() if k != 'package'} for p in
            sorted(package_info.values(), key=lambda p: p['package'])},
        'busses': {HEX(i): {'kind': b['kind'], 'parent': HEX(b['parent']) if b['parent'] else None,
            'name': name_of('bus', i), 'nameSources': names.get('bus', {}).get(i, {}).get('sources')}
            for i, b in sorted(busses.items())},
        'parameters': {HEX(p['id']): {'default': p['default'], 'builtIn': p['builtIn'], 'rampType': p['rampType'],
            'name': name_of('parameter', p['id']), 'nameSources': names.get('parameter', {}).get(p['id'], {})
            .get('sources'), 'events': parameter_use.get(p['id'], 0)} for p in stmg['parameters']},
        'stateGroups': {HEX(g): {'states': {HEX(s): name_of('state', s) for s in sorted(states_seen.get(g, ()))},
            'name': name_of('stateGroup', g), 'inInit': g in {x['id'] for x in stmg['stateGroups']}}
            for g in sorted({x['id'] for x in stmg['stateGroups']} | set(states_seen))},
        'switchGroups': {HEX(g): {'switches': {HEX(s): name_of('switch', s) for s in sorted(switches_seen.get(g, ()))},
            'name': name_of('switchGroup', g), 'parameter': next((HEX(x['parameter']) for x in stmg['switchGroups']
                if x['id'] == g), None)} for g in sorted({x['id'] for x in stmg['switchGroups']} | set(switches_seen))},
        'eventNames': {HEX(i): row for i, row in sorted(names.get('event', {}).items())},
        'events': {HEX(i): {**e, 'banks': ['%016X' % b for b in e['banks']], 'busses': [HEX(b) for b in e['busses']],
            'parameters': [HEX(p) for p in e['parameters']], 'stateGroups': [HEX(g) for g in e['stateGroups']],
            'volumeParameters': [HEX(p) for p in e['volumeParameters']],
            'switchGroups': [HEX(g) for g in e['switchGroups']]} for i, e in sorted(events.items())},
    }
    text = json.dumps(result, indent=None, separators=(',', ':'))
    # One event / bank / package per line keeps the file diffable.
    text = re.sub(r'(,)("[0-9A-F]{8,16}":\{)', r'\1\n\2', text)
    with open(OUTPUT, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text + '\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; banks', len(banks), '; events', len(events), '; named',
        {k: len(v) for k, v in names.items()}, '; control', control, '; strings', string_count)


if __name__ == '__main__':
    main()
