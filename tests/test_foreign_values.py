"""Values changed by mods outside HD2Runtime (core/foreign_values.lua, api/inspect.lua, core/ownership.lua).

A data-file mod (patched game archives) or another program changes game values HD2Runtime never wrote. HD2Runtime must
leave such a value alone and refuse writes to that value only, naming its owner as an unknown mod, while every other
value (the same record included) stays writable; hd2.inspect tells a stats editor, before it writes anything, which
values are vanilla, which an HD2Runtime mod holds and which an unknown mod owns.

The snapshot tests run on a copy-on-write overlay of the retained current-build snapshot (no game process).
"""
import unittest

from support import run
from test_multi_mod_composition import build_profile, snapshot_run


class OwnershipRuleTests(unittest.TestCase):
    def test_unknown_owner_is_named_and_remembered_once(self):
        self.assertEqual(run(r'''
local ownership=require('hd2runtime/core/ownership')
local foreign=require('hd2runtime/core/foreign_values')
local records=require('hd2runtime/core/shared_records')
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local b=require('hd2runtime/core/bytes')
records.reset_claims();foreign.reset()
local spec=patches.validate({id='arc-stun',allow_shared=true,
 target=hd2.support_weapon('ARC-3 Arc Thrower'):attack('primary_status_37'),field=hd2.fields.status.duration,
 expect=1.5,value=3})
local change=spec.changes[1]
-- The rule is unchanged: the reviewed and the desired bytes pass.
assert(ownership.expected(change,change.expected)==change.expected)
assert(ownership.expected(change,change.desired)==change.expected)
assert(ownership.state(change,change.expected)=='vanilla')
-- Bytes no HD2Runtime operation applied: refused, owner unknown, remembered once.
local ok,why=pcall(ownership.expected,change,b.encode(2,'f32'))
why=tostring(why)
assert(not ok and why:find('CONFLICT: status.duration is neither expected nor desired',1,true),why)
assert(why:find('owner: unknown mod, not HD2Runtime',1,true)and ownership.foreign(why),why)
local state,owner=ownership.state(change,b.encode(2,'f32'))
assert(state=='foreign'and owner=='unknown',tostring(state))
pcall(ownership.expected,change,b.encode(2,'f32'))
local list=foreign.list()
assert(#list==1,#list)
assert(list[1].target=='support_weapon ARC-3 Arc Thrower'and list[1].field=='status.duration'
 and list[1].observed=='2'and list[1].expected=='1.5'and list[1].owner=='unknown'and list[1].seen==2,
 list[1].target..'|'..list[1].field..'|'..tostring(list[1].observed))
local result=ownership.annotate({code='CONFLICT'},why)
assert(result.owner=='unknown'and result.foreign==true)
-- Bytes another HD2Runtime mod applied: a Runtime conflict, never "unknown".
local tesla=patches.validate({id='tesla-stun',allow_shared=true,
 target=hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():weapon('primary'):attack('primary_damage_status_1'),
 field=hd2.fields.status.duration,expect=1.5,value=2})
records.claim(tesla,'ensure','mods/carol/sentries')
ok,why=pcall(ownership.expected,change,b.encode(2,'f32'))
why=tostring(why)
assert(not ok and not ownership.foreign(why)and why:find('held by mods/carol/sentries',1,true),why)
local state2,owner2,operation=ownership.state(change,b.encode(2,'f32'))
assert(state2=='runtime'and owner2=='mods/carol/sentries'and operation=='tesla-stun',tostring(state2))
assert(ownership.annotate({code='CONFLICT'},why).owner==nil)
records.reset_claims();foreign.reset()
return 'ok'
'''), b'ok')

    def test_inspect_request_validation(self):
        self.assertEqual(run(r'''
local inspect=require('hd2runtime/api/inspect')
local hd2=require('hd2runtime/api/hd2')
local function fails(request,text)
 local ok,why=pcall(inspect.validate,request)
 assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
local turret=hd2.stratagem('A/G-16 Gatling Sentry'):deployed_entity():turret()
fails({target=turret},'one to 64 fields')
fails({target=turret,fields={}},'one to 64 fields')
fails({target={},fields={'x'}},'typed target')
fails({target=turret,fields={'x'},extra=1},'unsupported inspect option')
fails({target=turret,fields={1}},'field 1 must be')
-- The reviewed value comes from the target's own catalogue when no expect is given.
local items=inspect.validate({target=turret,fields={hd2.fields.turret.yaw_speed,{field='x',expect=3}}})
assert(items[1].expect==80 and items[2].expect==3,tostring(items[1].expect))
return 'ok'
'''), b'ok')


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class ForeignValueSnapshotTests(unittest.TestCase):
    def test_a_data_file_change_refuses_only_its_own_value(self):
        result = snapshot_run(r'''
-- The game's own update callback, which the scheduler chains to (and restores when its last watch ends).
update=update or function()end
local foreign=require('hd2runtime/core/foreign_values')
local inspect=require('hd2runtime/api/inspect')
foreign.reset()
local turret=hd2.stratagem('A/G-16 Gatling Sentry'):deployed_entity():turret()
local targeting=hd2.stratagem('A/G-16 Gatling Sentry'):deployed_entity():targeting()
local yaw,pitch=F.turret.yaw_speed,F.turret.pitch_speed
local pitch_vanilla=inspect.reviewed(turret,pitch)
check(type(pitch_vanilla)=='number','no reviewed pitch speed')
-- A data-file mod changed the yaw speed before HD2Runtime started: the bytes differ, nobody in HD2Runtime wrote them.
local at=resolve('patch',{id='where',target=turret,field=yaw,expect=80,value=81})[1]
overlay[at.at]=b.encode(95,'f32')
-- 1. inspect: the yaw speed is an unknown mod's, the pitch speed is vanilla; nothing is written.
local job=hd2.inspect({target=turret,fields={yaw,pitch}})
settle({job})
check(job.status=='complete','inspect '..tostring(job.status))
local y,p=job.result.by_field[yaw],job.result.by_field[pitch]
check(y.state=='foreign'and y.owner=='unknown'and math.abs(y.value-95)<1e-4 and y.vanilla==80,
 'yaw '..tostring(y.state)..' '..tostring(y.value)..' '..tostring(y.reason))
check(p.state=='vanilla'and math.abs(p.value-pitch_vanilla)<1e-4,'pitch '..tostring(p.state)..' '..tostring(p.reason))
check(counts.writes==0 and counts.protection_changes==0,'inspect wrote')
-- 2. A mod's ensure on the yaw speed is refused (owner unknown) and writes nothing; the pitch speed of the same
-- record, and another record of the same sentry, apply.
local handles={}
events.run_as('mods/alice/turrets',function()
 handles.yaw=hd2.ensure({patch={id='yaw',target=turret,field=yaw,expect=80,value=120}})
 handles.pitch=hd2.ensure({patch={id='pitch',target=turret,field=pitch,expect=pitch_vanilla,value=pitch_vanilla*2}})
 handles.range=hd2.ensure({patch={id='range',target=targeting,field=F.targeting.range,expect=75,value=100}})
end)
settle({handles.yaw,handles.pitch,handles.range})
check(handles.yaw.status=='rejected'and handles.yaw.result.code=='CONFLICT'and handles.yaw.result.owner=='unknown',
 'yaw '..tostring(handles.yaw.status)..' '..tostring(handles.yaw.error))
check(runtime.read(at.at,4)==b.encode(95,'f32'),'the unknown mod\'s value was overwritten')
check(handles.pitch.runs>=1 and handles.pitch.result.status=='APPLIED','pitch '..tostring(handles.pitch.error))
check(handles.range.runs>=1 and handles.range.result.status=='APPLIED','range '..tostring(handles.range.error))
-- 3. inspect again: the pitch speed is now held by alice's ensure.
job=hd2.inspect({target=turret,fields={pitch}})
settle({job})
p=job.result.by_field[pitch]
check(p.state=='runtime'and p.owner=='mods/alice/turrets'and p.operation=='pitch',
 'pitch after '..tostring(p.state)..' '..tostring(p.owner))
-- 4. Another HD2Runtime mod expecting the vanilla range: a Runtime conflict naming alice, never "unknown".
local bob
events.run_as('mods/bob/turrets',function()
 bob=hd2.ensure({patch={id='range',target=targeting,field=F.targeting.range,expect=75,value=110}})
end)
settle({bob})
check(bob.status=='rejected'and bob.result.code=='CONFLICT'and bob.result.owner==nil
 and tostring(bob.error):find('held by mods/alice/turrets',1,true),'bob '..tostring(bob.error))
local list=foreign.list()
local logged=0
for _,line in ipairs(LINES)do if line:find('FOREIGN VALUE:',1,true)then logged=logged+1 end end
local owner_lines=0
for _,line in ipairs(LINES)do if line:find('REJECTED code=CONFLICT owner=unknown',1,true)then owner_lines=owner_lines+1 end end
return json.encode({foreign=list,logged=logged,owner_lines=owner_lines})
''')
        self.assertEqual(len(result['foreign']), 1, result)
        entry = result['foreign'][0]
        self.assertEqual(entry['target'], 'stratagem A/G-16 Gatling Sentry')
        self.assertEqual((entry['field'], entry['observed'], entry['expected'], entry['owner']),
                         ('turret.yaw_speed', '95', '80', 'unknown'))
        self.assertEqual(result['logged'], 1)
        self.assertEqual(result['owner_lines'], 1)

    def test_a_changed_graph_link_refuses_only_the_values_below_it(self):
        result = snapshot_run(r'''
update=update or function()end
local stratagem_writes=require('hd2runtime/domains/stratagem_writes')
local tesla=hd2.stratagem('A/ARC-3 Tesla Tower'):deployed_entity():weapon('primary')
local reviewed=require('hd2runtime/api/inspect').reviewed
local D=reviewed(tesla:attack('primary_damage'),'damage.standard_damage')
local R=reviewed(tesla:attack('primary'),F.arc.range)
local S=reviewed(tesla:attack('primary_damage_status_1'),F.status.duration)
check(D and R and S,'reviewed values')
-- Another mod swapped the status the Tesla Tower's DamageInfo row applies (slot 1 type, +44): the link from that row
-- to its stun status row no longer holds. Only the status row's own values hang below that link.
local damage=resolve('patch',{id='where',target=tesla:attack('primary_damage'),allow_shared=true,
 field='damage.standard_damage',expect=D,value=D+1})[1]
local slot=damage.at-4+44
overlay[slot]=b.encode(5,'u32')
-- The chains each write depends on: its own node and every node above it, nothing else.
local spec=require('hd2runtime/domains/patches').validate({id='p',target=tesla:attack('primary_damage'),allow_shared=true,
 field='damage.standard_damage',expect=D,value=D+1})
local entry=require('hd2runtime/domains/stratagem_authoring').stratagems['A/ARC-3 Tesla Tower']
local paths=stratagem_writes.graph_paths(entry,spec)
check(paths['weapon:primary/attack:primary/damage']and paths['weapon:primary/attack:primary']
 and paths['weapon:primary']and not paths['weapon:primary/attack:primary/damage/status:1'],'graph paths')
local h={}
events.run_as('mods/alice/tesla',function()
 h.damage=hd2.ensure({patch={id='damage',target=tesla:attack('primary_damage'),allow_shared=true,field='damage.standard_damage',
  expect=D,value=D*2}})
 h.range=hd2.ensure({patch={id='range',target=tesla:attack('primary'),allow_shared=true,field=F.arc.range,
  expect=R,value=R+10}})
 h.duration=hd2.ensure({patch={id='duration',target=tesla:attack('primary_damage_status_1'),allow_shared=true,
  field=F.status.duration,expect=S,value=S*2}})
end)
settle({h.damage,h.range,h.duration})
check(h.damage.runs>=1 and h.damage.result.status=='APPLIED','damage '..tostring(h.damage.error))
check(h.range.runs>=1 and h.range.result.status=='APPLIED','range '..tostring(h.range.error))
check(h.duration.status=='rejected'and tostring(h.duration.error):find('damage status link changed',1,true),
 'duration '..tostring(h.duration.status)..' '..tostring(h.duration.error))
check(runtime.read(slot,4)==b.encode(5,'u32'),'the other mod link was overwritten')
local job=hd2.inspect({target=tesla:attack('primary_damage_status_1'),fields={F.status.duration}})
settle({job})
local d=job.result.fields[1]
return json.encode({state=d.state,reason=d.reason})
''')
        self.assertEqual(result['state'], 'changed', result)
        self.assertIn('damage status link changed', result['reason'])


if __name__ == '__main__':
    unittest.main()
