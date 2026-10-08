"""Type-wide Helldiver fields (hd2.helldiver(); docs/helldiver-fields.md): movement speeds and stamina in the
avatar_helldiver AvatarComponentData record 0 and the six body zones in its HealthComponentData record 76, from
research/avatar-fields-F5FEE03DCFDB.json. Checks the generated data against the research, the API and its refusals,
the private-copy report (offline, on a synthetic avatar manager), the snapshot overlay report on all seven retained
snapshots, the SDK, docs and packaged-scenario wiring."""
import json
import re
import unittest

from support import ROOT, run

RESEARCH = json.loads((ROOT / 'research/avatar-fields-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
SCHEMA = json.loads((ROOT / 'schemas/helldiver_fields.json').read_text(encoding='utf-8'))
CATALOG = json.loads((ROOT / 'sdk/HelldiverFieldCapabilities.json').read_text(encoding='utf-8'))
OVERLAY = json.loads((ROOT / 'validation/helldiver-fields-snapshot.json').read_text(encoding='utf-8'))
ZONES = ['head', 'body', 'arm_left', 'arm_right', 'leg_left', 'leg_right']
SHIP = ('F5FEE03DCFDB-20260926T222226Z.hd2snap', 'F5FEE03DCFDB-20260927T155654Z.hd2snap',
    'F5FEE03DCFDB-20260927T160033Z.hd2snap')


class HelldiverFieldDataTests(unittest.TestCase):
    def test_the_research_is_read_only_and_pinned_in_every_snapshot(self):
        self.assertEqual(RESEARCH['source']['writes'], 0)
        self.assertEqual((RESEARCH['pinCount'], RESEARCH['pinsIdenticalInAllSnapshots']), (146, True))
        self.assertEqual(len(RESEARCH['source']['snapshots']), 7)

    def test_the_domain_is_generated_from_the_research(self):
        import generate_helldiver_fields
        self.assertEqual(generate_helldiver_fields.generate(check=True), [])

    def test_every_exposed_field_is_a_live_or_spawn_research_member(self):
        research = {(f['record'], f.get('zone'), f['offset']): f for f in RESEARCH['fields']}
        instances = CATALOG['fieldInstances']
        self.assertEqual((CATALOG['summary']['fields'], CATALOG['summary']['instances']), (27, 21 + 1 + 5 * 6))
        avatar = [i for i in instances if i['semanticFieldId'].startswith('helldiver.')]
        self.assertEqual(len(avatar), 21)
        for item in instances:
            self.assertEqual(item['acknowledgements'], ['allow_shared', 'allow_unverified_effect'])
            self.assertTrue(item['shared'] and item['allowSharedRequired'] and not item['liveTested'])
            self.assertIn(item['grade'], ('CONFIRMED', 'STRONG'))
            self.assertIn(item['lifecycle'], ('live', 'spawn'))
        exposed = {(d['record'], d['offset']) for d in SCHEMA['fields'] if 'offset' in d}
        # The UNKNOWN members (+56 jog drain, +84 vault cost) and the dormant zone explosive share are not exposed.
        self.assertNotIn(('avatar', 56), exposed)
        self.assertNotIn(('avatar', 84), exposed)
        self.assertFalse(any(d.get('zoneOffset') == 324 for d in SCHEMA['fields']))
        self.assertEqual({(n['member'], n['reason']) for n in CATALOG['notExposed']}, {
            ('jog_stamina_decay_duration', 'UNKNOWN'), ('stamina_cost_vault', 'UNKNOWN'),
            ('explosive_damage_percentage', 'DORMANT')})
        # STRONG-only members are exposed like the others, and published as STRONG.
        grades = {i['semanticFieldId']: i['grade'] for i in avatar}
        for field_id in ('helldiver.speed.direction_factor', 'helldiver.speed.aim', 'helldiver.speed.walk',
                'helldiver.speed.prone', 'helldiver.speed.swim', 'helldiver.speed.crouch_aim',
                'helldiver.speed.crouch_walk'):
            self.assertEqual(grades[field_id], 'STRONG', field_id)
        for field_id in ('helldiver.speed.jog', 'helldiver.speed.sprint', 'helldiver.speed.sprint_exhausted',
                'helldiver.speed.crouch_jog', 'helldiver.speed.crouch_sprint', 'helldiver.stamina.sprint_duration',
                'helldiver.stamina.recover_delay', 'helldiver.stamina.cost_slide'):
            self.assertEqual(grades[field_id], 'CONFIRMED', field_id)
        # Offsets and vanilla values are the research's.
        for definition in SCHEMA['fields']:
            if 'offset' in definition:
                record = 'AvatarComponentData#0' if definition['record'] == 'avatar' else 'HealthComponentData#76'
                zone = None if record.startswith('Avatar') else 'default'
                self.assertIn((record, zone, definition['offset']), research, definition['id'])
        values = {(i['semanticFieldId'], i['target'].get('zone')): (i['currentDefault'], i.get('min'), i.get('max'))
            for i in instances}
        self.assertEqual(values[('helldiver.speed.jog', None)], (3.2, 0, 10))
        self.assertEqual(values[('helldiver.speed.sprint', None)], (5.5, 0, 10))
        self.assertEqual(values[('helldiver.speed.sprint_exhausted', None)], (4.25, 0, 10))
        self.assertEqual(values[('helldiver.stamina.sprint_duration', None)], (23.0, 1, 3600))
        self.assertEqual(values[('helldiver.stamina.recover_time_standing', None)], (7.0, 0.5, 600))
        self.assertEqual(values[('helldiver.stamina.recover_delay', None)], (1.5, 0, 60))
        self.assertEqual(values[('helldiver.stamina.cost_jump', None)], (0.2, 0, 1))
        self.assertEqual(values[('entity.explosive_damage_percentage', None)], (0.5, 0, 10))
        self.assertEqual([values[('zone.health', z)][0] for z in ZONES], [85, 60, 35, 35, 45, 45])
        self.assertEqual([values[('zone.affects_main_health', z)][0] for z in ZONES], [1.5, 1.0, 0.85, 0.85, 0.85, 0.85])
        self.assertEqual({values[('zone.damage_multiplier', z)][0] for z in ZONES}, {'normal'})
        lifecycle = {(i['semanticFieldId'], i['target'].get('zone')): i['lifecycle'] for i in instances}
        self.assertEqual(lifecycle[('zone.health', 'head')], 'spawn')
        self.assertEqual(lifecycle[('zone.damage_multiplier', 'head')], 'live')
        shadow = {i['semanticFieldId']: i['shadowedByPrivateCopy'] for i in instances}
        self.assertEqual((shadow['helldiver.speed.jog'], shadow['zone.damage_multiplier'],
            shadow['zone.damage_multiplier_dps'], shadow['zone.durable_resistance'], shadow['zone.affects_main_health'],
            shadow['zone.health'], shadow['entity.explosive_damage_percentage']),
            ('avatar', None, None, None, 'health', 'health', 'health'))
        self.assertEqual(CATALOG['enums']['damage_multiplier']['factors'],
            {'none': 0.0, 'critical': 1.5, 'normal': 1.0, 'reduced': 0.75, 'symbolic': 0.25})
        self.assertNotRegex(json.dumps(CATALOG), r'0x[0-9A-Fa-f]{8,}')

    def test_the_generated_identity_is_the_research_identity(self):
        text = (ROOT / 'domains/helldiver_fields.lua').read_text(encoding='utf-8')
        avatar = RESEARCH['identity']['avatarComponent']
        self.assertIn('["resource"]="0x4D1C334D294DFA97"', text)
        self.assertIn('["avatar"]={["component"]="AvatarComponentData",["recordIndex"]=0,["indexRow"]=1,'
            '["ownerCount"]=1,["uniqueOwner"]=true', text)
        self.assertIn('["health"]={["component"]="HealthComponentData",["recordIndex"]=76,["indexRow"]=443,'
            '["ownerCount"]=1,["uniqueOwner"]=true}', text)
        self.assertIn('["offset"]=%d,["header"]="4c20ef404c444c4401000000' % avatar['frameOffset'], text)
        self.assertIn('["index"]=232,["indices"]=2,["records"]=2,["record_offset"]=32,["stride"]=852', text)
        # Zone name hashes: the 32-bit thin hash of each zone name, as the zone stores it at +96.
        self.assertEqual(re.findall(r'\["id"\]="(\w+)",\["index"\]=\d,\["nameHash"\]', text), ZONES)
        # The schema ids are the SDK constants (hd2.fields.helldiver.*, the zone multipliers).
        constants = (ROOT / 'domains/constants.lua').read_text(encoding='utf-8')
        for line in ('["speed_jog"]="helldiver.speed.jog"', '["stamina_recover_delay"]="helldiver.stamina.recover_delay"',
                '["damage_multiplier"]="zone.damage_multiplier"', '["damage_multiplier_dps"]="zone.damage_multiplier_dps"'):
            self.assertIn(line, constants)


class HelldiverApiTests(unittest.TestCase):
    def test_targets_descriptors_and_describe(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local W=require('hd2runtime/domains/helldiver_writes')
local F=hd2.fields
local h=hd2.helldiver()
assert(h.resource=='helldiver'and h.path=='entity'and hd2.helldiver('avatar_helldiver').path=='entity')
assert(not pcall(hd2.helldiver,'Charger'))
local d=h:describe()
assert(#d.fields==22 and #d.zones==6 and d.liveTested==false and d.speedCap==10)
assert(d.acknowledgements[1]=='allow_shared'and d.acknowledgements[2]=='allow_unverified_effect')
local zones=h:zones()
assert(#zones==6 and zones[1].zone=='head'and zones[6].zone=='leg_right')
assert(h:zone(0).zone=='head'and h:damage_zone('leg_left').zone=='leg_left')
local head=h:zone('head'):describe()
assert(#head.fields==5 and head.fields[1].semanticFieldId=='zone.damage_multiplier')
assert(head.fields[1].allowedValues[1]=='none'and head.fields[1].allowedValues[5]=='symbolic')
assert(head.fields[2].allowedValues[1]=='inherit')
local ok,why=pcall(h.zone,h,'tail')
assert(not ok and tostring(why):find('UNKNOWN_ZONE',1,true),tostring(why))
-- Every field: shared, both acknowledgements; a write with both is accepted at every boundary.
local spec=W.validate_transaction{id='t',target=h,allow_shared=true,allow_unverified_effect=true,changes={
 {field=F.helldiver.speed_jog,expect=3.2,value=10},{field=F.helldiver.speed_sprint,expect=5.5,value=0},
 {field=F.helldiver.stamina_sprint_duration,expect=23,value=1},{field=F.helldiver.stamina_recover_delay,expect=1.5,value=60},
 {field=F.helldiver.stamina_cost_jump,expect=0.2,value=1},{field=F.entity.explosive_damage_percentage,expect=0.5,value=10}}}
assert(spec.kind=='helldiver'and#spec.changes==6)
for _,change in ipairs(spec.changes)do
 assert(change.descriptor.shared==true and change.descriptor.acknowledgement=='allow_unverified_effect')
 assert(change.descriptor.backing.uniqueOwner==true and change.descriptor.backing.ownerCount==1)
end
assert(spec.changes[1].descriptor.backing.component=='AvatarComponentData'and spec.changes[1].descriptor.backing.offset==16)
assert(spec.changes[6].descriptor.backing.component=='HealthComponentData'and spec.changes[6].descriptor.backing.offset==388)
-- Zone fields: names for the multipliers (case-insensitive), the zone name hash as a guard, 520 + i*552 + member.
local z=W.validate_patch{id='t',target=h:zone('arm_right'),field=F.zone.damage_multiplier,expect='Normal',value='none',
 allow_shared=true,allow_unverified_effect=true}
local c=z.changes[1]
assert(c.expect=='normal'and c.value=='none'and c.desired=='\0\0\0\0'and c.expected=='\2\0\0\0')
assert(c.descriptor.backing.offset==520+3*552+196 and c.descriptor.backing.guards[1].offset==520+3*552+96)
assert(c.descriptor.backing.guards[1].hex=='f5baf2b6')
local dps=W.validate_patch{id='t',target=h:zone('body'),field=F.zone.damage_multiplier_dps,expect='normal',value='inherit',
 allow_shared=true,allow_unverified_effect=true}
assert(dps.changes[1].desired=='\0\0\0\0')
local health=W.validate_patch{id='t',target=h:zone('leg_left'),field=F.zone.health,expect=45,value=100000,
 allow_shared=true,allow_unverified_effect=true}
assert(health.changes[1].descriptor.backing.storage=='i32')
-- The write domain and the diagnostics know the target.
local domains=require('hd2runtime/domains/write_domains')
assert(domains.for_resource('helldiver')==W and domains.for_kind('helldiver')==W and domains.key_for_kind('helldiver')=='helldiver')
assert(require('hd2runtime/runtime/diagnostics').describe('patch',{target=h,field=F.helldiver.speed_jog})
 =='helldiver Helldiver entity: helldiver.speed.jog')
return 'ok'
''').decode().splitlines()[0], 'ok')

    def test_refusals(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local W=require('hd2runtime/domains/helldiver_writes')
local F=hd2.fields
local h=hd2.helldiver()
local function refused(needle,request)
 request.id=request.id or't'
 local ok,why=pcall(W.validate_patch,request)
 assert(not ok,'accepted: '..tostring(request.field)..' '..tostring(request.value))
 assert(tostring(why):find(needle,1,true),needle..' / '..tostring(why))
end
local both={allow_shared=true,allow_unverified_effect=true}
local function req(target,field,expect,value,acks)
 local r={target=target,field=field,expect=expect,value=value}
 for k,v in pairs(acks or both)do r[k]=v end
 return r
end
-- Acknowledgements: both are always required, on every field.
for _,case in ipairs({{h,F.helldiver.speed_jog,3.2,4},{h,F.helldiver.speed_aim,2,3},{h,F.entity.explosive_damage_percentage,0.5,1},
  {h:zone('head'),F.zone.damage_multiplier,'normal','none'},{h:zone('body'),F.zone.health,60,90}})do
 refused('allow_shared=true',req(case[1],case[2],case[3],case[4],{allow_unverified_effect=true}))
 refused('allow_unverified_effect=true',req(case[1],case[2],case[3],case[4],{allow_shared=true}))
end
-- Ranges and value kinds.
refused('reviewed range [0, 10]',req(h,F.helldiver.speed_sprint,5.5,10.01))
refused('reviewed range [0, 10]',req(h,F.helldiver.speed_jog,3.2,-0.5))
refused('reviewed range [1, 3600]',req(h,F.helldiver.stamina_sprint_duration,23,0))
refused('reviewed range [0.5, 600]',req(h,F.helldiver.stamina_recover_time_prone,5,0.25))
refused('reviewed range [0, 60]',req(h,F.helldiver.stamina_recover_delay,1.5,61))
refused('reviewed range [0, 1]',req(h,F.helldiver.stamina_cost_dodge,0.1,1.5))
refused('reviewed range [0, 1]',req(h:zone('head'),F.zone.durable_resistance,0,2))
refused('reviewed range [0, 10]',req(h:zone('head'),F.zone.affects_main_health,1.5,11))
refused('reviewed range [1, 100000]',req(h:zone('head'),F.zone.health,85,0))
refused('integer Helldiver field',req(h:zone('head'),F.zone.health,85,90.5))
for _,bad in ipairs({0/0,math.huge,-math.huge})do refused('finite',req(h,F.helldiver.speed_jog,3.2,bad))end
refused('expect differs',req(h,F.helldiver.speed_jog,3.0,4))
refused('expect differs',req(h:zone('head'),F.zone.damage_multiplier,'reduced','none'))
-- Damage multipliers by name only; 'none' is not a damage-over-time name.
refused('UNKNOWN_DAMAGE_MULTIPLIER',req(h:zone('head'),F.zone.damage_multiplier,'normal','armoured'))
refused('UNKNOWN_DAMAGE_MULTIPLIER',req(h:zone('head'),F.zone.damage_multiplier,'normal',3))
refused('UNKNOWN_DAMAGE_MULTIPLIER',req(h:zone('head'),F.zone.damage_multiplier,2,'none'))
refused('name it "inherit"',req(h:zone('head'),F.zone.damage_multiplier_dps,'normal','none'))
-- Targets: unknown zones, zone fields on the type and type fields on a zone, foreign fields and identities.
refused('UNKNOWN_ZONE',req({resource='helldiver',helldiver='Helldiver',path='damage_zone',zone='tail'},F.zone.health,85,90))
refused('is a damage zone field',req(h,F.zone.health,85,90))
refused('is not a damage zone field',req(h:zone('head'),F.helldiver.speed_jog,3.2,4))
refused('not exposed for the Helldiver',req(h,'helldiver.stamina.jog_decay',300,100))
refused('not exposed for the Helldiver',req(h:zone('head'),F.zone.armor,0,5))
refused('not exposed for the Helldiver',req(h:zone('head'),F.zone.explosive_damage_percentage,0.5,1))
refused('unsupported Helldiver target identity',req({resource='helldiver',helldiver='Helldiver',path='entity',enemy='x'},
 F.helldiver.speed_jog,3.2,4))
refused('unknown Helldiver type',req({resource='helldiver',helldiver='Charger',path='entity'},F.helldiver.speed_jog,3.2,4))
refused('unsupported option',{target=h,field=F.helldiver.speed_jog,expect=3.2,value=4,allow_shared=true,
 allow_unverified_effect=true,allow_unverified_reference=true})
local ok,why=pcall(W.validate_transaction,{id='t',target=h,allow_shared=true,allow_unverified_effect=true,changes={
 {field=F.helldiver.speed_jog,expect=3.2,value=4},{field=F.helldiver.speed_jog,expect=3.2,value=5}}})
assert(not ok and tostring(why):find('twice',1,true),tostring(why))
-- The public entry points refuse the same way (a helper never adds an acknowledgement).
local watch=hd2.patch({id='no-ack',target=h,field=F.helldiver.speed_jog,expect=3.2,value=4})
assert(watch==nil or watch.status=='rejected',tostring(watch and watch.status))
return 'ok'
''').decode().splitlines()[0], 'ok')

    def test_the_private_copy_report_on_a_synthetic_avatar_manager(self):
        # A synthetic game image: the pinned layout instructions, the avatar manager with one simulated avatar
        # (entity 249) and its private-copy map. No natives are called; the world is only a reader.
        self.assertEqual(run(r'''
local W=require('hd2runtime/domains/helldiver_writes')
local D=require('hd2runtime/domains/helldiver_fields')
local b=require('hd2runtime/core/bytes')
local hd2=require('hd2runtime/api/hd2')
local P=D.privateCopies
local G,MANAGER,DESCRIPTOR,BUCKETS=0x10000000,0x20000000,0x30000000,0x40000000
local function u64(v)return b.encode(v%4294967296,'u32')..b.encode(math.floor(v/4294967296),'u32')end
local function make(copy,tamper)
 local segments={}
 local function put(at,bytes)segments[#segments+1]={at=at,bytes=bytes}end
 for index,pin in ipairs(P.pins)do
  local bytes=b.unhex(pin.hex)
  if tamper and index==1 then bytes='\204'..bytes:sub(2)end
  put(G+pin.rva,bytes)
 end
 put(G+P.global,u64(MANAGER))
 put(MANAGER+P.simulated,b.encode(1,'u32'))
 put(MANAGER+P.descriptors,u64(DESCRIPTOR))
 put(DESCRIPTOR,b.unhex('97fa4d294d331c4d')..b.encode(249,'u32')..b.encode(0,'u32')..b.encode(0,'u32')..b.encode(1,'u32'))
 put(MANAGER+P.copyMap,u64(BUCKETS)..b.encode(4,'u32')..b.encode(0xFFFFFFFF,'u32')..b.encode(1,'u32'))
 local slots={}
 for slot=0,3 do slots[slot+1]=b.encode(0xFFFFFFFF,'u32')..b.encode(0,'u32')end
 if copy then slots[(249%4)+1]=b.encode(249,'u32')..b.encode(0,'u32')end
 put(BUCKETS,table.concat(slots))
 local view={}
 function view.read(at,size)
  for _,s in ipairs(segments)do
   if at>=s.at and at+size<=s.at+#s.bytes then return s.bytes:sub(at-s.at+1,at-s.at+size)end
  end
  return nil
 end
 function view.u32(at)local s=view.read(at,4);return s and b.u32(s,0)end
 function view.pointer(at)local s=view.read(at,8);if not s then return nil end;local v=b.u32(s,0)+b.u32(s,4)*4294967296;return v>=65536 and v or nil end
 function view.proves(at,hex)return view.read(at,#hex/2)==b.unhex(hex)end
 return setmetatable({view=view,game=G,key=tostring(copy)..tostring(tamper)},
  {__index=require('hd2runtime/runtime/event_world')})
end
local F=hd2.fields
local spec=W.validate_transaction{id='fast',target=hd2.helldiver(),allow_shared=true,allow_unverified_effect=true,changes={
 {field=F.helldiver.speed_jog,expect=3.2,value=4.5},{field=F.helldiver.stamina_cost_jump,expect=0.2,value=0}}}
local zone=W.validate_patch{id='head',target=hd2.helldiver():zone('head'),allow_shared=true,allow_unverified_effect=true,
 field=F.zone.damage_multiplier,expect='normal',value='reduced'}
local share=W.validate_patch{id='share',target=hd2.helldiver():zone('head'),allow_shared=true,allow_unverified_effect=true,
 field=F.zone.affects_main_health,expect=1.5,value=1}
-- A copy: reported, and the avatar write notes it; the type-only zone write has nothing to note.
W.reset_for_tests()
local report=W.private_copies(make(true))
assert(report.status=='checked'and report.simulated==1 and report.avatars[1].entity==249
 and report.avatars[1].avatar_copy==true and report.avatars[1].health_copy==false
 and report.avatars[1].type=='0x4D1C334D294DFA97',tostring(report.reason))
local notes=W.notes(spec,report)
assert(#notes==1 and notes[1]:find('note: fast: entity 249 carries a private AvatarComponentData copy',1,true)
 and notes[1]:find('helldiver.speed.jog, helldiver.stamina.cost_jump',1,true)
 and notes[1]:find('never writes private copies',1,true),notes[1])
assert(W.notes(zone,report)==nil)
assert(W.notes(share,report)==nil)
-- No copy: nothing to note.
W.reset_for_tests()
report=W.private_copies(make(false))
assert(report.status=='checked'and report.avatars[1].avatar_copy==false)
assert(W.notes(spec,report)==nil)
-- A changed layout pin: unavailable, and the note says the check could not run (the write is not refused).
W.reset_for_tests()
report=W.private_copies(make(true,true))
assert(report.status=='unavailable'and report.reason:find('avatar manager layout changed',1,true),tostring(report.reason))
notes=W.notes(spec,report)
assert(notes and notes[1]:find('could not check for private copies',1,true),tostring(notes and notes[1]))
return 'ok'
''').decode().splitlines()[0], 'ok')


class HelldiverSnapshotTests(unittest.TestCase):
    def test_the_snapshot_overlay_report(self):
        self.assertEqual((OVERLAY['status'], OVERLAY['snapshots'], OVERLAY['failed']), ('VALIDATED', 7, []))
        self.assertEqual(set(OVERLAY['results']), set(RESEARCH['source']['snapshots']))
        for name, result in OVERLAY['results'].items():
            self.assertEqual((result['status'], result['fixtureFallback'], result['noops']), ('VALIDATED', 'disabled', 52),
                name)
            identity = result['identity']
            self.assertTrue(identity['framing'], name)
            self.assertEqual(identity['avatar'], {'recordIndex': 0, 'indexRow': 1, 'ownerCount': 1}, name)
            self.assertEqual(identity['health'], {'recordIndex': 76, 'indexRow': 443, 'ownerCount': 1}, name)
            self.assertEqual(identity['zones'], ZONES, name)
            trips = result['roundTrips']
            self.assertEqual(set(trips), {'jog', 'stamina', 'head_damage_multiplier', 'body_damage_multiplier_dps',
                'body_health', 'explosive_share'}, name)
            for key, trip in trips.items():
                self.assertTrue(trip['protectionRestored'] and trip['restored'], key)
                self.assertEqual(trip['protectionChanges'], 2, key)
                self.assertGreaterEqual(trip['tableBytesChanged'], 1, key)
                self.assertLessEqual(trip['tableBytesChanged'], 4 * trip['writes'], key)
            self.assertEqual((trips['jog']['targetOffsetsInRecord'], trips['jog']['written']), ([16], [4.5]))
            self.assertEqual((trips['stamina']['writes'], trips['stamina']['targetOffsetsInRecord']), (2, [52, 72]))
            self.assertEqual((trips['head_damage_multiplier']['targetOffsetsInRecord'],
                trips['head_damage_multiplier']['written']), ([716], [0]))
            self.assertEqual((trips['body_health']['targetOffsetsInRecord'], trips['body_health']['written']),
                ([1304], [120]))
            self.assertEqual(trips['explosive_share']['targetOffsetsInRecord'], [388])
            self.assertEqual(trips['jog']['tableBytesCompared'], 32 + 2 * 852)
            self.assertEqual(trips['jog']['otherRecordsUnchanged'], 1)
            self.assertEqual(trips['body_health']['otherRecordsUnchanged'], 501)
            rejections = result['rejections']
            self.assertEqual(set(rejections), {'no allow_shared', 'no allow_unverified_effect', 'jog 10.5',
                'sprint duration 0', 'jog NaN', 'unknown zone', 'unknown damage multiplier name', 'stale expect',
                'avatar index row moved', 'avatar record gains a second owner', 'health index row moved',
                'zone name hash changed', 'avatar third-party value', 'zone third-party value'}, name)
            self.assertIn('record ownership changed', rejections['avatar index row moved'])
            self.assertIn('consumer scope changed', rejections['avatar record gains a second owner'])
            self.assertIn('damage zone identity changed', rejections['zone name hash changed'])
            self.assertTrue(rejections['avatar third-party value'].startswith('CONFLICT'))
            self.assertTrue(rejections['zone third-party value'].startswith('CONFLICT'))
            self.assertIn('avatar manager layout changed', result['tamperedPin'])
            # The private copy: the ship's avatar carries one, the mission avatars none (the research observations).
            copies = result['privateCopies']
            self.assertEqual(copies['status'], 'checked', name)
            if name in SHIP:
                self.assertEqual([(a['entity'], a['avatar_copy'], a['local']) for a in copies['avatars']],
                    [(249, True, True)], name)
                self.assertIn('entity 249 (the local player) carries a private AvatarComponentData copy',
                    result['notes']['avatar'][0])
                self.assertIn('private AvatarComponentData copy', trips['jog']['notes'][0])
            else:
                self.assertFalse(any(a['avatar_copy'] for a in copies['avatars']), name)
                self.assertFalse(result['notes']['avatar'], name)
            self.assertFalse(result['notes']['typeOnlyZone'], name)
            self.assertFalse(result['notes']['healthZone'], name)
            self.assertFalse(trips['head_damage_multiplier']['notes'], name)
        self.assertEqual(OVERLAY['results']['F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap']
            ['privateCopies']['simulated'], 0)


class HelldiverWiringTests(unittest.TestCase):
    def test_sdk_docs_release_notes_and_packaged_scenario(self):
        stub = (ROOT / 'sdk/stubs/mods/skyeshade/hd2runtime.lua').read_text(encoding='utf-8')
        for text in ('function hd2.helldiver(name) end', '---@class HD2Helldiver', '---@class HD2HelldiverZone',
                'function HD2Helldiver:zone(identity) end', 'function HD2Helldiver:private_copies() end',
                '---@alias HD2HelldiverZoneName'):
            self.assertIn(text, stub)
        self.assertEqual((ROOT / 'starter/stubs/mods/skyeshade/hd2runtime.lua').read_text(encoding='utf-8'), stub)
        doc = (ROOT / 'docs/helldiver-fields.md').read_text(encoding='utf-8')
        self.assertEqual((ROOT / 'sdk/docs/helldiver-fields.md').read_text(encoding='utf-8'), doc)
        for text in ('every Helldiver this machine simulates', 'allow_shared=true', 'allow_unverified_effect=true',
                '**from the next spawn**', '## Private copies', 'Runtime never writes a private copy', 'STRONG',
                'hd2.fields.zone.damage_multiplier', "'inherit'", 'UNKNOWN_ZONE', 'UNKNOWN_DAMAGE_MULTIPLIER',
                'min(10.0, speed)', 'restores the vanilla values when disabled'):
            self.assertIn(text, doc)
        for definition in SCHEMA['fields']:
            domain, name = definition['id'].split('.', 1)
            if domain == 'helldiver':
                self.assertIn('`' + name.replace('.', '_') + '`', doc, definition['id'])
        self.assertIn('docs/helldiver-fields.md', (ROOT / 'README.md').read_text(encoding='utf-8'))
        notes = (ROOT / 'docs/releases/0.30.0-dev.md').read_text(encoding='utf-8')
        self.assertIn('## Type-wide Helldiver fields (2026-10-08, not live-tested)', notes)
        self.assertIn("'generate_helldiver_fields'", (ROOT / 'scripts/regenerate_domains.py').read_text(encoding='utf-8'))
        self.assertIn('generate_helldiver_fields.generate(check=True)',
            (ROOT / 'scripts/build_release.py').read_text(encoding='utf-8'))
        packaged = (ROOT / 'scripts/validate_packaged_runtime.py').read_text(encoding='utf-8')
        self.assertIn("'helldiver-fields': lambda: HELLDIVER_FIELDS", packaged)
        self.assertIn("'helldiver-fields': {'after': HELLDIVER_FIELDS_LIVE, 'watches': 2", packaged)


if __name__ == '__main__':
    unittest.main()
