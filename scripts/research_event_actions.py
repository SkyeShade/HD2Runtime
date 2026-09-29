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
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    prologue = data[REQUEST:0x13C0A9A].hex()
    templates = call_templates(image)
    common = [t for t in templates if zero_template(t['arguments7to15'])]
    pins = [p for rows in proofs.values() for p in rows]
    observations, relocation = [], {}
    for name in SNAPSHOTS:
        relocation[name] = base.verify_pins_live(name, pins, [])
        observations.append(observe(name, catalog))
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    for o in observations:
        if o['queueCount'] != 0:
            raise ValueError('explosion queue not drained in ' + o['snapshot'])
        if not all(t['match'] for t in o['settingsTable']):
            raise ValueError('settings table disagrees with the explosion catalog in ' + o['snapshot'])
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
        'catalogueTypes': catalog, 'observations': observations,
        'findings': {
            'identity': 'The drain indexes game+0x37CC920 by the request ExplosionType; for all %d catalogued weapon '
                'explosions the entry points at a record with that type, damage type and radii in all %d mission '
                'snapshots.' % (len(catalog), len(SNAPSHOTS)),
            'semantics': 'Stale R-36 Eruptor requests (type 158): source = the Eruptor weapon entity, owner = the local '
                'avatar, creditor = the local peer.',
            'drained': 'The queue count is 0 in every snapshot: requests live for less than a frame.',
            'network': 'No network message call was found in the drain itself; the queue is the local explosion system. '
                'Health is host-authoritative (a remote-owned record is overwritten by synced health), so only a host '
                'request can change enemy health. Whether other machines see the effect is unproven.',
        },
        'unproven': [
            'Arguments 7 and 9..15 beyond the common call template (a Runtime request always passes the template).',
            'Whether the explosion effect is visible on other machines.',
            'The Hellbomb ExplosionType: no Hellbomb request or Hellbomb explosion owner was found; the Hellbomb '
                'entity has no explosive component naming a type.',
            'Frame order of the drain relative to the Lua update callback (a request made in update is drained by the '
                'game\'s own explosion update, within a frame).',
        ],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'callSites': len(templates), 'literalTemplate': len(common), 'eruptorRequests': eruptor,
        'settings': [all(t['match'] for t in o['settingsTable']) for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
