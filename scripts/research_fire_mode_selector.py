"""The fire-mode selector (WeaponFunctionType Firemode, 3): what binding it on a free input needs. Read-only.

Question (0.30.4 user request): "I cannot change the fire mode of the Hot-Shot: is that due to a specific limit in the
game files?" The R/40-K Hot-Shot lists one fire mode and binds no weapon function to either input, so its one mode can
only be replaced. Can the Firemode function be bound on a free input the way the rate-of-fire selector is (live-proven
on the AR-23 Liberator), and what does the selector then read?

Proven on build F5FEE03DCFDB from the unprotected game.dll code (exact instruction pins) and the fire-mode research
(research/weapon-fire-modes-F5FEE03DCFDB.json):

1. The press of a weapon-function input (0x7552D0) dispatches on the WeaponFunctionType bound to it (the built
   weapon's weapon_data instance +0x350, copied from WeaponData function_info +184 at build: research/weapon-functions)
   through the jump table 0x755954: type 2 runs the rate-of-fire cycle (0x617960), type 3 the fire-mode cycle
   (0x75542B). Nothing in either path depends on the weapon or on the binding being native.
2. The fire-mode cycle (0x75542B): the weapon's state word (weapon_data manager +0x60, 12-byte entries, +4) holds the
   current index in bits 12-13. It resolves the weapon's WeaponData record (0x509A40) and counts the non-empty mode
   slots +144, +148 and +152 (0x755476 .. 0x755497); index = (index + 1) mod that count, stored and replicated (key
   0x31F86165). 0x7567F0 maps index 0 / 1 / 2 to +144 / +148 / +152, and 0x755F90 stores that FireMode as the weapon's
   current mode (entry +0, replicated, key 0x49C250A6), which the weapon-function value reader returns (0x755D48).
3. So the selector reaches at most THREE modes: the quaternary slot (+156) is never counted nor mapped. No weapon
   fills it natively. A fourth listed mode would be dormant.
4. Binding the selector on a free input is therefore data-driven exactly like the rate-of-fire binding: a weapon with
   the Firemode function on an input and two or three modes in +144..+152 cycles them. The binding and the modes are
   read when the weapon is built (the bindings are copied into the weapon_data instance).

Per weapon: every single_mode weapon of the fire-mode research with an unbound input (and the other input not already
Firemode) can take the binding: state 'addable', the bindable inputs listed.

Nothing here writes memory. Requires the research-only package capstone.
Output: research/fire-mode-selector-F5FEE03DCFDB.json. `--check` compares with the committed output.
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
from scan import xref  # noqa: E402

OUTPUT = ROOT / 'research/fire-mode-selector-F5FEE03DCFDB.json'
FIRE_MODES = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'
JUMP_TABLE, CASES = 0x755954, {2: 0x7553DA, 3: 0x75542B}
FIREMODE = 3
MAX_SELECTABLE = 3

PINS = {
    'pressDispatch': [
        (0x755342, 'lea ecx, [r15 - 1]', 'the bound WeaponFunctionType - 1 ...'),
        (0x75534D, 'cmp ecx, 0xb', '... types 1 to 12 ...'),
        (0x755365, 'mov r8d, dword ptr [r9 + rcx*4 + 0x755954]', '... through the jump table'),
        (0x75541F, 'call 0x617960', 'type 2 (ROF): the rate-of-fire cycle'),
    ],
    'fireModeCycle': [
        (0x75542B, 'mov r13, qword ptr [rbp + 0x60]', 'type 3 (Firemode): the weapon state entries'),
        (0x755436, 'mov r14d, dword ptr [r13 + r12*4 + 4]', 'this weapon\'s state word'),
        (0x75543B, 'test r14d, 0xc00', 'bits 10-11 (a charge or safety state) hand over to another function'),
        (0x75545E, 'shr esi, 0xc', 'the current index ...'),
        (0x755461, 'and esi, 3', '... bits 12-13'),
        (0x755471, 'call 0x509a40', 'the weapon\'s WeaponData record'),
        (0x755476, 'cmp dword ptr [rax + 0x90], edi', 'primary_fire_mode (+144) set ...'),
        (0x755480, 'cmp dword ptr [rax + 0x94], 0', 'secondary (+148) set ...'),
        (0x75548D, 'cmp dword ptr [rax + 0x98], 0', 'tertiary (+152) set: the mode count (+156 is not read)'),
        (0x75549F, 'div edi', 'index = (index + 1) mod count'),
        (0x7554B7, 'mov dword ptr [r13 + r12*4 + 4], r14d', 'stored in the state word'),
        (0x7554AF, 'mov edx, 0x31f86165', 'replication key of the state'),
        (0x7554D3, 'call 0xfd97e0', 'replicated'),
        (0x7554DD, 'call 0x7567f0', 'the FireMode of the new index'),
        (0x7554EC, 'call 0x755f90', 'becomes the current mode'),
    ],
    'indexToMode': [
        (0x756810, 'call 0x509a40', 'the WeaponData record'),
        (0x75683B, 'mov eax, dword ptr [rax + 0x90]', 'index 0: +144'),
        (0x75682F, 'mov eax, dword ptr [rax + 0x94]', 'index 1: +148'),
        (0x756823, 'mov eax, dword ptr [rax + 0x98]', 'index 2: +152 (any other index: None)'),
    ],
    'currentMode': [
        (0x756039, 'mov dword ptr [r12 + r15*4], r14d', 'the weapon\'s current FireMode (entry +0)'),
        (0x75602A, 'mov edx, 0x49c250a6', 'replication key'),
        (0x756050, 'call 0xfd97e0', 'replicated'),
        (0x755D48, 'mov eax, dword ptr [rax + rcx*4]', 'the weapon-function value of Firemode is that mode'),
    ],
}


def build() -> dict:
    img = xref.CodeImage.from_snapshot()
    proofs = {group: [img.pin(rva, role, asm) for rva, asm, role in items] for group, items in PINS.items()}
    table = [JUMP_TABLE + struct.unpack_from('<i', img.data, JUMP_TABLE + 4 * i)[0] - JUMP_TABLE for i in range(12)]
    for function, target in CASES.items():
        if table[function - 1] != target:
            raise ValueError('the weapon-function press case %d moved' % function)
    research = json.loads(FIRE_MODES.read_text(encoding='utf-8'))
    weapons, quaternary = [], []
    for row in research['weapons']:
        slots = row.get('slots') or []
        if len(slots) == 4 and slots[3]:
            quaternary.append(row['weapon'])
        if row['state'] not in ('single_mode', 'selectable'):
            continue
        selector = row.get('selector') or {}
        values = {'left': selector.get('leftValue'), 'right': selector.get('rightValue')}
        if row['state'] == 'selectable':
            weapons.append({'kind': row['kind'], 'weapon': row['weapon'], 'state': 'selectable',
                'maxModes': MAX_SELECTABLE, 'bindableInputs': []})
            continue
        bindable = [side for side, other in (('left', 'right'), ('right', 'left'))
            if values[side] == 0 and values[other] != FIREMODE]
        weapons.append({'kind': row['kind'], 'weapon': row['weapon'],
            'state': 'addable' if bindable else 'single_mode', 'maxModes': MAX_SELECTABLE if bindable else 1,
            'bindableInputs': bindable, 'inputs': values})
    if quaternary:
        raise ValueError('a weapon fills the quaternary fire mode natively: ' + ', '.join(quaternary))
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'writes': 0, 'protectionChanges': 0,
        'gameDll': {'sha256': img.sha256}, 'proofs': proofs,
        'pressJumpTable': {'table': JUMP_TABLE, 'targets': {str(i + 1): '0x%X' % t for i, t in enumerate(table)}},
        'model': {
            'selector': ('Data-driven: a weapon whose input binds Firemode (3) cycles the non-empty slots +144, +148 '
                'and +152 of its WeaponData record; the binding is copied into the weapon when it is built.'),
            'maxModes': ('Three with a selector: the cycle counts and maps only +144..+152; +156 is never read by it. No '
                'weapon fills +156 natively.'),
            'binding': ('Binding Firemode on an unbound input needs nothing else in the weapon data: the press dispatch, '
                'the cycle, the current mode and the value reader are generic. The rate-of-fire binding, which runs '
                'through the same dispatch, is live-proven on the AR-23 Liberator (weapon_fire_rate_selector_added).'),
            'multiplayer': ('Weapon-local records read on every machine when the weapon is built; the selected index and '
                'mode are replicated with the weapon (keys 0x31F86165, 0x49C250A6). Every machine should run the same '
                'mod.'),
        },
        'weapons': weapons,
        'summary': {state: sum(1 for w in weapons if w['state'] == state)
            for state in ('selectable', 'addable', 'single_mode')},
        'notTraced': ['The weapon menu entry of the fire-mode selector (the rate binding\'s menu entry appeared live on '
            'the Liberator; the same is expected here).',
            'The HUD fire-mode icon of a weapon that never had a selector (the value reader is generic).'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    result = build()
    text = json.dumps(result, indent=1) + '\n'
    if args.check:
        if OUTPUT.read_text(encoding='utf-8') != text:
            raise SystemExit('stale: ' + str(OUTPUT))
        print('up to date')
        return
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    print(json.dumps(result['summary']))


if __name__ == '__main__':
    main()
