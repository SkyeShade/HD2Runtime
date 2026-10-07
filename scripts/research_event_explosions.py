"""The explosion event: when the game's explosion queue can be read, and what one read sees (research for the
`explosion` event, runtime/event_sources.lua).

Read-only. Proves, on build F5FEE03DCFDB:

1. The per-frame pair. The world update (game.dll 0xAB5000, called by the plugin update 0x4EE6C0, with r14 = the Game
   object global game+0x3326340) first calls the kick wrapper 0x13F73F0 (0xAB55AF) with Game + 0x1024220; that wrapper
   calls the explosion KICK 0x13C5420 with Game + 0x1024220 + 0xC798D8, then (tail jump) the projectile kick 0x13AB0E0.
   Much later in the same update (0xAB5FBF) it calls the explosion GATHER 0x13C6180 with Game + 0x1C9DAF8 (the same
   object), then the projectile gather 0x13BB240.
2. The kick snapshots at most 8 requests: kicked (+0x24) = min(count (+0x20), 8).
3. The gather processes entries 0 .. kicked-1 (0x13C0D10 each, entry = queue + 0x28 + 0x98 * i), then moves the
   unprocessed rest (count - kicked entries) to the front, sets count = count - kicked and kicked = 0. The queue is
   first-in first-out; nothing else removes an entry; RequestExplosion appends at index count.
4. In all seven retained snapshots the explosion queue global (game+0x346D558) points at Game + 0x1C9DAF8, the
   object the update kicks and gathers, and both counts are 0 (captured outside the kick..gather window).
5. Who requests when (direct calls and tail jumps, from the executable image): no function the world update calls
   before the kick can reach RequestExplosion (0x13C0A80); the projectile kick (impacts), the gather itself (a
   blast's damage requests chained explosions, 0x13C0D10 -> 0x12B06C0 -> 0x12B02B0) and the projectile gather all
   reach it, after the explosion kick. Indirect calls (engine API calls, component update tables, network message
   handlers) are not followed.

Consequence for a poll once per Lua update (outside the world update): every request made after the frame's
explosion kick is still queued at the next poll (and only removed by the next frame's gather), so it is seen there;
a request made between a poll and the next kick (Runtime's own Lua requests; an engine callback before the kick) is
processed in that frame and never seen queued, unless more than 8 are pending.

Requires the research-only package capstone.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/scan'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from scan.xref import CodeImage  # noqa: E402
from capstone import x86  # noqa: E402

OUTPUT = ROOT / 'research/event-explosions-F5FEE03DCFDB.json'
SHIP = ['F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap']
MISSION = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
SNAPSHOTS = SHIP + MISSION
REQUEST = 0x13C0A80
QUEUE = 0x346D558
GAME = 0x3326340
SYSTEM_OFFSET = 0x1C9DAF8        # Game + 0x1024220 (the kick wrapper's object) + 0xC798D8
WORLD_UPDATE = 0xAB5000
KICK_CALL = 0xAB55AF
GATHER_CALL = 0xAB5FBF
PER_FRAME = 8
ENTRY, STRIDE, COUNT, KICKED = 0x28, 0x98, 0x20, 0x24

GAME_PROOFS = {
    'order': [
        (0x4EE6E9, 'call 0xab5000', None, 'the plugin update runs the world update'),
        (0xAB5025, 'mov r14, qword ptr [rip + {rip}]', GAME, 'the world update: r14 = the Game object'),
        (0xAB55A8, 'lea rcx, [r14 + 0x1024220]', None, 'kick wrapper argument: Game + 0x1024220'),
        (0xAB55AF, 'call 0x13f73f0', None, 'the world update kicks first'),
        (0x13F7400, 'mov rdi, rcx', None, 'kick wrapper: rdi = Game + 0x1024220'),
        (0x13F7641, 'lea rcx, [rdi + 0xc798d8]', None, 'the explosion system: Game + 0x1C9DAF8'),
        (0x13F7648, 'call 0x13c5420', None, 'explosion kick'),
        (0x13F7682, 'jmp 0x13ab0e0', None, 'then the projectile kick (its impacts request explosions after the kick)'),
        (0xAB5FB8, 'lea rcx, [r14 + 0x1c9daf8]', None, 'gather argument: the same explosion system'),
        (0xAB5FBF, 'call 0x13c6180', None, 'explosion gather, later in the same world update'),
        (0xAB5FCB, 'call 0x13bb240', None, 'then the projectile gather (its impacts queue for the next update)'),
    ],
    'kick': [
        (0x13C548D, 'mov edx, 8', None, 'at most 8 requests a frame'),
        (0x13C5492, 'mov rdi, rcx', None, 'rdi = the explosion system'),
        (0x13C54AB, 'mov eax, dword ptr [rcx + 0x20]', None, 'the queued count'),
        (0x13C54AE, 'cmp eax, edx', None, 'fewer than 8 queued'),
        (0x13C54B0, 'cmovb edx, eax', None, 'kicked = min(count, 8)'),
        (0x13C54BD, 'mov dword ptr [rcx + 0x24], edx', None, 'kicked count +0x24'),
    ],
    'gather': [
        (0x13C61A7, 'xor r12d, r12d', None, 'r12d = 0'),
        (0x13C61AE, 'mov rsi, rcx', None, 'rsi = the explosion system'),
        (0x13C61B5, 'mov ecx, dword ptr [rcx + 0x24]', None, 'the gather processes the kicked requests'),
        (0x13C61E7, 'imul rdi, rax, 0x98', None, 'entry i at 0x98 * i'),
        (0x13C61F4, 'lea r8, [rdi + 0x28]', None, 'entries from +0x28'),
        (0x13C61F8, 'call 0x13c0d10', None, 'process one explosion'),
        (0x13C6627, 'mov ecx, dword ptr [rsi + 0x24]', None, 'loop bound: the kicked count'),
        (0x13C662A, 'inc r14d', None, 'next entry'),
        (0x13C662D, 'cmp r14d, ecx', None, 'entries 0 .. kicked - 1, in order'),
        (0x13C67B4, 'mov eax, dword ptr [rsi + 0x20]', None, 'the queued count now'),
        (0x13C67B7, 'cmp eax, ecx', None, 'kicked is at most the count'),
        (0x13C67B9, 'mov ebx, dword ptr [rsi + 0x20]', None, 'remaining = count'),
        (0x13C67C4, 'cmovb ecx, eax', None, 'processed = min(kicked, count)'),
        (0x13C67C7, 'sub ebx, ecx', None, 'remaining = count - processed'),
        (0x13C67CD, 'lea rdx, [rsi + 0x28]', None, 'move source: the entries'),
        (0x13C67D1, 'imul r8, rax, 0x98', None, 'remaining entries, 0x98 bytes each'),
        (0x13C67D8, 'mov eax, dword ptr [rsi + 0x24]', None, 'the kicked count'),
        (0x13C67DB, 'imul rcx, rax, 0x98', None, 'from entry `kicked`'),
        (0x13C67E2, 'add rdx, rcx', None, 'move source: entry `kicked`'),
        (0x13C67E5, 'lea rcx, [rsi + 0x28]', None, 'to entry 0'),
        (0x13C67E9, 'call 0x20988f0', None, 'the unprocessed rest moves to the front'),
        (0x13C67F4, 'mov dword ptr [rsi + 0x20], ebx', None, 'count = remaining'),
        (0x13C6801, 'mov dword ptr [rsi + 0x24], r12d', None, 'kicked = 0'),
    ],
}


def callees(image, fn, cache):
    """Direct call and tail-jump targets of a function (function roots)."""
    if fn in cache:
        return cache[fn]
    out, own = set(), image.root(fn) or fn
    for ins in image.function_insns(fn):
        if ins.mnemonic in ('call', 'jmp') and ins.operands and ins.operands[0].type == x86.X86_OP_IMM:
            root = image.root(ins.operands[0].imm)
            if root is not None and (ins.mnemonic == 'call' or root != own):
                out.add(root)
    cache[fn] = out
    return out


def closure(image, start, cache, cap=60000):
    """Every function reachable from start through direct calls and tail jumps, and the chain to the request."""
    seen, work, parent = {start}, [start], {}
    while work and len(seen) < cap:
        f = work.pop()
        for c in callees(image, f, cache):
            if c not in seen:
                seen.add(c)
                parent[c] = f
                work.append(c)
    chain = None
    if REQUEST in seen:
        chain, x = [REQUEST], REQUEST
        while x in parent:
            x = parent[x]
            chain.append(x)
        chain.reverse()
    return {'start': start, 'functions': len(seen), 'complete': len(seen) < cap, 'requestReachable': REQUEST in seen,
        'chain': chain, 'seen': seen}


def call_order(image):
    """The world update's direct calls before the kick, and the reach of each side of the kick..gather window."""
    cache = {}
    before = []
    for ins in image.disasm(0xAB5054, KICK_CALL):
        if ins.mnemonic == 'call' and ins.operands[0].type == x86.X86_OP_IMM:
            before.append(ins.operands[0].imm)
    indirect = sum(1 for ins in image.disasm(0xAB5054, KICK_CALL) if ins.mnemonic == 'call'
        and ins.operands[0].type != x86.X86_OP_IMM)
    pre = [closure(image, f, cache) for f in sorted(set(before))]
    # In the kick wrapper, before the explosion kick, only 0x175CA60 is called (when +0xC762F0 is set).
    wrapper_before = [ins.operands[0].imm for ins in image.disasm(0x13F73F0, 0x13F7648)
        if ins.mnemonic == 'call' and ins.operands[0].type == x86.X86_OP_IMM]
    pre += [closure(image, f, cache) for f in wrapper_before]
    post = [closure(image, f, cache) for f in (0x13C5420, 0x13AB0E0, 0x13C6180, 0x13BB240)]
    union = set().union(*(c.pop('seen') for c in pre))
    for c in post:
        c.pop('seen')
    return {'preKickDirectCalls': pre, 'preKickFunctions': len(union), 'preKickIndirectCalls': indirect,
        'postKick': post}


def observe(name):
    mem = base.Mem(name)
    game = mem.ptr(mem.game + GAME)
    queue = mem.ptr(mem.game + QUEUE)
    out = {'snapshot': name, 'game': None if game is None else '%X' % game,
        'queue': None if queue is None else '%X' % queue,
        'queueIsGameSystem': bool(game and queue and queue == game + SYSTEM_OFFSET)}
    out['count'] = mem.u32(queue + COUNT) if queue else None
    out['kicked'] = mem.u32(queue + KICKED) if queue else None
    # Slots ever written keep their bytes (a drained queue is never cleared): the highest one shows how many requests
    # were ever queued at once in this world.
    written, stale = 0, []
    for index in range(256):
        raw = mem.read(queue + ENTRY + STRIDE * index, STRIDE)
        if raw and any(raw):
            written = index + 1
            x, y, z, kind, source, owner, peer = struct.unpack_from('<fffIIIQ', raw, 0)
            stale.append({'slot': index, 'type': kind, 'position': [round(x, 2), round(y, 2), round(z, 2)],
                'source': source, 'owner': owner, 'peer': '%016X' % peer})
    out['slotsEverWritten'] = written
    out['staleEntries'] = stale
    mem.close()
    return out


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[3])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in GAME_PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    order = call_order(CodeImage(data, image_base, 'game.dll'))
    if any(c['requestReachable'] or not c['complete'] for c in order['preKickDirectCalls']):
        raise ValueError('a direct call before the explosion kick can request an explosion')
    reach = {c['start']: c['requestReachable'] for c in order['postKick']}
    if reach != {0x13C5420: False, 0x13AB0E0: True, 0x13C6180: True, 0x13BB240: True}:
        raise ValueError('the requests after the kick changed: %r' % reach)
    observations = [observe(name) for name in SNAPSHOTS]
    for o in observations:
        if not o['queueIsGameSystem'] or o['count'] != 0 or o['kicked'] != 0:
            raise ValueError('the explosion queue is not the drained Game system in ' + o['snapshot'])
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID,
        'gameDll': {'sha256': base.PROFILE_DLL_SHA, 'imageSize': base.IMAGE_SIZE},
        'queue': {'global': QUEUE, 'gameGlobal': GAME, 'systemOffset': SYSTEM_OFFSET, 'count': COUNT, 'kicked': KICKED,
            'entry': ENTRY, 'stride': STRIDE, 'perFrame': PER_FRAME, 'kick': 0x13C5420, 'gather': 0x13C6180,
            'process': 0x13C0D10, 'worldUpdate': WORLD_UPDATE, 'kickCall': KICK_CALL, 'gatherCall': GATHER_CALL},
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': relocation,
        'callOrder': order, 'observations': observations,
        'findings': {
            'fifo': 'Each frame the kick takes min(count, 8) requests and the gather processes exactly those, in order, '
                'then moves the rest to the front: the queue is first-in first-out and a request leaves it only when a '
                'gather processes it.',
            'window': 'The world update kicks (0xAB55AF) long before it gathers (0xAB5FBF). A request made between the '
                'kick and the end of the update (projectile impacts in the projectile kick and gather, the gather\'s own '
                'chained explosions, entity updates in between) is still queued when the update returns.',
            'unseen': 'A request made after a poll and before the next kick is processed in that frame without being '
                'queued at any poll (unless more than 8 are pending): Runtime\'s own requests from the Lua update, and '
                'any engine callback that runs before the game update. No direct call path in the world update before '
                'the kick reaches the request (%d functions checked); indirect calls are not followed.'
                % order['preKickFunctions'],
            'snapshots': 'In all seven snapshots the queue global points at Game + 0x1C9DAF8 and count = kicked = 0. At '
                'most %d slots were ever written in the mission (the queue never held more than that at once).'
                % max(o['slotsEverWritten'] for o in observations),
            'machines': 'The queue is this machine\'s own explosion system (no network send in the drain): a client queues '
                'the explosions it simulates itself (live 2026-10-07: a client\'s queue held the silo missiles\' own '
                'detonations).',
        },
        'unproven': [
            'Where the Lua update runs relative to the world update (outside it: inferred from the projectile spawn '
            'timing, never traced). The dedupe does not depend on it; what a poll sees does.',
            'Indirect calls before the kick: engine API calls in the world update, and engine callbacks before it (the '
            'network impact handlers 0xB9E0C0 / 0xBBADE0 request a peer\'s explosions; when they run is not traced).',
            'Which machine\'s queue holds another player\'s explosions (each machine simulates its own copies).',
        ],
        'writes': 0, 'protectionChanges': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'pins': len(pins), 'preKick': [(hex(c['start']), c['functions']) for c in
        order['preKickDirectCalls']], 'postKick': {hex(k): v for k, v in reach.items()},
        'slotsEverWritten': [o['slotsEverWritten'] for o in observations]}, indent=1))


if __name__ == '__main__':
    main()
