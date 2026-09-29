"""Cross-family output composition: can a projectile weapon fire a beam? Read-only.

Answers the next step after research/attack-outputs (a reference swap cannot cross output families) on build
F5FEE03DCFDB, from the pinned entity table, game.dll code and the retained snapshots:

1. Component composition is fixed data. An entity's components are a packed u16 list inside EntitySettingsHashmap
   (offset, count per entity); all 1909 lists are laid end to end with zero bytes between them, so giving the
   Liberator a BeamWeaponComponent would overwrite the next entity's list. Each component table's index is a hash
   table (resource mod capacity, linear probing: 0x514C10 for ProjectileWeapon, 0x4F5C10 for LoadoutEntry); every
   BeamWeapon row sits on its hashed probe path, so a new membership also needs a hashed slot. No allocation or
   ownership mechanism for either exists, so component cloning or attachment is blocked, not deferred.
2. Even a weapon owning both would not fire the beam. The trigger dispatch (0x742550) reads the entity's output-family
   flags from the weapon manager (game+0x3326660, 0x28-byte records): bit 0 (projectile) routes to the projectile
   trigger (0x612800) and only otherwise bit 1 (beam) to the beam trigger (0x83F750). The projectile always wins.
3. A beam is not a request. The beam trigger 0x83F750(entity, firing) only sets the firing flag (+0x18) of that
   entity's own beam_weapon instance (game+0x3326A20, 0x70-byte records); the per-frame beam update does the rest
   (ray, damage, heat, audio). There is no BeamType, origin or direction argument and no beam queue like the
   explosion (0x13C0A80) and projectile (0x13A8F50) requests; for an entity without a beam instance the lookup
   falls through to index 0xFFFFFFFF and writes out of bounds. A hd2.beams.fire action cannot be built on it.
4. The event route cannot suppress output: events are polled after the fact (player_fired from the stats table at
   10 Hz); nothing runs before the trigger dispatch, and cancelling native output would need a code hook.
5. Ownership facts for the record: 22 of 23 beam entities own WeaponHeat; the 40-K Meltagun is the native
   magazine-fed beam (BeamWeapon + WeaponCharge + WeaponMagazine + WeaponReload, no heat), so a beam does not
   intrinsically need heat, but only as its own entity's composition.

Requires the research-only package capstone.
Output: research/output-composition-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_event_state as base  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
import snapshot_image  # noqa: E402

OUTPUT = ROOT / 'research/output-composition-F5FEE03DCFDB.json'
OUTPUTS = ROOT / 'sdk/AttackOutputCapabilities.json'
FUNCTIONS = ROOT / 'research/weapon-functions-F5FEE03DCFDB.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap', 'F5FEE03DCFDB-20260926T222226Z.hd2snap']
HOST = ('AR-23 Liberator', 0x968211C0033DCE64)
DONORS = {'LAS-5 Scythe': 'player', 'LAS-98 Laser Cannon': 'support', 'LAS-13 Trident': 'player'}
FAMILY = {'ProjectileWeaponComponentData': 'projectile', 'BeamWeaponComponentData': 'beam',
    'ArcWeaponComponentData': 'arc', 'SprayWeaponComponentData': 'spray', 'MeleeWeaponComponentData': 'melee'}
RESOURCE = {'WeaponMagazineComponentData': 'magazine', 'WeaponRoundsComponentData': 'rounds',
    'WeaponHeatComponentData': 'heat', 'WeaponChargeComponentData': 'charge', 'WeaponReloadComponentData': 'reload'}

GAME_PROOFS = {
    'triggerDispatch': [
        (0x74255E, 'mov r9, qword ptr [rip + {rip}]', 0x3326660, 'the trigger dispatch loads the weapon manager'),
        (0x7425DD, 'mov r8d, dword ptr [rax + rdx*8]', None, 'the entity output-family flags (0x28-byte records)'),
        (0x7425E1, 'test r8b, 1', None, 'a projectile weapon'),
        (0x742605, 'jmp 0x612800', None, 'fires its projectile trigger'),
        (0x742624, 'test r8b, 2', None, 'only otherwise a beam weapon'),
        (0x742648, 'jmp 0x83f750', None, 'fires its beam trigger'),
    ],
    'beamTrigger': [
        (0x83F75C, 'mov r11, qword ptr [rip + {rip}]', 0x3326A20, 'the beam trigger loads the beam_weapon manager'),
        (0x83F770, 'imul rdx, rcx, 0x70', None, 'instance records of 0x70 bytes'),
        (0x83F774, 'mov byte ptr [rdx + rax + 0x18], r8b', None, 'an entity without a beam instance writes index -1'),
        (0x83F7F3, 'mov byte ptr [rdx + rax + 0x18], r14b', None, 'the entity beam instance firing flag (+0x18)'),
    ],
    'componentIndex': [
        (0x514C37, 'imul eax, edx, 0x21e', None, 'ProjectileWeapon index: resource mod 542'),
        (0x514C74, 'cmp eax, 0x21d', None, 'linear probing wraps at the last row'),
        (0x4F5C37, 'imul eax, edx, 0x182', None, 'LoadoutEntry index: resource mod 386'),
    ],
}


def families(native, resource):
    report = native.report(hex(resource))
    names = {c['name'] for c in report['components'] if c.get('name')}
    return sorted(FAMILY[n] for n in names if n in FAMILY), sorted(RESOURCE[n] for n in names if n in RESOURCE)


def main():
    native = entity_research.Native()
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
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

    # 1. Membership lists: packed end to end.
    _, body, _, _, _ = native.probe.find_component(native.entities, 'EntitySettingsHashmap')
    rows = []
    for row in range(4096):
        resource, offset, count = struct.unpack_from('<QQQ', body, row * 32)
        if resource:
            rows.append((offset, count, resource))
    rows.sort()
    gaps = [rows[i + 1][0] - (rows[i][0] + 2 * rows[i][1]) for i in range(len(rows) - 1)]
    host = next(r for r in rows if r[2] == HOST[1])
    following = rows[rows.index(host) + 1]
    membership = {'entities': len(rows), 'zeroGapLists': sum(1 for g in gaps if g == 0),
        'nonZeroGaps': sum(1 for g in gaps if g != 0), 'host': {'weapon': HOST[0], 'listOffset': host[0],
            'components': host[1], 'nextListOffset': following[0], 'slackBytes': following[0] - (host[0] + 2 * host[1])}}
    if membership['nonZeroGaps'] or membership['host']['slackBytes']:
        raise ValueError('an entity component list has slack; re-audit component composition')

    # Component tables: hashed placement and capacity.
    tables = {}
    for component in ('BeamWeaponComponentData', 'ProjectileWeaponComponentData', 'WeaponHeatComponentData',
            'ArcWeaponComponentData', 'SprayWeaponComponentData', 'WeaponMagazineComponentData'):
        body_c, capacity, _, record_size, record_count = native.table(component)
        used = [struct.unpack_from('<Q', body_c, r * 16)[0] for r in range(capacity)]
        consistent = 0
        for r, resource in enumerate(used):
            if not resource:
                continue
            k, fine = resource % capacity, True
            while k != r:
                if not used[k]:
                    fine = False
                    break
                k = (k + 1) % capacity
            consistent += fine
        tables[component] = {'indexRows': capacity, 'usedRows': sum(1 for u in used if u), 'records': record_count,
            'recordSize': record_size, 'rowsOnHashedProbePath': consistent}
        if consistent != tables[component]['usedRows']:
            raise ValueError(component + ' index is not a resource-mod-capacity hash table')

    # Ownership of beams, heat and magazines.
    def owners(component):
        found = set()
        for resources in native.owners(component).values():
            found.update(resources)
        return found
    beam, heat, magazine = owners('BeamWeaponComponentData'), owners('WeaponHeatComponentData'), \
        owners('WeaponMagazineComponentData')
    projectile = owners('ProjectileWeaponComponentData')
    precedent = [{'entity': native.path(r) or '0x%016X' % r, 'families': families(native, r)[0],
        'resources': families(native, r)[1]} for r in sorted(beam - heat)]
    catalog = json.loads(OUTPUTS.read_text())
    support_names = {}
    for w in json.loads((ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json').read_text())['weapons']:
        identity = w['catalogIdentity']
        for r in w['resourceHashes']:
            support_names[int(r, 16)] = identity['name'] if isinstance(identity, dict) else identity
    for item in precedent:
        resource = next(r for r in beam - heat if (native.path(r) or '0x%016X' % r) == item['entity'])
        item['weapon'] = support_names.get(resource)
    ownership = {'beamEntities': len(beam), 'beamWithHeat': len(beam & heat), 'beamWithProjectile': len(beam & projectile),
        'magazineFedBeams': precedent}

    host_families = families(native, HOST[1])
    player = {w['name']: w for w in json.loads((ROOT / 'sdk/PlayerWeaponAuthoringCapabilities.json').read_text())['weapons']}
    donors = []
    for name, kind in DONORS.items():
        resources = player[name]['resources'] if kind == 'player' else [r for r, n in (
            ('0x%016X' % k, v) for k, v in support_names.items()) if n == name]
        fam, res = families(native, int(resources[0], 16))
        output = next((o for o in catalog['outputs'] if o['owner']['name'] == name), None)
        donors.append({'donor': name, 'kind': kind, 'families': fam, 'resources': res,
            'beamKind': output and output.get('kind'), 'outputId': output and output.get('semanticId')})
    blockers = [
        {'id': 'MEMBERSHIP_PACKED', 'route': 'component_composition', 'detail': 'The Liberator component list (%d '
            'components) is followed immediately by the next entity list; all %d lists are packed with zero slack, so '
            'adding a BeamWeaponComponent overwrites another entity.' % (host[1], len(rows))},
        {'id': 'COMPONENT_INDEX_HASHED', 'route': 'component_composition', 'detail': 'BeamWeaponComponentData is a '
            '%d-row hash index (%d used, %d records); a new membership needs a hashed row and a record, and no safe '
            'allocation for either exists.' % (tables['BeamWeaponComponentData']['indexRows'],
                tables['BeamWeaponComponentData']['usedRows'], tables['BeamWeaponComponentData']['records'])},
        {'id': 'TRIGGER_PREFERS_PROJECTILE', 'route': 'component_composition', 'detail': 'The trigger dispatch '
            '(0x742550) routes a weapon with the projectile flag to its projectile trigger and never to its beam '
            'trigger, so a Liberator owning both would still fire bullets.'},
        {'id': 'BEAM_IS_ENTITY_STATE', 'route': 'event_action', 'detail': 'A beam is the firing flag of an entity own '
            'beam_weapon instance (0x83F750); there is no request taking a beam type, origin or direction, and the '
            'call writes out of bounds for an entity without a beam instance.'},
        {'id': 'NO_PRE_FIRE_HOOK', 'route': 'event_action', 'detail': 'Events are polled after the game has fired '
            '(player_fired from the stats table, 10 Hz); native output cannot be suppressed without a code hook.'},
        {'id': 'REFERENCE_FAMILY', 'route': 'reference_swap', 'detail': 'A ProjectileType reference cannot name a '
            'BeamType (research/attack-outputs): INCOMPATIBLE_OUTPUT_FAMILY.'}]
    verdicts = [{'host': HOST[0], 'donor': d['donor'], 'outputId': d['outputId'], 'beamKind': d['beamKind'],
        'status': 'blocked', 'routes': {'reference_swap': 'blocked', 'component_composition': 'blocked',
            'event_action': 'blocked'}, 'blockers': [b['id'] for b in blockers]} for d in donors]
    functions = json.loads(FUNCTIONS.read_text())
    selectable = [{'kind': w['kind'], 'weapon': w['weapon'], 'mechanism': mechanism} for w in functions['weapons']
        for mechanism in (['programmable_ammo'] if (w.get('functionAmmo') or {}).get('state') == 'native' else [])
        + (['rounds_magazine'] if (w.get('feeds') or {}).get('selectorBound') and w['feeds']['alternate']['projectile']
            else [])]
    report = {'schemaVersion': 1, 'writes': 0, 'build': build_profile.BUILD_ID, 'proofs': proofs,
        'membership': membership, 'componentTables': tables, 'ownership': ownership,
        'host': {'weapon': HOST[0], 'families': host_families[0], 'resources': host_families[1]},
        'donors': donors, 'blockers': blockers, 'verdicts': verdicts,
        'beamLifecycle': {'start': 'the wielder trigger sets the beam instance firing flag (0x83F750, +0x18)',
            'stop': 'releasing the trigger clears it', 'continuous': 'LAS-5 and LAS-98 (BeamFireMode 4) beam while the '
                'flag is set; the Trident (BeamFireMode 6) fires its pulse per trigger (research/attack-outputs)',
            'heat': 'the owner WeaponHeat instance (or, on the 40-K Meltagun, its magazine and charge)',
            'networking': 'not traced; the beam instance belongs to the owner entity'},
        'nativeMultipleOutputs': selectable,
        'summary': {'requestedCompositions': len(verdicts), 'blocked': len(verdicts),
            'magazineFedBeamPrecedent': [p['weapon'] for p in precedent], 'nativeSelectableOutputs': len(selectable)}}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', newline='\n')
    print(json.dumps(report['summary'], indent=1))


if __name__ == '__main__':
    main()
