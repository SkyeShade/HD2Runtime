"""Event research over the in-mission snapshots (host, alive / after reinforce / mission end): mission start and
end state, avatar and entity lifetime (death, corpse replacement, destruction), handle invalidation, per-weapon
stat attribution, the avatar inventory and the explosion request queue. Read-only; nothing writes.

Four armed captures of one game session (process 99148, session 99148-1790702655, build F5FEE03DCFDB):
  172647Z mission-host, 172918Z mission-host-alive, 173206Z mission-host-after-reinforce, 173443Z
  mission-end-transition (each has a .capture.json context sidecar).

Every structure used by Runtime is pinned below as exact instruction bytes (re-verified in every snapshot); every
behaviour claim is an observation across the four snapshots. A capture takes about a minute while the game runs,
so different memory regions can come from slightly different moments; claims below only compare values read from
one structure at a time, or state where a cross-structure comparison is involved.
Requires the research-only package capstone.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
import snapshot_regions  # noqa: E402

OUTPUT = ROOT / 'research/event-mission-F5FEE03DCFDB.json'
STATE = ROOT / 'research/event-state-F5FEE03DCFDB.json'
SNAPSHOTS = [
    ('mission-host', 'F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap'),
    ('mission-host-alive', 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap'),
    ('mission-host-after-reinforce', 'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap'),
    ('mission-end-transition', 'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap'),
]
G_CORPSE = 0x3326920          # "corpse" component manager (capacity 512)
G_INVENTORY = 0x3326738       # InventoryComponent manager
G_WIELDER = 0x3326420         # WeaponWielderComponent manager
G_EXPLOSIONS = 0x346D558      # explosion request queue (256 entries)
CORPSE_STRIDE = 0x48
CORPSE_ORIGIN = 0x3C

GAME_PROOFS = {
    'corpseManager': [
        (0x56826C, 'lea rax, [rbx + 0x128]', None, 'corpse manager = component world + 0x128'),
        (0x568273, 'mov qword ptr [rip + {rip}], rax', G_CORPSE, 'corpse manager global'),
        (0x56AA99, 'mov r9d, dword ptr [rdi + 0x13c]', None, 'debug print: corpse max = world + 0x128 + 0x14'),
        (0x56AAA7, 'lea r8, [rip + {rip}]', 0x224B8F8, '"corpse" : { "max" : %u, "capacity" : 512 }'),
        (0x87209A, 'mov rbx, qword ptr [rip + {rip}]', G_CORPSE, 'add instance (owned): corpse manager'),
        (0x8720A4, 'mov eax, dword ptr [rbx + 0x18]', None, 'live count +0x18'),
        (0x8720CB, 'mov rax, qword ptr [rbx + 0x48]', None, 'record array +0x48'),
        (0x8720D2, 'lea rcx, [r8 + r8*8]', None, 'record stride 9*8 = 0x48 (record zeroed on add)'),
        (0x8720F4, 'inc dword ptr [rbx + 0x18]', None, 'live count grows on add'),
        (0x8720FA, 'mov rax, qword ptr [rbx + 0x40]', None, 'descriptor pointer array +0x40'),
        (0x872109, 'mov qword ptr [rax + r8*8], rdi', None, 'descriptor pointer store'),
        (0x516869, 'mov rbx, qword ptr [rip + {rip}]', G_CORPSE, 'remove instance: corpse manager'),
        (0x516883, 'mov dword ptr [rbx + 0x18], r8d', None, 'live count shrinks on remove'),
    ],
    'corpseOrigin': [
        (0x556ED2, 'lea rax, [rip + {rip}]', 0x5168F0, 'corpse post-spawn callback'),
        (0x556ED9, 'mov qword ptr [rcx + 0xf0d570], rax', None, 'registered in the post-spawn table (component 4)'),
        (0x581A3B, 'mov rax, qword ptr [rdi + rcx*8 + 0xf0d550]', None, 'spawn calls every component post-spawn callback'),
        (0x5168F6, 'mov rcx, qword ptr [rip + {rip}]', G_CORPSE, 'post-spawn thunk: corpse manager'),
        (0x5168FD, 'jmp 0x86f060', None, 'corpse init from its source entity'),
        (0x86F294, 'mov eax, dword ptr [rdi + 0xc]', None, 'source (dead entity) descriptor unit'),
        (0x86F29B, 'mov dword ptr [r12 + 0xc], eax', None, 'the corpse descriptor takes over the dead entity\'s unit'),
        (0x86F2A0, 'mov eax, dword ptr [rdi + 8]', None, 'source (dead entity) full entity id'),
        (0x86F2A3, 'mov rcx, qword ptr [r13 + 0x48]', None, 'corpse record array'),
        (0x86F2A7, 'mov dword ptr [rcx + rdx*8 + 0x3c], eax', None, 'corpse record +0x3C = the dead entity id'),
        (0x8703BF, 'lea rcx, [rdi + rdi*8]', None, 'corpse lookup: record index * 9'),
        (0x8703C3, 'mov ecx, dword ptr [rax + rcx*8 + 0x3c]', None, 'corpse lookup reads the origin entity id'),
    ],
    'entityDestroy': [
        (0xFDC3EF, 'mov rcx, qword ptr [rdi + 0xf3ef20]', None, 'destroy request: pending list'),
        (0xFDC3F6, 'mov dword ptr [rcx + rdx*4], eax', None, 'destroy request appends the record slot'),
        (0xFDC3F9, 'inc dword ptr [rdi + 0xf3ef18]', None, 'pending count'),
        (0xFDC7C0, 'mov rax, qword ptr [rbx + 0xf3ef20]', None, 'flush walks the pending list'),
        (0xFDC7E0, 'call 0xfdc820', None, 'flush destroys each pending entity'),
        (0xFDCB3F, 'call 0x870310', None, 'destroy consults the corpse link of the destroyed entity'),
        (0xFDCC53, 'mov rdx, qword ptr [r13 + rax*8 + 0xf0e9d0]', None, 'destroy calls every component remove callback'),
        (0x55B978, 'lea rax, [rip + {rip}]', 0x53DDF0, 'health remove callback'),
        (0x55B97F, 'mov qword ptr [rcx + 0xf0f090], rax', None, 'registered in the remove table (component 224)'),
        (0x53DDF3, 'jmp 0x928a70', None, 'health remove instance'),
        (0x928A78, 'mov rdi, qword ptr [rip + {rip}]', 0x3326688, 'health remove: health manager'),
        (0x928B0E, 'mov dword ptr [rdi + 0x1020], r8d', None, 'health remove: live count shrinks'),
    ],
    'explosionQueue': [
        (0x13C0A86, 'mov eax, dword ptr [rcx + 0x20]', None, 'queued request count +0x20'),
        (0x13C0A8F, 'cmp eax, 0x100', None, '256 requests at most'),
        (0x13C0AC0, 'imul rdi, r10, 0x98', None, 'request stride 0x98 from +0x28'),
        (0x13C0AD1, 'movsd qword ptr [rdi + rcx + 0x28], xmm0', None, 'request position x, y'),
        (0x13C0AD7, 'mov dword ptr [rdi + rcx + 0x30], eax', None, 'request position z'),
        (0x13C0ADB, 'mov dword ptr [rdi + rcx + 0x34], r8d', None, 'request explosion id (3rd argument)'),
        (0x13C0B25, 'mov dword ptr [rdi + rbx + 0x38], r9d', None, 'request source entity (4th argument)'),
        (0x13C0B34, 'mov dword ptr [rdi + rbx + 0x3c], ecx', None, 'request owner entity (5th argument)'),
        (0x13C0B0F, 'mov qword ptr [rdi + rbx + 0x40], rax', None, 'request creditor peer (6th argument)'),
        (0x13C0B30, 'mov dword ptr [rdi + rbx + 0x48], edx', None, 'request 7th argument'),
    ],
}


def exists(mem, eem, gens, entity):
    index = entity & 0x3FFFFF
    return index < len(gens) and gens[index] == (entity >> 22) & 0xFF


def unit_alive(mem, ureg, unit):
    index, count = unit & 0x3FFFFF, mem.u32(ureg + 0x98)
    if index >= count:
        return False
    return mem.read(mem.ptr(ureg + 0xA0) + index, 1)[0] == (unit >> 22) & 0xFF


def entity_names():
    """Type hash -> {name, kill, avatar} and stat source type -> name, from the generated event catalog."""
    import re
    text = (ROOT / 'domains/event_entities.lua').read_text(encoding='utf-8')
    entity_part, _, source_part = text.partition('["sources"]=')
    names, sources = {}, {}
    for match in re.finditer(r'\["([0-9A-F]{16})"\]=\{([^{}]*)\}', entity_part):
        body = match.group(2)
        name = re.search(r'\["name"\]="([^"]*)"', body)
        names[match.group(1)] = {'name': name and name.group(1), 'kill': '["kill"]=true' in body,
            'avatar': '["avatar"]=true' in body}
    for match in re.finditer(r'\["([0-9A-F]{16})"\]=\{([^{}]*)\}', source_part):
        name = re.search(r'\["name"\]="([^"]*)"', match.group(2))
        if name:
            sources[match.group(1)] = name.group(1)
    return names, sources


def observe(label, name, key_names, names, sources):
    mem = base.Mem(name)
    out = {'label': label, 'snapshot': name}
    context = build_profile.snapshot_directory() / (name + '.capture.json')
    if context.exists():
        ctx = json.loads(context.read_text(encoding='utf-8'))
        out['capture'] = {k: ctx.get(k) for k in ('captured_at', 'process_id', 'game_session', 'mode', 'label')}
    game = mem.ptr(mem.game + base.G_GAME)
    out['gameState'] = mem.u32(game + 0xAC21C)
    gm = mem.ptr(mem.game + base.G_GAME_MODE)
    gm_count = mem.u32(gm + 8)
    gm_desc = base.descriptor(mem, mem.ptr(gm + 0x38)) if gm_count else None
    out['gameMode'] = {'count': gm_count, 'type': mem.u32(gm + 0x40) if gm_count else None,
        'entity': gm_desc and gm_desc['entity'], 'host': gm_desc and gm_desc['authority']}
    em = mem.ptr(mem.game + base.G_ENTITY_MANAGER)
    eem = mem.ptr(mem.exe + base.X_ENTITY_MANAGER)
    gens = mem.read(mem.ptr(eem + 0x88), mem.u32(eem + 0x80))
    ureg = mem.ptr(mem.exe + base.X_UNIT_REGISTRY)
    local_peer = mem.u64(mem.ptr(mem.game + base.G_SESSION) + 0xB398)
    pm = mem.ptr(mem.game + base.G_PLAYER)
    block = mem.read(pm, 0x430)
    players = []
    for i in range(struct.unpack_from('<I', block, 0x84)[0]):
        d = base.descriptor(mem, struct.unpack_from('<Q', block, 0xE8 + 8 * i)[0])
        net = struct.unpack_from('<I', block, 0x3A8 + 0x20 * i)[0]
        slot = None if net == 0x7FFF else base.map_lookup(mem, em + 0xF22EC8, net)
        avatar = mem.u32(em + 0xF32F20 + 24 * slot) if slot is not None else None
        players.append({'peer': '%016X' % struct.unpack_from('<Q', block, 0x2C8 + 0x38 * i)[0],
            'local': struct.unpack_from('<Q', block, 0x2C8 + 0x38 * i)[0] == local_peer, 'playerEntity': d['entity'],
            'lifecycle': struct.unpack_from('<I', block, 0x2E0 + 0x38 * i)[0], 'avatarNetworkId': net,
            'avatar': avatar})
    out['players'] = players
    hm = mem.ptr(mem.game + base.G_HEALTH)
    live, owned = mem.u32(hm + 0x1020), mem.u32(hm + 0x1024)
    records = mem.read(mem.u64(hm + 0x1058), max(live, 1) * 0x1B8) if live else b''
    pointers = mem.read(mem.u64(hm + 0x1048), max(live, 1) * 8) if live else b''
    life = {'alive': 0, 'downed': 0, 'dead': 0}
    health_entities, avatars = {}, []
    for i in range(live):
        d = base.descriptor(mem, struct.unpack_from('<Q', pointers, i * 8)[0])
        state = struct.unpack_from('<I', records, i * 0x1B8 + 0x19C)[0]
        life[{0: 'alive', 1: 'downed', 2: 'dead'}.get(state, 'other')] = life.get(
            {0: 'alive', 1: 'downed', 2: 'dead'}.get(state, 'other'), 0) + 1
        health_entities[d['entity']] = d
        if names.get(d['type'], {}).get('avatar'):
            avatars.append({'entity': d['entity'], 'unit': d['unit'], 'life': state,
                'health': struct.unpack_from('<i', records, i * 0x1B8 + 0x14)[0]})
    out['health'] = {'live': live, 'owned': owned, 'lifeStates': life, 'avatars': avatars}
    # Records past the live count keep the last bytes swapped out of them: a dead record removed while dead shows.
    stale_dead = []
    if hm:
        tail = mem.read(mem.u64(hm + 0x1058) + live * 0x1B8, 64 * 0x1B8) or b''
        for k in range(len(tail) // 0x1B8):
            if struct.unpack_from('<I', tail, k * 0x1B8 + 0x19C)[0] == 2:
                stale_dead.append({'slot': live + k, 'health': struct.unpack_from('<i', tail, k * 0x1B8 + 0x14)[0],
                    'secondsSinceDamage': round(struct.unpack_from('<f', tail, k * 0x1B8 + 0x1A4)[0], 2)})
    out['health']['staleDeadRecordsPastLiveCount'] = stale_dead
    cm = mem.ptr(mem.game + G_CORPSE)
    c_count = mem.u32(cm + 0x18)
    c_records = mem.read(mem.u64(cm + 0x48), max(c_count, 1) * CORPSE_STRIDE)
    corpses = []
    for i in range(c_count):
        d = base.descriptor(mem, mem.u64(mem.u64(cm + 0x40) + 8 * i))
        origin = struct.unpack_from('<I', c_records, i * CORPSE_STRIDE + CORPSE_ORIGIN)[0]
        corpses.append({'corpse': d['entity'], 'type': d['type'], 'name': names.get(d['type'], {}).get('name'),
            'unit': d['unit'], 'origin': origin, 'originExists': exists(mem, eem, gens, origin),
            'originHasHealthRecord': origin in health_entities})
    out['corpses'] = {'count': c_count, 'owned': mem.u32(cm + 0x1C), 'corpses': corpses}
    # Replicated entities whose type owns a HealthComponent but that have no health record.
    slots_ptr, capacity, empty = mem.u64(em + 0xF22EC8), mem.u32(em + 0xF22ED0), mem.u32(em + 0xF22ED4)
    table = mem.read(slots_ptr, capacity * 8)
    without = []
    corpse_ids = {c['corpse'] for c in corpses}
    for s in range(capacity):
        key, slot = struct.unpack_from('<II', table, s * 8)
        if key == empty:
            continue
        kind, entity, unit = struct.unpack('<QII', mem.read(em + 0xF32F18 + 24 * slot, 16))
        type_hex = '%016X' % kind
        if type_hex in names and entity not in health_entities:
            without.append({'entity': entity, 'name': names[type_hex]['name'], 'enemy': names[type_hex]['kill'],
                'isCorpse': entity in corpse_ids})
    out['replicatedHealthTypesWithoutRecord'] = {'count': len(without),
        'corpses': sum(w['isCorpse'] for w in without), 'enemyCorpses': sum(w['isCorpse'] and w['enemy'] for w in without)}
    # Local player's stats: totals and per-source (weapon / stratagem payload type) blocks.
    sm = mem.ptr(mem.game + base.G_SCORE)
    stats = None
    for player in players:
        if player['local']:
            index = base.map_lookup(mem, sm + 0x37D58, player['playerEntity'])
            if index is not None:
                stats = base.stat_table(mem, sm + 0x37D98 + 0x28 * index, key_names)
    if stats:
        wanted = ('dealt_kills', 'projectiles_fired', 'projectiles_hit', 'received_deaths')
        main = {k: stats['mainEntries'].get(k, {}).get('int', 0) for k in wanted}
        blocks = [{'source': b['source'], 'name': sources.get(b['source']) or names.get(b['source'], {}).get('name'),
            **{k: b['entries'][k]['int'] for k in wanted if k in b['entries']}} for b in stats['sourceBlocksInUse']]
        out['localStats'] = {'main': main, 'totals': {k: main[k] + sum(b.get(k, 0) for b in blocks) for k in wanted},
            'sources': blocks}
    # The local avatar's inventory: record stride 0x30 at +0x50 (observed; not pinned, not used by Runtime).
    im = mem.ptr(mem.game + G_INVENTORY)
    inventory = []
    for i in range(mem.u32(im + 0x18)):
        d = base.descriptor(mem, mem.u64(mem.u64(im + 0x40) + 8 * i))
        items = struct.unpack('<5I', mem.read(mem.u64(im + 0x50) + 0x30 * i, 20))
        inventory.append({'owner': d['entity'], 'items': list(items)})
    out['inventory'] = inventory
    queue = mem.ptr(mem.game + G_EXPLOSIONS)
    stale = []
    for i in range(4):
        raw = mem.read(queue + 0x28 + 0x98 * i, 0x28)
        x, y, z, ident, source, owner, peer, seventh = struct.unpack_from('<fffIIIQI', raw, 0)
        if ident or source:
            stale.append({'slot': i, 'position': [round(x, 1), round(y, 1), round(z, 1)], 'explosionId': ident,
                'source': source, 'owner': owner, 'peer': '%016X' % peer, 'seventhArgument': seventh})
    out['explosionQueue'] = {'count': mem.u32(queue + 0x20), 'staleEntries': stale}
    out['identity'] = {str(e): exists(mem, eem, gens, e) for e in (309, 602, 851, 852)}
    out['units'] = {str(u): unit_alive(mem, ureg, u) for u in (4194863, 12585357)}
    mem.close()
    return out


HANDLE_CHECK = r'''
local json=require('hd2runtime/primary_mapper/json')
local W=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
W.set_runtime(source)
local out={}
local old=handles.entity({id=602,type='4D1C334D294DFA97'})
out.old_valid=old:is_valid()
out.old_reason=old:describe().reason
local player=handles.local_player()
local avatar=player and player:avatar()
out.avatar=avatar and avatar.id
out.avatar_valid=avatar and avatar:is_valid()
out.avatar_alive=avatar and avatar:is_alive()
return json.encode(out)
'''


def main():
    state = json.loads(STATE.read_text(encoding='utf-8'))
    key_names = {int(s['key'], 16): s['telemetryName'] for s in state['statKeys'] if s['telemetryName']}
    first = build_profile.snapshot_directory() / SNAPSHOTS[0][1]
    snap = snapshot_image.Snapshot(first)
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA or snap.executable_sha256.upper() != base.PROFILE_EXE_SHA:
        raise ValueError('snapshot fingerprints differ from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    if image.cstr(0x224B8F8) != '"corpse" : { "max" : %u, "capacity" : 512 }':
        raise ValueError('corpse manager name changed')
    pins = [p for rows in proofs.values() for p in rows]
    names, sources = entity_names()
    observations, relocation = [], {}
    for label, name in SNAPSHOTS:
        relocation[name] = base.verify_pins_live(name, pins, [])
        observations.append(observe(label, name, key_names, names, sources))
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    handle_check = json.loads(snapshot_regions.run_lua(HANDLE_CHECK, build_profile.snapshot_directory() / SNAPSHOTS[2][1]))

    by_label = {o['label']: o for o in observations}
    alive, after, end = by_label['mission-host-alive'], by_label['mission-host-after-reinforce'], by_label['mission-end-transition']
    # Corpse pairs: a corpse whose origin was a live health record one snapshot earlier, with the same unit.
    pairs = []
    for earlier, later in ((by_label['mission-host'], alive), (alive, after)):
        units = {}
        mem = base.Mem(earlier['snapshot'])
        hm = mem.ptr(mem.game + base.G_HEALTH)
        for i in range(mem.u32(hm + 0x1020)):
            d = base.descriptor(mem, mem.u64(mem.u64(hm + 0x1048) + 8 * i))
            units[d['entity']] = d['unit']
        mem.close()
        for corpse in later['corpses']['corpses']:
            if corpse['origin'] in units:
                pairs.append({'from': earlier['label'], 'to': later['label'], 'origin': corpse['origin'],
                    'corpse': corpse['corpse'], 'name': corpse['name'], 'sameUnit': units[corpse['origin']] == corpse['unit']})
    if not pairs or not all(p['sameUnit'] for p in pairs):
        raise ValueError('corpse origin / unit link not confirmed')
    local_after = [p for p in after['players'] if p['local']][0]
    avatar_corpse = [c for c in after['corpses']['corpses'] if c['origin'] == 602]
    findings = {
        'missionState': {
            'started': 'Mission iff game state 4 and a game_mode entity exists (count 1); all three in-mission snapshots '
                'read state 4, game_mode entity %s, host (authority bit) %s.' % (alive['gameMode']['entity'],
                alive['gameMode']['host']),
            'ended': 'The mission-end snapshot reads state %d (PrepareShip), game_mode count %d, health live %d, player '
                'lifecycle %s, avatar network id %s: the state leaves 4 and the mission population is torn down '
                'together.' % (end['gameState'], end['gameMode']['count'], end['health']['live'],
                [p['lifecycle'] for p in end['players']], [p['avatarNetworkId'] for p in end['players']]),
            'gameModeEntityDestroyed': not end['identity']['309'],
        },
        'avatarLifetime': {
            'beforeReinforce': {'avatar': alive['players'][0]['avatar'], 'unit': 4194863},
            'afterReinforce': {'avatar': local_after['avatar'], 'networkId': local_after['avatarNetworkId'],
                'oldAvatarExists': after['identity']['602'], 'oldUnitAlive': after['units']['4194863'],
                'corpseOfOldAvatar': avatar_corpse},
            'deadAvatarKeepsRecord': end['health']['staleDeadRecordsPastLiveCount'][:2],
            'summary': 'A dead avatar keeps its health record in the dead state (life 2) while its player waits to be '
                'reinforced (the mission-end teardown moved a dead avatar record, 31 s after its last damage). On '
                'reinforce the game destroys the dead avatar entity (generation advanced), spawns a corpse entity of '
                'the same type that takes over its unit (corpse record origin = the old avatar id), and spawns a new '
                'avatar with a new network id and entity.',
        },
        'entityDeath': {
            'corpsePairs': pairs,
            'deadRecordsInMission': [o['health']['lifeStates']['dead'] for o in observations[:3]],
            'killsVersusEnemyCorpses': {'mission-host-alive': {'dealt_kills': alive.get('localStats', {}).get(
                'totals', {}).get('dealt_kills'), 'enemyCorpses': alive['replicatedHealthTypesWithoutRecord']['enemyCorpses']}},
            'summary': 'When an enemy dies the game replaces it: the living entity is destroyed through the deferred '
                'destroy list (its health record goes with it) and a corpse entity of the same type is spawned that '
                'takes over the unit and records the dead entity\'s full id (corpse record +0x3C). No enemy record in '
                'the dead state was present in any mission snapshot, so how many frames the dead state lasts before '
                'the swap is unproven; a poll can miss it. The corpse link identifies the death regardless.',
        },
        'handles': dict(handle_check, summary='An Entity handle to the old avatar (602) is invalid after reinforce; '
            'Player:avatar() re-resolves to the new avatar through the player list.'),
        'weaponAttribution': {
            'summary': 'The kill-credit listener adds each stat to the credited player with the source entity\'s type '
                '(0x62C930 arg 5 via 0xFD9D40): the stat record keeps one source block per type. Guns are keyed by the '
                'weapon entity type, stratagems by their payload type; entries in the main table have no source.',
            'afterReinforce': after.get('localStats'),
        },
        'inventory': {'observed': [o['inventory'] for o in observations],
            'summary': 'InventoryComponent (manager game+0x3326738, descriptors +0x40, records 0x30 bytes at +0x50) '
                'lists the avatar\'s loadout weapon entities: slot 0 primary, slot 1 secondary, more slots for other '
                'items. The weapon currently wielded lives in WeaponWielderComponent (game+0x3326420); its field was '
                'not decoded. Observation only; not pinned and not used by Runtime.'},
        'explosionQueue': {'observed': [o['explosionQueue'] for o in observations],
            'summary': 'Requests are {position, explosion id, source entity, owner entity, creditor peer, ...}; an '
                'R-36 Eruptor shell request carries source = the weapon entity and owner = the avatar. The count is 0 '
                'in every snapshot (the queue is drained each frame); only the last frame\'s requests remain as stale '
                'entries. No Hellbomb request was captured; the Hellbomb explosion id stays unproven.'},
    }
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'snapshots': [{'label': label, 'name': name} for label, name in SNAPSHOTS],
        'globals': {'corpse': G_CORPSE, 'inventory': G_INVENTORY, 'weaponWielder': G_WIELDER, 'explosionQueue': G_EXPLOSIONS},
        'layouts': {'corpse': {'count': 0x18, 'owned': 0x1C, 'descriptors': 0x40, 'records': 0x48, 'stride': CORPSE_STRIDE,
            'origin': CORPSE_ORIGIN, 'capacity': 512}},
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'findings': findings,
        'unproven': [
            'How long an enemy stays in the dead state before the corpse swap (0 dead records in three mission '
                'snapshots with 47 kills).',
            'Which system requests the corpse spawn for enemies (the spawn is generic, 0xFDC140; the corpse callback '
                'reads its source from the corpse\'s own spawn data).',
            'Deaths that leave no corpse (for example an entity destroyed outright) are indistinguishable from '
                'despawns by the corpse link.',
            'The currently wielded weapon (WeaponWielderComponent field) and the meaning of the other inventory slots.',
            'The Hellbomb explosion id and the full explosion request argument list.',
            'Client-side behaviour: every snapshot is from the host.',
        ],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'pairs': len(pairs), 'handles': handle_check, 'deadInMission': findings['entityDeath'][
        'deadRecordsInMission'], 'killsVsCorpses': findings['entityDeath']['killsVersusEnemyCorpses']}, indent=1))


if __name__ == '__main__':
    main()
