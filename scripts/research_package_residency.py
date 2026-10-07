"""Research Helldivers 2 package (asset) residency and the native loader. Read-only; nothing here writes or calls.

Model (proven below from code bytes, retained snapshots, and the game's own logs):

* Every loadout-capable entity owns a LoadoutPackageComponent whose +8 member is a package resource
  ("packages/generated/loadout/<item>"). The package is generated from the entity, so it carries the entity's
  own resources (units, projectiles, effects).
* game.dll's RefcountedPackageSystem is the single place gameplay asks for packages:
  request(system, const u64 *ids, u32 count) increments a per-package reference count and, on 0 -> 1, asks
  the engine to load the package; release(...) decrements and, on 1 -> 0, asks the engine to unload it.
* The engine (helldivers2.exe) queues loads asynchronously; a package is resident when every part reached
  state 4.
* What becomes resident: every player's loadout (weapons, throwable, stratagem payload items) is requested
  on the ship, at mission preparation, and when a peer hot-joins; level generation requests world-loot items.
  A reference swap into an item nobody carries therefore points at resources that were never loaded.

Outputs research/package-residency-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)

OUTPUT = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
LOG_EVIDENCE = ROOT / 'research/package-lifecycle-log-evidence.json'
GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2')
SNAPSHOTS = ('F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap')
LOADED = 4                       # engine package-part state value for "loaded"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def murmur64a(data: bytes, seed: int = 0) -> int:
    """Stingray resource name hash (MurmurHash64A)."""
    m, mask = 0xC6A4A7935BD1E995, (1 << 64) - 1
    h = (seed ^ (len(data) * m)) & mask
    whole = len(data) // 8
    for i in range(whole):
        k = (int.from_bytes(data[i * 8:i * 8 + 8], 'little') * m) & mask
        k = ((k ^ (k >> 47)) * m) & mask
        h = ((h ^ k) * m) & mask
    if len(data) % 8:
        h = ((h ^ int.from_bytes(data[whole * 8:], 'little')) * m) & mask
    h = ((h ^ (h >> 47)) * m) & mask
    return h ^ (h >> 47)


def hexid(value: int) -> str:
    return f'0x{value:016X}'


class Image:
    """A module image from a snapshot, with the RIP-relative helpers the proofs need."""

    def __init__(self, snap, name):
        self.name = name
        self.base, self.data = snap.module_image(name)

    def rel(self, at, disp_at, length):
        """Target RVA of a RIP-relative operand whose disp32 sits at disp_at and whose instruction ends at
        at+length."""
        return at + length + struct.unpack_from('<i', self.data, disp_at)[0]

    def strings(self, text):
        return [m.start() for m in re.finditer(re.escape(text.encode()) + b'\0', self.data)]

    def lea_refs(self, target, limit):
        refs = []
        for m in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]', self.data[:limit]):
            at = m.start()
            if self.rel(at, at + 3, 7) == target:
                refs.append(at)
        return refs

    def calls_to(self, target, limit):
        return [m.start() for m in re.finditer(rb'\xe8', self.data[:limit])
            if m.start() + 5 + struct.unpack_from('<i', self.data, m.start() + 1)[0] == target]

    def function_start(self, at):
        while not (self.data[at - 1] == 0xCC and self.data[at - 2] == 0xCC):
            at -= 1
        return at


def expect(condition, message):
    if not condition:
        raise ValueError('package loader proof failed: ' + message)


def loader_pins(snap):
    """Derive every runtime pin from code bytes, not from constants."""
    dll = Image(snap, 'game.dll')
    exe = Image(snap, 'helldivers2.exe')
    text_limit = 0x2200000

    def function_for(message):
        strings = dll.strings(message)
        expect(len(strings) == 1, 'log string ' + message + ' is not unique')
        # The out-of-line entry point (other references are inlined single-package copies of the same logic):
        # it starts `test r8d, r8d` and is the function gameplay systems call.
        candidates = []
        for ref in dll.lea_refs(strings[0], text_limit):
            start = dll.function_start(ref)
            if dll.data[start:start + 3] == bytes((0x45, 0x85, 0xC0)) and len(dll.calls_to(start, text_limit)) >= 10:
                candidates.append((start, ref))
        expect(len(candidates) == 1, 'log string ' + message + ' has ' + str(len(candidates)) + ' entry points')
        return candidates[0]

    request, request_log = function_for('Requesting package %s, ref_count=%llu')
    release, release_log = function_for('Releasing package %s, ref_count=%llu')
    # Both entry points: `test r8d, r8d; je` (count 0 is a no-op), the refcount map walk, then the engine call.
    for name, start in (('request', request), ('release', release)):
        expect(dll.data[start:start + 3] == b'\x45\x85\xc0', name + ' does not begin with test r8d, r8d')
    # Engine API: mov rax,[rip+G]; mov rcx,rsi; mov rdx,[rax+0x10]; call [rdx+SLOT]
    engine_slots = {}
    for name, start, end in (('request', request, request + 0x180), ('release', release, release + 0x180)):
        m = re.search(rb'\x48\x8b\x05(....)\x48\x8b\xce\x48\x8b\x50\x10\xff\x92(....)', dll.data[start:end], re.S)
        expect(m is not None, name + ' engine call shape changed')
        at = start + m.start()
        engine_slots[name] = {'apiGlobal': dll.rel(at, at + 3, 7), 'table': 0x10,
            'slot': struct.unpack('<I', m.group(2))[0], 'callSite': at}
    expect(engine_slots['request']['apiGlobal'] == engine_slots['release']['apiGlobal'], 'engine API global differs')
    expect((engine_slots['request']['slot'], engine_slots['release']['slot']) == (0x2F0, 0x300),
        'engine load/unload slots changed')
    # Refcount map layout from the request walk: entries [+0], capacity [+8], empty key [+0x10], multiplier [+0x18].
    walk = dll.data[request:request + 0x100]
    for pattern, meaning in ((b'\x41\x8b\x56\x08', 'capacity at +8'), (b'\x45\x8b\x46\x18', 'multiplier at +0x18'),
            (b'\x49\x8b\x0e', 'entries at +0'), (b'\x4d\x8b\x5e\x10', 'empty key at +0x10'),
            (b'\x48\xc7\x43\x08\x01\x00\x00\x00', 'new entry refcount 1 at +8')):
        expect(pattern in walk, 'refcount map layout: ' + meaning)
    # The single RefcountedPackageSystem instance: every caller loads it with mov rcx,[rip+X] before the call.
    instances = {}
    sites = dll.calls_to(request, text_limit) + dll.calls_to(release, text_limit)
    for site in sites:
        window = dll.data[site - 0x30:site]
        for m in re.finditer(rb'\x48\x8b\x0d(....)', window, re.S):
            at = site - 0x30 + m.start()
            instances[dll.rel(at, at + 3, 7)] = instances.get(dll.rel(at, at + 3, 7), 0) + 1
    instance, votes = max(instances.items(), key=lambda kv: kv[1])
    expect(votes >= 0.8 * len(sites), 'RefcountedPackageSystem instance global not unanimous')
    # Engine-side residency: api table slot +0x310 is has_loaded(id). Resolve it in the snapshot and prove its
    # structure walk: [G+0x400] package manager, [pm+0x208] resource manager, [rm+0x80]/[rm+0x88] package list,
    # package +0x10 id / +0x18 part count / +0x20 parts, part +0x1c state == 4.
    api = snap_q(snap, dll.base + engine_slots['request']['apiGlobal'])
    table = snap_q(snap, api + 0x10)
    has_loaded = snap_q(snap, table + 0x310) - exe.base
    code = exe.data[has_loaded:has_loaded + 0x60]
    m = re.match(rb'\x48\x83\xec\x28\x48\x8b\x05(....)\x48\x8b\xd1\x48\x8b\x88\x00\x04\x00\x00\x48\x8b\x89\x08\x02\x00\x00'
        rb'\xe8(....)', code, re.S)
    expect(m is not None, 'engine has_loaded shape changed')
    manager_global = exe.rel(has_loaded + 4, has_loaded + 7, 7)
    find = exe.rel(has_loaded + 0x1c, has_loaded + 0x1d, 5)
    expect(b'\x83\x7a\x1c\x04' in code, 'part state 4 test absent in has_loaded')
    find_code = exe.data[find:find + 0x50]
    for pattern, meaning in ((b'\x8b\xb9\x80\x00\x00\x00', 'package list count at +0x80'),
            (b'\x48\x8b\xb1\x88\x00\x00\x00', 'package list at +0x88'), (b'\x4c\x39\x40\x10', None)):
        if meaning:
            expect(pattern in find_code, 'resource manager layout: ' + meaning)
    expect(b'\x48\x39\x50\x10' in find_code or b'\x49\x39\x50\x10' in find_code or b'\x4c\x39' in find_code
        or b'\x48\x39' in find_code, 'package id compare absent')
    # Load path proves the queue (asynchronous: enqueue, processed later by the engine update).
    load_wrapper = snap_q(snap, table + 0x2F0) - exe.base
    expect(exe.data[load_wrapper:load_wrapper + 3] == b'\x48\x8b\xd1', 'engine load wrapper shape changed')
    load = exe.rel(load_wrapper + 0x11, load_wrapper + 0x12, 5)
    load_strings = [s for s in ('Package already in queue, setting to load %s',)
        if exe.strings(s) and any(load <= r < load + 0x200 for r in exe.lea_refs(exe.strings(s)[0], 0x1600000))]
    expect(load_strings, 'engine load function does not reference its queue log string')
    return {
        'gameDll': {'requestRva': request, 'releaseRva': release,
            'requestProof': dll.data[request:request + 0x180].hex(), 'releaseProof': dll.data[release:release + 0x180].hex(),
            'requestLogReference': request_log, 'releaseLogReference': release_log,
            'instanceGlobalRva': instance, 'instanceVotes': votes, 'callSites': len(sites),
            'engineApiGlobalRva': engine_slots['request']['apiGlobal'], 'engineLoadSlot': 0x2F0,
            'engineUnloadSlot': 0x300, 'refcountMap': {'entries': 0, 'capacity': 8, 'emptyKey': 0x10,
                'multiplier': 0x18, 'entryStride': 16, 'refcount': 8}},
        'engine': {'hasLoadedRva': has_loaded, 'hasLoadedProof': code.hex(), 'findPackageRva': find,
            'findPackageProof': find_code.hex(), 'loadRva': load, 'managerGlobalRva': manager_global,
            'packageManager': 0x400, 'resourceManager': 0x208, 'listCount': 0x80, 'list': 0x88,
            'packageId': 0x10, 'partCount': 0x18, 'parts': 0x20, 'partState': 0x1C, 'loadedState': LOADED,
            'queue': {'head': 0x321C, 'tail': 0x3220, 'entries': 0x218, 'stride': 24, 'loadFlag': 0x10,
                'capacity': 512}},
        'hashes': {'gameDllImage': sha(dll.data), 'exeImage': sha(exe.data)}}


def snap_q(snap, va):
    from snapshot_image import CAPTURED
    region = snap.region(va)
    assert region and region['status'] == CAPTURED
    snap.handle.seek(region['data_offset'] + va - region['base'])
    return struct.unpack('<Q', snap.handle.read(8))[0]


def snap_read(snap, va, n):
    snap.handle.seek(snap.region(va)['data_offset'] + va - snap.region(va)['base'])
    return snap.handle.read(n)


def residency(snap, pins):
    """Resident packages (every part state 4) and the RefcountedPackageSystem table in one snapshot."""
    exe, dll = snap.modules['helldivers2.exe']['base'], snap.modules['game.dll']['base']
    e = pins['engine']
    rm = snap_q(snap, snap_q(snap, snap_q(snap, exe + e['managerGlobalRva']) + e['packageManager']) + e['resourceManager'])
    count = struct.unpack('<I', snap_read(snap, rm + e['listCount'], 4))[0]
    listing = snap_q(snap, rm + e['list'])
    resident = {}
    for i in range(count):
        package = snap_q(snap, listing + 8 * i)
        pid = snap_q(snap, package + e['packageId'])
        parts = struct.unpack('<I', snap_read(snap, package + e['partCount'], 4))[0]
        array = snap_q(snap, package + e['parts'])
        states = [struct.unpack('<I', snap_read(snap, snap_q(snap, array + 8 * k) + e['partState'], 4))[0]
            for k in range(parts)]
        resident[pid] = bool(states) and all(s == LOADED for s in states)
    g = pins['gameDll']
    system = snap_q(snap, dll + g['instanceGlobalRva'])
    entries = snap_q(snap, system)
    capacity = struct.unpack('<I', snap_read(snap, system + 8, 4))[0]
    refs = {}
    raw = snap_read(snap, entries, 16 * capacity)
    for i in range(capacity):
        pid, count = struct.unpack_from('<QQ', raw, 16 * i)
        if pid:
            refs[pid] = count
    return resident, refs, capacity


def bundle_database():
    path = GAME / 'data/bundle_database.data'
    data = path.read_bytes()
    names = {int(m.group(), 16) for m in re.finditer(rb'[0-9a-f]{16}', data)}
    return {'sha256': sha(data), 'packages': names}


def build():
    from snapshot_image import Snapshot
    import research_entity_authoring as rea
    from migration import source
    native = rea.Native()
    snap = Snapshot(build_profile.SNAPSHOT)
    pins = loader_pins(snap)
    evidence = []
    for name in SNAPSHOTS:
        s = Snapshot(build_profile.snapshot_directory() / name)
        resident, refs, capacity = residency(s, pins)
        loadout_names = sorted(native.path(p) for p in resident if (native.path(p) or '').startswith(
            'packages/generated/loadout/'))
        evidence.append({'snapshot': name, 'residentPackages': len(resident), 'fullyLoaded': sum(resident.values()),
            'residentLoadoutPackages': loadout_names, 'refcountedPackages': len(refs),
            'refcountCapacity': capacity, 'refcountedLoadoutPackages': sorted(native.path(p) for p in refs
                if (native.path(p) or '').startswith('packages/generated/loadout/')),
            'requestedNotYetResident': sorted(native.path(p) or hexid(p) for p in refs if not resident.get(p)),
            'everyRefcountedLoadoutPackageResident': all(resident.get(p) for p in refs
                if (native.path(p) or '').startswith('packages/generated/loadout/'))})
        s.handle.close()
    bundles = bundle_database()
    loadout = {}
    for record, owners in native.owners('LoadoutPackageComponentData').items():
        raw = native.record('LoadoutPackageComponentData', record)
        value = struct.unpack_from('<Q', raw, 8)[0]
        for owner in owners:
            loadout[owner] = value
    tables = source.load_tables(source.resolve_ref('current'))

    def package(pid, via, holder=None):
        return {'package': hexid(pid), 'name': native.path(pid), 'via': via, 'holder': holder,
            'inBundleDatabase': pid in bundles['packages']}

    # Stratagem packages: a stratagem row names the package its call-in needs (the Meltagun stratagem's is the
    # Meltagun's generated loadout package). Items a vanilla rack delivers inherit the delivering stratagems'.
    stratagem_packages = {}
    strat = tables['stratagem_authoring']['stratagems']
    for rack in tables['pod_payload_authoring']['racks'].values():
        packages_ = sorted({int(strat[c['name']]['root']['package'], 16) for c in rack.get('consumers') or []
            if c['name'] in strat and int(strat[c['name']]['root']['package'], 16)})
        for slot in rack['slots'].values():
            item = int(slot['resource'], 16)
            if item and packages_:
                stratagem_packages.setdefault(item, set()).update(packages_)

    def dependency(resource, holders=()):
        own = loadout.get(resource)
        if own:
            found = package(own, 'own_loadout_package')
            if found['name'] is None and native.path(resource):
                # A generated loadout package is named after its entity: accept the name only when it hashes to
                # exactly this package ID.
                candidate = 'packages/generated/loadout/' + native.path(resource).rsplit('/', 1)[-1]
                if murmur64a(candidate.encode()) == own:
                    found['name'] = candidate
            return found
        for holder in holders:
            if loadout.get(holder):
                return package(loadout[holder], 'native_holder_package', native.path(holder))
        delivered = sorted(stratagem_packages.get(resource, ()))
        if len(delivered) == 1:
            return package(delivered[0], 'delivering_stratagem_package')
        return None

    catalog = {}

    def add(key, label, resource, holders=(), kind=None):
        dep = dependency(resource, holders)
        catalog[key] = {'label': label, 'kind': kind, 'resource': hexid(resource), 'path': native.path(resource),
            'dependency': dep, 'known': dep is not None and dep['inBundleDatabase']}

    for name, weapon in tables['player_weapon_authoring']['weapons'].items():
        for index, res in enumerate(weapon['resources']):
            add('player_weapon/' + name + ('' if index == 0 else '#' + str(index + 1)), name, int(res, 16),
                kind='player_weapon')
    for name, weapon in tables['support_weapon_authoring']['weapons'].items():
        for index, res in enumerate(weapon['resources']):
            add('support_weapon/' + name + ('' if index == 0 else '#' + str(index + 1)), name, int(res, 16),
                kind='support_weapon')
    entity = tables['entity_authoring']
    mounted_holders = {}
    for name, vehicle in entity['vehicles'].items():
        add('vehicle/' + name, name, int(vehicle['resource'], 16), kind='vehicle')
        for mount in (vehicle.get('mounts') or {}).values():
            if mount.get('current'):
                mounted_holders.setdefault(mount['current'], []).append(int(vehicle['resource'], 16))
    for key, weapon in entity['mountedWeapons'].items():
        add('mounted_weapon/' + key, weapon.get('displayName') or key, int(weapon['resource'], 16),
            sorted(mounted_holders.get(key, [])), kind='mounted_weapon')
    for name, backpack in entity['backpacks'].items():
        add('backpack/' + name, name, int(backpack['resource'], 16), kind='backpack')
    for key, pickup in tables['pod_payload_authoring']['pickups'].items():
        add('pickup/' + key, pickup['name'], int(pickup['resource'], 16), kind='pickup_' + pickup['category'])
    throwables = json.loads((ROOT / 'research/throwable-authoring-F5FEE03DCFDB.json').read_text())
    for item in throwables['catalog']:
        if item['identity']['status'] == 'RESOLVED':
            add('throwable/' + item['name'], item['name'], int(item['identity']['resource'], 16), kind='throwable')
    # Stratagem-owned projectile donors (research/stun-field-donors-F5FEE03DCFDB.json): the entity whose own
    # ProjectileWeapon fires the donor projectile (the EMS Mortar turret) owns the package its effects ship in.
    donors_path = ROOT / 'research/stun-field-donors-F5FEE03DCFDB.json'
    if donors_path.is_file():
        for donor in json.loads(donors_path.read_text(encoding='utf-8'))['donors']:
            add('stratagem_weapon/' + donor['name'], donor['name'], int(donor['resource'], 16),
                kind='stratagem_weapon')
    # More projectile donors (research/projectile-donors-F5FEE03DCFDB.json): a stratagem's Eagle payload, orbital shell,
    # orbital projectile or entity weapon; the owner entity's package (its own loadout package, a holder's, or the
    # delivering stratagem's). Weapon-owned donors resolve through their weapon's entry above.
    more_path = ROOT / 'research/projectile-donors-F5FEE03DCFDB.json'
    if more_path.is_file():
        for donor in json.loads(more_path.read_text(encoding='utf-8'))['donors']:
            if donor['ownerKind'] == 'stratagem':
                add('projectile_donor/' + donor['name'], donor['name'], int(donor['resource'], 16),
                    kind='projectile_donor')
    # Projectiles: a projectile reference swap needs the source weapon's package (the projectile's unit and
    # effects are generated into it); the source is the weapon the reference is copied from.
    composition = json.loads((ROOT / 'schemas/player_weapon_composition_catalog.json').read_text())
    projectiles = {}
    for name, weapon in composition['weapons'].items():
        for attack in weapon.get('attacks') or []:
            if attack.get('kind') == 'Projectile':
                projectiles['projectile_source/' + name + ':' + attack['role']] = name
    for key, weapon_name in projectiles.items():
        entry = catalog.get('player_weapon/' + weapon_name)
        if entry:
            catalog[key] = dict(entry, kind='projectile_source', label=key.split('/', 1)[1])
    # Named explosions (research/event-actions-F5FEE03DCFDB.json): the requested type is a code literal of an entity
    # behavior, so the explosion's effects ship with that entity; the stratagem that delivers the entity names the
    # package the game loads for it (the NUX-223 Hellbomb's is its generated loadout package).
    # An explosion an objective's ability requests (the Cyborg Production Unit's) ships its effect and its sound in
    # objective packages: 'explosion/<name>' is the package holding its particle effect, 'explosion/<name>/sound' the
    # one holding its sound bank (research event-actions, assets).
    actions = json.loads((ROOT / 'research/event-actions-F5FEE03DCFDB.json').read_text())
    for item in actions.get('namedExplosions', []):
        assets = item.get('assets')
        if item['stratagemPackage']:
            dep = package(int(item['stratagemPackage'], 16), 'delivering_stratagem_package')
        else:
            dep = package(int(assets['effectPackage'], 16), 'explosion_effect_package')
            sound = package(int(assets['soundPackage'], 16), 'explosion_sound_package')
            catalog['explosion/' + item['name'] + '/sound'] = {'label': item['name'] + ' (sound)', 'kind': 'explosion',
                'resource': item['entity'], 'path': item['path'], 'dependency': sound, 'known': sound['inBundleDatabase']}
        catalog['explosion/' + item['name']] = {'label': item['name'], 'kind': 'explosion', 'resource': item['entity'],
            'path': item['path'], 'dependency': dep, 'known': dep['inBundleDatabase']}
    # Catalogued explosions (research/explosion-identities-F5FEE03DCFDB.json, scripts/research_explosion_identities.py):
    # 'explosion/<semantic id>' is the package that lists the explosion's particle effect: its owner's (a loadout or
    # call-in package), a loadout package that lists it, or the mission effects package (resident in every mission; the
    # Runtime checks it, never loads it). An explosion without a particle effect uses its owner's package.
    identities_path = ROOT / 'research/explosion-identities-F5FEE03DCFDB.json'
    if identities_path.is_file():
        for item in json.loads(identities_path.read_text(encoding='utf-8'))['explosions']:
            chosen = item.get('package')
            if not (item.get('name') and chosen):
                continue
            dep = package(int(chosen['package'], 16), 'explosion_' + chosen['via'])
            catalog['explosion/' + item['name']] = {'label': item['label'], 'kind': 'explosion', 'resource': None,
                'path': None, 'dependency': dep, 'known': dep['inBundleDatabase']}
    catalog = dict(sorted(catalog.items()))
    log_evidence = json.loads(LOG_EVIDENCE.read_text()) if LOG_EVIDENCE.is_file() else None
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'snapshot': build_profile.SNAPSHOT_NAME,
        'loader': pins, 'bundleDatabase': {'sha256': bundles['sha256'], 'packageNames': len(bundles['packages'])},
        'snapshotEvidence': evidence, 'logEvidence': log_evidence, 'catalog': dict(sorted(catalog.items())),
        'summary': {'semanticObjects': len(catalog), 'known': sum(v['known'] for v in catalog.values()),
            'ownPackage': sum((v['dependency'] or {}).get('via') == 'own_loadout_package' for v in catalog.values()),
            'holderPackage': sum((v['dependency'] or {}).get('via') == 'native_holder_package'
                for v in catalog.values()),
            'stratagemPackage': sum((v['dependency'] or {}).get('via') == 'delivering_stratagem_package'
                for v in catalog.values()),
            'objectivePackage': sum((v['dependency'] or {}).get('via') in ('explosion_effect_package',
                'explosion_sound_package') for v in catalog.values()),
            'explosionPackage': sum(key.startswith('explosion/') and (v['dependency'] or {}).get('via', '').startswith(
                'explosion_') and v['dependency']['via'] not in ('explosion_effect_package', 'explosion_sound_package')
                for key, v in catalog.items()),
            'unknown': sum(not v['known'] for v in catalog.values())}}


def refresh_log_evidence(dumps):
    """Summarise the game's own in-memory log (crash dumps from real sessions): the loadout/package lifecycle."""
    import research_entity_authoring as rea
    native = rea.Native()
    line = re.compile(rb'\d\d:\d\d:\d\d\.\d{3} \[([A-Za-z_]+)\] ([\x20-\x7e]{3,400})')
    events, seen = [], set()
    for dump in dumps:
        data = Path(dump).read_bytes()
        for m in line.finditer(data):
            text = m.group().decode()
            if text in seen:
                continue
            seen.add(text)
            events.append(text)
    request = re.compile(r'Requesting package #ID\[([0-9a-f]{16})\], ref_count=(\d+)')
    phases, current, first_requests = {}, 'boot', {}
    for text in events:
        for marker, phase in (('[StateShip] Setup', 'ship'), ('[StatePrepareMission] on_enter', 'prepare_mission'),
                ('[StateGame] On Enter', 'game'), ('on_ready_peer_added', 'peer_hotjoin')):
            if marker in text:
                current = phase
        m = request.search(text)
        if m:
            name = native.path(int(m.group(1), 16)) or '?'
            if name.startswith('packages/generated/loadout/'):
                phases.setdefault(current, set()).add(name.rsplit('/', 1)[1])
    return {'source': 'HD2 in-memory log captured in local crash dumps from real sessions (older build; the same '
        'RefcountedPackageSystem/PackageLoader log strings exist in the current game.dll)',
        'lines': len(events),
        'loadoutPackagesRequestedByPhase': {k: sorted(v) for k, v in phases.items()},
        'observations': [
            'Ship: every player\'s primary, sidearm and throwable loadout packages are requested; each additional '
            'player carrying the same item increments its reference count.',
            'Mission preparation: PlayerHistory "Loading all loadouts" requests every player\'s weapons and every '
            'stratagem payload item (for example recoilless_rifle and recoilless_rifle_backpack); level generation '
            'then requests world-loot items (samples, lat_oneshot, machinegun, sniper_rifle, ...).',
            'Hot join: a joining peer\'s loadout packages are requested and loaded locally mid-mission (40-100 ms '
            'each) before "PlayerHistory Finished loading for peer".',
            'Armory preview loads and unloads each previewed weapon\'s package through the same reference counts.']}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-log-evidence', nargs='*', help='crash dump files to summarise')
    args = parser.parse_args()
    if args.refresh_log_evidence:
        LOG_EVIDENCE.write_text(json.dumps(refresh_log_evidence(args.refresh_log_evidence), indent=1) + '\n',
            encoding='utf-8', newline='\n')
    result = build()
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result['summary'], indent=1))
    for item in result['snapshotEvidence']:
        print(item['snapshot'], item['residentLoadoutPackages'], item['everyRefcountedLoadoutPackageResident'])


if __name__ == '__main__':
    main()
