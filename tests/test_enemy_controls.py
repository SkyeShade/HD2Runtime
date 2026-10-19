"""0.40.0 enemy authoring: truthful discovery, guarded writes and retained-memory round trips."""
import json
import unittest
from support import ROOT, run
import build_profile


class EnemyControlTests(unittest.TestCase):
    def test_display_names_preserve_target_identity(self):
        self.assertEqual(run(r'''
local h=require('hd2runtime/api/hd2')
local W=require('hd2runtime/domains/enemy_writes')
for _,pair in ipairs({{'spawner','Factory Strider'},{'illuminate_dropship','Warp Ship'},
    {'boomer_nurser','Nursing Spewer'},{'cy_stratagem_blocker','Stratagem Jammer'},
    {'il_obj_asset_weather_device_core','Exospire Core'},{'unnamed_entity_0034','MG Raider'}})do
    local target=h.enemy(pair[1]);local d=target:describe()
    assert(target.enemy==pair[1]and d.name==pair[1]and d.displayName==pair[2])
    assert(W.entries()[pair[1]].displayName==d.displayName)
    d.displayName='edited';assert(target:describe().displayName==pair[2])
end
assert(h.enemy('Spore Burst Bile Titan'):describe().displayName=='Spore Burst Bile Titan')
assert(h.enemy('cha_soldier.cha_soldier_jumppack'):describe().fullDisplayName=='Devastator - Soldier Jumppack')
assert(h.enemy('unnamed_entity_0216'):describe().nameSource=='unresolved')
local count=0
for _,entry in pairs(W.entries())do
    assert(type(entry.displayName)=='string'and#entry.displayName>0)
    assert(not entry.displayName:find('content/',1,true))
    count=count+1
end
assert(count==1178)
local named=0
for _,row in ipairs(h.enemies.rosters())do
    assert(row.metadata.displayName)
    if row.metadata.displayName=='Scavenger'then named=named+1 end
end
assert(named>0)
for _,row in ipairs(h.enemies.compositions())do
    for _,group in ipairs(row.metadata.groups)do assert(#group.candidates==#group.candidateNames)end
end
return 'ok'
'''),b'ok')

    def test_generated_catalogues_and_constants(self):
        import generate_enemy_controls
        import generate_enemy_director
        self.assertEqual(generate_enemy_controls.generate(check=True), [])
        self.assertEqual(generate_enemy_director.generate(check=True), [])
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
assert(hd2.version=='0.40.1')
assert(hd2.fields.unit.scale_min=='unit.scale_min')
assert(hd2.fields.spawner.queue_limit=='spawner.queue_limit')
assert(hd2.fields.hive.refill_clock_rate_players_1=='hive.refill_clock_rate_players_1')
assert(hd2.fields.demolition.force=='demolition.force')
assert(#hd2.enemies()==1178)
assert(#hd2.enemies({component='HiveMind'})==19) -- twentieth record is unowned
assert(#hd2.enemies({component='Bughole'})>0)
assert(#hd2.enemies.rosters()==191 and #hd2.enemies.compositions()==452)
assert(#hd2.enemies.destruction_models()==1641)
local ship=hd2.enemy('illuminate_dropship'):describe()
assert(ship.transport.capacityCells==15 and ship.transport.dimensions[1]==5 and ship.transport.dimensions[2]==3)
local landed=hd2.structure('il_spawner_ship'):describe()
assert(#landed.mountedEntities>0 and #landed.demolition>0)
assert(landed.demolition[1].association=='embedded_model_reference')
assert(hd2.enemy('Charger').enemy==hd2.enemy('charger').enemy)
return 'ok'
'''), b'ok')

    def test_new_fields_reject_bad_values_and_acknowledgements(self):
        self.assertEqual(run(r'''
local h=require('hd2runtime/api/hd2')
local W=require('hd2runtime/domains/enemy_writes')
local D=require('hd2runtime/domains/enemy_director_writes')
local function req(target,field,expect,value)
 return {id='check',target=target,field=field,expect=expect,value=value,allow_shared=true,allow_unverified_effect=true}
end
local function bad(domain,r,needle)
 local ok,why=pcall(domain.validate_patch,r)
 assert(not ok and tostring(why):find(needle,1,true),tostring(why))
end
local r=req(h.enemy('Charger'),'unit.scale_min',1,1.5)
assert(W.validate_patch(r).changes[1].descriptor.backing.component=='UnitComponentData')
r.allow_unverified_effect=nil;bad(W,r,'allow_unverified_effect')
bad(W,req(h.enemy('Charger'),'unit.scale_max',1,2),'read-only')
bad(W,req(h.enemy('Charger'),'unit.scale_min',1,0/0),'finite')
bad(W,req(h.enemy('Charger'),'unit.scale_min',1,0),'reviewed range')
bad(W,req(h.structure('il_spawner_ship'),'spawner.queue_limit',4,17),'reviewed range')
bad(W,req(h.structure('il_spawner_ship'),'spawner.queue_limit',4,2.5),'integer')
bad(W,req(h.structure('cy_stratagem_blocker'),'jammer.radius',150,0),'reviewed range')
bad(W,req(h.enemy('illuminate_dropship'),'transport.grid_dimension_0',5,6),'reviewed range')
r=req(h.enemies.difficulty(10),'difficulty.encounter_points',600,450)
assert(D.validate_patch(r).kind=='enemy_director')
r.allow_shared=nil;bad(D,r,'allow_shared')
bad(D,req(h.enemies.demolition_template('none'),'demolition.force',0,1),'not writable')
bad(D,req(h.enemies.demolition_template('Hellbomb'),'demolition.force',60,256),'reviewed director range')
bad(D,req(h.enemies.composition('terminids/family_3/row_0'),'composition.group_0_count',999,3),'read-only')
local transaction={id='duplicate',target=h.enemies.difficulty(10),allow_shared=true,allow_unverified_effect=true,
 changes={{field='difficulty.encounter_points',expect=600,value=400},{field='difficulty.encounter_points',expect=600,value=500}}}
assert(not pcall(D.validate_transaction,transaction))
return 'ok'
'''), b'ok')

    def test_zone_ambiguity_and_descriptions_do_not_mutate_catalogues(self):
        self.assertEqual(run(r'''
local h=require('hd2runtime/api/hd2')
local m=h.enemy('mothership')
local ok,why=pcall(function()return m:zone('body_default')end)
assert(not ok and tostring(why):find('ambiguous',1,true))
assert(m:zone(0).zone=='zone_0'and m:zone(1).zone=='zone_1')
assert(not pcall(function()return m:zone(nil)end))
local first=m:zone(0):describe();first.fields[1].currentDefault=-999
assert(m:zone(0):describe().fields[1].currentDefault~=-999)
local d=h.enemies.difficulty(10);local info=d:describe();info.fields[1].currentDefault=-999
assert(d:describe().fields[1].currentDefault==600)
local found=false
for _,e in pairs(require('hd2runtime/domains/enemy_controls').enemies)do
 for _,z in ipairs(e.zones)do
  if #z.nameCandidates>1 then assert(z.name==nil);found=true end
 end
end
assert(found,'collision evidence was dropped')
return 'ok'
'''), b'ok')

    def test_expanded_attack_links_require_shared_acknowledgement(self):
        self.assertEqual(run(r'''
local h=require('hd2runtime/api/hd2')
local W=require('hd2runtime/domains/enemy_writes')
local e=W.entry('tripod_tier_2');local found
for _,a in ipairs(e.attacks)do if a.source and a.source.component=='ArcWeaponComponentData'and a.role=='damage'then
 for _,f in ipairs(e.fields)do if f.attack==a.id and f.id=='damage.standard_damage'and f.editable then
  local r={id='arc',target=h.enemy(e.name):attack(a.id),field=f.id,expect=f.currentDefault,value=f.currentDefault+1,
   allow_unverified_effect=true}
  local ok,why=pcall(W.validate_patch,r);assert(not ok and tostring(why):find('allow_shared',1,true))
  r.allow_shared=true;assert(W.validate_patch(r).changes[1].descriptor.shared);found=true
 end end
end end
assert(found)
return 'ok'
'''), b'ok')

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot unavailable')
    def test_snapshot_writes_conflicts_and_inverse(self):
        from validate_enemy_controls_snapshot import validate
        result=validate()
        self.assertEqual(result['status'],'VALIDATED')
        self.assertFalse(result['liveGameTested'])
        self.assertEqual(result['coverage']['directorRows'],dict(composition=452,demolition_template=9,difficulty=10,roster=191))
        self.assertEqual(len(result['roundTrips']),92)
        self.assertEqual(result['coverage']['entityFields'],38787)
        self.assertEqual(result['coverage']['entityTargetBatches'],4990)
        self.assertTrue(all(result['coverage']['publicApi'].values()))
        for trip in result['roundTrips']:
            self.assertTrue(trip['restored'] and trip['nonTargetBytesUnchanged'])
        self.assertTrue({'native code changed','row identity changed','Ship state','CONFLICT'}<=set(result['rejections']))
