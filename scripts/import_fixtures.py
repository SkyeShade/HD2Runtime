"""Extract reviewed layouts and sparse regression captures; never modify siblings.

Only reads already-decoded, previously audited inputs. No extraction/decompilation.
Run once to refresh the pinned profile, then normal tests need no sibling projects.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = ROOT.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import layout, dl_hash, find_component, groups, lua


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def main():
    folder = SIBLINGS / 'ShieldRelayImprovements/local_research/dependencies/filediver-current/datalibrary'
    entity = (folder / 'generated_entities.dl_bin').read_bytes()
    library = (folder / 'dl_library.dl_typelib').read_bytes()
    assert sha(entity) == '21377252B81FDBC670EBA1E59A8AB64B170323DF208F175E708992E4C1FB515E'
    assert sha(library) == '4D04870D0A0D4DC1284998C72CDFA6F8FF6D21ABA0E36B6F758C6F73DD0417A4'
    manifest = {'mode': 'read_only', 'sources': [], 'field_evidence': 'schemas/sdk.json'}
    def source(relative):
        raw = (SIBLINGS / relative).read_bytes()
        manifest['sources'].append({'path': relative, 'sha256': sha(raw)})
        return raw
    for project, paths in {
        'Jar-5_buff': ['README.md', 'docs/research.md', 'research/jar5-evidence.json', 'src/gameplay/parse.lua', 'src/gameplay/capture.lua', 'src/gameplay/transaction.lua',
            'src/gameplay/validate.lua', 'src/infra/windows_write.lua',
            'scripts/research/probe_components.py', 'scripts/research/inspect_typelib.py', 'scripts/research/grouped_dl.py', 'scripts/research/runtime_reference.py', 'scripts/hd2_archive.py'],
        'BastionReArmored': ['README.md', 'src/diagnostic/inspect.lua', 'src/armor_proof/validate.lua', 'src/lunchbox_proof/validate.lua', 'src/release/transaction.lua'],
        'StrongerOrbitalLaser': ['README.md', 'src/damage/validate.lua', 'src/damage/transaction.lua', 'research/gameplay-proof-400.md',
            'research/laser-evidence.json', 'scripts/research/laser_capture.lua'],
        'ShieldRelayImprovements': ['README.md', 'scripts/shield_reference.py', 'scripts/research/stratagem_probe.lua',
            'scripts/research/guarded_memory.lua', 'scripts/research/stratagem_patch.lua',
            'scripts/research/windows_memory.lua', 'research/cooldown-live-confirmation.json'],
        'JumpPackImprovements': ['README.md', 'research/current-build-port.md', 'research/movement.md', 'src/jump_pack_improvements.lua',
            'local_research/dependencies/BingusSharedLoader/docs/AUTHORING.md'],
        'ReticleAmr': ['README.md', 'src/diagnostic/inspect.lua', 'src/diagnostic/windows_readonly.lua', 'src/infra/windows_ffi.lua', 'research/gameplay-confirmation-0.1.0.json',
            'src/gameplay/patch.lua', 'scripts/lua_offline.py'],
    }.items():
        for path in paths:
            source(project + '/' + path)
    source(str(folder.relative_to(SIBLINGS) / 'generated_entities.dl_bin').replace('\\', '/'))
    source(str(folder.relative_to(SIBLINGS) / 'dl_library.dl_typelib').replace('\\', '/'))
    files = json.loads(source('Jar-5_buff/src/current_build.json'))['files']
    profile = {'exe_sha': files['bin/helldivers2.exe']['sha256'], 'dll_sha': files['data/game/game.dll']['sha256'],
               'entity_size': len(entity), 'entity_region_size': (len(entity)+4095)//4096*4096,
               'components': {}, 'resources': {}, 'settings': {}}
    spans = {}
    def span(offset, data):
        spans[offset] = data
    map_inst, map_body, _, _, _ = find_component(entity, 'EntitySettingsHashmap')
    profile['map_header'] = map_inst[:28].hex()
    profile['map_rows'] = 4096
    span(0, map_inst)
    component_names = ['ProjectileWeaponComponentData', 'WeaponDataComponentData', 'HealthComponentData',
                       'OrbitalAbilityComponentData', 'ShieldComponentData', 'HellpodPayloadComponentData',
                       'RechargeComponentData', 'JumppackComponentData',
                       'LoadoutPackageComponentData', 'WeaponMagazineComponentData',
                       'WeaponRoundsComponentData', 'WeaponCustomizationComponentData',
                       'ArcWeaponComponentData', 'MeleeWeaponComponentData',
                       'BeamWeaponComponentData', 'SprayWeaponComponentData',
                       'WeaponHeatComponentData',
                       'WeaponChargeComponentData', 'ExplosiveComponentData',
                       'HellpodRackComponentData', 'WeaponLinkedAmmoComponentData',
                       'BackpackComponentData', 'WeaponLinkerComponentData',
                       'BombardmentComponentData', 'EagleComponentData', 'MountComponentData',
                       'WeaponReloadComponentData', 'WeaponWindUpComponentData',
                       'DepositComponentData', 'TagComponentData', 'InteractableComponentData',
                       'ThrowableComponentData', 'StickyComponentData', 'MinefieldComponentData',
                       'TurretComponentData', 'SensorEyeComponentData', 'ThrowerComponentData',
                       'LoadoutEntryComponentData', 'DisplacementComponentData', 'ShieldControllerComponentData',
                       'GoreComponentData', 'RotationComponentData', 'VehicleMotionComponentData']
    mapper_auxiliary = {'LoadoutPackageComponentData', 'WeaponMagazineComponentData',
                        'WeaponRoundsComponentData', 'WeaponCustomizationComponentData',
                        'ArcWeaponComponentData', 'MeleeWeaponComponentData',
                        'BeamWeaponComponentData', 'SprayWeaponComponentData',
                        'WeaponHeatComponentData',
                        'WeaponChargeComponentData', 'ExplosiveComponentData',
                        'HellpodRackComponentData', 'WeaponLinkedAmmoComponentData',
                        'BackpackComponentData', 'WeaponLinkerComponentData',
                        'BombardmentComponentData', 'EagleComponentData',
                        'WeaponReloadComponentData', 'WeaponWindUpComponentData',
                        'DepositComponentData', 'TagComponentData', 'InteractableComponentData',
                        'ThrowableComponentData', 'StickyComponentData', 'MinefieldComponentData',
                        'DisplacementComponentData', 'ShieldControllerComponentData'}
    for name in component_names:
        inst, body, version, is64, offset = find_component(entity, name)
        outer = layout(library, name)
        indices, records = outer['members'][:2]
        record_layout = layout(library, records['type_hash'])
        assert version == 1 and is64 and indices['offset64'] == 0
        assert records['offset64'] == indices['array_or_bits'] * 16
        # LoadoutEntryComponentData alone carries a third, parallel per-record array after its records.
        for extra in outer['members'][2:]:
            assert name == 'LoadoutEntryComponentData' and extra['offset64'] == records['offset64'] + records['size64']                 and extra['array_or_bits'] == records['array_or_bits']
        c = {'offset': offset, 'header': inst[:28].hex(), 'index': struct.unpack_from('<I', entity, offset-4)[0],
             'indices': indices['array_or_bits'], 'records': records['array_or_bits'],
             'record_offset': records['offset64'], 'stride': record_layout['size64'], 'type': dl_hash(name)}
        profile['components'][name] = c
        end = offset+28+(c['record_offset']+c['records']*c['stride']
                         if name in mapper_auxiliary else c['record_offset'])
        span(offset-4, entity[offset-4:end])
    weapon_resources = set()
    for name in ('ProjectileWeaponComponentData', 'WeaponDataComponentData'):
        c = profile['components'][name]
        body_at = c['offset'] + 28
        for row in range(c['indices']):
            resource = struct.unpack_from('<Q', entity, body_at + row*16)[0]
            if resource:
                weapon_resources.add(resource)
    profile['weapon_mapper'] = {'expected_candidates': len(weapon_resources),
        'component_indices': ['ProjectileWeaponComponentData', 'WeaponDataComponentData']}
    resources = {
        'jar5': ('JAR-5 Dominator', '0x80F1A156D9FA1E36', ['ProjectileWeaponComponentData']),
        'bastion': ('Bastion', '0x16474112801385B6', ['HealthComponentData']),
        'maelstrom': ('Maelstrom', '0xB0C9FAF4AF8903F9', ['HealthComponentData']),
        'orbital_laser': ('Orbital Laser', '0xEC3575E7A93793BB', ['OrbitalAbilityComponentData']),
        'shield_relay': ('Shield Relay', '0xED13DDC480EC6910', ['ShieldComponentData', 'HellpodPayloadComponentData']),
        'jump_pack': ('Jump Pack', '0x59C5CA839449B379', ['RechargeComponentData', 'JumppackComponentData']),
        'amr': ('APW-1 Anti-Materiel Rifle', '0x89C5493E08CA4207', ['WeaponDataComponentData']),
    }
    for key, (label, resource, components) in resources.items():
        rid = int(resource, 16)
        owners = [i for i in range(4096) if struct.unpack_from('<Q', map_body, i*32)[0] == rid]
        assert len(owners) == 1
        member_at, count = struct.unpack_from('<QQ', map_body, owners[0]*32+8)
        r = {'label': label, 'resource': resource, 'owner_row': owners[0], 'membership_offset': member_at,
             'membership': map_body[member_at:member_at+count*2].hex(), 'components': {}}
        for name in components:
            c = profile['components'][name]
            body_at = c['offset']+28
            rows = [i for i in range(c['indices']) if struct.unpack_from('<Q', entity, body_at+i*16)[0] == rid]
            assert len(rows) == 1
            record = struct.unpack_from('<I', entity, body_at+rows[0]*16+8)[0]
            record_at = body_at+c['record_offset']+record*c['stride']
            span(record_at, entity[record_at:record_at+c['stride']])
            r['components'][name] = {'row': rows[0], 'record': record}
        profile['resources'][key] = r
    buffers = {}
    setting_sources = [
        ('projectile', 'generated_projectile_settings.dl_bin', 'ProjectileSettings', 272,
         'Jar-5_buff/local_research/dependencies/filediver-reference/datalibrary/'),
        ('damage', 'generated_damage_settings.dl_bin', 'DamageSettings', 76,
         'Jar-5_buff/local_research/dependencies/filediver-reference/datalibrary/'),
        ('arc', 'generated_arc_settings.dl_bin', 'ArcSettings', 104,
         'ShieldRelayImprovements/local_research/dependencies/filediver-current/datalibrary/'),
        ('beam', 'generated_beam_settings.dl_bin', 'BeamSettings', 112,
         'ShieldRelayImprovements/local_research/dependencies/filediver-current/datalibrary/'),
        ('explosion', 'generated_explosion_settings.dl_bin', 'ExplosionSettings', 152,
         'ShieldRelayImprovements/local_research/dependencies/filediver-current/datalibrary/'),
    ]
    for key, name, typename, stride, source_folder in setting_sources:
        raw = source(source_folder + name)
        desc = {'size': len(raw), 'stride': stride, 'groups': []}
        for g in groups(raw):
            item = {'offset': g['root']-24, 'header': raw[g['root']-24:g['root']].hex()}
            if g['type'] == dl_hash(typename):
                off, count = struct.unpack_from('<QQ', raw, g['root'])
                item.update(root=g['root'], row_offset=off, count=count)
            desc['groups'].append(item)
        profile['settings'][key] = desc
        buffers[key] = raw.hex()
    # The current snapshot's decoded status table is pinned by its exact grouped
    # framing. The installed file is encoded and therefore is not used as a
    # fixture source. Snapshot scans validate this descriptor before reading a row.
    profile['settings']['status'] = {
        'size': 13116, 'stride': 152, 'groups': [
            {'offset': 4,
             'header': '4c444c4401000000220b3ec6702e00000100000000000000',
             'root': 28, 'row_offset': 16, 'count': 71},
            {'offset': 11916,
             'header': '4c444c4401000000c09381de980400000100000000000000'},
        ]}
    # Entity delta table (attachment-owned component patches). The live allocation is
    # this file with its five header offsets relocated to absolute pointers.
    deltas = source(str(folder.relative_to(SIBLINGS) / 'generated_entity_deltas.dl_bin').replace(chr(92), '/'))
    assert sha(deltas) == '3FADC7C2475558000F9E8AD30E01D52CAEA481E1633E35674ED2864572694F4E'
    fields = struct.unpack_from('<10Q', deltas, 28)
    profile['entity_deltas'] = {'size': len(deltas), 'header': deltas[:28].hex(), 'header_offset': 28,
        'hashmap_offset': fields[0], 'hashmap_count': fields[1], 'settings_offset': fields[2],
        'settings_count': fields[3], 'component_offset': fields[4], 'component_count': fields[5],
        'delta_offset': fields[6], 'delta_count': fields[7], 'data_offset': fields[8], 'data_count': fields[9]}
    profile['stratagem'] = {'buffer_rva': 0x348E8F8, 'table_rva': 0x37CB600, 'entries': 150,
        'size': 80280, 'groups': 11, 'stride': 400, 'type': 0x30EB6399,
        'version': 1, 'info_type': 0x7BD60854, 'payload_max': 16, 'payload_count': 2,
        'record_type': 22, 'id': 0x880384FF, 'package': '0xFE0DB34AC2B9AC61',
        'resource': resources['shield_relay'][1], 'group': 3, 'row': 1, 'total_records': 149}
    receipt = json.loads(source('ShieldRelayImprovements/research/cooldown-live-confirmation.json'))
    import re
    log = source('ShieldRelayImprovements/' + receipt['ignored_log'])
    assert sha(log) == receipt['log_sha256']
    captures = re.findall(rb'snapshot_[12]_hex=([0-9A-F]+)', log)
    assert len(captures) == 2 and captures[0] == captures[1]
    cooldown = bytes.fromhex(captures[0].decode())
    assert sha(cooldown) == receipt['record_sha256']
    payload_lines = re.findall(rb'^\[ShieldRelayImprovements\] payload=([^\r\n]+)\r?$', log, re.MULTILINE)
    assert len(payload_lines) == 1
    relay_payloads = payload_lines[0].decode().split(',')
    assert len(relay_payloads) == 2 and relay_payloads[0] == receipt['payload']
    laser_evidence=json.loads((SIBLINGS/'StrongerOrbitalLaser/research/laser-evidence.json').read_text())
    orbital=laser_evidence['stratagem']
    stratagem_records={
        'shield_relay': {'source':'saved current live record and payload log',
            'record_hex':cooldown.hex(),'type':receipt['current_type'],'id':int(receipt['id'],16),
            'package':receipt['package'],'payloads':relay_payloads,
            'group':receipt['group_index'],'row':receipt['row_index'],
            'pointer_representation':'relocated_absolute','payload_count_storage':'UINT32'},
        'orbital_laser': {'source':'pinned decoded reference identity; structural record fixture',
            'type':105,'id':orbital['id'],'package':orbital['package'],'payloads':orbital['payload'],
            'group':orbital['group_index'],'row':orbital['index'],
            'pointer_representation':'serialized_group_relative','payload_count_storage':'UINT32'}}
    fixture = {'entity': [{'offset': k, 'hex': v.hex()} for k, v in sorted(spans.items())],
               'buffers': buffers, 'cooldown_record': cooldown.hex(),
               'notice': 'Sparse reference bytes plus saved live cooldown row. Synthetic allocation addresses; not a new live capture.'}
    (ROOT/'schemas/current.lua').write_text('return '+lua(profile)+'\n', encoding='ascii', newline='\n')
    (ROOT/'tests/fixtures').mkdir(parents=True, exist_ok=True)
    (ROOT/'tests/fixtures/reference.json').write_text(json.dumps(fixture, separators=(',', ':'))+'\n', newline='\n')
    (ROOT/'tests/fixtures/stratagem_records.json').write_text(json.dumps(stratagem_records,indent=2)+'\n', newline='\n')
    (ROOT/'docs/provenance.json').write_text(json.dumps(manifest, indent=2)+'\n', newline='\n')
    print('Generated pinned schema profile and sparse fixtures for', len(resources), 'resources')


if __name__ == '__main__':
    main()
