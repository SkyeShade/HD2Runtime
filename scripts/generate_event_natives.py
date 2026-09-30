"""Generate domains/event_natives.lua: the native structures event sources read, from the event research.

Every global, offset and callable function is taken from a research output (research/event-*-F5FEE03DCFDB.json)
together with the exact instruction bytes that prove it. The generator checks each value against the pinned
instruction's own text (for example `mov r9d, dword ptr [r10 + 0x1038]` for the hash capacity), so a value can only
enter the runtime table if a pinned instruction uses exactly that value. At runtime every pin is re-read from the
loaded game.dll before any source starts; one mismatch makes every event source unavailable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

COMBAT = ROOT / 'research/event-combat-F5FEE03DCFDB.json'
STATE = ROOT / 'research/event-state-F5FEE03DCFDB.json'
ACTIONS = ROOT / 'research/event-actions-F5FEE03DCFDB.json'
WIELDER = ROOT / 'research/event-wielder-F5FEE03DCFDB.json'
MISSION = ROOT / 'research/event-mission-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/event_natives.lua'


class Pins:
    """Pinned instructions from the research outputs, per module ('game' = game.dll, 'exe' = the executable)."""

    def __init__(self, combat: dict, state: dict, mission: dict, actions: dict, wielder: dict):
        self.by_rva = {'game': {}, 'exe': {}}
        for group in (list(mission['proofs'].values()) + list(actions['proofs'].values())
                + list(wielder['proofs'].values())):
            for pin in group:
                self.by_rva['game'].setdefault(pin['rva'], pin)
        for name, function in combat['functions'].items():
            for pin in function['pins']:
                self.by_rva['game'][pin['rva']] = dict(pin, function=name)
        for group in state['proofs'].values():
            for pin in group:
                self.by_rva['game'].setdefault(pin['rva'], pin)
        for group in state['exeProofs'].values():
            for pin in group:
                self.by_rva['exe'].setdefault(pin['rva'], pin)
        self.used = []

    def use(self, rva: int, asm: str, label: str, module: str = 'game') -> dict:
        pin = self.by_rva[module].get(rva)
        if pin is None or pin['asm'] != asm:
            raise ValueError(f'pin {rva:#x} ({label}) is not the reviewed instruction {asm!r}: {pin and pin["asm"]}')
        self.used.append({'label': label, 'rva': rva, 'hex': pin['bytes'], 'module': module})
        return pin

    def rip(self, rva: int, asm: str, label: str, target: int, module: str = 'game') -> None:
        if self.use(rva, asm, label, module).get('ripTarget') != target:
            raise ValueError(f'{label}: global moved')


def health_section(pins: Pins, research: dict) -> dict:
    manager = research['globals']['healthManager']['rva']
    loaded = pins.use(0x4A441A, 'mov r10, qword ptr [rip + 0x2e82267]', 'health manager global (record getter)')
    if loaded.get('ripTarget') != manager:
        raise ValueError('health manager global moved')
    pins.use(0x4A442A, 'mov r9d, dword ptr [r10 + 0x1038]', 'hash capacity')
    pins.use(0x4A4439, 'mov ebx, dword ptr [r10 + 0x1040]', 'hash multiplier')
    pins.use(0x4A445A, 'mov rdi, qword ptr [r10 + 0x1030]', 'hash buckets')
    pins.use(0x4A4461, 'mov esi, dword ptr [r10 + 0x103c]', 'hash empty key')
    pins.use(0x4A44C1, 'mov eax, dword ptr [r11 + 4]', 'bucket value is the record index')
    pins.use(0x4A44AA, 'imul rax, rcx, 0x1b8', 'record stride')
    pins.use(0x4A44B1, 'add rax, qword ptr [r10 + 0x1058]', 'record array')
    pins.use(0x928A91, 'mov r8d, dword ptr [rdi + 0x1020]', 'live count')
    pins.use(0x53DDB5, 'mov rax, qword ptr [rsi + 0x1048]', 'descriptor array')
    pins.use(0x53DDC9, 'mov qword ptr [rax + rdi*8], r14', 'descriptor pointer store')
    pins.use(0x91D62D, 'imul rbp, rcx, 0x1c', 'ext stride')
    pins.use(0x91D646, 'add rbp, qword ptr [rdi + 0x1060]', 'ext array')
    pins.use(0x91D694, 'mov eax, dword ptr [rbp + 0x14]', 'ext max health')
    pins.use(0x91D69E, 'mov dword ptr [r13 + 0x14], eax', 'record health')
    pins.use(0x91CF8B, 'mov dword ptr [r8 + rsi + 0x19c], ebx', 'record life state store')
    pins.use(0x9270F2, 'cmp dword ptr [rcx + rax + 0x19c], 2', 'dead = life state >= 2')
    pins.use(0x923C20, 'mov qword ptr [r15 + 0x38], rax', 'record last-hit creditor')
    pins.use(0x925567, 'mov rdx, qword ptr [r14 + 0x38]', 'kill dispatch creditor = record+0x38')
    pins.use(0x923C34, 'mov dword ptr [r9 + 0x30], r15d', 'record last-hit owner entity')
    pins.use(0x924F3E, 'mov dword ptr [rax + 0x44], ecx', 'record owner entity at downing')
    pins.use(0x924F50, 'mov dword ptr [rax + 0x48], edi', 'record dealer entity at downing')
    pins.use(0x924F48, 'mov qword ptr [rax + 0x50], rcx', 'record creditor at downing')
    pins.use(0x924D18, 'mov dword ptr [rax + 0x1a4], r13d', 'record seconds since damage reset')
    pins.use(0x928AD6, 'test byte ptr [rcx + 0x14], 1', 'descriptor flag bit0 = owned by this peer')
    return {'global': manager, 'capacity': 0x1010, 'live': 0x1020, 'buckets': 0x1030, 'hashCapacity': 0x1038,
        'hashEmpty': 0x103C, 'hashMultiplier': 0x1040, 'descriptors': 0x1048, 'records': 0x1058, 'extArray': 0x1060,
        'header': 0x1010, 'headerSize': 0x58, 'stride': 0x1B8, 'extStride': 0x1C, 'maxRecords': 4096,
        'record': {'health': 0x14, 'lastOwner': 0x30, 'lastCreditor': 0x38, 'downOwner': 0x44, 'downDealer': 0x48,
            'downCreditor': 0x50, 'life': 0x19C, 'sinceDamage': 0x1A4},
        'extFields': {'maxHealth': 0x14},
        'descriptor': {'size': 0x18, 'type': 0x00, 'entity': 0x08, 'unit': 0x0C, 'goid': 0x10, 'flags': 0x14}}


def players_section(pins: Pins, research: dict) -> dict:
    manager = research['globals']['playerManager']['rva']
    loaded = pins.use(0x62C71A, 'mov rcx, qword ptr [rip + 0x2cf9d47]', 'player manager global')
    if loaded.get('ripTarget') != manager:
        raise ValueError('player manager global moved')
    pins.use(0x62C724, 'mov r10d, dword ptr [rcx + 0x84]', 'player count')
    pins.use(0x62C730, 'lea r9, [rcx + 0x2c8]', 'player peer ids')
    pins.use(0x62C73E, 'add r9, 0x38', 'player peer id stride')
    pins.use(0x62C751, 'mov rcx, qword ptr [rcx + rax*8 + 0xe8]', 'player descriptors')
    pins.use(0x62C759, 'mov edx, dword ptr [rcx + 8]', 'player entity')
    local_user = research['globals']['localUser']['rva']
    loaded = pins.use(0x12A874A, 'mov rax, qword ptr [rip + 0x21d479f]', 'local user global')
    if loaded.get('ripTarget') != local_user:
        raise ValueError('local user global moved')
    pins.use(0x12A8751, 'cmp rcx, qword ptr [rax + 0xb398]', 'local peer id')
    return {'global': manager, 'count': 0x84, 'peers': 0x2C8, 'peerStride': 0x38, 'descriptors': 0xE8,
        'descriptorEntity': 0x08, 'maxPlayers': 4, 'localUser': local_user, 'localPeer': 0xB398}


def state_section(pins: Pins, state: dict) -> dict:
    game = state['globals']['game']
    pins.rip(0x541402, 'mov rax, qword ptr [rip + 0x2de4f37]', 'game object global', game['Game'])
    pins.use(0x541409, 'cmp dword ptr [rax + 0xac21c], 4', 'game state member; 4 = Mission')
    pins.use(0xAB309C, 'mov dword ptr [rdi + 0xac21c], ebx', 'game state writer (change_state)')
    pins.use(0xAB2FDA, 'lea r14, [rbx*8 + 0x2147f30]', 'game state name table')
    names = state['gameStateNames']
    if names[:7] != ['None', 'Splash', 'TitleScreen', 'Ship', 'Mission', 'PrepareShip', 'PrepareMission']:
        raise ValueError('game state numbering changed')
    pins.rip(0xACC715, 'mov rax, qword ptr [rip + 0x2859f84]', 'game_mode manager global', game['game_mode'])
    pins.use(0xACC723, 'cmp dword ptr [rax + 8], edi', 'game_mode live count')
    pins.use(0xACC728, 'mov rcx, qword ptr [rax + 0x38]', 'game_mode descriptor')
    pins.use(0xACC731, 'test byte ptr [rcx + 0x14], 1', 'authority over the game mode (host)')
    pins.use(0xAD4C49, 'mov ecx, dword ptr [rax + 0x40]', 'game mode type')
    return {'game': game['Game'], 'state': 0xAC21C, 'names': names, 'mission': 4, 'gameMode': game['game_mode'],
        'gameModeCount': 8, 'gameModeDescriptor': 0x38, 'gameModeType': 0x40, 'modeNames': state['gameModeNames'],
        'descriptorFlags': 0x14, 'descriptorEntity': 0x08}


def player_avatars_section(pins: Pins, state: dict) -> dict:
    game = state['globals']['game']
    pins.use(0x608B2C, 'imul rax, rcx, 0x38', 'player block stride')
    pins.use(0x608B4C, 'mov dword ptr [rax + r9 + 0x2e0], ebx', 'player lifecycle state')
    pins.use(0xACC665, 'shl rax, 5', 'player avatar network id stride')
    pins.use(0xACC66C, 'mov edx, dword ptr [rax + r14 + 0x3a8]', 'player avatar network id')
    pins.use(0x60C6F2, 'mov dword ptr [rbx + rbp + 0x3a8], 0x7fff', 'avatar cleared: network id 0x7FFF')
    pins.rip(0xFD9BA4, 'mov r11, qword ptr [rip + 0x24923ed]', 'entity manager global (network id map)',
        game['EntityManager'])
    pins.use(0xFD9BC9, 'mov r10d, dword ptr [r11 + 0xf22ed0]', 'network id map capacity')
    pins.use(0xFD9BD7, 'mov ebx, dword ptr [r11 + 0xf22ed8]', 'network id map multiplier')
    pins.use(0xFD9BF9, 'mov rdi, qword ptr [r11 + 0xf22ec8]', 'network id map slots')
    pins.use(0xFD9C00, 'mov esi, dword ptr [r11 + 0xf22ed4]', 'network id map empty key')
    pins.use(0xFD9C49, 'mov eax, dword ptr [rax + 4]', 'network id map value = record slot')
    pins.use(0xFD9C50, 'lea rax, [rax + 0x1e65e4]', 'record slot -> entity id (em + 0xF32F20 + 24*slot)')
    return {'lifecycle': 0x2E0, 'lifecycleStride': 0x38, 'lifecycleNames': {'2': 'waiting_for_respawn', '3': 'spawned'},
        'avatarId': 0x3A8, 'avatarIdStride': 0x20, 'noNetworkId': 0x7FFF,
        'entities': game['EntityManager'], 'mapSlots': 0xF22EC8, 'mapCapacity': 0xF22ED0, 'mapEmpty': 0xF22ED4,
        'mapMultiplier': 0xF22ED8, 'entityBase': 0xF32F20, 'entityStride': 24}


def engine_section(pins: Pins, state: dict) -> dict:
    exe = state['globals']['exe']
    pins.rip(0x86A97, 'mov qword ptr [rip + 0x1a8cb1a], rax', 'engine entity manager global', exe['EntityManager'],
        'exe')
    pins.use(0x6046A6, 'lea r14, [rcx + 0x80]', 'entity generation array {size, cap, data}', 'exe')
    pins.use(0x604755, 'mov rax, qword ptr [rbx + 0x88]', 'entity generation bytes', 'exe')
    pins.use(0x604793, 'and edx, 0x3fffff', 'entity index = id & 0x3FFFFF', 'exe')
    pins.use(0x6047A2, 'shr eax, 0x16', 'entity generation = id >> 22', 'exe')
    pins.use(0x6047CF, 'inc byte ptr [rax + rbx]', 'destroy increments the generation', 'exe')
    pins.rip(0x9D8CF, 'mov rsi, qword ptr [rip + 0x197281a]', 'unit registry global', exe['UnitRegistry'], 'exe')
    pins.use(0x9D8EC, 'cmp eax, dword ptr [rsi + 0x98]', 'unit count', 'exe')
    pins.use(0x9D8FA, 'mov rax, qword ptr [rsi + 0xa0]', 'unit generation bytes', 'exe')
    pins.use(0x9D904, 'cmp byte ptr [rcx + rax], bl', 'unit 8-bit generation compare', 'exe')
    pins.use(0x9D909, 'mov rax, qword ptr [rsi + 0x88]', 'unit objects', 'exe')
    pins.use(0x407864, 'call qword ptr [rdx + 0xe8]', 'Unit.world_position: scene graph accessor', 'exe')
    pins.use(0x407871, 'mov rcx, qword ptr [rax + 0x28]', 'Unit.world_position: world poses', 'exe')
    pins.use(0x407875, 'add rcx, 0x30', 'Unit.world_position: translation row', 'exe')
    accessor = state['unitSceneGraphAccessor']
    if accessor['bytes'] != '488d4160c3' or accessor['slot'] != 0xE8:
        raise ValueError('unit scene graph accessor changed')
    return {'entities': exe['EntityManager'], 'generationSize': 0x80, 'generations': 0x88, 'indexMask': 0x3FFFFF,
        'units': exe['UnitRegistry'], 'unitCount': 0x98, 'unitGenerations': 0xA0, 'unitObjects': 0x88,
        'unitId': 0x08, 'unitVtable': accessor['vtableRva'], 'sceneGraphMethod': accessor['methodRva'],
        'sceneGraphMethodBytes': accessor['bytes'], 'sceneGraphOffset': 0x60, 'poses': 0x28, 'translation': 0x30}


def stats_section(pins: Pins, state: dict) -> dict:
    game = state['globals']['game']
    pins.rip(0x62CD3F, 'mov rsi, qword ptr [rip + 0x2cf9d9a]', 'score manager global (get_stat)', game['score'])
    pins.use(0x62C764, 'mov r9d, dword ptr [r11 + 0x37d60]', 'score index map capacity')
    pins.use(0x62C78C, 'mov rdi, qword ptr [r11 + 0x37d58]', 'score index map slots')
    pins.use(0x62CD70, 'add rax, 0x1657', 'stat record = score + (index + 0x1657) * 0x28')
    pins.use(0x62CD7D, 'lea rax, [rax + rax*4]', 'stat record stride (x5)')
    pins.use(0x62CD81, 'lea rsi, [rsi + rax*8]', 'stat record stride (x8)')
    pins.use(0x62CD96, 'mov edi, dword ptr [rax + 4]', 'stat int value at entry +4')
    pins.use(0x62CDA2, 'mov r9, qword ptr [rsi + 0x18]', 'stat source blocks at record +0x18')
    pins.use(0x62CDDF, 'add rcx, 0x14', 'stat source entry stride')
    pins.use(0x62CDE3, 'cmp edx, 0x10', '16 entries per source block')
    pins.use(0x6303AA, 'add r13, 0x148', 'stat source block stride')
    pins.use(0x6303B1, 'cmp r12d, 0x40', '64 stat source blocks')
    pins.use(0x1731A6A, 'mov r8d, dword ptr [rcx + 8]', 'stat table capacity')
    pins.use(0x1731A70, 'mov r10d, dword ptr [rcx + 0x10]', 'stat table multiplier')
    pins.use(0x1731A84, 'mov r11, qword ptr [rcx]', 'stat table entries')
    pins.use(0x1731A87, 'mov ebx, dword ptr [rcx + 0xc]', 'stat table empty key')
    pins.use(0x1731A99, 'lea rcx, [rdx + rdx*4]', 'stat entry stride 0x14')
    keys = {item['telemetryName']: int(item['key'], 16) for item in state['statKeys']}
    return {'score': game['score'], 'indexSlots': 0x37D58, 'indexCapacity': 0x37D60, 'indexEmpty': 0x37D64,
        'indexMultiplier': 0x37D68, 'recordBase': 0x37D98, 'recordStride': 0x28, 'maxPlayers': 4,
        'tableEntries': 0x00, 'tableCapacity': 0x08, 'tableEmpty': 0x0C, 'tableMultiplier': 0x10, 'entryStride': 0x14,
        'entryValue': 0x04, 'sources': 0x18, 'sourceBlocks': 0x40, 'sourceStride': 0x148, 'sourceEntries': 0x08,
        'sourceEntryCount': 0x10, 'keys': {'projectiles_fired': keys['projectiles_fired'],
            'dealt_kills': keys['dealt_kills'], 'received_deaths': keys['received_deaths'],
            'projectiles_hit': keys['projectiles_hit'], 'dealt_damage': keys['dealt_damage']}}


def corpses_section(pins: Pins, mission: dict) -> dict:
    """The corpse manager: a dead entity is replaced by a corpse entity that keeps the dead entity's full id."""
    manager = mission['globals']['corpse']
    pins.rip(0x87209A, 'mov rbx, qword ptr [rip + 0x2ab487f]', 'corpse manager global (add instance)', manager)
    pins.use(0x8720A4, 'mov eax, dword ptr [rbx + 0x18]', 'corpse live count')
    pins.use(0x8720FA, 'mov rax, qword ptr [rbx + 0x40]', 'corpse descriptor pointers')
    pins.use(0x8720CB, 'mov rax, qword ptr [rbx + 0x48]', 'corpse record array')
    pins.use(0x8720D2, 'lea rcx, [r8 + r8*8]', 'corpse record stride 0x48')
    pins.use(0x86F29B, 'mov dword ptr [r12 + 0xc], eax', 'the corpse takes over the dead entity unit')
    pins.use(0x86F2A0, 'mov eax, dword ptr [rdi + 8]', 'dead entity full id')
    pins.use(0x86F2A7, 'mov dword ptr [rcx + rdx*8 + 0x3c], eax', 'corpse record +0x3C = dead entity id')
    pins.use(0x8703C3, 'mov ecx, dword ptr [rax + rcx*8 + 0x3c]', 'corpse lookup reads the origin')
    layout = mission['layouts']['corpse']
    if (layout['count'], layout['descriptors'], layout['records'], layout['stride'], layout['origin']) != (
            0x18, 0x40, 0x48, 0x48, 0x3C):
        raise ValueError('corpse layout changed')
    return {'global': manager, 'count': 0x18, 'descriptors': 0x40, 'records': 0x48, 'stride': 0x48, 'origin': 0x3C,
        'maxRecords': layout['capacity']}


def explosion_section(pins: Pins, actions: dict) -> dict:
    """The game's explosion request (research/event-actions-F5FEE03DCFDB.json): the queue, the call and its bounds."""
    research = actions['explosion']
    pins.rip(0x8CB18B, 'mov rcx, qword ptr [rip + 0x2ba23c6]', 'explosion queue global (a caller)', research['queueGlobal'])
    pins.use(0x13C0A86, 'mov eax, dword ptr [rcx + 0x20]', 'explosion queue count')
    pins.use(0x13C0A8F, 'cmp eax, 0x100', 'explosion queue holds 256 requests')
    pins.use(0x13C0AC0, 'imul rdi, r10, 0x98', 'explosion request stride')
    pins.use(0x13C0ADB, 'mov dword ptr [rdi + rcx + 0x34], r8d', 'explosion request type (argument 3)')
    pins.use(0x13C0B25, 'mov dword ptr [rdi + rbx + 0x38], r9d', 'explosion request source (argument 4)')
    pins.use(0x13C0B34, 'mov dword ptr [rdi + rbx + 0x3c], ecx', 'explosion request owner (argument 5)')
    pins.use(0x13C0B0F, 'mov qword ptr [rdi + rbx + 0x40], rax', 'explosion request creditor (argument 6)')
    pins.use(0x13C0DB5, 'cmp eax, 0x1a7', 'explosion types are below 0x1A7')
    pins.use(0x13C0DC0, 'mov r14, qword ptr [rcx + rax*8 + 0x37cc920]', 'explosion settings table by type')
    template = research['template']
    if template != {'7': 0, '8': None, '9': 1, '10': 0, '11': None, '12': None, '13': None, '14': 0, '15': 0}:
        raise ValueError('explosion call template changed')
    if len(actions['callSitesWithLiteralTemplate']) < 4:
        raise ValueError('the explosion call template is not the game\'s own')
    if any(not all(t['match'] for t in o['settingsTable']) for o in actions['observations']):
        raise ValueError('explosion settings table disagrees with the catalog')
    # Named explosions: the requested type is a code literal of the entity behavior; Runtime re-proves each literal
    # (and the wrapper chain that carries it to the request) before it requests that type.
    pins.use(0x4C8A6D, 'mov r9d, r14d', 'behavior explosion wrapper passes the type')
    pins.use(0x13C6D78, 'mov r8d, esi', 'second wrapper: type is request argument 3')
    pins.use(0x13C6DE4, 'call 0x13c0a80', 'second wrapper calls RequestExplosion')
    literals = {242: [(0x28837D, 'cmp edx, 0xb3fd1aff', 'NUX-223 Hellbomb: explode event'),
            (0x288817, 'mov edx, 0xf2', 'NUX-223 Hellbomb: requests ExplosionType 242'),
            (0x288825, 'call 0x4c89c0', 'NUX-223 Hellbomb: through the behavior explosion wrapper')],
        125: [(0xC2FE9, 'cmp edx, 0xb3fd1aff', 'B-100 Portable Hellbomb: explode event'),
            (0xC3305, 'mov edx, 0x7d', 'B-100 Portable Hellbomb: requests ExplosionType 125'),
            (0xC3313, 'call 0x4c89c0', 'B-100 Portable Hellbomb: through the behavior explosion wrapper')]}
    named = []
    for item in actions['namedExplosions']:
        rows = literals[item['type']]
        for rva, asm, label in rows:
            pins.use(rva, asm, label)
        if not item['stratagemPackage']:
            raise ValueError(item['name'] + ': no single delivering stratagem package')
        named.append({'name': item['name'], 'type': item['type'], 'literal': rows[1][0],
            'package': item['stratagemPackage'], 'packagePath': item['stratagemPackagePath'],
            'sharedType': bool(item['sharedType'])})
    return {'rva': research['request'], 'prologue': research['prologue'], 'queue': research['queueGlobal'],
        'count': 0x20, 'capacity': research['queueCapacity'], 'settingsTable': research['settingsTable'],
        'typeBound': research['typeBound'], 'signature': research['signature'],
        # Catalogued weapon explosions whose settings-table entry the research matched in every mission snapshot.
        'weapons': [{'weapon': item['weapon'], 'type': item['type']} for item in actions['catalogueTypes']],
        'named': named}


def projectile_section(pins: Pins, actions: dict) -> dict:
    """The game's projectile wrapper (research/event-actions-F5FEE03DCFDB.json): active-system gate, table, template."""
    research = actions['projectile']
    pins.rip(0x13A8F7F, 'mov r12, qword ptr [rip + 0x20d3f22]', 'projectile system global', research['systemGlobal'])
    pins.use(0x13A8F8F, 'cmp byte ptr [r12 + 0x28], 0', 'projectile system active flag')
    pins.use(0x13A8F9B, 'cmp qword ptr [rbp + 0xa10], 0', 'zero entity_path: a plain projectile')
    pins.rip(0x13A9715, 'lea rcx, [rip + 0x241df54]', 'projectile settings table', research['settingsTable'])
    pins.use(0x13A971C, 'mov rcx, qword ptr [rcx + r15*8]', 'projectile settings by type (unbounded)')
    pins.use(0x13A976C, 'mov dword ptr [rbp - 0x58], ebx', 'projectile source = entity')
    pins.use(0x13A976F, 'mov dword ptr [rbp - 0x54], ebx', 'projectile owner = entity')
    pins.use(0x13A9796, 'call 0x13a9830', 'projectile pool insert')
    pins.use(0x119E5F6, 'mov qword ptr [rsp + 0x30], 0', 'the game\'s own call passes a zero entity_path')
    pins.use(0x119E612, 'call 0x13a8f50', 'the game\'s own call to the projectile wrapper')
    if research['template'] != {'target': 0, 'entityPath': 0}:
        raise ValueError('projectile call template changed')
    if any(o['actions']['projectileTypeMismatches'] for o in actions['observations']):
        raise ValueError('projectile settings table disagrees with the catalog')
    return {'rva': research['rva'], 'prologue': research['prologue'], 'system': research['systemGlobal'],
        'active': research['activeOffset'], 'settingsTable': research['settingsTable'], 'typeCount': research['typeCount'],
        'signature': research['signature'],
        # Catalogued weapon projectiles whose settings-table entry the research matched in every mission snapshot.
        'types': [{'weapon': item['weapon'], 'role': item['role'], 'type': item['type']} for item in research['types']]}


def status_section(pins: Pins, actions: dict) -> dict:
    """The game's status request queue (research/event-actions-F5FEE03DCFDB.json): bounds, routing, allowlist."""
    research = actions['status']
    pins.rip(0x129F18E, 'mov rsi, qword ptr [rip + 0x21ddda3]', 'status request queue global', research['queueGlobal'])
    pins.rip(0x129F199, 'mov rax, qword ptr [rip + 0x2087480]', 'status manager global', research['managerGlobal'])
    pins.use(0x129F218, 'mov eax, dword ptr [rsi + 0x201134]', 'status queue count')
    pins.use(0x129F21E, 'cmp eax, 0x1000', 'status queue holds 4096 requests')
    pins.use(0x129F258, 'mov dword ptr [rdi], ebx', 'status request target')
    pins.use(0x129F25A, 'mov dword ptr [rdi + 4], ebp', 'status request type')
    pins.use(0x129F26F, 'movss dword ptr [rdi + 0x14], xmm3', 'status request buildup')
    pins.use(0x13F7D5E, 'call 0x12a6ef0', 'the world update drains the status queue')
    pins.use(0x129F483, 'call 0xb894b0', 'status router: owned targets apply here')
    pins.use(0x129F48D, 'call 0xbebde0', 'status router: other targets go to their owner')
    pins.use(0x864EC6, 'mov dword ptr [rsp + 0x28], 0', 'the game\'s own status request passes variant 0')
    pins.use(0x864ED2, 'call 0x129f170', 'the game\'s own status request')
    if research['template'] != {'variant': 0, 'buildup': 100.0}:
        raise ValueError('status call template changed')
    if any(o['actions']['statusTypeMismatches'] for o in actions['observations']):
        raise ValueError('status settings table disagrees with the allowlist')
    return {'rva': research['rva'], 'prologue': research['prologue'], 'queue': research['queueGlobal'],
        'count': research['count'], 'capacity': research['capacity'], 'manager': research['managerGlobal'],
        'settingsTable': research['settingsTable'], 'signature': research['signature'],
        # Statuses a player weapon already applies through its damage (the only types Runtime requests).
        'allowlist': [{'type': item['type'], 'id': item['semanticId'], 'name': item['name'],
            'family': item['family']} for item in research['allowlist']]}


def wielder_section(pins: Pins, research: dict) -> dict:
    """The item a player's avatar holds (research/event-wielder-F5FEE03DCFDB.json): wielder slot 0, the inventory
    selection written by the same switch, and the held entity's descriptor type."""
    w, i, e = research['wielder'], research['inventory'], research['entityTypes']
    pins.rip(0x9AAF53, 'mov rcx, qword ptr [rip + 0x297b4c6]', 'wielder manager global (weapon switch)', w['global'])
    pins.use(0x785E10, 'mov r8d, dword ptr [rcx + 0x38]', 'wielder hash capacity')
    pins.use(0x785E14, 'mov r10d, dword ptr [rcx + 0x40]', 'wielder hash multiplier')
    pins.use(0x785E3A, 'mov r11, qword ptr [rcx + 0x30]', 'wielder hash buckets')
    pins.use(0x785E43, 'mov r14d, dword ptr [rcx + 0x3c]', 'wielder hash empty key')
    pins.use(0x785E7F, 'mov r14d, dword ptr [r9 + 4]', 'wielder bucket value = instance')
    pins.use(0x785E9B, 'mov rax, qword ptr [rbp + 0x60]', 'wielder slot records')
    pins.use(0x785EA3, 'imul r9, r14, 0x1d0', 'wielder instance stride')
    pins.use(0x785EAA, 'shl r10, 4', 'wielder slot stride 0x50')
    pins.use(0x785EBA, 'mov dword ptr [r10 + rax], edi', 'wield stores the held entity')
    pins.rip(0xA96062, 'mov rcx, qword ptr [rip + 0x28906cf]', 'inventory manager global (switch caller)', i['global'])
    pins.use(0x9AAA76, 'mov r9d, dword ptr [rcx + 0x30]', 'inventory hash capacity')
    pins.use(0x9AAA7A, 'mov r10d, dword ptr [rcx + 0x38]', 'inventory hash multiplier')
    pins.use(0x9AAA9D, 'mov r11, qword ptr [rcx + 0x28]', 'inventory hash buckets')
    pins.use(0x9AAAA5, 'mov edi, dword ptr [rcx + 0x34]', 'inventory hash empty key')
    pins.use(0x9AAAF7, 'shl rcx, 4', 'inventory record stride 0x30')
    pins.use(0x9AAB0A, 'mov r15, qword ptr [r13 + 0x50]', 'inventory records')
    pins.use(0x9AAC0F, 'mov dword ptr [r15 + 0x1c], ebp', 'the switch writes the selection')
    pins.use(0x9AAC49, 'mov edi, dword ptr [rdx]', 'selection 1: primary')
    pins.use(0x9AAC4D, 'mov edi, dword ptr [rdx + 4]', 'selection 2: secondary')
    pins.rip(0xFD9D50, 'mov r10, qword ptr [rip + 0x2492241]', 'entity manager global (entity map)', e['global'])
    pins.use(0xFD9D68, 'mov r9d, dword ptr [r10 + 0xf1aeb8]', 'entity map capacity')
    pins.use(0xFD9D83, 'mov rbx, qword ptr [r10 + 0xf1aeb0]', 'entity map buckets')
    pins.use(0xFD9DDB, 'lea rax, [rax + 0x1e65e3]', 'entity descriptor = manager + 0xF32F18 + 24 * index')
    if (w['hash'], w['slots'], w['stride'], w['slotStride'], w['slotCount'], i['hash'], i['records'], i['stride'],
            i['selection'], e['map'], e['descriptors'], e['stride']) != (0x30, 0x60, 0x1D0, 0x50, 5, 0x28, 0x50, 0x30,
            0x1C, 0xF1AEB0, 0xF32F18, 24):
        raise ValueError('wielder or inventory layout changed')
    return {'wielder': w['global'], 'wielderHash': w['hash'], 'slots': w['slots'], 'stride': w['stride'],
        'slotStride': w['slotStride'], 'slotCount': w['slotCount'],
        'inventory': i['global'], 'inventoryHash': i['hash'], 'records': i['records'], 'recordStride': i['stride'],
        'selection': i['selection'],
        'selections': {int(k): {'offset': v['offset'], 'slot': v['slot'], 'proven': v['proven']}
            for k, v in i['selections'].items()},
        'entities': e['global'], 'entityMap': e['map'], 'descriptors': e['descriptors'], 'descriptorStride': e['stride'],
        'descriptorEntity': e['entity']}


def heal_section(pins: Pins, research: dict) -> dict:
    callable_ = research['callable']['heal_add_fraction']
    pins.use(0x91EA3C, 'call 0x927050', 'heal: IsDead gate')
    pins.use(0x91EA86, 'cmovl ecx, eax', 'heal: clamp to max health')
    pins.use(0x91EA17, 'test byte ptr [r12 + 0x14], 1', 'heal: owning-peer gate')
    return {'rva': callable_['rva'], 'prologue': callable_['prologue'], 'signature': callable_['signature']}


def build() -> dict:
    combat = json.loads(COMBAT.read_text(encoding='utf-8'))
    state = json.loads(STATE.read_text(encoding='utf-8'))
    mission = json.loads(MISSION.read_text(encoding='utf-8'))
    actions = json.loads(ACTIONS.read_text(encoding='utf-8'))
    wielder = json.loads(WIELDER.read_text(encoding='utf-8'))
    for research in (combat, state, mission, actions, wielder):
        if research['writes'] or research['protectionChanges']:
            raise ValueError('event research must be read-only')
    if state['gameDll']['sha256'] != combat['gameDll']['sha256']:
        raise ValueError('event research covers different game.dll builds')
    if not (state['gameDll']['sha256'] == mission['gameDll']['sha256'] == actions['gameDll']['sha256']
            == wielder['gameDll']['sha256']):
        raise ValueError('event research covers different game.dll builds')
    if any(any(r['pinnedBytesMismatchPerSnapshot'].values()) for r in (state, mission, actions, wielder)):
        raise ValueError('a pinned instruction differs between retained snapshots')
    pins = Pins(combat, state, mission, actions, wielder)
    value = {'source': {'research': [COMBAT.name, STATE.name, MISSION.name, ACTIONS.name, WIELDER.name],
            'gameDllSha256': combat['gameDll']['sha256'],
            'imageSize': combat['gameDll']['imageSize'], 'exeImageSize': state['exe']['imageSize']},
        'health': health_section(pins, combat), 'players': players_section(pins, combat),
        'playerAvatars': player_avatars_section(pins, state), 'state': state_section(pins, state),
        'engine': engine_section(pins, state), 'stats': stats_section(pins, state),
        'corpses': corpses_section(pins, mission), 'heal': heal_section(pins, combat),
        'explosion': explosion_section(pins, actions), 'projectile': projectile_section(pins, actions),
        'status': status_section(pins, actions), 'wielder': wielder_section(pins, wielder)}
    value['pins'] = sorted(pins.used, key=lambda pin: (pin['module'], pin['rva']))
    return value


def outputs() -> dict[str, str]:
    return {'domains/event_natives.lua': '-- Generated by scripts/generate_event_natives.py; do not edit.\nreturn '
        + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale event natives: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
