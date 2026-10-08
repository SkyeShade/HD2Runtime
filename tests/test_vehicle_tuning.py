"""Vehicle tuning fields (phase 2 of research/vehicle-mech-components-F5FEE03DCFDB.json): turret motion on mounted
weapons (the sentry turret ids on the same TurretComponent members), Exosuit body rotation and wheeled/tracked steering
on hd2.vehicle(name). Checks the runtime profile and migration view, every field on every applicable vehicle and mount
(baselines are the research values), the refusals, the on-demand table capture, the snapshot overlay report and the
live-test artifact."""
import json
import re
import sys
import unittest

from support import ROOT, run

RESEARCH = json.loads((ROOT / 'research/vehicle-mech-components-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
AUTHORING = RESEARCH['authoring']
OVERLAY = json.loads((ROOT / 'validation/vehicle-tuning-snapshot.json').read_text(encoding='utf-8'))
VEHICLE_SDK = json.loads((ROOT / 'sdk/VehicleAuthoringCapabilities.json').read_text(encoding='utf-8'))
WEAPON_SDK = json.loads((ROOT / 'sdk/VehicleWeaponCapabilities.json').read_text(encoding='utf-8'))
TURRET_IDS = ('turret.yaw_speed', 'turret.pitch_speed', 'turret.pitch_min', 'turret.pitch_max', 'turret.yaw_min',
    'turret.yaw_max')
VEHICLE_IDS = ('rotation.turn_speed', 'rotation.acceleration', 'rotation.deceleration',
    'vehicle.steering_response_speed')
RANGES = {'turret.yaw_speed': (1, 720), 'turret.pitch_speed': (1, 720), 'turret.pitch_min': (-90, 90),
    'turret.pitch_max': (-90, 90), 'turret.yaw_min': (-180, 180), 'turret.yaw_max': (-180, 180),
    'rotation.turn_speed': (1, 720), 'rotation.acceleration': (0, 10000), 'rotation.deceleration': (0, 10000),
    'vehicle.steering_response_speed': (0.05, 50)}


def lua_value(value):
    return repr(value) if isinstance(value, (int, float)) else json.dumps(value)


class VehicleTuningProfileTests(unittest.TestCase):
    def test_the_profile_locates_rotation_and_vehicle_motion(self):
        profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
        fixture = json.loads((ROOT / 'tests/fixtures/reference.json').read_text(encoding='utf-8'))
        spans = {e['offset']: len(e['hex']) // 2 for e in fixture['entity']}
        for name, parts in (('RotationComponentData', ('["index"]=310', '["indices"]=448', '["records"]=225',
                '["record_offset"]=7168', '["stride"]=312')), ('VehicleMotionComponentData', ('["index"]=225',
                '["indices"]=28', '["records"]=14', '["record_offset"]=448', '["stride"]=456'))):
            entry = re.search(r'\["' + name + r'"\]=\{([^}]*)\}', profile).group(1)
            for part in parts:
                self.assertIn(part, entry)
            offset = int(re.search(r'\["offset"\]=(\d+)', entry).group(1))
            record_offset = int(re.search(r'\["record_offset"\]=(\d+)', entry).group(1))
            self.assertEqual(spans[offset - 4], 4 + 28 + record_offset)   # framing and every index row, no records
            self.assertIn("'" + name + "'", (ROOT / 'scripts/import_fixtures.py').read_text(encoding='utf-8'))
        sys.path.insert(0, str(ROOT / 'scripts'))
        from migration import build_view
        self.assertTrue({'RotationComponentData', 'VehicleMotionComponentData', 'TurretComponentData'}
            <= set(build_view.COMPONENTS))
        self.assertGreaterEqual(build_view.EXTRACTOR_VERSION, 7)

    def test_field_declarations_and_constants(self):
        fields = {f['id']: f for f in json.loads((ROOT / 'schemas/entity_fields.json').read_text())['fields']}
        for field_id, component, offset in (('rotation.turn_speed', 'RotationComponentData', 0),
                ('rotation.acceleration', 'RotationComponentData', 4),
                ('rotation.deceleration', 'RotationComponentData', 8),
                ('vehicle.steering_response_speed', 'VehicleMotionComponentData', 364)):
            self.assertEqual((fields[field_id]['component'], fields[field_id]['offset'], fields[field_id]['storage']),
                (component, offset, 'f32'))
        constants = (ROOT / 'domains/constants.lua').read_text(encoding='utf-8')
        for field_id in VEHICLE_IDS + TURRET_IDS:
            domain, name = field_id.split('.', 1)
            self.assertIn('["%s"]="%s"' % (name, field_id), constants)


class VehicleTuningFieldTests(unittest.TestCase):
    def test_every_field_on_every_applicable_target(self):
        checks = []
        for item in AUTHORING['vehicleFields']:
            checks.append("check_vehicle(%s,%s,%s,%s,%s)" % (json.dumps(item['vehicle']), json.dumps(item['field']),
                lua_value(item['baseline']), item['recordIndex'], item['indexRow']))
        for item in AUTHORING['mountFields']:
            checks.append("check_mount(%s,%s,%s,%s,%s)" % (json.dumps(item['weapon']), json.dumps(item['field']),
                lua_value(item['baseline']), item['recordIndex'], item['indexRow']))
        self.assertEqual(len(checks), 49)
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local entity=require('hd2runtime/domains/entity_writes')
local weapons=require('hd2runtime/domains/player_weapon_writes')
local entity_db=require('hd2runtime/domains/entity_authoring')
local weapon_db=require('hd2runtime/domains/vehicle_weapon_authoring')
local RANGES=''' + '{' + ','.join('[%s]={%r,%r}' % (json.dumps(k), lo, hi) for k, (lo, hi) in RANGES.items()) + '}' + r'''
local seen={}
local function check(field,label,id,baseline,record,row,component)
 assert(field,label..' missing')
 assert(math.abs(field.currentDefault-baseline)<1e-6,id..' baseline '..tostring(field.currentDefault))
 assert(field.acknowledgement=='allow_unverified_effect',id..' acknowledgement')
 assert(field.min==RANGES[id][1]and field.max==RANGES[id][2],id..' range')
 assert(field.backing.component==component and field.backing.recordIndex==record and field.backing.indexRow==row
  and field.backing.ownerCount==1 and field.backing.uniqueOwner==true and field.backing.storage=='f32',id..' backing')
end
local function check_vehicle(name,id,baseline,record,row)
 local found
 for _,field in ipairs(entity_db.vehicles[name].fields)do if field.semanticFieldId==id then found=field end end
 check(found,name..' '..id,id,baseline,record,row,id:match('^rotation')and'RotationComponentData'or'VehicleMotionComponentData')
 assert(found.target.path=='entity'and not found.shared,id..' target')
 assert(found.notices and found.notices[1].kind=='lifecycle',id..' lifecycle notice')
 local spec=entity.validate_patch{id='t',target=hd2.vehicle(name),field=id,expect=baseline,value=baseline,
  allow_unverified_effect=true}
 assert(spec.changes[1].descriptor==found)
 local described=false
 for _,f in ipairs(hd2.vehicle(name):describe().fields)do if f.semanticFieldId==id then described=true end end
 assert(described,name..' describe() lacks '..id)
 seen[#seen+1]=name
end
local function check_mount(key,id,baseline,record,row)
 local found
 for _,field in ipairs(weapon_db.weapons[key].fields)do if field.semanticFieldId==id then found=field end end
 check(found,key..' '..id,id,baseline,record,row,'TurretComponentData')
 assert(found.writeScope=='weapon_local'and not found.affectsMultipleWeapons and found.lifecycle,id..' scope')
 local vehicle,label=key:match('^(.-) / (.+)$')
 local spec=weapons.validate_patch{id='t',target=hd2.vehicle(vehicle):weapon(label),field=id,expect=baseline,
  value=baseline,allow_unverified_effect=true}
 assert(spec.changes[1].descriptor==found)
 seen[#seen+1]=key
end
''' + '\n'.join(checks) + r'''
return tostring(#seen)
'''), b'49')

    def test_refusals(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local entity=require('hd2runtime/domains/entity_writes')
local weapons=require('hd2runtime/domains/player_weapon_writes')
local F=hd2.fields
local function refused(needle,fn,...)
 local ok,why=pcall(fn,...)
 assert(not ok and tostring(why):find(needle,1,true),tostring(why))
end
local function vehicle(name,field,expect,value,ack)
 return entity.validate_patch{id='t',target=hd2.vehicle(name),field=field,expect=expect,value=value,
  allow_unverified_effect=ack}
end
local function weapon(name,mount,field,expect,value,ack)
 return weapons.validate_patch{id='t',target=hd2.vehicle(name):weapon(mount),field=field,expect=expect,value=value,
  allow_unverified_effect=ack}
end
-- Ranges: every boundary is accepted, every value past it refused.
for _,case in ipairs({{F.rotation.turn_speed,65,1,720,0.99,720.5},{F.rotation.acceleration,0,0,10000,-0.01,10001},
  {F.rotation.deceleration,0,0,10000,-1,10000.5}})do
 vehicle('EXO-45 Patriot Exosuit',case[1],case[2],case[3],true);vehicle('EXO-45 Patriot Exosuit',case[1],case[2],case[4],true)
 refused('reviewed range',vehicle,'EXO-45 Patriot Exosuit',case[1],case[2],case[5],true)
 refused('reviewed range',vehicle,'EXO-45 Patriot Exosuit',case[1],case[2],case[6],true)
end
vehicle('M-102 Gunner FRV',F.vehicle.steering_response_speed,3.1,0.05,true)
vehicle('M-102 Gunner FRV',F.vehicle.steering_response_speed,3.1,50,true)
refused('reviewed range',vehicle,'M-102 Gunner FRV',F.vehicle.steering_response_speed,3.1,0.04,true)
refused('reviewed range',vehicle,'M-102 Gunner FRV',F.vehicle.steering_response_speed,3.1,50.5,true)
weapon('M-103 Supply FRV','gun',F.turret.yaw_speed,130,1,true);weapon('M-103 Supply FRV','gun',F.turret.yaw_speed,130,720,true)
refused('reviewed minimum',weapon,'M-103 Supply FRV','gun',F.turret.yaw_speed,130,0.5,true)
refused('reviewed maximum',weapon,'M-103 Supply FRV','gun',F.turret.pitch_speed,90,721,true)
refused('reviewed minimum',weapon,'M-103 Supply FRV','gun',F.turret.pitch_min,-60,-91,true)
refused('reviewed maximum',weapon,'M-103 Supply FRV','gun',F.turret.yaw_max,180,181,true)
-- Non-finite values.
for _,bad in ipairs({0/0,math.huge,-math.huge})do
 refused('finite',vehicle,'EXO-45 Patriot Exosuit',F.rotation.turn_speed,65,bad,true)
 refused('finite',vehicle,'M-102 Gunner FRV',F.vehicle.steering_response_speed,3.1,bad,true)
 refused('finite',weapon,'GATER Oil Rig','turret',F.turret.yaw_speed,60,bad,true)
end
-- Acknowledgement and stale expect.
refused('allow_unverified_effect',vehicle,'EXO-45 Patriot Exosuit',F.rotation.turn_speed,65,20,nil)
refused('allow_unverified_effect',vehicle,'M-102 Gunner FRV',F.vehicle.steering_response_speed,3.1,0.5,nil)
refused('allow_unverified_effect',weapon,'M-103 Supply FRV','gun',F.turret.yaw_speed,130,30,nil)
refused('allow_unverified_effect',weapon,'TD-220 Bastion MK XVI','attach_tank_gun',F.turret.yaw_min,-20,-5,nil)
refused('expect differs',vehicle,'EXO-45 Patriot Exosuit',F.rotation.turn_speed,60,20,true)
refused('expect differs',weapon,'TD-220 Bastion MK XVI','attach_tank_gun_mg',F.turret.yaw_speed,30,8,true)
-- Non-applicable targets: mounts without a turret record, vehicles without the component.
for _,mount in ipairs({{'M-102 Gunner FRV','gun'},{'FRV (Super Earth variant)','gun'},{'M-104 Incinerator FRV','gun'},
  {'EXO-45 Patriot Exosuit','left_gun'},{'EXO-45 Patriot Exosuit','right_gun'},{'EXO-49 Emancipator Exosuit','left_gun'},
  {'EXO-51 Lumberer Exosuit','right_gun'},{'EXO-55 Breakthrough Exosuit','right_gun'},{'TD-110 Maelstrom',2}})do
 refused('not exposed',weapon,mount[1],mount[2],F.turret.yaw_speed,35,30,true)
end
for _,name in ipairs({'M-102 Gunner FRV','M-103 Supply FRV','GATER Oil Rig','TD-220 Bastion MK XVI','TD-110 Maelstrom'})do
 refused('not exposed',vehicle,name,F.rotation.turn_speed,65,20,true)
end
for _,name in ipairs({'EXO-45 Patriot Exosuit','EXO-49 Emancipator Exosuit','EXO-51 Lumberer Exosuit',
  'EXO-55 Breakthrough Exosuit'})do
 refused('not exposed',vehicle,name,F.vehicle.steering_response_speed,3.1,0.5,true)
end
-- Limit order: a crossing patch is refused; the same values written together are accepted.
refused('TURRET_LIMIT_ORDER',weapon,'TD-220 Bastion MK XVI','attach_tank_gun',F.turret.yaw_min,-20,20,true)
refused('TURRET_LIMIT_ORDER',weapon,'TD-220 Bastion MK XVI','attach_tank_gun',F.turret.pitch_max,25,-3,true)
local cannon=hd2.vehicle('TD-220 Bastion MK XVI'):weapon('attach_tank_gun')
weapons.validate_transaction{id='t',target=cannon,allow_unverified_effect=true,changes={
 {field=F.turret.yaw_min,expect=-20,value=30},{field=F.turret.yaw_max,expect=20,value=60}}}
refused('TURRET_LIMIT_ORDER',weapons.validate_transaction,{id='t',target=cannon,allow_unverified_effect=true,changes={
 {field=F.turret.pitch_min,expect=-3,value=10},{field=F.turret.pitch_max,expect=25,value=10}}})
-- One Rotation record per transaction: turn speed and acceleration together.
entity.validate_transaction{id='t',target=hd2.vehicle('EXO-49 Emancipator Exosuit'),allow_unverified_effect=true,
 changes={{field=F.rotation.turn_speed,expect=65,value=30},{field=F.rotation.acceleration,expect=0,value=30}}}
return 'ok'
'''), b'ok')

    def test_tables_are_captured_only_by_their_own_writes(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local entity=require('hd2runtime/domains/entity_writes')
local weapons=require('hd2runtime/domains/player_weapon_writes')
local function has(list,name)for _,item in ipairs(list)do if item==name then return true end end;return false end
local health=entity.validate_patch{id='h',target=hd2.vehicle('TD-220 Bastion MK XVI'),field=hd2.fields.entity.health,
 expect=8000,value=8000}
local names=entity.names_for({health})
assert(not has(names,'RotationComponentData')and not has(names,'VehicleMotionComponentData'))
local turn=entity.validate_patch{id='r',target=hd2.vehicle('EXO-45 Patriot Exosuit'),field=hd2.fields.rotation.turn_speed,
 expect=65,value=20,allow_unverified_effect=true}
names=entity.names_for({health,turn})
assert(has(names,'RotationComponentData')and not has(names,'VehicleMotionComponentData'))
local capacity=weapons.validate_patch{id='c',target=hd2.vehicle('M-103 Supply FRV'):weapon('gun'),
 field=hd2.fields.weapon.capacity,expect=120,value=120}
assert(not has(weapons.with_turret({'WeaponDataComponentData'},{capacity}),'TurretComponentData'))
local yaw=weapons.validate_patch{id='y',target=hd2.vehicle('M-103 Supply FRV'):weapon('gun'),
 field=hd2.fields.turret.yaw_speed,expect=130,value=30,allow_unverified_effect=true}
assert(has(weapons.with_turret({'WeaponDataComponentData'},{capacity,yaw}),'TurretComponentData'))
return 'ok'
'''), b'ok')

    def test_public_catalogs_publish_range_lifecycle_and_no_native_identity(self):
        vehicle_fields = [f for f in VEHICLE_SDK['fieldInstances'] if f['semanticFieldId'] in VEHICLE_IDS]
        self.assertEqual(len(vehicle_fields), 19)
        for field in vehicle_fields:
            self.assertEqual((field['acknowledgement'], field['evidence']['tier']),
                ('allow_unverified_effect', 'native_consumer_proven'))
            self.assertTrue(field['lifecycle'] and field['rangeReason'] and field['effect']['activeSourceProven'])
            self.assertEqual((field['min'], field['max']), RANGES[field['semanticFieldId']])
        turret = [i for i in WEAPON_SDK['fieldInstances'] if i['semanticFieldId'] in TURRET_IDS]
        self.assertEqual(len(turret), 30)
        self.assertEqual({i['weapon'] for i in turret}, {'M-103 Supply FRV / gun', 'GATER Oil Rig / turret',
            'TD-220 Bastion MK XVI / attach_tank_gun', 'TD-220 Bastion MK XVI / attach_tank_gun_mg',
            'TD-110 Maelstrom / attach_tank_gun'})
        for instance in turret:
            self.assertEqual((instance['acknowledgement'], instance['scope'], instance['allowSharedRequired']),
                ('allow_unverified_effect', 'weapon_local', False))
            self.assertEqual((instance['min'], instance['max']), RANGES[instance['semanticFieldId']])
            self.assertTrue(instance['lifecycle'])
        immediate = {i['semanticFieldId'] for i in turret if 'every turret update' in i['lifecycle']}
        self.assertEqual(immediate, {'turret.pitch_min', 'turret.pitch_max', 'turret.yaw_min', 'turret.yaw_max'})
        text = json.dumps(turret + vehicle_fields)
        self.assertNotRegex(text, r'0x[0-9A-Fa-f]{8,}')

    def test_the_snapshot_overlay_writes_exactly_the_targets(self):
        self.assertEqual((OVERLAY['status'], OVERLAY['fixtureFallback'], OVERLAY['instances'], OVERLAY['vehicles'],
            OVERLAY['mounts']), ('VALIDATED', 'disabled', 49, 11, 5))
        trips = OVERLAY['roundTrips']
        self.assertEqual(set(trips), {'m103_turret_yaw_speed', 'patriot_turn_speed', 'frv_steering_response_speed',
            'bastion_cannon_yaw_limits'})
        for key, trip in trips.items():
            self.assertTrue(trip['protectionRestored'] and trip['restored'], key)
            self.assertEqual(trip['protectionChanges'], 2, key)
            self.assertLessEqual(trip['tableBytesChanged'], 4 * trip['writes'], key)
            self.assertGreaterEqual(trip['tableBytesChanged'], trip['writes'], key)
            # The table contributes its index rows and exactly one record to the guarded context.
            self.assertEqual((trip['tableIndexContextBytes'], trip['tableRecordContextBytes']),
                (trip['tableIndexBytes'], trip['recordStride']), key)
            self.assertLess(trip['tableRecordContextBytes'], trip['tableRecordBytes'], key)
            self.assertLess(trip['readAllowance'], trip['readCeiling'], key)
        self.assertEqual((trips['m103_turret_yaw_speed']['targetOffsetsInRecord'], trips['m103_turret_yaw_speed']['written']),
            ([12], [30]))
        self.assertEqual((trips['patriot_turn_speed']['targetOffsetsInRecord'], trips['patriot_turn_speed']['written']),
            ([0], [20]))
        self.assertEqual(trips['frv_steering_response_speed']['targetOffsetsInRecord'], [364])
        self.assertAlmostEqual(trips['frv_steering_response_speed']['written'][0], 0.5)
        self.assertEqual((trips['bastion_cannon_yaw_limits']['writes'],
            trips['bastion_cannon_yaw_limits']['targetOffsetsInRecord']), (2, [28, 32]))
        self.assertFalse(OVERLAY['unrelatedWritesCaptureTuningTables'])
        rejections = OVERLAY['rejections']
        for label in ('not applicable: M-102 Gunner FRV / gun', 'not applicable: M-104 Incinerator FRV / gun',
                'not applicable: EXO-45 Patriot Exosuit / left_gun', 'not applicable: FRV body rotation',
                'not applicable: Exosuit steering', 'crossing yaw limits', 'value NaN', 'value inf', 'steering NaN',
                'turret missing acknowledgement', 'rotation missing acknowledgement',
                'steering missing acknowledgement', 'stale expect'):
            self.assertIn(label, rejections)
        for kind in ('turret', 'rotation', 'steering'):
            self.assertIn('ownership', rejections[kind + ': index row moved'])
            self.assertTrue(rejections[kind + ': third-party value'].startswith('CONFLICT'))


class VehicleTuningArtifactTests(unittest.TestCase):
    def test_the_live_test_artifact(self):
        project = ROOT / 'examples/projects/VehicleTuningTest'
        source = (project / 'src/addon.lua').read_text(encoding='utf-8')
        manifest = json.loads((project / 'hd2runtime.json').read_text(encoding='utf-8'))
        self.assertEqual((project / 'VERSION').read_text().strip(), '0.1.0')
        self.assertEqual(manifest['requires']['hd2runtime']['min_version'], '0.30.0')
        self.assertIn('mod_options_menu', manifest['optional'])
        self.assertIn("local BANNER='VEHICLE TUNING 0.1.0 BUILD'", source)
        for line in ("values={130,30}", "values={35,8}", "values={-20,-5}", "values={20,5}", "values={25,45}",
                "values={65,20}", "values={0,30}", "values={3.1,0.5}",
                "field=F.turret.yaw_speed,expect=130,value=m103_traverse",
                "field=F.vehicle.steering_response_speed,expect=3.1,value=frv_steering",
                "{field=F.rotation.turn_speed,expect=65,value=patriot_turn}"):
            self.assertIn(line, source)
        self.assertEqual(source.count('allow_unverified_effect=true'), 5)
        self.assertFalse(list(project.glob('build/*.zip')), 'no release ZIPs for the live-test artifact')
        readme = (project / 'README.md').read_text(encoding='utf-8')
        for text in ('call in a **new** vehicle', 'nothing: a deployed vehicle follows at once',
                '`VEHICLE TUNING 0.1.0 BUILD: loaded;'):
            self.assertIn(text, readme)
        packaged = (ROOT / 'scripts/validate_packaged_runtime.py').read_text(encoding='utf-8')
        self.assertIn("'example-vehicle-tuning-test': {'menu': MENU_STUB, 'watches': 5", packaged)
        report = json.loads((ROOT / 'validation/example-projects.json').read_text(encoding='utf-8'))
        result = report['results']['VehicleTuningTest']
        self.assertEqual((result['status'], result['requiredMinVersion'], len(result['operations'])),
            ('VALIDATED', '0.30.0', 5))

    def test_docs_state_the_lifecycle(self):
        authoring = (ROOT / 'docs/vehicle-authoring.md').read_text(encoding='utf-8')
        weapons = (ROOT / 'docs/vehicle-weapons.md').read_text(encoding='utf-8')
        for text in ('hd2.fields.rotation.turn_speed', 'hd2.fields.vehicle.steering_response_speed',
                'Read every frame', 'Copied when the Exosuit spawns'):
            self.assertIn(text, authoring)
        for text in ('## Turret motion', 'Re-read every turret update', 'Copied into the turret when the vehicle is created',
                'TURRET_LIMIT_ORDER'):
            self.assertIn(text, weapons)
        self.assertEqual((ROOT / 'sdk/docs/vehicle-weapons.md').read_text(encoding='utf-8'), weapons)
        self.assertEqual((ROOT / 'sdk/docs/vehicle-authoring.md').read_text(encoding='utf-8'), authoring)


if __name__ == '__main__':
    unittest.main()
