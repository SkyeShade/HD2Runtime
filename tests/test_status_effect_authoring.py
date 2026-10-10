"""Status effect stats (0.31.0): hd2.status_effect(id) edits a status definition itself (its duration) and, through
:damage(), the DamageInfo row it deals while active (domains/status_effect_writes.lua,
scripts/generate_status_effect_authoring.py).

The snapshot tests run on a copy-on-write overlay of the retained current-build snapshot (no game process).
"""
import json
import unittest

from support import ROOT, run
from test_multi_mod_composition import build_profile, snapshot_run


class CatalogueTests(unittest.TestCase):
    def test_generated_catalogue_is_current(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_status_effect_authoring
        self.assertEqual(generate_status_effect_authoring.generate(check=True), [])

    def test_every_status_and_its_tick_damage(self):
        document = json.loads((ROOT / 'sdk/StatusEffectAuthoringCapabilities.json').read_text(encoding='utf-8'))
        by_id = {s['semanticId']: s for s in document['statuses']}
        self.assertEqual(len(by_id), 71)
        fire = by_id['fire']
        self.assertEqual(fire['fields'][0]['semanticFieldId'], 'status.duration')
        self.assertEqual(fire['fields'][0]['currentDefault'], 3.0)
        damage = {f['semanticFieldId']: f['currentDefault'] for f in fire['tickDamage']['fields']}
        self.assertEqual((damage['damage.standard_damage'], damage['damage.durable_damage'], damage['damage.ap_direct']),
                         (100, 100, 4))
        # Gas, the second gas status and gloom deal one DamageInfo row: each names the others.
        self.assertEqual(by_id['gas']['tickDamage']['sharedWithStatuses'], ['gas_2', 'gloom'])
        self.assertEqual(by_id['gloom']['tickDamage']['sharedWithStatuses'], ['gas', 'gas_2'])
        # Stuns deal no tick damage.
        self.assertIsNone(by_id['stun_medium']['tickDamage'])
        # +36 and the tick rate stay unnamed and read-only.
        self.assertEqual([m['member'] for m in document['notExposed']][:2], ['StatusEffectInfo +36', 'tick rate'])

    def test_validation(self):
        self.assertEqual(run(r'''
local hd2=require('hd2runtime/api/hd2')
local patches=require('hd2runtime/domains/patches')
local function fails(request,text)
 local ok,why=pcall(patches.validate,request)
 assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
local fire=hd2.status_effect('fire')
assert(fire.resource=='status_effect'and fire.status=='fire'and fire.path=='status')
assert(fire:damage().path=='damage')
local d=fire:describe()
assert(d.id=='fire'and d.name=='Fire'and d.tickDamage==true and #d.fields==1 and d.fields[1].currentDefault==3)
assert(#fire:damage():describe().fields==9)
assert(not pcall(hd2.status_effect,'Fire'),'display names are not ids')
assert(not pcall(function()return hd2.status_effect('stun_medium'):damage()end),'a stun has no tick damage')
local ids=hd2.status_effects();assert(#ids==71 and ids[1]<ids[2])
fails({id='a',target=fire,field='status.duration',expect=3,value=5},'shared field requires allow_shared=true')
fails({id='a',target=fire,allow_shared=true,field='status.duration',expect=2,value=5},'expect differs')
fails({id='a',target=fire,allow_shared=true,field='status.duration',expect=3,value=-1},'outside the reviewed range')
fails({id='a',target=fire:damage(),allow_shared=true,field='damage.standard_damage',expect=100,value=50},
 'allow_unverified_effect')
fails({id='a',target=fire:damage(),allow_shared=true,allow_unverified_effect=true,field='damage.standard_damage',
 expect=100,value=50.5},'integer')
fails({id='a',target=fire,allow_shared=true,field='damage.standard_damage',expect=100,value=50},'not exposed')
local gas=patches.validate({id='a',target=hd2.status_effect('gas'):damage(),allow_shared=true,allow_unverified_effect=true,
 field='damage.standard_damage',expect=25,value=50})
assert(gas.kind=='status_effect'and gas.changes[1].descriptor.backing.settings=='damage')
-- The shared-record index ties the gas tick row to the other statuses that deal it.
local records=require('hd2runtime/core/shared_records')
local others={}
for _,g in ipairs(records.others(gas.changes[1].descriptor))do others[#others+1]=g.resource..' '..g.target end
table.sort(others)
assert(table.concat(others,',')=='status_effect gas_2,status_effect gloom',table.concat(others,','))
-- And the status row's duration to every attack that applies it.
local dur=patches.validate({id='a',target=hd2.status_effect('stun_small'),allow_shared=true,field='status.duration',
 expect=1.5,value=3})
local users={}
for _,g in ipairs(records.others(dur.changes[1].descriptor))do users[g.resource..' '..g.target]=true end
assert(users['support_weapon ARC-3 Arc Thrower']and users['stratagem A/ARC-3 Tesla Tower'],'stun users')
return 'ok'
'''), b'ok')


@unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained current-build snapshot not available')
class StatusEffectSnapshotTests(unittest.TestCase):
    def test_duration_and_tick_damage_write_their_rows_only(self):
        result = snapshot_run(r'''
update=update or function()end
local fire=hd2.status_effect('fire')
local gas=hd2.status_effect('gas'):damage()
local duration=resolve('patch',{id='d',target=fire,allow_shared=true,field='status.duration',expect=3,value=6})[1]
local tick=resolve('patch',{id='t',target=gas,allow_shared=true,allow_unverified_effect=true,
 field='damage.standard_damage',expect=25,value=40})[1]
check(duration.before==b.encode(3,'f32'),'fire duration bytes '..b.hex(duration.before))
check(tick.before==b.encode(25,'i32'),'gas tick bytes '..b.hex(tick.before))
local h={}
events.run_as('mods/alice/status',function()
 h.duration=hd2.ensure({patch={id='fire-duration',target=fire,allow_shared=true,field='status.duration',
  expect=3,value=6}})
 h.tick=hd2.ensure({transaction={id='gas-tick',target=gas,allow_shared=true,allow_unverified_effect=true,changes={
  {field='damage.standard_damage',expect=25,value=40},{field='damage.durable_damage',expect=25,value=40}}}})
end)
settle({h.duration,h.tick})
check(h.duration.runs>=1 and h.duration.result.status=='APPLIED','duration '..tostring(h.duration.error))
check(h.tick.runs>=1 and h.tick.result.status=='APPLIED','tick '..tostring(h.tick.error))
check(runtime.read(duration.at,4)==b.encode(6,'f32'),'fire duration not written')
check(runtime.read(tick.at,4)==b.encode(40,'i32'),'gas tick damage not written')
-- Exactly the three fields' bytes changed.
local written=0
for at,bytes in pairs(overlay)do written=written+1 end
check(written==3,'overlay entries '..written)
-- inspect reports the values as alice's.
local job=hd2.inspect({target=fire,fields={'status.duration'}})
settle({job})
local f=job.result.fields[1]
check(f.state=='runtime'and f.owner=='mods/alice/status'and math.abs(f.value-6)<1e-6,'inspect '..tostring(f.state))
-- Another mod changed gas_2's own tick link (+44) in its data files: its damage target refuses, gas's still holds.
local gas2=resolve('patch',{id='g2',target=hd2.status_effect('gas_2'),allow_shared=true,field='status.duration',
 expect=10,value=11})[1]
overlay[gas2.at-40+44]=b.encode(519,'u32')
local bob
events.run_as('mods/bob/status',function()
 bob=hd2.ensure({patch={id='gas2-tick',target=hd2.status_effect('gas_2'):damage(),allow_shared=true,
  allow_unverified_effect=true,field='damage.ap_direct',expect=6,value=7}})
end)
settle({bob})
check(bob.status=='rejected'and tostring(bob.error):find('tick damage link changed',1,true),'gas_2 '..tostring(bob.error))
return json.encode({ok=true})
''')
        self.assertTrue(result['ok'])


if __name__ == '__main__':
    unittest.main()
