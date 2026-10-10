"""Stratagem charges: which native member makes a stratagem hold several uses before a cooldown. Read-only research.

Question (0.30.4 user request): "Make it so we can edit charges before cooldown on stratagems." Eagles hold several
uses and then rearm; every other stratagem spends a mission use and cools down after each call. Is there a native
member for charges on a non-Eagle stratagem, and how do charges come back (one at a time, or all at once)?

Proven on build F5FEE03DCFDB from the pinned type library, the retained snapshots (every StratagemInfo row) and the
unprotected game.dll code (exact instruction pins):

1. Uses. StratagemInfo +80 (u32, hidden name length 4) is the use count. When the mission stratagem record is built
   (0x66EFD0) each entry's uses (+0x18C = entry +4) are set from 0x879550: row +80, plus the bonus of a linked row
   (+268 StratagemType, when +272 bit 0 is set), plus the player's upgrades. 0x66D3D0 reads an entry's remaining uses.
2. The rearm pool. StratagemInfo +200 is a StratagemType (hidden name length 20, the length of rearm_stratagem_type is
   a lead, not a proof). It is 49 (StratagemType_EagleRearm: the type library alias length 24 matches) on the ten
   Eagle rows and 0 on every other row. Its four readers in the unprotected code all compare it with the constant 0x31:
   - 0x66D650: Eagle Rearm can be called while any entry of the pool has fewer uses than its maximum (0x879550);
   - 0x66E580: every entry of the pool has 0 uses left (the automatic rearm test);
   - 0xB9A6D0 and its twin 0x135C2C0 (a call starts its cooldown: end = arrival + the effective cooldown 0x8796A0):
     a call of a pool member gives every other pool entry the same cooldown end; a call of Eagle Rearm (type 0x31)
     does the same and refills every pool entry's uses to its maximum (0x879550).
   So "charges before cooldown" exists natively only as the Eagle Rearm pool: N uses (+80), each call followed by the
   row's own cooldown (+104) shared by the whole pool, and all uses come back at once when Eagle Rearm is called (its
   own row cooldown). There is no per-charge recharge and no other pool (the comparisons are against a constant).
3. Joining the pool is a value of +200 that a non-Eagle row can take (the readers are generic over the row; only the
   pool's identity is the constant). Consequences, all from the readers above: the stratagem's calls put every Eagle
   on the stratagem's own cooldown and vice versa; its uses become uses per rearm; Eagle Rearm refills it; and the
   automatic rearm waits until it is empty too, so an unlimited use count (0xFFFFFFFF = -1 in the entry, never 0)
   would stop the automatic rearm of the whole pool. The use decrement at a call is not in the unprotected code.
4. Multiplayer. StratagemInfo is a per-machine type record. Use counts are applied by the mission host (docs/
   stratagem-uses.md); rpc_sync_stratagems carries entries between peers (research/slot-cooldown).

Nothing here writes memory. Requires the research-only package capstone.
Output: research/stratagem-rearm-pool-F5FEE03DCFDB.json. `--check` compares with the committed output.
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
import research_entity_authoring as entity_research  # noqa: E402
import research_weapon_fire_modes as fire_modes  # noqa: E402
import snapshot_regions  # noqa: E402
from scan import xref  # noqa: E402

OUTPUT = ROOT / 'research/stratagem-rearm-pool-F5FEE03DCFDB.json'
CALLDOWN = ROOT / 'research/stratagem-calldown-F5FEE03DCFDB.json'
EAGLE_REARM = 49
USES, COOLDOWN, CATEGORY, REARM, LINKED, LINKED_FLAG = 80, 104, 60, 200, 268, 272
# StratagemInfo members (offset, storage, type, hidden-name length).
MEMBERS = [(CATEGORY, 'ENUM_UINT32', 'StratagemCategoryType', 8), (USES, 'UINT32', None, 4),
    (COOLDOWN, 'FP32', None, 25), (REARM, 'ENUM_UINT32', 'StratagemType', 20),
    (LINKED, 'ENUM_UINT32', 'StratagemType', 30)]

PINS = {
    'maxUses': [
        (0x879576, 'lea rbx, [rip + 0x2f52083]', 'the StratagemInfo row table (one pointer per StratagemType)'),
        (0x879589, 'mov rdi, qword ptr [rbx + rbp*8]', 'the row of the entry\'s type'),
        (0x879592, 'mov r8d, dword ptr [rdi + 0x10c]', 'a linked type (+268) ...'),
        (0x87959E, 'test byte ptr [rdi + 0x110], 1', '... used when +272 bit 0 is set'),
        (0x8795B5, 'sub ecx, dword ptr [rbx + 0x50]', 'the linked row\'s bonus: its maximum minus its own +80'),
        (0x8795BC, 'mov ebx, dword ptr [rdi + 0x50]', 'the row\'s use count (+80)'),
        (0x8795C8, 'add ebx, ecx', 'plus the linked bonus (the player\'s upgrades follow)'),
    ],
    'recordBuild': [
        (0x66F11E, 'mov dword ptr [rdi + 0x188], r8d', 'a new record entry: its StratagemType (entry +0)'),
        (0x66F125, 'call 0x879550', 'its maximum uses'),
        (0x66F12A, 'mov dword ptr [rdi + 0x18c], eax', 'are its uses (entry +4)'),
        (0x66F13A, 'mov qword ptr [rdi + 0x1a0], 0', 'cooldown end 0'),
    ],
    'usesReader': [
        (0x66D3E5, 'mov eax, dword ptr [rdx + rcx*8 + 0x18c]', 'an entry\'s remaining uses (entry +4)'),
        (0x66D40B, 'cmp dword ptr [rax + 0x94], 0', 'a row with a cooldown type reads a shared pool of uses instead'),
    ],
    'rearmAvailable': [
        (0x66D687, 'mov r8d, dword ptr [rsi + rcx*8 + 0x188]', 'each entry\'s type'),
        (0x66D694, 'mov rax, qword ptr [r14 + r8*8]', 'its row'),
        (0x66D698, 'cmp dword ptr [rax + 0xc8], 0x31', 'a row in the Eagle Rearm pool (+200 = 49) ...'),
        (0x66D6B2, 'call 0x879550', '... its maximum uses'),
        (0x66D6BF, 'call 0x66d3d0', '... its remaining uses'),
        (0x66D6C4, 'cmp eax, edi', 'fewer than the maximum ...'),
        (0x66D6C6, 'jb 0x66d6ea', '... Eagle Rearm is available'),
    ],
    'automaticRearm': [
        (0x66E696, 'cmp dword ptr [rax + 0xc8], 0x31', 'every entry of the pool ...'),
        (0x66E6A5, 'call 0x66d3d0', '... its remaining uses'),
        (0x66E6AA, 'test eax, eax', 'any non-zero ...'),
        (0x66E6AC, 'jne 0x66e6bd', '... the pool is not empty (an unlimited count, -1, is never 0)'),
    ],
    'callCooldown': [
        (0xB9A7DA, 'mov edx, dword ptr [rdi + rbx + 0x1c0]', 'the called entry\'s type'),
        (0xB9A820, 'call 0x8796a0', 'its effective cooldown (row +104 with the modifiers)'),
        (0xB9A89F, 'add rax, qword ptr [rdi + rbx + 0x1e0]', 'counted from the arrival ...'),
        (0xB9A8A7, 'mov qword ptr [rdi + rbx + 0x1d8], rax', '... is the entry\'s cooldown end'),
        (0xB9A8AF, 'cmp edx, 0x31', 'the call is Eagle Rearm ...'),
        (0xB9A8B4, 'cmp dword ptr [r15 + 0xc8], 0x31', '... or a member of its pool'),
        (0xB9A909, 'cmp dword ptr [rax + 0xc8], 0x31', 'then every other pool entry ...'),
        (0xB9A91A, 'mov qword ptr [rsi + rbx + 0x1d8], rax', '... takes the same cooldown end'),
        (0xB9A92D, 'mov qword ptr [rsi + rbx + 0x1d0], rcx', '... and an activation now'),
        (0xB9A935, 'cmp dword ptr [rdi + rbx + 0x1c0], 0x31', 'a call of Eagle Rearm itself ...'),
        (0xB9A94C, 'call 0x879550', '... computes each pool entry\'s maximum ...'),
        (0xB9A951, 'mov dword ptr [rsi + rbx + 0x1c4], eax', '... and refills its uses (all at once)'),
    ],
    'callCooldownTwin': [
        (0x135C428, 'cmp dword ptr [r13 + 0xc8], 0x31', 'the twin call path: a pool member ...'),
        (0x135C480, 'cmp dword ptr [rax + 0xc8], 0x31', 'every other pool entry ...'),
        (0x135C491, 'mov qword ptr [rsi + rbx + 0x1d8], rax', '... takes the same cooldown end'),
        (0x135C4AC, 'cmp dword ptr [rdi + rbx + 0x1c0], 0x31', 'Eagle Rearm itself ...'),
        (0x135C4C3, 'call 0x879550', '... the maximum ...'),
        (0x135C4C8, 'mov dword ptr [rsi + rbx + 0x1c4], eax', '... refills the uses'),
    ],
}
# The only instructions in the unprotected code that compare StratagemInfo +200 (a dword at +0xC8 of a row) with a
# constant: every one is 0x31. Recomputed by scanning every `cmp dword ptr [reg + 0xc8], imm`.
EXPECTED_COMPARISONS = [0x66D698, 0x66E696, 0xB9A8B4, 0xB9A909, 0x135C428, 0x135C480]

ROWS_LUA = r'''
local Reader=require('hd2runtime/runtime/reader')
local stratagem=require('hd2runtime/core/stratagem')
local b=require('hd2runtime/core/bytes')
local reader=Reader.new(source)
local records,owner=stratagem.capture_all(source,reader,profile)
local out={rows={}}
for _,r in ipairs(records)do
 local bytes=reader.read(owner,r.offset,400)
 out.rows[#out.rows+1]={kind=r.record_kind,id=r.id,hex=b.hex(bytes)}
end
return require('hd2runtime/primary_mapper/json').encode(out)
'''


def native_names() -> dict:
    """StratagemType -> its native type name and catalogued name (research/stratagem-calldown)."""
    out = {}

    def walk(item):
        if isinstance(item, dict):
            if 'nativeTypeName' in item and 'type' in item and 'id' in item:
                out[item['id']] = {'type': item['type'], 'nativeTypeName': item['nativeTypeName'],
                    'catalogued': item.get('catalogued')}
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)
    walk(json.loads(CALLDOWN.read_text(encoding='utf-8')))
    return out


def layout(native) -> list:
    members = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, 'StratagemInfo',
        structured=True)['members']}
    out = []
    for offset, storage, type_name, length in MEMBERS:
        member = members[offset]
        if member.get('storage') != storage or not str(member['name']).endswith('inferred_length=%d' % length):
            raise ValueError('StratagemInfo +%d changed' % offset)
        if type_name and member.get('type_hash') != native.probe.dl_hash(type_name):
            raise ValueError('StratagemInfo +%d is no longer %s' % (offset, type_name))
        out.append({'offset': offset, 'storage': storage, 'type': type_name, 'hiddenNameLength': length})
    lengths = fire_modes.TypeLibrary(native.typelib, native.probe).lengths('StratagemType')
    if lengths.get(EAGLE_REARM) != len('StratagemType_EagleRearm'):
        raise ValueError('StratagemType 49 is no longer EagleRearm')
    return out


def comparisons(img) -> list:
    found = []
    for ins in img.immediates(0xC8, 4, limit=200000):
        if ins.mnemonic == 'cmp' and ins.op_str.startswith('dword ptr [') and '+ 0xc8]' in ins.op_str \
                and ', 0x' in ins.op_str and 'rsp' not in ins.op_str and 'rbp' not in ins.op_str:
            found.append({'rva': ins.address, 'asm': ins.mnemonic + ' ' + ins.op_str,
                'constant': int(ins.op_str.rsplit(', ', 1)[1], 16)})
    return found


def extract(row, names) -> dict:
    raw = bytes.fromhex(row['hex'])
    name = names.get(row['id'], {})
    return {'id': row['id'], 'type': row['kind'], 'nativeTypeName': name.get('nativeTypeName'),
        'catalogued': name.get('catalogued'), 'category': struct.unpack_from('<I', raw, CATEGORY)[0],
        'uses': struct.unpack_from('<I', raw, USES)[0],
        'cooldown': round(struct.unpack_from('<f', raw, COOLDOWN)[0], 4),
        'rearmPool': struct.unpack_from('<I', raw, REARM)[0],
        'linkedUses': struct.unpack_from('<I', raw, LINKED)[0] if raw[LINKED_FLAG] & 1 else 0}


# Retained snapshots taken with third-party data mods loaded (the user's own setup, 2026-10-08): their rows are recorded
# as observations, never as native values. Leads only.
MODDED = ('F5FEE03DCFDB-20261008T162919Z-weapon-roots-scythe-dagger.hd2snap',
    'F5FEE03DCFDB-20261008T163453Z-weapon-roots-defender-etool.hd2snap')


def rows(names) -> dict:
    """Every StratagemInfo row's members of interest: equal in every unmodded retained snapshot (pointers excluded);
    the differences of the modded snapshots are listed."""
    folder = build_profile.snapshot_directory()
    snapshots = sorted(folder.glob(build_profile.BUILD_ID + '-*.hd2snap'))
    first, observed = None, []
    for path in snapshots:
        report = json.loads(snapshot_regions.run_lua(ROWS_LUA, snapshot=path))
        table = sorted((extract(row, names) for row in report['rows']), key=lambda item: item['type'])
        if first is None:
            first = table
            continue
        changed = [{'type': a['type'], 'nativeTypeName': a['nativeTypeName'],
            'changed': {k: [a[k], b[k]] for k in a if a[k] != b[k]}} for a, b in zip(first, table) if a != b]
        if changed and path.name not in MODDED:
            raise ValueError('the StratagemInfo members differ in the unmodded snapshot ' + path.name)
        if path.name in MODDED:
            observed.append({'snapshot': path.name, 'rowsChangedByThirdPartyMods': changed})
    return {'snapshots': [p.name for p in snapshots], 'unmoddedIdentical': True, 'rows': first,
        'moddedSnapshots': observed,
        'moddedNote': ('Taken with third-party data mods loaded (lead only, never native evidence). One of them joins '
            'the CarpetBomb row to the Eagle Rearm pool (+200 = 49, uses 2, cooldown 15): the same member this research '
            'proves from the code, set by another author.')}


def build() -> dict:
    native = entity_research.Native()
    img = xref.CodeImage.from_snapshot()
    proofs = {group: [img.pin(rva, role, asm) for rva, asm, role in items] for group, items in PINS.items()}
    found = comparisons(img)
    if [c['rva'] for c in found] != EXPECTED_COMPARISONS or {c['constant'] for c in found} != {EAGLE_REARM}:
        raise ValueError('the readers of StratagemInfo +200 changed: %r' % found)
    table = rows(native_names())
    pool = [r for r in table['rows'] if r['rearmPool']]
    if {r['rearmPool'] for r in pool} != {EAGLE_REARM} or any(r['category'] != 0 for r in pool):
        raise ValueError('a row outside the Eagle family names a rearm pool')
    if len(pool) != 10 or any((r['nativeTypeName'] or '').find('Eagle') != 0 for r in pool):
        raise ValueError('the Eagle Rearm pool is not the ten Eagle rows')
    rearm = next(r for r in table['rows'] if r['type'] == EAGLE_REARM)
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'writes': 0, 'protectionChanges': 0,
        'gameDll': {'sha256': img.sha256}, 'layout': layout(native), 'proofs': proofs,
        'rearmPoolComparisons': found,
        'pool': {'member': 'StratagemInfo +200 (StratagemType)', 'value': EAGLE_REARM, 'valueName': 'EagleRearm',
            'members': [{'id': r['id'], 'type': r['type'], 'nativeTypeName': r['nativeTypeName'],
                'catalogued': r['catalogued'], 'uses': r['uses'], 'cooldown': r['cooldown']} for r in pool],
            'rearm': {'id': rearm['id'], 'type': rearm['type'], 'cooldown': rearm['cooldown']}},
        'rows': table,
        'model': {
            'charges': ('Native charges exist only as the Eagle Rearm pool: a row whose +200 is 49 holds +80 uses per '
                'rearm; each call starts the row\'s own cooldown (+104) on every pool entry; Eagle Rearm refills every '
                'pool entry to its maximum at once and puts the pool on the rearm\'s cooldown. No other pool exists: '
                'every reader compares +200 with the constant 0x31.'),
            'recharge': 'All at once, by calling Eagle Rearm (or its automatic call once the whole pool is empty); '
                'never one charge at a time.',
            'nonEagle': ('A non-Eagle row spends +80 as mission uses: every call starts its own cooldown and nothing '
                'refills the uses. Setting its +200 to 49 joins the Eagle Rearm pool (the readers above are generic '
                'over the row): its +80 becomes uses per rearm and its cooldown is shared with the Eagles.'),
            'unlimited': ('An unlimited use count (0xFFFFFFFF, -1 in the entry) is never 0, so a pool member with '
                'unlimited uses stops the automatic rearm of the whole pool (0x66E580); a member must keep a finite '
                'count.'),
            'timing': ('+80 is read when the mission record is built (0x66EFD0) and at every rearm (0x879550); +200 is '
                'read at every call and rearm test. A change applies fully from the next mission; uses already '
                'counted keep their value until the next rearm.'),
            'multiplayer': ('StratagemInfo is a per-machine type record. The mission host applies use counts '
                '(docs/stratagem-uses.md) and rpc_sync_stratagems carries entries between peers (research/'
                'slot-cooldown). Every machine should run the same mod.'),
        },
        'notTraced': [
            'The use decrement at a call: the writer is not in the unprotected code (like the cooldown write, '
            'research/slot-cooldown).',
            'Whether the mission HUD shows a non-Eagle pool member with the Eagle rearm presentation: the HUD reads '
            'uses generically, but no pool member outside the Eagles exists natively. Needs a live test.',
        ],
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
    print(json.dumps({'pool': [m['nativeTypeName'] for m in result['pool']['members']],
        'identical': result['rows']['unmoddedIdentical'],
        'comparisons': [hex(c['rva']) for c in result['rearmPoolComparisons']]}, indent=1))


if __name__ == '__main__':
    main()
