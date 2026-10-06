"""The in-mission teammate stratagem HUD (the panels the game shows while the stratagem key is held), read-only, proven on
build F5FEE03DCFDB from the game.dll image and the retained mission snapshots
(docs/research/teammate-hud-F5FEE03DCFDB.md).

1. Where it lives. The mission HUD (HUD system [game+0x346D538] +0x24E340) updates its squad container at +0x1F8C8
   (0x12EBECA / 0x12EBEDA -> 0x182D9E0). The container is drawn while its flags (+0) have bit 4 (0x182DA03..0x182DA10).
   It walks the session player table [game+0x347CED8] (8 entries of 0xC0, the peer id at +0; 0x182DADD..0x182DB49),
   skips this machine's player and gives each other player one panel, at most 3: panel k = container + 0x6A0 +
   k * 0xA6A0 (0x182DBA9..0x182DBD3, -> 0x182F560).
2. A panel's player. 0x182F560 takes the session entry's peer (+0) to the player manager [game+0x3326468] (players at
   +0x2C8 by peer, stride 0x38; their entity at descriptor +8, 0x182F6BD..0x182F710) and stores that entity in the
   panel (+0xA66C, 0x182F6EB). Its stratagem record is the per-peer record (records [game+0x347CE50], keyed by the
   u64 peer id: 0x1830A8A / 0x1830A91 -> 0x1366DC0).
3. Its four stratagem cards: card j = panel + 0x2A20 + j * 0x14F0 (0x1830C4F..0x1830D29). Each card shows ONE record
   entry, by index (card +0x14B8). Every frame 0x1839FD0 reads that entry's TYPE from the record (record +0x1C0 + index
   * 0x30, via its +0x38 view: 0x183A003 / 0x183A053) and, when it differs from the card's cached type (+0x14C8,
   0x183A05B), takes that type's StratagemInfo row (0x183A06E) and sets the card's icon element (card +0x518) to the
   row's icon (+0xB0, 0x183A1E5..0x183A1F6) and its colours from the row's category (+0xB8). The card's state (ready,
   cooling: 4, unavailable: 5) comes from the same entry's cooldown end (+0x18) against the game clock (0x1830CD3..
   0x1830CF5), by index.
4. So the teammate HUD shows exactly this machine's copy of the teammate's record entry: the raw types the owner's game
   last sent (rpc_sync_stratagems / rpc_sync_stratagem_changes; the receiver 0x11E82D0 writes them unchecked). A custom
   stratagem's owner converts only its OWN copy of the entry (token -> carrier, runtime/stratagem_slot_conversion.lua);
   until its game sends that record again, the copy here still holds the token (Orbital Precision Strike), and the
   custom multiplayer's own thrower check relies on that (custom_stratagems.lua ball_accept: entry type == token).

The snapshots are solo missions: the container exists with every panel unbound (no teammate). They prove the layout
(the container's flags, unbound panels' entity, the cards' elements as GUI elements), not a bound panel.

Output: research/teammate-hud-F5FEE03DCFDB.json.  py scripts/research_teammate_hud.py [--check]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/teammate-hud-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap']
LAYOUT = {
    'hudSystem': 0x346D538, 'missionHud': 0x24E340, 'setUp': 0x24E334,
    'container': 0x1F8C8, 'shownBit': 0x10,
    'sessionPlayers': 0x347CED8, 'sessionStride': 0xC0, 'sessionCount': 8,
    'panels': 0x6A0, 'panelStride': 0xA6A0, 'panelCount': 3, 'panelEntity': 0xA66C,
    'cards': 0x2A20, 'cardStride': 0x14F0, 'cardCount': 4, 'cardEntry': 0x14B8, 'cardType': 0x14C8, 'cardIcon': 0x518,
    'cardState': 0x14CC, 'bandStart': 0x14D4, 'bandEnd': 0x14DC, 'stateReady': 1, 'stateCooling': 4,
    'stateUnavailable': 5,
    'records': 0x347CE50, 'recordStride': 0x1690, 'recordCount': 0x2D200, 'recordEntries': 0x1C0, 'entryStride': 0x30,
    'invalidEntity': 0x3483C34,
}

PROOFS = {
    'container': [
        (0x12EBECA, 'lea rcx, [r14 + 0x1f8c8]', None, 'the mission HUD\'s squad container (+0x1F8C8)'),
        (0x12EBEDA, 'call 0x182d9e0', None, 'its update, every frame'),
        (0x182DA03, 'mov eax, dword ptr [rcx]', None, 'the container\'s flags'),
        (0x182DA08, 'shr eax, 4', None, 'bit 4 ...'),
        (0x182DA10, 'je 0x182df3c', None, '... clear: nothing is updated (not shown)'),
        (0x182DADD, 'mov rbp, qword ptr [rip + {rip}]', 0x347CED8, 'the session player table'),
        (0x182DB3F, 'add rsi, 0xc0', None, 'entries of 0xC0'),
        (0x182DB46, 'cmp ecx, 8', None, '8 entries'),
        (0x182DBA9, 'cmp edi, 3', None, 'at most 3 teammate panels'),
        (0x182DBB8, 'imul rax, rbp, 0xa6a0', None, 'panel stride 0xA6A0'),
        (0x182DBBF, 'add rax, 0x6a0', None, 'panel 0 at +0x6A0'),
        (0x182DBD3, 'call 0x182f560', None, 'each panel updated with its player\'s session entry'),
    ],
    'panel': [
        (0x182F6BD, 'mov r8, qword ptr [r15]', None, 'the session entry\'s peer id (+0)'),
        (0x182F6CE, 'lea rcx, [r9 + 0x2c8]', None, 'the player manager\'s players by peer'),
        (0x182F6DC, 'add rcx, 0x38', None, 'stride 0x38'),
        (0x182F708, 'mov rcx, qword ptr [r9 + rax*8 + 0xe8]', None, 'that player\'s descriptor'),
        (0x182F710, 'mov r8d, dword ptr [rcx + 8]', None, 'its entity'),
        (0x182F6E4, 'mov r8d, dword ptr [rip + {rip}]', 0x3483C34, 'no such player: the invalid entity'),
        (0x182F6EB, 'mov dword ptr [r14 + 0xa66c], r8d', None, 'stored as the panel\'s player entity (+0xA66C)'),
        (0x1830A8A, 'mov rcx, qword ptr [rip + {rip}]', 0x347CE50, 'the per-peer stratagem records'),
        (0x1830A91, 'call 0x1366dc0', None, 'the record of that player\'s peer'),
        (0x1830C4F, 'lea rdi, [r14 + 0x3ed8]', None, 'card 0\'s entry index (+0x2A20 + 0x14B8)'),
        (0x1830CD3, 'mov rcx, qword ptr [rbx + rcx*8 + 0x1a0]', None, 'that entry\'s cooldown end'),
        (0x1830C60, 'mov eax, dword ptr [rdi - 0x14b8]', None, 'a card\'s flags (+0) ...'),
        (0x1830C66, 'shr eax, 4', None, '... bit 4: the card is updated'),
        (0x1830CED, 'mov r15d, 4', None, 'above the clock: cooling (4)'),
        (0x1830CF5, 'mov r15d, 5', None, 'no record or not available: unavailable (5); else ready (1)'),
        (0x1830D00, 'imul rcx, rax, 0x14f0', None, 'card stride 0x14F0'),
        (0x1830D0E, 'add rcx, 0x2a20', None, 'card 0 at +0x2A20'),
        (0x1830D18, 'call 0x1839fd0', None, 'each card updated with the record'),
        (0x1830D26, 'cmp esi, 4', None, '4 cards'),
    ],
    'card': [
        (0x183A003, 'mov eax, dword ptr [rcx + 0x14b8]', None, 'the card\'s record entry index'),
        (0x183A053, 'mov edx, dword ptr [r9 + r12*8 + 0x188]', None, 'that entry\'s stratagem type (record +0x1C0)'),
        (0x183A05B, 'cmp edx, dword ptr [rsi + 0x14c8]', None, 'unchanged since the card\'s cached type ...'),
        (0x183A061, 'je 0x183a358', None, '... nothing is rebuilt'),
        (0x183A06E, 'mov r14, qword ptr [rcx + rdx*8]', None, 'the type\'s StratagemInfo row'),
        (0x183A1E5, 'mov rdx, qword ptr [r14 + 0xb0]', None, 'the row\'s icon'),
        (0x183A1EC, 'lea rdi, [rsi + 0x518]', None, 'the card\'s icon element (+0x518)'),
        (0x183A1F6, 'call 0x1450160', None, 'set to that icon'),
        (0x183A352, 'mov dword ptr [rsi + 0x14c8], eax', None, 'the shown type cached (+0x14C8)'),
        (0x183A358, 'cmp dword ptr [rsi + 0x14cc], r13d', None, 'the card\'s state (+0x14CC) ...'),
        (0x183A367, 'call 0x183aa60', None, '... changed: its state visuals'),
    ],
    # The card's cooldown display: while cooling (4) every frame 1 - remaining / total (the total kept at +0x14C4) goes
    # to 0x183AC90, which stores the lit band (+0x14D4 = 0, +0x14DC = that fraction; ready 0..1, unavailable 0..0) and
    # sets it, as one vector (+0x14D0), on the icon and its frame (shader variable 0x112A6412); the sweep line (+0x670)
    # moves 46 units down with the same fraction (0x183A9C3..0x183A9F9: (round(2) - round(48)) * fraction).
    'cooldown': [
        (0x183A914, 'cmp r13d, 4', None, 'cooling ...'),
        (0x183A952, 'mov r14, qword ptr [r15 + rcx*8 + 0x1a0]', None, '... the entry\'s cooldown end'),
        (0x183A99C, 'movss dword ptr [rsi + 0x14c4], xmm1', None, 'the total remaining kept (+0x14C4)'),
        (0x183A9AE, 'subss xmm9, xmm0', None, '1 - remaining / total'),
        (0x183A9B7, 'call 0x183ac90', None, 'the lit band set to it'),
        (0x183A9E4, 'lea rcx, [rsi + 0x670]', None, 'the sweep line ...'),
        (0x183A9EB, 'mulss xmm6, xmm9', None, '... moved by the same fraction'),
        (0x183ACC6, 'movss dword ptr [rcx + 0x14e4], xmm1', None, 'the band\'s second vector'),
        (0x183ACDD, 'movss dword ptr [rcx + 0x14d4], xmm2', None, 'the lit band\'s start (+0x14D4)'),
        (0x183ACE5, 'movss dword ptr [rcx + 0x14dc], xmm0', None, 'the lit band\'s end (+0x14DC)'),
        (0x183ACCE, 'lea rdi, [rcx + 0x518]', None, 'on the icon element ...'),
        (0x183AD6E, 'lea r8, [rbx + 0x14d0]', None, '... the band vector ...'),
        (0x183AD75, 'mov edx, 0x112a6412', None, '... as shader variable 0x112A6412'),
        (0x183AD7D, 'call 0x14498c0', None, 'set'),
    ],
}
# The card class is also the local HUD's stratagem entry widget (entry + 0x7C0; the same setter 0x1839FD0, research
# stratagem-slot-conversion hudIcon): a drawn local card shows the layout of the icon quad.
LOCAL = {'list': 0x24E340 + 0x146DC0, 'entries': 0x1150, 'entryStride': 0x3760, 'entrySlot': 0x3748, 'widget': 0x7C0,
    'count': 16}
STACK = {'background': 0x110, 'frame': 0x268, 'layer3': 0x3C0, 'icon': 0x518, 'sweep': 0x670}


def element(mem, at: int) -> dict:
    def f(o):
        return struct.unpack('<f', mem.read(at + o, 4))[0]
    return {'drawn': mem.u32(at + 0x110) != 0xFFFFFFFF, 'layer': mem.u32(at + 0xBC), 'x': round(f(0x94), 2),
        'y': round(f(0x9C), 2), 'w': round(f(0x64) * f(0x24), 2), 'h': round(f(0x8C) * f(0x28), 2)}


def local_cards(mem, hud: int) -> list:
    out = []
    for k in range(LOCAL['count']):
        entry = hud + LOCAL['list'] + LOCAL['entries'] + k * LOCAL['entryStride']
        card = entry + LOCAL['widget']
        kind = mem.u32(card + LAYOUT['cardType'])
        if mem.u32(entry + LOCAL['entrySlot']) >= LOCAL['count'] or not kind:
            continue
        band = struct.unpack('<4f', mem.read(card + 0x14D0, 16))
        out.append({'entry': k, 'type': kind, 'state': mem.u32(card + 0x14CC), 'band': [band[1], band[3]],
            'stack': {name: element(mem, card + off) for name, off in STACK.items()}})
    return out


def observe(name: str) -> dict:
    mem = base.Mem(name)
    hud = mem.ptr(mem.game + LAYOUT['hudSystem'])
    out = {'snapshot': name}
    if not hud:
        mem.close()
        out['hud'] = None
        return out
    mission = hud + LAYOUT['missionHud']
    container = mission + LAYOUT['container']
    invalid = mem.u32(mem.game + LAYOUT['invalidEntity'])
    out['setUp'] = mem.read(hud + LAYOUT['setUp'], 1)[0]
    out['containerFlags'] = mem.u32(container)
    panels = []
    for k in range(LAYOUT['panelCount']):
        panel = container + LAYOUT['panels'] + k * LAYOUT['panelStride']
        cards = []
        for j in range(LAYOUT['cardCount']):
            card = panel + LAYOUT['cards'] + j * LAYOUT['cardStride']
            cards.append({'entry': mem.u32(card + LAYOUT['cardEntry']), 'type': mem.u32(card + LAYOUT['cardType']),
                'iconPrimitive': mem.u32(card + LAYOUT['cardIcon'] + 0x110)})
        panels.append({'entity': mem.u32(panel + LAYOUT['panelEntity']), 'unbound':
            mem.u32(panel + LAYOUT['panelEntity']) in (0, invalid), 'cards': cards})
    out['panels'] = panels
    out['invalidEntity'] = invalid
    out['localCards'] = local_cards(mem, hud)
    mem.close()
    return out


def build() -> dict:
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    observations = [observe(name) for name in SNAPSHOTS]
    for o in observations:
        if not o.get('setUp'):
            raise ValueError('the mission HUD is not set up in ' + o['snapshot'])
        if not all(p['unbound'] for p in o['panels']):
            raise ValueError('a solo snapshot has a bound teammate panel: ' + o['snapshot'])
        for card in o['localCards']:
            st = card['stack']
            quad = {(st[n]['x'], st[n]['y'], st[n]['w'], st[n]['h'], st[n]['layer']) for n in
                ('background', 'frame', 'layer3', 'icon')}
            if len(quad) != 1:
                raise ValueError('a local card\'s icon stack is not one quad: %r' % (card,))
            if st['sweep']['layer'] != st['icon']['layer'] + 1:
                raise ValueError('the sweep line is not one layer above the icon: %r' % (card,))
            if card['state'] == 1 and card['band'] != [0.0, 1.0]:
                raise ValueError('a ready card is not fully lit: %r' % (card,))
            if card['state'] == 5 and card['band'] != [0.0, 0.0]:
                raise ValueError('an unavailable card is lit: %r' % (card,))
    if not any(c['stack']['icon']['drawn'] for o in observations for c in o['localCards']):
        raise ValueError('no drawn local card in the snapshots')
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'layout': LAYOUT,
        'semantics': {
            'source': 'each teammate card shows this machine\'s copy of that teammate\'s record entry (by index): its '
                'type -> the StratagemInfo row -> the row\'s icon; its cooldown end -> the card\'s state',
            'copy': 'a teammate\'s record copy holds the raw types its owner\'s game last sent; a custom stratagem\'s '
                'owner converts only its own copy, so here the slot may still hold the token',
            'binding': 'a panel is bound to its player by the player entity it stores (+0xA66C)',
            'stack': 'the card\'s background, frame, a third image and its icon are one quad at one layer (557); the '
                'sweep line (+0x670) lies over it one layer up, the text to its right',
            'cooldown': 'the card\'s cooldown is drawn ON the icon quad: a lit band [+0x14D4, +0x14DC] of its height, set '
                'as a shader vector on the icon and its frame, and the sweep line moved down by the same fraction; an '
                'overlay covering the quad covers both'},
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation, 'observations': observations,
        'unproven': [
            'Live: a bound teammate panel (every retained snapshot is solo).',
            'Which end of the icon the lit band starts at: inferred as the top (the sweep line rests at the top of a '
                'card never used and at its bottom after a cooldown, and moves down as the band grows); and how the '
                'shader draws the unlit part.',
            'When the owner\'s game sends its record again during a mission (then the copy holds the carrier).'],
        'writes': 0, 'protectionChanges': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    body = json.dumps(build(), indent=1) + '\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != body:
            raise SystemExit('stale: ' + OUTPUT.relative_to(ROOT).as_posix())
        print('up to date')
        return
    OUTPUT.write_text(body, encoding='utf-8', newline='\n')
    report = json.loads(body)
    print(json.dumps({'pins': sum(len(v) for v in report['proofs'].values()),
        'observations': report['observations']}, indent=1)[:4000])


if __name__ == '__main__':
    main()
