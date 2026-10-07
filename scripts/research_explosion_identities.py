"""Explosion identities: who requests each vanilla explosion type (ExplosionSettings, 422 rows of build F5FEE03DCFDB),
named from the game's own data and code, with the package that ships its effect. Read-only and offline (the pinned
datalibrary, the retained snapshots' game.dll image and settings table, the installed game data); nothing is written to
game memory.

Every name comes from a typed reference, strongest first:

1. ``data``: a member the type library types ``ExplosionType`` holds the type:
   * ProjectileInfo +144 (impact) / +156 (expiry) of a projectile row; the projectile is named by its own owners
     (research/projectile-identities-F5FEE03DCFDB.json: what fires it, an orbital's shell, an Eagle's payload, ...);
   * BeamInfo +96 of a beam row; the beam by the BeamWeaponComponent that fires it;
   * an entity component member: ExplosiveComponent +36 (the detonation: the explosive update requests its record
     +0x24, research/event-actions) and +40, WeaponChargeComponent +200 (the overcharge explosion,
     research/charge-explosions), BackblastComponent +8, MinefieldComponent +24, ProjectileClusterComponent +4,
     DisplacementComponent +56, GibEntityComponent's +24, CrashingActorInfo +24 of RagdollSync and VehicleCrash;
   * a customization entity delta that patches one of those members.
   Component owners are named from the Runtime's own catalogues (research_projectile_identities.catalogue_names), else
   from their resource path.
2. ``code``: a literal passed as the type to the game's explosion request (RequestExplosion 0x13C0A80) or to one of the
   wrappers proven to pass their type argument on unchanged (the behavior, second and five ability explosion wrappers;
   ``WRAPPERS``), at a call site whose straight-line block sets it (scan.literals). The calling code is attributed to the
   behavior or ability dispatcher entries that run it (directly or through up to three caller levels); a BehaviorId
   names the entities whose BehaviorComponent holds it, an AbilityId the entities whose typed AbilityId members hold it
   or whose behavior plays it (a literal passed to the ability play 0x4C3210).
3. ``chain``: the explosion is the impact or expiry of a projectile that only another explosion releases (its shrapnel,
   ExplosionInfo +84): it is named after that explosion.

A row referenced by more than one owner is ``shared`` (an edit changes every one of them). Each named explosion gets a
semantic id ``<family>/<owner>/<role>`` (``weapon/r36_eruptor/impact``, ``stratagem/orbital_gas_strike/shell_impact``).

Packages: the effect an explosion draws is its row's particle resource (+56). An owner's package (its loadout package,
a stratagem's call-in package, a named explosion's package; research/package-residency) holds the effect when the
installed game data lists that particle resource in that package; else a generated loadout package that lists it is
used. Faction content and objective packages are never chosen (the Runtime does not load faction content); a row
without a particle effect uses its owner's package. ``package`` is None when nothing is proven.

Settings table: in every mission snapshot, game+0x37CC920 + 8 * type points at a record that equals the pinned row
byte for byte outside its relocated array (+40..+56), for every type below the request's bound (0x1A7).

Output: research/explosion-identities-F5FEE03DCFDB.json and research/docs/explosion-identities-F5FEE03DCFDB.md;
``--check`` compares instead of writing.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from scan import tables as T  # noqa: E402
from scan.settings import SettingsView  # noqa: E402

OUTPUT = ROOT / 'research/explosion-identities-F5FEE03DCFDB.json'
DOC = ROOT / 'research/docs/explosion-identities-F5FEE03DCFDB.md'
PROJECTILES = ROOT / 'research/projectile-identities-F5FEE03DCFDB.json'
RESIDENCY = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
ACTIONS = ROOT / 'research/event-actions-F5FEE03DCFDB.json'
STRATAGEMS = ROOT / 'schemas/stratagem_authoring_catalog.json'
MISSION_SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
SETTINGS_TABLE, TYPE_BOUND, STRIDE = 0x37CC920, 0x1A7, 152
RELOCATED = (40, 56)          # the row's array member: a file offset in the data, a pointer in memory
PARTICLES = 0xA8193123526FAD64
# The mission's common effects package: resident in every in-mission retained snapshot and in none aboard the ship
# (re-proven in mission_package_evidence). An effect it lists is resident whenever a mission is; the Runtime never
# loads it (about 300 MB), it checks that it is resident.
MISSION_PACKAGES = ('packages/content/effects_mission',)
SHIP_SNAPSHOTS = ['F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap']
REQUEST = 0x13C0A80
# Functions whose type argument reaches the request unchanged: (register at entry, the instruction that keeps it, the
# instruction that passes it on, the call that passes it). Each is re-proven below (the keeping register is written
# once in the function).
WRAPPERS = {
    0x13C6D30: {'name': 'second explosion wrapper', 'register': 'r9d', 'keep': (0x13C6D55, 'mov esi, r9d'),
        'pass': (0x13C6D78, 'mov r8d, esi'), 'call': (0x13C6DE4, 'call 0x13c0a80')},
    0x4C89C0: {'name': 'behavior explosion wrapper', 'register': 'edx', 'keep': (0x4C89F4, 'mov r14d, edx'),
        'pass': (0x4C8A6D, 'mov r9d, r14d'), 'call': (0x4C8A86, 'call 0x13c6d30')},
    0x11AD240: {'name': 'ability explosion wrapper', 'register': 'edx', 'keep': (0x11AD279, 'mov r14d, edx'),
        'pass': (0x11AD416, 'mov r8d, r14d'), 'call': (0x11AD464, 'call 0x13c0a80')},
    0x11AD4A0: {'name': 'ability explosion wrapper 2', 'register': 'edx', 'keep': (0x11AD4DC, 'mov ebp, edx'),
        'pass': None, 'call': (0x11AD6A2, 'call 0x13c0a80')},
    0x11AD6E0: {'name': 'ability explosion wrapper 3', 'register': 'edx', 'keep': (0x11AD6F9, 'mov esi, edx'),
        'pass': None, 'call': (0x11AD792, 'call 0x13c6d30')},
    0x11AD7E0: {'name': 'ability explosion wrapper 4', 'register': 'edx', 'keep': (0x11AD824, 'mov r14d, edx'),
        'pass': None, 'call': (0x11AD991, 'call 0x13c0a80')},
    0x11AD9D0: {'name': 'ability explosion wrapper 5', 'register': 'edx', 'keep': (0x11ADA0C, 'mov r14d, edx'),
        'pass': None, 'call': (0x11ADBAB, 'call 0x13c0a80')},
}
ABILITY_PLAY = 0x4C3210
DISPATCH_PINS = [
    (0x4966EA, 'cmp edx, 0x2b4', 'behavior event dispatcher: BehaviorId - 1 <= 0x2B4'),
    (0x496708, 'mov edx, dword ptr [rcx + rax*4 + 0x4a0154]', 'behavior dispatcher jump table'),
    (0x11509E9, 'cmp edx, 0xb32', 'ability dispatcher: AbilityId - 1 <= 0xB32'),
    (0x11509FC, 'mov edx, dword ptr [r10 + rdx*4 + 0x115c784]', 'ability dispatcher jump table'),
    (0x3571D9, 'mov edx, 0x38a', 'a behavior plays AbilityId 906 ...'),
    (0x3571E1, 'call 0x4c3210', '... through the ability play'),
    (0x13C0ADB, 'mov dword ptr [rdi + rcx + 0x34], r8d', 'the request stores argument 3 as the ExplosionType'),
]
BEHAVIOR_TABLE, BEHAVIOR_COUNT = 0x4A0154, 0x2B5
ABILITY_TABLE, ABILITY_COUNT = 0x115C784, 0xB33
# Entity component members typed ExplosionType, and what each one is (a reviewed role; the member's meaning).
COMPONENT_ROLES = {
    ('ExplosiveComponentData', '36'): 'detonation',
    ('ExplosiveComponentData', '40'): 'explosive_40',
    ('WeaponChargeComponentData', '200'): 'overcharge',
    ('BackblastComponentData', '8'): 'backblast',
    ('MinefieldComponentData', '24'): 'mine',
    ('ProjectileClusterComponentData', '4'): 'cluster',
    ('DisplacementComponentData', '56'): 'displacement',
    ('GibEntityComponentData', '24.0'): 'gib',
}
CRASH = {'RagdollSyncComponentData': 'ragdoll_crash', 'VehicleCrashComponentData': 'vehicle_crash'}
# The projectile identity roles (research_projectile_identities.ROLES values) as id parts.
PROJECTILE_ROLES = {'fires': '', 'projectile member +576': 'function_', 'magazine round pattern': 'magazine_',
    'rounds feed': 'rounds_', 'charge level 1': 'charge_1_', 'charge level 2': 'charge_2_',
    'charge level 3': 'charge_3_', 'heat level 1': 'heat_1_', 'heat level 2': 'heat_2_', 'heat level 3': 'heat_3_',
    'orbital shell': 'shell_', 'Eagle payload projectile': 'payload_', 'objective shell': 'objective_shell_',
    'orbital ability projectile': 'orbital_', 'guided missile projectile': 'missile_', 'spray projectile': 'spray_'}
# Owner categories (catalogue_names) -> family; their order is the naming priority.
FAMILIES = [('player weapon', 'weapon'), ('support weapon', 'support_weapon'), ('throwable', 'throwable'),
    ('stratagem payload', 'stratagem'), ('stratagem deployed entity', 'stratagem'), ('backpack', 'backpack'),
    ('vehicle', 'vehicle'), ('vehicle weapon', 'vehicle'), ('enemy', 'enemy'), ('weapon of enemy', 'enemy'),
    ('mounted', 'mounted'), ('entity', 'entity')]
REFERENCE_ORDER = {'named': -1, 'projectile': 0, 'beam': 1, 'component': 2, 'delta': 3, 'code': 4, 'chain': 5}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def f32(raw, at):
    return round(struct.unpack_from('<f', raw, at)[0], 6)


def hexid(value):
    return '0x%016X' % value


def slug(text):
    text = re.sub(r"[\-./'’]", '', str(text).lower())
    return re.sub(r'[^a-z0-9]+', '_', text).strip('_')


def family_of(category):
    if category.startswith('mounted on '):
        # A mounted entity is named by what mounts it: its family is the mounter's.
        return family_of(category[len('mounted on '):])
    for prefix, family in FAMILIES:
        if category == prefix or category.startswith(prefix + ' ') or (prefix == 'mounted' and
                category.startswith('mounted')):
            return family if family != 'mounted' else 'entity'
    return 'entity'


def priority(category):
    for index, (prefix, _) in enumerate(FAMILIES):
        if category == prefix or category.startswith(prefix + ' ') or (prefix == 'mounted' and
                category.startswith('mounted')):
            return index
    return len(FAMILIES)


# ------------------------------------------------------------------------------------------------- owners
class Owners:
    """Entity resource -> its catalogue name (category, name), else its path, from the Runtime's catalogues; an entity
    with neither is named by the entity whose reviewed resource member holds it (``REFERRERS``: an item an inventory
    carries, the entity a weapon fires instead of a projectile, a mount slot, an entity spawned on players)."""

    REFERRERS = {('InventoryComponentData', '24'): 'inventory', ('ProjectileWeaponComponentData', '40'): 'fired',
        ('SpawnOnPlayersComponentData', '16'): 'spawned_on_players'}

    def __init__(self, tables):
        import research_projectile_identities as identities
        self.tables = tables
        self.names = identities.catalogue_names(tables)
        self._referrers = None

    def referrers(self):
        """resource -> [(referrer, component, member path, link)] from the reviewed resource members."""
        if self._referrers is None:
            self._referrers = collections.defaultdict(list)
            for component in self.tables.component_names():
                try:
                    table = self.tables.component(component)
                except ValueError:
                    continue
                members = [m for m in table.members() if (component, m.path) in self.REFERRERS
                    or (component == 'MountComponentData' and re.fullmatch(r'0\[\d+\]\.0', m.path))]
                for record, owners in table.owner_map().items():
                    raw = table.raw(record)
                    for member in members:
                        value = T.decode(member, raw)
                        if isinstance(value, int) and value:
                            link = self.REFERRERS.get((component, member.path), 'mounted')
                            for owner in owners:
                                self._referrers[value].append((owner, component, member.path, link))
        return self._referrers

    def describe(self, resource, depth=0):
        known = self.names.get(resource) or []
        path = self.tables.paths.get(resource)
        link = None
        if known:
            category, name = known[0]
        elif path:
            category, name = 'entity', path.rsplit('/', 1)[-1]
        else:
            category, name = None, None
            if depth < 2:
                for referrer, component, member, kind in sorted(set(self.referrers().get(resource, []))):
                    found = self.describe(referrer, depth + 1)
                    if found['name']:
                        category, name = found['category'], found['name']
                        link = {'resource': hexid(referrer), 'component': component, 'member': member, 'link': kind,
                            'via': found.get('link')}
                        break
        out = {'resource': hexid(resource), 'category': category, 'name': name, 'path': path,
            'names': [{'category': c, 'name': n} for c, n in known]}
        if link:
            out['link'] = link
        return out


def entity_references(tables, type_name, limit):
    """value -> [(owner, component, member path)] for every member typed ``type_name`` (owned records only)."""
    refs = collections.defaultdict(list)
    for component in tables.component_names():
        try:
            table = tables.component(component)
        except ValueError:
            continue
        members = [m for m in table.members() if m.type_name == type_name]
        if not members:
            continue
        for record, owners in table.owner_map().items():
            raw = table.raw(record)
            for member in members:
                value = T.decode(member, raw)
                for item in (value if isinstance(value, list) else [value]):
                    if isinstance(item, int) and 0 < item <= limit:
                        for owner in owners:
                            refs[item].append((owner, component, member.path, len(owners)))
    return refs


# ------------------------------------------------------------------------------------------------- code literals
def code_evidence(tables, owners):
    """Explosion types passed as code literals, attributed to the dispatcher entries that run the calling code."""
    from scan.xref import CodeImage
    from scan.literals import Attribution, CallLiterals, Dispatcher
    image = CodeImage.from_snapshot('game.dll', MISSION_SNAPSHOTS[1])
    pins = [image.pin(rva, role, asm) for rva, asm, role in DISPATCH_PINS]
    behavior = Dispatcher(image, 'behavior', BEHAVIOR_TABLE, BEHAVIOR_COUNT)
    ability = Dispatcher(image, 'ability', ABILITY_TABLE, ABILITY_COUNT)
    literals = CallLiterals(image, entries=set(behavior.stubs) | set(ability.stubs))
    attribution = Attribution(image, [behavior, ability], depth=3)
    # Each wrapper passes its type on: keep and pass are pinned, the keeping register is written once, and the
    # instruction that sets the outgoing type register in the call's block reads the keeping register.
    wrappers = []
    for function, item in WRAPPERS.items():
        keep = image.pin(item['keep'][0], item['name'] + ': keeps the type', item['keep'][1])
        call = image.pin(item['call'][0], item['name'] + ': passes it on', item['call'][1])
        kept = item['keep'][1].split(',')[0].split()[-1]
        from scan.literals import FAMILIES as REGS
        # Writes before the call (the epilogue restores the register after it).
        writes = [ins.address for ins in image.function_insns(function) if ins.address < item['call'][0] and ins.op_str and
            REGS.get(ins.op_str.split(',')[0].strip()) == REGS[kept] and ins.mnemonic not in ('push', 'pop', 'cmp',
                'test') and not ins.op_str.startswith('qword ptr') and not ins.op_str.startswith('dword ptr')]
        if writes != [item['keep'][0]]:
            raise ValueError('%s: the type register %s is written at %s' % (item['name'], kept, [hex(w) for w in writes]))
        outgoing = 'r8d' if item['call'][1].endswith('13c0a80') else 'r9d'
        block = literals.block(item['call'][0])
        setter = next((i for i in block if REGS.get(i[3].split(',')[0].strip()) == REGS[outgoing]), None)
        if setter is None or setter[2] != 'mov' or REGS.get(setter[3].split(',')[1].strip()) != REGS[kept]:
            raise ValueError('%s: the outgoing type register is not set from %s' % (item['name'], kept))
        if item['pass'] and (setter[0], setter[2] + ' ' + setter[3]) != item['pass']:
            raise ValueError('%s: pass instruction moved' % item['name'])
        wrappers.append({'function': function, 'name': item['name'], 'typeRegister': item['register'], 'keep': keep,
            'pass': image.pin(setter[0], item['name'] + ': sets the outgoing type', setter[2] + ' ' + setter[3]),
            'call': call})
    sites = []
    entry_points = [(REQUEST, 'r8d', 'RequestExplosion')] + [(f, w['register'], w['name']) for f, w in WRAPPERS.items()]
    for target, register, label in entry_points:
        for site, root, value in literals.calls(target, register):
            if root in WRAPPERS and target in (REQUEST, 0x13C6D30):
                continue        # the wrappers themselves (their type is the caller's)
            item = {'site': site, 'function': root, 'entry': label, 'literal': value}
            if value is not None:
                found, complete = attribution.site(site)
                item['dispatchers'] = sorted([d, i] for d, i in found)
                item['complete'] = complete
            sites.append(item)
    # Who owns a BehaviorId / an AbilityId (data), and which behaviors play an ability (code literals).
    behaviors = collections.defaultdict(list)
    table = tables.component('BehaviorComponentData')
    for record, record_owners in table.owner_map().items():
        behaviors[u32(table.raw(record), 0)].extend(record_owners)
    ability_refs = entity_references(tables, 'AbilityId', ABILITY_COUNT)
    plays = collections.defaultdict(set)
    for site, _root, value in literals.calls(ABILITY_PLAY, 'edx'):
        if value:
            found, _complete = attribution.site(site)
            for dispatcher, ident in found:
                if dispatcher == 'behavior':
                    plays[value].add(ident)

    def owners_of(dispatcher, ident):
        out = []
        if dispatcher == 'behavior':
            for resource in sorted(set(behaviors.get(ident, []))):
                out.append(dict(owners.describe(resource), via='BehaviorId %d' % ident))
        else:
            for resource, component, path, _shared in sorted(set(ability_refs.get(ident, []))):
                out.append(dict(owners.describe(resource), via='AbilityId %d (%s +%s)' % (ident, component, path)))
            for behavior_id in sorted(plays.get(ident, ())):
                for resource in sorted(set(behaviors.get(behavior_id, []))):
                    out.append(dict(owners.describe(resource), via='AbilityId %d played by BehaviorId %d' % (ident,
                        behavior_id)))
        return out
    return {'image': image.describe(), 'pins': pins, 'wrappers': wrappers, 'sites': sites, 'owners_of': owners_of,
        'dispatchers': {'behavior': {'table': BEHAVIOR_TABLE, 'entries': BEHAVIOR_COUNT,
            'handlers': len(behavior.handlers)}, 'ability': {'table': ABILITY_TABLE, 'entries': ABILITY_COUNT,
            'handlers': len(ability.handlers)}}}


# ------------------------------------------------------------------------------------------------- settings table
def settings_proof(rows):
    """Every type's settings-table entry in every mission snapshot equals the pinned row (outside +40..+56)."""
    import research_event_state as base
    result = []
    for name in MISSION_SNAPSHOTS:
        mem = base.Mem(name)
        mismatched = []
        for kind, raw in rows.items():
            pointer = mem.ptr(mem.game + SETTINGS_TABLE + 8 * kind)
            record = pointer and mem.read(pointer, STRIDE)
            if not record or record[:RELOCATED[0]] != raw[:RELOCATED[0]] or record[RELOCATED[1]:] != raw[RELOCATED[1]:]:
                mismatched.append(kind)
        zero = mem.ptr(mem.game + SETTINGS_TABLE)
        mem.close()
        result.append({'snapshot': name, 'matched': len(rows) - len(mismatched), 'mismatched': mismatched,
            'zeroEntryNull': not zero})
    return result


# ------------------------------------------------------------------------------------------------- packages
class Packages:
    """Which packages of the installed game data list a resource, their sizes and names."""

    def __init__(self, tables, wanted):
        import hd2_game_data
        import research_package_residency as residency
        self.holders = collections.defaultdict(set)
        self.sizes = collections.Counter()
        for archive, rname, rtype, main, stream, gpu in hd2_game_data.Data().tables():
            self.sizes[int(archive, 16)] += main[1] + stream[1] + gpu[1]
            if rtype == PARTICLES and rname in wanted:
                self.holders[rname].add(int(archive, 16))
        self.bundles = residency.bundle_database()['packages']
        self.tables = tables

    def name(self, package):
        return self.tables.paths.get(package)

    def holds(self, package, particle):
        return package in self.holders.get(particle, ())

    def mission_holder(self, particle):
        for package in sorted(self.holders.get(particle, ())):
            if self.name(package) in MISSION_PACKAGES:
                return package
        return None

    def loadout_holders(self, particle):
        found = [p for p in self.holders.get(particle, ()) if (self.name(p) or '').startswith(
            'packages/generated/loadout/') and p in self.bundles]
        return sorted(found, key=lambda p: (self.sizes[p], p))


def mission_package_evidence(tables):
    """Residency of each MISSION_PACKAGES package in every retained snapshot (the native loader's own state)."""
    import build_profile
    import research_package_residency as residency
    from snapshot_image import Snapshot
    import hd2_game_data
    reference = Snapshot(build_profile.SNAPSHOT)
    try:
        pins = residency.loader_pins(reference)
    finally:
        reference.handle.close()
    wanted = {hd2_game_data.murmur64(name.encode()): name for name in MISSION_PACKAGES}
    out = {name: {'package': hexid(pid), 'mission': [], 'ship': []} for pid, name in wanted.items()}
    for kind, names in (('mission', MISSION_SNAPSHOTS[:3]), ('ship', SHIP_SNAPSHOTS)):
        for snapshot in names:
            snap = Snapshot(build_profile.snapshot_directory() / snapshot)
            try:
                resident, _refs, _capacity = residency.residency(snap, pins)
            finally:
                snap.handle.close()
            for pid, name in wanted.items():
                out[name][kind].append({'snapshot': snapshot, 'resident': bool(resident.get(pid))})
    for name, item in out.items():
        if not all(s['resident'] for s in item['mission']) or any(s['resident'] for s in item['ship']):
            raise ValueError(name + ' is not resident in exactly the in-mission snapshots')
    return out


def owner_packages(owner, residency, stratagems):
    """[(key, package id, via)] an owner's catalogued package dependencies, strongest first."""
    category, name = owner.get('category'), owner.get('name')
    keys = []
    if category == 'player weapon' or (category or '').startswith('player weapon '):
        keys.append('player_weapon/' + name)
    if category == 'support weapon':
        keys.append('support_weapon/' + name)
    if category == 'throwable':
        keys.append('throwable/' + name)
    if category == 'backpack':
        keys.append('backpack/' + name)
    if category in ('vehicle',):
        keys.append('vehicle/' + name)
    out = []
    for key in keys:
        dependency = (residency['catalog'].get(key) or {}).get('dependency')
        if dependency and residency['catalog'][key]['known']:
            out.append((key, int(dependency['package'], 16), dependency['via']))
    if category in ('stratagem payload', 'stratagem deployed entity'):
        entry = stratagems.get(name)
        package = entry and entry['root'].get('package')
        if package and int(package, 16):
            out.append(('stratagem/' + name, int(package, 16), 'stratagem_call_in_package'))
    return out


# ------------------------------------------------------------------------------------------------- build
def build():
    tables = T.pinned()
    settings = SettingsView(tables)
    owners = Owners(tables)
    projectiles = {t['type']: t for t in load(PROJECTILES)['types']}
    residency = load(RESIDENCY)
    stratagems = load(STRATAGEMS)['stratagems']
    actions = load(ACTIONS)
    rows = {kind: raw for _row, kind, raw in settings.table('explosion').rows}
    row_index = {kind: row for row, kind, _raw in settings.table('explosion').rows}
    group = settings.table('explosion')
    if len(rows) != 422 or max(rows) >= TYPE_BOUND:
        raise ValueError('explosion settings table changed: %d rows' % len(rows))

    references = collections.defaultdict(list)
    # 1. Projectile rows, beam rows.
    for _row, kind, raw in settings.table('projectile').rows:
        for offset, phase in ((144, 'impact'), (156, 'expiry')):
            if u32(raw, offset):
                references[u32(raw, offset)].append({'kind': 'projectile', 'projectile': kind, 'phase': phase})
    beam_owners = entity_references(tables, 'BeamType', 64)
    for _row, kind, raw in settings.table('beam').rows:
        if u32(raw, 96):
            references[u32(raw, 96)].append({'kind': 'beam', 'beam': kind,
                'owners': sorted({o for o, _c, _p, _s in beam_owners.get(kind, [])})})
    # 2. Entity component members typed ExplosionType.
    unowned = collections.Counter()
    for component in tables.component_names():
        try:
            table = tables.component(component)
        except ValueError:
            continue
        members = [m for m in table.members() if m.type_name == 'ExplosionType']
        if not members:
            continue
        owned = table.owner_map()
        for record in range(table.count):
            raw = table.raw(record)
            for member in members:
                value = T.decode(member, raw)
                if not isinstance(value, int) or not value:
                    continue
                if record not in owned:
                    unowned[value] += 1
                    continue
                role = COMPONENT_ROLES.get((component, member.path)) or CRASH.get(component)
                if role is None:
                    raise ValueError('unreviewed ExplosionType member %s +%s' % (component, member.path))
                for owner in owned[record]:
                    references[value].append({'kind': 'component', 'component': component, 'member': member.path,
                        'role': role, 'owner': owner, 'recordOwners': len(owned[record])})
    # 3. Customization deltas patching such a member.
    import research_magazine_attachments as attachments
    tables.entity_rows()
    index_types = tables._index_type
    explosion_members = {}
    for component in tables.component_names():
        try:
            table = tables.component(component)
        except ValueError:
            continue
        offsets = [m for m in table.members() if m.type_name == 'ExplosionType']
        if offsets:
            explosion_members[table.type_hash] = (component, offsets)
    deltas, _layout = attachments.entity_deltas((tables.folder / 'generated_entity_deltas.dl_bin').read_bytes())
    for resource, delta in deltas.items():
        for entry in delta['entries']:
            found = explosion_members.get(index_types.get(entry['component']))
            if not found:
                continue
            component, members = found
            for member in members:
                if entry['offset'] <= member.offset < entry['offset'] + entry['size']:
                    value = u32(entry['bytes'], member.offset - entry['offset'])
                    if value:
                        references[value].append({'kind': 'delta', 'component': component, 'member': member.path,
                            'role': COMPONENT_ROLES.get((component, member.path), 'delta'), 'delta': resource})
    # 4. Code literals.
    code = code_evidence(tables, owners)
    for site in code['sites']:
        if site['literal'] and 0 < site['literal'] < TYPE_BOUND:
            references[site['literal']].append({'kind': 'code', 'site': site['site'], 'function': site['function'],
                'entry': site['entry'], 'dispatchers': site['dispatchers'], 'complete': site['complete']})

    # 5. Named explosions (research/event-actions): a reviewed entity behavior's or ability's request literal.
    for named in actions.get('namedExplosions', []):
        references[named['type']].append({'kind': 'named', 'name': named['name'], 'entity': int(named['entity'], 16),
            'requestedBy': named.get('requestedBy') or 'behavior', 'delivered': bool(named.get('deliveredBy'))})

    # Owners of each reference.
    def projectile_owners(kind):
        identity = projectiles.get(kind, {}).get('identity') or {}
        out = []
        for owner in identity.get('owners') or []:
            described = owners.describe(int(owner['resource'], 16))
            out.append(dict(described, role=owner['role']))
        for output in identity.get('outputs') or []:
            if output.get('name') and not out:
                out.append({'resource': None, 'category': 'player weapon' if output.get('owner') == 'player_weapon'
                    else 'attack output', 'name': output['name'], 'path': None, 'names': [], 'role': 'fires'})
        return out, identity.get('submunitionOf') or []

    explosions = {}
    for kind in sorted(rows):
        raw = rows[kind]
        found = []
        chain_sources = []
        for ref in references.get(kind, []):
            if ref['kind'] == 'projectile':
                prj_owners, submunition = projectile_owners(ref['projectile'])
                for owner in prj_owners:
                    found.append(dict(owner, reference='projectile', role=PROJECTILE_ROLES.get(owner['role'],
                        slug(owner['role']) + '_') + ref['phase'], projectile=ref['projectile']))
                for source in submunition:
                    chain_sources.append({'explosion': source['explosion'], 'projectile': ref['projectile'],
                        'phase': ref['phase']})
            elif ref['kind'] == 'beam':
                for resource in ref['owners']:
                    found.append(dict(owners.describe(resource), reference='beam', role='beam', beam=ref['beam']))
            elif ref['kind'] == 'component':
                found.append(dict(owners.describe(ref['owner']), reference='component', role=ref['role'],
                    component=ref['component'], member=ref['member'], recordOwners=ref['recordOwners']))
            elif ref['kind'] == 'delta':
                found.append(dict(owners.describe(ref['delta']), reference='delta', role=ref['role'],
                    component=ref['component'], member=ref['member']))
            elif ref['kind'] == 'named':
                described = owners.describe(ref['entity'])
                category = (described['category'] if described['names'] else 'stratagem payload' if ref['delivered']
                    else 'entity')
                found.append(dict(described, category=category, name=ref['name'], reference='named',
                    role=ref['requestedBy']))
            elif ref['kind'] == 'code':
                for dispatcher, ident in ref['dispatchers']:
                    for owner in code['owners_of'](dispatcher, ident):
                        found.append(dict(owner, reference='code', role=dispatcher, site=ref['site']))
        for owner in found:
            # An owner named through the entity that references it: the link is part of its role.
            link = owner.get('link')
            while link:
                owner['role'] = link['link'] + '_' + owner['role']
                link = link.get('via')
        explosions[kind] = {'owners': found, 'chain': chain_sources}

    # Naming.
    def best(found):
        named = [o for o in found if o.get('name')]
        if not named:
            return None
        # A reviewed named explosion (research/event-actions) keeps its reviewed owner whatever else requests it.
        return sorted(named, key=lambda o: (o['reference'] != 'named', priority(o['category']),
            REFERENCE_ORDER[o['reference']],
            o['role'] != 'impact', o['name'], o['role']))[0]

    names = {}
    for kind, item in explosions.items():
        owner = best(item['owners'])
        if owner:
            names[kind] = ('%s/%s/%s' % (family_of(owner['category']), slug(owner['name']), owner['role']),
                '%s (%s)' % (owner['name'], owner['role'].replace('_', ' ')), family_of(owner['category']))
    # Chains: an explosion only a submunition of a named explosion requests (two passes cover the depth seen).
    for _ in range(3):
        for kind, item in explosions.items():
            if kind in names or not item['chain']:
                continue
            for source in sorted(item['chain'], key=lambda s: (s['explosion'], s['phase'])):
                if source['explosion'] in names and source['explosion'] != kind:
                    base_id, base_label, family = names[source['explosion']]
                    names[kind] = (base_id + '/shrapnel_' + source['phase'], base_label.rsplit(' (', 1)[0] + ' ('
                        + base_label.rsplit(' (', 1)[1].rstrip(')') + ', shrapnel ' + source['phase'] + ')', family)
                    item['owners'].append({'resource': None, 'category': 'explosion', 'name': base_id,
                        'path': None, 'names': [], 'reference': 'chain', 'role': 'shrapnel_' + source['phase'],
                        'explosion': base_id, 'projectile': source['projectile']})
                    break
    # Unique ids: a collision keeps the lowest type's id and numbers the others in type order.
    used = collections.defaultdict(list)
    for kind in sorted(names):
        used[names[kind][0]].append(kind)
    final = {}
    for base_id, kinds in used.items():
        for index, kind in enumerate(kinds):
            _id, label, family = names[kind]
            final[kind] = (base_id if index == 0 else '%s_%d' % (base_id, index + 1), label if index == 0
                else '%s #%d' % (label, index + 1), family)

    # Damage rows: who else uses each DamageInfo row (sharing of explosion.damage.* fields).
    damage_users = collections.Counter()
    for kind_name in settings.kinds():
        if kind_name == 'damage':
            continue
        members = [m for m in settings.members(kind_name) if m.type_name == 'DamageInfoType']
        for _row, kind, raw in settings.table(kind_name).rows:
            for member in members:
                value = T.decode(member, raw)
                if isinstance(value, int) and value:
                    damage_users[value] += 1
    for value, refs in entity_references(tables, 'DamageInfoType', 4096).items():
        damage_users[value] += len({(o, c, p) for o, c, p, _s in refs})
    damage_group = settings.table('damage')
    reviewed = load(ROOT / 'sdk/ExplosionAuthoringCapabilities.json')['explosions'][0]
    if ('0x%08X' % group.settings_type, group.group) != (reviewed['settings']['settingsType'],
            reviewed['settings']['group']) or ('0x%08X' % damage_group.settings_type, damage_group.group) != (
            reviewed['damageSettings']['settingsType'], reviewed['damageSettings']['group']):
        raise ValueError('the explosion or damage settings group differs from the reviewed weapon explosions')
    damage_rows = {kind: raw for _row, kind, raw in settings.table('damage').rows}
    damage_index = {kind: row for row, kind, _raw in settings.table('damage').rows}

    # Packages.
    particles = {kind: struct.unpack_from('<Q', raw, 56)[0] for kind, raw in rows.items()}
    packages = Packages(tables, {p for p in particles.values() if p})
    named_packages = {item['type']: item for item in actions.get('namedExplosions', [])}
    proof = settings_proof(rows)
    mission_packages = mission_package_evidence(tables)
    proven = {kind for kind in rows if all(kind not in p['mismatched'] for p in proof)}

    result = []
    for kind in sorted(rows):
        raw = rows[kind]
        item = explosions[kind]
        damage_type = u32(raw, 4)
        damage = damage_rows.get(damage_type)
        owner_set = {(o.get('resource') or o.get('name'), o['reference'] == 'chain') for o in item['owners']}
        distinct = {o.get('resource') or ('chain', o.get('explosion')) for o in item['owners']}
        unnamed_refs = [r for r in references.get(kind, []) if r['kind'] == 'code' and not r['dispatchers']]
        shared = len(distinct) + (1 if unnamed_refs else 0) + (1 if unowned.get(kind) else 0) > 1
        stats = {'damageType': damage_type, 'innerRadius': f32(raw, 16), 'outerRadius': f32(raw, 20),
            'shockwaveRadius': f32(raw, 24), 'shrapnelCount': u32(raw, 80), 'shrapnelProjectile': u32(raw, 84),
            'arc': u32(raw, 120), 'particle': hexid(particles[kind]) if particles[kind] else None,
            'soundKey': u32(raw, 64), 'statusTemplate': u32(raw, 100), 'fireTemplate': u32(raw, 96)}
        if damage:
            stats['damage'] = {'standard': struct.unpack_from('<i', damage, 4)[0],
                'durable': struct.unpack_from('<i', damage, 8)[0],
                'armorPenetration': [u32(damage, 12 + 4 * i) for i in range(4)],
                'demolition': u32(damage, 28), 'stagger': u32(damage, 32), 'pushForce': u32(damage, 36),
                'statuses': [u32(damage, 44 + 8 * i) for i in range(4) if u32(damage, 44 + 8 * i)],
                'row': damage_index[damage_type], 'users': damage_users.get(damage_type, 0)}
        # Package: an owner's package that lists the particle, else a loadout package that lists it.
        candidates = []
        for owner in sorted([o for o in item['owners'] if o.get('name')], key=lambda o: (priority(o['category']),
                REFERENCE_ORDER[o['reference']], o['name'])):
            for key, package, via in owner_packages(owner, residency, stratagems):
                if (key, package) not in [(c[0], c[1]) for c in candidates]:
                    candidates.append((key, package, via))
        if kind in named_packages:
            named = named_packages[kind]
            package = named.get('stratagemPackage') or (named.get('assets') or {}).get('effectPackage')
            if package:
                candidates.insert(0, ('explosion/' + named['name'], int(package, 16), 'named_explosion_package'))
        chosen = None
        particle = particles[kind]
        for key, package, via in candidates:
            if package not in packages.bundles:
                continue
            if not particle:
                chosen = {'key': key, 'via': via, 'effect': 'no_particle_effect'}
            elif packages.holds(package, particle):
                chosen = {'key': key, 'via': via, 'effect': 'listed_in_package'}
            if chosen:
                chosen.update(package=hexid(package), name=packages.name(package), bytes=packages.sizes[package])
                break
        if chosen is None and particle and packages.mission_holder(particle):
            mission = packages.mission_holder(particle)
            chosen = {'key': None, 'via': 'mission_effects_package', 'effect': 'listed_in_package',
                'package': hexid(mission), 'name': packages.name(mission), 'bytes': packages.sizes[mission],
                'mission': True}
        if chosen is None and particle:
            holders = packages.loadout_holders(particle)
            if holders:
                chosen = {'key': None, 'via': 'effect_loadout_package', 'effect': 'listed_in_package',
                    'package': hexid(holders[0]), 'name': packages.name(holders[0]), 'bytes': packages.sizes[holders[0]]}
        identity = final.get(kind)
        reason = None
        if identity is None:
            refs = references.get(kind, [])
            if not refs and not unowned.get(kind):
                reason = 'no typed reference in the data and no literal in the request code'
            elif unowned.get(kind) and not refs:
                reason = 'held only by component records no entity owns'
            elif item['owners']:
                reason = 'its owners carry no name in the Runtime catalogues or the resource paths'
            elif all(r['kind'] == 'code' and not r['dispatchers'] for r in refs):
                reason = 'requested only by code no behavior or ability dispatcher is proven to run'
            elif all(r['kind'] == 'code' for r in refs):
                reason = 'requested by behaviors or abilities no entity is proven to own'
            elif all(r['kind'] == 'projectile' for r in refs):
                reason = 'the impact or expiry of projectiles nothing proven fires'
            else:
                reason = 'its references (projectiles nothing proven fires, unowned code) name no owner'
        tier = None
        kinds_seen = {o['reference'] for o in item['owners']}
        for candidate_tier, members in (('data', {'projectile', 'beam', 'component', 'delta'}), ('code', {'code', 'named'}),
                ('chain', {'chain'})):
            if kinds_seen & members:
                tier = candidate_tier
                break
        compact_owners = []
        for owner in item['owners']:
            entry = {k: owner[k] for k in ('category', 'name', 'reference', 'role', 'resource', 'path') if owner.get(k)}
            for extra in ('projectile', 'beam', 'component', 'member', 'via', 'site', 'explosion', 'link'):
                if owner.get(extra) is not None:
                    entry[extra] = owner[extra]
            if entry not in compact_owners:
                compact_owners.append(entry)
        result.append({'type': kind, 'row': row_index[kind], 'name': identity[0] if identity else None,
            'label': identity[1] if identity else None, 'family': identity[2] if identity else None,
            'evidenceTier': tier or ('unowned' if unowned.get(kind) else 'none'), 'shared': shared,
            'owners': compact_owners, 'ownerCount': len({o.get('resource') or o.get('name') for o in compact_owners}),
            'references': len(references.get(kind, [])), 'unownedRecords': unowned.get(kind, 0),
            'unattributedCode': [r['site'] for r in unnamed_refs],
            'settingsVerified': kind in proven, 'stats': stats, 'package': chosen, 'unnamedReason': reason})
    by_family = collections.Counter(r['family'] for r in result if r['name'])
    summary = {'types': len(result), 'named': sum(1 for r in result if r['name']),
        'byFamily': dict(sorted(by_family.items())),
        'byTier': dict(sorted(collections.Counter(r['evidenceTier'] for r in result).items())),
        'shared': sum(1 for r in result if r['name'] and r['shared']),
        'withPackage': sum(1 for r in result if r['name'] and r['package']),
        'packageBy': dict(sorted(collections.Counter(r['package']['via'] for r in result if r['name'] and r['package'])
            .items())),
        'settingsVerified': len(proven),
        'unnamedBy': dict(sorted(collections.Counter(r['unnamedReason'] for r in result if not r['name']).items())),
        'codeLiteralSites': sum(1 for s in code['sites'] if s['literal']),
        'codeSitesAttributed': sum(1 for s in code['sites'] if s['literal'] and s.get('dispatchers'))}
    return {'schemaVersion': 1, 'build': 'F5FEE03DCFDB',
        'source': {'datalibrary': 'pinned (scan.tables)', 'projectiles': str(PROJECTILES.relative_to(ROOT)).replace('\\', '/'),
            'packages': str(RESIDENCY.relative_to(ROOT)).replace('\\', '/'), 'code': code['image'],
            'snapshots': MISSION_SNAPSHOTS},
        'layout': {'ExplosionSettings': {'stride': STRIDE, 'damageType': 4, 'innerRadius': 16, 'outerRadius': 20,
            'shockwaveRadius': 24, 'particle': 56, 'soundKey': 64, 'shrapnelCount': 80, 'shrapnelProjectile': 84,
            'fireTemplate': 96, 'statusTemplate': 100, 'arc': 120, 'relocated': list(RELOCATED)},
            'settingsGroup': {'group': group.group, 'settingsType': '0x%08X' % group.settings_type},
            'damageGroup': {'group': damage_group.group, 'settingsType': '0x%08X' % damage_group.settings_type}},
        'settingsTable': {'rva': SETTINGS_TABLE, 'typeBound': TYPE_BOUND, 'observations': proof},
        'missionPackages': mission_packages,
        'code': {'pins': code['pins'], 'wrappers': code['wrappers'], 'dispatchers': code['dispatchers'],
            'sites': [{k: v for k, v in s.items()} for s in code['sites']]},
        'writes': 0, 'protectionChanges': 0, 'summary': summary, 'explosions': result}


def cell(text):
    return str(text).replace('|', '/')


def document(report):
    s = report['summary']
    lines = ['# Explosion identities (build F5FEE03DCFDB)', '',
        'Generated by `scripts/research_explosion_identities.py` from `research/explosion-identities-F5FEE03DCFDB.json`.',
        'Read-only and offline. Every name comes from a typed reference in the game\'s own data or a literal in its',
        'request code; nothing is named from a value or a resemblance.', '',
        '## Evidence', '',
        '- **data**: a member typed `ExplosionType` holds the type: a projectile row\'s impact (+144) or expiry (+156)',
        '  explosion (the projectile named by what fires it, research/projectile-identities), a beam row\'s +96, an',
        '  entity component (ExplosiveComponent +36 detonation and +40, WeaponCharge +200 overcharge, Backblast +8,',
        '  Minefield +24, ProjectileCluster +4, Displacement +56, GibEntity, RagdollSync and VehicleCrash crash',
        '  explosions) or a customization delta patching one of them.',
        '- **code**: a literal passed as the type to the explosion request or to a wrapper proven to pass its type on;',
        '  the calling code is attributed to the behavior or ability dispatcher entries that run it, and those ids to',
        '  the entities that own them (BehaviorComponent, typed AbilityId members, behaviors that play the ability).',
        '- **chain**: the impact or expiry of a projectile only a named explosion releases as shrapnel.', '',
        '| Evidence tier | Types |', '| --- | --- |']
    lines += ['| %s | %d |' % (tier, count) for tier, count in s['byTier'].items()]
    lines += ['', '%d of %d types are named; %d of them are shared (more than one owner); %d have a package proven to'
        % (s['named'], s['types'], s['shared'], s['withPackage']),
        'list their particle effect.', '',
        'All %d types are proven against the game\'s settings table: in every mission snapshot, its entry equals the'
        % s['settingsVerified'],
        'pinned row byte for byte (outside the relocated array at +40..+56).', '',
        '## Named, by family', '', '| Family | Types |', '| --- | --- |']
    lines += ['| %s | %d |' % (family, count) for family, count in s['byFamily'].items()]
    lines += ['', '## Packages', '', '| How the package was found | Named types |', '| --- | --- |']
    meaning = {'own_loadout_package': 'the owner\'s own loadout package lists the effect',
        'native_holder_package': 'a vanilla holder\'s loadout package lists it',
        'delivering_stratagem_package': 'the delivering stratagem\'s package lists it',
        'stratagem_call_in_package': 'the owning stratagem\'s call-in package lists it',
        'named_explosion_package': 'the named explosion\'s package (research/event-actions)',
        'mission_effects_package': 'no owner package lists it; the mission effects package does (resident in every mission; never loaded by the Runtime)',
        'effect_loadout_package': 'neither does; the smallest loadout package that lists it'}
    lines += ['| %s (%s) | %d |' % (via, meaning.get(via, via), count) for via, count in s['packageBy'].items()]
    lines += ['', 'Faction content and objective packages are never chosen; an explosion whose effect ships only there',
        '(most enemy explosions) is editable but has no package, so it is neither a payload donor nor spawnable.', '',
        '## Code literals', '',
        '%d request call sites carry a literal type; %d of them are attributed to behavior or ability dispatcher'
        % (s['codeLiteralSites'], s['codeSitesAttributed']),
        'entries. The wrappers whose type argument reaches the request unchanged:', '',
        '| Wrapper | Type register | Keeps it | Passes it |', '| --- | --- | --- | --- |']
    for w in report['code']['wrappers']:
        lines.append('| %s (0x%X) | %s | 0x%X `%s` | 0x%X `%s` |' % (w['name'], w['function'], w['typeRegister'],
            w['keep']['rva'], w['keep']['asm'], w['pass']['rva'], w['pass']['asm']))
    lines += ['', '## Unnamed', '', '| Why | Types |', '| --- | --- |']
    lines += ['| %s | %d |' % (cell(reason), count) for reason, count in s['unnamedBy'].items()]
    lines += ['', 'Unnamed rows stay out of the public catalogue (`hd2.explosions`): an id without an owner would name',
        'nothing a mod can reason about. They remain listed here by type:', '']
    unnamed = [r for r in report['explosions'] if not r['name']]
    for reason in sorted({r['unnamedReason'] for r in unnamed}):
        kinds = [str(r['type']) for r in unnamed if r['unnamedReason'] == reason]
        lines.append('- %s: %s' % (reason, ', '.join(kinds)))
    lines += ['', '## Limits', '',
        '- A code literal in a function no dispatcher entry is proven to run (directly or through three caller',
        '  levels) names nothing; nor does an indirect call (a virtual or a callback table).',
        '- Explosions requested with a computed type (a value read from data at run time) are covered only through',
        '  the data member that holds the type.',
        '- DestructionSettings (DestructionEffectExplosion +4) and VehicleEffectInfo +28 are typed ExplosionType in the',
        '  type library but are not in the decoded datalibrary; their users are not scanned.',
        '- The sound bank of an explosion (+64, the game\'s sound key) is not resolved here: the package is proven for',
        '  the particle effect.',
        '- A name is the evidence\'s first owner by catalogue priority (player weapon, support weapon, throwable,',
        '  stratagem, backpack, vehicle, enemy, mounted entity, path); `owners` lists every one.', '',
        '## Named explosions', '', '| Name | Label | Shared | Owners | Package |', '| --- | --- | --- | --- | --- |']
    for r in report['explosions']:
        if r['name']:
            lines.append('| `%s` | %s | %s | %d | %s |' % (r['name'], cell(r['label']), 'yes' if r['shared'] else 'no',
                r['ownerCount'], cell((r['package'] or {}).get('name') or ('known' if r['package'] else '-'))))
    lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    report = build()
    text = json.dumps(report, indent=1, sort_keys=True) + '\n'
    doc = document(report)
    if args.check:
        stale = [str(p) for p, body in ((OUTPUT, text), (DOC, doc))
            if not p.exists() or p.read_text(encoding='utf-8') != body]
        if stale:
            raise SystemExit('stale explosion identities: ' + ', '.join(stale))
        print('explosion identities are current')
        return
    with open(OUTPUT, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)
    with open(DOC, 'w', encoding='utf-8', newline='') as handle:
        handle.write(doc)
    print(json.dumps(report['summary'], indent=1))


if __name__ == '__main__':
    main()
