"""Coverage catalogue of the Trident-pulse beam conversion (EXPERIMENTAL, solo only; branch feature/beam-conversion):
for EVERY player primary, secondary and support weapon whose entity lists ProjectileWeapon (component 321), can the
live-proven in-place conversion (membership 321 -> 270, a BeamWeapon index row naming a Runtime-owned copy of the
LAS-13 Trident's record 18, pulse mode 6) be applied, and with which write set, caveats or refusal?

Read-only, offline, build F5FEE03DCFDB: the pinned entity file, the pinned entity delta and weapon customization
files, the research catalogues, the game.dll image of a retained snapshot (capstone) and every retained snapshot.
Follows research/docs/multi-beam-swap-F5FEE03DCFDB.md, component-swap-liberator-beam-chamber.md and
beam-table-relocation-F5FEE03DCFDB.md (the live-proven Liberator / Talon / Reprimand conversions).

Per weapon: identity and roots; the membership swap and its 4-aligned write window; the BeamWeapon index row (home =
resource mod 46, first empty row on the probe path); the ammunition model (WeaponMagazine chamber byte +156, WeaponHeat
heat per pulse, WeaponRounds, WeaponLinkedAmmo, WeaponCharge) with ownership; customization deltas; fire modes and
weapon functions; package. Every new code fact is pinned (exact bytes) and checked in all nine retained snapshots.

Output: research/beam-conversion-coverage-F5FEE03DCFDB.json.   py -3 scripts/research_beam_conversion_coverage.py
"""
from __future__ import annotations

import collections
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_component_membership as cm  # noqa: E402
import research_event_state as base  # noqa: E402
import research_magazine_attachments as rma  # noqa: E402
from research_beam_damage import SNAPSHOTS  # noqa: E402
from scan import instances, tables, xref  # noqa: E402
from capstone import x86  # noqa: E402

OUTPUT = ROOT / 'research/beam-conversion-coverage-F5FEE03DCFDB.json'
PLAYER_CATALOG = ROOT / 'schemas/player_weapon_authoring_catalog.json'
SUPPORT_CATALOG = ROOT / 'schemas/support_weapon_authoring_catalog.json'
VARIANTS = ROOT / 'research/weapon-variants-F5FEE03DCFDB.json'
ROOTS = ROOT / 'research/weapon-roots-F5FEE03DCFDB.json'
UNDERBARRELS = ROOT / 'research/underbarrel-weapons-F5FEE03DCFDB.json'
FUNCTIONS = ROOT / 'research/weapon-functions-F5FEE03DCFDB.json'
FIRE_MODES = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'
UNLOCKS = ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json'
RESIDENCY = ROOT / 'research/package-residency-F5FEE03DCFDB.json'
MULTI = ROOT / 'research/multi-beam-swap-F5FEE03DCFDB.json'

PROJECTILE, BEAM, MAGAZINE, HEAT, CHARGE, ROUNDS, LINKED = 321, 270, 5, 266, 204, 117, 246
RELOAD, ASSISTED, BACKBLAST, ARC, SPRAY = 113, 60, 62, 265, 315
TRIDENT, TRIDENT_RECORD, TRIDENT_ROW = 0x3C86E871923F3970, 18, 20
MELTAGUN = 0x6CFCC7F8801A0266
BEAM_CAPACITY, BEAM_ROW, BEAM_RECORD_BASE, BEAM_RECORD_STRIDE, BEAM_FILE_RECORDS = 46, 16, 0x2E0, 0x78, 24
MAG_CAPACITY, MAG_RECORD_BASE, MAG_RECORD_STRIDE, CHAMBER = 540, 8640, 160, 156
COPY_FIXED = 32 + 46 * 16 + 24 * 0x78 + 32            # framing + rows + records 0..23 + trailer (beam-table research)
LIVE_PROVEN = {0x968211C0033DCE64: 'AR-23 Liberator', 0x416D053372C4E433: 'LAS-58 Talon',
               0x94BD931B5FB4EE95: 'SMG-32 Reprimand'}
LAS_FIRST = ('LAS-16 Sickle', 'LAS-17 Double-Edge Sickle', 'LAS-12 Sai', 'LAS-58 Talon', 'LAS-99 Quasar Cannon')
MANAGERS = {0x3326648: 'WeaponMagazine', 0x3326CF0: 'WeaponRounds', 0x3326AA8: 'WeaponLinkedAmmo',
            0x3326D48: 'WeaponHeat', 0x3326C20: 'WeaponCharge', 0x3326A20: 'BeamWeapon', 0x33266D8: 'ProjectileWeapon',
            0x3326C10: 'ArcWeapon', 0x3326620: 'StatusEffectReceiver', 0x3326660: 'component 237 (weapon state)'}

# (rva, exact asm, role). Every one is checked byte for byte in all nine retained snapshots.
PINS = {
    'roundAvailable 0x744C20: the ammunition model per state flag (no ProjectileWeapon on any branch)': [
        (0x744CFA, 'test al, al', 'flag bit 7 (WeaponMagazine) ...'),
        (0x744CFC, 'jns 0x744db8', '... clear: the next model'),
        (0x744D02, 'mov rbp, qword ptr [rip + 0x2be193f]', 'WeaponMagazine manager 0x3326648 (chamber model, live-proven)'),
        (0x744DB8, 'bt eax, 8', 'flag bit 8: WeaponRounds ...'),
        (0x744DC2, 'mov r9, qword ptr [rip + 0x2be1f27]', '... WeaponRounds manager 0x3326CF0'),
        (0x744E3D, 'call 0x4fdd20', '... its record'),
        (0x744E42, 'cmp byte ptr [rax + 0x68], 0', '... +0x68 set: the pump/bolt chamber state of WeaponRounds itself'),
        (0x744E75, 'cmp dword ptr [rbx + rax*4 + 4], 0', '... else rounds of the current feed > 0'),
        (0x744E7F, 'bt eax, 0xa', 'flag bit 10: WeaponLinkedAmmo ...'),
        (0x744E85, 'mov rcx, qword ptr [rip + 0x2be1c1c]', '... WeaponLinkedAmmo manager 0x3326AA8'),
        (0x744E8E, 'call 0x7725b0', '... linked (backpack) ammunition available'),
        (0x744E9A, 'bt eax, 9', 'flag bit 9: WeaponHeat ...'),
        (0x744EA2, 'call 0x764ee0', '... heat can-fire'),
    ],
    'roundSpend 0x744690: one round per shot for rounds and linked ammunition too (no ProjectileWeapon)': [
        (0x744896, 'bt eax, 8', 'flag bit 8: WeaponRounds ...'),
        (0x7448BA, 'mov rbp, qword ptr [rip + 0x2be242f]', '... WeaponRounds manager'),
        (0x7449EA, 'dec dword ptr [rdi + rax*4 + 4]', '... one round of the current feed'),
        (0x744A5E, 'bt eax, 0xa', 'flag bit 10: WeaponLinkedAmmo ...'),
        (0x744A79, 'mov rcx, qword ptr [rip + 0x2be2028]', '... WeaponLinkedAmmo manager'),
        (0x744A93, 'call 0x772470', '... one linked round'),
    ],
    'beamShot 0x83F9D0: every pulse spends a round and runs the heat step of the weapon\'s OWN WeaponHeat': [
        (0x83FC0C, 'mov rcx, qword ptr [rip + 0x2ae6a4d]', 'component 237 (weapon state) ...'),
        (0x83FC1B, 'call 0x744690', '... round spend, once per pulse'),
        (0x83FC6D, 'mov rcx, qword ptr [rip + 0x2ae70d4]', 'WeaponHeat instance probe ...'),
        (0x83FD16, 'call 0x7627b0', '... heat step (only with a WeaponHeat instance)'),
    ],
    'heatStep 0x7627B0: heat per pulse = WeaponHeat +116; heat stages fire nothing without ProjectileWeapon': [
        (0x762859, 'call 0x50e1f0', 'the weapon\'s WeaponHeat record (resolver 0x50E1F0)'),
        (0x762920, 'movss xmm0, dword ptr [r10 - 0x30]', 'heat stage 0 threshold (record +0) ...'),
        (0x76292A, 'movss xmm1, dword ptr [r10 - 0x18]', '... stage 1 (+24) ...'),
        (0x762930, 'movss xmm2, dword ptr [r10]', '... stage 2 (+48): a 24-byte stage table'),
        (0x7629A4, 'mov ecx, dword ptr [r11 + rax*8 + 4]', 'the reached stage\'s projectile type (+4) ...'),
        (0x762B52, 'call 0x741df0', '... fired through the generic fire 0x741DF0'),
        (0x762C37, 'call 0x741df0', '... (second form)'),
        (0x762C69, 'mov r8d, dword ptr [rcx + rax*8 + 0x14]', 'the stage\'s status (+20) ...'),
        (0x762C77, 'mov rcx, qword ptr [rip + 0x2bc39a2]', '... StatusEffectReceiver manager 0x3326620 ...'),
        (0x762C95, 'call 0x699e40', '... applied to the wielder (no ProjectileWeapon dependency)'),
        (0x762CA7, 'mov r14, qword ptr [rip + 0x2bc3a2a]', 'no stage: the projectile only through a ProjectileWeapon instance'),
        (0x762DE2, 'movss xmm0, dword ptr [rsi + 0x74]', 'WeaponHeat +116 (heat per shot) ...'),
        (0x762DE7, 'addss xmm0, dword ptr [rax + r12*4 + 4]', '... added to the instance heat ...'),
        (0x762DEE, 'movss dword ptr [rax + r12*4 + 4], xmm0', '... once per call = once per pulse'),
    ],
    'genericFire 0x741DF0: needs a ProjectileWeapon or ArcWeapon instance, else returns': [
        (0x741EA4, 'mov rax, qword ptr [rip + 0x2be482d]', 'ProjectileWeapon instance probe ...'),
        (0x741EF8, 'jne 0x741f65', '... found: fire'),
        (0x741F06, 'mov rax, qword ptr [rip + 0x2be4d03]', 'else ArcWeapon instance probe ...'),
        (0x741F5F, 'je 0x7421b4', '... neither: return (a converted weapon\'s heat-stage projectile is not fired)'),
    ],
    'beamReload 0x775580 -> 0x83F810: a beam weapon reloads only by WeaponHeat or WeaponMagazine': [
        (0x775F1F, 'mov rax, qword ptr [rip + 0x2bb0afa]', 'reload check: BeamWeapon instance probe ...'),
        (0x775FF5, 'call 0x83f810', '... a beam weapon asks the beam can-reload'),
        (0x83F830, 'mov rax, qword ptr [rip + 0x2ae7511]', 'beam can-reload: WeaponHeat instance ...'),
        (0x83F8F2, 'call 0x7651b0', '... heat can-reload'),
        (0x83F880, 'mov rax, qword ptr [rip + 0x2ae6dc1]', 'else WeaponMagazine instance ...'),
        (0x83F90A, 'call 0x76e940', '... magazine can-reload'),
        (0x83F8D0, 'xor al, al', 'neither (WeaponRounds, WeaponLinkedAmmo): reload refused'),
    ],
    'heatCanFire 0x764EE0: only the overheated flag (no wind-up gate)': [
        (0x764EFA, 'mov r10, qword ptr [rip + 0x2bc1e47]', 'WeaponHeat instance ...'),
        (0x764F83, 'cmp byte ptr [rax + rdx*4 + 8], 0', '... can fire unless overheated'),
    ],
    'beamUpdate 0x83E200: the WeaponCharge gate': [
        (0x83E311, 'call 0x5052c0', 'the WeaponCharge record'),
        (0x83E321, 'mov rax, qword ptr [rip + 0x2ae88f8]', 'WeaponCharge instance probe'),
        (0x83E3B9, 'call 0x744ad0', 'can fire'),
        (0x83E3D8, 'movss xmm0, dword ptr [rdx + r8*8 + 4]', 'with an instance: the charge level ...'),
        (0x83E3DF, 'comiss xmm0, dword ptr [r14]', '... must reach WeaponCharge +0 (stage 0 threshold)'),
        (0x83E41C, 'mov cl, 1', 'no WeaponCharge instance: charged'),
        (0x83E420, 'je 0x83e49e', 'cannot fire: no pulse'),
        (0x83E424, 'je 0x83e49e', 'not charged: no pulse'),
    ],
    'chargeUpdate 0x73C8F0: release fire needs ProjectileWeapon / ArcWeapon; the overcharge does not': [
        (0x73CC42, 'cmp byte ptr [r13 + 0xb8], 0', 'WeaponCharge +184 (fire on release) ...'),
        (0x73CC62, 'call 0x73d8c0', '... the charged shot 0x73D8C0 ...'),
        (0x73DB84, 'call 0x741a00', '... -> 0x741A00 ...'),
        (0x741C8B, 'call 0x741df0', '... -> the generic fire 0x741DF0 (returns without a ProjectileWeapon / ArcWeapon '
         'instance)'),
        (0x73CC74, 'movss xmm0, dword ptr [r13 + 0xd0]', 'WeaponCharge +208: overcharge time ...'),
        (0x73CCB3, 'cmp eax, dword ptr [r13 + 0xcc]', '... at the stage named by +204 ...'),
        (0x73CCC4, 'call 0x73dc60', '... the overcharge 0x73DC60 (no ProjectileWeapon reference)'),
    ],
    'triggerDispatch 0x7406A0: charge start and the heat update run for any weapon': [
        (0x740986, 'bt eax, 0xe', 'flag bit 14 (WeaponCharge) ...'),
        (0x7409A0, 'mov rcx, qword ptr [rip + 0x2be6279]', '... WeaponCharge instance ...'),
        (0x740A88, 'mov byte ptr [rax + rdx*8 + 0xc], 1', '... trigger held and can fire: charging'),
        (0x740BD2, 'mov r15, qword ptr [rip + 0x2be616f]', 'WeaponHeat instance ...'),
        (0x740C75, 'call 0x763780', '... the heat update (wind-up members +148/+152/+156) with no fire-type gate'),
        (0x763959, 'movss xmm2, dword ptr [r13 + 0x94]', 'heat update reads WeaponHeat +148 ...'),
        (0x76396F, 'mulss xmm0, dword ptr [r13 + 0x98]', '... +152 ...'),
        (0x763A53, 'mulss xmm0, dword ptr [r13 + 0x9c]', '... +156 (no shot is fired from 0x763780)'),
    ],
    'magazineTable: the WeaponMagazine lookup (relocation assessment)': [
        (0x4F32FF, 'mov r10, qword ptr [rax + 0xf124a0]', 'slot 5 read per call'),
        (0x4F3317, 'imul eax, edx, 0x21c', 'home = resource mod 540: capacity in code'),
    ],
}
SLOT5_DISP = 0xF124A0


def hx(v: int) -> str:
    return '0x%X' % v


def le(v: int) -> str:
    return struct.pack('<Q', v).hex()


def prove(img) -> dict:
    out = {}
    for group, rows in PINS.items():
        out[group] = []
        for rva, asm, role in rows:
            pin = img.pin(rva, role, asm)
            target = pin.get('ripTarget')
            if target is not None and target in MANAGERS:
                pin['manager'] = MANAGERS[target]
            out[group].append(pin)
    return out


def code_facts(img) -> dict:
    """Facts derived from the code by scans (not single instructions)."""
    facts = {}
    beam_update = img.function_insns(0x83E200)
    rips = {img.rip_target(i) for i in beam_update}
    facts['beamUpdateReadsWeaponHeat'] = 0x3326D48 in rips
    facts['beamUpdateReadsWeaponCharge'] = 0x3326C20 in rips
    if facts['beamUpdateReadsWeaponHeat'] or not facts['beamUpdateReadsWeaponCharge']:
        raise ValueError('the beam update changed its heat / charge references')
    heat_update = img.function_insns(0x763780)
    fired = sorted({i.operands[0].imm for i in heat_update if i.mnemonic == 'call' and i.operands
                    and i.operands[0].type == x86.X86_OP_IMM and i.operands[0].imm in (0x741DF0, 0x6128B0, 0x7627B0,
                                                                                       0x83F9D0)})
    facts['heatUpdateFiresAShot'] = bool(fired)
    if fired:
        raise ValueError('the heat update fires a shot')

    def proj_refs(start, depth):
        seen, hits = set(), []

        def walk(f, d):
            if f in seen or d < 0:
                return
            seen.add(f)
            try:
                ins = img.function_insns(f)
            except Exception:  # noqa: BLE001
                return
            for i in ins:
                if img.rip_target(i) == 0x33266D8:
                    hits.append(hx(i.address))
                if i.mnemonic in ('call', 'jmp') and i.operands and i.operands[0].type == x86.X86_OP_IMM:
                    target = i.operands[0].imm
                    if target == 0x515100:
                        hits.append(hx(i.address))
                    chunk = img.chunk(target)
                    if chunk is None or chunk[0] == target or img.root(target) != (img.root(f) or f):
                        walk(target, d - 1)
        walk(start, depth)
        return {'functions': len(seen), 'projectileWeaponReferences': sorted(set(hits))}

    # The component lifecycle handlers (component world tables, read from the default snapshot by
    # research_component_membership) and the ammunition paths: which reach ProjectileWeapon?
    handlers = {'WeaponRounds': (0x528E50, 0x528F20, 0x528F50, 0x528F10),
                'WeaponLinkedAmmo': (0x542340, 0x542440, 0x542430),
                'WeaponCharge': (0x538F30, 0x538FD0, 0x539090, 0x538FC0),
                'WeaponHeat': (0x5460E0, 0x5461D0, 0x546200, 0x546210, 0x5461C0),
                'WeaponMagazine': (0x516990, 0x516A50, 0x516A80, 0x516A40)}
    lifecycle = {}
    for comp, fns in handlers.items():
        lifecycle[comp] = {hx(f): proj_refs(f, 4) for f in fns}
    paths = {'roundAvailable 0x744C20': proj_refs(0x744C20, 3), 'linkedCanFire 0x7725B0': proj_refs(0x7725B0, 3),
             'linkedSpend 0x772470': proj_refs(0x772470, 3), 'beamCanReload 0x83F810': proj_refs(0x83F810, 3),
             'roundsWrite 0x77A6F0': proj_refs(0x77A6F0, 2)}
    facts['projectileWeaponReach'] = {'lifecycle': lifecycle, 'paths': paths,
                                      'method': 'call/tail-jump tree from each function (depth 2-4); a hit is a rip '
                                                'reference to the ProjectileWeapon manager 0x33266D8 or a call of '
                                                'its resolver 0x515100. Validated by the method finding the known '
                                                'magazine chamber dependency (post-create 0x516A80 -> 0x76D8A0).'}
    if not lifecycle['WeaponMagazine'][hx(0x516A80)]['projectileWeaponReferences']:
        raise ValueError('the scan no longer finds the known magazine chamber dependency')
    for comp in ('WeaponRounds', 'WeaponLinkedAmmo', 'WeaponCharge', 'WeaponHeat'):
        for f, r in lifecycle[comp].items():
            if r['projectileWeaponReferences']:
                raise ValueError(comp + ' lifecycle reaches ProjectileWeapon at ' + f)
    for name, r in paths.items():
        if r['projectileWeaponReferences']:
            raise ValueError(name + ' reaches ProjectileWeapon')
    # Slot 5 (WeaponMagazine table) readers: raw scan of .text for the displacement.
    lo, hi = base.TEXT
    hits, at = [], lo
    while True:
        at = img.data.find(SLOT5_DISP.to_bytes(4, 'little'), at, hi)
        if at < 0:
            break
        hits.append(at)
        at += 1
    decoded = []
    for h in hits:
        f = img.root(h)
        chunk = img.chunk(h)
        if chunk:
            cover = next((i for i in img.disasm(chunk[0], chunk[1]) if i.address <= h < i.address + i.size), None)
        else:   # a leaf without unwind data: the covering instruction most linear sweeps from before h agree on
            votes = collections.Counter()
            for start in range(h - 64, h - 8):
                for i in img.md.disasm(img.data[start:h + 8], start):
                    if i.address <= h < i.address + i.size:
                        votes[i.address] += 1
                        break
            cover = img.insn(votes.most_common(1)[0][0]) if votes else None
        if cover is None or '0xf124a0' not in cover.op_str:
            raise ValueError('an undecoded slot-5 displacement at 0x%X' % h)
        decoded.append({'rva': hx(cover.address), 'asm': cover.mnemonic + ' ' + cover.op_str,
                        'function': hx(f) if f else 'leaf without unwind data'})
    facts['magazineSlotReaders'] = decoded
    return facts


def pinned_files():
    deltas_file = (rma.DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    if hashlib.sha256(deltas_file).hexdigest().upper() != rma.DELTAS_SHA:
        raise ValueError('the entity delta file is not the pinned one')
    deltas, _ = rma.entity_deltas(deltas_file)
    custom = rma.customization_items((rma.DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes())
    return deltas, custom


def catalogue():
    """(name, kind, loadout root, candidate roots, source) for every player and support weapon."""
    players = json.loads(PLAYER_CATALOG.read_text(encoding='utf-8'))['weapons']
    supports = json.loads(SUPPORT_CATALOG.read_text(encoding='utf-8'))['weapons']
    hosts = json.loads(VARIANTS.read_text(encoding='utf-8'))['hosts']
    roots = {c['weapon']: c for c in json.loads(ROOTS.read_text(encoding='utf-8'))['corrections']}
    out = []
    for w in players:
        if len(w['resources']) != 1 or w['resolution'] != 'UNIQUE':
            raise ValueError(w['name'] + ': a player weapon without one proven root')
        r = int(w['resources'][0], 16)
        out.append({'name': w['name'], 'kind': w['slot'], 'root': r, 'candidates': [r],
                    'rootSource': 'player catalogue (UNIQUE)' + (' + weapon-roots correction' if w['name'] in roots
                                                                 else ''),
                    'droppedRoots': roots.get(w['name'], {}).get('droppedRoots', []),
                    'droppedIs': roots.get(w['name'], {}).get('droppedIs')})
    for w in supports:
        cands = [int(x, 16) for x in w['resources']]
        host = hosts.get(w['name'])
        if w['resolution'] == 'UNIQUE':
            r, src = cands[0], 'support catalogue (UNIQUE)'
        elif host and host.get('entity'):
            r, src = int(host['entity'], 16), 'weapon-variants host (the loadout root of a DUPLICATE)'
        else:
            r, src = None, 'unresolved DUPLICATE'
        out.append({'name': w['name'], 'kind': 'support', 'root': r, 'candidates': cands, 'rootSource': src,
                    'droppedRoots': [], 'droppedIs': None})
    return out


def main():
    snap_img = xref.CodeImage.from_snapshot('game.dll')
    if snap_img.sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('the snapshot game.dll is not the pinned profile')
    pins = prove(snap_img)
    flat = [p for rows in pins.values() for p in rows]
    mismatch = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(mismatch.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % mismatch)
    facts = code_facts(snap_img)

    t = tables.pinned()
    names = cm.names_of(t)
    rows = t.entity_rows()
    n = lambda i: names.get(i, 'tableless %d' % i)  # noqa: E731
    B = t.component('BeamWeaponComponentData')
    P = t.component('ProjectileWeaponComponentData')
    M = t.component('WeaponMagazineComponentData')
    H = t.component('WeaponHeatComponentData')
    C = t.component('WeaponChargeComponentData')
    R = t.component('WeaponRoundsComponentData')
    L = t.component('WeaponLinkedAmmoComponentData')
    W = t.component('WeaponDataComponentData')
    CU = t.component('WeaponCustomizationComponentData')
    LE = t.component('LoadoutEntryComponentData')
    if (B.capacity, B.count, B.records_offset, B.record_size) != (BEAM_CAPACITY, BEAM_FILE_RECORDS, BEAM_RECORD_BASE,
                                                                  BEAM_RECORD_STRIDE):
        raise ValueError('the BeamWeapon table shape changed')
    if (M.capacity, M.records_offset, M.record_size) != (MAG_CAPACITY, MAG_RECORD_BASE, MAG_RECORD_STRIDE):
        raise ValueError('the WeaponMagazine table shape changed')
    if B.record_of(TRIDENT) != TRIDENT_RECORD:
        raise ValueError('the Trident record moved')
    trident_record = B.raw(TRIDENT_RECORD)
    if struct.unpack_from('<I', trident_record, 0x64)[0] != 6:
        raise ValueError('the Trident record is not pulse mode 6')
    beam_occ = {row: (key, rec) for row, key, rec in B.rows()}
    empty_rows = [row for row in range(BEAM_CAPACITY) if row not in beam_occ]
    esh = cm.esh_body(t)
    list_offsets = sorted(cm.esh_row(esh, q)[1] for q in range(cm.ESH_CAPACITY) if cm.esh_row(esh, q)[0])

    # vanilla census: no component table shares a record between rows (re-checked for the tables used here)
    shared = {}
    for label, comp in (('BeamWeapon', B), ('ProjectileWeapon', P), ('WeaponMagazine', M), ('WeaponHeat', H),
                        ('WeaponCharge', C), ('WeaponRounds', R), ('WeaponLinkedAmmo', L), ('WeaponData', W)):
        own = collections.Counter(rec for _, _, rec in comp.rows())
        shared[label] = sum(1 for v in own.values() if v > 1)
    if any(shared.values()):
        raise ValueError('a weapon component table shares a record: %r' % shared)

    deltas, custom = pinned_files()
    by_option = {it['optionId']: it for it in custom}
    unlocks = {int(w['resource'], 16): w for w in json.loads(UNLOCKS.read_text(encoding='utf-8'))['weapons']}
    functions = {w['weapon']: w for w in json.loads(FUNCTIONS.read_text(encoding='utf-8'))['weapons']}
    fire_modes = {w['weapon']: w for w in json.loads(FIRE_MODES.read_text(encoding='utf-8'))['weapons']}
    residency = json.loads(RESIDENCY.read_text(encoding='utf-8'))['catalog']
    underbarrel_hosts = {}
    for u in json.loads(UNDERBARRELS.read_text(encoding='utf-8'))['underbarrels']:
        for h in u['hostsByDefault']:
            underbarrel_hosts.setdefault(int(h['resource'], 16), []).append(
                {'item': u['item'], 'entity': u['underbarrel']['resource'], 'family': u['underbarrel']['family']})
    trident_list = set(rows[TRIDENT])
    melta_list = set(rows[MELTAGUN])

    def mag_info(r):
        rec = M.record_of(r)
        if rec is None:
            return None
        raw = M.raw(rec)
        mrow = [row for row, key, _ in M.rows() if key == r]
        home = r % MAG_CAPACITY
        probe, at = [], home
        while True:
            key = struct.unpack_from('<Q', M.body, 16 * at)[0]
            probe.append(at)
            if key in (r, 0):
                break
            at = (at + 1) % MAG_CAPACITY
        if at != mrow[0]:
            raise ValueError('magazine row off the probe path')
        woff = MAG_RECORD_BASE + MAG_RECORD_STRIDE * rec + CHAMBER
        return {'row': mrow[0], 'home': home, 'probe': probe, 'record': rec,
                'owners': [hx(o) for o in M.owners(rec)],
                'rowBytes': M.body[16 * mrow[0]:16 * mrow[0] + 16].hex(),
                'capacity136': struct.unpack_from('<I', raw, 136)[0],
                'capacityOverride152': struct.unpack_from('<I', raw, 152)[0],
                'chamber156': raw[CHAMBER], 'plus157': raw[157],
                'windowOffset': woff, 'before': raw[CHAMBER:CHAMBER + 4].hex(),
                'after': ('00' + raw[CHAMBER + 1:CHAMBER + 4].hex()) if raw[CHAMBER] else None}

    def heat_info(r):
        rec = H.record_of(r)
        if rec is None:
            return None
        raw = H.raw(rec)
        f = lambda o: round(struct.unpack_from('<f', raw, o)[0], 4)  # noqa: E731
        u = lambda o: struct.unpack_from('<I', raw, o)[0]  # noqa: E731
        stages = []
        for k in range(3):
            o = 24 * k
            stages.append({'threshold': f(o), 'projectileType': u(o + 4), 'status': u(o + 20)})
        return {'record': rec, 'owners': [hx(o) for o in H.owners(rec)],
                'heatPerShot116': f(116), 'heatPerSecond120': f(120), 'capacity96': f(96), 'cooling128': f(128),
                'startingHeatsinks84': u(84), 'spareHeatsinks92': u(92),
                'windup148_152_156': [f(148), f(152), f(156)], 'flags160_161': [raw[160], raw[161]],
                'stages': stages, 'hasStages': any(s['threshold'] for s in stages)}

    def charge_info(r):
        rec = C.record_of(r)
        if rec is None:
            return None
        raw = C.raw(rec)
        stages = [{'threshold': round(struct.unpack_from('<f', raw, 24 * k)[0], 4),
                   'projectileType': struct.unpack_from('<I', raw, 24 * k + 4)[0]} for k in range(3)]
        return {'record': rec, 'owners': [hx(o) for o in C.owners(rec)], 'stages': stages,
                'overcharge204_4': round(struct.unpack_from('<f', raw, 208)[0], 4)}

    def delta_info(r):
        defaults = []
        rec = CU.record_of(r)
        if rec is not None:
            body = CU.raw(rec)
            for at in range(0, 80, 8):
                slot, option = struct.unpack_from('<II', body, at)
                if option in by_option:
                    defaults.append((slot, by_option[option]['debugName'], by_option[option]['addPath']))
        opts = [(o['slots'], o['debugName'], int(o['addPath'], 16)) for o in unlocks.get(r, {}).get('options', [])]
        seen = {}
        for s, nm, p in defaults:
            seen[p] = ('default', s, nm)
        for s, nm, p in opts:
            seen.setdefault(p, ('option', s, nm))
        res = []
        for p, (kind, s, nm) in seen.items():
            if not p:
                continue
            d = deltas.get(p)
            if not d:
                continue
            comps = sorted({n(e['component']) for e in d['entries']})
            touch = [e['bytes'].hex() for e in d['entries'] if e['component'] == MAGAZINE
                     and e['offset'] <= CHAMBER < e['offset'] + e['size']]
            res.append({'kind': kind, 'item': nm, 'delta': hx(p), 'components': comps, 'touch156': touch})
        pick = lambda kind, comp: sorted({x['item'] for x in res if (kind is None or x['kind'] == kind)  # noqa: E731
                                          and comp in x['components']})
        return {'defaults': [nm for _, nm, _ in defaults],
                'defaultDeltasPatchingProjectileWeapon': pick('default', 'ProjectileWeapon'),
                'optionDeltasPatchingProjectileWeapon': pick('option', 'ProjectileWeapon'),
                'deltasPatchingBeamWeapon': pick(None, 'BeamWeapon'),
                'deltasPatchingWeaponMagazine': pick(None, 'WeaponMagazine'),
                'deltasTouchingMagazine156': [{'item': x['item'], 'kind': x['kind'], 'bytes': x['touch156']}
                                              for x in res if x['touch156']]}

    def membership(r):
        at, probe = r & 0xFFF, []
        while True:
            key = cm.esh_row(esh, at)[0]
            probe.append(at)
            if key in (r, 0):
                break
            at = (at + 1) % cm.ESH_CAPACITY
        res, off, cnt, net = cm.esh_row(esh, at)
        before = list(struct.unpack_from('<%dH' % cnt, esh, off))
        if res != r or before != rows[r]:
            raise ValueError('EntitySettings row mismatch for ' + hx(r))
        after = sorted([i for i in before if i != PROJECTILE] + [BEAM])
        changed = [j for j, (a, b) in enumerate(zip(before, after)) if a != b]
        first, end = off + 2 * changed[0], off + 2 * changed[-1] + 2
        wstart, wend = first - first % 4, end + (-end) % 4
        nxt = min(o for o in list_offsets if o > off)
        after_bytes = bytearray(esh[wstart:wend])
        rel = off - wstart
        packed_after = struct.pack('<%dH' % cnt, *after)
        for j in range(len(after_bytes)):
            k = j - rel
            if 0 <= k < 2 * cnt:
                after_bytes[j] = packed_after[k]
        return {'entitySettingsRow': at, 'home': r & 0xFFF, 'probe': probe, 'listOffsetInBody': off, 'count': cnt,
                'networkType': hx(net), 'before': before, 'after': after,
                'beforeHex': struct.pack('<%dH' % cnt, *before).hex(), 'afterHex': packed_after.hex(),
                'sortedAfter': after == sorted(after), 'uniqueAfter': len(set(after)) == len(after),
                'countUnchanged': len(after) == cnt, 'changedEntries': changed,
                'changedByteRange': [2 * changed[0], 2 * changed[-1] + 2],
                'window': {'offsetInBody': wstart, 'offsetFromList': wstart - off, 'size': wend - wstart,
                           'before': esh[wstart:wend].hex(), 'after': bytes(after_bytes).hex(),
                           'includesNextList': wend > off + 2 * cnt},
                'nextListStartsAt': nxt, 'gapAfterList': nxt - (off + 2 * cnt)}

    def beam_row(r):
        home = r % BEAM_CAPACITY
        p, path = home, []
        while p in beam_occ:
            path.append({'row': p, 'key': hx(beam_occ[p][0])})
            p = (p + 1) % BEAM_CAPACITY
        return {'home': home, 'occupiedOnPath': path, 'firstEmptyOnPath': p, 'rowOffset': BEAM_ROW * p,
                'rowBefore': B.body[BEAM_ROW * p:BEAM_ROW * p + BEAM_ROW].hex(),
                'rowAfterTemplate': le(r) + '{record:u32le}' + '00000000',
                'rowAfterSharedRecord23': le(r) + '17000000' + '00000000'}

    def package(name, kind):
        key = ('support_weapon/' if kind == 'support' else 'player_weapon/') + name
        c = residency.get(key)
        if not c or not c.get('dependency'):
            return {'key': key, 'package': None, 'known': bool(c and c.get('known'))}
        return {'key': key, 'package': c['dependency']['package'], 'name': c['dependency']['name'],
                'via': c['dependency']['via']}

    weapons, out_of_scope = [], []
    for w in catalogue():
        name, kind, r = w['name'], w['kind'], w['root']
        cands = []
        for c in w['candidates']:
            lst = rows.get(c)
            le_rec = LE.record_of(c)
            cands.append({'resource': hx(c), 'path': t.name(c), 'hasProjectileWeapon': bool(lst and PROJECTILE in lst),
                          'hasBeamWeapon': bool(lst and BEAM in lst), 'hasLoadoutEntry': le_rec is not None,
                          'isLoadoutRoot': c == r})
        entry = {'name': name, 'kind': kind, 'resource': hx(r) if r else None, 'path': t.name(r) if r else None,
                 'rootSource': w['rootSource'], 'roots': cands, 'droppedRoots': w['droppedRoots'],
                 'droppedIs': w['droppedIs']}
        lst = rows.get(r) if r else None
        if not lst or PROJECTILE not in lst:
            fam = [k for k, i in (('BeamWeapon', BEAM), ('ArcWeapon', ARC), ('SprayWeapon', SPRAY)) if lst and i in lst]
            entry['verdict'] = 'out_of_scope'
            entry['reasonCode'] = ('ALREADY_BEAM' if 'BeamWeapon' in fam else 'NO_PROJECTILE_WEAPON')
            entry['reason'] = ('already a BeamWeapon weapon' if 'BeamWeapon' in fam else
                               'the loadout root lists no ProjectileWeapon (%s)' % (', '.join(fam) or 'melee / tool / '
                                                                                    'carrier'))
            entry['otherRootsWithProjectileWeapon'] = [c['resource'] for c in cands if c['hasProjectileWeapon']]
            out_of_scope.append(entry)
            continue
        comps = set(lst)
        mem = membership(r)
        beam = beam_row(r)
        mag = mag_info(r)
        heat = heat_info(r)
        charge = charge_info(r) if CHARGE in comps else None
        dl = delta_info(r)
        prow = [(row, rec) for row, key, rec in P.rows() if key == r]
        wd = W.raw(W.record_of(r))
        fm = fire_modes.get(name, {})
        fn = functions.get(name, {})
        le_rec = LE.record_of(r)
        le_same = []
        if le_rec is not None:
            ident = LE.raw(le_rec)[:8]
            le_same = [hx(o) for _, o, rr in LE.rows() if o != r and LE.raw(rr)[:8] == ident]
        entry.update({
            'componentsBefore': [n(i) for i in lst],
            'ammunition': {'WeaponMagazine': MAGAZINE in comps, 'WeaponHeat': HEAT in comps,
                           'WeaponRounds': ROUNDS in comps, 'WeaponLinkedAmmo': LINKED in comps,
                           'WeaponCharge': CHARGE in comps, 'WeaponReload': RELOAD in comps,
                           'WeaponAssistedReload': ASSISTED in comps, 'Backblast': BACKBLAST in comps},
            'membership': mem, 'beam': beam,
            'projectileRowKept': {'row': prow[0][0], 'record': prow[0][1], 'owners': [hx(o) for o in
                                                                                       P.owners(prow[0][1])]},
            'magazine': mag, 'heat': heat, 'charge': charge,
            'rounds': ({'record': R.record_of(r), 'owners': [hx(o) for o in R.owners(R.record_of(r))],
                        'chamberState68': R.raw(R.record_of(r))[0x68]} if ROUNDS in comps else None),
            'linkedAmmo': ({'record': L.record_of(r), 'owners': [hx(o) for o in L.owners(L.record_of(r))]}
                           if LINKED in comps else None),
            'customization': dl,
            'fireModes': {'vector144': list(struct.unpack_from('<IIII', wd, 144)),
                          'burstRounds140': struct.unpack_from('<I', wd, 140)[0],
                          'modes': fm.get('modes'), 'selectorBound': fm.get('selectorBound'),
                          'specialFireControl160': fm.get('specialStruct')},
            'functions': {'rofSelectorBound': (fn.get('fireRate') or {}).get('selectorBound'),
                          'rofSlots': (fn.get('fireRate') or {}).get('slots'),
                          'functionAmmoProjectile': (fn.get('functionAmmo') or {}).get('projectile'),
                          'functionAmmoSelectorBound': (fn.get('functionAmmo') or {}).get('selectorBound'),
                          'functionAmmoState': (fn.get('functionAmmo') or {}).get('state')},
            'underbarrel': underbarrel_hosts.get(r),
            'loadoutEntrySharedWith': le_same,
            'package': package(name, kind),
            'afterNotInTrident': [n(i) for i in sorted(set(mem['after']) - trident_list)],
            'afterNotInMeltagun': [n(i) for i in sorted(set(mem['after']) - melta_list)],
            'liveProvenSolo': r in LIVE_PROVEN,
        })
        def root_ws(c, role):
            clst = set(rows[c])
            cprow = [(row, rec) for row, key, rec in P.rows() if key == c]
            cheat = heat_info(c)
            path = t.name(c) or None
            return {'resource': hx(c), 'role': role, 'path': path,
                    'hasLoadoutEntry': LE.record_of(c) is not None,
                    'sharesLoadoutEntryId': hx(c) in le_same,
                    'ammunition': {k: i in clst for k, i in (('WeaponMagazine', MAGAZINE), ('WeaponHeat', HEAT),
                                                             ('WeaponRounds', ROUNDS), ('WeaponLinkedAmmo', LINKED),
                                                             ('WeaponCharge', CHARGE), ('WeaponReload', RELOAD))},
                    'membership': membership(c), 'beam': beam_row(c),
                    'projectileRowKept': ({'row': cprow[0][0], 'record': cprow[0][1],
                                           'owners': [hx(o) for o in P.owners(cprow[0][1])]} if cprow else None),
                    'magazine': mag_info(c),
                    'heat': ({'record': cheat['record'], 'owners': cheat['owners'],
                              'heatPerShot116': cheat['heatPerShot116']} if cheat else None)}

        roots_to_swap, excluded = [root_ws(r, 'loadout root')], []
        for c in w['candidates']:
            if c == r:
                continue
            path = t.name(c) or ''
            if PROJECTILE not in rows.get(c, []):
                excluded.append({'resource': hx(c), 'path': path or None,
                                 'why': 'no ProjectileWeapon in its list (nothing to convert)'})
            elif '/vehicles/' in path:
                excluded.append({'resource': hx(c), 'path': path,
                                 'why': 'a vehicle armament (out of scope: no wielder trigger path proven; a '
                                        'Helldiver does not wield it)'})
            else:
                roots_to_swap.append(root_ws(c, 'catalogue candidate root (unnamed%s)' % (
                    ', shares the LoadoutEntry id' if hx(c) in le_same else
                    ', has a LoadoutEntry' if LE.record_of(c) is not None else ', no LoadoutEntry')))
        for d in w['droppedRoots']:
            excluded.append({'resource': d, 'path': t.name(int(d, 16)),
                             'why': 'dropped by research/weapon-roots: ' + str(w['droppedIs'])})
        entry['rootsToSwap'] = roots_to_swap
        entry['rootsExcluded'] = excluded
        others = [{'resource': x['resource'], 'path': x['path'], 'category': x['role']} for x in roots_to_swap[1:]]
        entry['otherRoots'] = others
        verdict, code, reason, caveats, confidence = classify(entry, comps)
        entry.update({'verdict': verdict, 'reasonCode': code, 'reason': reason, 'caveats': caveats,
                      'confidence': confidence})
        weapons.append(entry)

    # The three live-proven conversions must equal research/multi-beam-swap byte for byte.
    multi = json.loads(MULTI.read_text(encoding='utf-8'))
    by_res = {w['resource']: w for w in weapons}
    for key, mw in multi['weapons'].items():
        c = by_res[mw['resource']]
        mm, cmm = mw['membership'], c['membership']
        same = (mm['entitySettingsRow'] == cmm['entitySettingsRow'] and mm['listOffsetInBody'] == cmm['listOffsetInBody']
                and mm['beforeHex'] == cmm['beforeHex'] and mm['afterHex'] == cmm['afterHex']
                and mw['beam']['row'] == c['beam']['firstEmptyOnPath']
                and mw['projectileRowKept']['row'] == c['projectileRowKept']['row']
                and ((mw['magazine'] or {}).get('windowOffset') == (c['magazine'] or {}).get('windowOffset')
                     if mw['magazine'] else not (c['magazine'] and c['magazine']['chamber156'])))
        if not same:
            raise ValueError(key + ': differs from the live-proven multi-beam write set')
    # BeamWeapon rows: collisions and capacity
    convertible = [w for w in weapons if w['verdict'] in ('supported', 'supported_with_caveats')]
    items = []
    for w in convertible:
        items.append((w['name'], w, w))
        for x in w['rootsToSwap'][1:]:
            items.append((w['name'] + ' root ' + x['resource'], x, w))
    by_row = collections.defaultdict(list)
    for label, item, _ in items:
        by_row[item['beam']['firstEmptyOnPath']].append(label)
    for label, item, _ in items:
        item['beam']['sharesFirstEmptyRowWith'] = [x for x in by_row[item['beam']['firstEmptyOnPath']] if x != label]
    # every first-empty row is empty in vanilla, and every row on a path before it is occupied: a path never
    # crosses another weapon's vanilla first-empty row.
    for label, item, _ in items:
        for p in item['beam']['occupiedOnPath']:
            if p['row'] in by_row:
                raise ValueError('a probe path crosses an insert row')
    snaps = snapshot_checks(items, t)
    for w in convertible:
        w['rootsToSwap'][0] = {k: v for k, v in w['rootsToSwap'][0].items()}
        w['rootsToSwap'][0]['membership'] = w['membership']
        w['rootsToSwap'][0]['beam'] = w['beam']
    for w in convertible:
        wh = w['membership']['window']
        w['writeSet'] = {
            'resource': w['resource'], 'entitySettingsRow': w['membership']['entitySettingsRow'],
            'listOffsetInBody': w['membership']['listOffsetInBody'],
            'listWindow': {'offsetInBody': wh['offsetInBody'], 'offsetFromList': wh['offsetFromList'],
                           'size': wh['size'], 'before': wh['before'], 'after': wh['after']},
            'beamRow': {'home': w['beam']['home'], 'vanillaInsertRow': w['beam']['firstEmptyOnPath'],
                        'rowOffset': w['beam']['rowOffset'], 'before': w['beam']['rowBefore'],
                        'resourceLe': le(int(w['resource'], 16)), 'recordIndex': 'placeholder (24 + n)',
                        'rowAfterTemplate': w['beam']['rowAfterTemplate']},
            'magazine': (None if not w['magazine'] or not w['magazine']['chamber156'] else
                         {'record': w['magazine']['record'], 'row': w['magazine']['row'],
                          'rowBytes': w['magazine']['rowBytes'], 'windowOffset': w['magazine']['windowOffset'],
                          'before': w['magazine']['before'], 'after': w['magazine']['after']}),
            'heatRecord': w['heat']['record'] if w['heat'] else None,
            'projectileRowKept': w['projectileRowKept']['row'],
            'package': w['package'], 'donorPackage': 'packages/generated/loadout/laser_shotgun',
            'restartAfterUse': any(c['code'] in ('RESTART_AFTER_USE', 'OPTION_LEAKS_PROJECTILE_COPY')
                                   for c in w['caveats'])}

    distinct_rows = sorted(by_row)
    counts = collections.Counter(w['verdict'] for w in weapons)
    las = [w for w in weapons if w['name'].startswith('LAS-') or w['name'].startswith('PLAS-')
           or 'Hot-Shot' in w['name'] or 'Bolt Pistol' in w['name'] or w['name'] == '40-K Meltagun']
    report = {
        'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'gameDllSha256': base.PROFILE_DLL_SHA,
        'writes': 0, 'protectionChanges': 0,
        'question': __doc__.split('\n\n')[0].strip(),
        'follows': ['multi-beam-swap-F5FEE03DCFDB.md', 'component-swap-liberator-beam-chamber.md',
                    'beam-table-relocation-F5FEE03DCFDB.md', 'beam-pulse-rate-F5FEE03DCFDB.md'],
        'sources': ['pinned entity file (scan.tables.pinned)', 'pinned entity delta and weapon customization files',
                    'schemas/player_weapon_authoring_catalog.json', 'schemas/support_weapon_authoring_catalog.json',
                    'research weapon-variants, weapon-roots, underbarrel-weapons, weapon-functions, '
                    'weapon-fire-modes, attachment-unlock-lists, package-residency',
                    'game.dll image of a retained snapshot (capstone)', 'nine retained snapshots'],
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': mismatch, 'codeFacts': facts,
        'donor': {'name': 'LAS-13 Trident', 'resource': hx(TRIDENT), 'beamRow': TRIDENT_ROW,
                  'record': TRIDENT_RECORD, 'recordOffset': BEAM_RECORD_BASE + BEAM_RECORD_STRIDE * TRIDENT_RECORD,
                  'mode100': struct.unpack_from('<I', trident_record, 0x64)[0], 'bytes': trident_record.hex(),
                  'package': 'packages/generated/loadout/laser_shotgun'},
        'beamTable': {'capacity': BEAM_CAPACITY, 'occupiedRows': len(beam_occ), 'emptyRows': empty_rows,
                      'rowsHex': B.body[:BEAM_RECORD_BASE].hex(),
                      'record23Hex': B.raw(BEAM_FILE_RECORDS - 1).hex(),
                      'record23Owners': [hx(o) for o in B.owners(BEAM_FILE_RECORDS - 1)],
                      'rowsIdenticalInEverySnapshot': all(v['beamRowsByteIdenticalToFile'] for v in snaps.values()),
                      'fileRecords': BEAM_FILE_RECORDS, 'ownedCopyFixedBytes': COPY_FIXED,
                      'ownedCopyBytesFor': {str(k): COPY_FIXED + BEAM_RECORD_STRIDE * k for k in (1, 3, 4, 17)},
                      'note': 'The owned copy keeps 46 rows (capacity is code: imul 0x2E). Each conversion needs one '
                              'empty row and one appended record (24 + n). The copy fits one 4 KiB page for at most 3 '
                              'conversions (3680 + 120 n bytes); more need a second page.'},
        'magazineTable': {'capacity': MAG_CAPACITY, 'recordBase': MAG_RECORD_BASE, 'recordStride': MAG_RECORD_STRIDE,
                          'recordsSharedByTwoOrMoreRows': shared['WeaponMagazine'],
                          'relocationNeeded': False,
                          'slotReaders': facts['magazineSlotReaders'],
                          'note': 'No WeaponMagazine record is shared (vanilla census), so every chamber byte write '
                                  'touches only its own weapon; no relocation or repointing is needed. For reference, '
                                  'the table is read through slot 5 (manager + 0xF124A0) with the capacity 540 in code '
                                  '(imul 0x21C), the same shape as BeamWeapon slot 270.'},
        'sharedRecordCensus': shared,
        'weapons': weapons,
        'outOfScope': out_of_scope,
        'mountedSentryVehicle': mounted_census(t, rows, {int(w['resource'], 16) for w in weapons if w['resource']}),
        'snapshots': snaps,
        'summary': {
            'weaponsCatalogued': len(weapons) + len(out_of_scope),
            'withProjectileWeapon': len(weapons),
            'verdicts': dict(sorted(counts.items())),
            'reasonCodes': dict(sorted(collections.Counter(w['reasonCode'] for w in weapons).items())),
            'outOfScope': dict(sorted(collections.Counter(w['reasonCode'] for w in out_of_scope).items())),
            'convertible': len(convertible),
            'emptyBeamRows': len(empty_rows),
            'distinctVanillaInsertRows': len(distinct_rows),
            'rootsToConvert': len(items),
            'maxSimultaneousIndependent': min(len(distinct_rows), len(empty_rows)),
            'maxSimultaneousOrdered': min(len(items), len(empty_rows)),
            'maxUnit': 'roots (each converted root needs its own BeamWeapon row and record)',
            'maxNote': 'Independent: one weapon per distinct vanilla first-empty row (any subset, any order, as the '
                       'live-proven three). Ordered: the owned copy is rebuilt as a whole for the chosen set, so all '
                       '%d empty rows can be filled (a full table is safe: the lookup stops after 46 probes, '
                       '0x50E8EB); a weapon whose first-empty row is taken then probes on to the next empty row, and '
                       'its row must be removed before the row it probes past. The vanilla table has %d empty rows '
                       '(%d occupied = 2 x rows, load factor 0.5), not 17 as multi-beam-swap section 6 states.'
                       % (len(empty_rows), len(empty_rows), len(beam_occ)),
            'lasAndEnergy': {w['name']: [w['verdict'], w['reasonCode']] for w in las},
        },
    }
    text = json.dumps(report, indent=1) + '\n'
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    print(json.dumps({'bytes': len(text), 'pins': len(flat), 'summary': report['summary']}, indent=1))
    for w in weapons:
        print('%-34s %-9s %-24s %-34s %s' % (w['name'], w['kind'], w['verdict'], w['reasonCode'],
                                             ','.join(c['code'] for c in w['caveats'])))


def cav(code, text):
    return {'code': code, 'text': text}


def classify(e, comps):
    """(verdict, reasonCode, reason, caveats, confidence)."""
    caveats = []
    mem, beam = e['membership'], e['beam']
    if not (mem['sortedAfter'] and mem['uniqueAfter'] and mem['countUnchanged']):
        return 'refused', 'LIST_SWAP_INVALID', 'the swapped list is not sorted, unique and of the same count', [], \
            'CONFIRMED'
    if BEAM in comps:
        return 'refused', 'ALREADY_BEAM', 'BeamWeapon already in the list', [], 'CONFIRMED'
    if e['projectileRowKept']['owners'] != [e['resource']]:
        return 'refused', 'PROJECTILE_RECORD_SHARED', 'the ProjectileWeapon record is not its own', [], 'CONFIRMED'
    if e['customization']['deltasPatchingBeamWeapon']:
        return 'refused', 'BEAM_DELTA_CONFLICT', 'a customization delta patches BeamWeapon: ' + \
            ', '.join(e['customization']['deltasPatchingBeamWeapon']), [], 'CONFIRMED'
    if CHARGE in comps:
        st = e['charge']['stages']
        return ('refused', 'CHARGE_WEAPON',
                'WeaponCharge: on the beam path the pulse waits only for the charge level to reach stage 0 (+0 = %s s, '
                'beam update 0x83E3DF) and then pulses while held; the weapon\'s own model (charge stages %s with '
                'their projectile types %s, fire on release, overcharge +208 = %s) is the projectile path, and the '
                'only vanilla beam+charge weapon (40-K Meltagun) uses beam mode 5, not 6. Not proven to break; not '
                'proven to work.' % (st[0]['threshold'], [s['threshold'] for s in st],
                                      [s['projectileType'] for s in st], e['charge']['overcharge204_4']),
                [], 'STRONG')
    if ROUNDS in comps:
        return ('refused', 'ROUNDS_NO_BEAM_RELOAD',
                'WeaponRounds: pulses spend rounds (0x7449EA) and can fire (0x744E75) without ProjectileWeapon, but a '
                'beam weapon reloads only through 0x83F810, which accepts WeaponHeat or WeaponMagazine and refuses '
                'everything else (0x83F8D0): the weapon empties and can never reload', [], 'CONFIRMED')
    if LINKED in comps:
        return ('refused', 'LINKED_AMMO_NO_BEAM_RELOAD',
                'WeaponLinkedAmmo (backpack-fed): can-fire and spend are ProjectileWeapon-free (0x7725B0, 0x772470), '
                'but the beam reload check 0x83F810 refuses a weapon with neither WeaponHeat nor WeaponMagazine '
                '(0x83F8D0)%s' % ('; it lists WeaponReload, so its vanilla reload is lost' if RELOAD in comps else ''),
                [], 'CONFIRMED' if RELOAD in comps else 'STRONG')
    for x in e['rootsToSwap'][1:]:
        am = x['ammunition']
        why = None
        if not x['projectileRowKept'] or x['projectileRowKept']['owners'] != [x['resource']]:
            why = 'its ProjectileWeapon record is not its own'
        elif BEAM in x['membership']['before'] or not (x['membership']['sortedAfter']
                                                       and x['membership']['uniqueAfter']):
            why = 'its list swap is invalid'
        elif am['WeaponCharge'] or am['WeaponRounds'] or am['WeaponLinkedAmmo']:
            why = 'its ammunition model is refused (charge / rounds / linked)'
        elif not am['WeaponMagazine'] and not am['WeaponHeat']:
            why = 'it has neither WeaponMagazine nor WeaponHeat'
        elif x['magazine'] and x['magazine']['owners'] != [x['resource']]:
            why = 'its WeaponMagazine record is shared'
        elif x['heat'] and x['heat']['owners'] != [x['resource']]:
            why = 'its WeaponHeat record is shared'
        if why:
            return ('refused', 'ROOT_WRITE_SET_UNDERIVABLE', 'root %s must be converted too, but %s'
                    % (x['resource'], why), [], 'CONFIRMED')
    mag, heat = e['magazine'], e['heat']
    if not mag and not heat:
        return 'refused', 'NO_AMMUNITION_MODEL', 'neither WeaponMagazine nor WeaponHeat', [], 'STRONG'
    if mag:
        if mag['owners'] != [e['resource']]:
            return 'refused', 'MAGAZINE_SHARED', 'the WeaponMagazine record is shared', [], 'CONFIRMED'
        bad_default = [d for d in e['customization']['deltasTouchingMagazine156'] if d['kind'] == 'default'
                       and any(b[:2] != '00' for b in d['bytes'])]
        if bad_default:
            return 'refused', 'DEFAULT_DELTA_SETS_CHAMBER', 'a default delta sets the chamber byte', [], 'CONFIRMED'
        bad_option = [d['item'] for d in e['customization']['deltasTouchingMagazine156'] if d['kind'] == 'option'
                      and any(b[:2] != '00' for b in d['bytes'])]
        if bad_option:
            caveats.append(cav('OPTION_SETS_CHAMBER', 'equipping %s sets the chamber byte again (deadlock): test '
                                                      'without it' % ', '.join(bad_option)))
        if mag['capacity136'] <= 1:
            caveats.append(cav('ONE_ROUND_MAGAZINE', 'magazine capacity %d: one pulse per magazine'
                               % mag['capacity136']))
    if heat:
        if heat['owners'] != [e['resource']]:
            return 'refused', 'HEAT_SHARED', 'the WeaponHeat record is shared', [], 'CONFIRMED'
        if heat['hasStages']:
            caveats.append(cav('HEAT_STAGES', 'heat stages %s: the stage projectiles %s are not fired on the beam '
                                              'path (0x741DF0 returns without a ProjectileWeapon instance); the stage '
                                              'statuses %s on the wielder still apply (0x762C95)'
                               % ([s['threshold'] for s in heat['stages']], [s['projectileType'] for s in heat['stages']],
                                  [s['status'] for s in heat['stages']])))
        if heat['heatPerSecond120']:
            caveats.append(cav('HEAT_PER_SECOND', '+120 = %s is applied only by the continuous path; a pulse adds '
                                                  '+116 only' % heat['heatPerSecond120']))
        if heat['flags160_161'][0] or heat['heatPerShot116'] >= heat['capacity96']:
            caveats.append(cav('WINDUP_SKIPPED', 'the beam update fires on can-fire (heat: the overheated flag only, '
                                                 '0x764F83) and the WeaponCharge gate (no WeaponCharge here); it has '
                                                 'no WeaponHeat reference, and the heat update 0x763780 that reads '
                                                 '+148/+152/+156 (%s, +160 = %d) fires nothing. So a pulse fires on '
                                                 'the press with no wind-up, adding +116 = %s heat (capacity %s): one '
                                                 'pulse, then overheat and cooldown'
                               % (heat['windup148_152_156'], heat['flags160_161'][0], heat['heatPerShot116'],
                                  heat['capacity96'])))
        if not heat['startingHeatsinks84'] and not heat['spareHeatsinks92']:
            caveats.append(cav('NO_HEATSINKS', 'no heat sinks: cooldown only (heat can-reload refuses)'))
    cu = e['customization']
    if cu['defaultDeltasPatchingProjectileWeapon']:
        caveats.append(cav('RESTART_AFTER_USE', 'default %s patch ProjectileWeapon: a ProjectileWeapon private copy '
                                                'leaks per spawn' % ', '.join(cu['defaultDeltasPatchingProjectileWeapon'])))
    if cu['optionDeltasPatchingProjectileWeapon']:
        caveats.append(cav('OPTION_LEAKS_PROJECTILE_COPY', 'options patching ProjectileWeapon (%s) leak a private copy '
                                                           'when equipped' % ', '.join(
                                                               cu['optionDeltasPatchingProjectileWeapon'])))
    a = e['ammunition']
    if a['WeaponAssistedReload'] or a['Backblast']:
        caveats.append(cav('ASSISTED_RELOAD_UNTRACED', 'WeaponAssistedReload / Backblast: the team reload and the '
                                                       'backblast are not traced on the beam path'))
    if not a['WeaponReload']:
        caveats.append(cav('NO_RELOAD', 'no WeaponReload: expendable, as in vanilla'))
    fm = e['fireModes']
    vec = fm['vector144']
    if vec[0] != 1:
        caveats.append(cav('TRIGGER_MODE_NOT_AUTOMATIC', 'default fire mode %d (WeaponData +144 = %s; 2 single, 3 burst): '
                                                         'how a non-automatic trigger drives the pulse beam is not '
                                                         'traced (the live Talon, single, pulsed)' % (vec[0], vec)))
    elif any(v in (2, 3) for v in vec[1:]):
        caveats.append(cav('SELECTABLE_NON_AUTO_MODES', 'automatic by default; its selectable single / burst modes '
                                                        '(WeaponData +144 = %s) are untested on the pulse beam' % vec))
    if any(v > 3 for v in vec):
        caveats.append(cav('UNNAMED_FIRE_MODES', 'fire-mode values above 3 (%s; 4 = Safety_Off, others unnamed) are '
                                                 'untested on the pulse beam' % vec))
    if fm['specialFireControl160']:
        caveats.append(cav('SPECIAL_FIRE_CONTROL', 'WeaponData +160 special fire-control structure (semantics '
                                                   'unknown) on the beam path'))
    fn = e['functions']
    if fn['rofSelectorBound']:
        caveats.append(cav('ROF_SELECTOR_INERT', 'its rate-of-fire selector switches ProjectileWeapon +4 slots, which '
                                                 'the beam ignores (the beam rate is BeamWeapon +104)'))
    if fn['functionAmmoProjectile'] or fn['functionAmmoSelectorBound']:
        caveats.append(cav('FUNCTION_AMMO_INERT', 'its weapon-function ammunition (ProjectileWeapon +576 = %s) needs '
                                                  'the projectile path' % fn['functionAmmoProjectile']))
    if e['underbarrel']:
        caveats.append(cav('UNDERBARREL_UNCHANGED', 'underbarrel %s stays a separate %s entity; its interplay with '
                                                    'the beam trigger is untested' % (
                                                        [u['item'] for u in e['underbarrel']],
                                                        [u['family'] for u in e['underbarrel']])))
    others = e['otherRoots']
    if others:
        same_id = [o['resource'] for o in others if o['resource'] in e['loadoutEntrySharedWith']]
        caveats.append(cav('OTHER_ROOTS_UNCONVERTED', 'other catalogue roots keep ProjectileWeapon: %s. %s Which '
                                                      'root a given delivery spawns is not proven here; each has its '
                                                      'own write set (rootsToSwap) and must be converted too for the '
                                                      'weapon to fire beams everywhere'
                           % (', '.join('%s (%s)' % (o['resource'], o['path'] or o['category']) for o in others),
                              ("%s share the loadout root's LoadoutEntry id." % same_id) if same_id else
                              "None shares the loadout root's LoadoutEntry id.")))
    if heat and not mag:
        model = 'heat: +116 = %s heat per pulse from its own WeaponHeat record %d' % (heat['heatPerShot116'],
                                                                                    heat['record'])
    elif mag and mag['chamber156']:
        model = 'magazine with a chamber: record %d +156 1 -> 0 (owned alone), one round per pulse' % mag['record']
    else:
        model = 'magazine without a chamber (+156 = 0, the Meltagun model), one round per pulse'
    proven = e['liveProvenSolo']
    verdict = 'supported_with_caveats' if caveats else 'supported'
    if proven:
        code = 'LIVE_PROVEN'
    elif heat and not mag:
        code = 'HEAT_PULSE'
    elif mag and mag['chamber156']:
        code = 'MAGAZINE_CHAMBER_FIX'
    else:
        code = 'MAGAZINE_NO_CHAMBER'
    confidence = 'CONFIRMED' if proven else 'STRONG'
    return verdict, code, model + ('; live-proven solo 2026-10-10' if proven else ''), caveats, confidence


def mounted_census(t, rows, covered):
    cats = collections.Counter()
    helldiver = []
    for r, lst in rows.items():
        if PROJECTILE not in lst or r in covered:
            continue
        path = t.name(r) or ''
        if '/vehicles/' in path:
            cat = 'helldiver vehicle'
        elif 'fac_helldivers' in path and any(k in path for k in ('sentry', 'turret', 'hellpod', 'emplacement',
                                                                 'stratagem')):
            cat = 'helldiver sentry / emplacement / hellpod'
        elif 'fac_helldivers' in path:
            cat = 'helldiver other (drones, backpacks, underbarrels, loot)'
        elif path:
            cat = 'enemy / world'
        else:
            cat = 'unnamed'
        cats[cat] += 1
        if cat.startswith('helldiver') and len(helldiver) < 80:
            helldiver.append({'resource': hx(r), 'path': path, 'category': cat})
    return {'verdict': 'out_of_scope',
            'reason': 'no wielder trigger path is proven for mounted, sentry or vehicle weapons; the conversion is '
                      'only reviewed for weapons a Helldiver wields',
            'entitiesWithProjectileWeaponByCategory': dict(sorted(cats.items())),
            'helldiverSide': sorted(helldiver, key=lambda x: x['path'])}


def snapshot_checks(items, t) -> dict:
    """Every retained snapshot: each convertible weapon's list, window page, BeamWeapon row and magazine window."""
    B = t.component('BeamWeaponComponentData')
    M = t.component('WeaponMagazineComponentData')
    out, page_offsets = {}, {}
    for name in SNAPSHOTS:
        reader = instances.SnapshotReader(name)
        try:
            game = reader.modules['game.dll']['base']
            root = instances.u64(reader, game + cm.ENTITY_MANAGER)
            beam_slot = instances.u64(reader, root + cm.SLOT_BASE + 8 * BEAM)
            mag_slot = instances.u64(reader, root + cm.SLOT_BASE + 8 * MAGAZINE)
            tb = reader.read(beam_slot, len(B.body))
            mb = reader.read(mag_slot, len(M.body))
            esh = instances.u64(reader, root + cm.ESH_SLOT)
            invalid = struct.unpack('<I', reader.read(game + cm.INVALID_ENTITY, 4))[0]
            raw = reader.read(root + cm.DESCRIPTORS, cm.DESCRIPTOR_STRIDE * cm.DESCRIPTOR_COUNT)
            live = collections.Counter()
            for j in range(cm.DESCRIPTOR_COUNT):
                r_, e_ = struct.unpack_from('<QI', raw, j * cm.DESCRIPTOR_STRIDE)
                if e_ != invalid and r_:
                    live[r_] += 1
            bad, crossing, live_now = [], [], {}
            for label, w, _ in items:
                m = w['membership']
                rowb = reader.read(esh + 32 * m['entitySettingsRow'], 32)
                lp = struct.unpack_from('<Q', rowb, 8)[0]
                cnt = struct.unpack_from('<I', rowb, 16)[0]
                ok = (lp - esh == m['listOffsetInBody'] and cnt == m['count']
                      and reader.read(lp, 2 * cnt).hex() == m['beforeHex']
                      and reader.read(esh + m['window']['offsetInBody'], m['window']['size']).hex()
                      == m['window']['before']
                      and tb[w['beam']['rowOffset']:w['beam']['rowOffset'] + 16] == bytes(16)
                      and hx(reader.snapshot.region(lp)['protect']) == '0x2')
                wstart = esh + m['window']['offsetInBody']
                page_offsets.setdefault(label, set()).add(wstart % 4096)
                if wstart % 4096 + m['window']['size'] > 4096:
                    crossing.append(label)
                mz = w['magazine']
                if mz and mz['chamber156']:
                    ok = ok and mb[mz['windowOffset']:mz['windowOffset'] + 4].hex() == mz['before'] and \
                        mb[16 * mz['row']:16 * mz['row'] + 16].hex() == mz['rowBytes']
                if not ok:
                    bad.append(label)
                c = live.get(int(w['resource'], 16), 0)
                if c:
                    live_now[label] = c
            mag_diff = sorted({(k - MAG_RECORD_BASE) // MAG_RECORD_STRIDE if k >= MAG_RECORD_BASE else -1
                               for k in range(min(len(mb), len(M.body))) if mb[k] != M.body[k]})
            out[name] = {'beamTableByteIdenticalToFile': tb == B.body,
                         'beamRowsByteIdenticalToFile': tb[:BEAM_RECORD_BASE] == B.body[:BEAM_RECORD_BASE], 'magazineTableByteIdenticalToFile': mb == M.body,
                         'magazineRecordsDifferingFromFile': ['index rows' if k < 0 else k for k in mag_diff],
                         'rootsChecked': len(items), 'mismatches': bad, 'windowsCrossingAPage': crossing,
                         'liveInstances': live_now}
        finally:
            reader.close()
        if not out[name]['beamTableByteIdenticalToFile'] or out[name]['mismatches']:
            raise ValueError('snapshot %s: %r' % (name, out[name]))
    for label, w, owner in items:
        offsets = page_offsets[label]
        if len(offsets) != 1:
            raise ValueError(label + ': the list window page offset differs between snapshots')
        po = offsets.pop()
        size = w['membership']['window']['size']
        w['membership']['window']['pageOffset'] = po
        w['membership']['window']['crossesPage'] = po + size > 4096
        if po + size > 4096:
            first = 4096 - po
            w['membership']['window']['splitAtPage'] = [[0, first], [first, size - first]]
            owner['caveats'].append(cav('WINDOW_CROSSES_PAGE', '%s: the 4-aligned list window (%d bytes at page '
                                                               'offset %d) crosses a page in every snapshot: write '
                                                               'it as two aligned windows (%d + %d bytes), one per '
                                                               'page' % (w['resource'], size, po, first, size - first)))
            owner['verdict'] = 'supported_with_caveats'
    return out


if __name__ == '__main__':
    main()
