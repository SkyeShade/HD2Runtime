"""Gameplay actions an event script may perform: the game's explosion request (research for hd2.explosions).

Read-only. Proves, on build F5FEE03DCFDB:

1. The request: game.dll 0x13C0A80 appends one explosion to the game's explosion queue (global game+0x346D558):
   count at +0x20 (at most 256; a full queue is refused inside the function), entries of 0x98 bytes from +0x28.
   Its first four arguments are the queue, a pointer to the position, the ExplosionType and the source entity; the
   stack arguments 5 and 6 are the owner entity and the creditor peer id.
2. The argument template: every call site's stack arguments 7..15. The common template (7 = 0, 8 = null, 9 = 1,
   10 = 0, 11..13 = null, 14 = 0, 15 = 0) is what Runtime passes; the call sites that use it are listed.
3. Identity: the queue drain (0x13C0D10) resolves the ExplosionType through the settings pointer table at
   game+0x37CC920 (bounded by 0x1A7). In every mission snapshot, the table entry of every catalogued weapon
   explosion points at a record whose type, damage type and radii are the catalogued ExplosionSettings values.
4. Semantics: the mission snapshots hold a stale request of an R-36 Eruptor shell: ExplosionType 158 (the Eruptor's
   catalogued terminal explosion), source = the Eruptor weapon entity, owner = the local avatar, creditor = the local
   peer. The queue count is 0 in every snapshot: the game drains it each frame.
5. Hellbombs. Neither Hellbomb names its explosion in data: the type is a code literal in the entity's behavior,
   passed through two wrappers (0x4C89C0 -> 0x13C6D30) to the request. The NUX-223 Hellbomb (StratagemType 42
   DropoffHellbomb, payload content/fac_helldivers/hellpod/hellbomb/hellbomb) is the sole owner of BehaviorId 224;
   the behavior dispatcher's table entry 223 calls 0x288360, whose "explode" event (thin hash 0xB3FD1AFF) enters
   state 3, which requests ExplosionType 242 at the "nuke" node. The B-100 Portable Hellbomb (bomb_backpack, sole
   owner of BehaviorId 8) requests ExplosionType 125 the same way. Both settings rows (17 / 25 / 45 m, damage type
   479) are identical in every snapshot. Type 242 is also requested by several mission objectives, so editing its
   settings would change them too; requesting it does not.
   The Cyborg Production Unit's self-destruct (ExplosionType 293) is requested by an ABILITY: the only owner of
   BehaviorId 327 (behavior dispatcher entry 326 -> 0x357150) plays AbilityId 906 (0x3571D9); the ability dispatcher's
   entry 905 calls 0x10CEA90, which at tick 1800 (30 s at 60 ticks a second) requests ExplosionType 293 at the
   "vfx_nuke" node through the ability explosion wrapper 0x11AD240, which passes the type on as argument 3 of the
   request (0x11AD279, 0x11AD416, 0x11AD464). No other code requests 293. Its settings row (50 / 100 / 100 m, damage
   type 497) is identical in every snapshot. Its effect and sound ship in no stratagem's package: the effect package
   is the smallest package that holds the row's particle effect (+0x38; only two Automaton objective packages hold
   it, each with the whole Cyborg Production Unit), the sound package the one that holds the bank of its sound
   (+0x40 is the game's sound key; the hash_lookup slot table maps it to the event; the bank
   obj_cy_city_blow_up_assembly_site holds that event; besides an audio test level one package holds that bank).
6. Projectiles: game.dll 0x13A8F50 FireProjectile(ignored, type, const float pos[3], const float dir[3], entity,
   target, entity_path) is the game's own scalar wrapper (the AI fire helper calls it at 0x119E612 with a zero
   entity_path). It returns at once unless the projectile system (global game+0x347CEA8) is active (+0x28 = 1, set
   in a mission only). With a zero entity_path it looks the type up in the settings pointer table at game+0x37C7670
   WITHOUT a bounds or null check, sets source = owner = entity and inserts into the system's bounded 2048-slot pool
   (0x13A9830). Every catalogued weapon projectile type's table entry points at a record carrying that type.
7. Status effects: game.dll 0x129F170 QueueStatusRequest(ignored, type, target, float amount, instigator, variant)
   appends to the game's status request queue (global game+0x347CF38; count at +0x201134, capacity 0x1000, entries
   of 0x1C bytes). It refuses a missing target, a target without a status instance, a type the target cannot
   receive (0x6994F0, which does NOT bound the type) and a full queue. The game drains it every frame (0x13F7D5E ->
   0x12A6EF0) and routes each request (0x129F2A0): applied here when this machine owns the target (0xB894B0), else
   sent to the owner (0xBEBDE0). The game's own stun callers pass variant 0 and an entity instigator. The float is
   BUILDUP (each request adds it; the status triggers when buildup reaches the target's susceptibility threshold),
   not strength (strength and duration come from the status settings). Every allowlisted type's settings record
   carries that type.

Requires the research-only package capstone.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/event-actions-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
EXPLOSIONS = ROOT / 'sdk/ExplosionAuthoringCapabilities.json'
REQUEST = 0x13C0A80
DRAIN = 0x13C0D10
QUEUE = 0x346D558
SETTINGS_TABLE = 0x37CC920
TYPE_BOUND = 0x1A7
ENTRY = 0x28
STRIDE = 0x98
ERUPTOR_TYPE_HASH = 'B6AFF2195568767F'
LINKS = ROOT / 'research/support-equipment-links-F5FEE03DCFDB.json'
PODS = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
DISPATCH_TABLE = 0x4A0154
BEHAVIOR = 'BehaviorComponentData'
# Named explosions whose type is a code literal of the entity behavior that requests it.
HELLBOMBS = [
    {'name': 'NUX-223 Hellbomb', 'type': 242, 'behaviorId': 224, 'handler': 0x4991E7, 'proofs': 'hellbomb',
        'entity': 0xC6A87C428FD3C7A3, 'stratagemKinds': [42], 'damageType': 479,
        'inner': 17.0, 'outer': 25.0, 'shockwave': 45.0},
    {'name': 'B-100 Portable Hellbomb', 'type': 125, 'behaviorId': 8, 'handler': 0x496871, 'proofs': 'portableHellbomb',
        'entity': 0x9ACE8638421ABC8E, 'stratagemKinds': [31, 120], 'damageType': 479,
        'inner': 17.0, 'outer': 25.0, 'shockwave': 45.0},
]
# Named explosions an ABILITY requests: the type is a code literal of the ability's own handler (at one tick of the
# ability), carried by the ability explosion wrapper (0x11AD240) to the request. The entity whose behavior plays the
# ability is the only owner of that BehaviorId. The effect and the sound ship in objective packages (see effect_assets).
ABILITY_EXPLOSIONS = [
    {'name': 'Cyborg Production Unit', 'type': 293, 'behaviorId': 327, 'behaviorStub': 0x49A73B,
        'behaviorHandler': 0x357150, 'abilityId': 906, 'abilityStub': 0x1154556, 'abilityHandler': 0x10CEA90,
        'tick': 1800, 'node': 0x9EAD14D1, 'proofs': 'cyborgProductionUnit', 'entity': 0x900FF9707522851F,
        'soundBank': 'content/audio/obj_cy_city_blow_up_assembly_site', 'soundTestLevel': 0x22150AB83161D8EC,
        'damageType': 497, 'inner': 50.0, 'outer': 100.0, 'shockwave': 100.0},
]
ABILITY_TABLE = 0x115C784
HASH_LOOKUP = 0xB9EE36888EF19818  # the game's sound key table (resource type hash_lookup)
PROJECTILES = ROOT / 'sdk/ProjectileCompositionCapabilities.json'
STATUSES = ROOT / 'research/status-effects-F5FEE03DCFDB.json'
PROJECTILE_SYSTEM, PROJECTILE_TABLE, PROJECTILE_TYPES = 0x347CEA8, 0x37C7670, 351
STATUS_QUEUE, STATUS_MANAGER, STATUS_TABLE = 0x347CF38, 0x3326620, 0x37C5C50


def status_allowlist():
    """Statuses a player weapon already applies to its targets through a DamageInfo slot (weaponSlotUsers > 0)."""
    rows = json.loads(STATUSES.read_text(encoding='utf-8'))['statuses']
    return [{'type': row['nativeType'], 'semanticId': row['semanticId'], 'name': row['name'],
        'family': row['family'], 'duration': row['duration']} for row in rows if row['weaponSlotUsers'] > 0]


def projectile_catalog():
    """Catalogued weapon projectiles: every attack with a projectile type and a known package."""
    result = []
    for weapon in json.loads(PROJECTILES.read_text(encoding='utf-8'))['weapons']:
        for attack in weapon.get('attacks') or []:
            if attack.get('projectileType'):
                result.append({'weapon': weapon['weapon'], 'role': attack['role'], 'type': attack['projectileType']})
    return result


def observe_actions(name, projectiles, statuses):
    """Projectile system state and table identity; status queue and table identity (one mission snapshot)."""
    mem = base.Mem(name)
    out = {'snapshot': name}
    system = mem.ptr(mem.game + PROJECTILE_SYSTEM)
    out['projectileSystemActive'] = system and mem.read(system + 0x28, 1)[0]
    bad = []
    for item in projectiles:
        record = mem.ptr(mem.game + PROJECTILE_TABLE + 8 * item['type'])
        if not record or mem.u32(record) != item['type']:
            bad.append(item['type'])
    out['projectileTypesMatched'] = len(projectiles) - len(bad)
    out['projectileTypeMismatches'] = sorted(set(bad))
    out['projectileTableBounds'] = {'zeroNull': not mem.ptr(mem.game + PROJECTILE_TABLE),
        'lastCarriesType': mem.u32(mem.ptr(mem.game + PROJECTILE_TABLE + 8 * (PROJECTILE_TYPES - 1))) == PROJECTILE_TYPES - 1,
        'pastEndNull': not mem.ptr(mem.game + PROJECTILE_TABLE + 8 * PROJECTILE_TYPES)}
    queue = mem.ptr(mem.game + STATUS_QUEUE)
    out['statusQueueCount'] = queue and mem.u32(queue + 0x201134)
    out['statusManager'] = bool(mem.ptr(mem.game + STATUS_MANAGER))
    bad = []
    for item in statuses:
        record = mem.ptr(mem.game + STATUS_TABLE + 8 * item['type'])
        if not record or mem.u32(record) != item['type']:
            bad.append(item['type'])
    out['statusTypesMatched'] = len(statuses) - len(bad)
    out['statusTypeMismatches'] = bad
    mem.close()
    return out


# Other requesters of type 242 (from the same wrapper's literal callers); informational.
SHARED_242 = ['BehaviorId 132 bug_stratagem_blocker', 'BehaviorId 422 cy_control_tower',
    'BehaviorId 426 cy_destroy_factories', 'BehaviorId 432 refinery_terminal', 'BehaviorIds 584 and 602',
    'AbilityIds 353 and 2157']


def hellbomb_evidence(data):
    """The entity behind each Hellbomb explosion and the stratagem that delivers it (pinned data, not names)."""
    import research_entity_authoring as entity_research
    native = entity_research.Native()
    behaviors = {}
    for record, owners in native.owners(BEHAVIOR).items():
        behaviors.setdefault(struct.unpack_from('<I', native.record(BEHAVIOR, record), 0)[0], []).extend(owners)
    links = {row['kind']: row for row in json.loads(LINKS.read_text(encoding='utf-8'))['stratagemDefinitions']}
    racks = {rack['resource']: rack for rack in json.loads(PODS.read_text(encoding='utf-8'))['racks']}
    result = []
    for item in HELLBOMBS:
        owners = behaviors.get(item['behaviorId'], [])
        if owners != [item['entity']]:
            raise ValueError('BehaviorId %d is not owned by exactly the %s entity' % (item['behaviorId'], item['name']))
        handler = struct.unpack_from('<I', data, DISPATCH_TABLE + 4 * (item['behaviorId'] - 1))[0]
        if handler != item['handler']:
            raise ValueError('behavior dispatcher entry for %s moved' % item['name'])
        entity = '0x%016X' % item['entity']
        delivered = []
        for kind in item['stratagemKinds']:
            row = links[kind]
            first = row['payloads'][0]
            holds = first == entity or any(slot['item'] == entity for slot in racks.get(first, {}).get('slots', []))
            if not holds:
                raise ValueError('StratagemType %d does not deliver the %s entity' % (kind, item['name']))
            delivered.append({'stratagemType': kind, 'id': row['id'], 'package': row['package'],
                'via': 'payload' if first == entity else 'rack ' + first})
        packages = {d['package'] for d in delivered}
        result.append({'name': item['name'], 'type': item['type'], 'entity': entity, 'path': native.path(item['entity']),
            'behaviorId': item['behaviorId'], 'behaviorOwners': 1, 'dispatcherEntry': item['behaviorId'] - 1,
            'handler': item['handler'], 'deliveredBy': delivered, 'stratagemPackage': packages.pop() if len(packages) == 1
                else None, 'stratagemPackagePath': None,
            'settings': {'damageType': item['damageType'], 'inner': item['inner'], 'outer': item['outer'],
                'shockwave': item['shockwave']},
            'sharedType': SHARED_242 if item['type'] == 242 else []})
        if result[-1]['stratagemPackage']:
            result[-1]['stratagemPackagePath'] = native.path(int(result[-1]['stratagemPackage'], 16))
    return result

def effect_assets(item, record):
    """An ability explosion's effect and sound packages, from its settings record (the first snapshot's) and the
    installed game data (read-only): the particle effect (+0x38) and every archive (package) that holds it, the
    smallest one chosen; the sound key (+0x40) -> its event (hash_lookup) -> the bank that holds it (HIRC) -> the
    packages that hold the bank, the audio test level excluded."""
    import hd2_game_data
    import research_custom_payloads as payloads
    M = hd2_game_data.murmur64
    particle, key = struct.unpack_from('<QI', record, 0x38)
    data = hd2_game_data.Data()
    PACKAGE, BANK, LOOKUP = M(b'package'), M(b'wwise_bank'), M(b'hash_lookup')
    bank = M(item['soundBank'].encode())
    sizes, holders, found = {}, {'particle': [], 'bank': []}, {}
    for archive, rname, rtype, main, stream, gpu in data.tables():
        sizes[archive] = sizes.get(archive, 0) + main[1] + stream[1] + gpu[1]
        if rtype == payloads.PARTICLES and rname == particle:
            holders['particle'].append(archive)
        if rtype == BANK and rname == bank:
            holders['bank'].append(archive)
            found.setdefault('bank', (archive, main))
        if rtype == LOOKUP and rname == HASH_LOOKUP:
            found.setdefault('lookup', (archive, main))
    table = data.read(*found['lookup'])
    slots = table[len(table) - 0x100000:]
    event = None
    for i in range(0x10000):
        e, k = struct.unpack_from('<II', slots, 16 * i)
        if k == key and e:
            if event is not None:
                raise ValueError(item['name'] + ': the sound key maps to several events')
            event = e
    if event is None:
        raise ValueError(item['name'] + ': the sound key maps to no event')
    raw = data.read(*found['bank'])
    events, at = set(), raw.find(b'BKHD')
    while 0 <= at < len(raw) - 8:
        tag, size = raw[at:at + 4], struct.unpack_from('<I', raw, at + 4)[0]
        if tag == b'HIRC':
            p = at + 12
            for _ in range(struct.unpack_from('<I', raw, at + 8)[0]):
                kind, length, oid = struct.unpack_from('<BII', raw, p)
                if kind == 4:
                    events.add(oid)
                p += 5 + length
        at += 8 + size
    if event not in events:
        raise ValueError(item['name'] + ': the sound bank does not hold its event')
    # Package names: every package path the research and domains know, as research_custom_payloads.effect_packages.
    import glob
    import re as regex
    known = set(payloads.EXTRA_PACKAGE_NAMES)
    for path in glob.glob(str(ROOT / 'research/*.json')) + glob.glob(str(ROOT / 'domains/*.lua')):
        known.update(regex.findall(r'packages/[A-Za-z0-9_/\-\.]+', Path(path).read_text(encoding='utf-8',
            errors='ignore')))
    by_hash = {M(n.encode()): n for n in known}

    def described(archives):
        return sorted(({'id': '0x%016X' % int(a, 16), 'name': by_hash.get(int(a, 16)), 'bytes': sizes[a]}
            for a in set(archives)), key=lambda p: p['id'])
    effect = described(holders['particle'])
    sound = [p for p in described(holders['bank']) if int(p['id'], 16) != item['soundTestLevel']]
    if not effect or len(sound) != 1:
        raise ValueError(item['name'] + ': the effect or sound package is not unique enough: %r %r' % (effect, sound))
    chosen = min(effect, key=lambda p: (p['bytes'], p['id']))
    return {'particle': '0x%016X' % particle, 'effectPackages': effect, 'effectPackage': chosen['id'],
        'soundKey': key, 'soundEvent': event, 'soundBank': item['soundBank'], 'soundBankResource': '0x%016X' % bank,
        'soundPackages': described(holders['bank']), 'soundPackage': sound[0]['id']}


def ability_explosion_evidence(data):
    """The entity, behavior and ability behind each ability explosion, its settings row's assets (pinned data)."""
    import research_entity_authoring as entity_research
    native = entity_research.Native()
    behaviors = {}
    for record, owners in native.owners(BEHAVIOR).items():
        behaviors.setdefault(struct.unpack_from('<I', native.record(BEHAVIOR, record), 0)[0], []).extend(owners)
    result = []
    for item in ABILITY_EXPLOSIONS:
        if behaviors.get(item['behaviorId'], []) != [item['entity']]:
            raise ValueError('BehaviorId %d is not owned by exactly the %s entity' % (item['behaviorId'], item['name']))
        if struct.unpack_from('<I', data, DISPATCH_TABLE + 4 * (item['behaviorId'] - 1))[0] != item['behaviorStub']:
            raise ValueError('behavior dispatcher entry for %s moved' % item['name'])
        if struct.unpack_from('<I', data, ABILITY_TABLE + 4 * (item['abilityId'] - 1))[0] != item['abilityStub']:
            raise ValueError('ability dispatcher entry for %s moved' % item['name'])
        mem = base.Mem(SNAPSHOTS[0])
        record = mem.read(mem.ptr(mem.game + SETTINGS_TABLE + 8 * item['type']), 0x48)
        mem.close()
        result.append({'name': item['name'], 'type': item['type'], 'entity': '0x%016X' % item['entity'],
            'path': native.path(item['entity']), 'requestedBy': 'ability', 'behaviorId': item['behaviorId'],
            'behaviorOwners': 1, 'dispatcherEntry': item['behaviorId'] - 1, 'handler': item['behaviorStub'],
            'behaviorHandler': item['behaviorHandler'], 'abilityId': item['abilityId'],
            'abilityEntry': item['abilityId'] - 1, 'abilityHandler': item['abilityHandler'], 'tick': item['tick'],
            'node': item['node'], 'deliveredBy': [], 'stratagemPackage': None, 'stratagemPackagePath': None,
            'assets': effect_assets(item, record),
            'settings': {'damageType': item['damageType'], 'inner': item['inner'], 'outer': item['outer'],
                'shockwave': item['shockwave']}, 'sharedType': []})
    return result


GAME_PROOFS = {
    'request': [
        (0x13C0A80, 'push rbx', None, 'RequestExplosion(queue, const vec3 *position, u32 type, u32 source, ...)'),
        (0x13C0A82, 'sub rsp, 0x30', None, 'frame'),
        (0x13C0A86, 'mov eax, dword ptr [rcx + 0x20]', None, 'queued count +0x20'),
        (0x13C0A89, 'mov r11, rdx', None, 'r11 = position pointer'),
        (0x13C0A8C, 'mov rbx, rcx', None, 'rbx = queue'),
        (0x13C0A8F, 'cmp eax, 0x100', None, 'a full queue (256) is refused'),
        (0x13C0A94, 'jae 0x13c0d03', None, 'full: return without writing'),
        (0x13C0AC0, 'imul rdi, r10, 0x98', None, 'entry stride 0x98'),
        (0x13C0AD1, 'movsd qword ptr [rdi + rcx + 0x28], xmm0', None, 'entry +0x00: position x, y'),
        (0x13C0AD7, 'mov dword ptr [rdi + rcx + 0x30], eax', None, 'entry +0x08: position z'),
        (0x13C0ADB, 'mov dword ptr [rdi + rcx + 0x34], r8d', None, 'entry +0x0C: ExplosionType (argument 3)'),
        (0x13C0B25, 'mov dword ptr [rdi + rbx + 0x38], r9d', None, 'entry +0x10: source entity (argument 4)'),
        (0x13C0B34, 'mov dword ptr [rdi + rbx + 0x3c], ecx', None, 'entry +0x14: owner entity (argument 5)'),
        (0x13C0B0F, 'mov qword ptr [rdi + rbx + 0x40], rax', None, 'entry +0x18: creditor peer (argument 6)'),
        (0x13C0B30, 'mov dword ptr [rdi + rbx + 0x48], edx', None, 'entry +0x20: argument 7'),
        (0x13C0C26, 'mov byte ptr [rdi + rbx + 0xa1], al', None, 'argument 9 flag'),
        (0x13C0C42, 'mov byte ptr [rdi + rbx + 0xa0], al', None, 'argument 8 present'),
        (0x13C0C7B, 'mov dword ptr [rdi + rbx + 0x50], eax', None, 'argument 10 = element count of argument 11'),
        (0x13C0C83, 'call 0x20988f0', None, 'copies count * 4 bytes of argument 11'),
        (0x13C0D08, 'ret', None, 'end of the request'),
    ],
    'queue': [
        (0x8CB18B, 'mov rcx, qword ptr [rip + {rip}]', QUEUE, 'a caller loads the explosion queue global'),
        (0x8CB1FA, 'call 0x13c0a80', None, 'and requests an explosion'),
    ],
    # An explosive's own detonation (the explosive update 0x8CAFF0): its type is its ExplosiveComponent record's +0x24,
    # its source its own entity (the instance's +8; +0xC is its unit, whose position it is). A queued entry of that type
    # and source is that entity's detonation (custom silo payloads observe their missile's this way, read-only).
    'explosiveDetonation': [
        (0x8CB15A, 'cmp dword ptr [r15 + 0x24], 0', None, 'an explosive with a detonation type (record +0x24)'),
        (0x8CB179, 'mov ecx, dword ptr [r14 + 0xc]', None, 'its unit: the position is the unit position'),
        (0x8CB17F, 'mov r9d, dword ptr [r14 + 8]', None, 'source = the explosive entity itself (argument 4)'),
        (0x8CB187, 'mov r8d, dword ptr [r15 + 0x24]', None, 'type = its record +0x24, the detonation (argument 3)'),
    ],
    'hellbomb': [
        (0x4966EA, 'cmp edx, 0x2b4', None, 'behavior event dispatcher: BehaviorId - 1 <= 0x2B4'),
        (0x496708, 'mov edx, dword ptr [rcx + rax*4 + 0x4a0154]', None, 'dispatcher jump table'),
        (0x4991ED, 'call 0x288360', None, 'BehaviorId 224 (table entry 223): the hellbomb event handler'),
        (0x28837D, 'cmp edx, 0xb3fd1aff', None, 'hellbomb event "explode" (thin hash 0xB3FD1AFF)'),
        (0x2883B7, 'mov edx, 3', None, 'explode enters state 3'),
        (0x2883C1, 'jmp 0x288590', None, 'hellbomb set-state'),
        (0x288817, 'mov edx, 0xf2', None, 'state 3 requests ExplosionType 242'),
        (0x28881C, 'mov r8d, 0x73e71450', None, 'at the "nuke" node'),
        (0x288825, 'call 0x4c89c0', None, 'behavior explosion wrapper'),
        (0x4C89F4, 'mov r14d, edx', None, 'wrapper keeps the type'),
        (0x4C8A6D, 'mov r9d, r14d', None, 'and passes it on'),
        (0x4C8A86, 'call 0x13c6d30', None, 'to the second wrapper'),
        (0x13C6D55, 'mov esi, r9d', None, 'second wrapper keeps the type'),
        (0x13C6D78, 'mov r8d, esi', None, 'type is argument 3 of the request'),
        (0x13C6DE4, 'call 0x13c0a80', None, 'RequestExplosion'),
    ],
    'portableHellbomb': [
        (0x496877, 'call 0xc2fd0', None, 'BehaviorId 8 (table entry 7): the bomb backpack event handler'),
        (0xC2FE9, 'cmp edx, 0xb3fd1aff', None, 'bomb backpack event "explode"'),
        (0xC3305, 'mov edx, 0x7d', None, 'requests ExplosionType 125'),
        (0xC330A, 'mov r8d, 0xbccf91e5', None, 'at the "root" node'),
        (0xC3313, 'call 0x4c89c0', None, 'through the same behavior explosion wrapper'),
    ],
    'cyborgProductionUnit': [
        (0x49A741, 'call 0x357150', None, 'BehaviorId 327 (table entry 326): the production unit\'s event handler'),
        (0x3571D9, 'mov edx, 0x38a', None, 'plays AbilityId 906'),
        (0x3571E1, 'call 0x4c3210', None, 'ability play'),
        (0x11509E7, 'dec edx', None, 'ability dispatcher: AbilityId - 1'),
        (0x11509E9, 'cmp edx, 0xb32', None, 'ability dispatcher bound'),
        (0x11509FC, 'mov edx, dword ptr [r10 + rdx*4 + 0x115c784]', None, 'ability dispatcher jump table'),
        (0x1154559, 'call 0x10cea90', None, 'AbilityId 906 (table entry 905): the self-destruct ability handler'),
        (0x10CEAD7, 'cmp edx, 0x708', None, 'at tick 1800'),
        (0x10CEAF6, 'mov edx, 0x125', None, 'requests ExplosionType 293'),
        (0x10CEAFB, 'mov r8d, 0x9ead14d1', None, 'at the "vfx_nuke" node'),
        (0x10CEB08, 'call 0x11ad240', None, 'ability explosion wrapper'),
        (0x11AD279, 'mov r14d, edx', None, 'wrapper keeps the type'),
        (0x11AD416, 'mov r8d, r14d', None, 'type is argument 3 of the request'),
        (0x11AD41D, 'mov rcx, qword ptr [rip + {rip}]', QUEUE, 'the explosion queue'),
        (0x11AD464, 'call 0x13c0a80', None, 'RequestExplosion'),
    ],
    'projectile': [
        (0x13A8F50, 'mov r11, rsp', None, 'FireProjectile(ignored, type, pos, dir, entity, target, entity_path)'),
        (0x13A8F7F, 'mov r12, qword ptr [rip + {rip}]', 0x347CEA8, 'the projectile system global'),
        (0x13A8F86, 'mov r14, r9', None, 'r14 = direction pointer'),
        (0x13A8F89, 'mov r13, r8', None, 'r13 = position pointer'),
        (0x13A8F8C, 'mov r15d, edx', None, 'r15d = projectile type'),
        (0x13A8F8F, 'cmp byte ptr [r12 + 0x28], 0', None, 'inactive system (outside a mission): return'),
        (0x13A8F95, 'je 0x13a97ab', None, 'return without spawning'),
        (0x13A8F9B, 'cmp qword ptr [rbp + 0xa10], 0', None, 'entity_path (argument 7) zero: a plain projectile'),
        (0x13A8FA7, 'mov ebx, dword ptr [rbp + 0xa00]', None, 'entity (argument 5)'),
        (0x13A8FB1, 'je 0x13a9700', None, 'plain projectile path'),
        (0x13A9700, 'mov edx, ebx', None, 'creditor of the entity'),
        (0x13A9702, 'call 0x129c690', None, 'creditor lookup'),
        (0x13A9715, 'lea rcx, [rip + {rip}]', 0x37C7670, 'projectile settings pointer table'),
        (0x13A971C, 'mov rcx, qword ptr [rcx + r15*8]', None, 'indexed by type WITHOUT bounds or null check'),
        (0x13A9765, 'mov dword ptr [rbp - 0x48], 2', None, 'descriptor kind 2'),
        (0x13A976C, 'mov dword ptr [rbp - 0x58], ebx', None, 'source = entity'),
        (0x13A976F, 'mov dword ptr [rbp - 0x54], ebx', None, 'owner = entity'),
        (0x13A9796, 'call 0x13a9830', None, 'SpawnProjectile into the pool'),
        (0x119E5EF, 'mov rcx, qword ptr [rip + {rip}]', 0x347CEA8, 'the AI fire helper passes the system'),
        (0x119E5F6, 'mov qword ptr [rsp + 0x30], 0', None, 'and a zero entity_path'),
        (0x119E612, 'call 0x13a8f50', None, 'to FireProjectile'),
    ],
    'status': [
        (0x129F170, 'mov qword ptr [rsp + 8], rbx', None, 'QueueStatusRequest(ignored, type, target, amount, '
            'instigator, variant)'),
        (0x129F184, 'cmp r8d, dword ptr [rip + {rip}]', None, 'the invalid entity is refused'),
        (0x129F18E, 'mov rsi, qword ptr [rip + {rip}]', 0x347CF38, 'the status request queue global'),
        (0x129F199, 'mov rax, qword ptr [rip + {rip}]', 0x3326620, 'the status manager global'),
        (0x129F20F, 'call 0x6994f0', None, 'the target can receive the type (no type bound inside)'),
        (0x129F218, 'mov eax, dword ptr [rsi + 0x201134]', None, 'queue count'),
        (0x129F21E, 'cmp eax, 0x1000', None, 'the queue holds 4096 requests'),
        (0x129F223, 'jae 0x129f277', None, 'full: return without writing'),
        (0x129F236, 'add rcx, 0xe778', None, 'entries start at +0x195120'),
        (0x129F251, 'imul rdi, rcx, 0x1c', None, 'entry stride 0x1C'),
        (0x129F258, 'mov dword ptr [rdi], ebx', None, 'entry +0: target'),
        (0x129F25A, 'mov dword ptr [rdi + 4], ebp', None, 'entry +4: type'),
        (0x129F26F, 'movss dword ptr [rdi + 0x14], xmm3', None, 'entry +0x14: amount (buildup)'),
        (0x13F7D5E, 'call 0x12a6ef0', None, 'the world update drains the status queue every frame'),
        (0x129F483, 'call 0xb894b0', None, 'router: applied here when this machine owns the target'),
        (0x129F48D, 'call 0xbebde0', None, 'router: otherwise sent to the owner'),
        (0x864EC6, 'mov dword ptr [rsp + 0x28], 0', None, 'game stun caller: variant 0'),
        (0x864ECE, 'mov dword ptr [rsp + 0x20], ebx', None, 'game stun caller: an entity instigator'),
        (0x864ED2, 'call 0x129f170', None, 'game stun caller'),
        (0xB7205D, 'mov dword ptr [rsp + 0x28], 0', None, 'second game stun caller: variant 0'),
        (0xB72069, 'call 0x129f170', None, 'second game stun caller'),
    ],
    'drain': [
        (0x13C61F8, 'call 0x13c0d10', None, 'the game drains the queue'),
        (0x13C0D91, 'mov eax, dword ptr [r8 + 0xc]', None, 'drain reads the entry ExplosionType'),
        (0x13C0DB5, 'cmp eax, 0x1a7', None, 'types are below 0x1A7'),
        (0x13C0DBC, 'test eax, eax', None, 'type 0 is none'),
        (0x13C0DC0, 'mov r14, qword ptr [rcx + rax*8 + 0x37cc920]', None, 'settings pointer table, indexed by type'),
    ],
}


FAMILIES = {}
for names in (('rax', 'eax', 'ax', 'al'), ('rbx', 'ebx', 'bx', 'bl'), ('rcx', 'ecx', 'cx', 'cl'),
        ('rdx', 'edx', 'dx', 'dl'), ('rsi', 'esi', 'si', 'sil'), ('rdi', 'edi', 'di', 'dil'),
        ('rbp', 'ebp', 'bp', 'bpl')) + tuple(('r%d' % n, 'r%dd' % n, 'r%dw' % n, 'r%db' % n) for n in range(8, 16)):
    for name in names:
        FAMILIES[name] = names[0]
VOLATILE = {'rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'}


def register_value(sweep, index, register):
    """The value a register holds at sweep[index] from the nearest earlier write in straight-line code: 0 for
    `xor r, r`, the literal for `mov r, imm`, else None. A call ends the search for volatile registers."""
    family = FAMILIES.get(register)
    if family is None:
        return None
    for j in range(index - 1, max(0, index - 400), -1):
        _, _, m, o = sweep[j]
        if m == 'ret' or m == 'jmp':
            return None
        if m == 'call':
            if family in VOLATILE:
                return None
            continue
        destination = o.split(',')[0].strip() if ',' in o else o.strip()
        if FAMILIES.get(destination) != family:
            continue
        zero = re.fullmatch(r'(\w+), (\w+)', o)
        if m == 'xor' and zero and FAMILIES.get(zero.group(1)) == FAMILIES.get(zero.group(2)):
            return 0
        literal = re.fullmatch(r'\w+, (0x[0-9a-f]+|\d+)', o)
        if m == 'mov' and literal:
            return int(literal.group(1), 0)
        return None
    return None


def call_templates(image):
    """Stack arguments 7..15 of every call to the request, with register-sourced values resolved from the
    straight-line code before the call (xor r, r = 0; mov r, imm = imm)."""
    sweep = list(image.sweep())
    sites = [i for i, (_, _, m, o) in enumerate(sweep) if m == 'call' and o == hex(REQUEST)]
    slots = {0x30: 7, 0x38: 8, 0x40: 9, 0x48: 10, 0x50: 11, 0x58: 12, 0x60: 13, 0x68: 14, 0x70: 15}
    results = []
    for i in sites:
        args, literal_type = {}, None
        start = i
        while start > 0 and i - start < 80 and sweep[start - 1][2] not in ('call', 'ret', 'jmp'):
            start -= 1
        for j in range(start, i):
            _, _, m, o = sweep[j]
            store = re.fullmatch(r'(?:byte|dword|qword) ptr \[rsp \+ (0x[0-9a-f]+)\], (\w+)', o)
            if m == 'mov' and store and int(store.group(1), 16) in slots:
                value = store.group(2)
                if re.fullmatch(r'0x[0-9a-f]+|\d+', value):
                    args[slots[int(store.group(1), 16)]] = int(value, 0)
                else:
                    resolved = register_value(sweep, j, value)
                    args[slots[int(store.group(1), 16)]] = value if resolved is None else resolved
            type_literal = re.fullmatch(r'r8d, (0x[0-9a-f]+)', o)
            if m == 'mov' and type_literal:
                literal_type = int(type_literal.group(1), 16)
        results.append({'site': sweep[i][0], 'arguments7to15': {str(k): args.get(k) for k in range(7, 16)},
            'literalType': literal_type})
    return results


def zero_template(arguments):
    """True when arguments 7..15 are the common template (7=0, 8=null, 9=1, 10=0, 11..13=null, 14=0, 15=0)."""
    want = {7: 0, 8: 0, 9: 1, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0, 15: 0}
    return all(arguments.get(str(slot)) == expected for slot, expected in want.items())


def observe(name, catalog):
    mem = base.Mem(name)
    out = {'snapshot': name}
    queue = mem.ptr(mem.game + QUEUE)
    out['queueCount'] = mem.u32(queue + 0x20)
    stale = []
    for index in range(4):
        raw = mem.read(queue + ENTRY + STRIDE * index, 0x28)
        x, y, z, kind, source, owner, peer, seventh = struct.unpack_from('<fffIIIQI', raw, 0)
        if kind:
            stale.append({'slot': index, 'position': [round(x, 2), round(y, 2), round(z, 2)], 'type': kind,
                'source': source, 'owner': owner, 'peer': '%016X' % peer, 'argument7': seventh})
    out['staleEntries'] = stale
    table = []
    for item in catalog:
        pointer = mem.ptr(mem.game + SETTINGS_TABLE + 8 * item['type'])
        record = pointer and mem.read(pointer, 28)
        if not record:
            table.append({'type': item['type'], 'match': False, 'reason': 'unreadable'})
            continue
        kind, damage, _, _, inner, outer, shock = struct.unpack('<IIIIfff', record)
        match = (kind == item['type'] and damage == item['damageType'] and abs(inner - item['inner']) < 1e-4
            and abs(outer - item['outer']) < 1e-4 and abs(shock - item['shockwave']) < 1e-4)
        table.append({'type': item['type'], 'weapon': item['weapon'], 'match': match})
    out['settingsTable'] = table
    # Identity of the stale requests' source and owner through the network id map (type of each entity).
    em = mem.ptr(mem.game + base.G_ENTITY_MANAGER)
    capacity, empty = mem.u32(em + 0xF22ED0), mem.u32(em + 0xF22ED4)
    slots = mem.read(mem.u64(em + 0xF22EC8), capacity * 8)
    types = {}
    for s in range(capacity):
        key, slot = struct.unpack_from('<II', slots, s * 8)
        if key != empty:
            kind, entity = struct.unpack('<QI', mem.read(em + 0xF32F18 + 24 * slot, 12))
            types[entity] = '%016X' % kind
    local_peer = mem.u64(mem.ptr(mem.game + base.G_SESSION) + 0xB398)
    player = mem.ptr(mem.game + base.G_PLAYER)
    avatars = []
    for i in range(mem.u32(player + 0x84)):
        net = mem.u32(player + 0x3A8 + 0x20 * i)
        slot = None if net == 0x7FFF else base.map_lookup(mem, em + 0xF22EC8, net)
        if slot is not None:
            avatars.append(mem.u32(em + 0xF32F20 + 24 * slot))
    for entry in stale:
        entry['sourceType'] = types.get(entry['source'])
        entry['ownerIsLocalAvatar'] = entry['owner'] in avatars
        entry['peerIsLocal'] = int(entry['peer'], 16) == local_peer
    mem.close()
    return out


def main():
    explosions = json.loads(EXPLOSIONS.read_text(encoding='utf-8'))
    catalog = []
    for weapon in explosions['weapons']:
        for item in weapon['explosions']:
            values = {f['id']: f['value'] for f in item['fields']}
            catalog.append({'type': item['explosionType'], 'weapon': weapon['weapon'], 'damageType': item['damageType'],
                'inner': values['explosion.inner_radius'], 'outer': values['explosion.outer_radius'],
                'shockwave': values['explosion.shockwave_radius']})
    for item in HELLBOMBS + ABILITY_EXPLOSIONS:
        catalog.append({'type': item['type'], 'weapon': item['name'], 'damageType': item['damageType'],
            'inner': item['inner'], 'outer': item['outer'], 'shockwave': item['shockwave']})
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    prologue = data[REQUEST:0x13C0A9A].hex()
    projectile_prologue = data[0x13A8F50:0x13A8F9B].hex()
    status_prologue = data[0x129F170:0x129F199].hex()
    projectiles = projectile_catalog()
    statuses = status_allowlist()
    hellbombs = hellbomb_evidence(data) + ability_explosion_evidence(data)
    templates = call_templates(image)
    common = [t for t in templates if zero_template(t['arguments7to15'])]
    pins = [p for rows in proofs.values() for p in rows]
    observations, relocation = [], {}
    for name in SNAPSHOTS:
        relocation[name] = base.verify_pins_live(name, pins, [])
        observations.append(observe(name, catalog))
        observations[-1]['actions'] = observe_actions(name, projectiles, statuses)
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    for o in observations:
        if o['queueCount'] != 0:
            raise ValueError('explosion queue not drained in ' + o['snapshot'])
        if not all(t['match'] for t in o['settingsTable']):
            raise ValueError('settings table disagrees with the explosion catalog in ' + o['snapshot'])
    for o in observations:
        a = o['actions']
        if a['projectileTypeMismatches'] or a['statusTypeMismatches'] or not a['statusManager']:
            raise ValueError('projectile or status tables disagree in ' + o['snapshot'])
        if not all(a['projectileTableBounds'].values()):
            raise ValueError('projectile table bounds changed in ' + o['snapshot'])
    active = [o['actions']['projectileSystemActive'] for o in observations]
    if active[:3] != [1, 1, 1] or active[3] != 0:
        raise ValueError('projectile system activity does not follow the mission: %r' % active)
    eruptor = [e for o in observations for e in o['staleEntries'] if e['type'] == 158]
    if not eruptor or not all(e['sourceType'] == ERUPTOR_TYPE_HASH and e['ownerIsLocalAvatar'] and e['peerIsLocal']
            for e in eruptor if e['sourceType']):
        raise ValueError('the R-36 Eruptor request semantics were not confirmed')
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'explosion': {'request': REQUEST, 'prologue': prologue, 'queueGlobal': QUEUE, 'drain': DRAIN,
            'settingsTable': SETTINGS_TABLE, 'typeBound': TYPE_BOUND, 'queueCapacity': 256, 'entry': ENTRY,
            'stride': STRIDE,
            'signature': 'RequestExplosion(queue, const float position[3], u32 explosion_type, u32 source_entity, '
                'u32 owner_entity, u64 creditor_peer, u32 a7, const float *a8, u8 a9, u32 a10, const u32 *a11, '
                'const float *a12, const float *a13, u8 a14, u32 a15)',
            'template': {'7': 0, '8': None, '9': 1, '10': 0, '11': None, '12': None, '13': None, '14': 0, '15': 0}},
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation,
        'callSites': templates, 'callSitesWithLiteralTemplate': [t['site'] for t in common],
        'projectile': {'rva': 0x13A8F50, 'prologue': projectile_prologue, 'systemGlobal': PROJECTILE_SYSTEM,
            'activeOffset': 0x28, 'settingsTable': PROJECTILE_TABLE, 'typeCount': PROJECTILE_TYPES, 'spawn': 0x13A9830,
            'poolSlots': 2048,
            'signature': 'FireProjectile(void *ignored, u32 type, const float position[3], const float direction[3], '
                'u32 entity, u32 target, u64 entity_path)',
            'template': {'target': 0, 'entityPath': 0},
            'types': projectiles,
            'sideEffects': ['The owner\'s "shots fired" statistic counts each projectile (0x62C930 via 0x13B28A0).',
                'A full pool reuses its oldest slot (the game\'s own overflow behaviour).',
                'The spawn creates the projectile\'s particle and sound effects at once: its package must be resident.'],
            'unproven': ['The creditor is derived by an engine ownership call (inferred: the local peer for the local '
                'avatar).', 'How damage authority works after a hit (the host processes its own hit buffer; a client '
                'spawn is refused).', 'Whether other machines see the projectile: no network send was found.']},
        'status': {'rva': 0x129F170, 'prologue': status_prologue, 'queueGlobal': STATUS_QUEUE, 'count': 0x201134,
            'capacity': 0x1000, 'managerGlobal': STATUS_MANAGER, 'settingsTable': STATUS_TABLE,
            'signature': 'QueueStatusRequest(void *ignored, u32 type, u32 target, float buildup, u32 instigator, '
                'u32 variant)',
            'template': {'variant': 0, 'buildup': 100.0},
            'allowlist': statuses,
            'unproven': ['The drain has not been observed running (the queue was empty in every snapshot).',
                'Behaviour on clients (routed to the owner) and what other players see.']},
        'catalogueTypes': [c for c in catalog if c['weapon'] not in {h['name'] for h in HELLBOMBS + ABILITY_EXPLOSIONS}],
        'namedExplosions': hellbombs, 'observations': observations,
        'findings': {
            'identity': 'The drain indexes game+0x37CC920 by the request ExplosionType; for all %d catalogued weapon '
                'explosions the entry points at a record with that type, damage type and radii in all %d mission '
                'snapshots.' % (len(catalog), len(SNAPSHOTS)),
            'semantics': 'Stale R-36 Eruptor requests (type 158): source = the Eruptor weapon entity, owner = the local '
                'avatar, creditor = the local peer.',
            'hellbombs': 'NUX-223 Hellbomb = ExplosionType 242 and B-100 Portable Hellbomb = ExplosionType 125: code '
                'literals in the behavior of the only entity with that BehaviorId, passed unchanged to the request; '
                'their settings rows match in every mission snapshot.',
            'cyborgProductionUnit': 'Cyborg Production Unit = ExplosionType 293: a code literal of AbilityId 906\'s '
                'handler (tick 1800), played by the only entity with BehaviorId 327, passed unchanged to the request '
                'by the ability explosion wrapper; its settings row matches in every mission snapshot. Its effect '
                'and sound ship only in Automaton objective packages (the effect package holds the whole production '
                'unit), so requesting it needs both packages resident.',
            'drained': 'The queue count is 0 in every snapshot: requests live for less than a frame.',
            'network': 'No network message call was found in the drain itself; the queue is the local explosion system. '
                'Health is host-authoritative (a remote-owned record is overwritten by synced health), so only a host '
                'request can change enemy health. Whether other machines see the effect is unproven.',
        },
        'unproven': [
            'Arguments 7 and 9..15 beyond the common call template (a Runtime request always passes the template).',
            'Whether the explosion effect is visible on other machines.',
            'Who sends the Hellbomb "explode" event (the detonation trigger is inferred from the "nuke" node and the '
                'destroy that follows); the requested type itself is a pinned code literal.',
            'What ExplosionType 293 does when its effect or sound package is not resident (Runtime never requests it '
                'then), and how loading those packages in a mission without the objective behaves (a live test).',
            'Frame order of the drain relative to the Lua update callback (a request made in update is drained by the '
                'game\'s own explosion update, within a frame).',
        ],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'callSites': len(templates), 'literalTemplate': len(common), 'eruptorRequests': eruptor,
        'settings': [all(t['match'] for t in o['settingsTable']) for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
