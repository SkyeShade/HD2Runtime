"""The explosion catalogue (docs/explosions.md): hd2.explosions.list / describe, the hd2.explosion(name) target and its
guarded edits (domains/explosion_writes.lua), catalogued explosions as payloads (terminal.explosion, attack output
slots, custom projectile rows) and hd2.explosions.spawn over the catalogue. Offline; the retained-snapshot write proofs
are scripts/validate_explosion_catalogue_snapshot.py (validation/explosion-catalogue-snapshot.json)."""
import json
import re
import unittest

from support import ROOT, run
from test_event_scripting import PRELUDE

import generate_explosion_catalogue

SDK = json.loads((ROOT / 'sdk/ExplosionCatalogue.json').read_text(encoding='utf-8'))
RESEARCH = json.loads((ROOT / 'research/explosion-identities-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
SNAPSHOT_REPORT = ROOT / 'validation/explosion-catalogue-snapshot.json'


def lua_ok(body):
    return run(body + '\n')


class CatalogueTests(unittest.TestCase):
    def test_generated_outputs_are_current(self):
        self.assertEqual(generate_explosion_catalogue.generate(check=True), [])

    def test_sdk_catalogue_carries_no_raw_ids(self):
        named = [r for r in RESEARCH['explosions'] if r['name']]
        self.assertEqual(SDK['summary']['named'], len(named))
        self.assertEqual(len(SDK['explosions']), len(named))
        text = json.dumps(SDK)
        self.assertIsNone(re.search(r'0x[0-9A-Fa-f]{8,}', text), 'no package or resource id')
        for item in SDK['explosions']:
            self.assertFalse({'type', 'row', 'resource', 'packageId'} & set(item), item['name'])
            self.assertFalse({'type', 'row', 'resource'} & set(item['package']))
        self.assertEqual(SDK['contract'], 'hd2runtime.explosion_catalogue.v1')
        by = {item['name']: item for item in SDK['explosions']}
        eruptor = by['weapon/r36_eruptor/impact']
        self.assertTrue(eruptor['reviewedSpawn'] and eruptor['legacyName'] == 'R-36 Eruptor')
        self.assertTrue(eruptor['package']['mission'] and eruptor['payload'])
        self.assertEqual(eruptor['values']['explosion.inner_radius'], 4.0)
        gas = by['stratagem/orbital_gas_strike/shell_impact']
        self.assertTrue(gas['shared'] and not gas['reviewedSpawn'] and gas['spawn'])
        self.assertIn('explosion.damage.standard_damage', gas['values'])
        # The Cyborg Production Unit ships in objective packages: spawnable through its reviewed name, never a payload.
        cpu = by['entity/cyborg_production_unit/ability']
        self.assertTrue(cpu['reviewedSpawn'] and not cpu['payload'])

    def test_list_describe_and_handles(self):
        self.assertEqual(lua_ok(r'''
local hd2=require('hd2runtime/api/hd2')
local all=hd2.explosions.list()
assert(#all==241,#all)
for _,e in ipairs(all)do
    assert(e.type==nil and e.row==nil,'no raw id: '..e.name)
    assert(type(e.name)=='string'and type(e.label)=='string'and type(e.family)=='string')
end
local weapons=hd2.explosions.list({family='weapon'})
for _,e in ipairs(weapons)do assert(e.family=='weapon')end
assert(#hd2.explosions.list({reviewed_spawn=true})==16)
local eagle=hd2.explosions.list({owner='eagle 500kg'})
assert(#eagle>=1,'an owner filter is a case-insensitive substring')
assert(#hd2.explosions.list({search='eruptor'})>=1)
assert(not pcall(hd2.explosions.list,{colour='red'}),'an unknown filter key is refused')
local d=hd2.explosions.describe('weapon/r36_eruptor/impact')
assert(d.label=='R-36 Eruptor (impact)'and d.package.known and d.package.mission and d.package.loaded_by_runtime==false)
assert(#d.fields==13 and d.fields[1].semanticFieldId=='explosion.inner_radius')
assert(d.fields[4].semanticFieldId=='explosion.shrapnel_count'and d.fields[4].editable,'the Eruptor releases shrapnel')
-- By label too, case-insensitive.
assert(hd2.explosions.describe('r-36 eruptor (impact)').name=='weapon/r36_eruptor/impact')
local missing,why=hd2.explosions.describe('weapon/nothing/impact')
assert(missing==nil and why:find('UNKNOWN_EXPLOSION',1,true))
-- A row without a damage link has read-only damage fields; one without shrapnel a read-only shrapnel count.
local smoke=hd2.explosion('throwable/g3_smoke/detonation'):describe()
for _,f in ipairs(smoke.fields)do
    if f.semanticFieldId:find('^explosion%.damage%.')then assert(not f.editable,f.semanticFieldId)end
end
local h=hd2.explosion('stratagem/orbital_gas_strike/shell_impact')
assert(h.resource=='explosion'and h.explosion=='stratagem/orbital_gas_strike/shell_impact')
local keys={};for k in pairs(h)do keys[#keys+1]=k end
assert(#keys==2,'a handle carries only its identity')
assert(not pcall(hd2.explosion,'nothing'),'an unknown explosion raises')
-- The reviewed set keeps its 0.29 shape (without the raw type).
local reviewed=hd2.explosions.reviewed()
assert(#reviewed==16)
for _,e in ipairs(reviewed)do assert(e.type==nil and e.catalogue,e.name)end
return 'ok'
'''), b'ok')


class WriteValidationTests(unittest.TestCase):
    def test_acknowledgements_ranges_and_identity(self):
        self.assertEqual(lua_ok(r'''
local hd2=require('hd2runtime/api/hd2')
local W=require('hd2runtime/domains/explosion_writes')
local function fails(request,needle)
    local ok,why=pcall(W.validate_patch,request)
    assert(not ok,'not rejected: '..needle)
    assert(tostring(why):find(needle,1,true),'wrong reason: '..tostring(why))
end
local crossbow=hd2.explosion('weapon/cb9_exploding_crossbow/impact')
local d=crossbow:describe()
assert(not d.shared)
local inner=d.stats.inner_radius
local spec=W.validate_patch({id='x',target=crossbow,field='explosion.inner_radius',expect=inner,value=5,
    allow_unverified_effect=true})
assert(spec.kind=='explosion'and spec.explosion=='weapon/cb9_exploding_crossbow/impact'and#spec.changes==1)
fails({id='x',target=crossbow,field='explosion.inner_radius',expect=inner,value=5},'allow_unverified_effect')
fails({id='x',target=crossbow,field='explosion.inner_radius',expect=inner+1,value=5,allow_unverified_effect=true},
    'expect differs')
fails({id='x',target=crossbow,field='explosion.inner_radius',expect=inner,value=500,allow_unverified_effect=true},
    'reviewed range')
fails({id='x',target=crossbow,field='explosion.damage.ap_direct',expect=3,value=2.5,allow_unverified_effect=true},
    'integer')
fails({id='x',target=crossbow,field='explosion.shrapnel_projectile',expect=0,value=1,allow_unverified_effect=true},
    'not exposed')
fails({id='x',target={resource='explosion',explosion=59},field='explosion.inner_radius',expect=inner,value=5,
    allow_unverified_effect=true},'unsupported explosion target')
fails({id='x',target={resource='explosion',explosion='weapon/x/impact'},field='explosion.inner_radius',expect=1,
    value=5,allow_unverified_effect=true},'UNKNOWN_EXPLOSION')
-- A shared row (the Orbital Gas Strike's shell explosion has seven owners) needs allow_shared.
local gas=hd2.explosion('stratagem/orbital_gas_strike/shell_impact')
local g=gas:describe()
assert(g.shared)
fails({id='x',target=gas,field='explosion.outer_radius',expect=g.stats.outer_radius,value=20,
    allow_unverified_effect=true},'allow_shared')
assert(W.validate_patch({id='x',target=gas,field='explosion.outer_radius',expect=g.stats.outer_radius,value=20,
    allow_unverified_effect=true,allow_shared=true}))
-- A transaction may change the row and its damage row together.
local damage=crossbow:describe().stats.standard_damage
local t=W.validate_transaction({id='x',target=crossbow,allow_unverified_effect=true,allow_shared=true,changes={
    {field='explosion.inner_radius',expect=inner,value=4},
    {field='explosion.damage.standard_damage',expect=damage,value=500}}})
assert(#t.changes==2)
-- Through the public entry points: the registration rejects it without the acknowledgement, without raising.
local handle=hd2.patch({id='explosion-no-ack',target=crossbow,field=hd2.fields.explosion.inner_radius,expect=inner,
    value=5})
assert(handle.status=='rejected'and handle.error:find('allow_unverified_effect',1,true),tostring(handle.error))
return 'ok'
'''), b'ok')


class PayloadValidationTests(unittest.TestCase):
    def test_terminal_explosion_and_output_slots_take_catalogued_explosions(self):
        self.assertEqual(lua_ok(r'''
local hd2=require('hd2runtime/api/hd2')
local weapons=require('hd2runtime/domains/player_weapon_writes')
local outputs=require('hd2runtime/domains/output_writes')
local terminal=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile():terminal_action('impact')
local own=terminal:explosion()
local gas=hd2.explosion('stratagem/orbital_gas_strike/shell_impact')
local function request(value,extra)
    local r={id='payload',target=terminal,field='terminal.explosion',expect=own,value=value}
    for k,v in pairs(extra or{})do r[k]=v end
    return r
end
local ok,why=pcall(weapons.validate_patch,request(gas))
assert(not ok and tostring(why):find('allow_unverified_reference',1,true),tostring(why))
ok,why=pcall(weapons.validate_patch,request(gas,{allow_unverified_reference=true}))
assert(not ok and tostring(why):find('allow_unverified_effect',1,true),tostring(why))
local spec=weapons.validate_patch(request(gas,{allow_unverified_reference=true,allow_unverified_effect=true}))
local change=spec.changes[1]
assert(change.catalogue_explosion and change.catalogue_explosion.type==82)
-- The Gas Strike's package is the stratagem's call-in package: loaded before the write.
assert(spec.asset_dependencies and#spec.asset_dependencies==1,'one package dependency')
-- A mission-effects explosion (the PLAS-15 Loyalist's) needs no load: resident in every mission.
spec=weapons.validate_patch(request(hd2.explosion('weapon/plas15_loyalist/impact'),{allow_unverified_reference=true,
    allow_unverified_effect=true}))
assert(#(spec.asset_dependencies or{})==0)
-- An explosion with no known package is refused; so is an explosion handle as expect.
local enemy
for _,e in ipairs(hd2.explosions.list({payload=false}))do enemy=enemy or e.name end
ok,why=pcall(weapons.validate_patch,request(hd2.explosion(enemy),{allow_unverified_reference=true,
    allow_unverified_effect=true}))
assert(not ok and tostring(why):find('ASSET_UNAVAILABLE',1,true),tostring(why))
ok,why=pcall(weapons.validate_patch,{id='p',target=terminal,field='terminal.explosion',expect=gas,value=own,
    allow_unverified_reference=true,allow_unverified_effect=true})
assert(not ok and tostring(why):find('expect must be',1,true),tostring(why))
-- An attack output's explosion slot.
local base=hd2.attack_output('LAS-58 Talon')
local slot={id='slot',target=base,field='projectile.impact_explosion',expect='none',value=gas,
    allow_unverified_effect=true,allow_shared=true}
ok,why=pcall(outputs.validate_patch,slot)
assert(not ok and tostring(why):find('allow_unverified_reference',1,true),tostring(why))
slot.allow_unverified_reference=true
spec=outputs.validate_patch(slot)
assert(spec.changes[1].catalogue_explosion.type==82 and spec.asset_dependencies)
-- Not for a damage slot.
ok,why=pcall(outputs.validate_patch,{id='slot',target=base,field='projectile.direct_damage',
    expect=base:direct_damage(),value=gas,allow_unverified_effect=true,allow_shared=true,allow_unverified_reference=true})
assert(not ok and tostring(why):find('damage slot',1,true),tostring(why))
return 'ok'
'''), b'ok')


class SpawnTests(unittest.TestCase):
    def test_spawn_over_the_catalogue(self):
        self.assertEqual(run(PRELUDE + r'''
local P={x=1,y=2,z=3}
hd2.events.run_as('mods/t/cat',function()hd2.events.on('mission_started',function()end)end)
local function spawn(what,opts)
    local action
    hd2.events.run_as('mods/t/cat',function()action=hd2.explosions.spawn(what,opts)end)
    return action
end
mission({host=true})
-- A reviewed explosion by its catalogue name resolves exactly as by its reviewed name.
local a=spawn('weapon/r36_eruptor/impact',{position=P})
assert(a.status=='requested'and a.explosion=='R-36 Eruptor'and W.runtime.explosions[1].type==158,tostring(a.code))
a=spawn(hd2.explosion('stratagem/nux223_hellbomb/behavior'),{position=P})
assert(a.status=='requested'and W.runtime.explosions[2].type==242,tostring(a.code))
-- Outside the reviewed set: allow_unverified_effect.
a=spawn('stratagem/orbital_gas_strike/shell_impact',{position=P})
assert(a.status=='refused'and a.code=='UNVERIFIED_EXPLOSION',tostring(a.code))
a=spawn('stratagem/orbital_gas_strike/shell_impact',{position=P,allow_unverified_effect=true})
assert(a.status=='requested'and a.explosion=='stratagem/orbital_gas_strike/shell_impact'
    and W.runtime.explosions[3].type==82,tostring(a.code)..' '..tostring(a.reason))
-- Without a known package: refused.
local enemy
for _,e in ipairs(hd2.explosions.list({spawn=false}))do enemy=enemy or e.name end
a=spawn(enemy,{position=P,allow_unverified_effect=true})
assert(a.status=='refused'and a.code=='ASSET_UNKNOWN',tostring(a.code))
-- A mission-effects explosion is requested only while that package is resident; the Runtime never loads it.
local mission_entry
for _,e in ipairs(hd2.explosions.list({reviewed_spawn=false,spawn=true}))do
    if e.mission_package then mission_entry=mission_entry or e.name end
end
assert(mission_entry,'a mission-effects explosion outside the reviewed set')
local id=require('hd2runtime/core/assets').dependency('explosion/'..mission_entry).package
W.runtime.packages[id]='absent'
a=spawn(mission_entry,{position=P,allow_unverified_effect=true})
assert(a.status=='refused'and a.code=='ASSET_UNAVAILABLE',tostring(a.code))
W.runtime.packages[id]='resident'
tick(40)
a=spawn(mission_entry,{position=P,allow_unverified_effect=true})
assert(a.status=='requested',tostring(a.code)..' '..tostring(a.reason))
return 'ok'
'''), b'ok')

    def test_silos_keep_the_reviewed_set(self):
        self.assertEqual(lua_ok(r'''
local actions=require('hd2runtime/api/actions')
local t,code=actions.explosion_target('stratagem/orbital_gas_strike/shell_impact')
assert(t==nil and code=='UNVERIFIED_EXPLOSION','a silo blast (no acknowledgement) stays in the reviewed set')
assert(actions.explosion_target('Hellbomb').type==242)
assert(actions.explosion_target('stratagem/nux223_hellbomb/behavior').name=='NUX-223 Hellbomb')
return 'ok'
'''), b'ok')


@unittest.skipUnless(SNAPSHOT_REPORT.is_file(), 'snapshot validation report absent')
class SnapshotValidationReportTests(unittest.TestCase):
    def test_report(self):
        report = json.loads(SNAPSHOT_REPORT.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'VALIDATED')
        self.assertEqual(report['explosions'], SDK['summary']['named'])
        self.assertEqual(report['identityProofs'], SDK['summary']['named'])
        self.assertGreater(report['changedWrites'], 0)
        self.assertEqual(report['changedWrites'], report['rollbacks'])
        self.assertGreater(report['payloadWrites'], 0)
        self.assertEqual(report['fixtureFallback'], 'disabled')


if __name__ == '__main__':
    unittest.main()
