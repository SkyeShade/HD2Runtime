"""What a missile silo's pod delivers: its rack's items and their roles (research for a custom silo payload).

Read-only. Proves, on build F5FEE03DCFDB, from the decoded entity table and research/pod-payloads-F5FEE03DCFDB.json:

1. The pod. The MS-11 Solo Silo's StratagemDefinition payload is its rack entity, weapon_rack_mini_missile_silo: the
   silo the pod deploys (its unit is the silo model). Its HellpodRack holds two active slots (spawn_payload_size 2):
   slot 0 the MISSILE (the only item with an ExplosiveComponent and a SeekingMissile component), slot 1 the laser
   REMOTE (LaserDesignator and WeaponLinker: the item a player carries to aim and fire). Both are spawned by the rack
   in the same native call as every rack item, so runtime/support_pods.lua capture finds them through the game's own
   records (the pod naming the beacon, its rack, each slot's network id).
2. The missile is an entity, not a projectile: SeekingMissile +173 = 0 (not run by the projectile system) and +176 = 0
   (no projectile type), so no projectile conversion applies to it. Its ExplosiveComponent record has exactly one
   owner (the missile type): mode +0 = 2 (external activation), detonation +36 = ExplosionType 135 (the vanilla silo
   blast), impact +40 = ExplosionType 420.
3. The launch timing is code, not data (ability 2088, the missile explosive's armed ability: tick 0 the silo retracts
   and fires its launch blast, tick 2 the missile detaches, tick 120 its explosive is activated); there is no data
   field for a countdown.

What a Runtime silo payload therefore observes, read-only: the call's own missile entity (by the capture), its
position while it exists, and its end. Unproven (live test): what a detonation looks like from outside (the entity's
removal follows its explosion; RemovalDelay 1 is shared type data), and whether the missile can end without
detonating (a destroyed silo).
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402

PODS = ROOT / 'research/pod-payloads-F5FEE03DCFDB.json'
OUTPUT = ROOT / 'research/silo-payload-F5FEE03DCFDB.json'
SILOS = ['MS-11 Solo Silo']
COMPONENTS = ['ExplosiveComponentData', 'SeekingMissileComponentData', 'LaserDesignatorComponentData',
    'WeaponLinkerComponentData', 'HealthComponentData', 'WeaponDataComponentData', 'HellpodRackComponentData']
EXPLOSIVE = {'mode': 0, 'detonation': 36, 'impact': 40}
SEEKING = {'projectileHandled': 173, 'projectileType': 176}


def main():
    import research_entity_authoring as entity_research
    native = entity_research.Native()
    pods = json.loads(PODS.read_text(encoding='utf-8'))
    out = []
    for name in SILOS:
        racks = [r for r in pods['racks'] if any(c['catalogStratagem'] == name for c in r['consumers'])]
        if len(racks) != 1:
            raise ValueError(name + ': not exactly one rack')
        rack = racks[0]
        if [c['catalogStratagem'] for c in rack['consumers']] != [name] or rack['ownerCount'] != 1:
            raise ValueError(name + ': its rack is shared')
        if native.component(rack['resource'], 'HellpodRackComponentData') is None:
            raise ValueError(name + ': the payload entity has no rack')
        active = [s for s in rack['slots'] if s['active'] and s['item']]
        if rack['spawnPayloadSize'] != len(active):
            raise ValueError(name + ': the spawn count is not its active slots')
        items = []
        for slot in active:
            present = [c for c in COMPONENTS if native.component(slot['item'], c) is not None]
            item = {'slot': slot['index'], 'resource': slot['item'], 'path': native.path(int(slot['item'], 16)),
                'node': slot['node'], 'components': present}
            if 'ExplosiveComponentData' in present and 'SeekingMissileComponentData' in present:
                item['role'] = 'missile'
                c = native.component(slot['item'], 'ExplosiveComponentData')
                raw = native.record('ExplosiveComponentData', c['record_index'])
                item['explosive'] = dict({k: struct.unpack_from('<I', raw, o)[0] for k, o in EXPLOSIVE.items()},
                    record=c['record_index'], owners=native.ownership(c)['ownerCount'])
                s = native.component(slot['item'], 'SeekingMissileComponentData')
                raw = native.record('SeekingMissileComponentData', s['record_index'])
                item['seekingMissile'] = dict({k: raw[o] for k, o in SEEKING.items()}, record=s['record_index'])
            elif 'LaserDesignatorComponentData' in present and 'WeaponLinkerComponentData' in present:
                item['role'] = 'remote'
            else:
                raise ValueError('%s slot %d: neither the missile nor the remote' % (name, slot['index']))
            items.append(item)
        roles = [i['role'] for i in items]
        if sorted(roles) != ['missile', 'remote']:
            raise ValueError(name + ': expected one missile and one remote, got %r' % roles)
        missile = items[roles.index('missile')]
        if missile['explosive']['owners'] != 1 or missile['explosive']['mode'] != 2:
            raise ValueError(name + ': the missile explosive is shared or not externally activated')
        if missile['seekingMissile']['projectileHandled'] or missile['seekingMissile']['projectileType']:
            raise ValueError(name + ': the missile is handled by the projectile system')
        consumer = rack['consumers'][0]
        out.append({'stratagem': name, 'id': consumer['id'], 'kind': consumer['kind'],
            'nativeType': consumer['nativeType'], 'rack': rack['resource'], 'rackPath': rack['path'],
            'rackComponents': [c for c in COMPONENTS if native.component(rack['resource'], c) is not None],
            'items': items})
    report = {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'silos': out,
        'findings': {
            'pod': 'The pod\'s content is the silo itself (its rack entity); its two rack items are the missile (slot 0) '
                'and the laser remote (slot 1), spawned and named in their slots by the rack.',
            'missile': 'The missile is an entity with its own ExplosiveComponent (one owner): it requests ExplosionType '
                '135 when it detonates; it is not a projectile.',
            'launch': 'The launch sequence is the missile explosive\'s armed ability (2088), timed in code (tick 0 '
                'retract and launch blast, tick 2 detach, tick 120 explosive active); no data field delays it.'},
        'unproven': ['What the detonation looks like from outside the explosive (the missile entity is removed after '
            'its explosion).', 'Whether the missile can be removed without detonating (for example a destroyed silo).',
            'What other machines see of a host-requested explosion.'],
        'writes': 0}
    OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps([{s['stratagem']: [(i['slot'], i['role'], i['path']) for i in s['items']]} for s in out]))


if __name__ == '__main__':
    main()
