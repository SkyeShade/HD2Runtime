"""Beam conversion in multiplayer (research/docs/beam-conversion-mp-F5FEE03DCFDB.md): pins the game.dll instructions
of the crash path a converted machine meets when it applies the replicated state of a REMOTE-owned weapon of a
converted type (the ProjectileWeapon network apply 0x6190C0 finds no instance, takes -1 and stores through it without a
test), and the three sites that run the per-network-type apply switch 0xBC2D30. Read-only, offline, build F5FEE03DCFDB:
every pin is checked byte for byte in every retained snapshot. The data checks of the write-up (the -1 target unmapped,
the owned-object flag, the network config layout) were run by the research's scratch tools on all nine snapshots and
are recorded in the write-up, not re-derived here.

Output: research/beam-conversion-mp-F5FEE03DCFDB.json.   py -3 scripts/research_beam_conversion_mp.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import snapshot_image  # noqa: E402
from research_beam_damage import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/beam-conversion-mp-F5FEE03DCFDB.json'

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
}


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    if snap.game_dll_sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('snapshot fingerprint differs from the pinned profile')
    image_base, data = snap.module_image('game.dll')
    snap.close()
    image = base.Image(data, image_base, base.TEXT)
    proofs = {group: [image.prove(*row) for row in rows] for group, rows in PROOFS.items()}
    pins = [p for rows in proofs.values() for p in rows]
    mismatches = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(mismatches.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % mismatches)
    out = {
        'schemaVersion': 1, 'build': 'F5FEE03DCFDB', 'gameDllSha256': base.PROFILE_DLL_SHA,
        'question': 'What happens on a beam-converted machine when another player is in the lobby?',
        'proofs': proofs, 'pinnedBytesMismatchPerSnapshot': mismatches,
        'verdict': {
            'crash': 'CONFIRMED code path (fault address STRONG): a weapon of a converted type owned by ANOTHER machine '
                     'is built here without ProjectileWeapon; its replicated state apply 0x6190C0 takes index -1 and '
                     'stores 12 bytes at [manager + 0x80] + 12 x 0xFFFFFFFF (unmapped in all nine snapshots): an '
                     'access violation at its spawn, every update with received data, or a migration',
            'ownWeapon': 'STRONG: our own converted weapon is safe on every machine (owned objects are never '
                         're-applied; the remote copy is built from the remote vanilla list)',
            'joinerSees': 'our weapon as shipped with replicated rate 0 and seed 0, no beam (BeamWeapon is applied by '
                          'none of the 1,855 network types); enemy damage is decided on our machine',
            'runtime': 'apply only solo; while converted and another lobby member is present: a loud log and notice '
                       '(leave the lobby), and every converted weapon with zero live instances restored at once; a '
                       'converted weapon in use stays (its list cannot change under a live instance)'},
        'writes': 0, 'protectionChanges': 0,
    }
    OUTPUT.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(OUTPUT, len(pins), 'pins')


if __name__ == '__main__':
    main()
