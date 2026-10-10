"""Beam conversion in multiplayer (research/docs/beam-conversion-mp-F5FEE03DCFDB.md and
research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md): pins the game.dll instructions of the crash path a converted
machine meets when it applies the replicated state of a REMOTE-owned weapon of a converted type (the ProjectileWeapon
network apply 0x6190C0 finds no instance, takes -1 and stores through it without a test), the three sites that run the
per-network-type apply switch 0xBC2D30, the remote spawn order (create pass from this machine's own list, then the
apply, then post-create), the damage authority split, and the helldivers2.exe network facts (the network config holder,
the engine create that copies a type's default bytes and overwrites only the fields it is given, the received-data
flag +0x234 and its three setters).

The synced-conversion question (would the same conversion on every machine make the remote apply safe?): for every
catalogued convertible root, its network type (from the entity file, domains/beam_conversion.lua) is looked up in the
engine's network config (read from every retained snapshot: 1,855 types sorted by hash, the index the apply switch
takes), its switch case is followed through the compiler's shared tails to its ret, and the case must be straight-line
(only the apply-call pattern, no conditional branch) with exactly one call of the ProjectileWeapon apply 0x6190C0. That
call is pinned per type. The case is chosen by the network TYPE alone: nothing in it reads the sender, the sender's
component list or the received fields before calling 0x6190C0, so a remote weapon of a converted type is applied
through 0x6190C0 on this machine whatever the owner converted.

Read-only, offline, build F5FEE03DCFDB: every pin (game.dll and helldivers2.exe) is checked byte for byte in every
retained snapshot. Output: research/beam-conversion-mp-F5FEE03DCFDB.json.
    py -3 scripts/research_beam_conversion_mp.py
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
from research_beam_damage import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/beam-conversion-mp-F5FEE03DCFDB.json'
CATALOGUE = ROOT / 'domains/beam_conversion.lua'

NETWORK_CONFIG_HOLDER = 0x1A10268     # helldivers2.exe: [[exe + this]] = the network config
CONFIG_TYPE_COUNT, CONFIG_TYPES, TYPE_STRIDE = 0x70, 0x78, 0x50
SWITCH_TABLE, SWITCH_BOUND = 0xBD9EB8, 0x73E
PROJECTILE_APPLY, PROJECTILE_MANAGER = 0x6190C0, 0xF0B3B8

PROOFS = {
    'projectileApply 0x6190C0 (no instance: -1, then an unchecked store)': [
        (0x619119, 'mov eax, dword ptr [r11 + r8*8]', None, 'the ProjectileWeapon instance hash probe ...'),
        (0x61911D, 'cmp eax, edi', None, '... key 0 / empty stops ...'),
        (0x61912C, 'mov eax, 0xffffffff', None, 'not found: index -1'),
        (0x61913B, 'mov r8, qword ptr [rbx + 0x80]', None, 'the instance array [manager + 0x80] ...'),
        (0x619147, 'mov ecx, eax', None, '... index (0xFFFFFFFF, zero-extended) ...'),
        (0x619149, 'lea r9, [rcx + rcx*2]', None, '... x 3 ...'),
        (0x619156, 'mov dword ptr [r8 + r9*4], eax', None, '... x 4: a 12-byte record 48 GB past the array, no test'),
    ],
    'applySwitch 0xBC2D30 callers': [
        (0xFDC29B, 'call 0xbc2d30', None, 'remote spawn: the replicated state applied before post-create'),
        (0xFDDE6A, 'call 0xbc2d30', None, 'every update, objects with received data'),
        (0xFDBE10, 'call 0xbc2d30', None, 'a migration to this machine'),
        (0xBC2D4D, 'test r8b, r8b', None, 'the switch entry'),
    ],
    'applySwitch 0xBC2D30 dispatch (by network type index only)': [
        (0xBC2D52, 'mov r8, qword ptr [rax + 0x40]', None, 'r8b = 1: the engine API ...'),
        (0xBC2D56, 'mov rax, qword ptr [r8 + 0xb0]', None, '... +0xB0 (received data for this object?) ...'),
        (0xBC2D65, 'je 0xbc685e', None, '... none: nothing is applied'),
        (0xBC2DA1, 'cmp eax, 0x73e', None, 'the network type index, 1,855 cases'),
        (0xBC2DB3, 'mov ecx, dword ptr [rdx + rax*4 + 0xbd9eb8]', None, 'the case table, indexed by the type alone'),
        (0xBC2DBD, 'jmp rcx', None, 'into the type\'s straight-line case'),
    ],
    'remote spawn 0xFDC140 (create from this machine\'s list, apply, post-create)': [
        (0xFDC25A, 'call 0x581320', None, 'the create pass: one instance per entry of THIS machine\'s membership list'),
        (0xFDC27A, 'cmp byte ptr [rbp], 0', None, 'the spawn\'s locally-created flag ...'),
        (0xFDC27E, 'jne 0xfdc2a0', None, '... set (owned here): no apply'),
        (0xFDC293, 'mov r8b, 1', None, 'remote: the apply switch with the received-data test'),
        (0xFDC2B1, 'call 0x581780', None, 'post-create, after the apply'),
    ],
    'damage authority (the shooter decides, the owner applies)': [
        (0x925AF7, 'test byte ptr [rdx + 0x14], 1', None, 'the damaged entity owned here? ...'),
        (0x925B1C, 'call 0x6b2a90', None, '... yes: its synced health is changed here'),
        (0xBF2FC5, 'mov ecx, 0xf2b32a25', None, '... no: RPC 0xF2B32A25 to its owner (target + four 4-byte values)'),
    ],
    'ProjectileWeapon network-state array (the -1 store\'s base)': [
        (0x6191AF, 'mov dword ptr [rcx + 0x2c], 0x180', None, 'manager init: capacity 384 instances'),
        (0x619406, 'mov qword ptr [rbx + 0x80], rax', None, 'the 12-byte-per-instance array, allocated at init'),
    ],
}

EXE_PROOFS = {
    'engine create 0x34B6F0 (a type\'s default bytes, then only the given fields)': [
        (0x34B719, 'mov rax, qword ptr [rip + {rip}]', NETWORK_CONFIG_HOLDER, 'the network config holder'),
        (0x34B72E, 'mov r10d, dword ptr [r14 + 0x70]', None, 'the config\'s type count'),
        (0x34B815, 'call 0x1267850', None, 'the type\'s default data copied into the new buffer'),
        (0x34B840, 'cmp dword ptr [r8 + rbx*4], eax', None, 'each given field found by hash in the type (+0x38)'),
        (0x34B884, 'call 0x34b270', None, 'only a given field is written over its default'),
    ],
    'received-data flag +0x234 (game.dll api +0xB0 -> session vtable +0x100)': [
        (0x297B51, 'cmp qword ptr [rax + 8], rcx', None, 'the object\'s +8 equals the session\'s +0x20: false'),
        (0x297B5F, 'movzx eax, byte ptr [rax + 0x234]', None, 'else its received-data flag'),
        (0x2975F3, 'mov byte ptr [rsi + 0x234], 1', None, 'set by receive path 1'),
        (0x299BF9, 'mov byte ptr [r8 + 0x234], 1', None, 'set by receive path 2'),
        (0x29D1C4, 'mov byte ptr [rbx + 0x234], 1', None, 'set by receive path 3'),
    ],
}

# A case: blocks of {mov edx, [rbp+0x28]; lea rcx, [rbx+manager]; lea r9, [rbp+0x20]; mov r8, rdi; call apply},
# joined by unconditional jumps into shared tails, ended by the epilogue and ret.
CASE_FORMS = {('mov', 'edx, dword ptr [rbp + 0x28]'), ('lea', 'r9, [rbp + 0x20]'), ('mov', 'r8, rdi'),
              ('mov', 'rbx, qword ptr [rsp + 0x40]'), ('mov', 'rdi, qword ptr [rsp + 0x48]'), ('add', 'rsp, 0x30'),
              ('pop', 'rbp')}


def catalogue_roots():
    """(resource, network type hash) of every catalogued convertible root (the generated domain)."""
    text = CATALOGUE.read_text(encoding='utf-8')
    out = []
    for match in re.finditer(r'\["resource"\]="(0x[0-9A-F]{16})",\["membership"\]=\{\["row"\]=\d+,\["home"\]=\d+,'
                             r'\["count"\]=\d+,\["networkType"\]=(\d+)', text):
        out.append((match.group(1), int(match.group(2))))
    if not out:
        raise ValueError('no catalogued root in ' + str(CATALOGUE))
    return out


def network_types(name):
    """The engine's network type hashes of one snapshot (sorted by hash: the switch index)."""
    mem = base.Mem(name)
    try:
        config = mem.ptr(mem.ptr(mem.exe + NETWORK_CONFIG_HOLDER))
        count = mem.u32(config + CONFIG_TYPE_COUNT)
        rows = mem.read(mem.ptr(config + CONFIG_TYPES), TYPE_STRIDE * count)
        return [struct.unpack_from('<I', rows, i * TYPE_STRIDE)[0] for i in range(count)]
    finally:
        mem.close()


def follow_case(image, index):
    """A switch case followed through its shared tails: (start, [(call rva, target)], [jump rva]); raises unless it
    is straight-line (the apply-call pattern only, no conditional branch)."""
    start = struct.unpack_from('<i', image.data, SWITCH_TABLE + 4 * index)[0] & 0xFFFFFFFF
    at, calls, jumps = start, [], []
    for _ in range(4000):
        insn = image.insn(at)
        m, ops = insn.mnemonic, insn.op_str
        if m == 'ret':
            return start, calls, jumps
        if m == 'jmp' and ops.startswith('0x'):
            jumps.append(at)
            at = int(ops, 16)
            continue
        if m == 'call' and ops.startswith('0x'):
            calls.append((at, int(ops, 16)))
        elif not ((m == 'lea' and ops.startswith('rcx, [rbx')) or (m, ops) in CASE_FORMS):
            raise ValueError('case %d at %x is not straight-line: %x %s %s' % (index, start, at, m, ops))
        at += insn.size
    raise ValueError('case %d at %x does not end' % (index, start))


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    if snap.executable_sha256.upper() != base.PROFILE_EXE_SHA:
        raise ValueError('snapshot executable differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    exe_name = [k for k in snap.modules if k.endswith('.exe')][0]
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    exe = base.Image(exe_data, exe_base, base.EXE_TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    exe_proofs = {group: [exe.prove(*row) for row in rows] for group, rows in EXE_PROOFS.items()}

    # The convertible roots' network types: the same index in every snapshot.
    roots = catalogue_roots()
    wanted = sorted({n for _, n in roots})
    per_snapshot = {}
    for name in SNAPSHOTS:
        hashes = network_types(name)
        if hashes != sorted(hashes) or len(hashes) != SWITCH_BOUND + 1:
            raise ValueError('%s: the network config is not 1,855 types sorted by hash' % name)
        per_snapshot[name] = {n: hashes.index(n) for n in wanted}
    first = per_snapshot[SNAPSHOTS[0]]
    if any(v != first for v in per_snapshot.values()):
        raise ValueError('a network type index differs between snapshots')
    types, type_pins = [], []
    for n in wanted:
        index = first[n]
        start, calls, jumps = follow_case(image, index)
        applies = [at for at, target in calls if target == PROJECTILE_APPLY]
        if len(applies) != 1:
            raise ValueError('type 0x%08X: %d ProjectileWeapon applies' % (n, len(applies)))
        call = applies[0]
        pins = [image.prove(call - 14, 'lea rcx, [rbx + 0x%x]' % PROJECTILE_MANAGER, None,
                            'type 0x%08X: the ProjectileWeapon manager ...' % n),
                image.prove(call, 'call 0x%x' % PROJECTILE_APPLY, None,
                            'type 0x%08X: ... its apply, unconditional' % n)]
        type_pins += [p for p in pins if p not in type_pins]
        types.append({'networkType': '0x%08X' % n, 'index': index, 'case': '0x%X' % start, 'applyCalls': len(calls),
                      'projectileApplyCall': '0x%X' % call, 'tailJumps': ['0x%X' % j for j in jumps],
                      'roots': [r for r, t in roots if t == n]})
    proofs['per-type ProjectileWeapon apply (every convertible root)'] = type_pins
    pins = [p for rows in proofs.values() for p in rows]
    exe_pins = [p for rows in exe_proofs.values() for p in rows]
    mismatches = {name: base.verify_pins_live(name, pins, exe_pins) for name in SNAPSHOTS}
    if any(mismatches.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % mismatches)
    sites = sorted({t['projectileApplyCall'] for t in types})
    out = {
        'schemaVersion': 2, 'build': 'F5FEE03DCFDB', 'gameDllSha256': base.PROFILE_DLL_SHA,
        'exeSha256': base.PROFILE_EXE_SHA,
        'question': 'What happens on a beam-converted machine when another player is in the lobby, and would the '
                    'same conversion on every machine (a synced conversion) make it safe?',
        'proofs': proofs, 'exeProofs': exe_proofs, 'pinnedBytesMismatchPerSnapshot': mismatches,
        'networkTypes': {'count': SWITCH_BOUND + 1, 'sortedByHash': True, 'convertibleRoots': len(roots),
                         'convertibleTypes': len(types), 'projectileApplySites': sites,
                         'indexIdenticalInSnapshots': len(SNAPSHOTS), 'types': types},
        'verdict': {
            'crash': 'CONFIRMED code path (fault address STRONG): a weapon of a converted type owned by ANOTHER machine '
                     'is built here without ProjectileWeapon; its replicated state apply 0x6190C0 takes index -1 and '
                     'stores 12 bytes at [manager + 0x80] + 12 x 0xFFFFFFFF (unmapped in all nine snapshots): an '
                     'access violation at its spawn, every update with received data, or a migration',
            'syncedConversion': 'CONFIRMED: the same conversion on every machine does NOT make it safe. The apply '
                                'switch picks the case by the network type index alone (0xBC2DA1..0xBC2DBD); the case '
                                'of every one of the %d convertible network types (%d roots) is straight-line and calls '
                                'the ProjectileWeapon apply once, unconditionally (%d shared sites, pinned). The '
                                'remote spawn creates the instances from THIS machine\'s list (0xFDC25A) and then '
                                'applies (0xFDC29B). So on a machine that converted the type, every remote-owned '
                                'weapon of that type reaches the -1 store, whatever its owner converted: with both '
                                'machines converted, EACH crashes when the other\'s weapon of that type spawns. The '
                                'owner\'s conversion only changes what it sends (no ProjectileWeapon fields: the '
                                'type\'s default bytes, exe 0x34B815), not what the receiver calls'
                                % (len(types), len(roots), len(sites)),
            'beamRecordsAndRows': 'not replicated: no network type applies BeamWeapon; hits are decided on the '
                                  'shooter\'s machine, damage to an entity owned elsewhere goes to its owner as RPC '
                                  '0xF2B32A25 (target + four 4-byte values; their meaning and any id in them NOT '
                                  'traced)',
            'ownWeapon': 'STRONG: our own converted weapon is safe on every machine (owned objects are never '
                         're-applied: the spawn skips the apply when created here, 0xFDC27E; the per-update apply '
                         'tests the received-data flag, exe 0x297B5F, set only by receive paths)',
            'joinerSees': 'our weapon as shipped with replicated rate 0 and seed 0, no beam (BeamWeapon is applied by '
                          'none of the 1,855 network types); enemy damage is decided on our machine',
            'lead': 'NOT a fix, a lead: the -1 store\'s target is [manager + 0x80] + 0xBFFFFFFF4, and the array is '
                    'allocated at the manager\'s init with a fixed capacity (0x6191AF, 0x619406). A committed '
                    'Runtime-owned page at that address would absorb the store. Unproven: that nothing reallocates '
                    'the array or re-initialises the manager, a fixed-address allocation in the adapter, and what a '
                    'remote BeamWeapon instance does (fire reproduction, damage)',
            'runtime': 'apply only solo; the conversion sync (hd2bc/1) never allows an apply with other players on '
                       'this build: the decision is REMOTE_APPLY_UNSAFE even when every member posts the identical '
                       'digest; while converted and another lobby member is present: a loud log and notice, and every '
                       'converted weapon with zero live instances restored at once; a converted weapon in use stays '
                       '(its list cannot change under a live instance); a Runtime that reads another member\'s '
                       'conversions warns its own player not to spawn those types'},
        'writes': 0, 'protectionChanges': 0,
    }
    OUTPUT.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(OUTPUT, len(pins), 'game.dll pins,', len(exe_pins), 'exe pins,', len(types), 'types,', len(sites), 'sites')


if __name__ == '__main__':
    main()
