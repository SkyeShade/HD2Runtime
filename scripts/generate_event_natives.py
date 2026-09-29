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
OUTPUT = ROOT / 'domains/event_natives.lua'


class Pins:
    """Pinned instructions from the research outputs, per module ('game' = game.dll, 'exe' = the executable)."""

    def __init__(self, combat: dict, state: dict):
        self.by_rva = {'game': {}, 'exe': {}}
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
            'dealt_kills': keys['dealt_kills'], 'received_deaths': keys['received_deaths']}}


def heal_section(pins: Pins, research: dict) -> dict:
    callable_ = research['callable']['heal_add_fraction']
    pins.use(0x91EA3C, 'call 0x927050', 'heal: IsDead gate')
    pins.use(0x91EA86, 'cmovl ecx, eax', 'heal: clamp to max health')
    pins.use(0x91EA17, 'test byte ptr [r12 + 0x14], 1', 'heal: owning-peer gate')
    return {'rva': callable_['rva'], 'prologue': callable_['prologue'], 'signature': callable_['signature']}


def build() -> dict:
    combat = json.loads(COMBAT.read_text(encoding='utf-8'))
    state = json.loads(STATE.read_text(encoding='utf-8'))
    for research in (combat, state):
        if research['writes'] or research['protectionChanges']:
            raise ValueError('event research must be read-only')
    if state['gameDll']['sha256'] != combat['gameDll']['sha256']:
        raise ValueError('event research covers different game.dll builds')
    if any(state['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    pins = Pins(combat, state)
    value = {'source': {'research': [COMBAT.name, STATE.name], 'gameDllSha256': combat['gameDll']['sha256'],
            'imageSize': combat['gameDll']['imageSize'], 'exeImageSize': state['exe']['imageSize']},
        'health': health_section(pins, combat), 'players': players_section(pins, combat),
        'playerAvatars': player_avatars_section(pins, state), 'state': state_section(pins, state),
        'engine': engine_section(pins, state), 'stats': stats_section(pins, state), 'heal': heal_section(pins, combat)}
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
