"""Generate domains/peer_messaging.lua: the game's PlayFab lobby member data as runtime/peer_channel.lua (development)
reaches it, the network context, the lobby wrapper and its flag, the PlayfabLobby members and state, the engine API
table's two member-data slots and the game's own keys, with the pinned code it re-proves first, from
research/peer-messaging-F5FEE03DCFDB.json (research/docs/runtime-peer-messaging-F5FEE03DCFDB.md).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/peer-messaging-F5FEE03DCFDB.json'
# The native barrage -> call association (scripts/research_barrage_association.py; research/docs/runtime-peer-messaging-
# F5FEE03DCFDB.md section 18): the rest of the barrage's replicated block, its instance state's shell count, the beacon
# fields the dispatcher reads, and the pins of the creation path from the activation to the block's target.
ASSOCIATION = ROOT / 'research/barrage-association-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'domains/peer_messaging.lua'

# The local fire cadence of a projectile-weapon instance (research/docs/runtime-peer-messaging-F5FEE03DCFDB.md section
# 16; 2026-10-05; read-only static research of this build's game.dll, each pin's bytes checked in the seven retained
# snapshots). Instance record (manager +0x78, 0xA8 each): +firing (byte: the trigger held past its delay), +trigger
# (byte: the replicated trigger, pinned by the research's 0x740795), +cooldown (f32 s: runs down every update; each local
# shot adds the interval), +decision (byte: the update's local fire decision), +shots (u32: shots of this trigger hold,
# cleared while not firing). Not network fields: the projectile weapon's network state is three fields (entry +0, the
# current RPM +4, +8).
CADENCE = {'firing': 0x0, 'trigger': 0x1, 'cooldown': 0x8, 'decision': 0x10, 'shots': 0x3C}
CADENCE_PINS = [
    (0x616C01, '41c6042e01', '+0 firing: the trigger (+1) held past its delay'),
    (0x616C38, 'f3410f11442e08', 'every update the cooldown (+8) runs down by the update time, remote copies included'),
    (0x616C27, '41897c2e3c', 'the shot count (+0x3C) is cleared while not firing'),
    (0x616BAA, 'f3410f10742e0c', 'while the trigger is held, the interval (+0xC) ...'),
    (0x616BD5, '4c8d055c0ac301', '... with the name "CyclingTime" ...'),
    (0x616BE2, 'ffd3', '... goes to the engine every update (the cycling follows the local interval)'),
    (0x61726E, '45887c2e10', "the update's local fire decision is kept in +0x10"),
    (0x61742C, '410f2f7c2e08', 'the fire loop: while the cooldown (+8) is spent ...'),
    (0x617438, '4584ff', '... and the fire decision is set ...'),
    (0x6174CE, 'e8ddb3ffff', '... one local shot (remote copies included)'),
    (0x612A0E, '4889442478', 'the shot routine takes the instance record (instances + index x 0xA8) ...'),
    (0x612CFD, 'f30f10400c', '... adds its interval (+0xC) ...'),
    (0x612D07, 'f30f114008', '... to its cooldown (+8) ...'),
    (0x61451E, 'ff403c', '... and counts the shot (+0x3C)'),
    (0x618F7C, '41c704cc77b23a6f', "the projectile weapon's network state: entry +0 ..."),
    (0x619021, '41c704c4a2c2bc4c', '... the current RPM (+4) ...'),
    (0x619080, '41c704c44ec53070', '... and +8: three fields, no interval, cooldown, shot count or cached RPM'),
    (0x611C69, 'f30f11450c', "creation sets the interval from this machine's resolved slot (every machine)"),
    (0xFD9864, '0f1144c708', 'a field reaches the network only through the replication queue {network id, field, '
        'pointer}'),
]


def association() -> dict:
    research = json.loads(ASSOCIATION.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges'] or research['nativeCalls']:
        raise ValueError('the barrage association research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned association instruction differs between retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['gameDll']['sha256'] not in profile:
        raise ValueError('the barrage association research covers another build than schemas/current.lua')
    block, state, beacon = research['block'], research['state'], research['beacon']
    return {'block': {k: block[k] for k in ('shells', 'salvos', 'heading', 'seed')},
        'state': {k: state[k] for k in ('states', 'stride', 'fired')},
        'beacon': {k: beacon[k] for k in ('statePosition', 'creationType', 'activated', 'elementPosition',
            'dispatchPayload', 'dispatchSpawn', 'spawnRequested')},
        'exactTarget': sorted(research['exactTargetPayloads']),
        'pins': sorted(({'module': 'game', 'rva': pin['rva'], 'hex': pin['bytes'], 'label': pin['role']}
            for rows in research['pins'].values() for pin in rows), key=lambda pin: pin['rva'])}


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    if research['writes'] or research['protectionChanges'] or research['nativeCalls']:
        raise ValueError('peer messaging research must be read-only')
    if any(research['pinnedBytesMismatchPerSnapshot'].values()):
        raise ValueError('a pinned instruction differs between retained snapshots')
    profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
    if research['gameDll']['sha256'] not in profile or research['exe']['sha256'] not in profile:
        raise ValueError('the peer messaging research covers another build than schemas/current.lua')
    if not all(s['localIsMember'] for s in research['snapshots']):
        raise ValueError('a retained lobby does not hold the local session peer')
    pins = []
    for rows in research['pins'].values():
        for pin in rows:
            pins.append({'module': pin['module'], 'rva': pin['rva'], 'hex': pin['bytes'], 'label': pin['role']
                or pin['asm']})
    pins.sort(key=lambda pin: (pin['module'], pin['rva']))
    api = research['api']
    ci = research['callIn']
    return {'source': {'research': RESEARCH.name, 'build': research['build'],
            'gameDllSha256': research['gameDll']['sha256'], 'exeSha256': research['exe']['sha256']},
        # [game + global] = the network context; + localPeer its local peer id (u64); + hostPeer the session host's peer id
        # (u64; the game's own game_session_disconnect check); + wrapper the game's lobby wrapper.
        'context': {'global': int(research['context']['global'], 16), 'localPeer': research['context']['localPeer'],
            'hostPeer': research['context']['hostPeer'], 'wrapper': research['context']['wrapper']},
        # The wrapper: + engineLobby the engine lobby (u64; 0 after a leave); + active the byte the game requires before
        # it uses the lobby (cleared by the leave together with engineLobby); + platformPosted the byte the game sets
        # right after its own one-shot "platform_lobby" post in this lobby (0x109408E; cleared by the leave).
        'wrapper': {'engineLobby': research['wrapper']['engineLobby'], 'active': research['wrapper']['active'],
            'platformPosted': research['wrapper']['platformPosted']},
        # The engine lobby: + playfab the PlayfabLobby; PlayfabLobby + memberCount (u32) and + members (u64 peer ids),
        # + state (3 = joined), + handle (the PFLobbyHandle).
        'playfab': {'lobby': research['engineLobby']['playfab'], 'memberCount': research['playfabLobby']['memberCount'],
            'members': research['playfabLobby']['members'], 'state': research['playfabLobby']['state'],
            'joined': research['playfabLobby']['joined'], 'handle': research['playfabLobby']['handle']},
        # [game + registryGlobal] = the engine API registry (exe + registry); + table = T (exe + tableRva); T + memberData
        # and T + setMemberData hold exe + memberDataRva and exe + setMemberDataRva.
        'api': {'registryGlobal': int(api['registryGlobal'], 16), 'registry': int(api['registry'], 16),
            'table': api['table'], 'tableRva': int(api['tableRva'], 16), 'memberData': api['memberData'],
            'setMemberData': api['setMemberData'], 'memberDataRva': int(api['memberDataRva'], 16),
            'setMemberDataRva': int(api['setMemberDataRva'], 16)},
        # The game's own member keys: never written by the Runtime.
        'gameKeys': sorted(research['gameKeys']),
        # The thrown stratagem balls ([game + global]): + total instances (network copies included), + states (0x28 each):
        # + type, + owner (the thrower's session peer id, u64), + entry (its record entry index, i32; -1 in hand),
        # + beaconNetwork (from the landing; noNetwork before). Their own pins (runtime/call_ins.lua re-proves them).
        # The loadout screen's player panels (ui = the loadout screen): panel k = ui + base + k * stride; + peer (its
        # player's peer id, u64; 0 unbound), + record (its record); slot panel = panel + slotPanel: + boundRecord (the
        # same record), + localFlag (0 for a teammate), widgets at + widgets, widgetStride apart, + widgetType (the type
        # shown); a record's owner peer at + recordOwner. Their own pins (stratagem_slot_overlay remote_panels).
        'panels': {k: research['panels'][k] for k in ('base', 'stride', 'count', 'peer', 'record', 'slotPanel',
            'boundRecord', 'localFlag', 'widgets', 'widgetStride', 'widgetType', 'recordOwner')} | {'pins': [
            {'module': 'game', 'rva': pin['rva'], 'hex': pin['bytes'], 'label': pin['role']}
            for pin in research['panels']['pins']]},
        # The Pelican CAS chin gun on a peer that did not spawn it, and the credit of its rounds (custom_mp_pelican.lua):
        # a PW instance's interval (+instanceInterval) and its cached current RPM (+instanceCachedRpm); the resources a
        # host-published Pelican and its chin turret must be; the pins of everything the mirror relies on.
        # A native orbital barrage on every machine (custom_barrages.lua): the bombardment manager's counts, entity map,
        # handles and blocks; the entity handle's network id and created-here bit; component 28's creator peers and
        # component 131's creation types (each by its own entity map). Their own pins.
        # association: the block's other replicated fields (+shells, +salvos, +heading, +seed; the target is
        # manager.blockTarget), the instance state's shells fired (manager + states, stride apart, + fired), the beacon's
        # fields the dispatcher reads (state + statePosition: its position, + creationType: the creation type component
        # 131 copies, + activated; element + elementPosition: the position every machine holds; state + dispatchPayload,
        # + dispatchSpawn = spawnRequested), the payloads whose target IS the spawn position (record +0x88 = 0), and the
        # creation path's own pins (re-proved before any association field is read; the fields above keep theirs).
        'barrage': {'manager': research['barrage']['manager'], 'handle': research['barrage']['handle'],
            'creator': {k: (int(v, 16) if k == 'global' else v) for k, v in research['barrage']['creator'].items()},
            'carrier': {k: (int(v, 16) if k == 'global' else v) for k, v in research['barrage']['carrier'].items()},
            'pins': [{'module': 'game', 'rva': pin['rva'], 'hex': pin['bytes'], 'label': pin['role']}
                for pin in research['barrage']['pins']],
            'association': association()},
        # cadence: the rest of a PW instance's local fire state (CADENCE below), read-only diagnostics of the mirror;
        # its pins join the mirror's, so the Runtime re-proves them before it mirrors anything.
        'pelicanMirror': {k: research['pelicanMirror'][k] for k in ('instanceInterval', 'instanceCachedRpm',
            'pelicanResource', 'chinResource')} | {'cadence': dict(CADENCE), 'pins': [
            {'module': 'game', 'rva': pin['rva'], 'hex': pin['bytes'], 'label': pin['role']}
            for pin in research['pelicanMirror']['pins']] + [
            {'module': 'game', 'rva': rva, 'hex': hexed, 'label': role} for rva, hexed, role in CADENCE_PINS]},
        'callIn': {'global': int(ci['global'], 16), 'total': ci['total'], 'states': ci['states'], 'stride': ci['stride'],
            'type': ci['type'], 'owner': ci['owner'], 'entry': ci['entry'], 'beaconNetwork': ci['beaconNetwork'],
            'noNetwork': ci['noNetwork'], 'pins': [{'module': 'game', 'rva': pin['rva'], 'hex': pin['bytes'],
            'label': pin['role']} for pin in ci['pins']]},
        'pins': pins}


def outputs() -> dict[str, str]:
    return {'domains/peer_messaging.lua': '-- Generated by scripts/generate_peer_messaging.py; do not edit.\n'
        'return ' + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale peer messaging domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
