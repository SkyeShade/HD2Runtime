"""Beam conversion, ADD layout (research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md): a projectile weapon fires
LAS-13 Trident pulses while it KEEPS ProjectileWeapon (321) and gains BeamWeapon (270), instead of the swap layout's
321 -> 270 (research/docs/beam-conversion-coverage-F5FEE03DCFDB.md). The lead is Bans' True Lasgun Beam Overhaul
(research/docs/las-beam-overhaul-comparison.md): its Sickles and Sai keep 321 and add 270 through a relocated
membership list. Nothing of the mod is used; every fact below is HD2Runtime's own, from the pinned entity file, the
game.dll image of a retained snapshot (capstone) and every retained snapshot.

Questions answered (each with pinned instructions):
  1. How a weapon with BOTH instances fires: the trigger dispatchers prefer ProjectileWeapon, but they only set a mode
     byte; the beam update and the projectile update each fire on their own from the shared trigger byte.
  2. Which member suppresses the projectile path: the projectile type the fire path takes (0x7456D0) is the weapon's
     effective ProjectileWeapon +0 for heat weapons and for magazines without a round list (the chamber is filled from
     it too); type 0 ends the shot at 0x614076 -> 0x6156BE, the vanilla empty-magazine exit, before the emission, the
     round spend, the recoil and the sound.
  3. Ammunition and rate: the beam shot spends the round (magazine) or runs the heat step; the heat step also runs
     on every projectile-update shot, so a heat weapon's ProjectileWeapon rate must not exceed its pulse rate (the
     beam update runs first in the world update and pushes the projectile timer by one projectile interval per pulse).
  4. Multiplayer: every machine keeps a ProjectileWeapon instance, so the network apply never takes the -1 path;
     every machine simulates every player's beam from the replicated trigger byte; health damage from a remote
     player's simulated shot is discarded at ApplyDamage (owner authority), but zone health and shields are lowered
     where the target is owned, so every machine must simulate the SAME beam: identical conversions only.
  5. Coverage: which supported weapons the add layout can take, and why the rest keep the swap layout (solo).

Read-only, offline, build F5FEE03DCFDB. Output: research/beam-conversion-add-layout-F5FEE03DCFDB.json.
    py -3 scripts/research_beam_conversion_add.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_beam_conversion_coverage as cov  # noqa: E402
import research_component_membership as cm  # noqa: E402
import research_event_state as base  # noqa: E402
from research_beam_damage import SNAPSHOTS  # noqa: E402
from scan import instances, tables, xref  # noqa: E402

OUTPUT = ROOT / 'research/beam-conversion-add-layout-F5FEE03DCFDB.json'
COVERAGE = ROOT / 'research/beam-conversion-coverage-F5FEE03DCFDB.json'
UNLOCKS = ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json'
PROJECTILE, BEAM, MAGAZINE = 321, 270, 5
TYPE_OFFSET, RATE_OFFSET, INFINITE_OFFSET, HOOK_OFFSET, NETWORKED_OFFSET, FUNCTION_AMMO_OFFSET = 0, 8, 36, 68, 148, 576
HEAT_STAGE_TYPES = (4, 28, 52)      # WeaponHeat HeatLevelSetting[n] +4 (typed ProjectileType)
ZERO_ROW_RVA = 0x37C7560            # ProjectileInfo getter 0x11EC7C0: type 0 -> this static row
ROW_ARRAY_RVA = 0x37C7670
RATE_CONSTANT_RVA = 0x23C7740       # 60.0: interval = 60 / rpm (0x616EA8)

# (rva, exact asm, role). Every one is checked byte for byte in all nine retained snapshots.
PINS = {
    'triggerDispatch: projectile first, but only a mode byte is set (no shot)': [
        (0x7425E1, 'test r8b, 1', 'weapon flags bit 0 (a ProjectileWeapon instance) ...'),
        (0x7425E5, 'je 0x742624', '... clear: the beam branch'),
        (0x742605, 'jmp 0x612800', '... set: the ProjectileWeapon setter only (the beam setter is skipped)'),
        (0x742624, 'test r8b, 2', 'flags bit 1 (a BeamWeapon instance)'),
        (0x742648, 'jmp 0x83f750', 'the BeamWeapon setter'),
        (0x612896, 'mov byte ptr [rdx + rax + 0x13], r14b', 'the ProjectileWeapon setter writes one mode byte (+0x13)'),
        (0x83F7F3, 'mov byte ptr [rdx + rax + 0x18], r14b', 'the BeamWeapon setter writes one mode byte (+0x18)'),
        (0x74270B, 'test cl, 1', 'second dispatcher: projectile first'),
        (0x742728, 'test cl, 2', '... then beam'),
        (0x82B5E8, 'test r8b, 1', 'third dispatcher: projectile first'),
        (0x82B629, 'test r8b, 2', '... then beam'),
    ],
    'flagsBuilder 0x73FCE0: both bits when both instances exist': [
        (0x73FDF9, 'mov dword ptr [rdi + rbx*8], 1', 'bit 0: ProjectileWeapon instance'),
        (0x73FE6A, 'or dword ptr [rdi + rbx*8], 2', 'bit 1: BeamWeapon instance (or-ed, both kept)'),
    ],
    'worldUpdate 0x571200: every beam instance, then every projectile instance': [
        (0x57379F, 'test byte ptr [rcx + 0x14], 2', 'the beam loop skips only entities with descriptor flag bit 1'),
        (0x5737B1, 'call 0x83e200', 'the beam update, per BeamWeapon instance ...'),
        (0x573F81, 'call 0x617550', '... later in the same update: the ProjectileWeapon manager update'),
        (0x617919, 'call 0x616ac0', 'the projectile update, per ProjectileWeapon instance (no skip)'),
    ],
    'beamUpdate 0x83E200: fires from the trigger byte, whatever the dispatch did': [
        (0x83E3B9, 'call 0x744ad0', 'can fire (ammunition / heat)'),
        (0x83E488, 'cmp byte ptr [rcx + rax], r12b', 'the weapon state\'s trigger byte [[0x3326660] + 0x58][index]'),
        (0x83F0D3, 'call 0x83f9d0', 'the beam shot (no authority test on the way)'),
    ],
    'projectileUpdate 0x616AC0: its own timer, the same trigger, the shot': [
        (0x616CE6, 'call 0x744ad0', 'can fire'),
        (0x616E63, 'cmp byte ptr [r12 + 0x94], dil', 'ProjectileWeapon +148 set ...'),
        (0x616E6D, 'test byte ptr [r13 + 0x14], 1', '... and this machine is not the authority ...'),
        (0x616E76, 'cmove r15d, edi', '... then no shot here (networked shots: only the owner fires)'),
        (0x616EA8, 'movss xmm0, dword ptr [rip + 0x1db0890]', '60.0 ...'),
        (0x616EB0, 'divss xmm0, xmm1', '... / the replicated current rpm (when > 0 and changed) ...'),
        (0x616EC0, 'movss dword ptr [r14 + rbp + 0xc], xmm0', '... = the shot interval'),
        (0x616C33, 'subss xmm0, xmm8', 'the shot timer runs down by the frame time'),
        (0x61742C, 'comiss xmm7, dword ptr [r14 + rbp + 8]', 'shots while the timer is <= 0 ...'),
        (0x6174CE, 'call 0x6128b0', '... the projectile fire (no WeaponHeat instance) ...'),
        (0x6174F1, 'call 0x7627b0', '... or the heat step (with one), which fires through 0x6128B0'),
        (0x6174F8, 'mov dword ptr [r14 + rbp + 8], edi', 'not firing: the timer is clamped at 0'),
    ],
    'projectileFire 0x6128B0: type 0 ends the shot before every effect': [
        (0x612CFD, 'movss xmm0, dword ptr [rax + 0xc]', 'interval ...'),
        (0x612D02, 'addss xmm0, dword ptr [rax + 8]', '... added to the timer ...'),
        (0x612D07, 'movss dword ptr [rax + 8], xmm0', '... first, on every call'),
        (0x612EA4, 'cmp byte ptr [r14 + 0x94], 0', 'ProjectileWeapon +148 (networked shots) ...'),
        (0x612F1E, 'call 0xbefeb0', '... the owner sends a shot RPC before the type test (form 1)'),
        (0x612F6E, 'call 0xbf2a10', '... (form 2)'),
        (0x613038, 'cmp byte ptr [r14 + 0x44], 0', 'ProjectileWeapon +68: an engine call before the type test'),
        (0x61405B, 'mov eax, dword ptr [rbp + 0x518]', 'the caller\'s explicit type (0: none) ...'),
        (0x61406C, 'call 0x7456d0', '... else the weapon\'s current projectile type'),
        (0x614074, 'test eax, eax', 'type 0 ...'),
        (0x614076, 'je 0x6156be', '... ends the shot: no emission, no round spent, no recoil, no sound'),
        (0x614450, 'cmp dword ptr [rax + 0x1c], 0', '(the emission loop: ProjectileInfo +28 pellets)'),
        (0x6149D8, 'cmp byte ptr [rax + 0x24], 0', '(the round spend unless ProjectileWeapon +36)'),
        (0x6149EC, 'call 0x744690', '(the round spend)'),
        (0x6156BE, 'cmp byte ptr [rsp + 0x71], 0', 'the shot end, shared with the normal path (falls through) ...'),
        (0x6156CA, 'sub dword ptr [rbp - 0x28], 1', '... the same multi-shot counter as a vanilla shot ...'),
        (0x6156DD, 'jne 0x612fc0', '... loops as a vanilla shot does (the empty-magazine shot)'),
    ],
    'projectileType 0x7456D0: the weapon\'s ProjectileWeapon +0 for heat and plain magazines': [
        (0x74575D, 'bt r8d, 9', 'flags bit 9 (WeaponHeat) ...'),
        (0x745762, 'jae 0x745782', '... clear: the magazine / rounds / linked models'),
        (0x74576C, 'call 0x515100', '... set: the effective ProjectileWeapon record (private copy or record) ...'),
        (0x745771, 'mov ebp, dword ptr [rax]', '... its +0'),
        (0x745805, 'mov ecx, dword ptr [rbx + 8]', 'magazine: the chambered type ...'),
        (0x745808, 'test ecx, ecx', '... when set'),
        (0x745813, 'mov edi, dword ptr [rbx]', 'rounds ...'),
        (0x745815, 'test edi, edi', '... none: type 0 (the empty magazine)'),
        (0x74581D, 'cmp dword ptr [rbx + 4], ebp', 'no round list (WeaponMagazine +0 = 0) ...'),
        (0x745820, 'je 0x745a4f', '... ->'),
        (0x745A4F, 'mov ebp, dword ptr [rax]', '... the effective ProjectileWeapon +0'),
        (0x74585A, 'bt r8d, 8', 'WeaponRounds: its own record\'s types (not ProjectileWeapon +0)'),
        (0x74591C, 'bt r8d, 0xa', 'WeaponLinkedAmmo: its own model'),
    ],
    'chamberFill 0x76D8A0: a chamber is filled from ProjectileWeapon +0': [
        (0x76D9DE, 'call 0x515100', 'the effective ProjectileWeapon record (needs an instance) ...'),
        (0x76DA5B, 'cmp byte ptr [rsi + 0x9c], dil', '... for a chamber magazine (WeaponMagazine +156) ...'),
        (0x76DA64, 'mov edi, dword ptr [rax]', '... its +0 ...'),
        (0x76DA66, 'mov dword ptr [rbx + 8], edi', '... is the chambered type (0: can-fire 0x744D9C refuses)'),
    ],
    'projectileRow 0x11EC7C0: type 0 is a static all-zero row': [
        (0x11EC7C0, 'test ecx, ecx', 'type 0 ...'),
        (0x11EC7C4, 'lea rax, [rip + 0x25dad95]', '... -> game.dll+0x37C7560 (all zero: 0 pellets)'),
        (0x11EC7CE, 'lea rcx, [rip + 0x25dae9b]', 'else the row array game.dll+0x37C7670'),
    ],
    'heatStep 0x7627B0: heat once per call; stage projectiles carry their own type': [
        (0x762B31, 'mov dword ptr [rsp + 0x28], eax', 'a reached stage: its projectile type as the explicit type ...'),
        (0x762B52, 'call 0x741df0', '... fired through the generic fire (served by a ProjectileWeapon instance)'),
        (0x762CA7, 'mov r14, qword ptr [rip + 0x2bc3a2a]', 'no stage: a ProjectileWeapon instance ...'),
        (0x762D2D, 'mov dword ptr [rsp + 0x28], ebp', '... explicit type 0 (the weapon\'s own type) ...'),
        (0x762D35, 'call 0x6128b0', '... the projectile fire (pushes the projectile timer)'),
        (0x762DE2, 'movss xmm0, dword ptr [rsi + 0x74]', 'WeaponHeat +116 (heat per shot) ...'),
        (0x762DEE, 'movss dword ptr [rax + r12*4 + 4], xmm0', '... added once per call'),
    ],
    'beamShot 0x83F9D0: the round or the heat of every pulse': [
        (0x83FC1B, 'call 0x744690', 'one round per pulse'),
        (0x83FD16, 'call 0x7627b0', 'the heat step (with a WeaponHeat instance): heat + the projectile fire'),
    ],
    'projectileInit 0x618EB0: the replicated rpm is the effective record +8': [
        (0x618FFC, 'mulss xmm0, dword ptr [rax + 8]', 'effective ProjectileWeapon +8 x the mode factor ...'),
        (0x619008, 'movss dword ptr [rax + rbp*4 + 4], xmm0', '... = the replicated current rpm (field 0x4CBCC2A2)'),
    ],
    'damageAuthority: a remote player\'s simulated hit does not change health here': [
        (0x129F8C9, 'mov byte ptr [r12 + 2], al', 'the queued hit\'s +0x6E: the owner (wielder) is authority here'),
        (0x12A7E51, 'cmp byte ptr [r14 + 0x6e], r15b', 'a player owner and a non-player target: ...'),
        (0x12A7E59, 'cmovne r12d, edx', '... the apply bit = owner authority'),
        (0x12A8277, 'mov byte ptr [rsp + 0x70], r12b', 'the apply bit as ApplyDamage argument 15 ...'),
        (0x12A82EB, 'call 0x9235f0', '... ApplyDamage'),
        (0x924D10, 'movzx r8d, byte ptr [rbp + 0xb30]', 'ApplyDamage reads it ...'),
        (0x924D1F, 'test r8b, r8b', '...'),
        (0x924D22, 'je 0x925bee', '... 0: no health change here and no damage RPC to the owner'),
        (0x923F15, 'mov dword ptr [rdx + rcx*4 + 0xf8], r13d', 'before the gate: zone health in the local record'),
        (0x652951, 'test byte ptr [rbp + 0x14], 1', 'shields: the shield\'s owner lowers it for every hit it simulates'),
        (0x13AC91F, 'test byte ptr [rax + 0x14], 1', 'projectiles only: an earlier hit gate (the wielder authority)'),
        (0x13AC923, 'je 0x13ace5e', '... no such gate for beams'),
    ],
    'triggerReplication: every machine reproduces every player\'s trigger': [
        (0x7414F7, 'mov byte ptr [rdx + rax], 1', 'the owner: press'),
        (0x74182F, 'mov byte ptr [rcx + rax], r12b', 'the owner: release'),
        (0x7464F2, 'movzx eax, byte ptr [r8 + r15]', 'the weapon state\'s network apply: the received byte ...'),
        (0x7464F7, 'mov byte ptr [rdx + rcx], al', '... is the remote copy\'s trigger byte'),
    ],
}


def le32(v: int) -> str:
    return struct.pack('<I', v).hex()


def prove(img) -> dict:
    out = {}
    for group, rows in PINS.items():
        out[group] = [img.pin(rva, role, asm) for rva, asm, role in rows]
    return out


def zero_row(img) -> dict:
    row = img.data[ZERO_ROW_RVA:ZERO_ROW_RVA + 0x110]
    if row != bytes(0x110):
        raise ValueError('the type-0 ProjectileInfo row is not all zero in the image')
    if struct.unpack_from('<f', img.data, RATE_CONSTANT_RVA)[0] != 60.0:
        raise ValueError('the rate constant is not 60.0')
    return {'rva': '0x%X' % ZERO_ROW_RVA, 'size': 0x110, 'allZero': True, 'pellets28': 0,
            'rateConstant': {'rva': '0x%X' % RATE_CONSTANT_RVA, 'value': 60.0}}


def grown(before: bytes) -> bytes:
    entries = [int.from_bytes(before[i:i + 2], 'little') for i in range(0, len(before), 2)]
    if entries != sorted(set(entries)) or PROJECTILE not in entries or BEAM in entries:
        raise ValueError('a list to grow is not sorted, unique, with ProjectileWeapon and without BeamWeapon')
    return b''.join(e.to_bytes(2, 'little') for e in sorted(entries + [BEAM]))


def delta_members(w: dict, deltas, by_option, unlocks, CU) -> list:
    """(kind, item, offset, size) of every default / option entity delta entry patching ProjectileWeapon."""
    out = []
    for root in w['roots']:
        r = int(root['resource'], 16)
        paths = {}
        rec = CU.record_of(r)
        if rec is not None:
            body = CU.raw(rec)
            for at in range(0, 80, 8):
                slot, option = struct.unpack_from('<II', body, at)
                if option in by_option:
                    paths[by_option[option]['addPath']] = ('default', by_option[option]['debugName'])
        for o in unlocks.get(r, {}).get('options', []):
            paths.setdefault(int(o['addPath'], 16) if isinstance(o['addPath'], str) else o['addPath'],
                             ('option', o['debugName']))
        for p, (kind, item) in paths.items():
            d = deltas.get(p)
            for e in (d or {}).get('entries', []):
                if e['component'] == PROJECTILE:
                    out.append({'root': root['resource'], 'kind': kind, 'item': item, 'offset': e['offset'],
                                'size': e['size'], 'bytes': e['bytes'].hex()})
    return out


def covers(entries, offset, size=4):
    return [e for e in entries if e['offset'] < offset + size and offset < e['offset'] + e['size']]


def classify(w: dict, P, M, H, deltas_of) -> dict:
    """The add-layout verdict of one coverage weapon: verdict, reasonCode, reason, caveats, roots."""
    name = w['name']
    if w['verdict'] == 'out_of_scope':
        return {'verdict': 'out_of_scope', 'reasonCode': w['reasonCode'], 'reason': w['reason'], 'caveats': []}
    if w['verdict'] == 'refused':
        code = w['reasonCode']
        reason = {
            'ROUNDS_NO_BEAM_RELOAD': 'still refused: with a BeamWeapon instance the reload check takes the beam branch '
                                     '(0x775F1F -> 0x83F810), which reloads only by heat or magazine, and the fired '
                                     'type comes from the WeaponRounds record (0x74585A), not ProjectileWeapon +0',
            'LINKED_AMMO_NO_BEAM_RELOAD': 'still refused: the beam reload check refuses linked ammunition, and the '
                                          'fired type comes from the linked-ammunition model (0x74591C)',
            'CHARGE_WEAPON': 'still refused: with ProjectileWeapon kept, the charged release is served again by the '
                             'generic fire 0x741DF0 with its own type, and the beam fires on the charge level '
                             '(0x83E3DF): the combination is untested',
        }.get(code, w['reason'])
        return {'verdict': 'refused', 'reasonCode': code, 'reason': reason, 'caveats': []}
    roots = w['rootsToSwap']
    refusals, caveats, out_roots = [], [], []
    heat = w.get('heat')
    pd = deltas_of(w)
    for root in roots:
        r = int(root['resource'], 16)
        rec = P.record_of(r)
        if rec is None or rec != root['projectileRowKept']['record'] or P.owners(rec) != [r]:
            raise ValueError(name + ': the ProjectileWeapon record is not the root\'s own')
        raw = P.raw(rec)
        mine = [e for e in pd if e['root'] == root['resource']]
        if raw[NETWORKED_OFFSET]:
            refusals.append(('NETWORKED_SHOTS', 'ProjectileWeapon +148 = 1: the owner sends every shot as an RPC '
                             'before the type test (0x612EA4 -> 0x612F1E / 0x612F6E), so other players would still '
                             'be sent its shots'))
        if raw[HOOK_OFFSET]:
            refusals.append(('PROJECTILE_HOOK', 'ProjectileWeapon +68 = 1: an engine call before the type test '
                             '(0x613038), untested on the add layout'))
        if struct.unpack_from('<I', raw, FUNCTION_AMMO_OFFSET)[0]:
            refusals.append(('FUNCTION_AMMO', 'its weapon-function ammunition (ProjectileWeapon +576 = %d) is fired '
                             'with its own projectile type, which ProjectileWeapon +0 does not suppress' %
                             struct.unpack_from('<I', raw, FUNCTION_AMMO_OFFSET)[0]))
        sets_type = covers(mine, TYPE_OFFSET)
        if sets_type:
            refusals.append(('AMMUNITION_SETS_PROJECTILE', 'its %s set ProjectileWeapon +0 in the weapon\'s private '
                             'copy (%s), which overrides the record: with one equipped its bullets fire as well'
                             % ('default ammunition' if any(e['kind'] == 'default' for e in sets_type) else
                                'ammunition options', ', '.join(sorted({e['item'] for e in sets_type})[:4]))))
        mrec = M.record_of(r)
        if mrec is not None and struct.unpack_from('<I', M.raw(mrec), 0)[0]:
            refusals.append(('ROUND_LIST_MAGAZINE', 'its magazine (WeaponMagazine record %d) has a round list '
                             '(+0 = 1): the fired type comes from the list, not ProjectileWeapon +0' % mrec))
        hrec = H.record_of(r)
        stages = [struct.unpack_from('<I', H.raw(hrec), o)[0] for o in HEAT_STAGE_TYPES] if hrec is not None else []
        if any(stages):
            refusals.append(('HEAT_STAGE_PROJECTILES', 'heat stages fire their own projectile types %s through the '
                             'generic fire (0x762B31 -> 0x762B52), served again by the kept ProjectileWeapon '
                             'instance' % [s for s in stages if s]))
        rate = struct.unpack_from('<f', raw, RATE_OFFSET)[0]
        modes = [struct.unpack_from('<f', raw, o)[0] for o in (4, 12)]
        entry = {'resource': root['resource'], 'projectile': {
            'row': root['projectileRowKept']['row'], 'record': rec,
            'recordOffset': P.records_offset + rec * P.record_size,
            'typeBefore': le32(struct.unpack_from('<I', raw, TYPE_OFFSET)[0]),
            'type': struct.unpack_from('<I', raw, TYPE_OFFSET)[0],
            'rateBefore': raw[RATE_OFFSET:RATE_OFFSET + 4].hex(), 'rate': round(rate, 4),
            'rateModes4And12': [round(m, 4) for m in modes],
            'networked148': raw[NETWORKED_OFFSET], 'infiniteAmmo36': raw[INFINITE_OFFSET]}}
        m = root['membership']
        before = bytes.fromhex(m['beforeHex'])
        after = grown(before)
        entry['list'] = {'row': m['entitySettingsRow'], 'home': m['home'], 'count': m['count'],
                         'countAfter': m['count'] + 1, 'listOffsetInBody': m['listOffsetInBody'],
                         'beforeHex': m['beforeHex'], 'afterHex': after.hex(),
                         'nextListStartsAt': m.get('nextListStartsAt'), 'gapAfterList': m.get('gapAfterList')}
        if m.get('gapAfterList') not in (0, None):
            raise ValueError(name + ': a list with slack (the lists are packed)')
        if heat:
            if any(modes):
                refusals.append(('HEAT_RATE_SELECTOR', 'a heat weapon with a rate selector (ProjectileWeapon +4 / '
                                 '+12 = %s): the projectile timer would follow the selected slot' % modes))
            rated = covers(mine, RATE_OFFSET)
            if rated:
                caveats.append(('HEAT_RATE_ATTACHMENT', 'with %s equipped the private copy sets the projectile rate '
                                '(ProjectileWeapon +8), so heat steps come at the faster of that rate and the pulse '
                                'rate' % ', '.join(sorted({e['item'] for e in rated}))))
        out_roots.append(entry)
    seen, uniq = set(), []
    for code, text in refusals:
        if code not in seen:
            seen.add(code)
            uniq.append((code, text))
    if uniq:
        return {'verdict': 'refused', 'reasonCode': uniq[0][0], 'reason': uniq[0][1],
                'allReasons': [{'code': c, 'text': t} for c, t in uniq], 'caveats': [], 'roots': out_roots,
                'swapFallback': True}
    carried = []
    for c in w.get('caveats', []):
        code = c['code']
        if code in ('OPTION_LEAKS_PROJECTILE_COPY', 'RESTART_AFTER_USE'):
            continue        # ProjectileWeapon is kept: its destroy handler frees the private copy (0x619F90)
        if code == 'WINDOW_CROSSES_PAGE':
            continue        # the add layout never writes inside a list
        if code == 'HEAT_STAGES':
            continue
        if code == 'ROF_SELECTOR_INERT':
            c = {'code': code, 'text': 'its rate-of-fire selector switches ProjectileWeapon +4 slots: only the '
                 'projectile timer follows it (every projectile shot ends at type 0); the beam rate is BeamWeapon '
                 '+104'}
        carried.append({'code': c['code'], 'text': c['text']})
    if heat:
        carried.append({'code': 'HEAT_PROJECTILE_TIMER', 'text': 'the heat step also runs on every projectile-update '
                        'shot: the conversion sets the ProjectileWeapon rate (+8) below the slowest pulse cadence, so '
                        'the beam pulses keep the projectile timer ahead and heat comes once per pulse'})
    for code, text in caveats:
        carried.append({'code': code, 'text': text})
    verdict = 'supported_with_caveats' if carried else 'supported'
    return {'verdict': verdict, 'reasonCode': 'ADD_LAYOUT', 'reason': 'keeps ProjectileWeapon (its type set to 0: '
            'every projectile shot ends at 0x614076) and gains BeamWeapon through a Runtime-owned list',
            'caveats': carried, 'roots': out_roots, 'heat': bool(heat)}


def snapshot_checks(items, P) -> dict:
    """Every retained snapshot: each add root's entity map row (pointer -> the file list, count), the list bytes and
    its ProjectileWeapon record's +0 / +8 (equal to the file)."""
    out = {}
    for name in SNAPSHOTS:
        reader = instances.SnapshotReader(name)
        try:
            game = reader.modules['game.dll']['base']
            root = instances.u64(reader, game + cm.ENTITY_MANAGER)
            esh = instances.u64(reader, root + cm.ESH_SLOT)
            pslot = instances.u64(reader, root + cm.SLOT_BASE + 8 * PROJECTILE)
            zero = reader.read(game + ZERO_ROW_RVA, 0x110)
            bad, rate_drift = [], []
            for label, e, heat in items:
                lst = e['list']
                rowb = reader.read(esh + 32 * lst['row'], 32)
                lp = struct.unpack_from('<Q', rowb, 8)[0]
                ok = (lp - esh == lst['listOffsetInBody'] and struct.unpack_from('<I', rowb, 16)[0] == lst['count']
                      and reader.read(lp, 2 * lst['count']).hex() == lst['beforeHex'])
                # slot 321 holds the table body (index rows, then records at recordsOffset), as the file reads it
                rec = reader.read(pslot + e['projectile']['recordOffset'], 16)
                ok = ok and rec[0:4].hex() == e['projectile']['typeBefore']
                if rec[8:12].hex() != e['projectile']['rateBefore']:
                    if heat:
                        ok = False          # the add layout writes +8 of a heat root: pinned
                    rate_drift.append({'root': label, 'rateNow': round(struct.unpack_from('<f', rec, 8)[0], 3),
                                       'file': e['projectile']['rate'], 'written': bool(heat)})
                if not ok:
                    bad.append(label)
            out[name] = {'rootsChecked': len(items), 'mismatches': bad, 'zeroRowAllZero': zero == bytes(0x110),
                         'rateDiffersFromFile': rate_drift}
        finally:
            reader.close()
        if out[name]['mismatches'] or not out[name]['zeroRowAllZero']:
            raise ValueError('snapshot %s: %r' % (name, out[name]))
    return out


def main():
    img = xref.CodeImage.from_snapshot('game.dll')
    if img.sha256.upper() != base.PROFILE_DLL_SHA:
        raise ValueError('the snapshot game.dll is not the pinned profile')
    pins = prove(img)
    flat = [p for rows in pins.values() for p in rows]
    mismatch = {name: base.verify_pins_live(name, flat, []) for name in SNAPSHOTS}
    if any(mismatch.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % mismatch)
    coverage = json.loads(COVERAGE.read_text(encoding='utf-8'))
    t = tables.pinned()
    P = t.component('ProjectileWeaponComponentData')
    M = t.component('WeaponMagazineComponentData')
    H = t.component('WeaponHeatComponentData')
    CU = t.component('WeaponCustomizationComponentData')
    rows = t.entity_rows()
    both = [hex(r) for r, lst in rows.items() if BEAM in lst and PROJECTILE in lst]
    unsorted = [hex(r) for r, lst in rows.items() if list(lst) != sorted(set(lst))]
    if unsorted:
        raise ValueError('a vanilla membership list is not sorted and unique')
    deltas, custom = cov.pinned_files()
    by_option = {it['optionId']: it for it in custom}
    unlocks = {int(w['resource'], 16): w for w in json.loads(UNLOCKS.read_text(encoding='utf-8'))['weapons']}
    cache = {}

    def deltas_of(w):
        if w['name'] not in cache:
            cache[w['name']] = delta_members({'roots': w['rootsToSwap']}, deltas, by_option, unlocks, CU)
        return cache[w['name']]
    weapons = []
    for w in coverage['weapons'] + coverage['outOfScope']:
        add = classify(w, P, M, H, deltas_of)
        item = {'name': w['name'], 'kind': w['kind'], 'resource': w.get('resource'),
                'swap': {'verdict': w['verdict'], 'reasonCode': w['reasonCode']}, 'add': add}
        if w['verdict'] in ('supported', 'supported_with_caveats'):
            item['projectileDeltas'] = deltas_of(w)
        weapons.append(item)
    items = [(x['name'] + ' ' + r['resource'], r, x['add'].get('heat')) for x in weapons
             for r in x['add'].get('roots', [])]
    checks = snapshot_checks(items, P)
    supported = [x for x in weapons if x['add']['verdict'] in ('supported', 'supported_with_caveats')]
    counts = {}
    for x in weapons:
        counts.setdefault(x['add']['verdict'], {}).setdefault(x['add']['reasonCode'], 0)
        counts[x['add']['verdict']][x['add']['reasonCode']] += 1
    lists = [r['list'] for x in supported for r in x['add']['roots']]
    out = {
        'schemaVersion': 1, 'build': 'F5FEE03DCFDB', 'gameDllSha256': img.sha256.upper(), 'writes': 0,
        'protectionChanges': 0,
        'question': 'Convert a projectile weapon to Trident pulses by KEEPING ProjectileWeapon and adding BeamWeapon '
                    '(the user\'s decision 2026-10-10, after Bans\' True Lasgun Beam Overhaul as a lead): how it '
                    'fires, what suppresses the projectile, ammunition, rate, multiplayer, coverage.',
        'follows': ['beam-conversion-coverage-F5FEE03DCFDB.md', 'beam-conversion-mp-F5FEE03DCFDB.md',
                    'beam-conversion-mp-sync-F5FEE03DCFDB.md', 'component-swap-liberator-beam.md',
                    'component-swap-liberator-beam-chamber.md', 'las-beam-overhaul-comparison.md'],
        'pins': pins, 'pinnedBytesMismatchPerSnapshot': mismatch,
        'zeroTypeRow': zero_row(img),
        'vanillaEntitiesWithBothComponents': both,
        'vanillaListsSortedUnique': True,
        'projectileTable': {'capacity': P.capacity, 'recordsOffset': P.records_offset, 'recordSize': P.record_size},
        'listBlock': {'maxListBytes': max(2 * l['countAfter'] for l in lists), 'roots': len(lists),
                      'bytes': sum(2 * l['countAfter'] for l in lists)},
        'weapons': weapons, 'snapshots': checks,
        'summary': {'weapons': len(weapons), 'addSupported': len(supported),
                    'addSupportedNames': sorted(x['name'] for x in supported),
                    'swapOnly': sorted(x['name'] for x in weapons if x['add'].get('swapFallback')),
                    'verdicts': counts},
    }
    text = json.dumps(out, indent=1, sort_keys=False)
    OUTPUT.write_text(text + '\n', encoding='utf-8')
    print('wrote', OUTPUT, hashlib.sha256(text.encode()).hexdigest()[:16])
    print(json.dumps(out['summary'], indent=1))


if __name__ == '__main__':
    main()
