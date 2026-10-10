"""The game's component table pointers (core/component_tables.lua, research/docs/entity-component-table-pointers.md).

The 0.31.0 report: "editing the Heat Per Shot and Cool Per Sec for the LAS-12 Sai has no effect". A third-party mod
(True Lasgun Beam Overhaul) repoints the entity manager's BeamWeapon, WeaponHeat and WeaponMagazine table pointers to
its own copies; HD2Runtime wrote the original tables, which the game no longer reads. Before a typed write to a
component record HD2Runtime now re-proves that the game reads that component from exactly the table it writes; a moved
component is refused alone (CONFLICT, owner unknown), every other component goes ahead, and the move is logged once.
"""
import json
from pathlib import Path
import re
import sys
import unittest

from support import ROOT, run
from test_multi_mod_composition import build_profile, snapshot_run

sys.path.insert(0, str(ROOT / 'scripts'))

# Shared by the fixture tests: capture two components of the fixture's entity region through the production path.
CAPTURE = r'''
local tables=require('hd2runtime/core/component_tables');tables.reset()
local catalog_module=require('hd2runtime/core/entity_catalog')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local p=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/component_tables')
local logged={}
require('hd2runtime/runtime/log').emit=function(t)logged[#logged+1]=t end
local function slots()for _,s in ipairs(spans)do if s.at==0x20000000 then return s end end end
local function move(name,to)
 local s=slots();local at=p.components[name].index*8
 s.bytes=s.bytes:sub(1,at)..u64(to)..s.bytes:sub(at+9)
end
local function in_job(fn)
 local co=coroutine.create(fn);local ok,a,b2
 repeat ok,a,b2=coroutine.resume(co);assert(ok,a)until coroutine.status(co)=='dead'
 return a,b2
end
local NAMES={'ProjectileWeaponComponentData','WeaponDataComponentData'}
local function capture()
 return in_job(function()
  local reader=Reader.new(runtime)
  local roots=discover.locate(runtime,reader,p,{entity=true})
  return catalog_module.capture(reader,roots.entity,p,NAMES),roots.entity
 end)
end
local function find(c,resource)for _,x in ipairs(c.candidates)do if x.resourceHash==resource then return x end end end
local JAR5,AMR=p.resources.jar5.resource,p.resources.amr.resource
local function moved_lines()
 local n=0;for _,l in ipairs(logged)do if l:find('COMPONENT TABLE MOVED',1,true)then n=n+1 end end;return n
end
'''


class ComponentTableGuardTests(unittest.TestCase):
    def test_in_place_tables_read_as_before(self):
        self.assertEqual(run(CAPTURE + r'''
local c=capture()
assert(next(c.tables)==nil,'no component refused')
assert(c.record(find(c,JAR5),'ProjectileWeaponComponentData').index==p.resources.jar5.components.ProjectileWeaponComponentData.record)
assert(c.record(find(c,AMR),'WeaponDataComponentData').index==p.resources.amr.components.WeaponDataComponentData.record)
assert(moved_lines()==0)
return 'ok'
'''), b'ok')

    def test_a_moved_table_refuses_only_its_own_component_and_is_logged_once(self):
        self.assertEqual(run(CAPTURE + r'''
local foreign=require('hd2runtime/core/foreign_values');foreign.reset()
local ownership=require('hd2runtime/core/ownership')
move('WeaponDataComponentData',0x7FF000010000)
local c=capture()
local why=c.tables.WeaponDataComponentData
assert(why and why:find('^CONFLICT: the game reads its WeaponDataComponentData table from another place %(another mod '
 ..'moved it%)')and ownership.foreign(why),tostring(why))
assert(not why:find('7FF0',1,true),'no address')
assert(c.tables.ProjectileWeaponComponentData==nil,'the other component is unaffected')
local ok,err=pcall(c.record,find(c,AMR),'WeaponDataComponentData')
assert(not ok and err==why,tostring(err))
assert(c.record(find(c,JAR5),'ProjectileWeaponComponentData').bytes,'the other component reads')
assert(ownership.annotate({code='CONFLICT'},err).owner=='unknown')
-- hd2.inspect: the field is an unknown mod's
local out=require('hd2runtime/api/inspect').classify({field='weapon.ergonomics',expect=65},err)
assert(out.state=='foreign'and out.owner=='unknown',tostring(out.state))
-- logged once per component and session, listed once among the unknown mods' values
capture();capture()
assert(moved_lines()==1,moved_lines())
local list=foreign.list()
assert(#list==1 and list[1].target=='WeaponDataComponentData table'and list[1].owner=='unknown',#list)
-- moved back by its owner: writes go ahead again
move('WeaponDataComponentData',0x100000+p.components.WeaponDataComponentData.offset+28)
c=capture()
assert(c.tables.WeaponDataComponentData==nil and c.record(find(c,AMR),'WeaponDataComponentData').bytes)
foreign.reset()
return 'ok'
'''), b'ok')

    def test_an_unreadable_pointer_is_transient_for_every_component(self):
        self.assertEqual(run(CAPTURE + r'''
replace(0x10000000+D.global,u64(0))
local c=capture()
for _,name in ipairs(NAMES)do
 assert(tostring(c.tables[name]):find('^TARGET_UNAVAILABLE: the game\'s component table pointers are unreadable'),
  tostring(c.tables[name]))
end
local ok,err=pcall(c.record,find(c,JAR5),'ProjectileWeaponComponentData')
assert(not ok and err:find('TARGET_UNAVAILABLE',1,true),err)
assert(moved_lines()==0)
return 'ok'
'''), b'ok')

    def test_pins_are_exact_bytes(self):
        self.assertEqual(run(CAPTURE + r'''
-- the loader's slot store changed: the layout is unproven, nothing is used
local pin=D.pins[#D.pins]
replace(0x10000000+pin.rva,string.rep('\144',#pin.hex/2))
local c=capture()
for _,name in ipairs(NAMES)do
 assert(tostring(c.tables[name]):find('component table pointers unproven',1,true),tostring(c.tables[name]))
end
-- restored, on a fresh proof: one component's own lookup changed refuses that component only
replace(0x10000000+pin.rva,(pin.hex:gsub('%x%x',function(h)return string.char(tonumber(h,16))end)))
tables.reset()
local lookup=D.lookups.WeaponDataComponentData[2]
replace(0x10000000+lookup.rva,string.rep('\144',#lookup.hex/2))
c=capture()
assert(tostring(c.tables.WeaponDataComponentData):find('lookup code is not as reviewed',1,true))
assert(c.tables.ProjectileWeaponComponentData==nil)
return 'ok'
'''), b'ok')

    def test_only_the_identity_scan_skips_the_check(self):
        callers = []
        for folder in ('api', 'core', 'domains', 'runtime', 'primary_mapper'):
            for path in sorted((ROOT / folder).glob('*.lua')):
                if b'identity_scan' in path.read_bytes():
                    callers.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(callers, ['api/weapon_mapper.lua', 'core/entity_catalog.lua'])


class ComponentTableResearchTests(unittest.TestCase):
    def test_the_domain_is_the_research(self):
        import generate_component_tables
        self.assertEqual(generate_component_tables.generate(check=True), [])
        research = json.loads((ROOT / 'research/entity-component-table-pointers-F5FEE03DCFDB.json')
                              .read_text(encoding='utf-8'))
        checks = research['checks']
        for key in ('globalWrittenOnlyByTheConstructor', 'slotsWrittenOnlyByTheLoader', 'everyComponentHasAGlobalLookup',
                    'everySlotSiteReadsTheManagerFromTheGlobal', 'everySnapshotPinByteIdentical',
                    'everyOtherPointerMovedOutsideTheGame', 'managerIsPrivateMemory', 'managerIsGamePlus0xE49F0'):
            self.assertIs(checks[key], True, key)
        self.assertGreaterEqual(checks['snapshotsWithEveryPointerOnTheProfileTable'], 7)
        profile = (ROOT / 'schemas/current.lua').read_text(encoding='utf-8')
        names = set(re.findall(r'\["(\w+ComponentData)"\]=\{\["offset"\]', profile))
        self.assertEqual(set(research['code']['components']), names)
        for name in ('WeaponHeatComponentData', 'BeamWeaponComponentData', 'WeaponMagazineComponentData'):
            self.assertTrue(research['code']['components'][name]['lookupPins'], name)


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class ComponentTableSnapshotTests(unittest.TestCase):
    BODY = r'''
update=update or function()end
local foreign=require('hd2runtime/core/foreign_values');foreign.reset()
require('hd2runtime/core/component_tables').reset()
local sai=hd2.weapon('LAS-12 Sai')
local D=require('hd2runtime/domains/component_tables')
local dll=runtime.address(runtime.module('game.dll'))
local manager=b.pointer(runtime.read(dll+D.global,8),0)
local slot=manager+D.slotBase+8*profile.components.WeaponHeatComponentData.index
local function le(n)local t={};for i=1,8 do t[i]=string.char(n%256);n=math.floor(n/256)end;return table.concat(t)end
local heat_at=resolve('patch',{id='where',target=sai,field=F.heat.heat_per_shot,expect=2,value=1})[1].at
if MOVE then overlay[slot]=le(0x7FF000010000+28)end
local h={}
events.run_as('mods/editor/sai',function()
 h.heat=hd2.ensure({patch={id='heat',target=sai,field=F.heat.heat_per_shot,expect=2,value=1}})
 h.cool=hd2.ensure({patch={id='cool',target=sai,field=F.heat.cool_per_second,expect=5.400000095367432,value=8}})
 h.erg=hd2.ensure({patch={id='erg',target=sai,field=F.weapon.ergonomics,expect=65,value=70}})
 h.rate=hd2.ensure({patch={id='rate',target=sai,field=F.weapon.fire_rate,expect=800,value=900}})
end)
settle({h.heat,h.cool,h.erg,h.rate})
local job=hd2.inspect({target=sai,fields={F.heat.heat_per_shot,F.weapon.ergonomics}})
settle({job})
local function row(x)return{status=x.status,code=x.result and x.result.code,owner=x.result and x.result.owner,
 applied=x.result and x.result.status,error=x.error and tostring(x.error)}end
local moved=0
for _,l in ipairs(LINES)do if l:find('COMPONENT TABLE MOVED: the game reads its WeaponHeatComponentData',1,true)then
 moved=moved+1 end end
return json.encode({heat=row(h.heat),cool=row(h.cool),erg=row(h.erg),rate=row(h.rate),moved=moved,
 heatBytes=b.hex(runtime.read(heat_at,4)),vanilla=b.hex(b.encode(2,'f32')),
 inspect={heat=job.result.by_field[F.heat.heat_per_shot].state,owner=job.result.by_field[F.heat.heat_per_shot].owner,
  erg=job.result.by_field[F.weapon.ergonomics].state}})
'''

    def test_a_moved_heat_table_refuses_the_sai_heat_writes_only(self):
        result = snapshot_run('local MOVE=true\n' + self.BODY)
        for key in ('heat', 'cool'):
            self.assertEqual((result[key]['status'], result[key]['code'], result[key]['owner']),
                             ('rejected', 'CONFLICT', 'unknown'), result[key])
            self.assertIn('the game reads its WeaponHeatComponentData table from another place', result[key]['error'])
        self.assertEqual(result['heatBytes'], result['vanilla'], 'the original heat table was written')
        for key in ('erg', 'rate'):
            self.assertEqual(result[key]['applied'], 'APPLIED', result[key])
        self.assertEqual(result['moved'], 1)
        self.assertEqual(result['inspect'], {'heat': 'foreign', 'owner': 'unknown', 'erg': 'runtime'})

    def test_with_the_pointer_in_place_everything_applies_as_before(self):
        result = snapshot_run('local MOVE=false\n' + self.BODY)
        for key in ('heat', 'cool', 'erg', 'rate'):
            self.assertEqual(result[key]['applied'], 'APPLIED', result[key])
        self.assertNotEqual(result['heatBytes'], result['vanilla'])
        self.assertEqual(result['moved'], 0)
        self.assertEqual(result['inspect']['heat'], 'runtime')


if __name__ == '__main__':
    unittest.main()


class YieldSafetyTests(unittest.TestCase):
    def test_the_check_never_yields_across_a_pcall(self):
        # 0.30.2 live: the game's LuaJIT cannot yield across a pcall. The reader yields mid-check; protected() passes
        # each yield up to the capture's coroutine and finishes the call; outside a coroutine it resumes at once.
        from support import run
        self.assertEqual(run(r'''
local T=require('hd2runtime/core/component_tables')
local yields=0
local function reads(n)for i=1,n do coroutine.yield()end;return 'done',n end
-- inside a coroutine: every inner yield reaches the outer resumer
local co=coroutine.create(function()return T.protected(reads,3)end)
local results
while true do
    local r={coroutine.resume(co)}
    assert(r[1],tostring(r[2]))
    if coroutine.status(co)=='dead'then results=r;break end
    yields=yields+1
end
assert(yields==3 and results[2]==true and results[3]=='done'and results[4]==3,yields)
-- outside a coroutine: resumed at once, no yield escapes
local ok,a,b=T.protected(reads,2)
assert(ok==true and a=='done'and b==2)
-- an error is returned like pcall's
local okx,why=T.protected(function()error('boom',0)end)
assert(okx==false and why=='boom')
return 'ok'
'''), b'ok')
